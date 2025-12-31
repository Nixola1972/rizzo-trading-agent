import json
from decimal import Decimal, ROUND_DOWN
from typing import Dict, Any, List, Optional

import eth_account
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

    def _to_hl_size(self, size_decimal: Decimal) -> str:
        # HL accetta max 8 decimali
        size_clamped = size_decimal.quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)
        return format(size_clamped, "f")   # HL vuole stringa decimale perfetta

    # ----------------------------------------------------------------------
    #                            VALIDAZIONE INPUT
    # ----------------------------------------------------------------------
    def _validate_order_input(self, order_json: Dict[str, Any]):
        # Base required fields
        if "operation" not in order_json:
            raise ValueError("Missing required field: operation")

        if "symbol" not in order_json:
            raise ValueError("Missing required field: symbol")

        op = order_json["operation"]
        if op not in ("open", "close", "hold"):
            raise ValueError("operation must be 'open', 'close', or 'hold'")

        # Additional fields required only for OPEN
        if op == "open":
            required_for_open = ["direction", "target_portion_of_balance", "leverage"]
            for f in required_for_open:
                if f not in order_json:
                    raise ValueError(f"Missing required field for open: {f}")

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

        if op == "hold":
            print(f"[HyperLiquidTrader] HOLD — nessuna azione per {symbol}.")
            return {"status": "hold", "message": "No action taken."}

        if op == "close":
            print(f"[HyperLiquidTrader] Market CLOSE per {symbol}")
            return self.exchange.market_close(symbol)

        # OPEN --------------------------------------------------------
        # These fields are only required for OPEN operations
        direction = order_json["direction"]
        portion = Decimal(str(order_json["target_portion_of_balance"]))
        leverage = int(order_json.get("leverage", 1))

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

        notional = balance_usd * portion * Decimal(str(leverage))

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

        print(
            f"\n[HyperLiquidTrader] Market {'BUY' if is_buy else 'SELL'} "
            f"{size_float} {symbol}\n"
            f"  💰 Prezzo: ${mark_px}\n"
            f"  📊 Notional: ${notional:.2f}\n"
            f"  🎯 Leva target: {leverage}x\n"
        )

        res = self.exchange.market_open(
            symbol,
            is_buy,
            size_float,
            None,
            0.01
        )

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

    # ----------------------------------------------------------------------
    #                        STOP LOSS ORDER
    # ----------------------------------------------------------------------
    def place_stop_loss(self, symbol: str, direction: str, size: float, trigger_price: float) -> Dict[str, Any]:
        """
        Place a stop loss order on HyperLiquid.

        Args:
            symbol: Trading pair (e.g., "ETH", "BTC")
            direction: Current position direction ("long" or "short")
            size: Position size to close
            trigger_price: Price at which SL triggers

        Returns:
            Order result from exchange
        """
        try:
            # For SL on LONG position: we need to SELL (is_buy=False)
            # For SL on SHORT position: we need to BUY (is_buy=True)
            is_buy = (direction.lower() == "short")

            # Get current price for debugging
            mids = self.info.all_mids()
            current_price = float(mids.get(symbol, trigger_price))

            # Get symbol info for proper rounding
            symbol_info = None
            for perp in self.meta["universe"]:
                if perp["name"] == symbol:
                    symbol_info = perp
                    break

            # Get price decimals - this is CRITICAL for ETH (uses 1 decimal, not 2)
            px_decimals = int(symbol_info.get("pxDecimals", 2)) if symbol_info else 2
            sz_decimals = int(symbol_info.get("szDecimals", 4)) if symbol_info else 4
            print(f"   pxDecimals for {symbol}: {px_decimals}, szDecimals: {sz_decimals}")

            # Round trigger and limit price to correct decimals
            trigger_price = round(trigger_price, px_decimals)

            # For SL: limit price should be worse than trigger to ensure fill
            # LONG position (selling): limit BELOW trigger
            # SHORT position (buying): limit ABOVE trigger
            if is_buy:  # SHORT closing = buying
                limit_price = round(trigger_price * 1.02, px_decimals)  # 2% above
            else:  # LONG closing = selling
                limit_price = round(trigger_price * 0.98, px_decimals)  # 2% below

            # Round size to correct decimals - CRITICAL for ETH!
            size = round(size, sz_decimals)

            # Stop Loss order type - tpsl is REQUIRED by SDK
            stop_order_type = {
                "trigger": {
                    "triggerPx": trigger_price,  # Must be float
                    "isMarket": True,
                    "tpsl": "sl"  # Required by HyperLiquid SDK
                }
            }

            print(f"🛡️ Placing SL order on HyperLiquid:")
            print(f"   Symbol: {symbol}")
            print(f"   Current price: ${current_price}")
            print(f"   Direction to close: {'BUY' if is_buy else 'SELL'}")
            print(f"   Size: {size}")
            print(f"   Trigger price: ${trigger_price}")
            print(f"   Limit price: ${limit_price}")
            print(f"   Distance: {abs(current_price - trigger_price) / current_price * 100:.2f}%")

            result = self.exchange.order(
                symbol,
                is_buy,
                size,
                limit_price,
                stop_order_type,
                reduce_only=True  # Only closes existing position
            )

            if result.get('status') == 'ok':
                # Debug: print full response structure
                print(f"   Full response: {result}")

                # Extract order ID - try multiple paths
                sl_order_id = None

                response = result.get('response', {})
                if isinstance(response, dict):
                    data = response.get('data', {})
                    statuses = data.get('statuses', [])

                    if statuses:
                        order_info = statuses[0]
                        print(f"   Status[0]: {order_info}")

                        # CHECK FOR ERROR IN RESPONSE!
                        if isinstance(order_info, dict) and 'error' in order_info:
                            error_msg = order_info.get('error', 'Unknown error')
                            print(f"❌ Stop Loss order REJECTED: {error_msg}")
                            return {"status": "error", "error": error_msg}

                        if isinstance(order_info, dict):
                            # Try 'resting' path (limit orders)
                            if 'resting' in order_info:
                                sl_order_id = order_info['resting'].get('oid')
                            # Try 'filled' path (market orders)
                            elif 'filled' in order_info:
                                sl_order_id = order_info['filled'].get('oid')
                            # Try direct 'oid'
                            elif 'oid' in order_info:
                                sl_order_id = order_info.get('oid')
                            # Try 'orderId'
                            elif 'orderId' in order_info:
                                sl_order_id = order_info.get('orderId')

                if sl_order_id:
                    print(f"✅ Stop Loss order placed successfully")
                    print(f"   Order ID: {sl_order_id}")
                    result['sl_order_id'] = sl_order_id
                else:
                    print(f"   ⚠️ Could not extract order ID from response")
            else:
                print(f"⚠️ SL order response: {result}")

            return result

        except Exception as e:
            print(f"❌ Error placing stop loss: {e}")
            import traceback
            traceback.print_exc()
            return {"status": "error", "error": str(e)}

    def cancel_order(self, symbol: str, order_id: int) -> Dict[str, Any]:
        """Cancel an order by ID."""
        try:
            result = self.exchange.cancel(symbol, order_id)
            return result
        except Exception as e:
            print(f"❌ Error cancelling order: {e}")
            return {"status": "error", "error": str(e)}

    # ----------------------------------------------------------------------
    #                        TAKE PROFIT ORDER
    # ----------------------------------------------------------------------
    def place_take_profit(self, symbol: str, direction: str, size: float, trigger_price: float) -> Dict[str, Any]:
        """
        Place a take profit order on HyperLiquid.

        Args:
            symbol: Trading pair (e.g., "ETH", "SUI")
            direction: Current position direction ("long" or "short")
            size: Position size to close
            trigger_price: Price at which TP triggers

        Returns:
            Order result from exchange
        """
        try:
            # For TP on LONG position: we SELL when price goes UP (is_buy=False)
            # For TP on SHORT position: we BUY when price goes DOWN (is_buy=True)
            is_buy = (direction.lower() == "short")

            # Get current price for debugging
            mids = self.info.all_mids()
            current_price = float(mids.get(symbol, trigger_price))

            # Get symbol info for proper rounding
            symbol_info = None
            for perp in self.meta["universe"]:
                if perp["name"] == symbol:
                    symbol_info = perp
                    break

            px_decimals = int(symbol_info.get("pxDecimals", 2)) if symbol_info else 2
            sz_decimals = int(symbol_info.get("szDecimals", 4)) if symbol_info else 4
            trigger_price = round(trigger_price, px_decimals)

            # For TP: limit price should be worse than trigger to ensure fill
            # LONG position (selling at profit): limit BELOW trigger
            # SHORT position (buying at profit): limit ABOVE trigger
            if is_buy:  # SHORT closing = buying
                limit_price = round(trigger_price * 1.02, px_decimals)  # 2% above
            else:  # LONG closing = selling
                limit_price = round(trigger_price * 0.98, px_decimals)  # 2% below

            # Round size to correct decimals - CRITICAL for ETH!
            size = round(size, sz_decimals)

            # Take Profit order type - tpsl is REQUIRED by SDK
            tp_order_type = {
                "trigger": {
                    "triggerPx": trigger_price,  # Must be float
                    "isMarket": True,
                    "tpsl": "tp"  # This is a Take Profit
                }
            }

            print(f"🎯 Placing TP order on HyperLiquid:")
            print(f"   Symbol: {symbol}")
            print(f"   Current price: ${current_price}")
            print(f"   Direction to close: {'BUY' if is_buy else 'SELL'}")
            print(f"   Size: {size}")
            print(f"   Trigger price: ${trigger_price}")
            print(f"   Distance: {abs(current_price - trigger_price) / current_price * 100:.2f}%")

            result = self.exchange.order(
                symbol,
                is_buy,
                size,
                limit_price,
                tp_order_type,
                reduce_only=True  # Only closes existing position
            )

            if result.get('status') == 'ok':
                print(f"   Full response: {result}")

                tp_order_id = None
                response = result.get('response', {})
                if isinstance(response, dict):
                    data = response.get('data', {})
                    statuses = data.get('statuses', [])

                    if statuses:
                        order_info = statuses[0]
                        print(f"   Status[0]: {order_info}")

                        # CHECK FOR ERROR IN RESPONSE!
                        if isinstance(order_info, dict) and 'error' in order_info:
                            error_msg = order_info.get('error', 'Unknown error')
                            print(f"❌ Take Profit order REJECTED: {error_msg}")
                            return {"status": "error", "error": error_msg}

                        if isinstance(order_info, dict):
                            if 'resting' in order_info:
                                tp_order_id = order_info['resting'].get('oid')
                            elif 'filled' in order_info:
                                tp_order_id = order_info['filled'].get('oid')
                            elif 'oid' in order_info:
                                tp_order_id = order_info.get('oid')

                if tp_order_id:
                    print(f"✅ Take Profit order placed successfully")
                    print(f"   Order ID: {tp_order_id}")
                    result['tp_order_id'] = tp_order_id
                else:
                    print(f"   ⚠️ Could not extract order ID from response")
            else:
                print(f"⚠️ TP order response: {result}")

            return result

        except Exception as e:
            print(f"❌ Error placing take profit: {e}")
            import traceback
            traceback.print_exc()
            return {"status": "error", "error": str(e)}

    def get_open_orders(self, symbol: str = None) -> List[Dict[str, Any]]:
        """
        Get all open orders, optionally filtered by symbol.

        Returns:
            List of open orders with order details
        """
        try:
            open_orders = self.info.open_orders(self.account_address)

            if symbol:
                # Filter by symbol
                open_orders = [o for o in open_orders if o.get('coin') == symbol]

            return open_orders
        except Exception as e:
            print(f"❌ Error getting open orders: {e}")
            return []

    def verify_sl_order_exists(self, symbol: str, expected_trigger_price: float, tolerance_pct: float = 1.0) -> Optional[int]:
        """
        Verify that a stop loss order exists for a symbol.

        Args:
            symbol: Trading pair
            expected_trigger_price: Expected SL trigger price
            tolerance_pct: Price tolerance percentage (default 1.0%)

        Returns:
            Order ID if found, None otherwise
        """
        try:
            open_orders = self.get_open_orders(symbol)

            print(f"🔍 Checking {len(open_orders)} open orders for {symbol}...")

            for order in open_orders:
                # Debug: print order structure
                print(f"   Order: {order}")

                # Check trigger price - HyperLiquid may use different field names
                trigger_px = 0
                if 'triggerPx' in order:
                    trigger_px = float(order.get('triggerPx', 0))
                elif 'trigger_px' in order:
                    trigger_px = float(order.get('trigger_px', 0))

                # If no trigger price, check if it's marked as reduce_only (SL orders are reduce_only)
                is_reduce_only = order.get('reduceOnly', False) or order.get('reduce_only', False)

                # Get order ID
                order_id = order.get('oid') or order.get('orderId') or order.get('id')

                if trigger_px > 0:
                    price_diff_pct = abs(trigger_px - expected_trigger_price) / expected_trigger_price * 100
                    print(f"   Found trigger order: ID={order_id}, trigger=${trigger_px}, diff={price_diff_pct:.2f}%")

                    if price_diff_pct <= tolerance_pct:
                        print(f"✅ Found SL order: ID={order_id}, trigger=${trigger_px}")
                        return order_id
                elif is_reduce_only:
                    # It's a reduce-only order, might be our SL
                    print(f"   Found reduce_only order: ID={order_id}")
                    # Check limit price instead
                    limit_px = float(order.get('limitPx', 0) or order.get('px', 0))
                    if limit_px > 0:
                        price_diff_pct = abs(limit_px - expected_trigger_price) / expected_trigger_price * 100
                        if price_diff_pct <= tolerance_pct * 2:  # Allow more tolerance for limit price
                            print(f"✅ Found SL order (by limit): ID={order_id}, limit=${limit_px}")
                            return order_id

            print(f"⚠️ No matching SL order found for {symbol} at ~${expected_trigger_price:.2f}")
            return None
        except Exception as e:
            print(f"❌ Error verifying SL order: {e}")
            import traceback
            traceback.print_exc()
            return None