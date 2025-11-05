from fastapi import APIRouter
from datetime import datetime

from config import get_settings

router = APIRouter(prefix="/healthz", tags=["health"])


@router.get("")
async def healthcheck():
    """Basic health check endpoint"""
    settings = get_settings()
    openai_ok = bool(settings.openai_api_key)
    return {
        "status": "ok",
        "app": settings.app_name,
        "env": settings.env,
        "openai_key_present": openai_ok,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/diagnostics")
async def diagnostics():
    """Comprehensive diagnostics endpoint for all external services"""
    settings = get_settings()
    
    results = {
        "timestamp": datetime.utcnow().isoformat(),
        "app": settings.app_name,
        "env": settings.env,
        "services": {}
    }
    
    # OpenAI
    results["services"]["openai"] = {
        "configured": bool(settings.openai_api_key),
        "model": settings.openai_model,
    }
    
    # Snowflake
    snowflake_status = {
        "enabled": settings.use_snowflake,
        "configured": bool(settings.snowflake_account and settings.snowflake_user),
    }
    
    if settings.use_snowflake and snowflake_status["configured"]:
        try:
            from services.db import fetch_dicts
            # Quick connectivity test
            result = fetch_dicts("SELECT CURRENT_VERSION() as version")
            snowflake_status["connected"] = True
            snowflake_status["version"] = result[0]['version'] if result else None
        except Exception as e:
            snowflake_status["connected"] = False
            snowflake_status["error"] = str(e)
    
    results["services"]["snowflake"] = snowflake_status
    
    # Email
    results["services"]["email"] = {
        "configured": bool(settings.smtp_password),
        "host": settings.smtp_host,
        "sender": settings.smtp_sender_email,
    }
    
    # BrightData
    results["services"]["brightdata"] = {
        "configured": bool(settings.brightdata_api_key),
        "zone": settings.brightdata_zone if settings.brightdata_api_key else None,
    }
    
    # Overall status
    critical_services = ["openai"]
    all_critical_ok = all(
        results["services"][svc].get("configured", False) 
        for svc in critical_services
    )
    
    results["status"] = "healthy" if all_critical_ok else "degraded"
    
    return results
