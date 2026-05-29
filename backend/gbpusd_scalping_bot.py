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
from db import get_active_users, get_user_mt5_account, save_trade, update_mt5_status, update_mt5_balance
from security import decrypt_password

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

SYMBOL          = "GBPUSD"
MAGIC_NUMBER    = 20240601          # Unique ID for this bot's trades
RISK_PERCENT    = 1.0               # Risk 1% of balance per trade
TAKE_PROFIT_PIP = 11                # TP in pips
STOP_LOSS_PIP   = 5                 # SL in pips
PIP_VALUE       = 0.0001            # 1 pip for GBPUSD (5-digit broker)
MAX_DAILY_TRADES= 3
MAX_DAILY_LOSSES= 2

# Session: 06:00–17:00 London time (UTC+1 BST / UTC+0 GMT)
SESSION_START_HOUR = 6
SESSION_END_HOUR   = 17
TIMEZONE           = "Europe/London"

# Spread filter
MAX_SPREAD_PIPS    = 1.5

# News filter: minutes before/after high-impact event to avoid trading
NEWS_BUFFER_MINUTES = 30

# Indicators
SMA_PERIOD = 50
EMA_PERIOD = 200

# Swing detection lookback (bars each side)
SWING_LOOKBACK = 5

# Supply/Demand zone tolerance in pips
ZONE_TOLERANCE_PIPS = 5

# Consolidation / low-volatility filter
MIN_CANDLE_BODY_PIPS = 2.0   # Minimum candle body to consider non-weak
ADR_CONSOLIDATION_RATIO = 0.3  # If candle range < 30% of ADR → consolidating

# Trend detection lookback in M5 bars
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
        self.halted       = False
        log.info("Daily state reset.")

    def check_date_rollover(self):
        today = datetime.now(pytz.timezone(TIMEZONE)).date()
        if today != self.date:
            self.reset()

    def can_trade(self) -> bool:
        self.check_date_rollover()
        if self.halted:
            log.info("Trading halted for today (2 losses reached).")
            return False
        if self.trade_count >= MAX_DAILY_TRADES:
            log.info("Max daily trades reached.")
            return False
        return True

    def record_trade_open(self):
        self.trade_count += 1
        log.info(f"Trade opened. Daily count: {self.trade_count}/{MAX_DAILY_TRADES}")

    def record_trade_result(self, profit: float):
        if profit < 0:
            self.loss_count += 1
            log.info(f"Loss recorded. Daily losses: {self.loss_count}/{MAX_DAILY_LOSSES}")
            if self.loss_count >= MAX_DAILY_LOSSES:
                self.halted = True
                log.warning("2 losses hit — trading halted for the rest of the day.")

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

    def is_news_window(self) -> bool:
        """Return True if current time is within the news buffer window."""
        self._ensure_fresh()
        now = datetime.now(pytz.timezone(TIMEZONE))
        buffer = timedelta(minutes=NEWS_BUFFER_MINUTES)
        for event in self._cached_events:
            event_time = event["time"]
            if (event_time - buffer) <= now <= (event_time + buffer):
                log.warning(f"NEWS WINDOW: {event['currency']} '{event['title']}' at {event_time.strftime('%H:%M')} — skipping trade.")
                return True
        return False

news_filter = NewsFilter()

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

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["sma50"]  = df["close"].rolling(SMA_PERIOD).mean()
    df["ema200"] = df["close"].ewm(span=EMA_PERIOD, adjust=False).mean()
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

def place_order_for_all_users(direction: str) -> bool:
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
            
            # Calculate dynamic lot size based on balance
            account_info = mt5.account_info()
            if account_info is None:
                continue
                
            balance = account_info.balance
            dynamic_lot = calculate_lot_size(balance, RISK_PERCENT, STOP_LOSS_PIP, sym_info)

            if direction == "buy":
                price    = tick.ask
                sl       = price - STOP_LOSS_PIP   * PIP_VALUE
                tp       = price + TAKE_PROFIT_PIP * PIP_VALUE
                order_type = mt5.ORDER_TYPE_BUY
            else:
                price    = tick.bid
                sl       = price + STOP_LOSS_PIP   * PIP_VALUE
                tp       = price - TAKE_PROFIT_PIP * PIP_VALUE
                order_type = mt5.ORDER_TYPE_SELL

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
                "type_filling": mt5.ORDER_FILLING_IOC,
            }

            result = mt5.order_send(request)
            if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
                log.error(f"Order failed for user {login}: {result}")
                continue

            log.info(f"✅ ORDER PLACED for {login} | {direction.upper()} {SYMBOL} @ {price:.5f} | Lot={dynamic_lot} | SL={sl:.5f} | TP={tp:.5f}")
            
            # Save trade to Supabase
            save_trade({
                "user_id": user_id,
                "symbol": SYMBOL,
                "type": direction.upper(),
                "entry": price,
                "sl": sl,
                "tp": tp,
                "profit": 0,
                "status": "OPEN",
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

_seen_deal_tickets: set = set()

def check_closed_trades():
    """Check history for newly closed trades and update daily loss counter."""
    tz = pytz.timezone(TIMEZONE)
    today_start = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    today_start_utc = today_start.astimezone(pytz.utc)

    from_date = today_start_utc
    to_date   = datetime.now(pytz.utc)
    deals = mt5.history_deals_get(from_date, to_date)
    if deals is None:
        return

    for deal in deals:
        if deal.magic != MAGIC_NUMBER:
            continue
        if deal.ticket in _seen_deal_tickets:
            continue
        if deal.type not in (mt5.DEAL_TYPE_BUY, mt5.DEAL_TYPE_SELL):
            continue
        _seen_deal_tickets.add(deal.ticket)
        profit = deal.profit
        log.info(f"Closed trade ticket={deal.ticket} | profit={profit:.2f}")
        daily.record_trade_result(profit)

# ─────────────────────────────────────────────────────────────────────────────
# BREAK-EVEN MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────

def manage_open_trades_breakeven():
    """
    Checks if any open positions are > +6 pips in profit.
    If so, moves the Stop-Loss to the entry price (Break-Even) to secure capital.
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
                
                # Check for BUY
                if pos.type == mt5.ORDER_TYPE_BUY:
                    profit_pips = (pos.price_current - pos.price_open) / PIP_VALUE
                    # If profit >= 6 pips and SL is not already at or above entry
                    if profit_pips >= 6.0 and pos.sl < pos.price_open:
                        request = {
                            "action": mt5.TRADE_ACTION_SLTP,
                            "position": pos.ticket,
                            "symbol": SYMBOL,
                            "sl": pos.price_open,
                            "tp": pos.tp
                        }
                        res = mt5.order_send(request)
                        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                            log.info(f"Break-even applied for user {login} BUY {pos.ticket}")
                            
                # Check for SELL
                elif pos.type == mt5.ORDER_TYPE_SELL:
                    profit_pips = (pos.price_open - pos.price_current) / PIP_VALUE
                    # If profit >= 6 pips and SL is not already at or below entry
                    if profit_pips >= 6.0 and (pos.sl > pos.price_open or pos.sl == 0.0):
                        request = {
                            "action": mt5.TRADE_ACTION_SLTP,
                            "position": pos.ticket,
                            "symbol": SYMBOL,
                            "sl": pos.price_open,
                            "tp": pos.tp
                        }
                        res = mt5.order_send(request)
                        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                            log.info(f"Break-even applied for user {login} SELL {pos.ticket}")
        except Exception as e:
            log.error(f"Error checking break-even for user {user_id}: {e}")

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

def evaluate_signal() -> Optional[str]:
    """
    Full signal evaluation pipeline.
    Returns: 'buy', 'sell', or None.
    """
    # ── 1. Fetch M5 data ────────────────────────────────────────────────────
    df_m5_raw = get_bars(mt5.TIMEFRAME_M5, 300)
    if df_m5_raw is None or len(df_m5_raw) < EMA_PERIOD + 50:
        log.debug("Not enough M5 data.")
        return None

    df_m5 = add_indicators(df_m5_raw)

    # Use only rows where indicators are valid
    df = df_m5.dropna(subset=["sma50", "ema200"]).copy()
    if len(df) < TREND_LOOKBACK + 10:
        return None

    # ── 2. Trend ─────────────────────────────────────────────────────────────
    trend = detect_trend(df)
    log.info(f"M5 Trend: {trend}")
    if trend == "ranging":
        log.info("Ranging market — no trade.")
        return None

    # ── 3. Consolidation ─────────────────────────────────────────────────────
    if is_consolidating(df, lookback=10):
        log.info("M5 consolidating — skipping.")
        return None

    # ── 4. Indicators at last closed bar ─────────────────────────────────────
    last_closed = df.iloc[-2]  # -1 is still forming
    prev_closed = df.iloc[-3]
    sma50  = last_closed["sma50"]
    ema200 = last_closed["ema200"]
    price  = last_closed["close"]

    # ── 5. Supply / Demand zones ─────────────────────────────────────────────
    demand_zones, supply_zones = detect_zones(df.iloc[:-1])  # exclude current bar

    # ── 6. Direction-specific checks ─────────────────────────────────────────
    for direction in (["buy"] if trend == "bullish" else ["sell"]):

        zones = demand_zones if direction == "buy" else supply_zones

        # 6a. Price must be near a key level (zone, SMA50, or EMA200)
        near_zone    = price_in_zone(price, zones)
        near_sma50   = price_near_level(price, sma50, 4)
        near_ema200  = price_near_level(price, ema200, 4)

        if not (near_zone or near_sma50 or near_ema200):
            log.debug(f"[{direction.upper()}] Price not near key level.")
            continue

        # 6b. Break & Retest
        if not detect_break_and_retest(df, direction, zones, sma50, ema200):
            log.debug(f"[{direction.upper()}] No B&R setup detected.")
            continue

        # 6c. Rejection candle on last_closed bar
        if not is_rejection_candle(last_closed, direction):
            log.debug(f"[{direction.upper()}] No rejection candle.")
            continue

        # 6d. Engulfing candle — MUST be fully closed (use last_closed over prev_closed)
        if not is_engulfing(prev_closed, last_closed, direction):
            log.debug(f"[{direction.upper()}] No engulfing confirmation.")
            continue

        # 6e. M1 momentum alignment
        if not m1_momentum_aligned(direction):
            log.debug(f"[{direction.upper()}] M1 not aligned.")
            continue

        log.info(f"🎯 HIGH-PROBABILITY SETUP: {direction.upper()} | near_zone={near_zone} | near_sma50={near_sma50} | near_ema200={near_ema200}")
        return direction

    return None

# ─────────────────────────────────────────────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────────────────────────────────────────────

def run():
    log.info("═" * 70)
    log.info("  GBPUSD SCALPING BOT — Starting up")
    log.info("═" * 70)

    if not mt5_connect():
        log.error("Failed to connect to MT5. Exiting.")
        return

    # Ensure symbol is available
    if not mt5.symbol_select(SYMBOL, True):
        log.error(f"Cannot select symbol {SYMBOL}.")
        mt5.shutdown()
        return

    log.info(f"Symbol: {SYMBOL} | Risk: {RISK_PERCENT}% | TP: {TAKE_PROFIT_PIP}p | SL: {STOP_LOSS_PIP}p")
    log.info(f"Session: {SESSION_START_HOUR:02d}:00–{SESSION_END_HOUR:02d}:00 ({TIMEZONE})")
    log.info("Polling every 10 seconds...")
    log.info("═" * 70)

    last_sync_time = 0

    while True:
        try:
            check_closed_trades()
            
            # Manage break-even for open positions
            manage_open_trades_breakeven()

            # Sync balances every 5 minutes (300 seconds)
            current_time = time.time()
            if current_time - last_sync_time > 300:
                sync_all_balances()
                last_sync_time = current_time

            # ── Session gate ────────────────────────────────────────────────
            if not in_trading_session():
                log.debug("Outside trading session. Waiting...")
                time.sleep(30)
                continue

            # ── Daily limit gate ─────────────────────────────────────────────
            if not daily.can_trade():
                time.sleep(60)
                continue

            # ── News filter gate ─────────────────────────────────────────────
            if news_filter.is_news_window():
                time.sleep(60)
                continue

            # ── Open position gate ───────────────────────────────────────────
            open_pos = get_open_position(MAGIC_NUMBER)
            if open_pos is not None:
                log.debug(f"Position already open: {open_pos.ticket}. Waiting for close.")
                time.sleep(POLL_INTERVAL)
                continue

            # ── Signal evaluation ────────────────────────────────────────────
            signal = evaluate_signal()

            if signal in ("buy", "sell"):
                place_order_for_all_users(signal)

            time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            log.info("Bot stopped by user.")
            break
        except Exception as e:
            log.error(f"Unexpected error: {e}", exc_info=True)
            time.sleep(30)

    mt5.shutdown()
    log.info("MT5 disconnected. Bot shut down.")

# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    run()
