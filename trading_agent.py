from openai import OpenAI
from dotenv import load_dotenv
import os
import json

load_dotenv()

# Configurazione AI Provider
AI_PROVIDER = os.getenv('AI_PROVIDER', 'openai').lower()

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
    MODEL = "gpt-4-turbo"
    print(f"🤖 Usando OpenAI con modello: {MODEL}")


def previsione_trading_agent(prompt):
    """
    Chiama l'AI (OpenAI o OpenRouter) per ottenere decisioni di trading.
    """
    try:
        # Chiamata API compatibile con OpenAI e OpenRouter
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You are a cryptocurrency trading AI. Always respond with valid JSON matching the required schema."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            response_format={"type": "json_object"},
            temperature=0.7
        )
        result = json.loads(response.choices[0].message.content)

        # Validazione base del risultato
        required_fields = ["operation", "symbol", "reason"]
        for field in required_fields:
            if field not in result:
                raise ValueError(f"Campo mancante nella risposta AI: {field}")

        print(f"✅ Decisione AI: {result['operation']} {result.get('symbol')} - {result.get('reason')}")
        return result

    except Exception as e:
        print(f"❌ Errore nella chiamata AI: {e}")
        # Fallback: HOLD in caso di errore
        return {
            "operation": "hold",
            "symbol": "BTC",
            "direction": "long",
            "target_portion_of_balance": 0.0,
            "leverage": 1,
            "reason": f"Error calling AI: {str(e)}"
        }