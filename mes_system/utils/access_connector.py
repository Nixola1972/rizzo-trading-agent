"""Connettore per database Microsoft Access (gestionale Riccardo).

Utilizza pyodbc per connettersi a un database Access (.mdb/.accdb).
Questo modulo è predisposto per Fase 2 — va configurato con il path
del database Access e la mappatura delle tabelle.

Requisiti sistema:
- Linux: mdbtools + unixodbc (apt install mdbtools unixodbc)
- Windows: Microsoft Access ODBC Driver
- pip install pyodbc
"""

from typing import Any
from dataclasses import dataclass


@dataclass
class AccessConfig:
    """Configurazione connessione Access."""
    db_path: str  # Path al file .mdb/.accdb
    # Linux con mdbtools
    driver: str = "{MDBTools}"
    # Windows: driver = "{Microsoft Access Driver (*.mdb, *.accdb)}"


class AccessConnector:
    """Connettore per leggere dati dal gestionale Access di Riccardo.

    FASE 2: Da implementare quando si ha accesso al database.

    Funzionalità previste:
    - Lettura anagrafica articoli
    - Lettura ordini clienti
    - Lettura storico movimenti
    - Sync con il sistema MES
    """

    def __init__(self, config: AccessConfig):
        self.config = config
        self._connection = None

    def connect(self):
        """Apre connessione al database Access."""
        try:
            import pyodbc
            conn_string = f"DRIVER={self.config.driver};DBQ={self.config.db_path};"
            self._connection = pyodbc.connect(conn_string)
            return True
        except ImportError:
            raise ImportError(
                "pyodbc non installato. Installa con: pip install pyodbc\n"
                "Su Linux serve anche: apt install mdbtools unixodbc"
            )
        except Exception as e:
            raise ConnectionError(f"Impossibile connettersi a {self.config.db_path}: {e}")

    def disconnect(self):
        if self._connection:
            self._connection.close()
            self._connection = None

    def list_tables(self) -> list[str]:
        """Lista tutte le tabelle nel database Access."""
        if not self._connection:
            self.connect()
        cursor = self._connection.cursor()
        tables = [
            row.table_name
            for row in cursor.tables(tableType="TABLE")
        ]
        return tables

    def query(self, sql: str, params: tuple = ()) -> list[dict]:
        """Esegue una query SQL e restituisce lista di dizionari."""
        if not self._connection:
            self.connect()
        cursor = self._connection.cursor()
        cursor.execute(sql, params)
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def get_articles(self) -> list[dict]:
        """Legge l'anagrafica articoli dal gestionale.

        NOTA: La query va adattata alla struttura reale del DB Access.
        Questi sono nomi di tabella/colonna placeholder.
        """
        # TODO: Adattare a struttura reale del DB di Riccardo
        return self.query("""
            SELECT
                CodiceArticolo,
                Descrizione,
                CodiceFornitore,
                PrezzoAcquisto,
                Giacenza,
                UnitaMisura
            FROM Articoli
            WHERE Attivo = True
            ORDER BY CodiceArticolo
        """)

    def get_orders(self) -> list[dict]:
        """Legge gli ordini clienti.

        NOTA: Da adattare alla struttura reale.
        """
        # TODO: Adattare a struttura reale
        return self.query("""
            SELECT
                NumeroOrdine,
                DataOrdine,
                Cliente,
                Stato,
                Totale
            FROM Ordini
            ORDER BY DataOrdine DESC
        """)

    def sync_to_mes(self, articles: list[dict]) -> dict:
        """Sincronizza articoli Access → sistema MES.

        FASE 2: Implementare mapping tra campi Access e anagrafica MES.
        """
        stats = {"total": len(articles), "synced": 0, "errors": []}

        for article in articles:
            try:
                # TODO: Implementare mapping e upsert
                # codice_access = article.get("CodiceArticolo")
                # descrizione = article.get("Descrizione")
                # ...
                stats["synced"] += 1
            except Exception as e:
                stats["errors"].append(str(e))

        return stats
