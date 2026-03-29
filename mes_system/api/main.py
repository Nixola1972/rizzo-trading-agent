"""FastAPI Application — Trade Skill MES/MRP/WMS.

Avvio: uvicorn mes_system.api.main:app --reload --port 8000
Docs: http://localhost:8000/docs
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mes_system.config import settings
from mes_system.api.routers import (
    anagrafica,
    wms,
    bom,
    mrp,
    mes,
    shipments,
    quality,
)
from mes_system.telegram_bot.webhook import router as telegram_router


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Sistema integrato MES/MRP/WMS per Trade Skill S.R.L.\n\n"
            "Gestione produzione elettronica Italia-Albania.\n"
            "Moduli: Anagrafica, WMS, BOM, MRP, MES, Spedizioni, Qualità."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS — permette accesso da frontend React e PWA
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # In produzione: specificare domini
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API Routers
    prefix = settings.api_prefix

    app.include_router(
        anagrafica.router,
        prefix=f"{prefix}/anagrafica",
        tags=["Anagrafica Componenti"],
    )
    app.include_router(
        wms.router,
        prefix=f"{prefix}/wms",
        tags=["WMS - Magazzino"],
    )
    app.include_router(
        bom.router,
        prefix=f"{prefix}/bom",
        tags=["BOM - Distinte Base"],
    )
    app.include_router(
        mrp.router,
        prefix=f"{prefix}/mrp",
        tags=["MRP - Pianificazione"],
    )
    app.include_router(
        mes.router,
        prefix=f"{prefix}/mes",
        tags=["MES - Produzione"],
    )
    app.include_router(
        shipments.router,
        prefix=f"{prefix}/spedizioni",
        tags=["Spedizioni IT↔AL"],
    )
    app.include_router(
        quality.router,
        prefix=f"{prefix}/qualita",
        tags=["Qualità"],
    )

    # Telegram Bot Webhook
    app.include_router(
        telegram_router,
        prefix="/telegram",
        tags=["Telegram Bot"],
    )

    # Health check
    @app.get("/health")
    async def health():
        return {"status": "ok", "version": settings.app_version}

    @app.get("/")
    async def root():
        return {
            "sistema": settings.app_name,
            "versione": settings.app_version,
            "azienda": settings.company_name,
            "docs": "/docs",
            "moduli": [
                "Anagrafica Componenti",
                "WMS (Warehouse Management)",
                "BOM (Bill of Materials)",
                "MRP (Material Requirements Planning)",
                "MES (Manufacturing Execution)",
                "Spedizioni IT↔AL",
                "Qualità",
                "Telegram Bot (produzione vocale)",
            ],
        }

    return app


app = create_app()
