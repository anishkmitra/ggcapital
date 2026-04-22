#!/usr/bin/env python3
"""Generate daily PnL and actions summary report."""

import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'), override=True)

from broker import Broker


def generate_report() -> tuple[str, str]:
    """Generate report and return (subject, html_body)."""
    b = Broker()
    account = b.get_account()
    positions = b.get_positions()
    orders_today = b.get_orders('closed')

    total_cost = sum(p['cost_basis'] for p in positions)
    total_mv = sum(p['market_value'] for p in positions)
    total_pnl = total_mv - total_cost
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0

    # Get benchmark data
    try:
        spy = b.get_snapshot('SPY')
        spy_day = (spy['daily_bar']['close'] - spy['prev_daily_bar']['close']) / spy['prev_daily_bar']['close'] * 100
        spy_close = spy['daily_bar']['close']
    except:
        spy_day = 0
        spy_close = 0

    try:
        qqq = b.get_snapshot('QQQ')
        qqq_day = (qqq['daily_bar']['close'] - qqq['prev_daily_bar']['close']) / qqq['prev_daily_bar']['close'] * 100
        qqq_close = qqq['daily_bar']['close']
    except:
        qqq_day = 0
        qqq_close = 0

    date_str = datetime.now().strftime('%B %d, %Y')
    pnl_emoji = "+" if total_pnl >= 0 else ""
    pnl_color = "#22c55e" if total_pnl >= 0 else "#ef4444"

    # Build positions table rows
    positions_sorted = sorted(positions, key=lambda p: p['unrealized_pl_pct'], reverse=True)
    position_rows = ""
    for p in positions_sorted:
        pl_color = "#22c55e" if p['unrealized_pl'] >= 0 else "#ef4444"
        position_rows += f"""
        <tr>
            <td style="padding:8px 12px;border-bottom:1px solid #eee;font-weight:600;">{p['symbol']}</td>
            <td style="padding:8px 12px;border-bottom:1px solid #eee;text-align:right;">${p['avg_entry_price']:,.2f}</td>
            <td style="padding:8px 12px;border-bottom:1px solid #eee;text-align:right;">${p['current_price']:,.2f}</td>
            <td style="padding:8px 12px;border-bottom:1px solid #eee;text-align:right;">${p['market_value']:,.2f}</td>
            <td style="padding:8px 12px;border-bottom:1px solid #eee;text-align:right;color:{pl_color};font-weight:600;">
                ${p['unrealized_pl']:,.2f} ({p['unrealized_pl_pct']:+.1%})
            </td>
        </tr>"""

    # Build orders section
    orders_section = ""
    if orders_today:
        orders_section = """
        <h2 style="color:#1e293b;font-size:18px;margin-top:24px;">Trades Executed Today</h2>
        <table style="width:100%;border-collapse:collapse;font-size:14px;">
            <tr style="background:#f1f5f9;">
                <th style="padding:8px 12px;text-align:left;">Symbol</th>
                <th style="padding:8px 12px;text-align:left;">Side</th>
                <th style="padding:8px 12px;text-align:right;">Filled Price</th>
                <th style="padding:8px 12px;text-align:left;">Status</th>
            </tr>"""
        for o in orders_today[:10]:
            side_color = "#22c55e" if "BUY" in str(o['side']) else "#ef4444"
            side_label = "BUY" if "BUY" in str(o['side']) else "SELL"
            filled = o['filled_avg_price'] or 'N/A'
            orders_section += f"""
            <tr>
                <td style="padding:8px 12px;border-bottom:1px solid #eee;font-weight:600;">{o['symbol']}</td>
                <td style="padding:8px 12px;border-bottom:1px solid #eee;color:{side_color};font-weight:600;">{side_label}</td>
                <td style="padding:8px 12px;border-bottom:1px solid #eee;text-align:right;">${filled}</td>
                <td style="padding:8px 12px;border-bottom:1px solid #eee;">{str(o['status']).replace('OrderStatus.','')}</td>
            </tr>"""
        orders_section += "</table>"

    # Read latest log file for agent actions
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
    latest_actions = ""
    try:
        log_files = sorted([f for f in os.listdir(log_dir) if f.endswith('.log')], reverse=True)
        if log_files:
            with open(os.path.join(log_dir, log_files[0]), 'r') as f:
                log_content = f.read()
            # Extract the summary section if present
            if '## SUMMARY' in log_content:
                summary_start = log_content.index('## SUMMARY')
                latest_actions = log_content[summary_start:]
            elif '# EXECUTED' in log_content:
                summary_start = log_content.index('# EXECUTED')
                latest_actions = log_content[summary_start:]
    except:
        pass

    actions_section = ""
    if latest_actions:
        actions_html = latest_actions.replace('\n', '<br>').replace('##', '<b>').replace('**', '<b>')
        actions_section = f"""
        <h2 style="color:#1e293b;font-size:18px;margin-top:24px;">Agent Actions Summary</h2>
        <div style="background:#f8fafc;padding:16px;border-radius:8px;font-size:13px;font-family:monospace;white-space:pre-wrap;">{actions_html}</div>
        """

    subject = f"Trading Bot | {date_str} | P&L: {pnl_emoji}${abs(total_pnl):,.0f} ({total_pnl_pct:+.1f}%)"

    html = f"""
    <div style="max-width:640px;margin:0 auto;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#1e293b;">

        <div style="background:linear-gradient(135deg,#0f172a,#1e3a5f);padding:24px 32px;border-radius:12px 12px 0 0;">
            <h1 style="color:white;margin:0;font-size:20px;">AI Trading Bot — Daily Report</h1>
            <p style="color:#94a3b8;margin:4px 0 0 0;font-size:14px;">{date_str}</p>
        </div>

        <div style="background:white;padding:24px 32px;border:1px solid #e2e8f0;border-top:none;">

            <div style="display:flex;gap:16px;margin-bottom:24px;">
                <div style="flex:1;background:#f8fafc;padding:16px;border-radius:8px;text-align:center;">
                    <div style="font-size:12px;color:#64748b;text-transform:uppercase;">Portfolio Value</div>
                    <div style="font-size:24px;font-weight:700;color:#0f172a;">${account['equity']:,.2f}</div>
                </div>
                <div style="flex:1;background:#f8fafc;padding:16px;border-radius:8px;text-align:center;">
                    <div style="font-size:12px;color:#64748b;text-transform:uppercase;">Total P&L</div>
                    <div style="font-size:24px;font-weight:700;color:{pnl_color};">{pnl_emoji}${abs(total_pnl):,.2f}</div>
                    <div style="font-size:14px;color:{pnl_color};">({total_pnl_pct:+.1f}%)</div>
                </div>
                <div style="flex:1;background:#f8fafc;padding:16px;border-radius:8px;text-align:center;">
                    <div style="font-size:12px;color:#64748b;text-transform:uppercase;">Cash</div>
                    <div style="font-size:24px;font-weight:700;color:#0f172a;">${account['cash']:,.2f}</div>
                </div>
            </div>

            <div style="background:#f8fafc;padding:12px 16px;border-radius:8px;margin-bottom:24px;font-size:13px;display:flex;gap:24px;">
                <span>SPY: ${spy_close:,.2f} ({spy_day:+.2f}%)</span>
                <span>QQQ: ${qqq_close:,.2f} ({qqq_day:+.2f}%)</span>
                <span>Day Trades: {account['day_trade_count']}</span>
            </div>

            <h2 style="color:#1e293b;font-size:18px;margin-top:0;">Positions</h2>
            <table style="width:100%;border-collapse:collapse;font-size:14px;">
                <tr style="background:#f1f5f9;">
                    <th style="padding:8px 12px;text-align:left;">Symbol</th>
                    <th style="padding:8px 12px;text-align:right;">Entry</th>
                    <th style="padding:8px 12px;text-align:right;">Current</th>
                    <th style="padding:8px 12px;text-align:right;">Value</th>
                    <th style="padding:8px 12px;text-align:right;">P&L</th>
                </tr>
                {position_rows}
                <tr style="background:#f1f5f9;font-weight:700;">
                    <td style="padding:8px 12px;">TOTAL</td>
                    <td style="padding:8px 12px;text-align:right;">${total_cost:,.2f}</td>
                    <td style="padding:8px 12px;text-align:right;"></td>
                    <td style="padding:8px 12px;text-align:right;">${total_mv:,.2f}</td>
                    <td style="padding:8px 12px;text-align:right;color:{pnl_color};">${total_pnl:,.2f} ({total_pnl_pct:+.1f}%)</td>
                </tr>
            </table>

            {orders_section}
            {actions_section}

        </div>

        <div style="background:#f8fafc;padding:16px 32px;border-radius:0 0 12px 12px;border:1px solid #e2e8f0;border-top:none;text-align:center;">
            <p style="color:#94a3b8;font-size:12px;margin:0;">AI Trading Bot — Automated Report</p>
        </div>
    </div>
    """

    return subject, html


if __name__ == "__main__":
    subject, html = generate_report()
    print(f"Subject: {subject}")
    print(f"\nHTML length: {len(html)} chars")
    # Write to file for inspection
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'latest_report.html'), 'w') as f:
        f.write(html)
    print("Report written to latest_report.html")
