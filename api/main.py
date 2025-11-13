import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from routers import agent, agent_v2, auth, health, briefings, campaigns, crawl_poc

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
    app.include_router(auth.router)
    app.include_router(health.router)
    app.include_router(agent.router)
    
    # AgentV2 - new agentic architecture
    try:
        app.include_router(agent_v2.router)
        logging.info("✅ AgentV2 router loaded successfully")
    except Exception as e:
        logging.error(f"❌ Failed to load AgentV2 router: {e}")
        import traceback
        traceback.print_exc()
    
    app.include_router(briefings.router)
    app.include_router(campaigns.router)
    app.include_router(crawl_poc.router)

    # Initialize scheduler and load active campaigns
    @app.on_event("startup")
    async def startup_event():
        # Initialize scheduler in async context (needs event loop)
        from services.scheduler_service import get_scheduler
        scheduler = get_scheduler()  # This starts the scheduler with the event loop
        logging.info("✅ Scheduler started")
        
        # Then load campaigns in background thread (doesn't need event loop)
        import asyncio
        from concurrent.futures import ThreadPoolExecutor
        from services.scheduler_service import reload_all_campaigns
        
        def load_campaigns():
            try:
                reload_all_campaigns()
                logging.info("✅ Campaigns loaded and scheduled")
            except Exception as e:
                logging.error(f"Failed to load campaigns: {e}")
        
        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, load_campaigns)

    @app.on_event("shutdown")
    async def shutdown_event():
        from services.scheduler_service import get_scheduler
        scheduler = get_scheduler()
        if scheduler:
            scheduler.shutdown()
            logging.info("Scheduler shut down")

    return app


app = create_app()