import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env", override=True)

# Alpaca
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
TRADING_MODE = os.getenv("TRADING_MODE", "paper")  # "paper" or "live"

# Anthropic
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Strategy
INITIAL_CAPITAL = float(os.getenv("INITIAL_CAPITAL", "15000"))
MAX_POSITION_PCT = float(os.getenv("MAX_POSITION_PCT", "0.20"))  # Max 20% of portfolio in one position
SELL_THRESHOLD_PCT = float(os.getenv("SELL_THRESHOLD_PCT", "0.50"))  # Only sell at 50%+ gain

# Risk controls
MAX_OPTIONS_PCT = 0.40  # Max 40% of portfolio in options
MAX_SINGLE_OPTION_PCT = 0.10  # Max 10% of portfolio in a single options play
STOP_LOSS_OPTIONS_PCT = 0.80  # Cut options losers at 80% loss of premium

# Screening criteria
MIN_BETA = 1.3  # Only high-beta stocks
MIN_AVG_VOLUME = 2_000_000  # Minimum average daily volume
MIN_VOLATILITY_PCT = 0.03  # Minimum daily volatility (3%+ avg daily range)
MAX_SECTOR_ALLOCATION_PCT = 0.35  # Max 35% in any one sector (sector neutral-ish)
EARNINGS_LOOKFORWARD_DAYS = 14  # Flag stocks with earnings in next 2 weeks

# Sectors to track
SECTORS = [
    "Technology",
    "Software",
    "Energy",
    "Financials",
    "Healthcare",
    "Consumer Discretionary",
    "Industrials",
    "Materials",
    "Communication Services",
    "Utilities",
    "Real Estate",
    "Consumer Staples",
]

# Never do these
ALLOW_MARGIN = False
ALLOW_NAKED_OPTIONS = False
ALLOW_SHORT_SELLING = False
