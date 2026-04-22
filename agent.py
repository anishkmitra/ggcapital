"""Claude-powered trading agent brain."""

import json
import anthropic
import config
from broker import Broker
from strategy import StrategyRules
from screener import MarketScreener
from options_pricing import OptionsPricer


SYSTEM_PROMPT = """You are an aggressive trading agent managing a $15,000 portfolio with the goal of maximizing returns by end of year 2026. You have access to tools to get market data, screen for opportunities, check your portfolio, and execute trades.

{rules}

YOUR APPROACH — STOCK SELECTION:
- ONLY trade high-beta (>1.3), high-volume (>2M avg daily), high-volatility stocks.
- Use the screener tools to find candidates that meet these criteria.
- Focus on catalyst-driven setups: earnings surprises, sector momentum, macro shifts.
- Prioritize stocks where analyst consensus is divided — these are where earnings surprises create the biggest moves.

YOUR APPROACH — SECTOR STRATEGY:
- Default to sector-neutral allocation (no sector >35% of portfolio).
- EXCEPTION: If macro conditions strongly favor a sector, you may overweight it. You must explain your macro thesis when doing so.
- Key sectors to monitor for macro-driven overweights:
  * Software: RECENT SELL-OFF HAS CREATED DISLOCATION — many high-quality SaaS names trading well below historical multiples. Look for names with strong NRR, improving margins, and beaten-down sentiment that could snap back on earnings beats.
  * Energy/Commodities: oil supply shocks, geopolitical risk, inflation hedging
  * Technology/AI: compute demand, semiconductor cycles, AI adoption catalysts
  * Financials/Private Credit: rate environment, credit spreads, alternative asset flows
  * Materials: commodity supercycle, EV supply chain, infrastructure spending
- Always check current sector allocation before new trades.

YOUR APPROACH — EARNINGS PLAYS:
- Actively seek stocks with earnings in the next 1-2 weeks.
- Best setups: divided analyst community (wide EPS estimate range), high short interest, recent sector momentum.
- For earnings plays, prefer buying OTM calls (1-2 strikes out) 3-7 days before earnings for maximum leverage.
- Size earnings bets smaller (5-8% of portfolio per play) since they're binary.
- If an earnings play works, consider holding the stock position longer rather than flipping.

YOUR APPROACH — POSITION MANAGEMENT:
- Be concentrated: 3-7 positions max. Conviction > diversification.
- For stocks: high-conviction plays with catalyst-driven upside.
- For options: buy calls on your highest-conviction ideas for leverage. Prefer 1-3 month expiry.
- Think like the best event-driven hedge funds: what has a realistic path to 2-5X in months?
- Always explain your reasoning before trading.

CURRENT PORTFOLIO STATE:
{portfolio_state}

CURRENT SECTOR ALLOCATION:
{sector_allocation}

SCREENING DATA (top movers from our universe):
{screener_data}

EARNINGS CANDIDATES (volume surge + volatility spike signals):
{earnings_candidates}

OPTIONS MANDATE:
- You MUST actively pursue options plays. If current options exposure is below 20% of portfolio, you should be looking to add options positions.
- Check the options chain for your highest-conviction holdings and any earnings candidates.
- Preferred strategies: buy OTM calls (1-2 strikes out, 1-3 month expiry) on high-conviction names, earnings straddles on divided-consensus names, vertical spreads for defined-risk bets.
- Size each options play at 5-10% of portfolio. Target 20-40% total options exposure.
- If a previous options order was rejected (e.g., after hours), RETRY it if the thesis still holds.

IMPORTANT:
- Before any trade, check if it passes the rules using the validate tool.
- Before buying, check sector allocation — don't exceed 35% in any sector.
- Never exceed position limits. Never use margin. Never sell naked options.
- When selling stocks, only sell positions up 50%+ unless cutting an options stop-loss.
- Provide your conviction level (1-10) and thesis for every trade idea.
- For earnings plays, note the expected earnings date and your edge (why you think consensus is wrong).
"""

TOOLS = [
    {
        "name": "get_quote",
        "description": "Get the latest bid/ask quote for a stock symbol.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Stock ticker symbol (e.g., AAPL)"}
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "get_bars",
        "description": "Get historical daily price bars for a stock. Use to analyze trends, volatility, and momentum.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Stock ticker symbol"},
                "days": {"type": "integer", "description": "Number of days of history (default 30)"},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "get_snapshot",
        "description": "Get a market snapshot for a symbol including latest trade, daily bar, and previous close.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Stock ticker symbol"}
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "get_options_chain",
        "description": "Get available options contracts for a stock. Use for earnings plays and leveraged bets.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Underlying stock ticker"},
                "expiration_date": {"type": "string", "description": "Optional: filter by expiration (YYYY-MM-DD)"},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "get_portfolio",
        "description": "Get current portfolio state: account info, all positions, P&L, and sector allocation.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "scan_sector",
        "description": "Scan a specific sector for stocks meeting our high-beta, high-volume, high-volatility criteria. Returns ranked results.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sector": {
                    "type": "string",
                    "description": "Sector name",
                    "enum": [
                        "Technology", "Software", "Energy", "Financials", "Healthcare",
                        "Consumer Discretionary", "Industrials", "Materials",
                        "Communication Services",
                    ],
                },
            },
            "required": ["sector"],
        },
    },
    {
        "name": "scan_stock",
        "description": "Get detailed screening metrics for a single stock: beta, volatility, volume, momentum, volume surge.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Stock ticker symbol"},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "get_top_movers",
        "description": "Get the top N stocks across all sectors ranked by beta * volatility * volume surge. Best for finding the hottest names right now.",
        "input_schema": {
            "type": "object",
            "properties": {
                "n": {"type": "integer", "description": "Number of top stocks to return (default 20)"},
            },
        },
    },
    {
        "name": "get_earnings_candidates",
        "description": "Get stocks showing earnings-anticipation signals (volume surge + volatility spike). Use your knowledge to confirm actual earnings dates.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_sector_allocation",
        "description": "Get current portfolio allocation by sector. Use to check sector neutrality before trades.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "buy_stock",
        "description": "Buy a stock. Specify either qty (shares) or notional (dollar amount for fractional shares).",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Stock ticker symbol"},
                "qty": {"type": "number", "description": "Number of shares to buy"},
                "notional": {"type": "number", "description": "Dollar amount to invest (for fractional shares)"},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "sell_stock",
        "description": "Sell a stock position. Only sell if up 50%+ or if the agent has strong conviction to exit.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Stock ticker symbol"},
                "qty": {"type": "number", "description": "Number of shares to sell"},
            },
            "required": ["symbol", "qty"],
        },
    },
    {
        "name": "buy_option",
        "description": "Buy an options contract using a LIMIT order. You MUST call evaluate_option first to get the suggested limit price.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "OCC option symbol (e.g., AAPL250620C00200000)"},
                "qty": {"type": "integer", "description": "Number of contracts to buy"},
                "limit_price": {"type": "number", "description": "Limit price per share (NOT per contract). Get this from evaluate_option's suggested_limit_price."},
            },
            "required": ["symbol", "qty", "limit_price"],
        },
    },
    {
        "name": "sell_option",
        "description": "Sell (close) an options position you own using a LIMIT order.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "OCC option symbol"},
                "qty": {"type": "integer", "description": "Number of contracts to sell"},
                "limit_price": {"type": "number", "description": "Limit price per share. Use the bid price or slightly below."},
            },
            "required": ["symbol", "qty"],
        },
    },
    {
        "name": "evaluate_option",
        "description": "REQUIRED before buying any option. Evaluates pricing favorability: IV rank, bid-ask spread, volume, DTE, and returns a favorability score (1-10) with a suggested limit price. Only proceed with score >= 5.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Underlying stock ticker (e.g., HIMS, not the OCC symbol)"},
                "strike": {"type": "number", "description": "Strike price"},
                "option_type": {"type": "string", "enum": ["call", "put"], "description": "Option type"},
                "expiry_date": {"type": "string", "description": "Optional expiry date (YYYY-MM-DD). Defaults to ~30 days out."},
            },
            "required": ["symbol", "strike", "option_type"],
        },
    },
    {
        "name": "get_best_strikes",
        "description": "Find the best option strikes for a given budget and direction. Returns top 5 recommended contracts ranked by liquidity, spread, and leverage.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Underlying stock ticker"},
                "direction": {"type": "string", "enum": ["bullish", "bearish"], "description": "Trade direction"},
                "budget": {"type": "number", "description": "Dollar budget for the trade"},
                "expiry_date": {"type": "string", "description": "Optional target expiry (YYYY-MM-DD)"},
            },
            "required": ["symbol", "direction", "budget"],
        },
    },
    {
        "name": "get_priced_chain",
        "description": "Get a fully priced options chain with bid/ask, IV, volume, and open interest from Yahoo Finance. More detailed than the Alpaca chain.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Underlying stock ticker"},
                "expiry_date": {"type": "string", "description": "Optional target expiry (YYYY-MM-DD)"},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "check_thesis",
        "description": "Check if a position's thesis is broken using quantitative signals (momentum collapse, volume exodus, extended loss). If broken, selling is allowed regardless of P&L.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Stock ticker of the position to check"},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "sell_broken_thesis",
        "description": "Sell a position whose thesis has been confirmed broken by check_thesis. Bypasses the 50% gain sell threshold.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Stock ticker to sell"},
                "qty": {"type": "number", "description": "Number of shares to sell (use full position qty to exit completely)"},
            },
            "required": ["symbol", "qty"],
        },
    },
    {
        "name": "validate_trade",
        "description": "Check if a proposed trade passes all strategy rules (position limits, sector limits, sell thresholds) before executing.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["buy_stock", "buy_option", "sell_stock", "sell_option", "sell_broken_thesis"]},
                "symbol": {"type": "string"},
                "amount": {"type": "number", "description": "Dollar amount or premium cost"},
            },
            "required": ["action", "symbol", "amount"],
        },
    },
]


class TradingAgent:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        self.broker = Broker()
        self.strategy = StrategyRules(self.broker)
        self.screener = MarketScreener(self.broker)
        self.pricer = OptionsPricer()
        self.conversation_history = []
        self._broken_thesis_confirmed = set()  # symbols confirmed broken

    def _get_system_prompt(self):
        portfolio_state = self.strategy.get_portfolio_state()
        positions = portfolio_state.get("positions", [])
        sector_allocation = self.screener.get_sector_allocation(positions)

        # Pre-fetch screener data for the prompt (top 10 to keep prompt reasonable)
        try:
            top_movers = self.screener.get_top_movers(10)
        except Exception:
            top_movers = []

        try:
            earnings = self.screener.get_earnings_plays()[:10]
        except Exception:
            earnings = []

        return SYSTEM_PROMPT.format(
            rules=self.strategy.get_rules_summary(),
            portfolio_state=json.dumps(portfolio_state, indent=2),
            sector_allocation=json.dumps(sector_allocation, indent=2),
            screener_data=json.dumps(top_movers, indent=2),
            earnings_candidates=json.dumps(earnings, indent=2),
        )

    def _handle_tool_call(self, tool_name: str, tool_input: dict) -> str:
        """Execute a tool call and return the result as a string."""
        try:
            if tool_name == "get_quote":
                result = self.broker.get_quote(tool_input["symbol"])
            elif tool_name == "get_bars":
                result = self.broker.get_bars(tool_input["symbol"], tool_input.get("days", 30))
            elif tool_name == "get_snapshot":
                result = self.broker.get_snapshot(tool_input["symbol"])
            elif tool_name == "get_options_chain":
                result = self.broker.get_options_chain(
                    tool_input["symbol"], tool_input.get("expiration_date")
                )
            elif tool_name == "get_portfolio":
                state = self.strategy.get_portfolio_state()
                state["sector_allocation"] = self.screener.get_sector_allocation(
                    state.get("positions", [])
                )
                result = state
            elif tool_name == "scan_sector":
                result = self.screener.scan_sector(tool_input["sector"])
            elif tool_name == "scan_stock":
                result = self.screener.scan_symbol(tool_input["symbol"])
                if result is None:
                    result = {"error": f"Could not get data for {tool_input['symbol']}"}
            elif tool_name == "get_top_movers":
                result = self.screener.get_top_movers(tool_input.get("n", 20))
            elif tool_name == "get_earnings_candidates":
                result = self.screener.get_earnings_plays()
            elif tool_name == "get_sector_allocation":
                positions = self.broker.get_positions()
                result = self.screener.get_sector_allocation(positions)
            elif tool_name == "evaluate_option":
                result = self.pricer.evaluate_option(
                    tool_input["symbol"], tool_input["strike"],
                    tool_input.get("option_type", "call"),
                    tool_input.get("expiry_date"),
                )
            elif tool_name == "get_best_strikes":
                result = self.pricer.get_best_strikes(
                    tool_input["symbol"], tool_input.get("direction", "bullish"),
                    tool_input.get("budget", 5000), tool_input.get("expiry_date"),
                )
            elif tool_name == "get_priced_chain":
                result = self.pricer.get_options_chain_priced(
                    tool_input["symbol"], tool_input.get("expiry_date"),
                )
            elif tool_name == "check_thesis":
                result = self._check_thesis(tool_input["symbol"])
            elif tool_name == "sell_broken_thesis":
                result = self._execute_sell_broken_thesis(tool_input)
            elif tool_name == "validate_trade":
                result = self._validate_trade(tool_input)
            elif tool_name == "buy_stock":
                result = self._execute_buy_stock(tool_input)
            elif tool_name == "sell_stock":
                result = self._execute_sell_stock(tool_input)
            elif tool_name == "buy_option":
                result = self._execute_buy_option(tool_input)
            elif tool_name == "sell_option":
                result = self.broker.sell_option(
                    tool_input["symbol"], tool_input["qty"],
                    limit_price=tool_input.get("limit_price"),
                )
            else:
                result = {"error": f"Unknown tool: {tool_name}"}
        except Exception as e:
            result = {"error": str(e)}

        return json.dumps(result, indent=2)

    def _validate_trade(self, tool_input: dict) -> dict:
        action = tool_input["action"]
        amount = tool_input["amount"]
        portfolio_state = self.strategy.get_portfolio_state()

        # Check sector allocation for buys
        if action in ("buy_stock", "buy_option"):
            positions = portfolio_state.get("positions", [])
            sector_alloc = self.screener.get_sector_allocation(positions)
            symbol = tool_input["symbol"]
            # Find which sector this symbol belongs to
            from screener import UNIVERSE
            symbol_sector = None
            underlying = symbol if len(symbol) <= 10 else symbol[:4].rstrip("0123456789")
            for sector, syms in UNIVERSE.items():
                if underlying in syms or symbol in syms:
                    symbol_sector = sector
                    break
            if symbol_sector and sector_alloc.get(symbol_sector, 0) > config.MAX_SECTOR_ALLOCATION_PCT:
                return {
                    "allowed": False,
                    "reason": f"Sector {symbol_sector} already at {sector_alloc[symbol_sector]:.0%}, max is {config.MAX_SECTOR_ALLOCATION_PCT:.0%}",
                }

        if action == "buy_stock":
            ok, reason = self.strategy.can_buy_stock(tool_input["symbol"], amount, portfolio_state)
        elif action == "buy_option":
            ok, reason = self.strategy.can_buy_option(amount, portfolio_state)
        elif action == "sell_stock":
            pos = self.broker.get_position(tool_input["symbol"])
            if not pos:
                return {"allowed": False, "reason": "No position found"}
            ok, reason = self.strategy.should_sell_stock(pos)
        elif action == "sell_broken_thesis":
            symbol = tool_input["symbol"]
            if symbol in self._broken_thesis_confirmed:
                ok, reason = True, f"Thesis confirmed broken for {symbol}, sell allowed"
            else:
                ok, reason = False, f"Must call check_thesis on {symbol} first to confirm broken thesis"
        elif action == "sell_option":
            ok, reason = True, "Closing owned option is always allowed"
        else:
            return {"allowed": False, "reason": f"Unknown action: {action}"}

        return {"allowed": ok, "reason": reason}

    def _execute_buy_stock(self, tool_input: dict) -> dict:
        portfolio_state = self.strategy.get_portfolio_state()
        amount = tool_input.get("notional") or 0
        if tool_input.get("qty"):
            quote = self.broker.get_quote(tool_input["symbol"])
            amount = tool_input["qty"] * quote["ask"]

        ok, reason = self.strategy.can_buy_stock(tool_input["symbol"], amount, portfolio_state)
        if not ok:
            return {"error": f"Trade blocked by rules: {reason}"}

        # Check sector limit
        positions = portfolio_state.get("positions", [])
        sector_alloc = self.screener.get_sector_allocation(positions)
        from screener import UNIVERSE
        for sector, syms in UNIVERSE.items():
            if tool_input["symbol"] in syms:
                current = sector_alloc.get(sector, 0)
                new_pct = current + (amount / portfolio_state["total_equity"])
                if new_pct > config.MAX_SECTOR_ALLOCATION_PCT:
                    return {"error": f"Trade would push {sector} to {new_pct:.0%}, max {config.MAX_SECTOR_ALLOCATION_PCT:.0%}"}
                break

        return self.broker.buy_stock(
            tool_input["symbol"],
            qty=tool_input.get("qty"),
            notional=tool_input.get("notional"),
        )

    def _execute_sell_stock(self, tool_input: dict) -> dict:
        pos = self.broker.get_position(tool_input["symbol"])
        if not pos:
            return {"error": f"No position in {tool_input['symbol']}"}

        should_sell, reason = self.strategy.should_sell_stock(pos)
        if not should_sell:
            return {"error": f"Sell blocked: {reason}"}

        return self.broker.sell_stock(tool_input["symbol"], qty=tool_input["qty"])

    def _execute_buy_option(self, tool_input: dict) -> dict:
        portfolio_state = self.strategy.get_portfolio_state()
        limit_price = tool_input.get("limit_price")
        if not limit_price:
            return {"error": "limit_price is required. Call evaluate_option first to get suggested_limit_price."}

        # Estimate total cost: limit_price * 100 (per contract) * qty
        estimated_cost = limit_price * 100 * tool_input["qty"]
        ok, reason = self.strategy.can_buy_option(estimated_cost, portfolio_state)
        if not ok:
            return {"error": f"Trade blocked by rules: {reason}"}

        return self.broker.buy_option(tool_input["symbol"], tool_input["qty"], limit_price=limit_price)

    def _check_thesis(self, symbol: str) -> dict:
        """Check if a position's thesis is broken."""
        pos = self.broker.get_position(symbol)
        if not pos:
            return {"error": f"No position in {symbol}"}

        scan_data = self.screener.scan_symbol(symbol)
        is_broken, summary, triggers = self.strategy.check_broken_thesis(pos, scan_data)

        if is_broken:
            self._broken_thesis_confirmed.add(symbol)

        return {
            "symbol": symbol,
            "is_broken": is_broken,
            "summary": summary,
            "triggers": triggers,
            "position_pnl": f"{pos['unrealized_pl_pct']:+.1%}",
            "scan_data": scan_data,
            "action_allowed": "SELL ALLOWED — use sell_broken_thesis" if is_broken else "HOLD — thesis intact",
        }

    def _execute_sell_broken_thesis(self, tool_input: dict) -> dict:
        """Sell a position with confirmed broken thesis."""
        symbol = tool_input["symbol"]
        if symbol not in self._broken_thesis_confirmed:
            return {"error": f"Must call check_thesis on {symbol} first. Thesis not confirmed broken."}

        pos = self.broker.get_position(symbol)
        if not pos:
            return {"error": f"No position in {symbol}"}

        result = self.broker.sell_stock(symbol, qty=tool_input["qty"])
        if "error" not in result:
            self._broken_thesis_confirmed.discard(symbol)
        return result

    def run(self, user_message: str) -> str:
        """Run the agent with a user message and return the final response."""
        self.conversation_history.append({"role": "user", "content": user_message})

        while True:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                system=self._get_system_prompt(),
                tools=TOOLS,
                messages=self.conversation_history,
            )

            # Collect all content blocks
            assistant_content = response.content
            self.conversation_history.append({"role": "assistant", "content": assistant_content})

            # If no tool use, we're done
            if response.stop_reason == "end_turn":
                text_parts = [block.text for block in assistant_content if block.type == "text"]
                return "\n".join(text_parts)

            # Handle tool calls
            tool_results = []
            for block in assistant_content:
                if block.type == "tool_use":
                    print(f"  [TOOL] {block.name}({json.dumps(block.input)})")
                    result = self._handle_tool_call(block.name, block.input)
                    print(f"  [RESULT] {result[:200]}...")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            self.conversation_history.append({"role": "user", "content": tool_results})

    def analyze_and_trade(self):
        """Main entry point: ask the agent to analyze the market and make trades."""
        return self.run(
            "Analyze the current market conditions, macro backdrop, and our portfolio. "
            "Use the screener data provided and drill into the most promising sectors.\n\n"
            "1. MACRO VIEW: What's the current macro environment? Which sectors should we overweight and why?\n"
            "2. SCREENER HITS: From the top movers and earnings candidates, which 3-5 names stand out?\n"
            "3. OPTIONS PLAYS (MANDATORY): Check current options exposure. If below 20%, you MUST add options positions.\n"
            "   - Look at options chains for our existing holdings (especially any with earnings signals)\n"
            "   - Look for earnings plays on names with divided analyst consensus\n"
            "   - Buy OTM calls, spreads, or straddles. Size at 5-10% of portfolio per play.\n"
            "4. EARNINGS PLAYS: Are any high-beta names reporting soon? Size an options play.\n"
            "5. SECTOR CHECK: Verify we're not overweight any sector before trading.\n"
            "6. EXECUTE: Place the trades you're most confident in — BOTH stock and options. Validate each one first.\n\n"
            "For each idea, provide: thesis, conviction (1-10), catalyst, expected timeline, and specific trade."
        )

    def review_positions(self):
        """Ask the agent to review existing positions."""
        return self.run(
            "Review all current positions. For each position:\n"
            "1. Check if any stocks are up 50%+ and should be sold\n"
            "2. Check if any options are down 80%+ and should be cut\n"
            "3. Check sector allocation — are we overweight anywhere?\n"
            "4. Assess if the original thesis still holds for each position\n"
            "5. Flag any upcoming earnings for names we hold\n"
            "6. Recommend any adjustments (but follow the rules strictly)"
        )

    def scan_market(self):
        """Quick market scan without trading."""
        return self.run(
            "Do a quick market scan. Show me:\n"
            "1. Top 10 highest-scoring stocks from the screener (beta * vol * volume surge)\n"
            "2. Any earnings candidates showing unusual activity\n"
            "3. Which sectors look strongest/weakest right now based on the data\n"
            "4. Any actionable trade ideas for our next session\n\n"
            "Don't execute any trades — just analyze and report."
        )
