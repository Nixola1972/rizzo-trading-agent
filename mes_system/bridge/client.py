"""Client per il MES cloud per chiamare il Bridge Agent locale.

Questo modulo viene usato dal MES (in cloud) per leggere dati
in tempo reale dal Danea SQL Server tramite il Bridge Agent.
"""

import httpx
from mes_system.config import settings


class DaneaBridgeClient:
    """Client HTTP per comunicare con il Bridge Agent sul PC locale.

    Il Bridge Agent è esposto via Cloudflare Tunnel con un URL tipo:
    https://danea-bridge-xxxxx.trycloudflare.com
    oppure un dominio personalizzato.
    """

    def __init__(self, bridge_url: str | None = None):
        self.bridge_url = (
            bridge_url
            or getattr(settings, "danea_bridge_url", None)
            or "http://localhost:8001"
        )

    async def health(self) -> dict:
        """Verifica che il bridge sia raggiungibile."""
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{self.bridge_url}/health")
            return resp.json()

    async def search_articoli(self, query: str, limit: int = 50) -> list[dict]:
        """Cerca articoli nel DB Danea."""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{self.bridge_url}/articoli",
                params={"search": query, "limit": limit},
            )
            resp.raise_for_status()
            return resp.json()

    async def get_articolo(self, codice: str) -> dict | None:
        """Dettaglio singolo articolo."""
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{self.bridge_url}/articoli/{codice}")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()

    async def get_giacenze(
        self,
        codice: str | None = None,
        solo_positivi: bool = True,
    ) -> list[dict]:
        """Giacenze in tempo reale da Danea."""
        params = {"solo_positivi": solo_positivi}
        if codice:
            params["codice"] = codice

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{self.bridge_url}/giacenze",
                params=params,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_movimenti(
        self,
        codice: str | None = None,
        data_da: str | None = None,
        data_a: str | None = None,
    ) -> list[dict]:
        """Movimenti di magazzino da Danea."""
        params = {}
        if codice:
            params["codice"] = codice
        if data_da:
            params["data_da"] = data_da
        if data_a:
            params["data_a"] = data_a

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{self.bridge_url}/movimenti",
                params=params,
            )
            resp.raise_for_status()
            return resp.json()

    async def custom_query(self, sql: str) -> dict:
        """Query SQL personalizzata (solo SELECT)."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.bridge_url}/query",
                params={"sql": sql},
            )
            resp.raise_for_status()
            return resp.json()

    async def list_tables(self) -> list[str]:
        """Lista tabelle nel DB."""
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{self.bridge_url}/tables")
            resp.raise_for_status()
            return resp.json().get("tables", [])
