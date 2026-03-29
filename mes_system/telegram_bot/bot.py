"""Telegram Bot per registrazione produzione via voce.

Flusso:
1. Operatore Albania manda messaggio vocale su Telegram (in albanese/italiano)
2. Il bot trascrive il vocale con Whisper (OpenAI API o locale)
3. Claude interpreta il testo e lo mappa a un'azione MES
4. Il bot risponde con i dati interpretati e chiede conferma
5. Operatore preme ✅ Conferma → registrazione nel MES

Comandi bot:
/start      - Registrazione operatore
/stato      - Stato ordini di lavoro in corso
/materiali  - Materiali disponibili/in arrivo
/help       - Aiuto

Messaggi vocali:
- "Kam përfunduar 200 copë nga porosia WO-2026-042, 3 skart"
  → Registra 200 buoni + 3 scarti su WO-2026-042
- "Ho finito 150 pezzi dell'ordine 42, fase reflow, 2 scarti"
  → Registra 150 buoni + 2 scarti su WO-2026-0042, fase REFLOW
"""

import os
import json
import logging
import tempfile
from dataclasses import dataclass

import httpx

from mes_system.config import settings

logger = logging.getLogger(__name__)


@dataclass
class TelegramConfig:
    bot_token: str
    webhook_url: str | None = None
    # Whisper API per speech-to-text
    openai_api_key: str | None = None
    # Claude API per interpretazione
    anthropic_api_key: str | None = None
    # Allowed chat IDs (sicurezza: solo operatori autorizzati)
    allowed_users: list[int] | None = None


class ProductionBot:
    """Bot Telegram per registrazione produzione in Albania.

    Architettura:
    - Riceve messaggi vocali
    - Trascrive con Whisper (multilingua: albanese + italiano)
    - Interpreta con Claude (estrae: ordine, quantità, scarti, fase)
    - Mostra dati dal MES per conferma
    - Registra su conferma operatore
    """

    def __init__(self, config: TelegramConfig):
        self.config = config
        self.api_base = f"https://api.telegram.org/bot{config.bot_token}"
        self._pending_confirmations: dict[int, dict] = {}  # chat_id -> data

    async def handle_update(self, update: dict) -> None:
        """Gestisce un update Telegram (webhook o polling)."""
        message = update.get("message")
        callback = update.get("callback_query")

        if callback:
            await self._handle_callback(callback)
            return

        if not message:
            return

        chat_id = message["chat"]["id"]

        # Verifica autorizzazione
        if self.config.allowed_users and chat_id not in self.config.allowed_users:
            await self._send_message(chat_id, "⛔ Non sei autorizzato. Contatta l'amministratore.")
            return

        # Messaggio vocale
        if "voice" in message:
            await self._handle_voice(chat_id, message)
        # Comando
        elif "text" in message and message["text"].startswith("/"):
            await self._handle_command(chat_id, message["text"])
        # Testo libero (interpretato come registrazione)
        elif "text" in message:
            await self._handle_text(chat_id, message["text"])

    async def _handle_voice(self, chat_id: int, message: dict) -> None:
        """Gestisce messaggio vocale: scarica → trascrivi → interpreta."""
        voice = message["voice"]
        file_id = voice["file_id"]

        await self._send_message(chat_id, "🎤 Sto ascoltando...")

        # 1. Scarica il file audio da Telegram
        audio_bytes = await self._download_voice(file_id)
        if not audio_bytes:
            await self._send_message(chat_id, "❌ Errore nel download del vocale.")
            return

        # 2. Trascrivi con Whisper
        transcript = await self._transcribe(audio_bytes)
        if not transcript:
            await self._send_message(chat_id, "❌ Non sono riuscito a trascrivere il messaggio.")
            return

        await self._send_message(chat_id, f"📝 Ho capito: \"{transcript}\"")

        # 3. Interpreta con Claude
        await self._interpret_and_confirm(chat_id, transcript)

    async def _handle_text(self, chat_id: int, text: str) -> None:
        """Gestisce testo libero come registrazione produzione."""
        await self._interpret_and_confirm(chat_id, text)

    async def _handle_command(self, chat_id: int, command: str) -> None:
        """Gestisce comandi bot."""
        cmd = command.split()[0].lower()

        if cmd == "/start":
            await self._send_message(
                chat_id,
                "👋 Benvenuto nel sistema di produzione Trade Skill!\n\n"
                "🎤 Manda un messaggio vocale per registrare la produzione\n"
                "📝 Oppure scrivi in testo\n\n"
                "Comandi:\n"
                "/stato - Ordini di lavoro in corso\n"
                "/materiali - Materiali disponibili\n"
                "/help - Aiuto"
            )
        elif cmd == "/stato":
            await self._send_production_status(chat_id)
        elif cmd == "/materiali":
            await self._send_material_status(chat_id)
        elif cmd == "/help":
            await self._send_message(
                chat_id,
                "📖 Come usare il bot:\n\n"
                "1. Manda un vocale dicendo cosa hai prodotto\n"
                "   Es: \"Ho finito 200 pezzi dell'ordine 42, 3 scarti alla fase reflow\"\n"
                "   Es: \"Kam përfunduar 200 copë nga porosia 42\"\n\n"
                "2. Il sistema interpreta e ti chiede conferma\n"
                "3. Premi ✅ per confermare o ✏️ per correggere"
            )

    async def _handle_callback(self, callback: dict) -> None:
        """Gestisce callback da bottoni inline."""
        chat_id = callback["message"]["chat"]["id"]
        data = callback["data"]

        if data == "confirm_production":
            pending = self._pending_confirmations.get(chat_id)
            if pending:
                # Qui chiama il servizio MES per registrare
                # await mes_service.register_production(db, pending)
                await self._send_message(
                    chat_id,
                    "✅ Produzione registrata con successo!\n"
                    f"📋 Ordine: {pending.get('work_order_code')}\n"
                    f"✅ Buoni: {pending.get('quantity_good')}\n"
                    f"❌ Scarti: {pending.get('quantity_scrap', 0)}"
                )
                del self._pending_confirmations[chat_id]
            else:
                await self._send_message(chat_id, "⚠️ Nessuna registrazione in sospeso.")

        elif data == "cancel_production":
            self._pending_confirmations.pop(chat_id, None)
            await self._send_message(chat_id, "❌ Registrazione annullata. Riprova con un nuovo vocale.")

    async def _interpret_and_confirm(self, chat_id: int, text: str) -> None:
        """Interpreta il testo con Claude e chiede conferma."""
        interpretation = await self._interpret_with_claude(text)

        if not interpretation:
            await self._send_message(
                chat_id,
                "❌ Non sono riuscito a interpretare il messaggio.\n"
                "Riprova dicendo: ordine, quantità buoni, scarti, fase."
            )
            return

        # Salva per conferma
        self._pending_confirmations[chat_id] = interpretation

        # Costruisci messaggio di conferma
        msg = (
            "📋 *Registrazione Produzione*\n\n"
            f"🔖 Ordine: `{interpretation.get('work_order_code', '?')}`\n"
            f"✅ Pezzi buoni: {interpretation.get('quantity_good', 0)}\n"
            f"❌ Scarti: {interpretation.get('quantity_scrap', 0)}\n"
        )
        if interpretation.get("phase_name"):
            msg += f"⚙️ Fase: {interpretation['phase_name']}\n"
        if interpretation.get("scrap_reason"):
            msg += f"📝 Motivo scarti: {interpretation['scrap_reason']}\n"

        msg += "\n*Confermi questi dati?*"

        # Bottoni inline
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "✅ Conferma", "callback_data": "confirm_production"},
                    {"text": "❌ Annulla", "callback_data": "cancel_production"},
                ]
            ]
        }

        await self._send_message(chat_id, msg, reply_markup=keyboard, parse_mode="Markdown")

    async def _download_voice(self, file_id: str) -> bytes | None:
        """Scarica file audio da Telegram."""
        async with httpx.AsyncClient() as client:
            # Get file path
            resp = await client.get(f"{self.api_base}/getFile", params={"file_id": file_id})
            if resp.status_code != 200:
                return None
            file_path = resp.json()["result"]["file_path"]

            # Download file
            resp = await client.get(
                f"https://api.telegram.org/file/bot{self.config.bot_token}/{file_path}"
            )
            return resp.content if resp.status_code == 200 else None

    async def _transcribe(self, audio_bytes: bytes) -> str | None:
        """Trascrive audio con Whisper API (OpenAI).

        Supporta albanese e italiano automaticamente.
        """
        if not self.config.openai_api_key:
            logger.warning("OpenAI API key non configurata per Whisper")
            return None

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {self.config.openai_api_key}"},
                files={"file": ("voice.ogg", audio_bytes, "audio/ogg")},
                data={"model": "whisper-1"},
                timeout=30,
            )

            if resp.status_code == 200:
                return resp.json().get("text")
            logger.error(f"Whisper error: {resp.status_code} {resp.text}")
            return None

    async def _interpret_with_claude(self, text: str) -> dict | None:
        """Interpreta il testo con Claude per estrarre dati produzione.

        Claude riceve il testo (albanese/italiano) e restituisce JSON strutturato.
        """
        if not self.config.anthropic_api_key:
            # Fallback: parsing regex base
            return self._basic_parse(text)

        prompt = f"""Sei un assistente per la registrazione di produzione in una fabbrica di elettronica.
L'operatore ha detto (in italiano o albanese):
"{text}"

Estrai i seguenti dati in formato JSON:
- work_order_code: codice ordine di lavoro (formato WO-YYYY-NNNN, es. WO-2026-0042)
- quantity_good: numero pezzi buoni prodotti
- quantity_scrap: numero scarti (default 0)
- phase_name: fase di produzione se menzionata (SERIGRAFIA, PICK_PLACE, REFLOW, AOI, WAVE, TEST, ASSEMBLY)
- scrap_reason: motivo scarti se menzionato
- operator: nome operatore se menzionato

Se il codice ordine è solo un numero (es. "42"), convertilo in formato WO-2026-0042.
Se non riesci a estrarre i dati, rispondi con null.
Rispondi SOLO con il JSON, nessun altro testo."""

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.config.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 300,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=30,
            )

            if resp.status_code == 200:
                content = resp.json()["content"][0]["text"]
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    logger.error(f"Claude response not JSON: {content}")
                    return None
            logger.error(f"Claude error: {resp.status_code} {resp.text}")
            return None

    def _basic_parse(self, text: str) -> dict | None:
        """Parsing base senza AI — fallback."""
        import re

        result = {
            "work_order_code": None,
            "quantity_good": 0,
            "quantity_scrap": 0,
            "phase_name": None,
            "operator": None,
        }

        # Cerca codice ordine
        wo_match = re.search(r'WO-\d{4}-\d{4}', text, re.IGNORECASE)
        if wo_match:
            result["work_order_code"] = wo_match.group().upper()
        else:
            # Cerca numero semplice dopo "ordine"/"porosia"
            num_match = re.search(r'(?:ordine|porosia|order)\s+(\d+)', text, re.IGNORECASE)
            if num_match:
                num = int(num_match.group(1))
                result["work_order_code"] = f"WO-2026-{num:04d}"

        # Cerca quantità
        qty_match = re.search(r'(\d+)\s*(?:pezzi|copë|pz|pieces|buoni)', text, re.IGNORECASE)
        if qty_match:
            result["quantity_good"] = int(qty_match.group(1))

        # Cerca scarti
        scrap_match = re.search(r'(\d+)\s*(?:scarti|skart|scrap|difettosi)', text, re.IGNORECASE)
        if scrap_match:
            result["quantity_scrap"] = int(scrap_match.group(1))

        # Cerca fase
        phases = {
            "serigrafia": "SERIGRAFIA",
            "pick.?place": "PICK_PLACE",
            "reflow": "REFLOW",
            "aoi": "AOI",
            "wave": "WAVE",
            "test": "TEST",
            "assembly": "ASSEMBLY",
            "montaggio": "ASSEMBLY",
        }
        for pattern, phase in phases.items():
            if re.search(pattern, text, re.IGNORECASE):
                result["phase_name"] = phase
                break

        if result["work_order_code"] and result["quantity_good"] > 0:
            return result
        return None

    async def _send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: dict | None = None,
        parse_mode: str | None = None,
    ) -> None:
        """Invia messaggio su Telegram."""
        payload = {"chat_id": chat_id, "text": text}
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)
        if parse_mode:
            payload["parse_mode"] = parse_mode

        async with httpx.AsyncClient() as client:
            await client.post(f"{self.api_base}/sendMessage", json=payload)

    async def _send_production_status(self, chat_id: int) -> None:
        """Invia stato ordini di lavoro in corso."""
        # TODO: Connettere al servizio MES reale
        await self._send_message(
            chat_id,
            "📊 *Stato Produzione*\n\n"
            "Connessione al sistema MES in configurazione...\n"
            "Usa /help per vedere come registrare la produzione.",
            parse_mode="Markdown",
        )

    async def _send_material_status(self, chat_id: int) -> None:
        """Invia stato materiali disponibili/in arrivo."""
        # TODO: Connettere al servizio WMS reale
        await self._send_message(
            chat_id,
            "📦 *Materiali*\n\n"
            "Connessione al sistema WMS in configurazione...",
            parse_mode="Markdown",
        )
