# AI-Powered Autonomous Trading Fund

## Overview

This is an AI-driven autonomous trading system that uses Claude (Anthropic's frontier LLM) as the decision-making engine, connected to live brokerage APIs for fully automated trade execution. The system screens for opportunities, builds conviction-weighted theses, enforces hard risk controls, and executes trades — all without human intervention.

**Inception**: April 14, 2026
**Return (first 2 days)**: +9.9% vs. SPY +1.9%
**Current Positions**: 5 concentrated holdings, all profitable

---

## Investment Strategy

### Philosophy
Concentrated, catalyst-driven, high-conviction investing with an AI agent that combines quantitative screening with qualitative reasoning. The system targets asymmetric opportunities — high upside, capped downside — in liquid, high-volatility names where market dislocations or upcoming catalysts create mispriced risk/reward.

### Universe & Screening
The system maintains a curated universe of ~155 stocks across 9 sectors. Every candidate must pass three quantitative filters:

- **Beta > 1.3** — Only high-beta names that amplify market moves
- **Average daily volume > 2M shares** — Ensures liquidity for clean entries and exits
- **Daily volatility > 3%** — Sufficient price movement to generate meaningful returns

Stocks are ranked by a composite score of beta x volatility x volume surge, surfacing the names with the most explosive near-term potential.

### Sector Strategy
- **Default: sector neutral** — No single sector exceeds 35% of portfolio
- **Tactical overweights** permitted when the AI agent identifies strong macro tailwinds (e.g., energy during supply shocks, software during valuation dislocations, financials during credit cycle shifts)
- The agent explains its macro thesis before overweighting any sector

### Earnings & Catalyst Trading
- Actively screens for stocks with upcoming earnings showing divided analyst consensus (wide EPS estimate ranges)
- Uses volume surge + volatility spike as real-time signals for earnings anticipation
- Sizes earnings plays at 5-8% of portfolio using options for maximum leverage on binary outcomes
- Targets stocks where the market is likely mispricing the probability of a surprise

---

## Instruments & Options Strategy

### Stocks
- Concentrated portfolio of 3-7 high-conviction positions
- Entries sized at 10-20% of portfolio per position
- Fractional shares supported for precise dollar-amount allocation

### Options (Level 3 Approved)
- **Long calls**: OTM calls (1-2 strikes out, 1-3 month expiry) on highest-conviction names for leverage
- **Long puts**: Protective puts as hedges when warranted
- **Spreads**: Vertical spreads for defined-risk directional bets
- **Covered calls**: Income generation on existing stock holdings
- **Earnings straddles**: Volatility plays around binary events
- Target options allocation: 20-40% of portfolio

---

## Risk Management

### Hard Constraints (enforced programmatically — cannot be overridden by AI)
| Rule | Limit |
|---|---|
| Max position size (single stock) | 20% of portfolio |
| Max sector allocation | 35% of portfolio |
| Max total options exposure | 40% of portfolio |
| Max single options position | 10% of portfolio |
| Options stop-loss | Cut at 80% loss of premium |
| Margin trading | Prohibited |
| Naked options | Prohibited |
| Short selling | Prohibited |

### Sell Discipline
- **Stocks**: Only sell when position is up 50%+ (let winners run)
- **Options**: Auto-cut at 80% loss; take profits opportunistically
- **Exception**: May exit if the original investment thesis is broken, regardless of P&L

### Maximum Loss
Capital at risk is strictly limited to the amount deposited. No margin, no naked options, no leverage beyond long options contracts. **Maximum loss = capital invested, never more.**

---

## Execution & Automation

### How It Works
```
Market Data (Alpaca API) --> AI Screener --> Claude Agent (reasoning + thesis) --> Risk Validation --> Order Execution
         ^                                                                                              |
         |_______________________________ Portfolio feedback loop ______________________________________|
```

1. **Screener** pulls live market data and ranks the universe by momentum, volatility, and volume signals
2. **Claude agent** receives the screening data, current portfolio state, macro context, and sector allocations
3. Agent reasons about market conditions, builds investment theses, and selects trades
4. **Every trade is validated** against hard risk limits before execution
5. Orders are placed via the Alpaca brokerage API

### Schedule
The system runs autonomously three times daily during market hours (Mon-Fri):

| Time (ET) | Action |
|---|---|
| 9:45 AM | **Analyze & Trade** — Post-open scan, new entries, options plays |
| 12:30 PM | **Analyze & Trade** — Midday reassessment, momentum shifts |
| 3:30 PM | **Review** — Pre-close position review, profit-taking, risk check |

### Technology Stack
- **AI Engine**: Claude (Anthropic) — frontier LLM for reasoning and decision-making
- **Brokerage**: Alpaca Markets — SEC/FINRA regulated, SIPC insured
- **Language**: Python
- **Execution**: Automated via cron scheduling on dedicated infrastructure

---

## Performance

### Inception to Date (April 14-16, 2026)

| Metric | Fund | SPY | QQQ |
|---|---|---|---|
| Return | **+9.9%** | +1.9% | +2.6% |
| Alpha vs. SPY | **+8.0%** | — | — |
| Win Rate | 5/5 positions (100%) | — | — |
| Max Drawdown | -4.2% (Day 1) | — | — |

### Current Holdings
| Position | Sector | Return |
|---|---|---|
| HIMS | Healthcare | +25.6% |
| DOCN | Software | +10.6% |
| NET | Technology | +6.8% |
| LUNR | Industrials | +5.4% |
| SNOW | Software | +4.8% |

*Past performance is not indicative of future results.*

---

## Key Differentiators

1. **AI-native decision making**: Not rules-based quant — the agent reasons about catalysts, macro conditions, and thesis quality the way a human PM would, but with faster data processing and no emotional bias
2. **Hard risk rails**: AI creativity is bounded by programmatic risk controls that cannot be overridden
3. **Transparent reasoning**: Every trade decision includes a written thesis, conviction score, and catalyst timeline — fully auditable
4. **Adaptive**: The agent reassesses 3x daily and adjusts to changing market conditions, unlike static algorithmic strategies
5. **Scalable**: Same infrastructure handles $15K or $15M — strategy scales with capital

---

## Disclaimers

- This is an experimental AI-driven trading system
- Past performance does not guarantee future results
- All investments involve risk, including potential loss of principal
- Options trading involves additional risks and is not suitable for all investors
- The system is designed so that maximum loss cannot exceed capital deposited
- Not registered as an investment advisor; this is a proprietary trading system
