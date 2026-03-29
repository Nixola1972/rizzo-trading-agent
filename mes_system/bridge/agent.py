"""Bridge Agent — Gira sul PC locale dove c'è Danea/SQL Server.

Questo servizio fa da ponte tra il database locale di Danea Easyfatt
(SQL Server) e il sistema MES in cloud.

SETUP:
1. Installa sul PC locale: pip install -r bridge_requirements.txt
2. Configura .env con la stringa di connessione SQL Server
3. Installa Cloudflare Tunnel: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/
4. Avvia: python -m mes_system.bridge.agent
5. Configura tunnel: cloudflared tunnel --url http://localhost:8001

L'agent espone API REST che il MES cloud chiama per leggere dati Danea in tempo reale.
"""

import os
import logging
from datetime import datetime
from contextlib import asynccontextmanager

import pyodbc
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# === Configurazione connessione SQL Server locale ===

# Stringa connessione per Imex-Stock / Danea SQL Server
# Formato tipico: DRIVER={SQL Server};SERVER=localhost\SQLEXPRESS;DATABASE=ImexStock;Trusted_Connection=yes;
SQL_CONNECTION_STRING = os.environ.get(
    "DANEA_SQL_CONNECTION",
    "DRIVER={SQL Server};SERVER=localhost\\SQLEXPRESS;DATABASE=ImexStock;Trusted_Connection=yes;"
)


def get_sql_connection():
    """Connessione al SQL Server locale."""
    try:
        conn = pyodbc.connect(SQL_CONNECTION_STRING)
        return conn
    except Exception as e:
        logger.error(f"Errore connessione SQL Server: {e}")
        raise


# === Modelli Response ===

class ArticoloResponse(BaseModel):
    codice: str
    descrizione: str | None = None
    giacenza: float | None = None
    prezzo: float | None = None
    fornitore: str | None = None
    unita_misura: str | None = None
    codice_fornitore: str | None = None


class GiacenzaResponse(BaseModel):
    codice: str
    descrizione: str | None = None
    giacenza: float
    magazzino: str | None = None
    ultimo_movimento: str | None = None


class MovimentoResponse(BaseModel):
    data: str
    tipo: str
    codice_articolo: str
    descrizione: str | None = None
    quantita: float
    documento: str | None = None
    causale: str | None = None


class DaneaSyncStatus(BaseModel):
    connected: bool
    database: str
    last_check: str
    articles_count: int | None = None
    error: str | None = None


# === FastAPI App (gira in locale) ===

app = FastAPI(
    title="Trade Skill - Danea Bridge Agent",
    version="0.1.0",
    description="Ponte locale tra Danea Easyfatt / SQL Server e il sistema MES in cloud.",
)


@app.get("/health")
async def health():
    """Verifica che il bridge sia attivo e connesso al DB."""
    try:
        conn = get_sql_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        conn.close()
        return {"status": "ok", "database": "connected", "timestamp": datetime.now().isoformat()}
    except Exception as e:
        return {"status": "error", "database": "disconnected", "error": str(e)}


@app.get("/status", response_model=DaneaSyncStatus)
async def sync_status():
    """Stato della connessione e statistiche DB."""
    try:
        conn = get_sql_connection()
        cursor = conn.cursor()

        # Conta articoli (adattare nome tabella al DB reale)
        try:
            cursor.execute("SELECT COUNT(*) FROM Articoli")
            count = cursor.fetchone()[0]
        except Exception:
            # Prova nome tabella alternativo
            try:
                cursor.execute("SELECT COUNT(*) FROM Art")
                count = cursor.fetchone()[0]
            except Exception:
                count = None

        conn.close()
        return DaneaSyncStatus(
            connected=True,
            database=SQL_CONNECTION_STRING.split("DATABASE=")[1].split(";")[0] if "DATABASE=" in SQL_CONNECTION_STRING else "unknown",
            last_check=datetime.now().isoformat(),
            articles_count=count,
        )
    except Exception as e:
        return DaneaSyncStatus(
            connected=False,
            database="disconnected",
            last_check=datetime.now().isoformat(),
            error=str(e),
        )


# === ENDPOINT: Articoli / Anagrafica ===

@app.get("/articoli", response_model=list[ArticoloResponse])
async def list_articoli(
    search: str | None = Query(None, description="Cerca per codice o descrizione"),
    limit: int = Query(100, ge=1, le=1000),
):
    """Lista articoli dal database Danea.

    NOTA: I nomi delle colonne vanno adattati alla struttura reale del DB.
    Questi sono nomi tipici per Easyfatt / Imex-Stock.
    """
    conn = get_sql_connection()
    cursor = conn.cursor()

    try:
        if search:
            query = """
                SELECT TOP (?)
                    Cod AS codice,
                    Descrizione AS descrizione,
                    Giacenza AS giacenza,
                    PrezzoAcquisto AS prezzo,
                    Fornitore AS fornitore,
                    UM AS unita_misura
                FROM Articoli
                WHERE Cod LIKE ? OR Descrizione LIKE ?
                ORDER BY Cod
            """
            search_pattern = f"%{search}%"
            cursor.execute(query, (limit, search_pattern, search_pattern))
        else:
            query = """
                SELECT TOP (?)
                    Cod AS codice,
                    Descrizione AS descrizione,
                    Giacenza AS giacenza,
                    PrezzoAcquisto AS prezzo,
                    Fornitore AS fornitore,
                    UM AS unita_misura
                FROM Articoli
                ORDER BY Cod
            """
            cursor.execute(query, (limit,))

        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()

        return [
            ArticoloResponse(**dict(zip(columns, row)))
            for row in rows
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore query SQL Server: {e}")
    finally:
        conn.close()


@app.get("/articoli/{codice}", response_model=ArticoloResponse)
async def get_articolo(codice: str):
    """Dettaglio singolo articolo per codice."""
    conn = get_sql_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT
                Cod AS codice,
                Descrizione AS descrizione,
                Giacenza AS giacenza,
                PrezzoAcquisto AS prezzo,
                Fornitore AS fornitore,
                UM AS unita_misura,
                CodFornitore AS codice_fornitore
            FROM Articoli
            WHERE Cod = ?
        """, (codice,))

        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Articolo {codice} non trovato")

        columns = [col[0] for col in cursor.description]
        return ArticoloResponse(**dict(zip(columns, row)))
    finally:
        conn.close()


# === ENDPOINT: Giacenze ===

@app.get("/giacenze", response_model=list[GiacenzaResponse])
async def list_giacenze(
    codice: str | None = None,
    solo_positivi: bool = True,
    limit: int = Query(200, ge=1, le=2000),
):
    """Giacenze in tempo reale dal database Danea."""
    conn = get_sql_connection()
    cursor = conn.cursor()

    try:
        where_clauses = []
        params = []

        if codice:
            where_clauses.append("a.Cod LIKE ?")
            params.append(f"%{codice}%")

        if solo_positivi:
            where_clauses.append("a.Giacenza > 0")

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        params.insert(0, limit)

        cursor.execute(f"""
            SELECT TOP (?)
                a.Cod AS codice,
                a.Descrizione AS descrizione,
                a.Giacenza AS giacenza
            FROM Articoli a
            {where_sql}
            ORDER BY a.Cod
        """, params)

        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()

        return [
            GiacenzaResponse(**dict(zip(columns, row)))
            for row in rows
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore query giacenze: {e}")
    finally:
        conn.close()


# === ENDPOINT: Movimenti ===

@app.get("/movimenti", response_model=list[MovimentoResponse])
async def list_movimenti(
    codice: str | None = None,
    data_da: str | None = Query(None, description="Data inizio YYYY-MM-DD"),
    data_a: str | None = Query(None, description="Data fine YYYY-MM-DD"),
    limit: int = Query(100, ge=1, le=1000),
):
    """Ultimi movimenti di magazzino da Danea."""
    conn = get_sql_connection()
    cursor = conn.cursor()

    try:
        where_clauses = []
        params = [limit]

        if codice:
            where_clauses.append("m.CodArticolo LIKE ?")
            params.append(f"%{codice}%")
        if data_da:
            where_clauses.append("m.Data >= ?")
            params.append(data_da)
        if data_a:
            where_clauses.append("m.Data <= ?")
            params.append(data_a)

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        cursor.execute(f"""
            SELECT TOP (?)
                CONVERT(VARCHAR, m.Data, 23) AS data,
                m.Tipo AS tipo,
                m.CodArticolo AS codice_articolo,
                a.Descrizione AS descrizione,
                m.Quantita AS quantita,
                m.NumDocumento AS documento,
                m.Causale AS causale
            FROM Movimenti m
            LEFT JOIN Articoli a ON m.CodArticolo = a.Cod
            {where_sql}
            ORDER BY m.Data DESC
        """, params)

        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()

        return [
            MovimentoResponse(**dict(zip(columns, row)))
            for row in rows
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore query movimenti: {e}")
    finally:
        conn.close()


# === ENDPOINT: Query SQL personalizzata (solo lettura) ===

@app.get("/query")
async def custom_query(
    sql: str = Query(..., description="Query SQL SELECT (solo lettura)"),
    limit: int = Query(100, ge=1, le=1000),
):
    """Esegue una query SQL personalizzata (solo SELECT).

    Utile per Claude/MCP per fare query specifiche sul DB Danea.
    """
    # Sicurezza: solo SELECT
    sql_upper = sql.strip().upper()
    if not sql_upper.startswith("SELECT"):
        raise HTTPException(status_code=400, detail="Solo query SELECT permesse")

    forbidden = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "EXEC", "EXECUTE"]
    for word in forbidden:
        if word in sql_upper:
            raise HTTPException(status_code=400, detail=f"Operazione '{word}' non permessa")

    conn = get_sql_connection()
    cursor = conn.cursor()

    try:
        # Aggiungi TOP se non presente
        if "TOP" not in sql_upper:
            sql = sql.replace("SELECT", f"SELECT TOP ({limit})", 1)

        cursor.execute(sql)
        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()

        return {
            "columns": columns,
            "rows": [dict(zip(columns, row)) for row in rows],
            "count": len(rows),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore query: {e}")
    finally:
        conn.close()


# === ENDPOINT: Tabelle disponibili ===

@app.get("/tables")
async def list_tables():
    """Lista tutte le tabelle nel database SQL Server."""
    conn = get_sql_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT TABLE_NAME
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_TYPE = 'BASE TABLE'
            ORDER BY TABLE_NAME
        """)
        tables = [row[0] for row in cursor.fetchall()]
        return {"tables": tables, "count": len(tables)}
    finally:
        conn.close()


@app.get("/tables/{table_name}/columns")
async def table_columns(table_name: str):
    """Schema colonne di una tabella specifica."""
    conn = get_sql_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, IS_NULLABLE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = ?
            ORDER BY ORDINAL_POSITION
        """, (table_name,))

        columns = [
            {
                "name": row[0],
                "type": row[1],
                "max_length": row[2],
                "nullable": row[3],
            }
            for row in cursor.fetchall()
        ]
        return {"table": table_name, "columns": columns}
    finally:
        conn.close()


# === Avvio diretto ===

if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("  Trade Skill — Danea Bridge Agent")
    print("  Ponte locale SQL Server → MES Cloud")
    print("=" * 60)
    print(f"\n  Database: {SQL_CONNECTION_STRING.split('DATABASE=')[1].split(';')[0] if 'DATABASE=' in SQL_CONNECTION_STRING else 'N/A'}")
    print(f"  API locale: http://localhost:8001")
    print(f"  Docs: http://localhost:8001/docs")
    print(f"\n  Per esporre su internet:")
    print(f"  cloudflared tunnel --url http://localhost:8001")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8001)
