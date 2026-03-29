"""Configurazione centralizzata del sistema MES/MRP/WMS."""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/mes_tradeskill"
    database_echo: bool = False

    # App
    app_name: str = "Trade Skill MES/MRP/WMS"
    app_version: str = "0.1.0"
    debug: bool = False
    api_prefix: str = "/api/v1"

    # Auth
    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 480  # 8 ore

    # Azienda
    company_name: str = "Trade Skill S.R.L."
    company_prefix: str = "TS"

    # Magazzini default
    default_warehouse_it: str = "MAG-IT"
    default_warehouse_al: str = "MAG-AL"
    default_warehouse_transit: str = "MAG-TRANSIT"

    # Lead time trasporto IT→AL (giorni)
    transit_lead_time_days: int = 3

    # MRP
    mrp_default_horizon_days: int = 30
    mrp_safety_stock_days: int = 7

    # Danea sync
    danea_export_path: Optional[str] = None
    danea_import_path: Optional[str] = None

    # Supabase (opzionale, alternativa a database_url diretto)
    supabase_url: Optional[str] = None
    supabase_key: Optional[str] = None

    model_config = {
        "env_file": ".env",
        "env_prefix": "MES_",
    }


settings = Settings()
