"""Configurazione test fixtures."""

import pytest


# I test di integrazione con database richiedono un DB PostgreSQL di test.
# Per ora includiamo solo test unitari che non richiedono DB.
# Per test con DB, usare: pytest --db-url=postgresql+asyncpg://...

def pytest_addoption(parser):
    parser.addoption(
        "--db-url",
        action="store",
        default=None,
        help="Database URL for integration tests",
    )
