"""Market screener for finding high-beta, high-volume, volatile stocks with earnings catalysts."""

import math
from datetime import datetime, timedelta
from broker import Broker
import config

# Universe of high-beta, liquid stocks organized by sector.
# This is our scanning universe — the agent will filter further based on current conditions.
UNIVERSE = {
    "Technology": [
        "NVDA", "AMD", "TSLA", "SMCI", "MRVL", "ARM", "CRWD", "SNOW",
        "PLTR", "NET", "SHOP", "SQ", "COIN", "MSTR", "IONQ", "RGTI",
        "APP", "RKLB", "AFRM", "U", "DDOG", "MDB", "CFLT", "PATH",
    ],
    "Software": [
        "CRM", "NOW", "WDAY", "ZS", "PANW", "FTNT", "OKTA", "S",
        "BILL", "HUBS", "VEEV", "PAYC", "PCOR", "MNDY", "TOST",
        "ZI", "ESTC", "DOCN", "GTLB", "IOT", "BRZE", "KVYO",
        "SMAR", "APPF", "TENB", "QLYS", "CYBR", "RPD", "FRSH",
        "ADSK", "ANSS", "TEAM", "INTU", "CDNS", "SNPS",
    ],
    "Energy": [
        "XOM", "CVX", "OXY", "DVN", "FANG", "MPC", "VLO", "HAL",
        "SLB", "EOG", "PXD", "AR", "RRC", "CTRA", "OVV", "SM",
    ],
    "Financials": [
        "GS", "MS", "JPM", "C", "BAC", "ARES", "APO", "BX", "KKR",
        "OWL", "SOFI", "HOOD", "AFRM", "UPST", "LC", "NU",
    ],
    "Healthcare": [
        "MRNA", "BNTX", "CRSP", "NTLA", "BEAM", "EDIT", "EXAS",
        "SGEN", "IONS", "SRPT", "VRTX", "REGN", "BIIB", "HIMS",
    ],
    "Consumer Discretionary": [
        "ABNB", "DASH", "UBER", "LYFT", "W", "ETSY", "PTON",
        "RIVN", "LCID", "NIO", "XPEV", "LI", "CVNA", "CART",
    ],
    "Industrials": [
        "BA", "CAT", "DE", "GE", "RTX", "LMT", "NOC",
        "AXON", "TDG", "BLDE", "JOBY", "LUNR", "RDW",
    ],
    "Materials": [
        "NEM", "FCX", "GOLD", "AEM", "WPM", "VALE", "RIO",
        "BHP", "CLF", "X", "AA", "MP", "LAC", "ALB",
    ],
    "Communication Services": [
        "META", "GOOGL", "SNAP", "PINS", "RDDT", "SPOT",
        "ROKU", "TTD", "DIS", "NFLX", "RBLX", "BMBL",
    ],
}


class MarketScreener:
    def __init__(self, broker: Broker):
        self.broker = broker

    def scan_symbol(self, symbol: str) -> dict | None:
        """Get screening metrics for a single symbol."""
        try:
            bars = self.broker.get_bars(symbol, days=60)
            if len(bars) < 20:
                return None

            closes = [b["close"] for b in bars]
            volumes = [b["volume"] for b in bars]
            highs = [b["high"] for b in bars]
            lows = [b["low"] for b in bars]

            # Average volume
            avg_volume = sum(volumes[-20:]) / 20

            # Volatility: average daily range as % of close
            daily_ranges = [(h - l) / c for h, l, c in zip(highs[-20:], lows[-20:], closes[-20:])]
            avg_volatility = sum(daily_ranges) / len(daily_ranges)

            # Simple beta proxy: stock daily return std / SPY-like baseline (assume ~1% daily)
            returns = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes))]
            return_std = self._std(returns)
            beta_proxy = return_std / 0.01  # rough: SPY daily std ≈ 1%

            # Recent momentum
            if len(closes) >= 20:
                momentum_20d = (closes[-1] - closes[-20]) / closes[-20]
            else:
                momentum_20d = 0

            # Volume surge: recent 5-day avg vs 20-day avg
            recent_vol = sum(volumes[-5:]) / 5
            volume_surge = recent_vol / avg_volume if avg_volume > 0 else 1

            current_price = closes[-1]

            return {
                "symbol": symbol,
                "price": round(current_price, 2),
                "avg_volume": int(avg_volume),
                "avg_volatility": round(avg_volatility, 4),
                "beta_proxy": round(beta_proxy, 2),
                "momentum_20d": round(momentum_20d, 4),
                "volume_surge": round(volume_surge, 2),
                "return_std": round(return_std, 4),
            }
        except Exception as e:
            return None

    def scan_sector(self, sector: str) -> list[dict]:
        """Scan all symbols in a sector and return those meeting criteria."""
        symbols = UNIVERSE.get(sector, [])
        results = []
        for symbol in symbols:
            data = self.scan_symbol(symbol)
            if data and self._passes_filters(data):
                results.append(data)
        results.sort(key=lambda x: x["beta_proxy"] * x["avg_volatility"], reverse=True)
        return results

    def scan_all(self) -> dict[str, list[dict]]:
        """Scan entire universe, return results grouped by sector."""
        all_results = {}
        for sector in UNIVERSE:
            sector_results = self.scan_sector(sector)
            if sector_results:
                all_results[sector] = sector_results
        return all_results

    def get_top_movers(self, n: int = 20) -> list[dict]:
        """Get top N stocks across all sectors by volatility * beta."""
        all_stocks = []
        for sector, symbols in UNIVERSE.items():
            for symbol in symbols:
                data = self.scan_symbol(symbol)
                if data and self._passes_filters(data):
                    data["sector"] = sector
                    all_stocks.append(data)
        all_stocks.sort(key=lambda x: x["beta_proxy"] * x["avg_volatility"] * x["volume_surge"], reverse=True)
        return all_stocks[:n]

    def get_earnings_plays(self) -> list[dict]:
        """
        Return symbols from our universe that likely have upcoming earnings.
        Uses volume surge + volatility spike as a proxy for earnings anticipation.
        The agent will verify via its own knowledge and web search.
        """
        candidates = []
        for sector, symbols in UNIVERSE.items():
            for symbol in symbols:
                data = self.scan_symbol(symbol)
                if not data:
                    continue
                # Earnings proxy: volume surge > 1.5x AND volatility expanding
                if data["volume_surge"] > 1.5 and data["avg_volatility"] > config.MIN_VOLATILITY_PCT:
                    data["sector"] = sector
                    data["earnings_signal"] = "Volume surge + elevated volatility"
                    candidates.append(data)
        candidates.sort(key=lambda x: x["volume_surge"], reverse=True)
        return candidates

    def get_sector_allocation(self, positions: list[dict]) -> dict[str, float]:
        """Calculate current sector allocation from positions."""
        sector_values = {s: 0.0 for s in UNIVERSE}
        total = sum(p["market_value"] for p in positions)

        for p in positions:
            symbol = p["symbol"]
            # Strip option symbols to underlying
            if len(symbol) > 10:
                # OCC format: first chars are underlying
                for underlying_len in range(1, 6):
                    candidate = symbol[:underlying_len]
                    for sector, syms in UNIVERSE.items():
                        if candidate in syms:
                            sector_values[sector] += p["market_value"]
                            break
            else:
                for sector, syms in UNIVERSE.items():
                    if symbol in syms:
                        sector_values[sector] += p["market_value"]
                        break

        if total == 0:
            return {s: 0.0 for s in sector_values}
        return {s: round(v / total, 4) for s, v in sector_values.items() if v > 0}

    def _passes_filters(self, data: dict) -> bool:
        """Check if a stock passes our minimum screening criteria."""
        return (
            data["beta_proxy"] >= config.MIN_BETA
            and data["avg_volume"] >= config.MIN_AVG_VOLUME
            and data["avg_volatility"] >= config.MIN_VOLATILITY_PCT
        )

    @staticmethod
    def _std(values: list[float]) -> float:
        if len(values) < 2:
            return 0
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
        return math.sqrt(variance)
