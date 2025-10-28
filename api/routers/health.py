from fastapi import APIRouter

from config import get_settings

router = APIRouter(prefix="/healthz", tags=["health"])


@router.get("")
async def healthcheck():
    settings = get_settings()
    openai_ok = bool(settings.openai_api_key)
    return {
        "status": "ok",
        "app": settings.app_name,
        "env": settings.env,
        "openai_key_present": openai_ok,
    }
