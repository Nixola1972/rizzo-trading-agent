"""Router Danea — Proxy verso il Bridge Agent locale per dati in tempo reale."""

from fastapi import APIRouter, HTTPException, Query

from mes_system.bridge.client import DaneaBridgeClient

router = APIRouter()


def get_client() -> DaneaBridgeClient:
    return DaneaBridgeClient()


@router.get("/health")
async def bridge_health():
    """Verifica connessione con il Bridge Agent sul PC Danea."""
    try:
        client = get_client()
        return await client.health()
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Bridge Agent non raggiungibile: {e}. "
                   f"Verificare che sia attivo sul PC locale e che il tunnel Cloudflare sia aperto."
        )


@router.get("/articoli")
async def search_articoli(
    search: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
):
    """Cerca articoli nel DB Danea in tempo reale."""
    try:
        client = get_client()
        return await client.search_articoli(search or "", limit)
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/articoli/{codice}")
async def get_articolo(codice: str):
    """Dettaglio articolo da Danea."""
    try:
        client = get_client()
        result = await client.get_articolo(codice)
        if not result:
            raise HTTPException(status_code=404, detail=f"Articolo {codice} non trovato in Danea")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/giacenze")
async def giacenze(
    codice: str | None = None,
    solo_positivi: bool = True,
):
    """Giacenze in tempo reale da Danea."""
    try:
        client = get_client()
        return await client.get_giacenze(codice, solo_positivi)
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/movimenti")
async def movimenti(
    codice: str | None = None,
    data_da: str | None = None,
    data_a: str | None = None,
):
    """Movimenti magazzino da Danea."""
    try:
        client = get_client()
        return await client.get_movimenti(codice, data_da, data_a)
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/tables")
async def tables():
    """Lista tabelle nel DB Danea (utile per esplorazione)."""
    try:
        client = get_client()
        return await client.list_tables()
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
