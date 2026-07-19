"""
================================================================================
BTC SCALP BOT - MT5 (Fusion Markets Demo)
================================================================================
Strategy   : EMA9/EMA21 crossover + RSI filter + ATR volatility filter
Timeframe  : M1 (scalp) with M5 confirmation
Risk model : Aggressive (2% risk/trade) + daily loss circuit breaker
Broker     : Fusion Markets (MT5) - DEMO account only until validated

REQUIREMENTS (run on Windows, since MetaTrader5 package needs the MT5 terminal):
    pip install MetaTrader5 pandas numpy

IMPORTANT REALITY CHECK:
- No strategy guarantees 80% win rate. This bot targets a realistic edge
  (aim: 45-58% win rate with 1:1.5+ reward:risk = still profitable long term).
- ALWAYS run on DEMO for at least 200-300 trades / 4-6 weeks before considering
  real money. Log everything and review weekly.
================================================================================
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import time
import csv
import os
from datetime import datetime, timezone

# Load environment variables
from dotenv import load_dotenv
from supabase import create_client, Client

# Try loading from local directory first, then fallback to backend directory
if os.path.exists(".env"):
    load_dotenv(".env")
elif os.path.exists("../backend/.env"):
    load_dotenv("../backend/.env")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase_client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("✅ Supabase konekte ak siksè pou Bot Crypto a!")
    except Exception as e:
        print(f"❌ Echèk koneksyon Supabase: {e}")

# ============================== CONFIGURATION ==============================

CONFIG = {
    "symbol": "BTCUSD",
    "magic_number": 20260719,          # unique ID for this bot's trades
    "timeframe": mt5.TIMEFRAME_M1,      # entry timeframe
    "confirm_timeframe": mt5.TIMEFRAME_M5,  # trend confirmation timeframe

    # --- Indicators ---
    "ema_fast": 9,
    "ema_slow": 21,
    "rsi_period": 14,
    "rsi_overbought": 70,
    "rsi_oversold": 30,
    "atr_period": 14,
    "atr_min_pips": 15,     # skip trading if volatility too low (choppy/no edge)

    # --- Risk management ---
    "risk_percent": 2.0,        # % of balance risked per trade (AGGRESSIVE - see warning)
    "sl_atr_multiplier": 1.2,   # stop loss = 1.2x ATR
    "tp_atr_multiplier": 2.0,   # take profit = 2.0x ATR (R:R ~1:1.6)
    "max_daily_loss_percent": 6.0,   # circuit breaker: stop bot for the day
    "max_daily_trades": 15,          # hard cap to prevent overtrading
    "max_open_positions": 1,         # only 1 position at a time for this bot

    # --- Timing ---
    "check_interval_seconds": 5,     # how often to check for new candle/signal

    # --- Logging ---
    "log_file": "trade_log.csv",

    # --- Multiple Instances ---
    "terminal_path": "",  # Path to the specific MT5 terminal.exe if running multiple instances
}

# ============================== MT5 CONNECTION ==============================

def connect_mt5():
    """Initialize connection to the MT5 terminal (must already be logged
    into the Fusion Markets demo account inside the MT5 app itself)."""
    terminal_path = CONFIG.get("terminal_path")
    
    if terminal_path:
        print(f"Ap eseye konekte ak MT5 nan chemen: {terminal_path}")
        initialized = mt5.initialize(path=terminal_path)
    else:
        initialized = mt5.initialize()

    if not initialized:
        raise RuntimeError(f"Echèk konèksyon MT5: {mt5.last_error()}")

    account_info = mt5.account_info()
    if account_info is None:
        raise RuntimeError("Pa gen kont ki konekte nan MT5. Louvri MT5 e login sou kont demo Fusion Markets la anvan.")

    print("=" * 60)
    print(f"Konekte sou kont: {account_info.login} ({account_info.server})")
    print(f"Balans: {account_info.balance} {account_info.currency}")
    print(f"Mode: {'DEMO' if account_info.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO else 'REAL - ATANSYON!'}")
    print("=" * 60)

    symbol_info = mt5.symbol_info(CONFIG["symbol"])
    if symbol_info is None:
        raise RuntimeError(f"Senbòl {CONFIG['symbol']} pa disponib. Verifye non l nan Market Watch.")
    if not symbol_info.visible:
        mt5.symbol_select(CONFIG["symbol"], True)

    return account_info


# ============================== DATA / INDICATORS ==============================

def get_candles(symbol, timeframe, count=200):
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
    if rates is None or len(rates) == 0:
        return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df


def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()


def rsi(series, period):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def atr(df, period):
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period).mean()


def build_indicators(df):
    df = df.copy()
    df["ema_fast"] = ema(df["close"], CONFIG["ema_fast"])
    df["ema_slow"] = ema(df["close"], CONFIG["ema_slow"])
    df["rsi"] = rsi(df["close"], CONFIG["rsi_period"])
    df["atr"] = atr(df, CONFIG["atr_period"])
    return df


# ============================== SIGNAL LOGIC ==============================

def get_trend_bias(symbol):
    """Use M5 EMA relationship to decide overall trend direction.
    We only take trades in the direction of the higher timeframe trend."""
    df5 = get_candles(symbol, CONFIG["confirm_timeframe"], 100)
    if df5 is None or len(df5) < CONFIG["ema_slow"] + 5:
        return None
    df5 = build_indicators(df5)
    last = df5.iloc[-1]
    if last["ema_fast"] > last["ema_slow"]:
        return "BUY"
    elif last["ema_fast"] < last["ema_slow"]:
        return "SELL"
    return None


def generate_signal(symbol):
    """
    Core scalp logic (M1):
      BUY  -> EMA9 crosses above EMA21, RSI between 40-70 (momentum, not overbought),
              ATR above minimum threshold (enough volatility to be worth trading),
              M5 trend bias also BUY.
      SELL -> mirror conditions.
    """
    df = get_candles(symbol, CONFIG["timeframe"], 100)
    if df is None or len(df) < CONFIG["ema_slow"] + 5:
        return None, None

    df = build_indicators(df)
    prev, last = df.iloc[-2], df.iloc[-1]

    point = mt5.symbol_info(symbol).point
    atr_pips = last["atr"] / point / 10  # rough pip conversion for BTCUSD

    if atr_pips < CONFIG["atr_min_pips"]:
        return None, None  # market too quiet, skip

    trend_bias = get_trend_bias(symbol)
    if trend_bias is None:
        return None, None

    crossed_up = prev["ema_fast"] <= prev["ema_slow"] and last["ema_fast"] > last["ema_slow"]
    crossed_down = prev["ema_fast"] >= prev["ema_slow"] and last["ema_fast"] < last["ema_slow"]

    if crossed_up and trend_bias == "BUY" and 40 <= last["rsi"] <= CONFIG["rsi_overbought"]:
        return "BUY", last["atr"]

    if crossed_down and trend_bias == "SELL" and CONFIG["rsi_oversold"] <= last["rsi"] <= 60:
        return "SELL", last["atr"]

    return None, None


# ============================== RISK / POSITION SIZING ==============================

def calculate_lot_size(symbol, sl_distance_price):
    """Position size so that if SL is hit, loss = risk_percent of balance."""
    account = mt5.account_info()
    symbol_info = mt5.symbol_info(symbol)

    risk_amount = account.balance * (CONFIG["risk_percent"] / 100)

    tick_value = symbol_info.trade_tick_value
    tick_size = symbol_info.trade_tick_size
    if tick_size == 0:
        return symbol_info.volume_min

    value_per_price_unit = tick_value / tick_size
    loss_per_lot = sl_distance_price * value_per_price_unit

    if loss_per_lot <= 0:
        return symbol_info.volume_min

    lot = risk_amount / loss_per_lot
    lot = max(symbol_info.volume_min, min(lot, symbol_info.volume_max))
    step = symbol_info.volume_step
    lot = round(lot / step) * step
    return round(lot, 2)


# ============================== DAILY GUARD (CIRCUIT BREAKER) ==============================

class DailyGuard:
    def __init__(self):
        self.day = datetime.now(timezone.utc).date()
        self.start_balance = None
        self.trades_today = 0

    def reset_if_new_day(self, balance):
        today = datetime.now(timezone.utc).date()
        if today != self.day:
            self.day = today
            self.start_balance = balance
            self.trades_today = 0
            print(f"[GUARD] Nouvo jou. Balans depa: {balance}")

    def can_trade(self, balance):
        if self.start_balance is None:
            self.start_balance = balance

        loss_percent = ((self.start_balance - balance) / self.start_balance) * 100
        if loss_percent >= CONFIG["max_daily_loss_percent"]:
            print(f"[GUARD] ARÈ! Pèt jodi a rive {loss_percent:.2f}% "
                  f"(limit: {CONFIG['max_daily_loss_percent']}%). Bot kanpe pou rès jounen an.")
            return False

        if self.trades_today >= CONFIG["max_daily_trades"]:
            print(f"[GUARD] Limit {CONFIG['max_daily_trades']} trade/jou atenn. Bot kanpe.")
            return False

        return True

    def record_trade(self):
        self.trades_today += 1


# ============================== ORDER EXECUTION ==============================

def has_open_position(symbol):
    positions = mt5.positions_get(symbol=symbol)
    if positions is None:
        return False
    return len([p for p in positions if p.magic == CONFIG["magic_number"]]) >= CONFIG["max_open_positions"]


def place_order(symbol, direction, atr_value):
    symbol_info = mt5.symbol_info(symbol)
    tick = mt5.symbol_info_tick(symbol)

    price = tick.ask if direction == "BUY" else tick.bid
    sl_distance = atr_value * CONFIG["sl_atr_multiplier"]
    tp_distance = atr_value * CONFIG["tp_atr_multiplier"]

    if direction == "BUY":
        sl = price - sl_distance
        tp = price + tp_distance
        order_type = mt5.ORDER_TYPE_BUY
    else:
        sl = price + sl_distance
        tp = price - tp_distance
        order_type = mt5.ORDER_TYPE_SELL

    lot = calculate_lot_size(symbol, sl_distance)

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot,
        "type": order_type,
        "price": price,
        "sl": round(sl, symbol_info.digits),
        "tp": round(tp, symbol_info.digits),
        "deviation": 20,
        "magic": CONFIG["magic_number"],
        "comment": "btc_scalp_bot",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"[ERè] Order pa pase: {result.retcode} - {result.comment}")
        return None

    print(f"[TRADE] {direction} {lot} lot @ {price} | SL={sl:.2f} TP={tp:.2f}")
    log_trade(direction, lot, price, sl, tp)
    return result


def log_trade(direction, lot, price, sl, tp):
    file_exists = os.path.isfile(CONFIG["log_file"])
    with open(CONFIG["log_file"], "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "direction", "lot", "price", "sl", "tp"])
        writer.writerow([datetime.now(timezone.utc).isoformat(), direction, lot, price, sl, tp])


# ============================== MAIN LOOP ==============================

def run():
    account = connect_mt5()
    guard = DailyGuard()
    guard.start_balance = account.balance

    last_candle_time = None
    last_heartbeat_time = 0

    print("Bot ap kòmanse... (Ctrl+C pou kanpe l)")

    try:
        while True:
            # ─── HEARTBEAT ───
            now = time.time()
            if now - last_heartbeat_time >= 25:  # Send heartbeat every 25 seconds
                last_heartbeat_time = now
                if supabase_client:
                    try:
                        utc_now = datetime.now(timezone.utc).isoformat()
                        supabase_client.table("bot_control").upsert({
                            "id": 2,
                            "last_heartbeat": utc_now
                        }).execute()
                    except Exception as e:
                        print(f"[SUPABASE] Erè voye heartbeat: {e}")

            # ─── STATUS CHECK (START/STOP) ───
            trading_enabled = True
            if supabase_client:
                try:
                    resp = supabase_client.table("bot_control").select("trading_enabled").eq("id", 2).execute()
                    if resp.data:
                        trading_enabled = resp.data[0].get("trading_enabled", False)
                except Exception as e:
                    print(f"[SUPABASE] Erè tcheke bot_control: {e}")

            if not trading_enabled:
                print("[INFO] Trading desantive sou Dashboard la (id=2). Ap tann...")
                time.sleep(10)
                continue

            account = mt5.account_info()
            guard.reset_if_new_day(account.balance)

            if not guard.can_trade(account.balance):
                time.sleep(60)
                continue

            df = get_candles(CONFIG["symbol"], CONFIG["timeframe"], 5)
            if df is None:
                time.sleep(CONFIG["check_interval_seconds"])
                continue

            current_candle_time = df.iloc[-1]["time"]

            # Only evaluate once per new closed candle to avoid re-signaling mid-candle
            if current_candle_time != last_candle_time:
                last_candle_time = current_candle_time

                if not has_open_position(CONFIG["symbol"]):
                    signal, atr_value = generate_signal(CONFIG["symbol"])
                    if signal:
                        place_order(CONFIG["symbol"], signal, atr_value)
                        guard.record_trade()
                else:
                    print("[INFO] Pozisyon deja ouvri, ap tann li fèmen.")

            time.sleep(CONFIG["check_interval_seconds"])

    except KeyboardInterrupt:
        print("\nBot kanpe pa itilizatè a.")
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    run()
