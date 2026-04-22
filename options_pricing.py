"""Options pricing intelligence via Yahoo Finance."""

import math
from datetime import datetime, timedelta
import yfinance as yf


class OptionsPricer:
    """Fetches and evaluates options pricing data from Yahoo Finance."""

    def get_options_chain_priced(self, symbol: str, expiry_date: str = None) -> dict:
        """
        Get a fully priced options chain with bid/ask, IV, Greeks, volume.
        Returns calls and puts with all pricing data.
        """
        try:
            ticker = yf.Ticker(symbol)
            stock_price = ticker.info.get("currentPrice") or ticker.info.get("regularMarketPrice", 0)

            # Get available expiration dates
            expirations = ticker.options
            if not expirations:
                return {"error": f"No options available for {symbol}"}

            # Pick the target expiry
            if expiry_date and expiry_date in expirations:
                target_expiry = expiry_date
            elif expiry_date:
                # Find closest expiry to requested date
                target_dt = datetime.strptime(expiry_date, "%Y-%m-%d")
                target_expiry = min(expirations, key=lambda x: abs(datetime.strptime(x, "%Y-%m-%d") - target_dt))
            else:
                # Default: find expiry 30-60 days out (sweet spot)
                now = datetime.now()
                target_30d = now + timedelta(days=30)
                target_expiry = min(expirations, key=lambda x: abs(datetime.strptime(x, "%Y-%m-%d") - target_30d))

            chain = ticker.option_chain(target_expiry)
            dte = (datetime.strptime(target_expiry, "%Y-%m-%d") - datetime.now()).days

            calls = self._format_chain(chain.calls, stock_price, dte, "call")
            puts = self._format_chain(chain.puts, stock_price, dte, "put")

            return {
                "symbol": symbol,
                "stock_price": round(stock_price, 2),
                "expiration": target_expiry,
                "dte": dte,
                "available_expirations": list(expirations[:8]),
                "calls": calls,
                "puts": puts,
            }
        except Exception as e:
            return {"error": str(e)}

    def evaluate_option(self, symbol: str, strike: float, option_type: str = "call",
                        expiry_date: str = None) -> dict:
        """
        Evaluate a specific option contract for favorability.
        Returns pricing data + a favorability assessment.
        """
        try:
            ticker = yf.Ticker(symbol)
            stock_price = ticker.info.get("currentPrice") or ticker.info.get("regularMarketPrice", 0)

            # Get historical volatility for IV rank comparison
            hist = ticker.history(period="1y")
            if len(hist) > 20:
                returns = hist["Close"].pct_change().dropna()
                hist_vol = float(returns.std() * math.sqrt(252))
            else:
                hist_vol = None

            # Get the options chain
            expirations = ticker.options
            if not expirations:
                return {"error": f"No options for {symbol}"}

            if expiry_date and expiry_date in expirations:
                target_expiry = expiry_date
            else:
                now = datetime.now()
                target_30d = now + timedelta(days=30)
                target_expiry = min(expirations, key=lambda x: abs(datetime.strptime(x, "%Y-%m-%d") - target_30d))

            chain = ticker.option_chain(target_expiry)
            dte = (datetime.strptime(target_expiry, "%Y-%m-%d") - datetime.now()).days

            # Find the specific contract
            if option_type == "call":
                options = chain.calls
            else:
                options = chain.puts

            contract = options[options["strike"] == strike]
            if contract.empty:
                # Find closest strike
                closest_strike = min(options["strike"].tolist(), key=lambda x: abs(x - strike))
                contract = options[options["strike"] == closest_strike]
                strike = closest_strike

            if contract.empty:
                return {"error": f"No contract found near strike {strike}"}

            row = contract.iloc[0]
            bid = float(row.get("bid", 0))
            ask = float(row.get("ask", 0))
            mid = (bid + ask) / 2 if bid > 0 and ask > 0 else float(row.get("lastPrice", 0))
            iv = float(row.get("impliedVolatility", 0))
            volume = int(row.get("volume", 0)) if not math.isnan(row.get("volume", 0)) else 0
            open_interest = int(row.get("openInterest", 0)) if not math.isnan(row.get("openInterest", 0)) else 0

            # Calculate spread quality
            spread = ask - bid if bid > 0 and ask > 0 else 0
            spread_pct = spread / mid if mid > 0 else 999

            # Calculate moneyness
            if option_type == "call":
                otm_pct = (strike - stock_price) / stock_price
            else:
                otm_pct = (stock_price - strike) / stock_price

            # Premium as % of stock price
            premium_pct = mid / stock_price if stock_price > 0 else 0

            # IV rank estimate (compare current IV to historical vol)
            iv_rank = None
            iv_assessment = "unknown"
            if hist_vol and hist_vol > 0:
                iv_rank = iv / hist_vol
                if iv_rank < 0.8:
                    iv_assessment = "CHEAP (IV below historical vol)"
                elif iv_rank < 1.2:
                    iv_assessment = "FAIR (IV near historical vol)"
                else:
                    iv_assessment = "EXPENSIVE (IV above historical vol)"

            # Favorability scoring
            issues = []
            score = 10  # Start at 10, deduct for problems

            if spread_pct > 0.15:
                issues.append(f"Wide spread: {spread_pct:.0%} (want <15%)")
                score -= 3
            elif spread_pct > 0.10:
                issues.append(f"Moderate spread: {spread_pct:.0%}")
                score -= 1

            if dte < 14:
                issues.append(f"Low DTE: {dte} days (theta decay accelerating)")
                score -= 3
            elif dte < 30:
                issues.append(f"Short DTE: {dte} days")
                score -= 1

            if volume < 10:
                issues.append(f"Very low volume: {volume} contracts")
                score -= 2
            elif volume < 50:
                issues.append(f"Low volume: {volume} contracts")
                score -= 1

            if open_interest < 100:
                issues.append(f"Low open interest: {open_interest}")
                score -= 1

            if iv_rank and iv_rank > 1.5:
                issues.append(f"IV very expensive: {iv_rank:.1f}x historical")
                score -= 2
            elif iv_rank and iv_rank > 1.2:
                issues.append(f"IV somewhat elevated: {iv_rank:.1f}x historical")
                score -= 1

            if premium_pct > 0.10:
                issues.append(f"Premium expensive: {premium_pct:.1%} of stock price")
                score -= 1

            score = max(1, min(10, score))

            if score >= 7:
                verdict = "FAVORABLE — good pricing, proceed"
            elif score >= 5:
                verdict = "ACCEPTABLE — some concerns but tradeable"
            else:
                verdict = "UNFAVORABLE — poor pricing, consider alternatives"

            return {
                "symbol": symbol,
                "option_type": option_type,
                "strike": strike,
                "expiration": target_expiry,
                "dte": dte,
                "stock_price": round(stock_price, 2),
                "bid": round(bid, 2),
                "ask": round(ask, 2),
                "mid": round(mid, 2),
                "last_price": round(float(row.get("lastPrice", 0)), 2),
                "spread": round(spread, 2),
                "spread_pct": round(spread_pct, 4),
                "implied_volatility": round(iv, 4),
                "historical_volatility": round(hist_vol, 4) if hist_vol else None,
                "iv_ratio": round(iv_rank, 2) if iv_rank else None,
                "iv_assessment": iv_assessment,
                "volume": volume,
                "open_interest": open_interest,
                "otm_pct": round(otm_pct, 4),
                "premium_pct": round(premium_pct, 4),
                "premium_per_contract": round(mid * 100, 2),
                "favorability_score": score,
                "verdict": verdict,
                "issues": issues,
                "suggested_limit_price": round(mid, 2),
            }
        except Exception as e:
            return {"error": str(e)}

    def get_best_strikes(self, symbol: str, direction: str = "bullish",
                         budget: float = 5000, expiry_date: str = None) -> dict:
        """
        Find the best option strikes for a given budget and direction.
        Returns top 3 recommended contracts ranked by favorability.
        """
        try:
            chain_data = self.get_options_chain_priced(symbol, expiry_date)
            if "error" in chain_data:
                return chain_data

            stock_price = chain_data["stock_price"]
            dte = chain_data["dte"]

            if direction == "bullish":
                candidates = chain_data["calls"]
            else:
                candidates = chain_data["puts"]

            # Filter to reasonable strikes (OTM, within 20% of stock price)
            recommendations = []
            for c in candidates:
                # Skip ITM options for directional plays
                if direction == "bullish" and c["strike"] < stock_price:
                    continue
                if direction == "bearish" and c["strike"] > stock_price:
                    continue

                # Skip if too far OTM (>20%)
                if abs(c["otm_pct"]) > 0.20:
                    continue

                # Skip if too expensive for budget
                premium_per_contract = c["mid"] * 100
                if premium_per_contract <= 0 or premium_per_contract > budget:
                    continue

                max_contracts = int(budget / premium_per_contract)
                total_cost = max_contracts * premium_per_contract

                # Score based on risk/reward
                leverage = stock_price / c["mid"] if c["mid"] > 0 else 0

                recommendations.append({
                    "strike": c["strike"],
                    "bid": c["bid"],
                    "ask": c["ask"],
                    "mid": c["mid"],
                    "spread_pct": c["spread_pct"],
                    "iv": c["iv"],
                    "volume": c["volume"],
                    "open_interest": c["open_interest"],
                    "otm_pct": c["otm_pct"],
                    "contracts": max_contracts,
                    "total_cost": round(total_cost, 2),
                    "leverage": round(leverage, 1),
                    "suggested_limit": c["mid"],
                })

            # Sort by a balanced score: prefer moderate OTM with good liquidity
            recommendations.sort(
                key=lambda x: (
                    min(x["volume"], 100) / 100 * 0.3  # liquidity weight
                    + (1 - min(x["spread_pct"], 0.2) / 0.2) * 0.3  # tight spread weight
                    + min(x["otm_pct"], 0.15) / 0.15 * 0.2  # moderate OTM weight
                    + min(x["leverage"], 50) / 50 * 0.2  # leverage weight
                ),
                reverse=True,
            )

            return {
                "symbol": symbol,
                "direction": direction,
                "stock_price": stock_price,
                "expiration": chain_data["expiration"],
                "dte": dte,
                "budget": budget,
                "recommendations": recommendations[:5],
            }
        except Exception as e:
            return {"error": str(e)}

    def _format_chain(self, df, stock_price: float, dte: int, opt_type: str) -> list[dict]:
        """Format a pandas options chain into clean dicts."""
        results = []
        for _, row in df.iterrows():
            strike = float(row["strike"])
            bid = float(row.get("bid", 0))
            ask = float(row.get("ask", 0))
            mid = (bid + ask) / 2 if bid > 0 and ask > 0 else float(row.get("lastPrice", 0))
            spread_pct = (ask - bid) / mid if mid > 0 else 999
            iv = float(row.get("impliedVolatility", 0))
            vol = int(row.get("volume", 0)) if not math.isnan(row.get("volume", 0)) else 0
            oi = int(row.get("openInterest", 0)) if not math.isnan(row.get("openInterest", 0)) else 0

            if opt_type == "call":
                otm_pct = (strike - stock_price) / stock_price
            else:
                otm_pct = (stock_price - strike) / stock_price

            # Only include near-the-money options (within 25%)
            if abs(otm_pct) > 0.25:
                continue

            results.append({
                "strike": strike,
                "bid": round(bid, 2),
                "ask": round(ask, 2),
                "mid": round(mid, 2),
                "spread_pct": round(spread_pct, 4),
                "iv": round(iv, 4),
                "volume": vol,
                "open_interest": oi,
                "otm_pct": round(otm_pct, 4),
            })

        return results
