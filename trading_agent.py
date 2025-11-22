from dotenv import load_dotenv
import os
import json
import re

load_dotenv()

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


def validate_trading_decision(result):
    """
    Valida che la decisione di trading abbia tutti i campi richiesti.
    Aggiunge campi mancanti con valori di default se possibile.
    """
    required_fields = ["operation", "symbol"]  # Solo questi sono veramente obbligatori

    # Validazione campi obbligatori
    for field in required_fields:
        if field not in result:
            raise ValueError(f"Campo mancante nella risposta AI: {field}")

    # Aggiungi campi opzionali con default se mancanti
    if "direction" not in result:
        result["direction"] = "long"

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


def call_ai_api(prompt, use_json_format=True, max_retries=2):
    """
    Chiama l'API AI con retry logic e gestione flessibile del JSON.

    Args:
        prompt: Il prompt da inviare
        use_json_format: Se usare response_format=json_object (solo per modelli compatibili)
        max_retries: Numero massimo di tentativi
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

            # Valida e normalizza il risultato
            result = validate_trading_decision(result)

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


def previsione_trading_agent(prompt):
    """
    Chiama l'AI (OpenAI o OpenRouter) per ottenere decisioni di trading.
    Supporta multipli modelli con gestione robusta del JSON.
    """
    try:
        # Determina se usare response_format JSON nativo
        use_json_format = MODEL in MODELS_WITH_JSON_SUPPORT

        # Chiamata con retry automatico
        result = call_ai_api(prompt, use_json_format=use_json_format, max_retries=2)

        print(f"✅ Decisione AI: {result['operation']} {result['symbol']} - {result['reason'][:80]}...")
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
