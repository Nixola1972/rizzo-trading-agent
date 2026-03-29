"""Test per il servizio di codifica automatica."""

import pytest
from mes_system.telegram_bot.bot import ProductionBot, TelegramConfig


class TestBasicParse:
    """Test del parser base (senza AI) del bot Telegram."""

    def setup_method(self):
        self.bot = ProductionBot(TelegramConfig(bot_token="test"))

    def test_parse_italian(self):
        result = self.bot._basic_parse(
            "Ho finito 200 pezzi dell'ordine 42, 3 scarti alla fase reflow"
        )
        assert result is not None
        assert result["work_order_code"] == "WO-2026-0042"
        assert result["quantity_good"] == 200
        assert result["quantity_scrap"] == 3
        assert result["phase_name"] == "REFLOW"

    def test_parse_with_full_wo_code(self):
        result = self.bot._basic_parse(
            "Completati 150 pezzi buoni per WO-2026-0015, fase test"
        )
        assert result is not None
        assert result["work_order_code"] == "WO-2026-0015"
        assert result["quantity_good"] == 150
        assert result["phase_name"] == "TEST"

    def test_parse_albanian(self):
        result = self.bot._basic_parse(
            "Kam përfunduar 300 copë nga porosia 42, 5 skart"
        )
        assert result is not None
        assert result["work_order_code"] == "WO-2026-0042"
        assert result["quantity_good"] == 300
        assert result["quantity_scrap"] == 5

    def test_parse_incomplete(self):
        result = self.bot._basic_parse("ciao come stai")
        assert result is None

    def test_parse_only_quantity_no_order(self):
        result = self.bot._basic_parse("ho fatto 100 pezzi")
        assert result is None  # Manca l'ordine


class TestBarcodeFormat:
    """Test formato barcode."""

    def test_component_code_format(self):
        # Verifica il formato atteso: TS-{CAT}-{SUBCAT}-{SEQ:06d}
        code = "TS-RES-0805-000001"
        parts = code.split("-")
        assert parts[0] == "TS"
        assert parts[1] == "RES"
        assert parts[2] == "0805"
        assert len(parts[3]) == 6
        assert parts[3].isdigit()

    def test_barcode_format(self):
        # Formato: {COMPONENT_CODE}-R{SEQ}
        barcode = "TS-RES-0805-000042-R001"
        assert barcode.startswith("TS-")
        assert "-R" in barcode
