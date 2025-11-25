import json
import os
from decimal import Decimal, ROUND_DOWN
from typing import Dict, Any

import eth_account
from dotenv import load_dotenv

load_dotenv()
from eth_account.signers.local import LocalAccount

from hyperliquid.info import Info
from hyperliquid.exchange import Exchange
from hyperliquid.utils import constants


class HyperLiquidTrader:
    def __init__(
        self,
        secret_key: str,
        account_address: str,
        testnet: bool = True,
        skip_ws: bool = True,
    ):
        self.secret_key = secret_key
        self.account_address = account_address

        base_url = constants.TESTNET_API_URL if testnet else constants.MAINNET_API_URL
        self.base_url = base_url

        # crea account signer
        account: LocalAccount = eth_account.Account.from_key(secret_key)

        self.info = Info(base_url, skip_ws=skip_ws)
        self.exchange = Exchange(account, base_url, account_address=account_address)

        # cache meta per tick-size e min-size
        self.meta = self.info.meta()

    def _get_tick_size(self, symbol: str) -> float:
        """Ottiene il tick size per un simbolo da meta."""
        try:
            for asset in self.meta.get("universe", []):
                if asset.get("name") == symbol:
                    # szDecimals indica i decimali per la size
                    # Per il prezzo, usiamo un approccio basato sul prezzo corrente
                    sz_decimals = asset.get("szDecimals", 8)
                    # Tick size tipici per Hyperliquid
                    if symbol == "BTC":
                        return 1.0  # BTC tick size è $1
                    elif symbol == "ETH":
                        return 0.1  # ETH tick size è $0.10
                    elif symbol == "SOL":
                        return 0.01  # SOL tick size è $0.01
                    else:
                        return 0.01  # Default
            return 0.01
        except Exception:
            return 0.01

    def _round_to_tick(self, price: float, symbol: str) -> float:
        """Arrotonda il prezzo al tick size più vicino."""
        tick_size = self._get_tick_size(symbol)
        return round(round(price / tick_size) * tick_size, 8)

    def _to_hl_size(self, size_decimal: Decimal) -> str:
        # HL accetta max 8 decimali
        size_clamped = size_decimal.quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)
        return format(size_clamped, "f")   # HL vuole stringa decimale perfetta

    # ----------------------------------------------------------------------
    #                            VALIDAZIONE INPUT
    # ----------------------------------------------------------------------
    def _validate_order_input(self, order_json: Dict[str, Any]):
        required_fields = [
            "operation",
            "symbol",
            "direction",
            "target_portion_of_balance",
            "leverage",
            "reason",
        ]

        for f in required_fields:
            if f not in order_json:
                raise ValueError(f"Missing required field: {f}")

        if order_json["operation"] not in ("open", "close", "hold"):
            raise ValueError("operation must be 'open', 'close', or 'hold'")

        if order_json["direction"] not in ("long", "short"):
            raise ValueError("direction must be 'long' or 'short'")

        try:
            float(order_json["target_portion_of_balance"])
        except:
            raise ValueError("target_portion_of_balance must be a number")

    # ----------------------------------------------------------------------
    #                           MIN SIZE / TICK SIZE
    # ----------------------------------------------------------------------
    def _get_min_tick_for_symbol(self, symbol: str) -> Decimal:
        """
        Hyperliquid definisce per ogni asset un tick size.
        Lo leggiamo da meta().
        """
        for perp in self.meta["universe"]:
            if perp["name"] == symbol:
                return Decimal(str(perp["szDecimals"]))
        return Decimal("0.00000001")  # fallback a 1e-8

    def _round_size(self, size: Decimal, decimals: int) -> float:
        """
        Hyperliquid accetta massimo 8 decimali.
        Inoltre dobbiamo rispettare il tick size.
        """
        # prima clamp a 8 decimali
        size = size.quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)

        # poi count of decimals per il tick
        fmt = f"{{0:.{decimals}f}}"
        return float(fmt.format(size))

    # ----------------------------------------------------------------------
    #                        GESTIONE LEVA
    # ----------------------------------------------------------------------
    def get_current_leverage(self, symbol: str) -> Dict[str, Any]:
        """Ottieni info sulla leva corrente per un simbolo"""
        try:
            user_state = self.info.user_state(self.account_address)
            
            # Cerca nelle posizioni aperte
            for position in user_state.get('assetPositions', []):
                pos = position.get('position', {})
                coin = pos.get('coin', '')
                if coin == symbol:
                    leverage_info = pos.get('leverage', {})
                    return {
                        'value': leverage_info.get('value', 0),
                        'type': leverage_info.get('type', 'unknown'),
                        'coin': coin
                    }
            
            # Se non c'è posizione aperta, controlla cross leverage default
            cross_leverage = user_state.get('crossLeverage', 20)
            return {
                'value': cross_leverage,
                'type': 'cross',
                'coin': symbol,
                'note': 'No open position, showing account default'
            }
            
        except Exception as e:
            print(f"Errore ottenendo leva corrente: {e}")
            return {'value': 20, 'type': 'unknown', 'error': str(e)}

    def set_leverage_for_symbol(self, symbol: str, leverage: int, is_cross: bool = True) -> Dict[str, Any]:
        """Imposta la leva per un simbolo specifico usando il metodo corretto"""
        try:
            print(f"🔧 Impostando leva {leverage}x per {symbol} ({'cross' if is_cross else 'isolated'} margin)")
            
            # Usa il metodo update_leverage con i parametri corretti
            result = self.exchange.update_leverage(
                leverage=leverage,      # int
                name=symbol,           # str - nome del simbolo come "BTC"
                is_cross=is_cross      # bool
            )
            
            if result.get('status') == 'ok':
                print(f"✅ Leva impostata con successo a {leverage}x per {symbol}")
            else:
                print(f"⚠️ Risposta dall'exchange: {result}")
                
            return result
            
        except Exception as e:
            print(f"❌ Errore impostando leva per {symbol}: {e}")
            return {"status": "error", "error": str(e)}

    # ----------------------------------------------------------------------
    #                        ESECUZIONE SEGNALE AI
    # ----------------------------------------------------------------------
    def execute_signal(self, order_json: Dict[str, Any]) -> Dict[str, Any]:
        from decimal import Decimal, ROUND_DOWN

        self._validate_order_input(order_json)

        op = order_json["operation"]
        symbol = order_json["symbol"]
        direction = order_json["direction"]
        portion = Decimal(str(order_json["target_portion_of_balance"]))
        leverage = int(order_json.get("leverage", 1))

        if op == "hold":
            print(f"[HyperLiquidTrader] HOLD — nessuna azione per {symbol}.")
            return {"status": "hold", "message": "No action taken."}

        if op == "close":
            print(f"[HyperLiquidTrader] Market CLOSE per {symbol}")
            return self.exchange.market_close(symbol)

        # OPEN --------------------------------------------------------
        # Prima di aprire la posizione, imposta la leva desiderata
        leverage_result = self.set_leverage_for_symbol(
            symbol=symbol,
            leverage=leverage,
            is_cross=True  # Puoi cambiare in False per isolated margin
        )
        
        if leverage_result.get('status') != 'ok':
            print(f"⚠️ Attenzione: impostazione leva potrebbe aver avuto problemi: {leverage_result}")
        
        # Piccola pausa per assicurarsi che la leva sia applicata
        import time
        time.sleep(0.5)
        
        # Verifica la leva attuale dopo l'aggiornamento
        current_leverage_info = self.get_current_leverage(symbol)
        print(f"📊 Leva attuale per {symbol}: {current_leverage_info}")

        # Ora procedi con l'apertura della posizione
        user = self.info.user_state(self.account_address)
        balance_usd = Decimal(str(user["marginSummary"]["accountValue"]))

        if balance_usd <= 0:
            raise RuntimeError("Balance account = 0")

        # === RISK MANAGEMENT: MAX_POSITION_SIZE_PCT ===
        # Limita l'investimento massimo per singola operazione
        max_position_pct = Decimal(os.getenv('MAX_POSITION_SIZE_PCT', '50'))
        max_investment = balance_usd * (max_position_pct / Decimal('100'))

        # Calcola il notional richiesto
        requested_notional = balance_usd * portion * Decimal(str(leverage))

        # Applica il limite se necessario
        if requested_notional > max_investment:
            print(f"⚠️ RISK LIMIT: Notional richiesto ${requested_notional:.2f} supera il limite ${max_investment:.2f} ({max_position_pct}% del portafoglio)")
            print(f"   📊 Ridotto notional da ${requested_notional:.2f} a ${max_investment:.2f}")
            notional = max_investment
        else:
            notional = requested_notional
            print(f"✅ Notional ${notional:.2f} entro il limite ${max_investment:.2f} ({max_position_pct}%)")

        mids = self.info.all_mids()
        if symbol not in mids:
            raise RuntimeError(f"Symbol {symbol} non presente su HL")

        mark_px = Decimal(str(mids[symbol]))
        raw_size = notional / mark_px

        # Ottieni info sul simbolo dalla meta
        symbol_info = None
        for perp in self.meta["universe"]:
            if perp["name"] == symbol:
                symbol_info = perp
                break
        
        if not symbol_info:
            raise RuntimeError(f"Symbol {symbol} non trovato nella meta universe")

        # IMPORTANTE: Ottieni il minimum order size (non szDecimals!)
        min_size = Decimal(str(symbol_info.get("minSz", "0.001")))
        sz_decimals = int(symbol_info.get("szDecimals", 8))
        max_leverage = symbol_info.get("maxLeverage", 100)

        # Verifica che la leva richiesta non superi il massimo
        if leverage > max_leverage:
            print(f"⚠️ Leva richiesta ({leverage}) supera il massimo per {symbol} ({max_leverage})")

        # Arrotonda secondo i decimali permessi
        quantizer = Decimal(10) ** -sz_decimals
        size_decimal = raw_size.quantize(quantizer, rounding=ROUND_DOWN)

        # Verifica che sia sopra il minimo
        if size_decimal < min_size:
            print(f"⚠️ Size calcolata ({size_decimal}) < minima richiesta ({min_size})")
            print(f"   Raw size: {raw_size}, Balance: {balance_usd}, Portion: {portion}, Leverage: {leverage}")
            print(f"   Notional: {notional}, Mark price: {mark_px}")
            
            # Usa direttamente il minimum size
            size_decimal = min_size

        # Converti a float per l'API
        size_float = float(size_decimal)

        is_buy = (direction == "long")

        # Check if MICRO_GAIN mode
        trading_mode = order_json.get("trading_mode", "NORMAL")
        micro_gain_target = order_json.get("micro_gain_target", 0.15)

        print(
            f"\n[HyperLiquidTrader] Market {'BUY' if is_buy else 'SELL'} "
            f"{size_float} {symbol}\n"
            f"  💰 Prezzo: ${mark_px}\n"
            f"  📊 Notional: ${notional:.2f}\n"
            f"  🎯 Leva target: {leverage}x\n"
            f"  📋 Trading mode: {trading_mode}\n"
        )

        res = self.exchange.market_open(
            symbol,
            is_buy,
            size_float,
            None,
            0.01
        )

        # Se MICRO_GAIN, piazza automaticamente TP order
        if trading_mode == "MICRO_GAIN" and res.get("status") == "ok":
            try:
                # Attendi un attimo per assicurarsi che la posizione sia registrata
                import time
                time.sleep(1)

                # Ottieni il prezzo di entrata effettivo
                user_state = self.info.user_state(self.account_address)
                entry_price = None
                position_size = None

                for p in user_state.get("assetPositions", []):
                    if isinstance(p, dict) and "position" in p:
                        pos = p["position"]
                        if pos.get("coin") == symbol:
                            entry_price = float(pos.get("entryPx", 0))
                            position_size = abs(float(pos.get("szi", 0)))
                            break

                if entry_price and position_size:
                    # Calcola prezzo target basato su P&L con leva
                    # micro_gain_target è già in % P&L (con leva inclusa)
                    # price_change = pnl_target / leverage
                    price_change_pct = micro_gain_target / leverage

                    if is_buy:  # LONG
                        target_price = entry_price * (1 + price_change_pct / 100)
                    else:  # SHORT
                        target_price = entry_price * (1 - price_change_pct / 100)

                    # Arrotonda il prezzo target al tick size corretto per l'asset
                    target_price = self._round_to_tick(target_price, symbol)

                    print(f"  🎯 MICRO_GAIN: Piazzo TP order @ ${target_price:.2f} (target P&L: +{micro_gain_target}%, tick={self._get_tick_size(symbol)})")

                    # Piazza Take Profit limit order (non trigger)
                    # Usa un limit order semplice che si attiva quando il prezzo raggiunge il target
                    tp_order = self.exchange.order(
                        symbol,
                        not is_buy,  # Direzione opposta per chiudere
                        position_size,
                        target_price,  # Prezzo limite
                        {"limit": {"tif": "Gtc"}},  # Good till cancelled
                        reduce_only=True
                    )

                    print(f"  📋 TP order response: {tp_order}")

                    if tp_order.get("status") == "ok":
                        response_data = tp_order.get("response", {})
                        if response_data.get("type") == "order":
                            order_data = response_data.get("data", {})
                            statuses = order_data.get("statuses", [])
                            if statuses and statuses[0].get("resting"):
                                print(f"  ✅ TP limit order piazzato: OID={statuses[0]['resting']['oid']}")
                                res["tp_order"] = tp_order
                                res["tp_price"] = target_price
                            else:
                                print(f"  ⚠️ TP order status inatteso: {statuses}")
                                res["tp_order_error"] = statuses
                        else:
                            print(f"  ⚠️ TP order response type inatteso: {response_data}")
                            res["tp_order_error"] = response_data
                    else:
                        print(f"  ⚠️ Errore TP order: {tp_order}")
                        res["tp_order_error"] = tp_order
                else:
                    print(f"  ⚠️ Non riesco a trovare entry price per TP order")

            except Exception as e:
                print(f"  ⚠️ Errore piazzamento TP order: {e}")
                res["tp_order_error"] = str(e)

        return res

    # ----------------------------------------------------------------------
    #                           STATO ACCOUNT
    # ----------------------------------------------------------------------
    def get_account_status(self) -> Dict[str, Any]:
        data = self.info.user_state(self.account_address)
        balance = float(data["marginSummary"]["accountValue"])

        mids = self.info.all_mids()
        positions = []

        # Gestisci il formato corretto dei dati
        asset_positions = data.get("assetPositions", [])
        
        for p in asset_positions:
            # Estrai la posizione dal formato corretto
            if isinstance(p, dict) and "position" in p:
                pos = p["position"]
                coin = pos.get("coin", "")
            else:
                # Se il formato è diverso, prova ad adattarti
                pos = p
                coin = p.get("coin", p.get("symbol", ""))
                
            if not pos or not coin:
                continue
                
            size = float(pos.get("szi", 0))
            if size == 0:
                continue

            entry = float(pos.get("entryPx", 0))
            mark = float(mids.get(coin, entry))

            # Calcola P&L
            pnl = (mark - entry) * size
            
            # Estrai info sulla leva
            leverage_info = pos.get("leverage", {})
            leverage_value = leverage_info.get("value", "N/A")
            leverage_type = leverage_info.get("type", "unknown")

            positions.append({
                "symbol": coin,
                "side": "long" if size > 0 else "short",
                "size": abs(size),
                "entry_price": entry,
                "mark_price": mark,
                "pnl_usd": round(pnl, 4),
                "leverage": f"{leverage_value}x ({leverage_type})"
            })

        return {
            "balance_usd": balance,
            "open_positions": positions,
        }
    
    # ----------------------------------------------------------------------
    #                           UTILITY DEBUG
    # ----------------------------------------------------------------------
    def debug_symbol_limits(self, symbol: str = None):
        """Mostra i limiti di trading per un simbolo o tutti"""
        print("\n📊 LIMITI TRADING HYPERLIQUID")
        print("-" * 60)
        
        for perp in self.meta["universe"]:
            if symbol and perp["name"] != symbol:
                continue
                
            print(f"\nSymbol: {perp['name']}")
            print(f"  Min Size: {perp.get('minSz', 'N/A')}")
            print(f"  Size Decimals: {perp.get('szDecimals', 'N/A')}")
            print(f"  Price Decimals: {perp.get('pxDecimals', 'N/A')}")
            print(f"  Max Leverage: {perp.get('maxLeverage', 'N/A')}")
            print(f"  Only Isolated: {perp.get('onlyIsolated', False)}")