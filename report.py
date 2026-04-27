#!/usr/bin/env python3
"""Generate the GG Capital public dashboard.

Builds a clean, Neutrogena-inspired HTML report with:
- Strategy summary at top
- Headline stats (Total Return, PnL, 1-Day Return, CAGR, SPY/QQQ comparison)
- Positions with business descriptions
- Trade history feed with rationale
"""

import html
import os
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'), override=True)

from broker import Broker
from stats import compute_portfolio_stats, _alpaca_headers, _alpaca_base_url
from descriptions import get_description
import requests
import config


# Shorthand for HTML-escaping any string interpolated into the template.
# Covers ticker descriptions (static), theses parsed from LLM logs (untrusted),
# and symbols/prices from Alpaca (trusted but escaped defensively).
_e = html.escape


# ── Helpers ──────────────────────────────────────────────

def _fmt_dollars(v: float, show_sign: bool = False) -> str:
    sign = "+" if show_sign and v > 0 else ("−" if v < 0 else "")
    return f"{sign}${abs(v):,.0f}"


def _fmt_pct(v: float, show_sign: bool = True) -> str:
    sign = "+" if show_sign and v > 0 else ("−" if v < 0 else "")
    return f"{sign}{abs(v)*100:.2f}%"


def _fmt_pct_1dp(v: float, show_sign: bool = True) -> str:
    sign = "+" if show_sign and v > 0 else ("−" if v < 0 else "")
    return f"{sign}{abs(v)*100:.1f}%"


def _fmt_paren_pct(v: float) -> str:
    """Format percent with negatives in parentheses instead of minus signs."""
    if v >= 0:
        return f"+{v*100:.2f}%"
    return f"({abs(v)*100:.2f}%)"


def _get_last_equity() -> float:
    """Get yesterday's closing equity for accurate daily return."""
    try:
        r = requests.get(
            f"{_alpaca_base_url()}/v2/account",
            headers=_alpaca_headers(),
            timeout=10,
        )
        return float(r.json().get("last_equity", 0))
    except Exception:
        return 0


def _get_entry_dates() -> dict[str, str]:
    """Return a map of symbol -> earliest filled-buy date (YYYY-MM-DD)."""
    try:
        r = requests.get(
            f"{_alpaca_base_url()}/v2/orders",
            headers=_alpaca_headers(),
            params={"status": "closed", "limit": 500, "direction": "asc"},
            timeout=10,
        )
        orders = r.json()
    except Exception:
        return {}
    first_buy: dict[str, str] = {}
    for o in orders:
        if o.get("status") != "filled" or o.get("side") != "buy":
            continue
        symbol = o.get("symbol")
        if not symbol or symbol in first_buy:
            continue
        ts = o.get("filled_at") or o.get("submitted_at") or ""
        first_buy[symbol] = ts[:10]
    return first_buy


def _extract_trade_history() -> list[dict]:
    """Pull executed orders + rationale from agent logs."""
    b = Broker()
    orders = b.get_orders("closed")

    # Build a map of symbol -> most recent thesis from logs
    log_dir = Path(os.path.dirname(os.path.abspath(__file__))) / "logs"
    theses = _extract_theses_from_logs(log_dir)

    history = []
    for o in orders:
        symbol = o["symbol"]
        side = "BUY" if "BUY" in str(o["side"]) else "SELL"
        submitted = o.get("submitted_at", "")
        # Parse ISO timestamp
        try:
            dt = datetime.fromisoformat(submitted.replace("Z", "+00:00"))
            date_str = dt.strftime("%b %d, %Y")
        except Exception:
            date_str = submitted[:10]

        filled_price = o.get("filled_avg_price") or "N/A"
        try:
            filled_price = f"${float(filled_price):.2f}"
        except (ValueError, TypeError):
            filled_price = str(filled_price)

        history.append({
            "date": date_str,
            "symbol": symbol,
            "side": side,
            "filled_price": filled_price,
            "status": str(o.get("status", "")).replace("OrderStatus.", ""),
            "thesis": theses.get(symbol, ""),
        })

    # Deduplicate by (date, symbol, side) — keep the first (earliest) instance
    seen = set()
    deduped = []
    for h in history:
        key = (h["date"], h["symbol"], h["side"])
        if key not in seen:
            seen.add(key)
            deduped.append(h)
    return deduped


def _extract_theses_from_logs(log_dir: Path) -> dict[str, str]:
    """Parse agent log files to extract the thesis behind each ticker buy."""
    theses = {}
    if not log_dir.exists():
        return theses

    log_files = sorted(log_dir.glob("analyze_*.log"), reverse=True)

    # Pattern: look for "SYMBOL" blocks followed by "thesis" or "Thesis" lines
    for log_file in log_files:
        try:
            text = log_file.read_text()
        except Exception:
            continue

        # Match patterns like "**TICKER** - ... Thesis: ..." or "TICKER (...): ... Thesis: ..."
        # Simple approach: find "Thesis:" lines and the nearest preceding ticker mention
        for match in re.finditer(r"(?:\*\*([A-Z]{2,5})(?:\s|\*|:)|\b([A-Z]{2,5})\b).{0,200}?[Tt]hesis[:\*\s]+([^\n]{20,200})", text, re.DOTALL):
            symbol = match.group(1) or match.group(2)
            thesis = match.group(3).strip().rstrip("*").strip()
            # Clean up markdown
            thesis = re.sub(r"[\*\_`]", "", thesis).strip()
            if symbol and len(thesis) > 15 and symbol not in theses:
                theses[symbol] = thesis[:180]
    return theses


# ── Strategy Copy ──────────────────────────────────────────────

STRATEGY_COPY = {
    "tagline": "An AI-native fund for both tails of the IQ bell curve — top-percentile returns, zero overthinking.",
    "overview": (
        "GG Capital is a fully autonomous trading strategy run by an AI agent. "
        "The agent screens a curated universe of high-beta US equities, builds "
        "catalyst-driven theses, and executes trades within strict risk rails — "
        "three times per trading day."
    ),
    "philosophy": {
        "low_iq": {
            "iq": "IQ 70",
            "label": "GG Capital.",
            "quote": "idk, chart go up.",
        },
        "midwit": {
            "iq": "IQ 100",
            "label": "The midwit",
            "quote": "THE MARKET IS ALREADY EFFICIENT!! INDEX FUNDS ARE THE OPTIMAL STRATEGY!! A ROLEX IS JUST A WATCH!!",
        },
        "high_iq": {
            "iq": "IQ 145",
            "label": "GG Capital.",
            "quote": "After decomposing 14 factors and regressing against expected returns across every credible asset class, GG Capital.",
        },
    },
    "parameters": [
        ("Inception Capital", "$100,000"),
        ("Universe", "~155 US equities across 9 sectors"),
        ("Instruments", "Stocks, long calls/puts, spreads"),
        ("Screening", "Beta > 1.3  ·  Volume > 2M  ·  Volatility > 3%"),
        ("Max position", "20% of portfolio"),
        ("Max sector", "35% of portfolio"),
        ("Max options", "40% of portfolio"),
        ("Sell discipline", "50%+ winners or broken-thesis exits"),
        ("Leverage", "None — no margin, no naked options, no shorts"),
        ("Trade cadence", "3× daily (Mon-Fri)"),
    ],
    "goal": "Target: Significantly outperform SPY and QQQ on a post-fee, pre-tax basis regardless of market backdrop.",
    "schedule_intro": (
        "Three times per trading day (Mon–Fri), the agent wakes up, reads the market, "
        "and decides what to buy, sell, or hold — bounded by risk rails it cannot override. "
        "Every run regenerates this dashboard."
    ),
    "schedule": [
        {
            "time": "9:45 AM ET",
            "tag": "Post-Open",
            "title": "Analyze & Trade",
            "body": (
                "After morning noise has settled, the agent runs a 6-step playbook: "
                "(1) form a macro view and pick sector overweights; "
                "(2) pull the 3–5 highest-scoring names from the screener; "
                "(3) if options exposure is below 20%, add OTM calls, spreads, or straddles "
                "(5–10% per play); "
                "(4) hunt earnings plays on high-beta names with divided analyst consensus; "
                "(5) verify no sector is over the 35% cap; "
                "(6) execute the highest-conviction trades with a written thesis, "
                "conviction score (1–10), and catalyst timeline."
            ),
        },
        {
            "time": "12:30 PM ET",
            "tag": "Midday",
            "title": "Analyze & Trade",
            "body": (
                "Same 6-step prompt as the morning run. The agent reassesses the macro "
                "tape, looks for fresh momentum shifts and intraday setups, and may add "
                "new positions — or do nothing if no idea clears the conviction bar."
            ),
        },
        {
            "time": "3:30 PM ET",
            "tag": "Pre-Close",
            "title": "Position Review",
            "body": (
                "30 minutes before the bell. No new entries — only management of the book: "
                "(1) sell any stock up 50%+; "
                "(2) cut any option down 80%+ on premium; "
                "(3) reassess each position's original thesis (exit if broken, regardless of P&L); "
                "(4) check sector drift; "
                "(5) flag upcoming earnings on holdings."
            ),
        },
    ],
}


# ── HTML Template ──────────────────────────────────────────────

def render_dashboard(
    stats: dict,
    positions: list[dict],
    trade_history: list[dict],
    account: dict,
) -> str:
    """Render the full HTML dashboard."""

    # ── Top-line numbers
    total_pct = stats["total_return_pct"]
    total_dollars = stats["total_return_dollars"]
    day_pct = stats["day_return_pct"]
    day_dollars = stats["day_return_dollars"]
    cagr = stats["cagr"]
    inception = stats["inception_date"]
    days_since = stats["days_since_inception"]

    spy_ret = stats["benchmarks"]["SPY"]["total_return_pct"]
    qqq_ret = stats["benchmarks"]["QQQ"]["total_return_pct"]
    spy_cagr = stats["benchmarks"]["SPY"]["cagr"]
    qqq_cagr = stats["benchmarks"]["QQQ"]["cagr"]
    spy_day = stats["benchmarks"]["SPY"]["day_return_pct"]
    qqq_day = stats["benchmarks"]["QQQ"]["day_return_pct"]
    alpha_spy = stats["alpha"]["vs_spy"]
    alpha_qqq = stats["alpha"]["vs_qqq"]

    pos_color = lambda v: "pos" if v > 0 else ("neg" if v < 0 else "neu")

    # Alpha cells render "—" when the benchmark fetch failed (yfinance can
    # return empty on rate limits / weekends), rather than a misleading 0.00%.
    def _alpha_cell(v):
        if v is None:
            return ('neu', '—')
        return (pos_color(v), _fmt_paren_pct(v))

    alpha_spy_class, alpha_spy_text = _alpha_cell(alpha_spy)
    alpha_qqq_class, alpha_qqq_text = _alpha_cell(alpha_qqq)

    # Sort positions by market value (largest first)
    positions_sorted = sorted(positions, key=lambda p: p["market_value"], reverse=True)
    total_invested = sum(p["market_value"] for p in positions_sorted)

    # Parameters table
    params_html = "".join(
        f'<div class="param-row"><span class="param-label">{k}</span><span class="param-value">{v}</span></div>'
        for k, v in STRATEGY_COPY["parameters"]
    )

    # Schedule tiles for the "Details" section
    schedule_tiles_html = "".join(
        f"""
        <div class="schedule-tile">
            <div class="schedule-time">{_e(slot['time'])} <span class="schedule-tag">{_e(slot['tag'])}</span></div>
            <div class="schedule-title">{_e(slot['title'])}</div>
            <div class="schedule-body">{_e(slot['body'])}</div>
        </div>
        """
        for slot in STRATEGY_COPY["schedule"]
    )

    # Philosophy: use real meme image if present, else text-based tiles
    philosophy_img_path = Path(os.path.dirname(os.path.abspath(__file__))) / "assets" / "bell-curve.png"
    phil = STRATEGY_COPY["philosophy"]
    if philosophy_img_path.exists():
        philosophy_html = f"""
        <div class="philosophy-image">
            <img src="assets/bell-curve.png" alt="Bell curve: GG Capital agrees at IQ 70 and IQ 145; the midwit disagrees at IQ 100.">
        </div>
        """
    else:
        philosophy_html = f"""
        <div class="philosophy-grid">
            <div class="phil-tile phil-tail">
                <div class="phil-iq">{phil['low_iq']['iq']}</div>
                <div class="phil-label">{phil['low_iq']['label']}</div>
                <div class="phil-quote">{phil['low_iq']['quote']}</div>
            </div>
            <div class="phil-tile phil-midwit">
                <div class="phil-iq">{phil['midwit']['iq']}</div>
                <div class="phil-label">{phil['midwit']['label']}</div>
                <div class="phil-quote">{phil['midwit']['quote']}</div>
            </div>
            <div class="phil-tile phil-tail">
                <div class="phil-iq">{phil['high_iq']['iq']}</div>
                <div class="phil-label">{phil['high_iq']['label']}</div>
                <div class="phil-quote">{phil['high_iq']['quote']}</div>
            </div>
        </div>
        """

    # Positions rows
    entry_dates = _get_entry_dates()
    pos_rows = ""
    for p in positions_sorted:
        symbol = p["symbol"]
        desc = get_description(symbol)
        pct_of_port = (p["market_value"] / account["equity"]) * 100 if account["equity"] > 0 else 0
        pl_class = pos_color(p["unrealized_pl"])
        day_class = pos_color(p["change_today"])
        entry_date = entry_dates.get(symbol, "—")
        # Format entry date as M/D/YY
        entry_date_display = entry_date
        try:
            dt = datetime.strptime(entry_date, "%Y-%m-%d")
            entry_date_display = f"{dt.month}/{dt.day}/{dt.year % 100:02d}"
        except Exception:
            pass
        # Round shares to nearest whole number
        qty_display = f"{round(p['qty']):,}"
        # Total return: 1 decimal place
        total_return_display = _fmt_pct_1dp(p["unrealized_pl_pct"])
        day_return_display = _fmt_pct_1dp(p["change_today"])
        pos_rows += f"""
        <tr>
            <td class="pos-ticker">{_e(symbol)}</td>
            <td class="entry-date">{_e(entry_date_display)}</td>
            <td class="right num">${p['avg_entry_price']:,.2f}</td>
            <td class="right num">${p['current_price']:,.2f}</td>
            <td class="right num">{qty_display}</td>
            <td class="right num">${p['market_value']:,.0f}</td>
            <td class="right num">{pct_of_port:.1f}%</td>
            <td class="right num {pl_class}">{total_return_display}</td>
            <td class="right num {day_class}">{day_return_display}</td>
            <td class="pos-desc">{_e(desc)}</td>
        </tr>
        """

    # Trade history feed (most recent first)
    trade_feed_html = ""
    for t in trade_history[:30]:
        thesis_html = f'<div class="trade-thesis">{_e(t["thesis"])}</div>' if t["thesis"] else ""
        desc = get_description(t["symbol"])
        side_class = "buy" if t["side"] == "BUY" else "sell"
        trade_feed_html += f"""
        <div class="trade-row">
            <div class="trade-date">{_e(t['date'])}</div>
            <div class="trade-main">
                <div class="trade-line">
                    <span class="trade-side trade-side-{side_class}">{_e(t['side'])}</span>
                    <span class="trade-symbol">{_e(t['symbol'])}</span>
                    <span class="trade-meta">at {_e(t['filled_price'])}</span>
                </div>
                <div class="trade-desc">{_e(desc)}</div>
                {thesis_html}
            </div>
        </div>
        """
    if not trade_feed_html:
        trade_feed_html = '<div class="empty">No trades yet.</div>'

    # Format date
    now_str = datetime.now().strftime("%B %d, %Y · %I:%M %p PT")

    # Handle extreme CAGR values (early in life, annualized % is absurd)
    cagr_note = ""
    if days_since < 60:
        cagr_note = f'<div class="cagr-caveat">Based on {days_since} days — annualization amplifies noise.</div>'

    spy_cagr_display = f"{spy_cagr*100:,.1f}%" if abs(spy_cagr) < 100 else f"{spy_cagr*100:,.0f}%"
    qqq_cagr_display = f"{qqq_cagr*100:,.1f}%" if abs(qqq_cagr) < 100 else f"{qqq_cagr*100:,.0f}%"
    gg_cagr_display = f"{cagr*100:,.0f}%" if abs(cagr) > 100 else f"{cagr*100:,.1f}%"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GG Capital · {now_str}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html, body {{
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #ffffff;
    color: #0A0A0A;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
    line-height: 1.5;
  }}
  .container {{
    max-width: 1120px;
    margin: 0 auto;
    padding: 48px 32px 96px;
  }}

  /* Header */
  .header {{
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    padding-bottom: 32px;
    border-bottom: 1px solid #EEEEEE;
    margin-bottom: 48px;
  }}
  .brand {{
    font-size: 28px;
    font-weight: 700;
    letter-spacing: -0.02em;
  }}
  .brand-sub {{
    font-size: 13px;
    font-weight: 400;
    color: #888;
    margin-top: 4px;
    letter-spacing: 0.02em;
  }}
  .header-meta {{
    text-align: right;
    font-size: 12px;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }}

  /* Sections */
  .section {{
    margin-bottom: 64px;
  }}
  .section-label {{
    font-size: 11px;
    font-weight: 600;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 0.15em;
    margin-bottom: 16px;
  }}
  .section-title {{
    font-size: 20px;
    font-weight: 600;
    letter-spacing: -0.01em;
    margin-bottom: 24px;
    color: #0A0A0A;
  }}

  /* Strategy block */
  .strategy {{
    display: grid;
    grid-template-columns: 1.2fr 1fr;
    gap: 48px;
  }}
  .strategy-overview {{
    font-size: 15px;
    color: #333;
    line-height: 1.7;
  }}
  .strategy-goal {{
    margin-top: 20px;
    padding-top: 20px;
    border-top: 1px solid #EEEEEE;
    font-size: 13px;
    color: #5B7B9A;
    font-weight: 500;
  }}
  .params {{
    display: flex;
    flex-direction: column;
    gap: 0;
  }}
  .param-row {{
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    padding: 10px 0;
    border-bottom: 1px solid #F3F3F3;
    font-size: 13px;
  }}
  .param-row:last-child {{ border-bottom: none; }}
  .param-label {{ color: #888; }}
  .param-value {{
    color: #0A0A0A;
    font-weight: 500;
    font-feature-settings: 'tnum';
  }}

  /* Philosophy section */
  .philosophy-image {{
    display: flex;
    justify-content: center;
    padding: 24px 0;
    border: 1px solid #EEEEEE;
    border-radius: 4px;
    background: #FAFBFC;
  }}
  .philosophy-image img {{
    max-width: 100%;
    height: auto;
    max-height: 460px;
    border-radius: 4px;
  }}
  .philosophy-grid {{
    display: grid;
    grid-template-columns: 1fr 1.4fr 1fr;
    gap: 0;
    border: 1px solid #EEEEEE;
    border-radius: 4px;
    overflow: hidden;
  }}
  .phil-tile {{
    padding: 32px 28px;
    border-right: 1px solid #EEEEEE;
    display: flex;
    flex-direction: column;
    gap: 12px;
    position: relative;
  }}
  .phil-tile:last-child {{ border-right: none; }}
  .phil-iq {{
    font-size: 10px;
    font-weight: 600;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 0.15em;
  }}
  .phil-label {{
    font-size: 20px;
    font-weight: 700;
    letter-spacing: -0.02em;
    color: #0A0A0A;
  }}
  .phil-midwit .phil-label {{
    color: #B33030;
  }}
  .phil-quote {{
    font-size: 14px;
    color: #333;
    line-height: 1.55;
    font-style: italic;
  }}
  .phil-midwit .phil-quote {{
    color: #666;
    font-weight: 500;
  }}
  .phil-tail {{
    background: #FAFBFC;
  }}
  .phil-midwit {{
    background: #ffffff;
    border-left: 2px solid #B33030;
    border-right: 2px solid #B33030;
  }}

  /* Details / Schedule section */
  .schedule-intro {{
    font-size: 14px;
    color: #333;
    line-height: 1.7;
    margin-bottom: 20px;
    max-width: 760px;
  }}
  .schedule-grid {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0;
    border: 1px solid #EEEEEE;
    border-radius: 4px;
    overflow: hidden;
  }}
  .schedule-tile {{
    padding: 28px 28px;
    border-right: 1px solid #EEEEEE;
    display: flex;
    flex-direction: column;
    gap: 10px;
    background: #FAFBFC;
  }}
  .schedule-tile:last-child {{ border-right: none; }}
  .schedule-tile:nth-child(2) {{ background: #ffffff; }}
  .schedule-time {{
    font-size: 11px;
    font-weight: 600;
    color: #5B7B9A;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    font-feature-settings: 'tnum';
  }}
  .schedule-tag {{
    display: inline-block;
    margin-left: 6px;
    padding: 2px 6px;
    background: #EEEEEE;
    color: #666;
    border-radius: 3px;
    font-size: 9px;
    letter-spacing: 0.08em;
  }}
  .schedule-title {{
    font-size: 17px;
    font-weight: 700;
    letter-spacing: -0.01em;
    color: #0A0A0A;
  }}
  .schedule-body {{
    font-size: 13px;
    color: #444;
    line-height: 1.65;
  }}
  .schedule-footnote {{
    margin-top: 16px;
    padding: 12px 16px;
    background: #FAFBFC;
    border-left: 2px solid #5B7B9A;
    font-size: 12px;
    color: #666;
    line-height: 1.6;
  }}

  /* Stats grid */
  .stats-grid {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 0;
    border: 1px solid #EEEEEE;
    border-radius: 4px;
    overflow: hidden;
  }}
  .stat {{
    padding: 28px 24px;
    border-right: 1px solid #EEEEEE;
  }}
  .stat:last-child {{ border-right: none; }}
  .stat-label {{
    font-size: 10px;
    font-weight: 600;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    margin-bottom: 12px;
  }}
  .stat-value {{
    font-size: 28px;
    font-weight: 600;
    color: #0A0A0A;
    letter-spacing: -0.02em;
    font-feature-settings: 'tnum';
  }}
  .stat-sub {{
    font-size: 12px;
    color: #888;
    margin-top: 6px;
    font-feature-settings: 'tnum';
  }}

  /* Benchmark comparison table */
  .bench-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 14px;
  }}
  .bench-table th {{
    text-align: left;
    font-weight: 600;
    font-size: 11px;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    padding: 12px 16px;
    border-bottom: 1px solid #EEEEEE;
  }}
  .bench-table th.right {{ text-align: right; }}
  .bench-table td {{
    padding: 16px;
    border-bottom: 1px solid #F3F3F3;
    font-feature-settings: 'tnum';
  }}
  .bench-table td.right {{ text-align: right; }}
  .bench-table tr:last-child td {{ border-bottom: none; }}
  .bench-name {{ font-weight: 600; }}
  .bench-tag {{
    display: inline-block;
    font-size: 10px;
    background: #F3F3F3;
    color: #888;
    padding: 2px 6px;
    border-radius: 3px;
    margin-left: 8px;
    vertical-align: middle;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }}
  .bench-tag-us {{
    background: #5B7B9A;
    color: #fff;
  }}

  /* Positions table */
  .positions-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 14px;
  }}
  .positions-table th {{
    text-align: left;
    font-weight: 600;
    font-size: 10px;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    padding: 10px 14px;
    border-bottom: 1px solid #EEEEEE;
    white-space: nowrap;
  }}
  .positions-table th.right {{ text-align: right; }}
  .positions-table td {{
    padding: 12px 14px;
    border-bottom: 1px solid #F3F3F3;
    vertical-align: middle;
    font-feature-settings: 'tnum';
    white-space: nowrap;
  }}
  .positions-table td.right {{ text-align: right; }}
  .positions-table tbody tr:nth-child(even) {{
    background: #FAFBFC;
  }}
  .positions-table tbody tr:hover {{
    background: #F4F6F8;
  }}
  .pos-ticker {{
    font-weight: 700;
    font-size: 14px;
    letter-spacing: -0.01em;
    color: #0A0A0A;
  }}
  .positions-table tfoot tr.pos-total-row {{
    background: #ffffff !important;
  }}
  .positions-table tfoot tr.pos-total-row td {{
    border-top: 1px solid #D4D4D4;
    border-bottom: none;
    padding-top: 14px;
    padding-bottom: 14px;
    font-weight: 600;
    font-feature-settings: 'tnum';
  }}
  .positions-table tfoot tr.pos-total-row .pos-ticker {{
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: #888;
  }}
  .methodology {{
    margin-top: 16px;
    padding: 12px 16px;
    background: #FAFBFC;
    border-left: 2px solid #5B7B9A;
    font-size: 12px;
    color: #666;
    line-height: 1.7;
  }}
  .methodology strong {{
    color: #0A0A0A;
    font-weight: 600;
  }}
  .entry-date {{
    color: #555;
    font-size: 13px;
    font-feature-settings: 'tnum';
  }}
  .pos-desc {{
    white-space: normal !important;
    padding-left: 20px !important;
    border-left: 1px solid #EEEEEE;
    max-width: 380px;
    font-size: 12px;
    color: #666;
    line-height: 1.5;
  }}

  /* Value coloring */
  .pos {{ color: #1E7A3A; }}
  .neg {{ color: #B33030; }}
  .neu {{ color: #0A0A0A; }}

  .num {{ font-feature-settings: 'tnum'; }}

  /* Trade history */
  .trade-row {{
    display: grid;
    grid-template-columns: 120px 1fr;
    gap: 24px;
    padding: 20px 0;
    border-bottom: 1px solid #F3F3F3;
  }}
  .trade-row:last-child {{ border-bottom: none; }}
  .trade-date {{
    font-size: 12px;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    padding-top: 2px;
  }}
  .trade-main {{ }}
  .trade-line {{
    display: flex;
    align-items: baseline;
    gap: 12px;
    margin-bottom: 6px;
  }}
  .trade-side {{
    display: inline-block;
    font-size: 10px;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 3px;
    letter-spacing: 0.08em;
  }}
  .trade-side-buy {{ background: #E8F0E6; color: #1E7A3A; }}
  .trade-side-sell {{ background: #FCE8E6; color: #B33030; }}
  .trade-symbol {{
    font-weight: 700;
    font-size: 15px;
  }}
  .trade-meta {{
    font-size: 12px;
    color: #888;
    font-feature-settings: 'tnum';
  }}
  .trade-desc {{
    font-size: 13px;
    color: #555;
    margin-bottom: 6px;
  }}
  .trade-thesis {{
    font-size: 13px;
    color: #0A0A0A;
    padding: 10px 14px;
    border-left: 2px solid #5B7B9A;
    background: #FAFBFC;
    margin-top: 8px;
    line-height: 1.6;
  }}
  .empty {{
    font-size: 14px;
    color: #888;
    font-style: italic;
    padding: 24px 0;
  }}

  .cagr-caveat {{
    font-size: 11px;
    color: #B88330;
    margin-top: 6px;
    font-style: italic;
  }}

  /* Footer */
  .footer {{
    margin-top: 96px;
    padding-top: 32px;
    border-top: 1px solid #EEEEEE;
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 11px;
    color: #888;
    letter-spacing: 0.04em;
  }}
  .footer a {{
    color: #888;
    text-decoration: none;
  }}
  .footer a:hover {{ color: #5B7B9A; }}

  /* Responsive — tablet & phone */
  @media (max-width: 768px) {{
    .container {{ padding: 32px 20px 64px; }}
    .header {{ flex-direction: column; align-items: flex-start; gap: 16px; }}
    .header-meta {{ text-align: left; }}
    .strategy {{ grid-template-columns: 1fr; gap: 32px; }}
    .philosophy-grid {{ grid-template-columns: 1fr; }}
    .phil-tile {{ border-right: none; border-bottom: 1px solid #EEEEEE; }}
    .phil-tile:last-child {{ border-bottom: none; }}
    .phil-midwit {{ border-left: 2px solid #B33030; border-right: 2px solid #B33030; }}
    .schedule-grid {{ grid-template-columns: 1fr; }}
    .schedule-tile {{ border-right: none; border-bottom: 1px solid #EEEEEE; padding: 22px 20px; }}
    .schedule-tile:last-child {{ border-bottom: none; }}
    .stats-grid {{ grid-template-columns: repeat(2, 1fr); }}
    .stat {{
      padding: 22px 18px;
      border-right: 1px solid #EEEEEE;
      border-bottom: 1px solid #EEEEEE;
    }}
    .stat:nth-child(2n) {{ border-right: none; }}
    .stat:nth-last-child(-n+2) {{ border-bottom: none; }}
    .stat-value {{ font-size: 24px; }}

    /* Benchmark table → card-style rows */
    .bench-table thead {{ display: none; }}
    .bench-table tbody tr {{
      display: block;
      padding: 14px 0;
      border-bottom: 1px solid #EEEEEE;
    }}
    .bench-table tbody tr:last-child {{ border-bottom: none; }}
    .bench-table td {{
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      padding: 5px 0;
      border: none;
      font-size: 13px;
    }}
    .bench-table td::before {{
      color: #888;
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .bench-table td:first-child {{
      display: block;
      padding: 0 0 8px 0;
      margin-bottom: 4px;
      border-bottom: 1px solid #F3F3F3;
      font-size: 15px;
    }}
    .bench-table td:nth-of-type(2)::before {{ content: "1-Day"; }}
    .bench-table td:nth-of-type(3)::before {{ content: "Total Return"; }}
    .bench-table td:nth-of-type(4)::before {{ content: "vs. GG"; }}

    /* Positions table → card-style rows with pseudo-labels */
    .positions-table thead {{ display: none; }}
    .positions-table tbody tr,
    .positions-table tfoot tr {{
      display: block;
      padding: 16px 14px;
      border-bottom: 1px solid #EEEEEE;
      background: #ffffff !important;
    }}
    .positions-table tfoot tr.pos-total-row {{
      border-top: 2px solid #0A0A0A;
      margin-top: 4px;
    }}
    .positions-table tr td:empty {{ display: none; }}
    .positions-table tbody tr:nth-child(even) {{
      background: #FAFBFC !important;
    }}
    .positions-table td {{
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      padding: 5px 0;
      border: none;
      font-size: 13px;
      white-space: normal;
    }}
    .positions-table td::before {{
      color: #888;
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      flex-shrink: 0;
      margin-right: 12px;
    }}
    .positions-table tbody td:nth-of-type(2)::before {{ content: "Entry"; }}
    .positions-table tbody td:nth-of-type(3)::before {{ content: "Avg Price"; }}
    .positions-table tbody td:nth-of-type(4)::before {{ content: "Last Price"; }}
    .positions-table tbody td:nth-of-type(5)::before {{ content: "Shares"; }}
    .positions-table tbody td:nth-of-type(6)::before {{ content: "Value"; }}
    .positions-table tbody td:nth-of-type(7)::before {{ content: "% Port."; }}
    .positions-table tbody td:nth-of-type(8)::before {{ content: "Total Return"; }}
    .positions-table tbody td:nth-of-type(9)::before {{ content: "1-Day"; }}
    .positions-table tfoot td:nth-of-type(6)::before {{ content: "Value"; }}
    .positions-table tfoot td:nth-of-type(7)::before {{ content: "% Port."; }}
    .positions-table tfoot td:nth-of-type(8)::before {{ content: "Total Return"; }}
    .positions-table tfoot td:nth-of-type(9)::before {{ content: "1-Day"; }}
    .positions-table td.pos-ticker {{
      display: block;
      padding: 0 0 10px 0;
      margin-bottom: 8px;
      border-bottom: 1px solid #F3F3F3;
      font-size: 17px;
    }}
    .positions-table td.pos-ticker::before {{ content: none; }}
    .positions-table tfoot tr.pos-total-row .pos-ticker {{
      font-size: 12px;
      letter-spacing: 0.12em;
    }}
    .positions-table td.pos-desc {{
      display: block;
      padding: 10px 0 0 0 !important;
      border-left: none;
      border-top: 1px solid #F3F3F3;
      margin-top: 8px;
      max-width: none;
    }}
    .positions-table td.pos-desc::before {{ content: none; }}

    .methodology {{ font-size: 11px; padding: 10px 12px; }}
    .trade-row {{ grid-template-columns: 1fr; gap: 8px; padding: 16px 0; }}
    .trade-line {{ flex-wrap: wrap; }}
    .footer {{ flex-direction: column; align-items: flex-start; gap: 8px; }}
  }}

  /* Small phones */
  @media (max-width: 480px) {{
    .container {{ padding: 24px 16px 48px; }}
    .brand {{ font-size: 22px; }}
    .brand-sub {{ font-size: 12px; }}
    .section {{ margin-bottom: 48px; }}
    .section-title {{ font-size: 17px; }}
    .stat-value {{ font-size: 20px; }}
    .stat {{ padding: 18px 14px; }}
    .phil-tile {{ padding: 24px 20px; }}
    .phil-label {{ font-size: 17px; }}
    .phil-quote {{ font-size: 13px; }}
  }}
</style>
</head>
<body>

<div class="container">

  <!-- Header -->
  <div class="header">
    <div>
      <div class="brand">GG Capital</div>
      <div class="brand-sub">{STRATEGY_COPY['tagline']}</div>
    </div>
    <div class="header-meta">
      Updated {now_str}<br>
      Inception · {inception}
    </div>
  </div>

  <!-- Strategy -->
  <div class="section">
    <div class="section-label">Strategy</div>
    <div class="strategy">
      <div class="strategy-overview">
        {STRATEGY_COPY['overview']}
        <div class="strategy-goal">{STRATEGY_COPY['goal']}</div>
      </div>
      <div class="params">
        {params_html}
      </div>
    </div>
  </div>

  <!-- Philosophy (bell-curve meme) -->
  <div class="section">
    <div class="section-label">Philosophy</div>
    <div class="section-title">Both tails of the IQ bell curve agree.</div>
    {philosophy_html}
  </div>

  <!-- Details (daily schedule + automation) -->
  <div class="section">
    <div class="section-label">Details</div>
    <div class="section-title">How the agent runs</div>
    <div class="schedule-intro">{STRATEGY_COPY['schedule_intro']}</div>
    <div class="schedule-grid">
      {schedule_tiles_html}
    </div>
    <div class="schedule-footnote">
      <strong>Hard rails (cannot be overridden):</strong> max 20% per position, 35% per sector,
      40% total options exposure, 10% per single options play. No margin, no naked options, no shorts.
      Options stop-loss at 80% loss of premium.
    </div>
  </div>

  <!-- Headline Stats -->
  <div class="section">
    <div class="section-label">Performance</div>
    <div class="stats-grid">
      <div class="stat">
        <div class="stat-label">Portfolio Value</div>
        <div class="stat-value">${account['equity']:,.0f}</div>
        <div class="stat-sub">${account['cash']:,.0f} cash</div>
      </div>
      <div class="stat">
        <div class="stat-label">Total Return · Inception</div>
        <div class="stat-value {pos_color(total_pct)}">{_fmt_pct(total_pct)}</div>
        <div class="stat-sub {pos_color(total_pct)}">{_fmt_dollars(total_dollars, show_sign=True)}</div>
      </div>
      <div class="stat">
        <div class="stat-label">1-Day Return</div>
        <div class="stat-value {pos_color(day_pct)}">{_fmt_pct(day_pct)}</div>
        <div class="stat-sub {pos_color(day_pct)}">{_fmt_dollars(day_dollars, show_sign=True)}</div>
      </div>
      <div class="stat">
        <div class="stat-label">CAGR · Annualized</div>
        <div class="stat-value {pos_color(cagr)}">{gg_cagr_display}</div>
        <div class="stat-sub">{days_since} days of data</div>
      </div>
    </div>
    {cagr_note}
  </div>

  <!-- Benchmark Comparison -->
  <div class="section">
    <div class="section-label">Benchmark Comparison</div>
    <div class="section-title">Since inception ({inception})</div>
    <table class="bench-table">
      <thead>
        <tr>
          <th>Strategy</th>
          <th class="right">1-Day</th>
          <th class="right">Total Return</th>
          <th class="right">GG Excess Return / Underperformance</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><span class="bench-name">GG Capital</span> <span class="bench-tag bench-tag-us">Us</span></td>
          <td class="right num {pos_color(day_pct)}">{_fmt_pct(day_pct)}</td>
          <td class="right num {pos_color(total_pct)}">{_fmt_pct(total_pct)}</td>
          <td class="right num neu">—</td>
        </tr>
        <tr>
          <td><span class="bench-name">S&amp;P 500</span> <span class="bench-tag">SPY</span></td>
          <td class="right num {pos_color(spy_day)}">{_fmt_pct(spy_day)}</td>
          <td class="right num {pos_color(spy_ret)}">{_fmt_pct(spy_ret)}</td>
          <td class="right num {alpha_spy_class}">{alpha_spy_text}</td>
        </tr>
        <tr>
          <td><span class="bench-name">Nasdaq 100</span> <span class="bench-tag">QQQ</span></td>
          <td class="right num {pos_color(qqq_day)}">{_fmt_pct(qqq_day)}</td>
          <td class="right num {pos_color(qqq_ret)}">{_fmt_pct(qqq_ret)}</td>
          <td class="right num {alpha_qqq_class}">{alpha_qqq_text}</td>
        </tr>
      </tbody>
    </table>
  </div>

  <!-- Positions -->
  <div class="section">
    <div class="section-label">Holdings</div>
    <div class="section-title">{len(positions_sorted)} positions · ${total_invested:,.0f} invested</div>
    <table class="positions-table">
      <thead>
        <tr>
          <th>Ticker</th>
          <th>Entry</th>
          <th class="right">Avg Price</th>
          <th class="right">Last Price</th>
          <th class="right">Shares</th>
          <th class="right">Value</th>
          <th class="right">% Port.</th>
          <th class="right">Total Return</th>
          <th class="right">1-Day</th>
          <th>Business</th>
        </tr>
      </thead>
      <tbody>
        {pos_rows}
      </tbody>
      <tfoot>
        <tr class="pos-total-row">
          <td class="pos-ticker">TOTAL</td>
          <td></td>
          <td></td>
          <td></td>
          <td></td>
          <td class="right num">${account['equity']:,.0f}</td>
          <td class="right num">100.0%</td>
          <td class="right num {pos_color(total_pct)}">{_fmt_pct_1dp(total_pct)}</td>
          <td class="right num {pos_color(day_pct)}">{_fmt_pct_1dp(day_pct)}</td>
          <td></td>
        </tr>
      </tfoot>
    </table>
    <div class="methodology">
      <strong>Total Return</strong> = (Last Price − Avg Price) ÷ Avg Price.
      <strong>Last Price</strong> is the most recent trade during market hours, or the official close after 4:00 PM ET.
      <strong>1-Day</strong> is Last Price vs. prior trading day&apos;s close.
    </div>
  </div>

  <!-- Trade History -->
  <div class="section">
    <div class="section-label">Activity</div>
    <div class="section-title">Trade history &amp; rationale</div>
    <div class="trade-feed">
      {trade_feed_html}
    </div>
  </div>

  <!-- Footer -->
  <div class="footer">
    <div>GG Capital · AI-managed paper trading strategy · Not investment advice.</div>
    <div><a href="https://github.com/anishkmitra/ggcapital">github.com/anishkmitra/ggcapital</a></div>
  </div>

</div>

</body>
</html>
"""
    return html


def generate_report() -> tuple[str, str]:
    """Generate the full dashboard. Returns (subject, html)."""
    b = Broker()
    account = b.get_account()
    positions = b.get_positions()
    last_equity = _get_last_equity()

    stats = compute_portfolio_stats(account["equity"], last_equity)
    if "error" in stats:
        return "GG Capital — Error", f"<p>Error computing stats: {stats['error']}</p>"

    trade_history = _extract_trade_history()
    html = render_dashboard(stats, positions, trade_history, account)

    total_pct = stats["total_return_pct"]
    total_dollars = stats["total_return_dollars"]
    sign = "+" if total_dollars >= 0 else ""
    date_str = datetime.now().strftime("%B %d, %Y")
    subject = f"GG Capital · {date_str} · {sign}${total_dollars:,.0f} ({_fmt_pct(total_pct)})"

    return subject, html


if __name__ == "__main__":
    subject, html = generate_report()
    print(f"Subject: {subject}")
    print(f"HTML length: {len(html):,} chars")

    out_path = Path(os.path.dirname(os.path.abspath(__file__))) / "latest_report.html"
    out_path.write_text(html)
    print(f"Report written to {out_path}")
