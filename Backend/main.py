###############################################################################
# FastAPI Backend — AI Cloud Cost Detective
#
# Endpoints:
#   - GET  /api/health                    → Health check
#   - GET  /api/regions                   → List AWS regions
#   - POST /api/scan                      → Scan resources in a region
#   - POST /api/detect                    → Scan + rule-based cost detection
#   - POST /api/analyze                   → Scan + detect + AI analysis
#   - GET  /api/history                   → Past analyses (auth required)
#   - GET  /api/analysis/{id}             → Single analysis result
#   - WS   /ws/progress/{analysis_id}     → Live progress updates
###############################################################################

import asyncio
import uuid
import json
from contextlib import asynccontextmanager
from collections import defaultdict

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Query, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, EmailStr
from dotenv import load_dotenv

from aws_scanner import (
    list_regions,
    scan_all_resources,
    AWSCredentialsError,
    AWSRegionError,
    AWSScannerError,
)
from ai_analyzer import analyze_resources, AIAnalyzerError
from cost_detector import detect_cost_flags
from db import (
    init_db, close_pool, create_analysis, update_analysis_status, 
    save_analysis_result, get_analysis_by_id, get_user_analyses,
    create_user, get_user_by_email
)
from auth import verify_password, get_password_hash, create_access_token, verify_access_token

load_dotenv()


# ─── WebSocket Progress Manager ─────────────────────────────────────────────

class ProgressManager:
    """Manages WebSocket connections for live progress updates."""

    def __init__(self):
        # analysis_id -> list of connected WebSockets
        self.connections: dict[str, list[WebSocket]] = defaultdict(list)

    async def connect(self, analysis_id: str, websocket: WebSocket):
        await websocket.accept()
        self.connections[analysis_id].append(websocket)

    def disconnect(self, analysis_id: str, websocket: WebSocket):
        if analysis_id in self.connections:
            self.connections[analysis_id] = [
                ws for ws in self.connections[analysis_id] if ws != websocket
            ]
            if not self.connections[analysis_id]:
                del self.connections[analysis_id]

    async def send_progress(self, analysis_id: str, step: str, progress: int, message: str):
        """Send a progress update to all connected clients for an analysis."""
        payload = json.dumps({
            "analysis_id": analysis_id,
            "step": step,
            "progress": progress,
            "message": message,
        })
        if analysis_id in self.connections:
            dead = []
            for ws in self.connections[analysis_id]:
                try:
                    await ws.send_text(payload)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self.disconnect(analysis_id, ws)


progress_manager = ProgressManager()


# ─── App Lifecycle ───────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB on startup, close pool on shutdown."""
    try:
        await init_db()
        print("✅ Database initialized")
    except Exception as e:
        print(f"⚠️  Database init failed (app will still run): {e}")
    yield
    await close_pool()


# ─── App Setup ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="AI Cloud Cost Detective",
    description="AI-powered AWS cloud cost analysis tool",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
        "http://localhost:5176",
        "http://localhost:5177",
        "http://localhost:5178",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Request Models ─────────────────────────────────────────────────────────

class ScanRequest(BaseModel):
    region: str = Field(..., description="AWS region to scan", examples=["us-east-1"])

class AnalyzeRequest(BaseModel):
    region: str = Field(..., description="AWS region to analyze", examples=["us-east-1"])
    user_id: str | None = Field(None, description="User ID (for saving to history)")


class AuthRequest(BaseModel):
    email: EmailStr
    password: str

# ─── Auth Dependencies ──────────────────────────────────────────────────────

async def get_current_user(authorization: str = Header(None)):
    """Dependency to extract and verify JWT from Authorization header."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail={"error": "unauthorized", "message": "Missing or invalid token"})
    
    token = authorization.split(" ")[1]
    payload = verify_access_token(token)
    if not payload or not payload.get("sub"):
        raise HTTPException(status_code=401, detail={"error": "unauthorized", "message": "Expired or invalid token"})
    
    return payload["sub"] # Returns user ID

# ─── Auth Endpoints ─────────────────────────────────────────────────────────

@app.post("/api/auth/signup")
async def signup(request: AuthRequest):
    """Create a new user account."""
    existing_user = await get_user_by_email(request.email)
    if existing_user:
        raise HTTPException(status_code=400, detail={"error": "email_taken", "message": "Email already in use"})
    
    hashed_password = get_password_hash(request.password)
    user = await create_user(request.email, hashed_password)
    
    access_token = create_access_token(data={"sub": str(user["id"])})
    return {"success": True, "token": access_token, "user": {"id": user["id"], "email": user["email"]}}

@app.post("/api/auth/login")
async def login(request: AuthRequest):
    """Log in an existing user."""
    user = await get_user_by_email(request.email)
    if not user or not verify_password(request.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail={"error": "invalid_credentials", "message": "Incorrect email or password"})
    
    access_token = create_access_token(data={"sub": str(user["id"])})
    return {"success": True, "token": access_token, "user": {"id": user["id"], "email": user["email"]}}

# ─── Endpoints ───────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "service": "ai-cost-detective"}


@app.get("/api/regions")
async def get_regions(current_user_id: str = Depends(get_current_user)):
    """List all available AWS regions."""
    try:
        regions = list_regions()
        return {"success": True, "regions": regions, "count": len(regions)}
    except AWSCredentialsError as e:
        raise HTTPException(status_code=401, detail={"error": "aws_credentials_error", "message": str(e)})
    except AWSScannerError as e:
        raise HTTPException(status_code=500, detail={"error": "scanner_error", "message": str(e)})


@app.get("/api/org-users")
async def get_org_users(current_user_id: str = Depends(get_current_user)):
    """List all users in the organization for cross-user cost analysis."""
    from db import get_all_users
    try:
        users = await get_all_users()
        return {"success": True, "users": users}
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "database_error", "message": str(e)})


@app.post("/api/scan")
async def scan_resources(request: ScanRequest):
    """Scan all AWS resources in the specified region."""
    try:
        result = scan_all_resources(region=request.region)
        return {"success": True, **result}
    except AWSCredentialsError as e:
        raise HTTPException(status_code=401, detail={"error": "aws_credentials_error", "message": str(e)})
    except AWSRegionError as e:
        raise HTTPException(status_code=400, detail={"error": "invalid_region", "message": str(e)})
    except AWSScannerError as e:
        raise HTTPException(status_code=500, detail={"error": "scanner_error", "message": str(e)})


@app.post("/api/detect")
async def detect_costs(request: ScanRequest):
    """Scan + rule-based cost detection (no AI, fast and free)."""
    try:
        scan_result = scan_all_resources(region=request.region)
    except AWSCredentialsError as e:
        raise HTTPException(status_code=401, detail={"error": "aws_credentials_error", "message": str(e)})
    except (AWSRegionError, AWSScannerError) as e:
        raise HTTPException(status_code=400, detail={"error": "scan_error", "message": str(e)})

    flags = detect_cost_flags(scan_result)
    total_savings = sum(f.get("estimated_monthly_savings", 0) for f in flags)

    return {
        "success": True,
        "scan": {
            "region": scan_result["region"],
            "account_id": scan_result["account_id"],
            "total_resources": scan_result["total_resources"],
            "resource_summary": scan_result["resource_summary"],
        },
        "detection": {
            "total_flags": len(flags),
            "total_estimated_monthly_savings": round(total_savings, 2),
            "flags": flags,
        },
    }


@app.post("/api/analyze")
async def analyze_cost(request: AnalyzeRequest, current_user_id: str = Depends(get_current_user)):
    """
    Full pipeline: Scan → Detect → AI Analysis → Save to DB.

    Progress is streamed via WebSocket at /ws/progress/{analysis_id}.
    """
    # Create analysis record in DB
    analysis_id = str(uuid.uuid4())
    try:
        analysis_id = await create_analysis(
            user_id=request.user_id,
            region=request.region,
        )
    except Exception:
        pass  # DB might not be available; continue without persistence

    # Step 1: Scan resources
    await progress_manager.send_progress(analysis_id, "scanning", 10, f"Scanning resources in {request.region}...")

    try:
        scan_result = scan_all_resources(region=request.region)
    except AWSCredentialsError as e:
        await progress_manager.send_progress(analysis_id, "error", 0, f"AWS credentials error: {e}")
        raise HTTPException(status_code=401, detail={"error": "aws_credentials_error", "message": str(e)})
    except (AWSRegionError, AWSScannerError) as e:
        await progress_manager.send_progress(analysis_id, "error", 0, f"Scan error: {e}")
        raise HTTPException(status_code=500, detail={"error": "scanner_error", "message": str(e)})

    await progress_manager.send_progress(
        analysis_id, "scanning", 40,
        f"Found {scan_result['total_resources']} resources in {request.region}"
    )

    # Step 2: Rule-based cost detection
    await progress_manager.send_progress(analysis_id, "detecting", 50, "Running cost detection rules...")
    cost_flags = detect_cost_flags(scan_result)
    total_savings = sum(f.get("estimated_monthly_savings", 0) for f in cost_flags)

    await progress_manager.send_progress(
        analysis_id, "detecting", 60,
        f"Detected {len(cost_flags)} cost issues (est. ${total_savings:.2f}/month savings)"
    )

    # Step 3: AI analysis
    await progress_manager.send_progress(analysis_id, "analyzing", 70, "Analyzing costs with AI...")
    try:
        await update_analysis_status(analysis_id, "analyzing")
    except Exception:
        pass

    try:
        analysis = await analyze_resources(scan_result, cost_flags=cost_flags)
    except AIAnalyzerError as e:
        await progress_manager.send_progress(analysis_id, "error", 70, f"AI analysis failed: {e}")
        try:
            await update_analysis_status(analysis_id, "partial")
            await save_analysis_result(
                analysis_id=analysis_id,
                resources_scanned=scan_result["total_resources"],
                issues_found=len(cost_flags),
                estimated_savings=total_savings,
                analysis_result={},
                detection_result={"flags": cost_flags},
                account_id=scan_result.get("account_id", ""),
            )
        except Exception:
            pass
        raise HTTPException(
            status_code=500,
            detail={
                "error": "ai_analysis_error",
                "message": str(e),
                "analysis_id": analysis_id,
                "detection": {
                    "total_flags": len(cost_flags),
                    "total_estimated_monthly_savings": round(total_savings, 2),
                    "flags": cost_flags,
                },
            },
        )

    # Step 4: Save to database
    await progress_manager.send_progress(analysis_id, "saving", 90, "Storing results in database...")
    ai_issues = len(analysis.get("issues", []))
    ai_savings = analysis.get("total_estimated_monthly_savings", 0)

    try:
        await save_analysis_result(
            analysis_id=analysis_id,
            resources_scanned=scan_result["total_resources"],
            issues_found=ai_issues,
            estimated_savings=float(ai_savings),
            analysis_result=analysis,
            detection_result={"flags": cost_flags, "total_flags": len(cost_flags)},
            account_id=scan_result.get("account_id", ""),
        )
    except Exception as e:
        print(f"⚠️  Failed to save analysis to DB: {e}")

    # Step 5: Done
    await progress_manager.send_progress(analysis_id, "complete", 100, "Analysis complete!")

    return {
        "success": True,
        "analysis_id": analysis_id,
        "scan": {
            "region": scan_result["region"],
            "account_id": scan_result["account_id"],
            "total_resources": scan_result["total_resources"],
            "resource_summary": scan_result["resource_summary"],
            "resources": scan_result["resources"],
        },
        "detection": {
            "total_flags": len(cost_flags),
            "total_estimated_monthly_savings": round(total_savings, 2),
            "flags": cost_flags,
        },
        "analysis": analysis,
    }


# ─── History Endpoints ──────────────────────────────────────────────────────

@app.get("/api/history")
async def get_history(user_id: str = Depends(get_current_user)):
    """Get past analyses for the authenticated user."""
    try:
        analyses = await get_user_analyses(user_id)
        return {"success": True, "analyses": analyses, "count": len(analyses)}
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "database_error", "message": str(e)})

@app.get("/api/analysis/{analysis_id}")
async def get_analysis(analysis_id: str, user_id: str = Depends(get_current_user)):
    """Get a single analysis result by ID for the authenticated user."""
    try:
        result = await get_analysis_by_id(analysis_id)
        if not result:
            raise HTTPException(status_code=404, detail={"error": "not_found", "message": "Analysis not found"})
        if str(result["user_id"]) != str(user_id):
            raise HTTPException(status_code=403, detail={"error": "forbidden", "message": "Not authorized to view this analysis"})
        return {"success": True, "analysis": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "database_error", "message": str(e)})


# ─── WebSocket ──────────────────────────────────────────────────────────────

@app.websocket("/ws/progress/{analysis_id}")
async def websocket_progress(websocket: WebSocket, analysis_id: str):
    """
    WebSocket endpoint for live progress updates during analysis.

    The frontend connects here before calling POST /api/analyze to
    receive real-time progress messages.
    """
    await progress_manager.connect(analysis_id, websocket)
    try:
        # Keep connection alive until client disconnects
        while True:
            # Wait for client messages (ping/pong keepalive)
            await websocket.receive_text()
    except WebSocketDisconnect:
        progress_manager.disconnect(analysis_id, websocket)
