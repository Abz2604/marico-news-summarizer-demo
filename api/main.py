import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from routers import agent, health, briefings, campaigns, crawl_poc

def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name, 
        debug=settings.debug,
        docs_url="/docs",              
        redoc_url="/redoc",            
        openapi_url="/openapi.json",   
        root_path="/backend"
    )

    # Logging configuration (Phase 0 diagnostics)
    level = logging.DEBUG if settings.debug else logging.INFO
    logging.getLogger().setLevel(level)
    # Tame noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)

    # CORS (Phase 0): allow local Next.js origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "https://insightingtool.maricoapps.biz",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers mounted under /api (Phase 0)
    app.include_router(health.router)
    app.include_router(agent.router)
    app.include_router(briefings.router)
    app.include_router(campaigns.router)
    app.include_router(crawl_poc.router)

    return app


app = create_app()