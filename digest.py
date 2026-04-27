#!/usr/bin/env python3
"""Generate a tight end-of-day email digest with LLM commentary.

Used by emailer.py for the daily portfolio email — replaces the previous
"send the entire dashboard" approach with a focused summary: PnL, top
movers, today's trades, and 5-7 sentences of Claude-generated commentary.
"""

import html
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'), override=True)

import anthropic

from broker import Broker
from descriptions import get_description
from stats import compute_portfolio_stats
import config
from report import (
    _e,
    _fmt_dollars,
    _fmt_pct,
    _fmt_pct_1dp,
    _get_last_equity,
    _extract_trade_history,
)


# ── Commentary ──────────────────────────────────────────────

def _generate_commentary(stats: dict, positions: list[dict], todays_trades: list[dict]) -> str:
    """Ask Claude for 5-7 sentences of portfolio commentary."""
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    portfolio_lines = "\n".join(
        f"- {p['symbol']}: today {p['change_today']*100:+.1f}%, total {p['unrealized_pl_pct']*100:+.1f}%, ${p['market_value']:,.0f}"
        for p in positions[:12]
    ) or "No open positions."

    trade_lines = "\n".join(
        f"- {t['side']} {t['symbol']} @ {t['filled_price']}: {t.get('thesis') or 'no thesis recorded'}"
        for t in todays_trades
    ) or "No trades executed today."

    day_pct = stats["day_return_pct"] * 100
    day_dollars = stats["day_return_dollars"]
    total_pct = stats["total_return_pct"] * 100
    equity = stats.get("current_equity", 0)

    prompt = f"""Write a brief end-of-day note for an investor email about the portfolio below.

State of the book:
- Portfolio value: ${equity:,.0f}
- Today's PnL: {day_pct:+.2f}% (${day_dollars:+,.0f})
- Total return since 4/14/26 inception: {total_pct:+.2f}%

Positions (today % / total %):
{portfolio_lines}

Today's trades:
{trade_lines}

Write 5-7 sentences covering, in this order:
(1) what happened today — the biggest movers and a plausible reason if obvious from context
(2) what's working in the book — winners and the strategy themes paying off
(3) what to watch tomorrow — earnings, catalysts, or risks visible from the holdings

Be direct and specific. Reference tickers by name. No hedging language, no generic
platitudes, no compliance disclaimers, no preamble like "Today the portfolio...".
One paragraph, no bullets, no headers."""

    msg = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    return next((b.text for b in msg.content if b.type == "text"), "").strip()


# ── Renderer ──────────────────────────────────────────────

_DIGEST_CSS = """
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #ffffff;
    color: #0A0A0A;
    line-height: 1.5;
    -webkit-font-smoothing: antialiased;
  }
  .wrap { max-width: 600px; margin: 0 auto; padding: 32px 24px; }
  .brand { font-size: 22px; font-weight: 700; letter-spacing: -0.02em; }
  .brand-sub { font-size: 12px; color: #888; text-transform: uppercase; letter-spacing: 0.1em; margin-top: 4px; }

  .hero { padding: 28px 0 20px; border-bottom: 1px solid #EEEEEE; margin-bottom: 24px; }
  .hero-label { font-size: 10px; font-weight: 600; color: #888; text-transform: uppercase; letter-spacing: 0.15em; margin-bottom: 8px; }
  .hero-value { font-size: 40px; font-weight: 700; letter-spacing: -0.03em; font-feature-settings: 'tnum'; }
  .hero-sub { font-size: 13px; color: #555; margin-top: 6px; font-feature-settings: 'tnum'; }

  .stats { display: table; width: 100%; border-collapse: collapse; margin-bottom: 24px; }
  .stat-cell { display: table-cell; width: 33.33%; padding: 14px 12px; border: 1px solid #EEEEEE; vertical-align: top; }
  .stat-label { font-size: 10px; font-weight: 600; color: #888; text-transform: uppercase; letter-spacing: 0.12em; margin-bottom: 6px; }
  .stat-value { font-size: 17px; font-weight: 600; font-feature-settings: 'tnum'; letter-spacing: -0.01em; }

  .section { margin-bottom: 24px; }
  .section-label { font-size: 11px; font-weight: 600; color: #888; text-transform: uppercase; letter-spacing: 0.15em; margin-bottom: 10px; }

  .movers { display: table; width: 100%; border-collapse: collapse; }
  .mover { display: table-row; }
  .mover-cell { display: table-cell; padding: 8px 0; border-bottom: 1px solid #F3F3F3; vertical-align: middle; font-size: 13px; }
  .mover-ticker { font-weight: 700; }
  .mover-pct { text-align: right; font-feature-settings: 'tnum'; }

  .trade { padding: 8px 0; border-bottom: 1px solid #F3F3F3; font-size: 13px; }
  .trade-side { display: inline-block; font-size: 10px; font-weight: 600; padding: 2px 8px; border-radius: 3px; letter-spacing: 0.08em; margin-right: 8px; }
  .trade-side-buy { background: #E8F0E6; color: #1E7A3A; }
  .trade-side-sell { background: #FCE8E6; color: #B33030; }
  .trade-symbol { font-weight: 700; }

  .commentary { padding: 18px 18px; background: #FAFBFC; border-left: 3px solid #5B7B9A; font-size: 14px; line-height: 1.7; color: #222; }

  .footer { margin-top: 28px; padding-top: 20px; border-top: 1px solid #EEEEEE; font-size: 11px; color: #888; }
  .footer a { color: #5B7B9A; text-decoration: none; }

  .pos { color: #1E7A3A; }
  .neg { color: #B33030; }
"""


def _render_digest(
    stats: dict,
    account: dict,
    positions: list[dict],
    todays_trades: list[dict],
    top_winners: list[dict],
    top_losers: list[dict],
    commentary: str,
) -> str:
    day_pct = stats["day_return_pct"]
    day_dollars = stats["day_return_dollars"]
    total_pct = stats["total_return_pct"]
    total_dollars = stats["total_return_dollars"]

    day_color = "pos" if day_pct > 0 else ("neg" if day_pct < 0 else "")
    total_color = "pos" if total_pct > 0 else ("neg" if total_pct < 0 else "")

    def mover_row(p: dict) -> str:
        cls = "pos" if p["change_today"] > 0 else ("neg" if p["change_today"] < 0 else "")
        return (
            f'<div class="mover">'
            f'<div class="mover-cell mover-ticker">{_e(p["symbol"])}</div>'
            f'<div class="mover-cell" style="color:#666">{_e(get_description(p["symbol"])[:48])}</div>'
            f'<div class="mover-cell mover-pct {cls}">{_fmt_pct_1dp(p["change_today"])}</div>'
            f'</div>'
        )

    winners_html = "".join(mover_row(p) for p in top_winners) or '<div class="mover-cell" style="color:#888">None</div>'
    losers_html = "".join(mover_row(p) for p in top_losers) or '<div class="mover-cell" style="color:#888">None</div>'

    def trade_row(t: dict) -> str:
        side_class = "buy" if t["side"] == "BUY" else "sell"
        thesis_html = ""
        if t.get("thesis"):
            thesis_html = f'<div style="margin-top:4px;color:#555">{_e(t["thesis"])}</div>'
        return (
            f'<div class="trade">'
            f'<span class="trade-side trade-side-{side_class}">{_e(t["side"])}</span>'
            f'<span class="trade-symbol">{_e(t["symbol"])}</span> '
            f'<span style="color:#888">at {_e(t["filled_price"])}</span>'
            f'{thesis_html}'
            f'</div>'
        )

    if todays_trades:
        trades_html = "".join(trade_row(t) for t in todays_trades)
    else:
        trades_html = '<div style="font-size:13px;color:#888;font-style:italic">No trades today.</div>'

    now = datetime.now()
    date_str = now.strftime("%B %d, %Y")
    time_str = now.strftime("%I:%M %p PT").lstrip("0")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GG Capital · {_e(date_str)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>{_DIGEST_CSS}</style>
</head>
<body>
<div class="wrap">

  <div>
    <div class="brand">GG Capital</div>
    <div class="brand-sub">{_e(date_str)} · {_e(time_str)}</div>
  </div>

  <div class="hero">
    <div class="hero-label">Today's PnL</div>
    <div class="hero-value {day_color}">{_fmt_pct(day_pct)}</div>
    <div class="hero-sub {day_color}">{_fmt_dollars(day_dollars, show_sign=True)} on ${account['equity']:,.0f}</div>
  </div>

  <div class="stats">
    <div class="stat-cell">
      <div class="stat-label">Portfolio Value</div>
      <div class="stat-value">${account['equity']:,.0f}</div>
    </div>
    <div class="stat-cell">
      <div class="stat-label">Total Return</div>
      <div class="stat-value {total_color}">{_fmt_pct(total_pct)}</div>
    </div>
    <div class="stat-cell">
      <div class="stat-label">Total $ PnL</div>
      <div class="stat-value {total_color}">{_fmt_dollars(total_dollars, show_sign=True)}</div>
    </div>
  </div>

  <div class="section">
    <div class="section-label">Top Movers Today</div>
    <div style="margin-bottom:12px">{winners_html}</div>
    <div>{losers_html}</div>
  </div>

  <div class="section">
    <div class="section-label">Trades Today</div>
    {trades_html}
  </div>

  <div class="section">
    <div class="section-label">What Happened</div>
    <div class="commentary">{_e(commentary)}</div>
  </div>

  <div class="footer">
    Full dashboard: <a href="https://ggcapital.vercel.app">ggcapital.vercel.app</a><br>
    AI-managed paper trading strategy · Not investment advice.
  </div>

</div>
</body>
</html>"""


# ── Entry point ──────────────────────────────────────────────

def generate_digest() -> tuple[str, str]:
    """Generate the digest email. Returns (subject, html)."""
    b = Broker()
    account = b.get_account()
    positions = b.get_positions()
    last_equity = _get_last_equity()

    stats = compute_portfolio_stats(account["equity"], last_equity)
    if "error" in stats:
        date_str = datetime.now().strftime("%B %d, %Y")
        return (
            f"GG Capital · {date_str} · Error",
            f"<p>Error computing stats: {html.escape(stats['error'])}</p>",
        )
    stats["current_equity"] = account["equity"]

    trade_history = _extract_trade_history()
    today_str = datetime.now().strftime("%b %d, %Y")
    todays_trades = [t for t in trade_history if t["date"] == today_str]

    sorted_by_day = sorted(positions, key=lambda p: p["change_today"], reverse=True)
    top_winners = [p for p in sorted_by_day[:3] if p["change_today"] > 0]
    top_losers = [p for p in reversed(sorted_by_day[-3:]) if p["change_today"] < 0]

    try:
        commentary = _generate_commentary(stats, positions, todays_trades)
    except Exception as e:
        commentary = f"(Commentary unavailable: {e})"

    body = _render_digest(stats, account, positions, todays_trades, top_winners, top_losers, commentary)

    date_str = datetime.now().strftime("%B %d, %Y")
    subject = (
        f"GG Capital · {date_str} · "
        f"{_fmt_dollars(stats['day_return_dollars'], show_sign=True)} "
        f"({_fmt_pct(stats['day_return_pct'])})"
    )
    return subject, body


if __name__ == "__main__":
    subject, html_body = generate_digest()
    print(f"Subject: {subject}")
    print(f"HTML length: {len(html_body):,} chars")
    out = Path(os.path.dirname(os.path.abspath(__file__))) / "latest_digest.html"
    out.write_text(html_body)
    print(f"Digest written to {out}")
