#!/usr/bin/env python3
"""Trading agent main entry point."""

import sys
import json
from datetime import datetime
from agent import TradingAgent


def print_header():
    print("=" * 60)
    print("  TRADING AGENT")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)


def cmd_status(agent: TradingAgent):
    """Show current portfolio status."""
    state = agent.strategy.get_portfolio_state()
    account = state["account"]
    positions = state["positions"]

    print(f"\n{'─' * 40}")
    print(f"  Equity:     ${account['equity']:>12,.2f}")
    print(f"  Cash:       ${account['cash']:>12,.2f}")
    print(f"  Day Trades: {account['day_trade_count']}")
    print(f"  PDT Flag:   {account['pattern_day_trader']}")
    print(f"{'─' * 40}")

    if positions:
        print(f"\n  {'Symbol':<10} {'Value':>10} {'P&L':>10} {'P&L%':>8}")
        print(f"  {'─' * 38}")
        for p in positions:
            print(f"  {p['symbol']:<10} ${p['market_value']:>9,.2f} ${p['unrealized_pl']:>9,.2f} {p['unrealized_pl_pct']:>7.1%}")
    else:
        print("\n  No open positions.")
    print()


def cmd_analyze(agent: TradingAgent):
    """Have the agent analyze market and suggest/execute trades."""
    print("\n[Agent] Analyzing market and portfolio...\n")
    response = agent.analyze_and_trade()
    print(f"\n{response}\n")


def cmd_review(agent: TradingAgent):
    """Have the agent review existing positions."""
    print("\n[Agent] Reviewing positions...\n")
    response = agent.review_positions()
    print(f"\n{response}\n")


def cmd_scan(agent: TradingAgent):
    """Have the agent scan the market without trading."""
    print("\n[Agent] Scanning market...\n")
    response = agent.scan_market()
    print(f"\n{response}\n")


def cmd_chat(agent: TradingAgent, message: str):
    """Free-form chat with the agent."""
    print(f"\n[Agent] Thinking...\n")
    response = agent.run(message)
    print(f"\n{response}\n")


def main():
    print_header()

    agent = TradingAgent()

    # Quick account check
    try:
        account = agent.broker.get_account()
        print(f"\n  Connected to Alpaca ({'PAPER' if 'paper' in str(agent.broker.trading_client) else 'LIVE'})")
        print(f"  Account equity: ${account['equity']:,.2f}\n")
    except Exception as e:
        print(f"\n  ERROR connecting to Alpaca: {e}")
        print("  Make sure your API keys are set in .env")
        sys.exit(1)

    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "status":
            cmd_status(agent)
        elif command == "analyze":
            cmd_analyze(agent)
        elif command == "review":
            cmd_review(agent)
        elif command == "scan":
            cmd_scan(agent)
        elif command == "chat":
            msg = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "What should we do today?"
            cmd_chat(agent, msg)
        else:
            print(f"Unknown command: {command}")
            print("Usage: python main.py [status|analyze|review|scan|chat <message>]")
        return

    # Interactive mode
    print("Commands: status | analyze | review | scan | chat <msg> | quit\n")
    while True:
        try:
            user_input = input(">> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("Goodbye!")
            break
        elif user_input.lower() == "status":
            cmd_status(agent)
        elif user_input.lower() == "analyze":
            cmd_analyze(agent)
        elif user_input.lower() == "review":
            cmd_review(agent)
        elif user_input.lower() == "scan":
            cmd_scan(agent)
        elif user_input.lower().startswith("chat "):
            cmd_chat(agent, user_input[5:])
        else:
            # Treat any other input as a chat message
            cmd_chat(agent, user_input)


if __name__ == "__main__":
    main()
