"""MCP Server — Interfaccia Claude per il sistema MES/MRP/WMS.

Permette a Claude di interagire direttamente con il sistema:
- Cercare componenti
- Verificare giacenze
- Controllare copertura materiali
- Stato ordini di lavoro
- Stato spedizioni
- Generare documenti doganali
- Dashboard qualità
"""

from fastmcp import FastMCP
from sqlalchemy import select, func

from mes_system.db.database import async_session
from mes_system.api.models.component import Component
from mes_system.api.models.inventory import InventoryItem
from mes_system.api.models.work_order import WorkOrder
from mes_system.api.models.shipment import Shipment
from mes_system.api.services import (
    anagrafica_service,
    wms_service,
    bom_service,
    mrp_service,
    mes_service,
    shipment_service,
    quality_service,
)
from mes_system.api.schemas import ComponentSearchParams
from mes_system.api.schemas.mrp import MrpRunCreate

mcp = FastMCP("Trade Skill MES/MRP/WMS")


@mcp.tool()
async def component_search(query: str) -> dict:
    """Cerca componenti per MPN, descrizione, codice interno o produttore.

    Esempio: component_search("STM32") oppure component_search("RES 10K")
    """
    async with async_session() as db:
        params = ComponentSearchParams(query=query, page_size=20)
        items, total = await anagrafica_service.search_components(db, params)
        return {
            "total": total,
            "components": [
                {
                    "codice": c.internal_code,
                    "mpn": c.mpn,
                    "descrizione": c.description,
                    "produttore": c.manufacturer,
                    "categoria": c.category,
                    "package": c.package,
                    "danea_code": c.danea_code,
                }
                for c in items
            ],
        }


@mcp.tool()
async def stock_check(component_code: str) -> dict:
    """Verifica giacenza di un componente in tutti i magazzini.

    Usa il codice interno (es. TS-RES-0805-000001) o cerca per MPN.
    """
    async with async_session() as db:
        # Cerca per codice interno
        component = await anagrafica_service.get_component_by_code(db, component_code)

        # Se non trovato, cerca per MPN
        if not component:
            result = await db.execute(
                select(Component).where(Component.mpn == component_code).limit(1)
            )
            component = result.scalar_one_or_none()

        if not component:
            return {"error": f"Componente '{component_code}' non trovato"}

        stock = await wms_service.stock_check(db, component.id)
        return {
            "codice": stock.internal_code,
            "descrizione": stock.description,
            "quantita_totale": stock.total_quantity,
            "dettaglio_per_zona": [
                {
                    "zona": s.zone_id,
                    "nome_zona": s.zone_name,
                    "magazzino": s.warehouse_id,
                    "quantita": s.quantity,
                    "num_reel": s.items_count,
                }
                for s in stock.stock_by_zone
            ],
        }


@mcp.tool()
async def mrp_coverage(product_code: str, quantity: int) -> dict:
    """Verifica copertura materiali per produrre N pezzi di un prodotto.

    Esempio: mrp_coverage("ASSY-PCB-CTRL-001", 200)
    Restituisce per ogni componente: necessario, disponibile, mancante.
    """
    async with async_session() as db:
        try:
            coverage = await mrp_service.mrp_coverage(db, product_code, quantity)
            return {
                "prodotto": coverage.product_code,
                "quantita": coverage.quantity,
                "coperto_completamente": coverage.fully_covered,
                "componenti_critici": coverage.critical_count,
                "componenti_mancanti": coverage.missing_count,
                "dettaglio": [
                    {
                        "codice": item.component_code,
                        "descrizione": item.description,
                        "necessario": item.quantity_needed,
                        "disponibile": item.quantity_on_hand,
                        "in_transito": item.quantity_in_transit,
                        "fabbisogno_netto": item.net_requirement,
                        "stato": item.status,
                        "copertura_giorni": item.coverage_days,
                    }
                    for item in coverage.coverage_items
                ],
            }
        except ValueError as e:
            return {"error": str(e)}


@mcp.tool()
async def suggest_purchases(horizon_days: int = 30) -> dict:
    """Genera suggerimenti di acquisto per i prossimi N giorni.

    Esegue un ciclo MRP e restituisce la lista di materiali da ordinare.
    """
    async with async_session() as db:
        run = await mrp_service.run_mrp(db, MrpRunCreate(horizon_days=horizon_days))
        await db.commit()

        suggestions = []
        for s in run.suggestions:
            comp = await db.get(Component, s.component_id)
            suggestions.append({
                "componente": comp.internal_code if comp else str(s.component_id),
                "descrizione": comp.description if comp else None,
                "quantita_da_ordinare": float(s.quantity_to_order),
                "fornitore_suggerito": s.suggested_supplier,
                "ordinare_entro": str(s.order_by_date) if s.order_by_date else None,
                "necessario_entro": str(s.need_by_date) if s.need_by_date else None,
                "priorita": s.priority,
            })

        return {
            "run_id": str(run.id),
            "riepilogo": run.summary,
            "suggerimenti": suggestions,
        }


@mcp.tool()
async def production_status(site: str = "AL") -> dict:
    """Stato degli ordini di lavoro in corso.

    Parametri: site = "AL" (Albania) o "IT" (Italia)
    """
    async with async_session() as db:
        orders = await mes_service.list_work_orders(db, status="IN_PROGRESS", site=site)
        return {
            "sito": site,
            "ordini_in_corso": len(orders),
            "ordini": [
                {
                    "codice": wo.wo_code,
                    "prodotto": str(wo.product_id),
                    "pianificati": wo.quantity_planned,
                    "buoni": wo.quantity_good,
                    "scarti": wo.quantity_scrap,
                    "progresso": f"{((wo.quantity_good + wo.quantity_scrap) / wo.quantity_planned * 100):.0f}%" if wo.quantity_planned > 0 else "0%",
                    "priorita": wo.priority,
                    "stato": wo.status,
                }
                for wo in orders
            ],
        }


@mcp.tool()
async def shipment_status() -> dict:
    """Stato di tutte le spedizioni in corso (non ancora consegnate)."""
    async with async_session() as db:
        shipments = await shipment_service.list_shipments(db)
        active = [s for s in shipments if s.status not in ("DELIVERED",)]
        return {
            "spedizioni_attive": len(active),
            "spedizioni": [
                {
                    "codice": s.shipment_code,
                    "direzione": "Italia → Albania" if s.direction == "IT_TO_AL" else "Albania → Italia",
                    "stato": s.status,
                    "data_spedizione": str(s.ship_date) if s.ship_date else None,
                    "arrivo_previsto": str(s.expected_arrival) if s.expected_arrival else None,
                    "peso_kg": float(s.total_weight_kg) if s.total_weight_kg else None,
                    "valore_eur": float(s.total_value_eur) if s.total_value_eur else None,
                    "colli": s.total_packages,
                }
                for s in active
            ],
        }


@mcp.tool()
async def customs_docs(shipment_code: str) -> dict:
    """Genera documenti doganali per una spedizione.

    Restituisce packing list e dati raggruppati per codice TARIC.
    """
    async with async_session() as db:
        shipment = await shipment_service.get_shipment_by_code(db, shipment_code)
        if not shipment:
            return {"error": f"Spedizione '{shipment_code}' non trovata"}

        customs = await shipment_service.generate_customs_data(db, shipment.id)
        packing = await shipment_service.generate_packing_list(db, shipment.id)

        return {
            "spedizione": customs.shipment_code,
            "mittente": customs.sender,
            "destinatario": customs.receiver,
            "peso_totale_kg": customs.total_weight_kg,
            "valore_totale_eur": customs.total_value_eur,
            "colli": customs.total_packages,
            "raggruppamento_taric": customs.grouped_by_taric,
            "packing_list": {
                "righe": len(packing.lines),
                "totali": packing.totals,
            },
        }


@mcp.tool()
async def quality_dashboard() -> dict:
    """KPI qualità: NC aperte, ispezioni, trend difetti."""
    async with async_session() as db:
        dash = await quality_service.quality_dashboard(db)
        return {
            "nc_aperte": dash.open_nc_count,
            "nc_per_gravita": dash.nc_by_severity,
            "nc_per_origine": dash.nc_by_source,
            "ispezioni_oggi": dash.inspections_today,
            "first_pass_yield": dash.first_pass_yield,
        }


# ============================================
# TOOLS DANEA — Dati in tempo reale dal gestionale
# (via Bridge Agent sul PC locale + Cloudflare Tunnel)
# ============================================

@mcp.tool()
async def danea_cerca_articolo(query: str) -> dict:
    """Cerca un articolo nel gestionale Danea Easyfatt in tempo reale.

    Cerca per codice articolo o descrizione nel database SQL Server di Danea.
    Esempio: danea_cerca_articolo("STM32") o danea_cerca_articolo("condensatore 100nF")
    """
    from mes_system.bridge.client import DaneaBridgeClient
    client = DaneaBridgeClient()
    try:
        items = await client.search_articoli(query)
        return {
            "fonte": "Danea Easyfatt (tempo reale)",
            "risultati": len(items),
            "articoli": items,
        }
    except Exception as e:
        return {"error": f"Bridge Agent non raggiungibile: {e}. Verificare che sia attivo sul PC locale."}


@mcp.tool()
async def danea_giacenza(codice: str | None = None) -> dict:
    """Giacenze in tempo reale dal gestionale Danea.

    Senza parametri: tutte le giacenze > 0.
    Con codice: filtra per codice articolo.
    """
    from mes_system.bridge.client import DaneaBridgeClient
    client = DaneaBridgeClient()
    try:
        items = await client.get_giacenze(codice)
        return {
            "fonte": "Danea Easyfatt (tempo reale)",
            "articoli_con_giacenza": len(items),
            "giacenze": items,
        }
    except Exception as e:
        return {"error": f"Bridge Agent non raggiungibile: {e}"}


@mcp.tool()
async def danea_movimenti(codice: str | None = None, data_da: str | None = None) -> dict:
    """Movimenti di magazzino dal gestionale Danea.

    Parametri:
    - codice: filtra per codice articolo
    - data_da: data inizio in formato YYYY-MM-DD
    """
    from mes_system.bridge.client import DaneaBridgeClient
    client = DaneaBridgeClient()
    try:
        items = await client.get_movimenti(codice=codice, data_da=data_da)
        return {
            "fonte": "Danea Easyfatt (tempo reale)",
            "movimenti": len(items),
            "dettaglio": items,
        }
    except Exception as e:
        return {"error": f"Bridge Agent non raggiungibile: {e}"}


@mcp.tool()
async def danea_query(sql: str) -> dict:
    """Esegue una query SQL personalizzata sul database Danea (solo SELECT).

    Utile per query specifiche che non sono coperte dagli altri tool.
    Esempio: danea_query("SELECT TOP 10 * FROM Articoli WHERE Giacenza > 100")
    """
    from mes_system.bridge.client import DaneaBridgeClient
    client = DaneaBridgeClient()
    try:
        result = await client.custom_query(sql)
        return {
            "fonte": "Danea Easyfatt (tempo reale)",
            **result,
        }
    except Exception as e:
        return {"error": f"Errore query: {e}"}


if __name__ == "__main__":
    mcp.run()
