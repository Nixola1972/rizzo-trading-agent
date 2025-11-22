from dotenv import load_dotenv
import os
import json
import re

load_dotenv()

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
    """
    # Cerca pattern JSON (oggetto tra { })
    json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
    matches = re.finditer(json_pattern, text, re.DOTALL)

    for match in matches:
        try:
            potential_json = match.group(0)
            parsed = json.loads(potential_json)
            # Verifica che sia un dizionario (non array)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue

    # Se non trova JSON, prova a fare parse diretto
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


def call_ai_api(prompt, use_json_format=True, max_retries=2, signal_scores=None):
    """
    Chiama l'API AI con retry logic e gestione flessibile del JSON.

    Args:
        prompt: Il prompt da inviare
        use_json_format: Se usare response_format=json_object (solo per modelli compatibili)
        max_retries: Numero massimo di tentativi
        signal_scores: Dizionario con score calcolati per ogni symbol (per validazione)
    """
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
                "temperature": 0.7
            }

            # Aggiungi response_format solo per modelli che lo supportano
            if use_json_format and MODEL in MODELS_WITH_JSON_SUPPORT:
                call_params["response_format"] = {"type": "json_object"}
                if attempt == 0:
                    print(f"   📋 Usando formato JSON nativo (supportato da {MODEL})")
            else:
                if attempt == 0:
                    print(f"   📝 Usando parsing JSON manuale (modello: {MODEL})")

            # Chiamata API
            response = client.chat.completions.create(**call_params)
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

            return result

        except json.JSONDecodeError as e:
            print(f"   ⚠️  Tentativo {attempt + 1}/{max_retries + 1}: Errore parsing JSON - {e}")
            if attempt < max_retries:
                print(f"   🔄 Riprovo con prompt più esplicito...")
                # Aggiungi enfasi sul formato JSON nel prompt
                if "IMPORTANT: Respond ONLY with a valid JSON object" not in prompt:
                    prompt = "IMPORTANT: Respond ONLY with a valid JSON object, no other text.\n\n" + prompt
            else:
                raise

        except ValueError as e:
            print(f"   ⚠️  Tentativo {attempt + 1}/{max_retries + 1}: Validazione fallita - {e}")
            if attempt < max_retries:
                print(f"   🔄 Riprovo...")
            else:
                raise

        except Exception as e:
            print(f"   ❌ Tentativo {attempt + 1}/{max_retries + 1}: Errore API - {e}")
            if attempt < max_retries:
                print(f"   🔄 Riprovo...")
                # Rimuovi response_format se causava problemi
                use_json_format = False
            else:
                raise

    # Non dovrebbe mai arrivare qui
    raise RuntimeError("Tutti i tentativi falliti")


# Variabile globale per memorizzare l'ultimo score calcolato
_last_signal_scores = {}


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
                    volume_ask=float(volume_ask)
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

    scoring_section += "\nIMPORTANT: Use this scoring as guidance for your decision. "
    scoring_section += "If NET_SCORE > 15, prefer LONG. If NET_SCORE < -15, prefer SHORT. "
    scoring_section += "If |NET_SCORE| < 15, prefer HOLD unless you have strong conviction.\n"
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


def previsione_trading_agent(prompt, indicators=None, sentiment=None, forecasts=None):
    """
    Chiama l'AI (OpenAI o OpenRouter) per ottenere decisioni di trading.
    Supporta multipli modelli con gestione robusta del JSON.

    Args:
        prompt: Il prompt da inviare all'AI
        indicators: Lista di indicatori tecnici (opzionale, per scoring)
        sentiment: Dati sentiment Fear & Greed (opzionale, per scoring)
        forecasts: Lista previsioni Prophet (opzionale, per scoring)
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
