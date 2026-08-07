collector.py        → Collects market data
validator.py        → Filters scams and invalid tokens
scorer.py           → Calculates the Alpha Score
analyst.py          → AI analysis and reasoning
decision.py         → Trade Candidate / Wait / No Trade
notifier.py         → Sends alerts
scheduler.py        → Runs every few minutes


"""
Configuration Loader
Solana Utility Scanner
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv

# Project root
ROOT_DIR = Path(__file__).resolve().parent.parent

# Load .env
load_dotenv(ROOT_DIR / ".env")

# Load settings.json
SETTINGS_PATH = ROOT_DIR / "data" / "settings.json"

with open(SETTINGS_PATH, "r") as file:
    SETTINGS = json.load(file)


class Config:
    # API Keys
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    BIRDEYE_API_KEY = os.getenv("BIRDEYE_API_KEY")
    HELIUS_API_KEY = os.getenv("HELIUS_API_KEY")

    # Notifications
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

    # Scanner Settings
    ALERT_SCORE = SETTINGS["alert_score"]
    SCAN_INTERVAL = SETTINGS["scan_interval"]

    # Filters
    MIN_MARKET_CAP = SETTINGS["market_cap"]["minimum"]
    MAX_MARKET_CAP = SETTINGS["market_cap"]["maximum"]

    MIN_LIQUIDITY = SETTINGS["liquidity"]["minimum"]
    MIN_VOLUME = SETTINGS["volume"]["minimum_24h"]
    MIN_HOLDERS = SETTINGS["holders"]["minimum"]

    MIN_CONFIDENCE = SETTINGS["confidence"]["minimum"]
