"""Sincronizzazione con Danea Easyfatt via CSV/Excel.

Danea Easyfatt esporta/importa in formato CSV (separatore ;, encoding Windows-1252).
Questo modulo gestisce:
- Import articoli da Danea → Anagrafica componenti
- Export componenti → formato Danea per import
- Mapping codici Danea ↔ codici interni
"""

import csv
import io
from pathlib import Path
from typing import AsyncGenerator

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mes_system.api.models.component import Component


# Mapping colonne Danea → campi interni
DANEA_COLUMN_MAP = {
    "Cod.": "danea_code",
    "Descrizione": "description",
    "Cod. Fornitore": "supplier_code",
    "Fornitore": "supplier_name",
    "Prezzo Acquisto": "last_price",
    "Unità di misura": "quantity_unit",
    "Note": "notes",
}


async def import_from_danea_csv(
    db: AsyncSession,
    file_path: str | Path,
    encoding: str = "cp1252",
    created_by: str = "DANEA_SYNC",
) -> dict:
    """Importa articoli da CSV Danea Easyfatt.

    Restituisce statistiche dell'import.
    """
    stats = {
        "total_rows": 0,
        "created": 0,
        "updated": 0,
        "errors": [],
    }

    df = pd.read_csv(
        file_path,
        sep=";",
        encoding=encoding,
        dtype=str,
        na_filter=False,
    )

    stats["total_rows"] = len(df)

    for _, row in df.iterrows():
        try:
            danea_code = row.get("Cod.", "").strip()
            if not danea_code:
                continue

            # Cerca componente esistente per codice Danea
            result = await db.execute(
                select(Component).where(Component.danea_code == danea_code)
            )
            component = result.scalar_one_or_none()

            description = row.get("Descrizione", "").strip()

            if component:
                # Aggiorna
                if description:
                    component.description = description
                stats["updated"] += 1
            else:
                # Il componente va creato manualmente con categoria/sottocategoria
                # Qui creiamo solo un placeholder
                stats["errors"].append(
                    f"Codice Danea '{danea_code}' non trovato in anagrafica. "
                    f"Descrizione: '{description}'. Da creare manualmente con categoria."
                )

        except Exception as e:
            stats["errors"].append(f"Errore riga {_}: {str(e)}")

    await db.flush()
    return stats


async def export_to_danea_csv(
    db: AsyncSession,
    output_path: str | Path,
    encoding: str = "cp1252",
) -> int:
    """Esporta componenti in formato CSV compatibile con Danea.

    Restituisce il numero di righe esportate.
    """
    result = await db.execute(
        select(Component).where(Component.danea_code.isnot(None)).order_by(Component.danea_code)
    )
    components = result.scalars().all()

    rows = []
    for c in components:
        rows.append({
            "Cod.": c.danea_code,
            "Descrizione": c.description or "",
            "Categoria": c.category,
            "Unità di misura": "pz",
        })

    df = pd.DataFrame(rows)
    df.to_csv(output_path, sep=";", encoding=encoding, index=False)

    return len(rows)


def parse_danea_ddt_csv(file_content: str | bytes, encoding: str = "cp1252") -> list[dict]:
    """Parsa un DDT esportato da Danea per verifica ricezione merce.

    Restituisce lista di righe con codice, descrizione, quantità.
    """
    if isinstance(file_content, bytes):
        file_content = file_content.decode(encoding)

    reader = csv.DictReader(io.StringIO(file_content), delimiter=";")
    lines = []

    for row in reader:
        lines.append({
            "danea_code": row.get("Cod.", "").strip(),
            "description": row.get("Descrizione", "").strip(),
            "quantity": float(row.get("Quantità", "0").replace(",", ".")),
            "unit": row.get("Unità di misura", "pz").strip(),
        })

    return lines
