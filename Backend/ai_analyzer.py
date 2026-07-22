###############################################################################
# AI Cost Analyzer — AI Cloud Cost Detective
#
# Takes AWS resource scan results and sends them to OpenAI for cost analysis.
# Returns structured findings with severity, estimated savings, and
# actionable AWS CLI fix commands.
###############################################################################

import os
import json
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")


class AIAnalyzerError(Exception):
    """Raised when the AI analysis fails."""
    pass


SYSTEM_PROMPT = """You are an expert AWS Cloud Cost Optimization Analyst. 
You analyze AWS resources and identify cost-saving opportunities.

When analyzing resources, look for:
1. **Over-provisioned resources** — EC2 instances, RDS databases, or Lambda functions sized larger than needed
2. **Unused/idle resources** — Unattached EBS volumes, unassociated Elastic IPs, idle load balancers, stopped instances still incurring storage costs
3. **Misconfigurations** — Wrong pricing tiers, missing auto-shutdown schedules, no reserved instances or savings plans, no lifecycle policies
4. **Storage costs** — Excessive EBS volumes, S3 buckets without lifecycle policies, old snapshots
5. **Networking costs** — NAT Gateway data processing charges, unused Elastic IPs ($3.60/month each), cross-AZ data transfer

For each issue found, provide:
- A clear title
- Severity: "high", "medium", or "low"
- The specific resource affected
- Estimated monthly savings (in USD)
- An explanation of why this is a cost issue
- An actionable fix using AWS CLI commands

Respond ONLY in valid JSON format with this exact structure:
{
  "summary": "Brief overall summary of the cost analysis",
  "total_estimated_monthly_savings": 0.00,
  "issues": [
    {
      "title": "Issue title",
      "severity": "high|medium|low",
      "resource_type": "EC2 Instance",
      "resource_id": "i-0123456789abcdef0",
      "resource_name": "my-instance",
      "estimated_monthly_savings": 0.00,
      "explanation": "Why this is a cost issue",
      "fix_command": "aws ec2 ... (CLI command to fix)"
    }
  ],
  "recommendations": [
    "General recommendation 1",
    "General recommendation 2"
  ]
}
"""


async def analyze_resources(scan_result: dict, cost_flags: list[dict] | None = None) -> dict:
    """
    Send scanned AWS resources + cost detector flags to Gemini for analysis.

    Args:
        scan_result: The output from aws_scanner.scan_all_resources()
        cost_flags: The output from cost_detector.detect_cost_flags()

    Returns:
        Structured cost analysis with issues, savings, and fix commands
    """
    if not GEMINI_API_KEY:
        raise AIAnalyzerError(
            "Gemini API key not configured. Set GEMINI_API_KEY in your .env file."
        )

    # Build the user prompt with resource data
    resource_data = json.dumps(scan_result["resources"], indent=2, default=str)

    # Include pre-detected cost flags if available
    flags_section = ""
    if cost_flags:
        flags_data = json.dumps(cost_flags, indent=2, default=str)
        flags_section = f"""
**Pre-Detected Cost Issues ({len(cost_flags)} found):**
{flags_data}

Review these pre-detected issues, validate them, and add any additional issues you find.
"""

    user_prompt = f"""Analyze the following AWS resources for cost optimization opportunities.

**AWS Account:** {scan_result['account_id']}
**Region:** {scan_result['region']}
**Total Resources Found:** {scan_result['total_resources']}

**Resource Summary:**
{json.dumps(scan_result['resource_summary'], indent=2)}
{flags_section}
**Detailed Resource Data:**
{resource_data}

Provide a comprehensive cost analysis with specific, actionable recommendations.
If there are no issues, still provide general best-practice recommendations.
Respond ONLY with valid JSON matching the specified schema."""

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.3,
                max_output_tokens=4096,
                response_mime_type="application/json",
            )
        )

        # Parse the response
        content = response.text
        analysis = json.loads(content)

        # Add metadata
        analysis["model_used"] = GEMINI_MODEL
        analysis["region"] = scan_result["region"]
        analysis["account_id"] = scan_result["account_id"]
        analysis["resources_analyzed"] = scan_result["total_resources"]
        analysis["pre_detected_flags"] = len(cost_flags) if cost_flags else 0

        return analysis

    except json.JSONDecodeError as e:
        raise AIAnalyzerError(f"Failed to parse AI response as JSON: {e}")
    except Exception as e:
        raise AIAnalyzerError(f"Unexpected error during AI analysis: {e}")
