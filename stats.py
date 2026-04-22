"""Portfolio statistics: returns, CAGR, benchmark comparison."""

import math
from datetime import datetime, timedelta
import requests
import yfinance as yf

import config


def _alpaca_headers():
    return {
        "APCA-API-KEY-ID": config.ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": config.ALPACA_SECRET_KEY,
    }


def _alpaca_base_url():
    return (
        "https://api.alpaca.markets"
        if config.TRADING_MODE == "live"
        else "https://paper-api.alpaca.markets"
    )


def get_portfolio_history(period: str = "1M", timeframe: str = "1D") -> dict:
    """Fetch daily portfolio equity history from Alpaca."""
    resp = requests.get(
        f"{_alpaca_base_url()}/v2/account/portfolio/history",
        headers=_alpaca_headers(),
        params={"period": period, "timeframe": timeframe},
    )
    if resp.status_code != 200:
        return {"error": f"HTTP {resp.status_code}: {resp.text}"}
    return resp.json()


def find_inception_date(history: dict) -> tuple[datetime, float] | None:
    """
    Inception = the first day equity actually moved (i.e. first day of trading).
    We use the day *before* the first equity change as the baseline so that
    day's full return is captured.
    Returns (inception_datetime, starting_equity).
    """
    equity = history.get("equity", [])
    timestamps = history.get("timestamp", [])

    # Find first non-zero equity value (account funded)
    funded_idx = None
    for i, eq in enumerate(equity):
        if eq > 0:
            funded_idx = i
            break
    if funded_idx is None:
        return None

    # Now walk forward from funded_idx to find the first day equity changed
    baseline_eq = equity[funded_idx]
    first_change_idx = None
    for i in range(funded_idx + 1, len(equity)):
        if equity[i] != baseline_eq and equity[i] > 0:
            first_change_idx = i
            break

    if first_change_idx is None:
        # No trading has happened yet — fall back to funding date
        return datetime.fromtimestamp(timestamps[funded_idx]), baseline_eq

    # Inception = the trading day on which equity first moved.
    # Baseline = the equity value going INTO that day (i.e. prior day's close).
    inception_ts = timestamps[first_change_idx]
    starting_equity = equity[first_change_idx - 1]
    return datetime.fromtimestamp(inception_ts), starting_equity


def get_benchmark_return(symbol: str, start_date: datetime, end_date: datetime = None) -> dict:
    """Get benchmark return between two dates using yfinance."""
    if end_date is None:
        end_date = datetime.now()

    try:
        ticker = yf.Ticker(symbol)
        # Pad end date by 1 day to ensure we capture today
        hist = ticker.history(
            start=start_date.strftime("%Y-%m-%d"),
            end=(end_date + timedelta(days=1)).strftime("%Y-%m-%d"),
        )
        if hist.empty:
            return {"error": f"No data for {symbol}"}

        start_price = float(hist["Close"].iloc[0])
        end_price = float(hist["Close"].iloc[-1])
        if start_price <= 0:
            return {"error": f"Invalid start price for {symbol}"}
        total_return = (end_price - start_price) / start_price

        # 1-day return (today vs yesterday)
        if len(hist) >= 2:
            prev_price = float(hist["Close"].iloc[-2])
            day_return = (end_price - prev_price) / prev_price if prev_price > 0 else 0.0
        else:
            day_return = 0.0

        return {
            "symbol": symbol,
            "start_date": hist.index[0].strftime("%Y-%m-%d"),
            "end_date": hist.index[-1].strftime("%Y-%m-%d"),
            "start_price": round(start_price, 2),
            "end_price": round(end_price, 2),
            "total_return": total_return,
            "day_return": day_return,
            "days_observed": len(hist),
        }
    except Exception as e:
        return {"error": str(e)}


def compute_cagr(total_return: float, days: int) -> float:
    """Compute annualized return (CAGR). Needs >= 1 day."""
    if days < 1:
        return 0.0
    years = days / 365.25
    if years <= 0:
        return 0.0
    try:
        return (1 + total_return) ** (1 / years) - 1
    except (ValueError, OverflowError):
        return 0.0


def compute_portfolio_stats(current_equity: float, last_equity: float = None) -> dict:
    """
    Compute the headline portfolio statistics:
    - Total return since inception (%, $)
    - 1-day return (%, $)
    - CAGR (annualized)
    - SPY, QQQ comparison over same period
    """
    history = get_portfolio_history(period="3M", timeframe="1D")
    if "error" in history:
        return history

    inception = find_inception_date(history)
    if inception is None:
        return {"error": "Could not determine inception date"}

    inception_date, starting_equity = inception
    now = datetime.now()
    days_since_inception = (now - inception_date).days

    # Total return since inception. find_inception_date guarantees
    # starting_equity > 0 when it returns a funded baseline, but guard
    # explicitly — a 0 here would otherwise raise ZeroDivisionError.
    if starting_equity <= 0:
        return {"error": "Starting equity is zero; cannot compute returns."}
    total_return_pct = (current_equity - starting_equity) / starting_equity
    total_return_dollars = current_equity - starting_equity

    # 1-day return
    if last_equity and last_equity > 0:
        day_return_pct = (current_equity - last_equity) / last_equity
        day_return_dollars = current_equity - last_equity
    else:
        # Fallback: use the portfolio history to find previous day's equity
        equity = history.get("equity", [])
        nonzero_equity = [e for e in equity if e > 0]
        if len(nonzero_equity) >= 2 and nonzero_equity[-2] > 0:
            prev_equity = nonzero_equity[-2]
            day_return_pct = (current_equity - prev_equity) / prev_equity
            day_return_dollars = current_equity - prev_equity
        else:
            day_return_pct = 0.0
            day_return_dollars = 0.0

    # CAGR
    cagr = compute_cagr(total_return_pct, days_since_inception)

    # Benchmarks
    spy = get_benchmark_return("SPY", inception_date, now)
    qqq = get_benchmark_return("QQQ", inception_date, now)

    # Alpha (simple: our return - benchmark return)
    alpha_vs_spy = total_return_pct - spy.get("total_return", 0) if "error" not in spy else None
    alpha_vs_qqq = total_return_pct - qqq.get("total_return", 0) if "error" not in qqq else None

    return {
        "inception_date": inception_date.strftime("%Y-%m-%d"),
        "days_since_inception": days_since_inception,
        "starting_equity": starting_equity,
        "current_equity": current_equity,
        "total_return_pct": total_return_pct,
        "total_return_dollars": total_return_dollars,
        "day_return_pct": day_return_pct,
        "day_return_dollars": day_return_dollars,
        "cagr": cagr,
        "benchmarks": {
            "SPY": {
                "total_return_pct": spy.get("total_return", 0),
                "day_return_pct": spy.get("day_return", 0),
                "cagr": compute_cagr(spy.get("total_return", 0), days_since_inception),
                "error": spy.get("error"),
            },
            "QQQ": {
                "total_return_pct": qqq.get("total_return", 0),
                "day_return_pct": qqq.get("day_return", 0),
                "cagr": compute_cagr(qqq.get("total_return", 0), days_since_inception),
                "error": qqq.get("error"),
            },
        },
        "alpha": {
            "vs_spy": alpha_vs_spy,
            "vs_qqq": alpha_vs_qqq,
        },
    }


if __name__ == "__main__":
    import json
    from dotenv import load_dotenv
    import os
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"), override=True)

    from broker import Broker
    b = Broker()
    account = b.get_account()

    # Get last_equity from Alpaca for accurate day return
    import requests
    resp = requests.get(
        f"{_alpaca_base_url()}/v2/account",
        headers=_alpaca_headers(),
    )
    acct_full = resp.json()
    last_equity = float(acct_full.get("last_equity", 0))

    stats = compute_portfolio_stats(account["equity"], last_equity)
    print(json.dumps(stats, indent=2, default=str))
