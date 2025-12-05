from dotenv import load_dotenv
import os
import json
import re
import time
from typing import Dict, List, Any, Optional

load_dotenv()

# ===== AI TIMING CONFIGURATION =====
AI_CALL_INTERVAL_MINUTES = int(os.getenv('AI_CALL_INTERVAL_MINUTES', '15'))
AI_DECISION_TIMEOUT_SECONDS = int(os.getenv('AI_DECISION_TIMEOUT_SECONDS', '60'))
AI_MAX_RETRIES = int(os.getenv('AI_MAX_RETRIES', '2'))
AI_RETRY_DELAY_SECONDS = int(os.getenv('AI_RETRY_DELAY_SECONDS', '5'))

print(f"⏱️  AI Timing: interval={AI_CALL_INTERVAL_MINUTES}min, timeout={AI_DECISION_TIMEOUT_SECONDS}s, retries={AI_MAX_RETRIES}")

# ===== CONFIGURAZIONE TRAILING STOP & POSITION PROTECTION =====
TRAILING_STOP_ENABLED = os.getenv('TRAILING_STOP_ENABLED', 'true').lower() == 'true'
TRAILING_STOP_PERCENT = float(os.getenv('TRAILING_STOP_PERCENT', '7'))
TRAILING_STOP_ACTIVATION_PERCENT = float(os.getenv('TRAILING_STOP_ACTIVATION_PERCENT', '3'))
INITIAL_STOP_LOSS_PERCENT = float(os.getenv('INITIAL_STOP_LOSS_PERCENT', '10'))
SCORE_THRESHOLD_CLOSE_REVERSAL = float(os.getenv('SCORE_THRESHOLD_CLOSE_REVERSAL', '10'))
SCORE_THRESHOLD_OPEN = float(os.getenv('SCORE_THRESHOLD_OPEN', '16'))

# ===== AI FREE MODE =====
# Quando attivo, disabilita la protezione chiusure e lascia decidere l'AI
AI_FREE_MODE = os.getenv('AI_FREE_MODE', 'false').lower() == 'true'

# ===== DOUBLE_CHECK AI =====
# Se attivo, l'AI decide in base agli indicatori, non allo score
DOUBLE_CHECK_AI_ENABLED = os.getenv('DOUBLE_CHECK_AI_ENABLED', 'false').lower() == 'true'

if TRAILING_STOP_ENABLED:
    print(f"🛡️  Trailing Stop: ENABLED (trailing={TRAILING_STOP_PERCENT}%, activation={TRAILING_STOP_ACTIVATION_PERCENT}%, stop_loss={INITIAL_STOP_LOSS_PERCENT}%)")
    print(f"🛡️  Close Reversal Threshold: {SCORE_THRESHOLD_CLOSE_REVERSAL}")

# Import signal scorer per calcolo score BULLISH/BEARISH
try:
    from signal_scorer import (
        calculate_signal_score,
        format_score_for_prompt,
        get_scoring_config
    )
    SCORING_ENABLED = True
    print("📊 Signal Scoring System: ENABLED")
except ImportError:
    SCORING_ENABLED = False
    print("⚠️  Signal Scoring System: DISABLED (signal_scorer.py not found)")

# Configurazione AI Provider
AI_PROVIDER = os.getenv('AI_PROVIDER', 'openai').lower()

# Import condizionale: importa OpenAI solo se necessario
if AI_PROVIDER == 'openai':
    from openai import OpenAI
elif AI_PROVIDER == 'openrouter':
    from openai import OpenAI  # OpenRouter usa la stessa interfaccia OpenAI
else:
    from openai import OpenAI  # Default fallback

# Modelli che supportano nativamente response_format={"type": "json_object"}
MODELS_WITH_JSON_SUPPORT = [
    # OpenAI GPT (2025)
    'gpt-5',
    'openai/gpt-5',
    'gpt-4.1',
    'openai/gpt-4.1',
    'gpt-4-turbo',
    'gpt-4o',
    'gpt-4o-mini',
    'gpt-4-1106-preview',
    'gpt-3.5-turbo-1106',
    # Claude 3.x (supporto nativo JSON)
    'anthropic/claude-3.5-sonnet',
    'anthropic/claude-3-opus',
    'anthropic/claude-3-sonnet',
]

# Modelli che NON supportano response_format ma possono comunque produrre JSON
# Questi sono modelli 2025 più recenti e performanti
MODELS_WITHOUT_JSON_SUPPORT = [
    # Claude 4.x e 3.7 (2025 - più recenti, ottime performance)
    'anthropic/claude-sonnet-4.5',
    'anthropic/claude-4.5-sonnet',
    'anthropic/claude-3.7-sonnet',
    'anthropic/claude-haiku-4.5',
    'anthropic/claude-opus-4.5',
    # Google Gemini 2.x (2025)
    'google/gemini-2.5-pro',
    'google/gemini-2.5-flash',
    'google/gemini-2.0-flash-exp',
    'google/gemini-pro',
    # DeepSeek V3 e R1 (2025 - top performance, economici!) 🔥
    'deepseek/deepseek-chat',  # DeepSeek V3 (chat model principale)
    'deepseek/deepseek-r1',  # DeepSeek R1 (reasoning avanzato)
    'deepseek/deepseek-r1:free',  # DeepSeek R1 FREE
    'deepseek/deepseek-r1-distill-llama-70b',
    'deepseek/deepseek-r1-distill-qwen-32b',
    'deepseek/deepseek-v3',  # DeepSeek V3
    'deepseek/deepseek-v3.1-terminus',  # DeepSeek V3.1 Terminus
    # Qwen (Alibaba)
    'qwen/qwen-2.5-72b-instruct',
    'qwen/qwen-2.5-coder-32b-instruct',
    # Meta Llama
    'meta-llama/llama-3.3-70b-instruct',
    'meta-llama/llama-3.1-405b-instruct',
    # Mistral
    'mistralai/mistral-large',
    'mistralai/mistral-small',
]

if AI_PROVIDER == 'openrouter':
    # OpenRouter configuration
    OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
    OPENROUTER_MODEL = os.getenv('OPENROUTER_MODEL', 'anthropic/claude-3.5-sonnet')

    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY mancante nel file .env")

    client = OpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1"
    )
    MODEL = OPENROUTER_MODEL
    print(f"🤖 Usando OpenRouter con modello: {MODEL}")

else:
    # OpenAI configuration (default)
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY mancante nel file .env")

    client = OpenAI(api_key=OPENAI_API_KEY)
    MODEL = os.getenv('OPENAI_MODEL', 'gpt-4-turbo')
    print(f"🤖 Usando OpenAI con modello: {MODEL}")


def extract_json_from_text(text):
    """
    Estrae JSON da una risposta che potrebbe contenere anche testo normale.
    Cerca il primo oggetto JSON valido nella risposta.
    Gestisce anche risposte "sporche" con markdown, commenti, etc.
    """
    if not text or not text.strip():
        return None

    # 1. Rimuovi markdown code blocks
    text = re.sub(r'```json\s*', '', text)
    text = re.sub(r'```\s*', '', text)

    # 2. Rimuovi commenti JavaScript/JSON style
    text = re.sub(r'//[^\n]*', '', text)

    # 3. Cerca pattern JSON (oggetto tra { })
    json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
    matches = re.finditer(json_pattern, text, re.DOTALL)

    for match in matches:
        try:
            potential_json = match.group(0)
            # Rimuovi virgole finali prima di } o ]
            potential_json = re.sub(r',\s*}', '}', potential_json)
            potential_json = re.sub(r',\s*]', ']', potential_json)
            parsed = json.loads(potential_json)
            # Verifica che sia un dizionario (non array)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue

    # 4. Prova a estrarre JSON anche con pattern più permissivo
    # Cerca tutto tra la prima { e l'ultima }
    first_brace = text.find('{')
    last_brace = text.rfind('}')
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        try:
            potential_json = text[first_brace:last_brace+1]
            potential_json = re.sub(r',\s*}', '}', potential_json)
            potential_json = re.sub(r',\s*]', ']', potential_json)
            parsed = json.loads(potential_json)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    # 5. Prova a estrarre campi chiave manualmente se JSON non parsabile
    # Questo gestisce risposte come: operation: "hold", symbol: "BTC", ...
    try:
        result = {}
        # Cerca operation
        op_match = re.search(r'["\']?operation["\']?\s*[:=]\s*["\']?(open|close|hold)["\']?', text, re.IGNORECASE)
        if op_match:
            result['operation'] = op_match.group(1).lower()

        # Cerca symbol
        sym_match = re.search(r'["\']?symbol["\']?\s*[:=]\s*["\']?([A-Z]{2,5})["\']?', text, re.IGNORECASE)
        if sym_match:
            result['symbol'] = sym_match.group(1).upper()

        # Cerca direction
        dir_match = re.search(r'["\']?direction["\']?\s*[:=]\s*["\']?(long|short)["\']?', text, re.IGNORECASE)
        if dir_match:
            result['direction'] = dir_match.group(1).lower()

        # Cerca reason
        reason_match = re.search(r'["\']?reason["\']?\s*[:=]\s*["\']([^"\']+)["\']', text)
        if reason_match:
            result['reason'] = reason_match.group(1)

        # Se abbiamo almeno operation e symbol, ritorna il risultato
        if 'operation' in result and 'symbol' in result:
            print(f"   🔧 JSON estratto manualmente: {result}")
            return result
    except Exception:
        pass

    # 6. Se non trova JSON, prova a fare parse diretto
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def validate_trading_decision(result, signal_scores=None):
    """
    Valida che la decisione di trading abbia tutti i campi richiesti.
    Aggiunge campi mancanti con valori di default se possibile.
    Usa il signal scoring per determinare la direzione se non specificata.

    Args:
        result: Dizionario con la decisione AI
        signal_scores: Dizionario con gli score calcolati per ogni symbol
    """
    required_fields = ["operation", "symbol"]  # Solo questi sono veramente obbligatori

    # Validazione campi obbligatori
    for field in required_fields:
        if field not in result:
            raise ValueError(f"Campo mancante nella risposta AI: {field}")

    # Aggiungi direction basata su scoring invece di default "long"
    if "direction" not in result:
        symbol = result.get("symbol", "")
        if signal_scores and symbol in signal_scores:
            score = signal_scores[symbol]
            suggested_direction = score.get('direction', 'HOLD')
            if suggested_direction == 'LONG':
                result["direction"] = "long"
            elif suggested_direction == 'SHORT':
                result["direction"] = "short"
            else:
                # Se scoring dice HOLD, usiamo long come fallback
                # ma l'operazione dovrebbe essere già HOLD
                result["direction"] = "long"
            print(f"   📊 Direction da scoring: {result['direction']} (score: {score.get('net_score', 0):.1f})")
        else:
            # Fallback: long se scoring non disponibile
            result["direction"] = "long"
            print(f"   ⚠️  Direction default: long (scoring non disponibile)")

    if "target_portion_of_balance" not in result:
        result["target_portion_of_balance"] = 0.0 if result["operation"] != "open" else 0.3

    if "leverage" not in result:
        result["leverage"] = 1

    if "reason" not in result:
        result["reason"] = "No reason provided by AI model"

    # Validazione valori
    valid_operations = ["open", "close", "hold"]
    if result["operation"] not in valid_operations:
        raise ValueError(f"Operazione non valida: {result['operation']}. Deve essere: {', '.join(valid_operations)}")

    valid_directions = ["long", "short"]
    if result["direction"] not in valid_directions:
        raise ValueError(f"Direction non valida: {result['direction']}. Deve essere: {', '.join(valid_directions)}")

    return result


def call_ai_api(prompt, use_json_format=True, max_retries=None, signal_scores=None, symbol=None):
    """
    Chiama l'API AI con retry logic, timeout e gestione flessibile del JSON.

    Args:
        prompt: Il prompt da inviare
        use_json_format: Se usare response_format=json_object (solo per modelli compatibili)
        max_retries: Numero massimo di tentativi (default da AI_MAX_RETRIES)
        signal_scores: Dizionario con score calcolati per ogni symbol (per validazione)
        symbol: Simbolo analizzato (per logging)
    """
    if max_retries is None:
        max_retries = AI_MAX_RETRIES

    for attempt in range(max_retries + 1):
        try:
            # Prepara parametri chiamata
            call_params = {
                "model": MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a cryptocurrency trading AI. Always respond with valid JSON matching the required schema. Do not include any text before or after the JSON object."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0.7,
                "timeout": AI_DECISION_TIMEOUT_SECONDS  # Timeout configurabile
            }

            # Aggiungi response_format solo per modelli che lo supportano
            if use_json_format and MODEL in MODELS_WITH_JSON_SUPPORT:
                call_params["response_format"] = {"type": "json_object"}
                if attempt == 0:
                    print(f"   📋 Usando formato JSON nativo (supportato da {MODEL})")
            else:
                if attempt == 0:
                    print(f"   📝 Usando parsing JSON manuale (modello: {MODEL})")

            # Chiamata API con timing
            start_time = time.time()
            response = client.chat.completions.create(**call_params)
            duration_ms = int((time.time() - start_time) * 1000)
            response_text = response.choices[0].message.content

            # Estrai JSON dalla risposta
            if MODEL in MODELS_WITH_JSON_SUPPORT:
                # Modelli con supporto nativo: parse diretto
                result = json.loads(response_text)
            else:
                # Modelli senza supporto: estrazione robusta
                result = extract_json_from_text(response_text)

                if result is None:
                    raise ValueError(f"Nessun JSON valido trovato nella risposta. Risposta: {response_text[:200]}")

            # Valida e normalizza il risultato (passa signal_scores per direction)
            result = validate_trading_decision(result, signal_scores=signal_scores)

            # === LOG PROMPT E RISPOSTA AI ===
            try:
                import db_utils
                log_symbol = symbol or result.get("symbol", "UNKNOWN")
                db_utils.log_ai_prompt(
                    symbol=log_symbol,
                    full_prompt=prompt,
                    ai_raw_response=response_text,
                    parsed_decision=result,
                    model_used=MODEL,
                    duration_ms=duration_ms
                )
            except Exception as log_err:
                print(f"   ⚠️ Errore log AI prompt: {log_err}")

            return result

        except json.JSONDecodeError as e:
            print(f"   ⚠️  Tentativo {attempt + 1}/{max_retries + 1}: Errore parsing JSON - {e}")
            if attempt < max_retries:
                print(f"   🔄 Riprovo tra {AI_RETRY_DELAY_SECONDS}s con prompt più esplicito...")
                time.sleep(AI_RETRY_DELAY_SECONDS)
                # Aggiungi enfasi sul formato JSON nel prompt
                if "IMPORTANT: Respond ONLY with a valid JSON object" not in prompt:
                    prompt = "IMPORTANT: Respond ONLY with a valid JSON object, no other text.\n\n" + prompt
            else:
                raise

        except ValueError as e:
            print(f"   ⚠️  Tentativo {attempt + 1}/{max_retries + 1}: Validazione fallita - {e}")
            if attempt < max_retries:
                print(f"   🔄 Riprovo tra {AI_RETRY_DELAY_SECONDS}s...")
                time.sleep(AI_RETRY_DELAY_SECONDS)
            else:
                raise

        except Exception as e:
            print(f"   ❌ Tentativo {attempt + 1}/{max_retries + 1}: Errore API - {e}")
            if attempt < max_retries:
                print(f"   🔄 Riprovo tra {AI_RETRY_DELAY_SECONDS}s...")
                time.sleep(AI_RETRY_DELAY_SECONDS)
                # Rimuovi response_format se causava problemi
                use_json_format = False
            else:
                raise

    # Non dovrebbe mai arrivare qui
    raise RuntimeError("Tutti i tentativi falliti")


# Variabile globale per memorizzare l'ultimo score calcolato
_last_signal_scores = {}


def check_trailing_stop(
    position: Dict[str, Any],
    current_price: float,
    tracking_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Controlla se il trailing stop o lo stop loss iniziale è stato triggerato.

    Args:
        position: Dati della posizione aperta (symbol, side, entry_price, mark_price, pnl_usd)
        current_price: Prezzo corrente del mercato
        tracking_data: Dati di tracking dal DB (peak_price, trailing_active, etc.)

    Returns:
        dict con:
            - triggered: bool (se deve chiudere)
            - reason: str (motivo)
            - trailing_active: bool (se il trailing è attivo)
            - new_peak: float (nuovo peak price da salvare)
    """
    if not TRAILING_STOP_ENABLED:
        return {"triggered": False, "reason": "Trailing stop disabled", "trailing_active": False}

    symbol = position.get("symbol", "")
    direction = position.get("side", "long").lower()
    entry_price = float(position.get("entry_price", 0))

    if entry_price == 0:
        return {"triggered": False, "reason": "No entry price", "trailing_active": False}

    # Calcola profitto attuale in percentuale
    if direction == "long":
        profit_pct = ((current_price - entry_price) / entry_price) * 100
    else:  # short
        profit_pct = ((entry_price - current_price) / entry_price) * 100

    # Determina peak_price (dal tracking o dal prezzo corrente se nuovo)
    if tracking_data:
        peak_price = tracking_data.get("peak_price", current_price)
        trailing_active = tracking_data.get("trailing_active", False)
    else:
        peak_price = current_price
        trailing_active = False

    # Aggiorna peak_price se migliore
    if direction == "long":
        new_peak = max(peak_price, current_price)
    else:
        new_peak = min(peak_price, current_price)

    # Calcola profitto dal peak
    if direction == "long":
        profit_from_peak_pct = ((current_price - new_peak) / new_peak) * 100
    else:
        profit_from_peak_pct = ((new_peak - current_price) / new_peak) * 100

    # Attiva trailing se profitto >= soglia attivazione
    if profit_pct >= TRAILING_STOP_ACTIVATION_PERCENT:
        trailing_active = True

    result = {
        "triggered": False,
        "reason": "",
        "trailing_active": trailing_active,
        "new_peak": new_peak,
        "profit_pct": profit_pct,
        "profit_from_peak_pct": profit_from_peak_pct
    }

    # CHECK 1: Stop loss iniziale (prima che trailing si attivi)
    if not trailing_active and profit_pct <= -INITIAL_STOP_LOSS_PERCENT:
        result["triggered"] = True
        result["reason"] = f"STOP LOSS: perdita {profit_pct:.2f}% >= {INITIAL_STOP_LOSS_PERCENT}%"
        return result

    # CHECK 2: Trailing stop (dopo attivazione)
    if trailing_active and profit_from_peak_pct <= -TRAILING_STOP_PERCENT:
        result["triggered"] = True
        result["reason"] = f"TRAILING STOP: {-profit_from_peak_pct:.2f}% dal peak (soglia {TRAILING_STOP_PERCENT}%)"
        return result

    return result


def check_close_protection(
    position: Dict[str, Any],
    score: Dict[str, Any],
    ai_wants_close: bool
) -> Dict[str, Any]:
    """
    Controlla se la chiusura richiesta dall'AI deve essere bloccata.

    Args:
        position: Dati della posizione aperta
        score: Score calcolato per il symbol
        ai_wants_close: True se l'AI vuole chiudere

    Returns:
        dict con:
            - allow_close: bool
            - reason: str
    """
    if not ai_wants_close:
        return {"allow_close": True, "reason": "AI non vuole chiudere"}

    direction = position.get("side", "long").lower()
    net_score = score.get("net_score", 0)

    # === AI_FREE_MODE: Bypassa la protezione, lascia decidere l'AI ===
    if AI_FREE_MODE:
        print(f"🆓 AI_FREE_MODE: Protezione chiusura disabilitata, AI decide liberamente")
        return {
            "allow_close": True,
            "reason": f"AI_FREE_MODE: AI libera di chiudere (score={net_score:.1f})"
        }

    # Logica di protezione (solo se AI_FREE_MODE è False):
    # - Se LONG e score >= -REVERSAL_THRESHOLD → NON chiudere (trend non invertito)
    # - Se SHORT e score <= +REVERSAL_THRESHOLD → NON chiudere (trend non invertito)

    if direction == "long":
        # Per LONG, chiudi solo se score < -THRESHOLD (inversione bearish confermata)
        if net_score >= -SCORE_THRESHOLD_CLOSE_REVERSAL:
            return {
                "allow_close": False,
                "reason": f"PROTECT LONG: score {net_score:.1f} >= -{SCORE_THRESHOLD_CLOSE_REVERSAL} (no inversione)"
            }
        else:
            return {
                "allow_close": True,
                "reason": f"ALLOW CLOSE LONG: score {net_score:.1f} < -{SCORE_THRESHOLD_CLOSE_REVERSAL} (inversione confermata)"
            }
    else:  # short
        # Per SHORT, chiudi solo se score > +THRESHOLD (inversione bullish confermata)
        if net_score <= SCORE_THRESHOLD_CLOSE_REVERSAL:
            return {
                "allow_close": False,
                "reason": f"PROTECT SHORT: score {net_score:.1f} <= +{SCORE_THRESHOLD_CLOSE_REVERSAL} (no inversione)"
            }
        else:
            return {
                "allow_close": True,
                "reason": f"ALLOW CLOSE SHORT: score {net_score:.1f} > +{SCORE_THRESHOLD_CLOSE_REVERSAL} (inversione confermata)"
            }


def evaluate_position_override(
    result: Dict[str, Any],
    positions: List[Dict[str, Any]],
    scores: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Valuta se l'operazione richiesta dall'AI deve essere modificata
    in base a trailing stop, stop loss, e protezione chiusure.

    Args:
        result: Decisione AI originale
        positions: Lista delle posizioni aperte
        scores: Score calcolati per ogni symbol

    Returns:
        result modificato se necessario
    """
    # Import db_utils qui per evitare import circolare
    try:
        import db_utils
    except ImportError:
        print("⚠️  db_utils non disponibile per tracking posizioni")
        return result

    symbol = result.get("symbol", "")
    operation = result.get("operation", "hold")

    # Trova la posizione aperta per questo symbol
    position = None
    for pos in positions:
        if pos.get("symbol") == symbol:
            position = pos
            break

    # Se non c'è posizione aperta per questo symbol, niente override
    if not position:
        # Se l'AI vuole aprire una nuova posizione, crea il tracking
        if operation == "open":
            print(f"   📝 Nuova posizione {symbol}: tracking verrà creato dopo apertura")
        return result

    # Ottieni tracking data dal DB
    tracking_data = db_utils.get_position_tracking(symbol)

    # Ottieni score per questo symbol
    score = scores.get(symbol, {})
    current_price = float(position.get("mark_price", 0))
    direction = position.get("side", "long")

    # CHECK 1: Trailing Stop / Stop Loss
    trailing_result = check_trailing_stop(position, current_price, tracking_data)

    # Aggiorna tracking nel DB
    if current_price > 0:
        db_utils.upsert_position_tracking(
            symbol=symbol,
            direction=direction,
            entry_price=float(position.get("entry_price", current_price)),
            current_price=current_price,
            trailing_active=trailing_result.get("trailing_active", False)
        )

    # Se trailing/stop loss triggerato → FORZA CLOSE
    if trailing_result.get("triggered", False):
        print(f"🛑 {trailing_result['reason']}")
        result["operation"] = "close"
        result["_override_reason"] = trailing_result["reason"]
        # Elimina tracking dopo close
        result["_delete_tracking"] = True
        return result

    # CHECK 2: Protezione chiusure premature
    if operation == "close":
        close_check = check_close_protection(position, score, ai_wants_close=True)

        if not close_check.get("allow_close", True):
            print(f"🛡️  {close_check['reason']}")
            print(f"   AI voleva: CLOSE {symbol} → Forzato: HOLD")
            result["operation"] = "hold"
            result["_override_reason"] = close_check["reason"]
            return result
        else:
            print(f"✅ {close_check['reason']}")
            # Elimina tracking dopo close
            result["_delete_tracking"] = True

    # Log stato trailing
    if trailing_result.get("trailing_active"):
        print(f"   📊 Trailing attivo per {symbol}: profit={trailing_result.get('profit_pct', 0):.2f}%, "
              f"dal peak={trailing_result.get('profit_from_peak_pct', 0):.2f}%")

    return result


def calculate_scores_for_symbols(indicators_data: list, sentiment_data: dict, forecasts_data: list) -> dict:
    """
    Calcola gli score per ogni simbolo basandosi sui dati disponibili.

    Args:
        indicators_data: Lista di dizionari con indicatori per ogni ticker
        sentiment_data: Dizionario con Fear & Greed Index
        forecasts_data: Lista di dizionari con previsioni Prophet

    Returns:
        dict con score per ogni simbolo: {'BTC': {...}, 'ETH': {...}, 'SOL': {...}}
    """
    global _last_signal_scores

    if not SCORING_ENABLED:
        return {}

    scores = {}

    # Estrai Fear & Greed (globale per tutti i simboli)
    fear_greed = 50  # default neutrale
    if sentiment_data and isinstance(sentiment_data, dict):
        fear_greed = sentiment_data.get('valore', sentiment_data.get('value', 50))
        if fear_greed is None:
            fear_greed = 50
    elif sentiment_data:
        print(f"[DEBUG] sentiment_data non è un dict: {type(sentiment_data)}")

    # Crea mappa forecast per ticker
    forecast_map = {}
    if forecasts_data and isinstance(forecasts_data, list):
        for fc in forecasts_data:
            if not isinstance(fc, dict):
                print(f"[DEBUG] forecast item non è un dict: {type(fc)}")
                continue
            ticker = fc.get('Ticker') or fc.get('ticker')
            timeframe = fc.get('Timeframe') or fc.get('timeframe', '')
            change_pct = fc.get('Variazione %') or fc.get('change_pct', 0)

            # Usa forecast a 15 min se disponibile
            if ticker and 'Prossimi 15' in str(timeframe):
                try:
                    forecast_map[ticker] = float(change_pct) if change_pct else 0
                except (ValueError, TypeError):
                    forecast_map[ticker] = 0

    # Calcola score per ogni ticker
    if indicators_data and isinstance(indicators_data, list):
        for ind in indicators_data:
            if not isinstance(ind, dict):
                print(f"[DEBUG] indicator item non è un dict: {type(ind)}")
                continue
            ticker = ind.get('ticker')
            if not ticker:
                continue

            # Estrai valori indicatori
            current = ind.get('current', {})
            if not isinstance(current, dict):
                current = {}
            price = current.get('price', 0)
            ema20 = current.get('ema20', price)
            rsi = current.get('rsi_7', 50)
            macd = current.get('macd', 0)

            # Volume
            volume_str = ind.get('volume', '')
            volume_bid, volume_ask = 0, 0
            if isinstance(volume_str, str) and 'Bid Vol' in volume_str:
                try:
                    parts = volume_str.replace('Bid Vol:', '').split('Ask Vol:')
                    volume_bid = float(parts[0].strip().strip(','))
                    volume_ask = float(parts[1].strip())
                except:
                    pass

            # Forecast per questo ticker
            forecast_change = forecast_map.get(ticker, 0)

            # Calcola score
            try:
                score_result = calculate_signal_score(
                    price=float(price) if price else 0,
                    ema20=float(ema20) if ema20 else 0,
                    rsi=float(rsi) if rsi else 50,
                    macd=float(macd) if macd else 0,
                    fear_greed=int(fear_greed),
                    forecast_change_pct=float(forecast_change),
                    volume_bid=float(volume_bid),
                    volume_ask=float(volume_ask),
                    symbol=ticker  # Per volume smoothing history
                )
                scores[ticker] = score_result
                print(f"   📊 {ticker} Score: BULL={score_result['score_bullish']:.1f} "
                      f"BEAR={score_result['score_bearish']:.1f} "
                      f"NET={score_result['net_score']:.1f} → {score_result['direction']}")
            except Exception as e:
                print(f"   ⚠️  Errore calcolo score per {ticker}: {e}")

    _last_signal_scores = scores
    return scores


def get_last_signal_scores() -> dict:
    """Restituisce l'ultimo score calcolato (per logging nel DB)."""
    return _last_signal_scores


def enhance_prompt_with_scoring(prompt: str, scores: dict) -> str:
    """
    Aggiunge le informazioni di scoring al prompt per guidare l'AI.
    """
    if not scores:
        return prompt

    scoring_section = "\n\n=== SIGNAL SCORING ANALYSIS ===\n"
    scoring_section += "Pre-calculated signal scores based on technical indicators:\n\n"

    for ticker, score in scores.items():
        direction = score.get('direction', 'HOLD')
        confidence = score.get('confidence', 'WEAK')
        net = score.get('net_score', 0)

        # Emoji basato sulla direzione
        if direction == 'LONG':
            emoji = "🟢"
        elif direction == 'SHORT':
            emoji = "🔴"
        else:
            emoji = "⚪"

        scoring_section += f"{emoji} {ticker}: {direction} (confidence: {confidence}, net_score: {net:.1f})\n"

        # Dettagli segnali principali
        signals = score.get('signals', [])
        active_signals = [s for s in signals if s.get('contribution', 0) > 0]
        if active_signals:
            for sig in active_signals[:3]:  # Max 3 segnali principali
                scoring_section += f"   - {sig['indicator']}: {sig['direction']} (+{sig['contribution']:.1f})\n"

    scoring_section += f"\nIMPORTANT: Use this scoring as guidance for your decision. "
    scoring_section += f"If NET_SCORE > {SCORE_THRESHOLD_OPEN}, prefer LONG. If NET_SCORE < -{SCORE_THRESHOLD_OPEN}, prefer SHORT. "
    scoring_section += f"If |NET_SCORE| < {SCORE_THRESHOLD_OPEN}, prefer HOLD unless you have strong conviction.\n"
    scoring_section += "================================\n"

    # Inserisci prima del JSON format
    if "Analyze the market" in prompt:
        prompt = prompt.replace(
            "Analyze the market and portfolio",
            scoring_section + "\nAnalyze the market and portfolio"
        )
    else:
        prompt = scoring_section + prompt

    return prompt


def previsione_trading_agent(prompt, indicators=None, sentiment=None, forecasts=None, open_positions=None):
    """
    Chiama l'AI (OpenAI o OpenRouter) per ottenere decisioni di trading.
    Supporta multipli modelli con gestione robusta del JSON.

    Args:
        prompt: Il prompt da inviare all'AI
        indicators: Lista di indicatori tecnici (opzionale, per scoring)
        sentiment: Dati sentiment Fear & Greed (opzionale, per scoring)
        forecasts: Lista previsioni Prophet (opzionale, per scoring)
        open_positions: Lista delle posizioni aperte (opzionale, per trailing stop)
    """
    # Calcola score se dati disponibili
    scores = {}
    if SCORING_ENABLED and (indicators or sentiment or forecasts):
        scores = calculate_scores_for_symbols(
            indicators_data=indicators or [],
            sentiment_data=sentiment or {},
            forecasts_data=forecasts or []
        )

        # Arricchisci il prompt con lo scoring
        if scores:
            prompt = enhance_prompt_with_scoring(prompt, scores)

    try:
        # Determina se usare response_format JSON nativo
        use_json_format = MODEL in MODELS_WITH_JSON_SUPPORT

        # Chiamata con retry automatico (passa scores per validazione)
        result = call_ai_api(
            prompt,
            use_json_format=use_json_format,
            max_retries=2,
            signal_scores=scores
        )

        # ===== SISTEMA DI OVERRIDE COMPLETO =====

        # 1. Non permettere all'AI di aprire posizioni se lo score è sotto soglia
        #    ECCEZIONE: Se AI_FREE_MODE è attivo, l'AI decide liberamente
        if scores and result.get('symbol') in scores:
            score = scores[result['symbol']]
            net_score = score.get('net_score', 0)
            threshold = score.get('thresholds', {}).get('open', 15.0)

            # Se score sotto soglia E AI vuole aprire → FORZA HOLD
            # ECCEZIONI: AI_FREE_MODE o DOUBLE_CHECK_AI_ENABLED (AI decide in base a indicatori reali)
            if abs(net_score) < threshold and result.get('operation') == 'open':
                if AI_FREE_MODE:
                    # AI_FREE_MODE: lascia decidere l'AI, non forzare HOLD
                    print(f"🆓 AI_FREE_MODE: AI vuole OPEN con score={net_score:.1f} (sotto soglia {threshold}) → PERMESSO")
                elif DOUBLE_CHECK_AI_ENABLED:
                    # DOUBLE_CHECK: AI ha già validato con indicatori reali, bypassa score threshold
                    print(f"🔍 DOUBLE_CHECK: AI vuole OPEN con score={net_score:.1f} (sotto soglia {threshold}) → PERMESSO (validato da indicatori)")
                else:
                    original_decision = f"{result['operation']} {result['direction']}"
                    print(f"⚠️  OVERRIDE OPEN: net_score={net_score:.1f} < threshold={threshold}")
                    print(f"   AI voleva: {original_decision} → Forzato: HOLD")
                    result['operation'] = 'hold'
                    result['_override_reason'] = f"Score {net_score:.1f} sotto soglia {threshold}. AI voleva: {original_decision}"

        # 2. Trailing Stop, Stop Loss, e Protezione Chiusure Premature
        if open_positions is not None:
            result = evaluate_position_override(result, open_positions, scores)

        # ===== FINE OVERRIDE =====

        # Aggiungi info scoring al risultato per logging
        if scores and result.get('symbol') in scores:
            result['_signal_score'] = scores[result['symbol']]

        print(f"✅ Decisione AI: {result['operation']} {result['symbol']} {result['direction']} - {result['reason'][:80]}...")
        return result

    except Exception as e:
        print(f"❌ Errore nella chiamata AI dopo tutti i retry: {e}")
        # Fallback: HOLD in caso di errore
        return {
            "operation": "hold",
            "symbol": "BTC",
            "direction": "long",
            "target_portion_of_balance": 0.0,
            "leverage": 1,
            "reason": f"Error calling AI after retries: {str(e)}"
        }
