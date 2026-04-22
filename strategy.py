"""Strategy rules engine. Enforces the user's trading constraints."""

import config


# Broken thesis thresholds — if 2+ of these trigger, selling is allowed
THESIS_BROKEN_MOMENTUM_THRESHOLD = -0.20      # 20-day momentum < -20%
THESIS_BROKEN_VOLUME_DRY_THRESHOLD = 0.5       # Volume surge < 0.5x (no interest)
THESIS_BROKEN_LOSS_THRESHOLD = -0.15           # Position down >15% from entry
THESIS_BROKEN_MIN_TRIGGERS = 2                 # Need at least 2 signals to confirm


class StrategyRules:
    """Hard rules that the agent must follow. These override any AI decision."""

    def __init__(self, broker):
        self.broker = broker

    def get_portfolio_state(self):
        """Get current portfolio state for decision-making."""
        account = self.broker.get_account()
        positions = self.broker.get_positions()

        stock_value = sum(p["market_value"] for p in positions if not self._is_option(p["symbol"]))
        option_value = sum(p["market_value"] for p in positions if self._is_option(p["symbol"]))
        total_equity = account["equity"]

        return {
            "account": account,
            "positions": positions,
            "stock_value": stock_value,
            "option_value": option_value,
            "total_equity": total_equity,
            "cash": account["cash"],
            "options_pct": option_value / total_equity if total_equity > 0 else 0,
        }

    def can_buy_stock(self, symbol: str, amount: float, portfolio_state: dict) -> tuple[bool, str]:
        """Check if a stock purchase is allowed under our rules."""
        equity = portfolio_state["total_equity"]

        # Check position size limit
        existing = next((p for p in portfolio_state["positions"] if p["symbol"] == symbol), None)
        existing_value = existing["market_value"] if existing else 0
        new_total = existing_value + amount

        if new_total > equity * config.MAX_POSITION_PCT:
            return False, f"Position would be {new_total/equity:.0%} of portfolio, max is {config.MAX_POSITION_PCT:.0%}"

        # Check we have the cash
        if amount > portfolio_state["cash"]:
            return False, f"Insufficient cash: need ${amount:.2f}, have ${portfolio_state['cash']:.2f}"

        # No margin
        if config.ALLOW_MARGIN is False and amount > portfolio_state["cash"]:
            return False, "Margin trading is disabled"

        return True, "OK"

    def can_buy_option(self, premium_cost: float, portfolio_state: dict) -> tuple[bool, str]:
        """Check if an options purchase is allowed under our rules."""
        equity = portfolio_state["total_equity"]
        current_options_pct = portfolio_state["options_pct"]
        new_options_value = portfolio_state["option_value"] + premium_cost

        # Check total options allocation
        if new_options_value / equity > config.MAX_OPTIONS_PCT:
            return False, f"Options allocation would exceed {config.MAX_OPTIONS_PCT:.0%} limit"

        # Check single option position size
        if premium_cost / equity > config.MAX_SINGLE_OPTION_PCT:
            return False, f"Single option position would exceed {config.MAX_SINGLE_OPTION_PCT:.0%} limit"

        # Check cash
        if premium_cost > portfolio_state["cash"]:
            return False, f"Insufficient cash for premium: need ${premium_cost:.2f}"

        return True, "OK"

    def should_sell_stock(self, position: dict) -> tuple[bool, str]:
        """Check if a stock position should be sold based on our rules."""
        gain_pct = position["unrealized_pl_pct"]

        if gain_pct >= config.SELL_THRESHOLD_PCT:
            return True, f"Position up {gain_pct:.0%} (threshold: {config.SELL_THRESHOLD_PCT:.0%})"

        return False, f"Position at {gain_pct:+.0%}, below {config.SELL_THRESHOLD_PCT:.0%} sell threshold"

    def check_broken_thesis(self, position: dict, scan_data: dict | None) -> tuple[bool, str, list[str]]:
        """
        Check if a position's thesis is broken using quantitative signals.
        Returns (is_broken, summary, list_of_triggered_signals).
        A thesis is broken if 2+ of these signals trigger.
        """
        triggers = []

        # Signal 1: Momentum collapse (20-day momentum < -20%)
        if scan_data and scan_data.get("momentum_20d", 0) < THESIS_BROKEN_MOMENTUM_THRESHOLD:
            triggers.append(
                f"Momentum collapse: {scan_data['momentum_20d']:+.1%} "
                f"(threshold: {THESIS_BROKEN_MOMENTUM_THRESHOLD:+.0%})"
            )

        # Signal 2: Volume exodus (volume surge < 0.5x — no one cares)
        if scan_data and scan_data.get("volume_surge", 1) < THESIS_BROKEN_VOLUME_DRY_THRESHOLD:
            triggers.append(
                f"Volume dried up: {scan_data['volume_surge']:.2f}x "
                f"(threshold: <{THESIS_BROKEN_VOLUME_DRY_THRESHOLD}x)"
            )

        # Signal 3: Extended loss (position down >15% from entry)
        if position["unrealized_pl_pct"] < THESIS_BROKEN_LOSS_THRESHOLD:
            triggers.append(
                f"Extended loss: {position['unrealized_pl_pct']:+.1%} "
                f"(threshold: {THESIS_BROKEN_LOSS_THRESHOLD:+.0%})"
            )

        # Signal 4: Agent qualitative assessment (passed in via scan_data)
        if scan_data and scan_data.get("agent_thesis_broken", False):
            triggers.append("Agent qualitative assessment: thesis broken")

        is_broken = len(triggers) >= THESIS_BROKEN_MIN_TRIGGERS

        if is_broken:
            summary = f"THESIS BROKEN ({len(triggers)}/{THESIS_BROKEN_MIN_TRIGGERS} signals): {'; '.join(triggers)}"
        else:
            summary = f"Thesis intact ({len(triggers)}/{THESIS_BROKEN_MIN_TRIGGERS} signals needed)"

        return is_broken, summary, triggers

    def should_cut_option(self, position: dict) -> tuple[bool, str]:
        """Check if an options position should be cut for risk management."""
        loss_pct = position["unrealized_pl_pct"]

        if loss_pct <= -config.STOP_LOSS_OPTIONS_PCT:
            return True, f"Option down {loss_pct:.0%}, hit stop-loss at {config.STOP_LOSS_OPTIONS_PCT:.0%}"

        return False, f"Option at {loss_pct:+.0%}, within stop-loss threshold"

    def get_rules_summary(self) -> str:
        """Return a human-readable summary of all active rules."""
        return f"""
TRADING RULES (these are HARD constraints — never violate):

POSITION LIMITS:
- Max position size: {config.MAX_POSITION_PCT:.0%} of portfolio per stock
- Max options allocation: {config.MAX_OPTIONS_PCT:.0%} of portfolio total
- Max single option: {config.MAX_SINGLE_OPTION_PCT:.0%} of portfolio
- Max sector allocation: {config.MAX_SECTOR_ALLOCATION_PCT:.0%} of portfolio (sector neutral default)

SCREENING CRITERIA (only trade stocks that meet ALL of these):
- Min beta: {config.MIN_BETA} (high beta only)
- Min avg daily volume: {config.MIN_AVG_VOLUME:,} shares
- Min daily volatility: {config.MIN_VOLATILITY_PCT:.0%} average daily range

SELL RULES:
- Only SELL stocks when up {config.SELL_THRESHOLD_PCT:.0%}+ (let winners run)
- Cut options losers at {config.STOP_LOSS_OPTIONS_PCT:.0%} loss
- BROKEN THESIS OVERRIDE: May sell a position at ANY P&L if thesis is broken.
  A thesis is broken when {THESIS_BROKEN_MIN_TRIGGERS}+ of these signals trigger:
  1. Momentum collapse: 20-day return < {THESIS_BROKEN_MOMENTUM_THRESHOLD:+.0%}
  2. Volume exodus: volume surge < {THESIS_BROKEN_VOLUME_DRY_THRESHOLD}x (smart money gone)
  3. Extended loss: position down > {abs(THESIS_BROKEN_LOSS_THRESHOLD):.0%} from entry
  4. Agent qualitative: catalyst expired, sector breakdown, fundamental deterioration
  Use the check_thesis tool to evaluate before selling a broken-thesis position.

OPTIONS PRICING RULES:
- ONLY buy options when pricing is favorable (use evaluate_option tool first)
- Check IV rank: prefer IV rank < 50% (options are relatively cheap)
- Check bid-ask spread: must be < 15% of mid price (liquid options only)
- Check theta: prefer > 30 DTE to avoid rapid time decay
- Use LIMIT orders for all options trades, never market orders
- Set limit price at or below the ask for buys

HARD CONSTRAINTS:
- NO margin trading
- NO naked options (only buy calls/puts, or sell covered calls)
- NO short selling

STRATEGY:
- GOAL: Maximize returns aggressively. Target 100X by EOY.
- FOCUS: High beta, high volume, high volatility stocks
- SECTOR: Neutral by default, but overweight sectors with strong macro tailwinds
- EARNINGS: Actively trade earnings with divided analyst consensus using options
- TAX STRATEGY: Minimize sells. Only sell big winners (50%+) or broken theses. Hold when possible.
- ALLOWED: Buy stocks, buy calls, buy puts, sell covered calls, cash-secured puts, spreads (verticals, multi-leg), covered straddles.
- LEVEL 3 OPTIONS APPROVED: Can use spreads for defined-risk directional bets and income strategies.
"""

    @staticmethod
    def _is_option(symbol: str) -> bool:
        """Check if a symbol is an option (OCC format is longer than stock tickers)."""
        return len(symbol) > 10
