"""Alpaca broker client for stocks and options trading."""

from datetime import datetime, timedelta
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest,
    LimitOrderRequest,
    GetOrdersRequest,
)
from alpaca.trading.enums import OrderSide, TimeInForce, OrderStatus, QueryOrderStatus
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import (
    StockLatestQuoteRequest,
    StockBarsRequest,
    StockSnapshotRequest,
)
from alpaca.data.timeframe import TimeFrame
import config


def _get_base_url():
    if config.TRADING_MODE == "live":
        return "https://api.alpaca.markets"
    return "https://paper-api.alpaca.markets"


class Broker:
    def __init__(self):
        self.trading_client = TradingClient(
            config.ALPACA_API_KEY,
            config.ALPACA_SECRET_KEY,
            paper=(config.TRADING_MODE == "paper"),
        )
        self.data_client = StockHistoricalDataClient(
            config.ALPACA_API_KEY,
            config.ALPACA_SECRET_KEY,
        )

    # ── Account ──────────────────────────────────────────────

    def get_account(self):
        """Get account info including buying power and equity."""
        account = self.trading_client.get_account()
        return {
            "equity": float(account.equity),
            "cash": float(account.cash),
            "buying_power": float(account.buying_power),
            "portfolio_value": float(account.portfolio_value),
            "day_trade_count": account.daytrade_count,
            "pattern_day_trader": account.pattern_day_trader,
        }

    # ── Positions ────────────────────────────────────────────

    def get_positions(self):
        """Get all open positions."""
        positions = self.trading_client.get_all_positions()
        result = []
        for p in positions:
            result.append({
                "symbol": p.symbol,
                "qty": float(p.qty),
                "side": str(p.side),
                "market_value": float(p.market_value),
                "cost_basis": float(p.cost_basis),
                "unrealized_pl": float(p.unrealized_pl),
                "unrealized_pl_pct": float(p.unrealized_plpc),
                "unrealized_intraday_pl": float(p.unrealized_intraday_pl) if p.unrealized_intraday_pl is not None else 0.0,
                "unrealized_intraday_pl_pct": float(p.unrealized_intraday_plpc) if p.unrealized_intraday_plpc is not None else 0.0,
                "current_price": float(p.current_price),
                "lastday_price": float(p.lastday_price) if p.lastday_price is not None else 0.0,
                "change_today": float(p.change_today) if p.change_today is not None else 0.0,
                "avg_entry_price": float(p.avg_entry_price),
            })
        return result

    def get_position(self, symbol: str):
        """Get a specific position."""
        try:
            p = self.trading_client.get_open_position(symbol)
            return {
                "symbol": p.symbol,
                "qty": float(p.qty),
                "side": str(p.side),
                "market_value": float(p.market_value),
                "cost_basis": float(p.cost_basis),
                "unrealized_pl": float(p.unrealized_pl),
                "unrealized_pl_pct": float(p.unrealized_plpc),
                "current_price": float(p.current_price),
                "avg_entry_price": float(p.avg_entry_price),
            }
        except Exception:
            return None

    # ── Market Data ──────────────────────────────────────────

    def get_quote(self, symbol: str):
        """Get latest quote for a symbol."""
        request = StockLatestQuoteRequest(symbol_or_symbols=symbol)
        quotes = self.data_client.get_stock_latest_quote(request)
        q = quotes[symbol]
        return {
            "symbol": symbol,
            "bid": float(q.bid_price),
            "ask": float(q.ask_price),
            "bid_size": q.bid_size,
            "ask_size": q.ask_size,
        }

    def get_bars(self, symbol: str, days: int = 30):
        """Get historical daily bars."""
        request = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame.Day,
            start=datetime.now() - timedelta(days=days),
        )
        bars = self.data_client.get_stock_bars(request)
        result = []
        for bar in bars[symbol]:
            result.append({
                "date": str(bar.timestamp.date()),
                "open": float(bar.open),
                "high": float(bar.high),
                "low": float(bar.low),
                "close": float(bar.close),
                "volume": int(bar.volume),
            })
        return result

    def get_snapshot(self, symbol: str):
        """Get a market snapshot for a symbol (quote + latest bar + minute bar)."""
        request = StockSnapshotRequest(symbol_or_symbols=symbol)
        snapshots = self.data_client.get_stock_snapshot(request)
        snap = snapshots[symbol]
        return {
            "symbol": symbol,
            "latest_trade_price": float(snap.latest_trade.price),
            "daily_bar": {
                "open": float(snap.daily_bar.open),
                "high": float(snap.daily_bar.high),
                "low": float(snap.daily_bar.low),
                "close": float(snap.daily_bar.close),
                "volume": int(snap.daily_bar.volume),
            },
            "prev_daily_bar": {
                "close": float(snap.previous_daily_bar.close),
                "volume": int(snap.previous_daily_bar.volume),
            },
        }

    # ── Orders ───────────────────────────────────────────────

    def buy_stock(self, symbol: str, qty: float = None, notional: float = None):
        """Buy stock by quantity or dollar amount (fractional shares)."""
        if notional:
            order = MarketOrderRequest(
                symbol=symbol,
                notional=round(notional, 2),
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY,
            )
        else:
            order = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY,
            )
        return self._submit_order(order)

    def sell_stock(self, symbol: str, qty: float = None, notional: float = None):
        """Sell stock by quantity or dollar amount."""
        if notional:
            order = MarketOrderRequest(
                symbol=symbol,
                notional=round(notional, 2),
                side=OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
            )
        else:
            order = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
            )
        return self._submit_order(order)

    def buy_option(self, symbol: str, qty: int, limit_price: float = None):
        """
        Buy an option contract using a LIMIT order.
        Symbol format: e.g., 'AAPL250620C00200000' (AAPL June 20 2025 $200 Call)
        Alpaca OCC format: SYMBOL + YYMMDD + C/P + strike*1000 (8 digits)
        """
        if limit_price:
            order = LimitOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY,
                limit_price=round(limit_price, 2),
            )
        else:
            order = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY,
            )
        return self._submit_order(order)

    def sell_option(self, symbol: str, qty: int, limit_price: float = None):
        """Sell an option contract you own (sell to close)."""
        if limit_price:
            order = LimitOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
                limit_price=round(limit_price, 2),
            )
        else:
            order = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
            )
        return self._submit_order(order)

    def _submit_order(self, order_request):
        """Submit an order and return standardized result."""
        try:
            order = self.trading_client.submit_order(order_request)
            return {
                "id": str(order.id),
                "symbol": order.symbol,
                "side": str(order.side),
                "qty": str(order.qty),
                "status": str(order.status),
                "type": str(order.order_type),
                "submitted_at": str(order.submitted_at),
            }
        except Exception as e:
            return {"error": str(e)}

    def get_orders(self, status: str = "open"):
        """Get orders by status."""
        query_status = QueryOrderStatus.OPEN if status == "open" else QueryOrderStatus.CLOSED
        request = GetOrdersRequest(status=query_status, limit=50)
        orders = self.trading_client.get_orders(request)
        return [
            {
                "id": str(o.id),
                "symbol": o.symbol,
                "side": str(o.side),
                "qty": str(o.qty),
                "status": str(o.status),
                "type": str(o.order_type),
                "submitted_at": str(o.submitted_at),
                "filled_avg_price": str(o.filled_avg_price) if o.filled_avg_price else None,
            }
            for o in orders
        ]

    def cancel_order(self, order_id: str):
        """Cancel an open order."""
        try:
            self.trading_client.cancel_order_by_id(order_id)
            return {"status": "cancelled", "order_id": order_id}
        except Exception as e:
            return {"error": str(e)}

    # ── Options Chain ────────────────────────────────────────

    def get_options_chain(self, symbol: str, expiration_date: str = None):
        """
        Get options chain for a symbol.
        Uses Alpaca's options API endpoint directly.
        """
        import requests

        base_url = _get_base_url()
        headers = {
            "APCA-API-KEY-ID": config.ALPACA_API_KEY,
            "APCA-API-SECRET-KEY": config.ALPACA_SECRET_KEY,
        }
        params = {"underlying_symbols": symbol, "status": "active", "limit": 100}
        if expiration_date:
            params["expiration_date"] = expiration_date

        resp = requests.get(
            f"https://paper-api.alpaca.markets/v2/options/contracts",
            headers=headers,
            params=params,
        )
        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}: {resp.text}"}

        data = resp.json()
        contracts = []
        for c in data.get("option_contracts", []):
            contracts.append({
                "symbol": c["symbol"],
                "underlying": c["underlying_symbol"],
                "type": c["type"],  # "call" or "put"
                "strike": float(c["strike_price"]),
                "expiration": c["expiration_date"],
                "style": c["style"],
            })
        return contracts
