"""
╔══════════════════════════════════════════════════════════════════════════════╗
║          GBPUSD ADVANCED SCALPING BOT — MetaTrader 5 (Python API)           ║
║          Strategy: Break & Retest | Supply & Demand | EMA/SMA Zones         ║
║          Author: Generated Trading Bot | Platform: MT5 Python API           ║
╚══════════════════════════════════════════════════════════════════════════════╝

REQUIREMENTS:
    pip install MetaTrader5 pandas numpy requests pytz

SETUP:
    1. Install MetaTrader 5 terminal and log in to your broker account.
    2. Install the required Python packages above.
    3. Configure NEWS_API_KEY below (use forexfactory or investing.com scraper,
       or a paid news API like TradingEconomics / NewsData.io).
    4. Run: python gbpusd_scalping_bot.py

NOTE: This bot is for educational purposes. Always test on a DEMO account first.
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import time
import logging
import json
import os
import pytz
from datetime import datetime, timedelta
from typing import Optional, Tuple, List, Dict

# ─────────────────────────────────────────────────────────────────────────────
# SAAS INTEGRATION
# ─────────────────────────────────────────────────────────────────────────────
from db import get_active_users, get_user_mt5_account, save_trade, update_mt5_status, update_mt5_balance, get_trading_enabled, update_bot_heartbeat
from security import decrypt_password

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

SYMBOL          = "GBPUSD"
MAGIC_NUMBER    = 20240601          # Unique ID for this bot's trades
RISK_PERCENT    = 1.0               # Risk 1% of balance per trade
ATR_SL_MULTIPLIER = 1.5             # SL is 1.5 * ATR
RISK_REWARD_RATIO = 1.5             # TP is 1.5 * SL (risk/reward ratio)
PIP_VALUE       = 0.0001            # 1 pip for GBPUSD (5-digit broker)
# Daily lock profit / stop trading rules
DAILY_PROFIT_TARGET_R   = 3.0       # Stop if daily profit >= 3R (e.g. +3R)
DAILY_PROFIT_TARGET_PCT = None      # Stop if daily profit >= X% of balance
DAILY_PROFIT_TARGET_USD = None      # Stop if daily profit >= X USD

DAILY_LOSS_LIMIT_R      = 2.0       # Stop if daily loss <= -2R
DAILY_LOSS_LIMIT_PCT    = None      # Stop if daily loss <= -X% of balance
DAILY_LOSS_LIMIT_USD    = None      # Stop if daily loss <= -X USD

MAX_DAILY_TRADES        = None      # Disabled (not limited by count of trades)
MAX_DAILY_LOSSES        = None      # Disabled (using R-multiple / percent / USD limits instead)

# Trailing Stop Loss Configuration
TRAILING_SL_ENABLED = True
# Tiers de trailing progressifs : (Seuil de profit en ratio de TP, Ratio de profit sécurisé)
# Par exemple : (0.40, 0.05) veut dire : à 40% du TP atteint, déplacer le SL à l'entrée + 5% du TP
TRAIL_TIERS = [
    (0.40, 0.05),   # Seuil 1 : À >= 40% du TP, déplacer le SL à +5% du TP (BE + couverture de spread)
    (0.70, 0.35),   # Seuil 2 : À >= 70% du TP, déplacer le SL à +35% du TP (sécurise 35% de profit)
    (0.90, 0.65)    # Seuil 3 : À >= 90% du TP, déplacer le SL à +65% du TP (sécurise 65% de profit)
]

MASTER_ACCOUNT_LOGIN = os.getenv("MASTER_ACCOUNT_LOGIN", "")

# Session: 06:00–17:00 London time (UTC+1 BST / UTC+0 GMT)
SESSION_START_HOUR = 6
SESSION_END_HOUR   = 17
TIMEZONE           = "Europe/London"

# Spread filter
MAX_SPREAD_PIPS    = 1.5

# News filter: minutes before/after high-impact event to avoid trading
NEWS_BUFFER_MINUTES = 30

# Indicators
ATR_PERIOD = 14

# Swing detection lookback (bars each side)
SWING_LOOKBACK = 5

# Supply/Demand zone tolerance in pips
ZONE_TOLERANCE_PIPS = 5

# Consolidation / low-volatility filter
MIN_CANDLE_BODY_PIPS = 2.0   # Minimum candle body to consider non-weak
ADR_CONSOLIDATION_RATIO = 0.3  # If candle range < 30% of ADR → consolidating

# Trend detection lookback in M1 bars
TREND_LOOKBACK = 20

# Polling interval in seconds
POLL_INTERVAL = 10

# ─────────────────────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("scalping_bot.log", encoding="utf-8"),
    ]
)
log = logging.getLogger("ScalpBot")

# ─────────────────────────────────────────────────────────────────────────────
# DAILY STATE (resets at midnight)
# ─────────────────────────────────────────────────────────────────────────────

class DailyState:
    def __init__(self):
        self.reset()

    def reset(self):
        self.date         = datetime.now(pytz.timezone(TIMEZONE)).date()
        self.trade_count  = 0
        self.loss_count   = 0
        self.win_count    = 0
        self.daily_profit = 0.0
        self.daily_profit_r = 0.0
        self.halted       = False
        self.halt_reason  = ""
        self.processed_signals = set()
        self.notified_news = set()
        log.info("Daily state reset.")

    def check_date_rollover(self):
        today = datetime.now(pytz.timezone(TIMEZONE)).date()
        if today != self.date:
            self.reset()

    def can_trade(self) -> bool:
        self.check_date_rollover()
        if self.halted:
            log.info(f"Trading halted for today ({self.halt_reason}).")
            return False
        return True

    def record_trade_open(self):
        self.trade_count += 1
        limit_str = str(MAX_DAILY_TRADES) if MAX_DAILY_TRADES is not None else "∞"
        log.info(f"Trade opened. Daily count: {self.trade_count}/{limit_str}")

    def record_trade_result(self, profit: float, balance: float):
        self.daily_profit += profit
        
        # Calculate R-multiple of this trade
        risk_per_trade = balance * (RISK_PERCENT / 100.0)
        trade_r = profit / risk_per_trade if risk_per_trade > 0 else 0.0
        self.daily_profit_r += trade_r

        if profit > 0:
            self.win_count += 1
        else:
            self.loss_count += 1

        log.info(f"Trade closed. Profit: ${profit:.2f} ({trade_r:.2f}R). Win count: {self.win_count}, Loss count: {self.loss_count}. Daily totals: ${self.daily_profit:.2f} ({self.daily_profit_r:.2f}R).")

        # ── Check Profit Targets ──
        if DAILY_PROFIT_TARGET_R is not None and self.daily_profit_r >= DAILY_PROFIT_TARGET_R:
            self.halted = True
            self.halt_reason = f"Objectif de profit atteint ({self.daily_profit_r:.2f}R >= {DAILY_PROFIT_TARGET_R}R) ✅"
            log.info(f"Daily Profit Target reached ({self.daily_profit_r:.2f}R). Trading halted.")
            return

        if DAILY_PROFIT_TARGET_PCT is not None and balance > 0:
            profit_pct = (self.daily_profit / balance) * 100.0
            if profit_pct >= DAILY_PROFIT_TARGET_PCT:
                self.halted = True
                self.halt_reason = f"Objectif de profit atteint ({profit_pct:.2f}% >= {DAILY_PROFIT_TARGET_PCT}%) ✅"
                log.info(f"Daily Profit Target reached ({profit_pct:.2f}%). Trading halted.")
                return

        if DAILY_PROFIT_TARGET_USD is not None and self.daily_profit >= DAILY_PROFIT_TARGET_USD:
            self.halted = True
            self.halt_reason = f"Objectif de profit atteint (${self.daily_profit:.2f} >= ${DAILY_PROFIT_TARGET_USD}) ✅"
            log.info(f"Daily Profit Target reached (${self.daily_profit:.2f} USD). Trading halted.")
            return

        # ── Check Loss Limits ──
        if DAILY_LOSS_LIMIT_R is not None and self.daily_profit_r <= -DAILY_LOSS_LIMIT_R:
            self.halted = True
            self.halt_reason = f"Limite de perte atteinte ({self.daily_profit_r:.2f}R <= -{DAILY_LOSS_LIMIT_R}R) 🛑"
            log.warning(f"Daily Loss Limit reached ({self.daily_profit_r:.2f}R). Trading halted.")
            return

        if DAILY_LOSS_LIMIT_PCT is not None and balance > 0:
            loss_pct = (self.daily_profit / balance) * 100.0
            if loss_pct <= -DAILY_LOSS_LIMIT_PCT:
                self.halted = True
                self.halt_reason = f"Limite de perte atteinte ({loss_pct:.2f}% <= -{DAILY_LOSS_LIMIT_PCT}%) 🛑"
                log.warning(f"Daily Loss Limit reached ({loss_pct:.2f}%). Trading halted.")
                return

        if DAILY_LOSS_LIMIT_USD is not None and self.daily_profit <= -DAILY_LOSS_LIMIT_USD:
            self.halted = True
            self.halt_reason = f"Limite de perte atteinte (${self.daily_profit:.2f} <= -${DAILY_LOSS_LIMIT_USD}) 🛑"
            log.warning(f"Daily Loss Limit reached (${self.daily_profit:.2f} USD). Trading halted.")
            return

        # ── Check Count Limits (if enabled) ──
        if MAX_DAILY_TRADES is not None and self.trade_count >= MAX_DAILY_TRADES:
            self.halted = True
            self.halt_reason = f"Limite de {MAX_DAILY_TRADES} trades atteinte 🛑"
            log.info("Max daily trades reached. Trading halted.")
            return

        if MAX_DAILY_LOSSES is not None and self.loss_count >= MAX_DAILY_LOSSES:
            self.halted = True
            self.halt_reason = f"Limite de {MAX_DAILY_LOSSES} pertes atteinte 🛑"
            log.warning(f"Max daily losses reached. Trading halted.")
            return

daily = DailyState()

# ─────────────────────────────────────────────────────────────────────────────
# NEWS FILTER
# ─────────────────────────────────────────────────────────────────────────────

class NewsFilter:
    """
    Fetches high-impact GBP/USD economic events.
    Uses ForexFactory RSS feed (free, no API key needed).
    Filters events with impact: HIGH for GBP or USD.
    """

    def __init__(self):
        self._cached_events: List[Dict] = []
        self._last_fetch: Optional[datetime] = None
        self._fetch_interval_minutes = 60

    def _fetch_events(self):
        """Fetch today's high-impact events from ForexFactory RSS."""
        try:
            import urllib.request
            import xml.etree.ElementTree as ET
            url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            tz = pytz.timezone(TIMEZONE)
            today = datetime.now(tz).date()
            high_events = []
            for event in data:
                if event.get("impact") != "High":
                    continue
                currency = event.get("currency", "")
                if currency not in ("GBP", "USD"):
                    continue
                # Parse date/time — ForexFactory uses "MM-DD-YYYY" and "HH:MM am/pm"
                date_str  = event.get("date", "")
                time_str  = event.get("time", "")
                try:
                    dt_naive = datetime.strptime(f"{date_str} {time_str}", "%m-%d-%Y %I:%M%p")
                    dt_aware = tz.localize(dt_naive)
                    if dt_aware.date() == today:
                        high_events.append({"currency": currency, "title": event.get("title"), "time": dt_aware})
                except Exception:
                    pass
            self._cached_events = high_events
            self._last_fetch = datetime.now(pytz.utc)
            log.info(f"News filter: loaded {len(high_events)} high-impact events for today.")
        except Exception as e:
            log.warning(f"News fetch failed: {e} — proceeding without live news filter.")

    def _ensure_fresh(self):
        if (self._last_fetch is None or
                (datetime.now(pytz.utc) - self._last_fetch).total_seconds() > self._fetch_interval_minutes * 60):
            self._fetch_events()

    def is_news_window(self) -> Tuple[bool, Optional[str]]:
        """Return (True, title) if current time is within the news buffer window."""
        self._ensure_fresh()
        now = datetime.now(pytz.timezone(TIMEZONE))
        buffer = timedelta(minutes=NEWS_BUFFER_MINUTES)
        for event in self._cached_events:
            event_time = event["time"]
            if (event_time - buffer) <= now <= (event_time + buffer):
                log.warning(f"NEWS WINDOW: {event['currency']} '{event['title']}' at {event_time.strftime('%H:%M')} — skipping trade.")
                return True, event['title']
        return False, None

news_filter = NewsFilter()

# ─────────────────────────────────────────────────────────────────────────────
# GEMINI SENTIMENT FILTER
# ─────────────────────────────────────────────────────────────────────────────
import google.generativeai as genai
import urllib.request
import xml.etree.ElementTree as ET

class SentimentFilter:
    def __init__(self, api_key: str):
        self.enabled = bool(api_key)
        if self.enabled:
            try:
                genai.configure(api_key=api_key)
                self.model = genai.GenerativeModel('gemini-1.5-flash')
                log.info("Gemini Sentiment Filter successfully configured and enabled.")
            except Exception as e:
                log.error(f"Error configuring Gemini Sentiment Filter: {e}")
                self.enabled = False
                self.model = None
        else:
            log.warning("No GEMINI_API_KEY found in .env — Sentiment filter is disabled.")
            self.model = None

    def get_recent_headlines(self) -> str:
        """Fetches recent GBP/USD news headlines from public ForexLive RSS feeds."""
        rss_urls = [
            "https://www.forexlive.com/feed/news",
            "https://www.forexlive.com/feed/TechnicalAnalysis"
        ]
        headlines = []
        for url in rss_urls:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=8) as response:
                    xml_data = response.read()
                    root = ET.fromstring(xml_data)
                    for item in root.findall(".//item")[:8]: # Top 8 articles from each feed
                        title = item.find("title")
                        desc = item.find("description")
                        txt = ""
                        if title is not None and title.text:
                            txt += title.text.strip()
                        if desc is not None and desc.text:
                            desc_clean = desc.text.split('<')[0].strip()
                            if desc_clean:
                                txt += f" - {desc_clean[:120]}"
                        if txt:
                            headlines.append(txt)
            except Exception as e:
                log.warning(f"Failed to fetch news from {url} for sentiment filter: {e}")
        
        if not headlines:
            return "No recent news headlines available."
        return "\n".join(headlines[:15])

    def get_market_bias(self) -> float:
        """
        Analyzes news headlines using Gemini and returns a sentiment score between -1 (Bearish) and +1 (Bullish).
        Returns 0.0 (Neutral) if disabled or if an error occurs.
        """
        if not self.enabled or not self.model:
            return 0.0
            
        headlines = self.get_recent_headlines()
        if "No recent news headlines" in headlines:
            log.info("No fresh news headlines available. Sentiment score neutral (0.0)")
            return 0.0

        prompt = f"""
        Analyze the current market sentiment for the GBP/USD currency pair based on these recent news headlines:
        ---
        {headlines}
        ---
        Return only a single decimal number between -1.0 (extremely Bearish / Sell bias) and +1.0 (extremely Bullish / Buy bias).
        Do not include any explanation, markdown, or other text. Return ONLY the number.
        """
        try:
            response = self.model.generate_content(prompt)
            score_str = response.text.strip()
            score = float(score_str)
            log.info(f"Gemini Sentiment Analysis: Score = {score:.2f} based on {len(headlines.splitlines())} headlines.")
            return score
        except Exception as e:
            log.warning(f"Failed to generate sentiment score from Gemini: {e}. Defaulting to neutral (0.0)")
            return 0.0

gemini_key = os.getenv("GEMINI_API_KEY", "")
sentiment_filter = SentimentFilter(api_key=gemini_key)

# ─────────────────────────────────────────────────────────────────────────────
# TELEGRAM NOTIFIER
# ─────────────────────────────────────────────────────────────────────────────
import requests

class TelegramNotifier:
    def __init__(self, token: str, chat_id: str):
        self.enabled = bool(token and chat_id)
        if self.enabled:
            self.token = token
            self.chat_id = chat_id
            self.base_url = f"https://api.telegram.org/bot{token}/sendMessage"
            log.info("Telegram Notifier successfully configured and enabled.")
        else:
            log.warning("Telegram token or chat_id is missing in .env. Notifications are disabled.")

    def send_message(self, message: str):
        if not self.enabled:
            return
        try:
            payload = {"chat_id": self.chat_id, "text": message, "parse_mode": "Markdown"}
            resp = requests.post(self.base_url, data=payload, timeout=5)
            if resp.status_code != 200:
                log.error(f"Telegram API error: {resp.status_code} - {resp.text}")
        except Exception as e:
            log.error(f"Erreur envoi Telegram: {e}")

telegram_token = os.getenv("TELEGRAM_TOKEN", "")
telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
telegram_notifier = TelegramNotifier(token=telegram_token, chat_id=telegram_chat_id)

# ─────────────────────────────────────────────────────────────────────────────
# MT5 HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def mt5_connect() -> bool:
    if not mt5.initialize():
        log.error(f"MT5 initialize failed: {mt5.last_error()}")
        return False
    info = mt5.terminal_info()
    log.info(f"Connected to MT5 | Build {info.build} | Connected: {info.connected}")
    return True

def get_bars(timeframe: int, count: int) -> Optional[pd.DataFrame]:
    rates = mt5.copy_rates_from_pos(SYMBOL, timeframe, 0, count)
    if rates is None or len(rates) == 0:
        return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    return df

def pip(n: float) -> float:
    return n * PIP_VALUE

def candle_body(row) -> float:
    return abs(row["close"] - row["open"])

def candle_range(row) -> float:
    return row["high"] - row["low"]

# ─────────────────────────────────────────────────────────────────────────────
# INDICATORS
# ─────────────────────────────────────────────────────────────────────────────

def calculate_vwap(df: pd.DataFrame) -> pd.Series:
    """
    Calculate daily resetting VWAP.
    Typical Price = (High + Low + Close) / 3
    VWAP = sum(Typical Price * Volume) / sum(Volume)
    Resets when the calendar day changes.
    """
    df = df.copy()
    # Typical price
    df['tp'] = (df['high'] + df['low'] + df['close']) / 3.0
    df['tp_vol'] = df['tp'] * df['tick_volume']
    
    # Convert 'time' to datetime format if not already done
    df['time_dt'] = pd.to_datetime(df['time'])
    df['date'] = df['time_dt'].dt.date
    
    cum_vol = df.groupby('date')['tick_volume'].cumsum()
    cum_tp_vol = df.groupby('date')['tp_vol'].cumsum()
    
    # Avoid division by zero
    vwap = cum_tp_vol / cum_vol.replace(0, 1)
    return vwap

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Calculate Average True Range (ATR) using Wilder's EMA smoothing.
    """
    df = df.copy()
    high = df['high']
    low = df['low']
    close_prev = df['close'].shift(1)
    
    tr1 = high - low
    tr2 = (high - close_prev).abs()
    tr3 = (low - close_prev).abs()
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1.0/period, adjust=False).mean()
    return atr

def calculate_stoch_rsi(df: pd.DataFrame, period: int = 14, k_period: int = 3, d_period: int = 3) -> Tuple[pd.Series, pd.Series]:
    """
    Calculate Stochastic RSI (%K and %D lines).
    """
    df = df.copy()
    delta = df['close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    
    # Wilder's EMA for RSI
    avg_gain = gain.ewm(alpha=1.0/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0/period, adjust=False).mean()
    
    rs = avg_gain / avg_loss.replace(0, 1e-9)
    rsi = 100 - (100 / (1 + rs))
    
    # Stochastic of RSI
    rsi_min = rsi.rolling(window=period).min()
    rsi_max = rsi.rolling(window=period).max()
    
    stoch_rsi = (rsi - rsi_min) / (rsi_max - rsi_min).replace(0, 1e-9)
    
    # Smooth %K and %D
    stoch_rsi_k = stoch_rsi.rolling(window=k_period).mean() * 100
    stoch_rsi_d = stoch_rsi_k.rolling(window=d_period).mean()
    
    return stoch_rsi_k, stoch_rsi_d

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["vwap"] = calculate_vwap(df)
    df["atr"] = calculate_atr(df, period=14)
    k, d = calculate_stoch_rsi(df, period=14)
    df["stoch_k"] = k
    df["stoch_d"] = d
    df["sma50"] = df["close"].rolling(window=50).mean()
    df["ema200"] = df["close"].ewm(span=200, adjust=False).mean()
    return df

# ─────────────────────────────────────────────────────────────────────────────
# TREND DETECTION
# ─────────────────────────────────────────────────────────────────────────────

def detect_trend(df: pd.DataFrame) -> str:
    """
    Detect trend on last TREND_LOOKBACK bars using swing highs/lows.
    Returns: 'bullish', 'bearish', or 'ranging'
    """
    highs = df["high"].values[-TREND_LOOKBACK:]
    lows  = df["low"].values[-TREND_LOOKBACK:]

    # Find local swing highs/lows (simplified)
    swing_highs = []
    swing_lows  = []
    lb = SWING_LOOKBACK
    for i in range(lb, len(highs) - lb):
        if highs[i] == max(highs[i-lb:i+lb+1]):
            swing_highs.append(highs[i])
        if lows[i] == min(lows[i-lb:i+lb+1]):
            swing_lows.append(lows[i])

    if len(swing_highs) >= 2 and len(swing_lows) >= 2:
        hh = swing_highs[-1] > swing_highs[-2]
        hl = swing_lows[-1] > swing_lows[-2]
        lh = swing_highs[-1] < swing_highs[-2]
        ll = swing_lows[-1] < swing_lows[-2]
        if hh and hl:
            return "bullish"
        if lh and ll:
            return "bearish"
    return "ranging"

# ─────────────────────────────────────────────────────────────────────────────
# CONSOLIDATION FILTER
# ─────────────────────────────────────────────────────────────────────────────

def is_consolidating(df: pd.DataFrame, lookback: int = 10) -> bool:
    """
    Returns True if market is ranging / low-volatility on recent bars.
    Criteria:
      1. Average candle body < MIN_CANDLE_BODY_PIPS
      2. Average range < ADR_CONSOLIDATION_RATIO * 20-bar ADR
    """
    recent = df.iloc[-lookback:]
    avg_body  = recent.apply(candle_body, axis=1).mean()
    avg_range = recent.apply(candle_range, axis=1).mean()
    adr       = df.iloc[-20:].apply(candle_range, axis=1).mean()

    body_weak  = avg_body  < pip(MIN_CANDLE_BODY_PIPS)
    range_low  = avg_range < (adr * ADR_CONSOLIDATION_RATIO)

    if body_weak or range_low:
        log.debug(f"Consolidation detected: avg_body={avg_body:.5f}, avg_range={avg_range:.5f}, adr={adr:.5f}")
        return True
    return False

# ─────────────────────────────────────────────────────────────────────────────
# SUPPLY & DEMAND ZONES
# ─────────────────────────────────────────────────────────────────────────────

def detect_zones(df: pd.DataFrame) -> Tuple[List[Tuple], List[Tuple]]:
    """
    Detect supply and demand zones based on price action:
    - Demand zone: strong bullish move after a base (consolidation + breakout up)
    - Supply zone: strong bearish move after a base (consolidation + breakout down)
    Returns: (demand_zones, supply_zones)
    Each zone = (zone_low, zone_high)
    """
    demand_zones = []
    supply_zones = []
    tol = pip(ZONE_TOLERANCE_PIPS)

    for i in range(3, len(df) - 3):
        c = df.iloc[i]
        prev = df.iloc[i-1]
        nxt  = df.iloc[i+1]

        body_c    = candle_body(c)
        range_c   = candle_range(c)
        body_nxt  = candle_body(nxt)

        # Demand zone: small base candle followed by a strong bullish candle
        if (body_c < pip(3) and                           # base candle small
                nxt["close"] > nxt["open"] and            # next is bullish
                body_nxt > pip(4) and                     # strong move
                nxt["close"] > c["high"]):                # breaks above base
            zone_low  = c["low"]  - tol
            zone_high = c["high"] + tol
            demand_zones.append((zone_low, zone_high))

        # Supply zone: small base candle followed by a strong bearish candle
        if (body_c < pip(3) and
                nxt["close"] < nxt["open"] and
                body_nxt > pip(4) and
                nxt["close"] < c["low"]):
            zone_low  = c["low"]  - tol
            zone_high = c["high"] + tol
            supply_zones.append((zone_low, zone_high))

    # Deduplicate overlapping zones (keep last 5 relevant)
    demand_zones = demand_zones[-5:] if demand_zones else []
    supply_zones = supply_zones[-5:] if supply_zones else []
    return demand_zones, supply_zones

def price_in_zone(price: float, zones: List[Tuple]) -> bool:
    for z_low, z_high in zones:
        if z_low <= price <= z_high:
            return True
    return False

def price_near_level(price: float, level: float, tolerance_pips: float = 3.0) -> bool:
    return abs(price - level) <= pip(tolerance_pips)

# ─────────────────────────────────────────────────────────────────────────────
# PRICE ACTION — REJECTION & ENGULFING
# ─────────────────────────────────────────────────────────────────────────────

def is_rejection_candle(c, direction: str) -> bool:
    """
    Bullish rejection: long lower wick, small body near top.
    Bearish rejection: long upper wick, small body near bottom.
    """
    body  = candle_body(c)
    rng   = candle_range(c)
    if rng < pip(1):
        return False

    if direction == "buy":
        lower_wick = min(c["open"], c["close"]) - c["low"]
        return lower_wick >= 0.55 * rng and body <= 0.35 * rng
    else:
        upper_wick = c["high"] - max(c["open"], c["close"])
        return upper_wick >= 0.55 * rng and body <= 0.35 * rng

def is_engulfing(c_prev, c_curr, direction: str) -> bool:
    """
    Bullish engulfing: current bullish candle body engulfs prior bearish body.
    Bearish engulfing: current bearish candle body engulfs prior bullish body.
    MUST be closed (caller must use confirmed/closed candle).
    """
    if direction == "buy":
        prev_bear = c_prev["close"] < c_prev["open"]
        curr_bull = c_curr["close"] > c_curr["open"]
        if not (prev_bear and curr_bull):
            return False
        return (c_curr["close"] >= c_prev["open"] and
                c_curr["open"]  <= c_prev["close"])
    else:
        prev_bull = c_prev["close"] > c_prev["open"]
        curr_bear = c_curr["close"] < c_curr["open"]
        if not (prev_bull and curr_bear):
            return False
        return (c_curr["close"] <= c_prev["open"] and
                c_curr["open"]  >= c_prev["close"])

# ─────────────────────────────────────────────────────────────────────────────
# BREAK & RETEST LOGIC
# ─────────────────────────────────────────────────────────────────────────────

def detect_break_and_retest(df: pd.DataFrame, direction: str, zones, sma50: float, ema200: float) -> bool:
    """
    Check if price has broken a key level and is now retesting it.
    direction: 'buy' → breakout above level, retest from above
               'sell' → breakout below level, retest from below
    """
    if len(df) < 6:
        return False

    # Last 3 closed candles (index -4, -3, -2); -1 is current forming
    c1 = df.iloc[-4]   # breakout bar
    c2 = df.iloc[-3]   # move away bar
    c3 = df.iloc[-2]   # retest bar (most recent closed)
    current_price = df.iloc[-1]["close"]

    key_levels = [sma50, ema200]
    for z_low, z_high in zones:
        key_levels.append((z_low + z_high) / 2)

    for level in key_levels:
        if direction == "buy":
            # c1 closes above level → break
            # c3 retraces back near level
            broke_above  = c1["close"] > level and c1["open"] < level
            retesting    = price_near_level(c3["low"], level, 4)
            if broke_above and retesting:
                return True
        else:
            # c1 closes below level → break
            # c3 retraces back near level
            broke_below  = c1["close"] < level and c1["open"] > level
            retesting    = price_near_level(c3["high"], level, 4)
            if broke_below and retesting:
                return True
    return False

# ─────────────────────────────────────────────────────────────────────────────
# M1 MOMENTUM CONFIRMATION
# ─────────────────────────────────────────────────────────────────────────────

def m1_momentum_aligned(direction: str) -> bool:
    """
    Check last 3 M1 candles for momentum alignment.
    Buy: majority of last 3 closed bullish, no consolidation.
    Sell: majority of last 3 closed bearish, no consolidation.
    """
    df_m1 = get_bars(mt5.TIMEFRAME_M1, 20)
    if df_m1 is None or len(df_m1) < 10:
        return False

    if is_consolidating(df_m1, lookback=6):
        log.debug("M1 consolidating — momentum not aligned.")
        return False

    last3 = df_m1.iloc[-4:-1]  # 3 closed candles
    bull_count = (last3["close"] > last3["open"]).sum()
    bear_count = (last3["close"] < last3["open"]).sum()

    if direction == "buy"  and bull_count >= 2:
        return True
    if direction == "sell" and bear_count >= 2:
        return True
    return False

# ─────────────────────────────────────────────────────────────────────────────
# SESSION CHECK
# ─────────────────────────────────────────────────────────────────────────────

def in_trading_session() -> bool:
    tz  = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    return SESSION_START_HOUR <= now.hour < SESSION_END_HOUR

# ─────────────────────────────────────────────────────────────────────────────
# TRADE EXECUTION
# ─────────────────────────────────────────────────────────────────────────────

def calculate_lot_size(balance: float, risk_percent: float, sl_pips: float, sym_info) -> float:
    """
    Calculate position size based on account balance and risk percentage.
    """
    if balance <= 0 or sl_pips <= 0:
        return sym_info.volume_min

    risk_amount = balance * (risk_percent / 100.0)
    
    tick_value = sym_info.trade_tick_value
    tick_size = sym_info.trade_tick_size
    
    if tick_value == 0 or tick_size == 0:
        return sym_info.volume_min

    ticks_per_pip = PIP_VALUE / tick_size
    loss_value_per_lot = sl_pips * ticks_per_pip * tick_value
    
    if loss_value_per_lot == 0:
        return sym_info.volume_min
        
    lot = risk_amount / loss_value_per_lot
    
    # Round to nearest step
    step = sym_info.volume_step
    if step > 0:
        lot = round(lot / step) * step
        
    # Constrain to min/max
    lot = max(sym_info.volume_min, min(lot, sym_info.volume_max))
    
    return float(round(lot, 2))

def get_open_position(magic: int) -> Optional[object]:
    """Return open position for GBPUSD placed by this bot, or None."""
    positions = mt5.positions_get(symbol=SYMBOL)
    if positions:
        for pos in positions:
            if pos.magic == magic:
                return pos
    return None

def place_order_for_all_users(direction: str, atr: float) -> bool:
    """
    Loop through all active users in Supabase, switch MT5 account, and place order.
    Returns True if at least one trade was placed.
    """
    active_users = get_active_users()
    if not active_users:
        log.warning("No active users found in database.")
        return False

    success_count = 0
    original_account = mt5.account_info()

    # Calculate standard SL/TP distances based on ATR
    sl_distance = atr * ATR_SL_MULTIPLIER
    tp_distance = sl_distance * RISK_REWARD_RATIO
    sl_pips = sl_distance / PIP_VALUE

    for user_id in active_users:
        mt5_acc = get_user_mt5_account(user_id)
        if not mt5_acc:
            continue

        try:
            plain_password = decrypt_password(mt5_acc['encrypted_password'])
            login = int(mt5_acc['login_id'])
            server = mt5_acc['server_name']

            # Login to user account
            if not mt5.login(login=login, password=plain_password, server=server):
                log.error(f"Failed to connect to user {login} on {server}")
                update_mt5_status(mt5_acc['id'], 'ERROR')
                continue
            
            update_mt5_status(mt5_acc['id'], 'CONNECTED')

            tick = mt5.symbol_info_tick(SYMBOL)
            if tick is None:
                continue

            sym_info = mt5.symbol_info(SYMBOL)
            point = sym_info.point
            pips_to_pts = int(round(PIP_VALUE / point))
            
            # Spread Check
            spread_pips = (tick.ask - tick.bid) / PIP_VALUE
            if spread_pips > MAX_SPREAD_PIPS:
                log.warning(f"Spread {spread_pips:.1f} pips exceeds limit {MAX_SPREAD_PIPS}. Skipping trade for {login}.")
                continue
            
            # Calculate dynamic lot size based on balance and ATR Stop-Loss
            account_info = mt5.account_info()
            if account_info is None:
                continue
                
            balance = account_info.balance
            
            # Set entry price and targets
            if direction == "buy":
                price    = tick.ask
                sl       = price - sl_distance
                tp       = price + tp_distance
                order_type = mt5.ORDER_TYPE_BUY
            else:
                price    = tick.bid
                sl       = price + sl_distance
                tp       = price - tp_distance
                order_type = mt5.ORDER_TYPE_SELL

            # ── Vérifier stop level minimum du broker ───────────────────────
            sym_info_check = mt5.symbol_info(SYMBOL)
            current_sl_pips = sl_pips
            current_sl_distance = sl_distance
            current_tp_distance = tp_distance
            
            if sym_info_check and sym_info_check.trade_stops_level > 0:
                min_stop_pips = sym_info_check.trade_stops_level / 10.0
                if current_sl_pips < min_stop_pips:
                    log.warning(f"⚠️  SL {current_sl_pips:.1f}p < stop_level min {min_stop_pips}p — SL ajusté!")
                    current_sl_pips = min_stop_pips + 2
                    current_sl_distance = current_sl_pips * PIP_VALUE
                    current_tp_distance = current_sl_distance * RISK_REWARD_RATIO
                    if direction == "buy":
                         sl = price - current_sl_distance
                         tp = price + current_tp_distance
                    else:
                         sl = price + current_sl_distance
                         tp = price - current_tp_distance

            dynamic_lot = calculate_lot_size(balance, RISK_PERCENT, current_sl_pips, sym_info)

            # Auto-détecter le filling mode supporté par le broker
            filling_mode = mt5.ORDER_FILLING_IOC  # défaut
            if sym_info.filling_mode & 1:    # FOK supporté
                filling_mode = mt5.ORDER_FILLING_FOK
            elif sym_info.filling_mode & 2:  # IOC supporté
                filling_mode = mt5.ORDER_FILLING_IOC
            elif sym_info.filling_mode & 4:  # RETURN supporté
                filling_mode = mt5.ORDER_FILLING_RETURN

            request = {
                "action":    mt5.TRADE_ACTION_DEAL,
                "symbol":    SYMBOL,
                "volume":    dynamic_lot,
                "type":      order_type,
                "price":     price,
                "sl":        round(sl, 5),
                "tp":        round(tp, 5),
                "deviation": 10,
                "magic":     MAGIC_NUMBER,
                "comment":   "Vibe_Trading_Bot",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": filling_mode,
            }

            result = mt5.order_send(request)
            if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
                log.error(f"Order failed for user {login}: {result}")
                continue

            log.info(f"✅ ORDER PLACED for {login} | {direction.upper()} {SYMBOL} @ {price:.5f} | Lot={dynamic_lot} | SL={sl:.5f} | TP={tp:.5f}")
            
            # Save trade to Supabase
            save_trade({
                "user_id":   user_id,
                "symbol":    SYMBOL,
                "type":      direction.upper(),
                "entry":     round(price, 5),
                "sl":        round(sl, 5),
                "tp":        round(tp, 5),
                "lot_size":  dynamic_lot,   # ← Lot reel kalkile selon balans
                "profit":    0,
                "status":    "OPEN",
                "open_time": datetime.utcnow().isoformat()
            })
            
            success_count += 1
            
        except Exception as e:
            log.error(f"Error processing user {user_id}: {e}")

    daily.record_trade_open()
    
    # Restore original master account if possible (or just leave the last one)
    if original_account:
        # Note: We can't automatically log back in without the master password, 
        # so for this MVP, the terminal stays connected to the last user's account.
        pass

    return success_count > 0

# ─────────────────────────────────────────────────────────────────────────────
# MONITOR CLOSED TRADES (for loss counting)
# ─────────────────────────────────────────────────────────────────────────────

def check_closed_trades():
    """
    Check if open trades in Supabase are still open in MT5.
    If closed, update their status, profit, and close_time.
    Also sends Telegram notifications for wins/losses.
    """
    try:
        from db import supabase
        # 1. Fetch all open trades from Supabase
        resp = supabase.table("trades").select("*").eq("status", "OPEN").eq("symbol", SYMBOL).execute()
        open_trades = resp.data if resp and resp.data else []
        if not open_trades:
            return

        telegram_sent = False

        for trade in open_trades:
            user_id = trade["user_id"]
            trade_id = trade["id"]
            open_time_str = trade["open_time"]

            # Fetch MT5 account for this user
            mt5_acc = get_user_mt5_account(user_id)
            if not mt5_acc:
                continue

            try:
                plain_password = decrypt_password(mt5_acc['encrypted_password'])
                login = int(mt5_acc['login_id'])
                server = mt5_acc['server_name']

                # Log in to user's account
                if not mt5.login(login=login, password=plain_password, server=server):
                    log.error(f"check_closed_trades: Failed to login to user {login}")
                    update_mt5_status(mt5_acc['id'], 'ERROR')
                    continue

                update_mt5_status(mt5_acc['id'], 'CONNECTED')

                # Check if position is still open in MT5
                open_pos = get_open_position(MAGIC_NUMBER)
                if open_pos is not None:
                    # Trade is still open, do nothing
                    continue

                # Parse open time from Supabase
                trade_open_time = datetime.fromisoformat(open_time_str.replace("Z", "+00:00"))

                # Determine broker timezone offset dynamically
                offset_seconds = 0
                tick = mt5.symbol_info_tick(SYMBOL)
                if tick:
                    utc_now = datetime.now(pytz.utc).timestamp()
                    offset_seconds = round((tick.time - utc_now) / 1800) * 1800

                # Query deals in a wide window around trade open time
                from_date_utc = trade_open_time - timedelta(days=2)
                to_date_utc = datetime.now(pytz.utc) + timedelta(days=2)

                from_date_server = datetime.fromtimestamp(from_date_utc.timestamp() + offset_seconds)
                to_date_server = datetime.fromtimestamp(to_date_utc.timestamp() + offset_seconds)

                deals = mt5.history_deals_get(from_date_server, to_date_server)
                profit        = 0.0
                found_deal    = False
                deal_time_str = datetime.now(pytz.utc).isoformat()
                close_reason  = None

                if deals:
                    # Filter exit deals matching our magic number and closed after trade_open_time
                    candidate_deals = []
                    for deal in deals:
                        if deal.magic != MAGIC_NUMBER:
                            continue
                        # Log every bot deal for diagnostics
                        log.info(
                            f"  Deal: ticket={deal.ticket} | entry={deal.entry} | "
                            f"reason={deal.reason} | profit={deal.profit:.2f} | "
                            f"type={deal.type}"
                        )
                        if deal.entry == mt5.DEAL_ENTRY_IN:
                            continue
                        
                        # Convert deal time (server time) to UTC
                        deal_utc_timestamp = deal.time - offset_seconds
                        deal_time_utc = datetime.fromtimestamp(deal_utc_timestamp, pytz.utc)
                        
                        if deal_time_utc > trade_open_time:
                            candidate_deals.append((deal, deal_time_utc))

                    log.info(f"MT5 deals trouvés pour ce bot après open_time: {len(candidate_deals)}")

                    if candidate_deals:
                        # Sort by time ascending to get the oldest exit deal since open_time
                        candidate_deals.sort(key=lambda x: x[1])
                        deal, deal_time_utc = candidate_deals[0]

                        profit        = deal.profit
                        deal_time_str = deal_time_utc.isoformat()
                        found_deal    = True

                        # Déterminer raison via deal.reason (le plus fiable)
                        if deal.reason == mt5.DEAL_REASON_TP:
                            close_reason = "TP"
                        elif deal.reason == mt5.DEAL_REASON_SL:
                            close_reason = "SL"
                        elif deal.profit < 0:
                            close_reason = "SL"
                            log.info(f"Raison inconnue mais profit négatif → forcé SL")
                        elif deal.profit > 0:
                            close_reason = "TP"
                            log.info(f"Raison inconnue mais profit positif → forcé TP")
                        else:
                            close_reason = "MANUAL"

                if not found_deal:
                    log.warning(f"Aucun deal de fermeture trouvé pour trade {trade_id}. Vérifier MT5 history. Skipping update.")
                    continue

                # ── Statut final ──────────────────────────────────────────────
                if close_reason == "TP":
                    status = "WIN"
                elif close_reason == "SL":
                    status = "LOSS"
                else:
                    # Dernier recours absolu : profit
                    status = "WIN" if profit > 0 else "LOSS"

                log.info(
                    f"✅ TRADE FERMÉ | ID={trade_id} | Raison={close_reason} | "
                    f"Profit=${profit:.2f} | Statut={status}"
                )

                # ── Mise à jour Supabase ──────────────────────────────────────
                supabase.table("trades").update({
                    "status":     status,
                    "profit":     round(profit, 2),
                    "close_time": deal_time_str
                }).eq("id", trade_id).execute()

                log.info(f"Supabase updated: trade {trade_id} → {status} ${profit:.2f}")

                # ── Daily limits & Notification (Géré par le compte Master) ────
                master_login = os.getenv("MASTER_ACCOUNT_LOGIN", "").strip()
                is_master = (not master_login) or (str(login) == master_login)

                if is_master:
                    signal_key = open_time_str[:16]  # Group by minute to identify the signal batch
                    if signal_key not in daily.processed_signals:
                        # Update Daily limits
                        was_halted = daily.halted
                        acc_info = mt5.account_info()
                        master_balance = acc_info.balance if acc_info is not None else 0.0
                        daily.record_trade_result(profit, master_balance)
                        daily.processed_signals.add(signal_key)
                        if daily.halted and not was_halted:
                            telegram_notifier.send_message(f"🛑 *Trading terminé pour aujourd'hui !*\nRaison: {daily.halt_reason}")

                        # ── Notification Telegram ──────────
                        if status == "WIN":
                            emoji       = "🎯"
                            status_text = "Take Profit atteint ✅"
                        else:
                            emoji       = "❌"
                            status_text = "Stop Loss atteint 🛑"
                        reason_label = f" ({close_reason})" if close_reason else ""
                        telegram_notifier.send_message(
                            f"{emoji} *{status_text} sur GBP/USD !*{reason_label}"
                        )

            except Exception as e:
                log.error(f"Error checking trade closure for user {user_id}: {e}")

    except Exception as e:
        log.error(f"Error in check_closed_trades: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# TRADE MANAGEMENT (BREAK-EVEN & NEAR TP CLOSE)
# ─────────────────────────────────────────────────────────────────────────────

near_tp_timers = {}

def close_trade_now(login: int, pos) -> bool:
    tick = mt5.symbol_info_tick(pos.symbol)
    if not tick: return False
    
    close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
    price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask
    
    sym_info = mt5.symbol_info(pos.symbol)
    filling_mode = mt5.ORDER_FILLING_IOC
    if sym_info:
        if sym_info.filling_mode & 1:
            filling_mode = mt5.ORDER_FILLING_FOK
        elif sym_info.filling_mode & 2:
            filling_mode = mt5.ORDER_FILLING_IOC

    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "position": pos.ticket,
        "symbol": pos.symbol,
        "volume": pos.volume,
        "type": close_type,
        "price": price,
        "deviation": 20,
        "magic": pos.magic,
        "comment": "Near_TP_Close",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling_mode,
    }
    res = mt5.order_send(req)
    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
        log.info(f"Successfully closed trade {pos.ticket} for {login} (Near TP)")
        return True
    else:
        log.error(f"Failed to close trade {pos.ticket} for {login}: {res}")
        return False

def get_progressive_trail_lock_ratio(profit_ratio: float) -> Optional[float]:
    """
    Returns the target lock ratio (percentage of TP to lock) based on current profit ratio.
    Returns None if trailing stop is not yet triggered.
    """
    if not TRAILING_SL_ENABLED:
        return None
        
    selected_lock_ratio = None
    for threshold, lock_ratio in TRAIL_TIERS:
        if profit_ratio >= threshold:
            selected_lock_ratio = lock_ratio
    return selected_lock_ratio

def manage_open_trades():
    """
    Checks if any open positions qualify for trailing stop updates.
    Updates the Stop-Loss progressively based on the current profit ratio.
    Also handles Near TP closing logic.
    """
    active_users = get_active_users()
    if not active_users: return
    
    for user_id in active_users:
        mt5_acc = get_user_mt5_account(user_id)
        if not mt5_acc: continue
        
        try:
            plain_password = decrypt_password(mt5_acc['encrypted_password'])
            login = int(mt5_acc['login_id'])
            server = mt5_acc['server_name']
            
            # Switch to this user's account to manage their trades
            if not mt5.login(login=login, password=plain_password, server=server):
                continue
            
            positions = mt5.positions_get(symbol=SYMBOL)
            if not positions: continue
            
            for pos in positions:
                if pos.magic != MAGIC_NUMBER:
                    continue
                
                # Calculate TP distance
                tp_pips = 0.0
                if pos.tp > 0:
                    tp_pips = abs(pos.price_open - pos.tp) / PIP_VALUE
                else:
                    # Fallback using SL and Risk-Reward ratio
                    sl_dist = abs(pos.price_open - pos.sl) / PIP_VALUE if pos.sl > 0 else 0.0
                    tp_pips = sl_dist * RISK_REWARD_RATIO if sl_dist > 0 else 0.0

                if tp_pips <= 0:
                    continue

                # Calculate profit in pips
                if pos.type == mt5.ORDER_TYPE_BUY:
                    profit_pips = (pos.price_current - pos.price_open) / PIP_VALUE
                else:
                    profit_pips = (pos.price_open - pos.price_current) / PIP_VALUE

                profit_ratio = profit_pips / tp_pips
                lock_ratio = get_progressive_trail_lock_ratio(profit_ratio)

                if lock_ratio is not None:
                    # Target SL
                    if pos.type == mt5.ORDER_TYPE_BUY:
                        target_sl = pos.price_open + (lock_ratio * tp_pips * PIP_VALUE)
                    else:
                        target_sl = pos.price_open - (lock_ratio * tp_pips * PIP_VALUE)

                    # Check if target SL is better than current SL and respects stop level limits
                    sym_info = mt5.symbol_info(SYMBOL)
                    min_stop_pips = (sym_info.trade_stops_level / 10.0) if (sym_info and sym_info.trade_stops_level > 0) else 0.0
                    min_distance = min_stop_pips * PIP_VALUE

                    should_update = False
                    if pos.type == mt5.ORDER_TYPE_BUY:
                        # For BUY, target SL must be higher than current SL and not too close to current price
                        is_better = target_sl > pos.sl
                        not_too_close = (pos.price_current - target_sl) >= min_distance
                        if is_better and not_too_close:
                            should_update = True
                    else:
                        # For SELL, target SL must be lower than current SL (or current SL is 0.0) and not too close to current price
                        is_better = target_sl < pos.sl or pos.sl == 0.0
                        not_too_close = (target_sl - pos.price_current) >= min_distance
                        if is_better and not_too_close:
                            should_update = True

                    if should_update:
                        request = {
                            "action": mt5.TRADE_ACTION_SLTP,
                            "position": pos.ticket,
                            "symbol": SYMBOL,
                            "sl": round(target_sl, 5),
                            "tp": pos.tp
                        }
                        res = mt5.order_send(request)
                        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                            log.info(f"Trailing SL progressive applied for user {login} {'BUY' if pos.type == mt5.ORDER_TYPE_BUY else 'SELL'} {pos.ticket} (SL: {target_sl:.5f}, Profit: {profit_pips:.1f}p, Ratio: {profit_ratio:.2%})")
                
                # Near TP Close Logic
                if pos.tp > 0:
                    dist_to_tp = 0.0
                    if pos.type == mt5.ORDER_TYPE_BUY:
                        dist_to_tp = (pos.tp - pos.price_current) / PIP_VALUE
                    elif pos.type == mt5.ORDER_TYPE_SELL:
                        dist_to_tp = (pos.price_current - pos.tp) / PIP_VALUE
                        
                    timer_key = f"{login}_{pos.ticket}"
                    
                    if 0 < dist_to_tp <= 2.0:
                        if timer_key not in near_tp_timers:
                            near_tp_timers[timer_key] = time.time()
                            log.info(f"Near TP zone entered for {login} ticket {pos.ticket}. Dist: {dist_to_tp:.1f} pips")
                        else:
                            elapsed = time.time() - near_tp_timers[timer_key]
                            if elapsed >= 120:  # 2 minutes
                                if close_trade_now(login, pos):
                                    master_login = os.getenv("MASTER_ACCOUNT_LOGIN", "").strip()
                                    if not master_login or str(login) == master_login:
                                        telegram_notifier.send_message(f"⚠️ *Near TP Close* sur GBP/USD !\nLa position a été fermée automatiquement car elle stagnait à {dist_to_tp:.1f} pips du TP pendant 2 minutes.")
                                    del near_tp_timers[timer_key]
                    else:
                        if timer_key in near_tp_timers:
                            del near_tp_timers[timer_key]

        except Exception as e:
            log.error(f"Error managing trades for user {user_id}: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# SYNC BALANCES
# ─────────────────────────────────────────────────────────────────────────────

def sync_all_balances():
    """Loops through all users to update their current balance and equity in Supabase."""
    active_users = get_active_users()
    if not active_users:
        return

    log.info("Syncing balances for all active users...")
    original_account = mt5.account_info()

    for user_id in active_users:
        mt5_acc = get_user_mt5_account(user_id)
        if not mt5_acc:
            continue
        try:
            plain_password = decrypt_password(mt5_acc['encrypted_password'])
            login = int(mt5_acc['login_id'])
            server = mt5_acc['server_name']

            if mt5.login(login=login, password=plain_password, server=server):
                account_info = mt5.account_info()
                if account_info is not None:
                    update_mt5_balance(mt5_acc['id'], account_info.balance, account_info.equity)
                    update_mt5_status(mt5_acc['id'], 'CONNECTED')
            else:
                update_mt5_status(mt5_acc['id'], 'ERROR')
        except Exception as e:
            log.error(f"Error syncing balance for {user_id}: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# CORE SIGNAL LOGIC
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_signal() -> Tuple[Optional[str], float]:
    """
    Full signal evaluation pipeline combining scoring system (6.5/10)
    and direct trigger logic:
    - Biais directionnel via VWAP
    - Déclencheur (trigger) via croisement StochRSI
    - Zone de support/résistance requise (Supply/Demand)
    - Validation de la tendance via SMA50 et EMA200
    - IA Sentiment validation via Gemini
    Returns: (direction, atr_value) -> ('buy'/'sell'/None, float)
    """
    # ── 1. Fetch M1 data ────────────────────────────────────────────────────
    df_m1_raw = get_bars(mt5.TIMEFRAME_M1, 300)
    if df_m1_raw is None or len(df_m1_raw) < 150:
        log.debug("Not enough M1 data.")
        return None, 0.0

    df_m1 = add_indicators(df_m1_raw)

    # Use only rows where indicators are valid
    df = df_m1.dropna(subset=["vwap", "atr", "stoch_k", "stoch_d", "sma50", "ema200"]).copy()
    if len(df) < 20:
        return None, 0.0

    # ── 2. Consolidation ─────────────────────────────────────────────────────
    if is_consolidating(df, lookback=10):
        log.info("M1 consolidating — skipping.")
        return None, 0.0

    # ── 3. Indicators at last closed bar ─────────────────────────────────────
    last_closed = df.iloc[-2]  # -1 is still forming
    prev_closed = df.iloc[-3]
    price  = last_closed["close"]
    vwap   = last_closed["vwap"]
    atr    = last_closed["atr"]
    sma50  = last_closed["sma50"]
    ema200 = last_closed["ema200"]
    stoch_k = last_closed["stoch_k"]
    stoch_d = last_closed["stoch_d"]
    prev_k = prev_closed["stoch_k"]
    prev_d = prev_closed["stoch_d"]

    # Supply / Demand zones
    demand_zones, supply_zones = detect_zones(df.iloc[:-1])  # exclude current bar

    # ── 4. Calculate 10-Point Score ──────────────────────────────────────────
    buy_score = 0.0
    sell_score = 0.0

    # 4.1 Trend Alignment (VWAP, EMA200, SMA50)
    if price > vwap: buy_score += 1.0
    if price < vwap: sell_score += 1.0

    if price > ema200: buy_score += 1.0
    if price < ema200: sell_score += 1.0

    if price > sma50: buy_score += 1.0
    if price < sma50: sell_score += 1.0

    # 4.2 M1 Momentum
    if m1_momentum_aligned("buy"): buy_score += 1.0
    if m1_momentum_aligned("sell"): sell_score += 1.0

    # 4.3 Price Action
    if is_engulfing(prev_closed, last_closed, "buy") or is_rejection_candle(last_closed, "buy"):
        buy_score += 1.0
    if is_engulfing(prev_closed, last_closed, "sell") or is_rejection_candle(last_closed, "sell"):
        sell_score += 1.0

    # 4.4 Supply/Demand
    in_demand = price_in_zone(price, demand_zones)
    in_supply = price_in_zone(price, supply_zones)
    if in_demand: buy_score += 1.5
    if in_supply: sell_score += 1.5

    # 4.5 Break & Retest
    if detect_break_and_retest(df.iloc[:-1], "buy", demand_zones, sma50, ema200):
        buy_score += 1.5
    if detect_break_and_retest(df.iloc[:-1], "sell", supply_zones, sma50, ema200):
        sell_score += 1.5

    # 4.6 StochRSI Trigger
    stoch_buy_trigger = stoch_k > stoch_d and prev_k <= prev_d and stoch_k < 80
    stoch_sell_trigger = stoch_k < stoch_d and prev_k >= prev_d and stoch_k > 20
    
    # Strict StochRSI threshold for score-based system
    if stoch_k > stoch_d and prev_k <= prev_d and stoch_k < 20: buy_score += 2.0
    if stoch_k < stoch_d and prev_k >= prev_d and stoch_k > 80: sell_score += 2.0

    log.debug(f"Current Scores - BUY: {buy_score}/10 | SELL: {sell_score}/10")

    # ── 5. Direct Trigger Evaluation ─────────────────────────────────────────
    # Buy Setup: VWAP bias (price > vwap) + StochRSI cross + Demand Zone + Trend verification (SMA50 & EMA200)
    direct_buy = price > vwap and stoch_buy_trigger and in_demand and (price > sma50 and price > ema200)

    # Sell Setup: VWAP bias (price < vwap) + StochRSI cross + Supply Zone + Trend verification (SMA50 & EMA200)
    direct_sell = price < vwap and stoch_sell_trigger and in_supply and (price < sma50 and price < ema200)

    direction = None
    if (buy_score >= 6.5 and buy_score > sell_score) or direct_buy:
        direction = "buy"
        trigger_type = "DIRECT TRIGGER" if direct_buy else f"SCORE SYSTEM ({buy_score}/10)"
        log.info(f"🎯 BUY SETUP: {trigger_type} triggered trade. price={price:.5f} | vwap={vwap:.5f} | StochRSI={stoch_k:.1f}")
    elif (sell_score >= 6.5 and sell_score > buy_score) or direct_sell:
        direction = "sell"
        trigger_type = "DIRECT TRIGGER" if direct_sell else f"SCORE SYSTEM ({sell_score}/10)"
        log.info(f"🎯 SELL SETUP: {trigger_type} triggered trade. price={price:.5f} | vwap={vwap:.5f} | StochRSI={stoch_k:.1f}")

    # ── 6. IA Sentiment Filter validation ────────────────────────────────────
    if direction in ("buy", "sell"):
        if sentiment_filter.enabled:
            log.info("Analyzing market sentiment with Gemini...")
            sentiment_score = sentiment_filter.get_market_bias()
            
            if direction == "buy" and sentiment_score < -0.2:
                log.warning(f"🚫 Technical BUY setup ignored: Bearish market sentiment (Score: {sentiment_score})")
                telegram_notifier.send_message(f"⚠️ *Trade BUY annulé par IA Sentiment*\nScore: `{sentiment_score:.2f}` (Biais Baissier)")
                return None, 0.0
            if direction == "sell" and sentiment_score > 0.2:
                log.warning(f"🚫 Technical SELL setup ignored: Bullish market sentiment (Score: {sentiment_score})")
                telegram_notifier.send_message(f"⚠️ *Trade SELL annulé par IA Sentiment*\nScore: `{sentiment_score:.2f}` (Biais Haussier)")
                return None, 0.0
                
            log.info(f"✅ Trade validated by Sentiment Filter! Score = {sentiment_score}")
        else:
            log.debug("Sentiment filter is disabled (No API key). Skipping sentiment validation.")

        return direction, atr

    return None, 0.0

# ─────────────────────────────────────────────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────────────────────────────────────────────

def run():
    log.info("═" * 70)
    log.info("  GBPUSD SCALPING BOT — Starting up")
    log.info("═" * 70)

    # Welcome message on Telegram
    telegram_notifier.send_message("🟢 *Vibe Trading Bot* démarré avec succès ! Surveillance active sur GBP/USD.")

    if not mt5_connect():
        log.error("Failed to connect to MT5. Exiting.")
        telegram_notifier.send_message("❌ *ERREUR CRITIQUE :* Impossible de se connecter au terminal MetaTrader 5 !")
        return

    # Ensure symbol is available
    if not mt5.symbol_select(SYMBOL, True):
        log.error(f"Cannot select symbol {SYMBOL}.")
        telegram_notifier.send_message(f"❌ *ERREUR CRITIQUE :* Impossible de sélectionner le symbole {SYMBOL} sur MT5 !")
        mt5.shutdown()
        return

    log.info(f"Symbol: {SYMBOL} | Risk: {RISK_PERCENT}% | ATR SL Multiplier: {ATR_SL_MULTIPLIER}x | Risk/Reward: {RISK_REWARD_RATIO}x")
    log.info(f"Session: {SESSION_START_HOUR:02d}:00–{SESSION_END_HOUR:02d}:00 ({TIMEZONE})")
    log.info("Polling every 10 seconds...")
    log.info("═" * 70)

    last_sync_time = 0
    last_heartbeat_time = 0
    last_telegram_heartbeat = time.time()
    last_trade_time = time.time()

    while True:
        try:
            check_closed_trades()
            
            # Manage break-even and near-TP close for open positions
            manage_open_trades()

            # Sync balances every 5 minutes (300 seconds)
            current_time = time.time()
            if current_time - last_sync_time > 300:
                sync_all_balances()
                last_sync_time = current_time

            # Heartbeat — signale au Dashboard que le bot est vivant
            if current_time - last_heartbeat_time > 30:
                update_bot_heartbeat()
                last_heartbeat_time = current_time

            # Active surveillance: Send "Bot Active" every hour if no trades occurred for 4 hours
            if current_time - last_trade_time >= 14400:
                if current_time - last_telegram_heartbeat > 3600:
                    telegram_notifier.send_message("ℹ️ *Vibe Trading Bot* : Actif et opérationnel. Aucune transaction détectée sur les 4 dernières heures.")
                    last_telegram_heartbeat = current_time

            # ── Session gate ────────────────────────────────────────────────
            if not in_trading_session():
                log.debug("Outside trading session. Waiting...")
                time.sleep(30)
                continue

            # ── Dashboard control gate ────────────────────────────────────
            if not get_trading_enabled():
                log.info("🔴 Trading PAUSÉ via Dashboard. En attente de réactivation...")
                time.sleep(30)
                continue

            # ── Daily limit gate ─────────────────────────────────────────────
            if not daily.can_trade():
                time.sleep(60)
                continue

            # ── News filter gate ─────────────────────────────────────────────
            is_news, news_title = news_filter.is_news_window()
            if is_news:
                if news_title not in daily.notified_news:
                    telegram_notifier.send_message(
                        f"⚠️ *Trading Suspendu (News)*\n"
                        f"Le bot ne prendra pas de trade pour le moment à cause de l'annonce :\n"
                        f"`{news_title}`"
                    )
                    daily.notified_news.add(news_title)
                time.sleep(60)
                continue

            # ── Open position gate ───────────────────────────────────────────
            open_pos = get_open_position(MAGIC_NUMBER)
            if open_pos is not None:
                log.debug(f"Position already open: {open_pos.ticket}. Waiting for close.")
                time.sleep(POLL_INTERVAL)
                continue

            # ── Signal evaluation ────────────────────────────────────────────
            signal, atr = evaluate_signal()

            if signal in ("buy", "sell"):
                if place_order_for_all_users(signal, atr):
                    sl_p = atr * ATR_SL_MULTIPLIER / PIP_VALUE
                    tp_p = sl_p * RISK_REWARD_RATIO
                    telegram_notifier.send_message(f"🚀 *Trade {signal.upper()} ouvert avec succès sur GBP/USD !*\nSL: `{sl_p:.1f}` pips | TP: `{tp_p:.1f}` pips")
                    last_trade_time = current_time
                else:
                    telegram_notifier.send_message(f"❌ *Erreur de transaction :* Signal {signal.upper()} détecté mais l'ordre n'a pas pu être placé sur les comptes.")

            time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            log.info("Bot stopped by user.")
            telegram_notifier.send_message("🔴 *Vibe Trading Bot* arrêté manuellement par l'utilisateur.")
            break
        except Exception as e:
            log.error(f"Unexpected error: {e}", exc_info=True)
            telegram_notifier.send_message(f"⚠️ *Alerte Système :* Une erreur inattendue est survenue : `{str(e)[:150]}`")
            time.sleep(30)

    mt5.shutdown()
    log.info("MT5 disconnected. Bot shut down.")

# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    run()
