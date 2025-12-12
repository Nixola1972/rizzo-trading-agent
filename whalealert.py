import requests
from datetime import datetime
import json

def get_whale_alerts():
    """
    Recupera i dati whale alerts e formatta gli alert in modo leggibile
    """
    url = "https://whale-alert.io/data.json?alerts=9&prices=BTC&hodl=bitcoin%2CBTC&potential_profit=bitcoin%2CBTC&average_buy_price=bitcoin%2CBTC&realized_profit=bitcoin%2CBTC&volume=bitcoin%2CBTC&news=true"
    
    try:
        # Fai la richiesta GET
        response = requests.get(url)
        response.raise_for_status()
        
        # Parse JSON
        data = response.json()
        
        # Estrai gli alerts
        alerts = data.get('alerts', [])
        
        if not alerts:
            print("Nessun alert trovato.")
            return
        
        print("🐋 WHALE ALERTS - MOVIMENTI CRYPTO SIGNIFICATIVI 🐋\n")
        print("=" * 80)
        
        for alert in alerts:
            # Parse l'alert string (formato: timestamp,emoji,amount,usd_value,description,link)
            parts = alert.split(',', 5)
            
            if len(parts) >= 6:
                timestamp = parts[0]
                emoji = parts[1]
                amount = parts[2].strip('"')
                usd_value = parts[3].strip('"')
                description = parts[4].strip('"')
                link = parts[5]
                
                # Converti timestamp in data leggibile
                try:
                    dt = datetime.fromtimestamp(int(timestamp))
                    formatted_time = dt.strftime("%d/%m/%Y %H:%M:%S")
                except:
                    formatted_time = "N/A"
                
                # Stampa alert formattato
                print(f"\n{emoji} ALERT del {formatted_time}")
                print(f"💰 Importo: {amount}")
                print(f"💵 Valore USD: {usd_value}")
                print(f"📝 Descrizione: {description}")
                print(f"🔗 Link: {link}")
                print("-" * 80)
        
    except requests.exceptions.RequestException as e:
        print(f"Errore nella richiesta: {e}")
    except json.JSONDecodeError as e:
        print(f"Errore nel parsing JSON: {e}")
    except Exception as e:
        print(f"Errore generico: {e}")

def format_whale_alerts_to_string():
    """
    Versione che ritorna una stringa formattata invece di stampare
    """
    url = "https://whale-alert.io/data.json?alerts=9&prices=BTC&hodl=bitcoin%2CBTC&potential_profit=bitcoin%2CBTC&average_buy_price=bitcoin%2CBTC&realized_profit=bitcoin%2CBTC&volume=bitcoin%2CBTC&news=true"
    
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        
        alerts = data.get('alerts', [])
        
        if not alerts:
            return "Nessun alert trovato."
        
        result = "🐋 WHALE ALERTS - MOVIMENTI CRYPTO SIGNIFICATIVI 🐋\n\n"        
        for alert in alerts:
            parts = alert.split(',', 5)
            
            if len(parts) >= 6:
                timestamp = parts[0]
                emoji = parts[1]
                amount = parts[2].strip('"')
                usd_value = parts[3].strip('"')
                description = parts[4].strip('"')
                link = parts[5]
                
                try:
                    dt = datetime.fromtimestamp(int(timestamp))
                    formatted_time = dt.strftime("%d/%m/%Y %H:%M:%S")
                except:
                    formatted_time = "N/A"
                
                result += f"\n{emoji} ALERT del {formatted_time}\n"
                result += f"Importo: {amount}\n"
                result += f"Valore USD: {usd_value}\n"
                result += f"Descrizione: {description}\n"
                result += "\n"
        
        return result
        
    except Exception as e:
        return f"Errore: {e}"

# ============================================================================
# NUOVA FUNZIONE: Whale Alerts in formato JSON strutturato per AI
# ============================================================================

# Liste exchange conosciuti per classificazione
KNOWN_EXCHANGES = [
    'binance', 'coinbase', 'kraken', 'bitfinex', 'huobi', 'okx', 'okex',
    'kucoin', 'bybit', 'ftx', 'gemini', 'bitstamp', 'crypto.com', 'gate.io',
    'bittrex', 'poloniex', 'bitmex', 'deribit', 'mexc', 'bitget'
]

def _parse_amount(amount_str: str) -> tuple:
    """
    Parse amount string like '500 BTC' or '10,000 ETH' into (value, symbol)
    """
    try:
        # Rimuovi virgole e spazi extra
        clean = amount_str.replace(',', '').strip()
        parts = clean.split()
        if len(parts) >= 2:
            value = float(parts[0])
            symbol = parts[1].upper()
            return value, symbol
    except:
        pass
    return 0.0, "UNKNOWN"


def _parse_usd_value(usd_str: str) -> float:
    """
    Parse USD value string like '$50,000,000' or '50M' into float
    """
    try:
        clean = usd_str.replace('$', '').replace(',', '').strip()
        # Handle M/B suffixes
        if clean.endswith('M'):
            return float(clean[:-1]) * 1_000_000
        elif clean.endswith('B'):
            return float(clean[:-1]) * 1_000_000_000
        elif clean.endswith('K'):
            return float(clean[:-1]) * 1_000
        return float(clean)
    except:
        return 0.0


def _classify_whale_movement(description: str) -> dict:
    """
    Classifica il movimento whale come bullish/bearish basandosi sulla descrizione.

    Logica:
    - TO exchange = exchange_inflow = BEARISH (whales depositing to sell)
    - FROM exchange = exchange_outflow = BULLISH (whales withdrawing to hold)
    - TO unknown wallet = accumulation = BULLISH
    - Unknown to unknown = neutral (internal transfer)

    Returns:
        dict con movement_type, sentiment, confidence
    """
    desc_lower = description.lower()

    # Identifica source e destination
    from_exchange = False
    to_exchange = False
    from_unknown = 'from unknown' in desc_lower or 'from an unknown' in desc_lower
    to_unknown = 'to unknown' in desc_lower or 'to an unknown' in desc_lower

    for exchange in KNOWN_EXCHANGES:
        if f'from {exchange}' in desc_lower:
            from_exchange = True
        if f'to {exchange}' in desc_lower:
            to_exchange = True

    # Classifica movimento
    if to_exchange and not from_exchange:
        # Deposito su exchange = probabile vendita
        return {
            "movement_type": "exchange_inflow",
            "sentiment": "bearish",
            "confidence": "high",
            "reason": "Whale depositing to exchange (likely selling)"
        }
    elif from_exchange and not to_exchange:
        # Prelievo da exchange = accumulation
        return {
            "movement_type": "exchange_outflow",
            "sentiment": "bullish",
            "confidence": "high",
            "reason": "Whale withdrawing from exchange (likely holding)"
        }
    elif from_exchange and to_exchange:
        # Transfer tra exchange = neutral
        return {
            "movement_type": "inter_exchange",
            "sentiment": "neutral",
            "confidence": "medium",
            "reason": "Transfer between exchanges"
        }
    elif from_unknown and to_unknown:
        # Unknown to unknown = potrebbe essere accumulation o internal
        return {
            "movement_type": "wallet_transfer",
            "sentiment": "neutral",
            "confidence": "low",
            "reason": "Transfer between unknown wallets"
        }
    elif to_unknown:
        # A wallet sconosciuto = accumulation
        return {
            "movement_type": "accumulation",
            "sentiment": "bullish",
            "confidence": "medium",
            "reason": "Transfer to unknown wallet (possible accumulation)"
        }
    else:
        return {
            "movement_type": "unknown",
            "sentiment": "neutral",
            "confidence": "low",
            "reason": "Unable to classify movement"
        }


def get_whale_alerts_json(max_alerts: int = 9) -> dict:
    """
    Recupera whale alerts in formato JSON strutturato per AI.

    Returns:
        dict con:
        - alerts: lista di alert strutturati
        - summary: analisi aggregata (net flow, sentiment)
        - symbols_affected: simboli coinvolti
    """
    url = f"https://whale-alert.io/data.json?alerts={max_alerts}&prices=BTC&hodl=bitcoin%2CBTC"

    result = {
        "alerts": [],
        "summary": {
            "total_alerts": 0,
            "bullish_signals": 0,
            "bearish_signals": 0,
            "neutral_signals": 0,
            "net_sentiment": "neutral",
            "total_usd_volume": 0,
            "exchange_inflow_usd": 0,
            "exchange_outflow_usd": 0,
            "net_flow": "neutral",
            "net_flow_usd": 0
        },
        "by_symbol": {},
        "error": None
    }

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        raw_alerts = data.get('alerts', [])

        if not raw_alerts:
            result["error"] = "No alerts found"
            return result

        # Parse ogni alert
        for alert in raw_alerts:
            parts = alert.split(',', 5)

            if len(parts) >= 6:
                timestamp_str = parts[0]
                emoji = parts[1]
                amount_str = parts[2].strip('"')
                usd_str = parts[3].strip('"')
                description = parts[4].strip('"')
                link = parts[5]

                # Parse valori
                amount, symbol = _parse_amount(amount_str)
                usd_value = _parse_usd_value(usd_str)

                # Timestamp
                try:
                    ts = int(timestamp_str)
                    dt = datetime.fromtimestamp(ts)
                    iso_time = dt.isoformat()
                except:
                    ts = 0
                    iso_time = None

                # Classifica movimento
                classification = _classify_whale_movement(description)

                # Crea alert strutturato
                structured_alert = {
                    "timestamp": iso_time,
                    "timestamp_unix": ts,
                    "symbol": symbol,
                    "amount": amount,
                    "usd_value": usd_value,
                    "description": description,
                    "movement_type": classification["movement_type"],
                    "sentiment": classification["sentiment"],
                    "confidence": classification["confidence"],
                    "reason": classification["reason"]
                }

                result["alerts"].append(structured_alert)

                # Aggiorna summary
                result["summary"]["total_alerts"] += 1
                result["summary"]["total_usd_volume"] += usd_value

                if classification["sentiment"] == "bullish":
                    result["summary"]["bullish_signals"] += 1
                elif classification["sentiment"] == "bearish":
                    result["summary"]["bearish_signals"] += 1
                else:
                    result["summary"]["neutral_signals"] += 1

                # Track exchange flows
                if classification["movement_type"] == "exchange_inflow":
                    result["summary"]["exchange_inflow_usd"] += usd_value
                elif classification["movement_type"] == "exchange_outflow":
                    result["summary"]["exchange_outflow_usd"] += usd_value

                # By symbol stats
                if symbol not in result["by_symbol"]:
                    result["by_symbol"][symbol] = {
                        "count": 0,
                        "total_usd": 0,
                        "bullish": 0,
                        "bearish": 0,
                        "net_sentiment": "neutral"
                    }

                result["by_symbol"][symbol]["count"] += 1
                result["by_symbol"][symbol]["total_usd"] += usd_value
                if classification["sentiment"] == "bullish":
                    result["by_symbol"][symbol]["bullish"] += 1
                elif classification["sentiment"] == "bearish":
                    result["by_symbol"][symbol]["bearish"] += 1

        # Calcola net sentiment
        bullish = result["summary"]["bullish_signals"]
        bearish = result["summary"]["bearish_signals"]

        if bullish > bearish + 2:
            result["summary"]["net_sentiment"] = "bullish"
        elif bearish > bullish + 2:
            result["summary"]["net_sentiment"] = "bearish"
        else:
            result["summary"]["net_sentiment"] = "neutral"

        # Calcola net flow
        inflow = result["summary"]["exchange_inflow_usd"]
        outflow = result["summary"]["exchange_outflow_usd"]
        result["summary"]["net_flow_usd"] = outflow - inflow  # Positive = bullish

        if outflow > inflow * 1.5:
            result["summary"]["net_flow"] = "bullish"  # More outflow = accumulation
        elif inflow > outflow * 1.5:
            result["summary"]["net_flow"] = "bearish"  # More inflow = selling pressure
        else:
            result["summary"]["net_flow"] = "neutral"

        # Per-symbol net sentiment
        for sym, stats in result["by_symbol"].items():
            if stats["bullish"] > stats["bearish"]:
                stats["net_sentiment"] = "bullish"
            elif stats["bearish"] > stats["bullish"]:
                stats["net_sentiment"] = "bearish"
            else:
                stats["net_sentiment"] = "neutral"

    except requests.exceptions.RequestException as e:
        result["error"] = f"Request error: {str(e)}"
    except json.JSONDecodeError as e:
        result["error"] = f"JSON parse error: {str(e)}"
    except Exception as e:
        result["error"] = f"Error: {str(e)}"

    return result


def get_whale_sentiment_for_symbol(symbol: str) -> dict:
    """
    Ottiene il sentiment whale specifico per un simbolo.

    Args:
        symbol: Simbolo da cercare (es. "BTC", "ETH")

    Returns:
        dict con sentiment e dettagli per il simbolo
    """
    whale_data = get_whale_alerts_json()

    symbol_upper = symbol.upper()

    if whale_data.get("error"):
        return {
            "symbol": symbol_upper,
            "sentiment": "neutral",
            "confidence": "low",
            "reason": f"Whale data unavailable: {whale_data['error']}",
            "alerts_count": 0
        }

    symbol_stats = whale_data.get("by_symbol", {}).get(symbol_upper)

    if not symbol_stats:
        return {
            "symbol": symbol_upper,
            "sentiment": "neutral",
            "confidence": "low",
            "reason": "No whale movements detected for this symbol",
            "alerts_count": 0,
            "market_sentiment": whale_data["summary"]["net_sentiment"]  # Overall market
        }

    return {
        "symbol": symbol_upper,
        "sentiment": symbol_stats["net_sentiment"],
        "confidence": "high" if symbol_stats["count"] >= 3 else "medium",
        "reason": f"{symbol_stats['bullish']} bullish, {symbol_stats['bearish']} bearish movements",
        "alerts_count": symbol_stats["count"],
        "total_volume_usd": symbol_stats["total_usd"],
        "market_sentiment": whale_data["summary"]["net_sentiment"]
    }


# Esempio di utilizzo
if __name__ == "__main__":
    # Versione che stampa direttamente
    get_whale_alerts()

    print("\n" + "="*80)
    print("JSON STRUCTURED VERSION:")
    print("="*80)

    # Versione JSON strutturata
    whale_json = get_whale_alerts_json()
    print(json.dumps(whale_json, indent=2, default=str))