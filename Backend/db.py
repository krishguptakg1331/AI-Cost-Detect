###############################################################################
# Database Module — AI Cloud Cost Detective
#
# Connects to AWS RDS PostgreSQL (provisioned via Terraform).
# Manages tables: users, analyses
# Uses asyncpg for async database operations.
###############################################################################

import os
import json
import asyncpg
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://costdetective_admin:password@localhost:5432/costdetective"
)


class DatabaseError(Exception):
    """Raised when a database operation fails."""
    pass


# ─── Connection Pool ────────────────────────────────────────────────────────

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    """Get or create the database connection pool."""
    global _pool
    if _pool is None:
        try:
            _pool = await asyncpg.create_pool(
                DATABASE_URL,
                min_size=2,
                max_size=10,
                command_timeout=30,
            )
        except Exception as e:
            raise DatabaseError(f"Failed to connect to database: {e}")
    return _pool


async def close_pool():
    """Close the database connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


# ─── Table Creation ─────────────────────────────────────────────────────────

async def init_db():
    """Create tables if they don't exist. Called on app startup."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Enable UUID extension
        await conn.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";")

        # Users table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                email VARCHAR(255) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)

        # Analyses table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS analyses (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                region VARCHAR(50) NOT NULL,
                account_id VARCHAR(20),
                resources_scanned INTEGER DEFAULT 0,
                issues_found INTEGER DEFAULT 0,
                estimated_savings NUMERIC(10, 2) DEFAULT 0.00,
                analysis_result JSONB,
                detection_result JSONB,
                status VARCHAR(20) DEFAULT 'pending',
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)

        # Index for fast user history lookups
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_analyses_user_id
            ON analyses(user_id, created_at DESC);
        """)


# ─── User Operations ────────────────────────────────────────────────────────

async def create_user(email: str, password_hash: str) -> dict:
    """Create a new user and return their record."""
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO users (email, password_hash)
                VALUES ($1, $2)
                RETURNING id, email, created_at
                """,
                email, password_hash,
            )
            return dict(row)
    except asyncpg.UniqueViolationError:
        raise DatabaseError(f"User with email {email} already exists")
    except Exception as e:
        raise DatabaseError(f"Failed to create user: {e}")


async def get_user_by_email(email: str) -> dict | None:
    """Get a user by email."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, email, password_hash, created_at FROM users WHERE email = $1",
            email,
        )
        return dict(row) if row else None


async def get_user_by_id(user_id: str) -> dict | None:
    """Get a user by ID."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, email, created_at FROM users WHERE id = $1::uuid",
            user_id,
        )
        return dict(row) if row else None


async def get_all_users() -> list[dict]:
    """Get all users in the organization and their most recently used region."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT u.id, u.email, u.created_at,
                   (SELECT region FROM analyses a WHERE a.user_id = u.id ORDER BY created_at DESC LIMIT 1) as latest_region
            FROM users u
            ORDER BY u.email ASC
        """)
        return [dict(row) for row in rows]


# ─── Analysis Operations ────────────────────────────────────────────────────

async def create_analysis(
    user_id: str | None,
    region: str,
    account_id: str = "",
) -> str:
    """Create a new analysis record and return its ID."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO analyses (user_id, region, account_id, status)
            VALUES ($1::uuid, $2, $3, 'scanning')
            RETURNING id
            """,
            user_id, region, account_id,
        )
        return str(row["id"])


async def update_analysis_status(analysis_id: str, status: str):
    """Update the status of an analysis."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE analyses SET status = $1 WHERE id = $2::uuid",
            status, analysis_id,
        )


async def save_analysis_result(
    analysis_id: str,
    resources_scanned: int,
    issues_found: int,
    estimated_savings: float,
    analysis_result: dict,
    detection_result: dict,
    account_id: str = "",
):
    """Save the completed analysis results."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE analyses SET
                account_id = $1,
                resources_scanned = $2,
                issues_found = $3,
                estimated_savings = $4,
                analysis_result = $5::jsonb,
                detection_result = $6::jsonb,
                status = 'completed'
            WHERE id = $7::uuid
            """,
            account_id,
            resources_scanned,
            issues_found,
            estimated_savings,
            json.dumps(analysis_result, default=str),
            json.dumps(detection_result, default=str),
            analysis_id,
        )


async def get_analysis_by_id(analysis_id: str) -> dict | None:
    """Get a single analysis by ID."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, user_id, region, account_id, resources_scanned,
                   issues_found, estimated_savings, analysis_result,
                   detection_result, status, created_at
            FROM analyses WHERE id = $1::uuid
            """,
            analysis_id,
        )
        if not row:
            return None
        result = dict(row)
        # Parse JSONB fields
        if result.get("analysis_result"):
            result["analysis_result"] = json.loads(result["analysis_result"]) if isinstance(result["analysis_result"], str) else result["analysis_result"]
        if result.get("detection_result"):
            result["detection_result"] = json.loads(result["detection_result"]) if isinstance(result["detection_result"], str) else result["detection_result"]
        return result


async def get_user_analyses(user_id: str, limit: int = 20) -> list[dict]:
    """Get analysis history for a user, most recent first."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, region, account_id, resources_scanned, issues_found,
                   estimated_savings, status, created_at
            FROM analyses
            WHERE user_id = $1::uuid
            ORDER BY created_at DESC
            LIMIT $2
            """,
            user_id, limit,
        )
        return [dict(row) for row in rows]
