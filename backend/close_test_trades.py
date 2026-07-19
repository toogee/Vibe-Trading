# -*- coding: utf-8 -*-
"""
Script to close all open test trades on MT5 accounts and update Supabase.
Also sends a Telegram notification.
"""
import MetaTrader5 as mt5
import logging
import sys
import os
import requests

# Add backend to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import get_active_users, get_user_mt5_account, supabase
from security import decrypt_password
from datetime import datetime

# CONFIG
SYMBOL = "GBPUSD"
MAGIC_NUMBER = 20240601

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
log = logging.getLogger("CloseTest")

def send_telegram(message):
    token = os.getenv("TELEGRAM_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if token and chat_id:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        try:
            resp = requests.post(url, json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown"
            })
            if resp.status_code == 200:
                log.info("Telegram notification sent successfully.")
            else:
                log.error(f"Telegram API error: {resp.status_code} - {resp.text}")
        except Exception as e:
            log.error(f"Error sending Telegram notification: {e}")
    else:
        log.warning("Telegram credentials missing, skipping notification.")

def run_close():
    if not mt5.initialize():
        log.error(f"❌ Failed to initialize MT5: {mt5.last_error()}")
        return
    log.info("✅ MT5 initialized.")

    active_users = get_active_users()
    if not active_users:
        log.error("❌ No active users in Supabase.")
        mt5.shutdown()
        return

    closed_count = 0
    telegram_messages = []

    for user_id in active_users:
        mt5_acc = get_user_mt5_account(user_id)
        if not mt5_acc:
            continue

        login = int(mt5_acc['login_id'])
        server = mt5_acc['server_name']
        log.info(f"Connecting to account {login} on {server}...")

        try:
            plain_password = decrypt_password(mt5_acc['encrypted_password'])
        except Exception as e:
            log.error(f"❌ Failed to decrypt password for {login}: {e}")
            continue

        if not mt5.login(login=login, password=plain_password, server=server):
            log.error(f"❌ Login failed for {login}: {mt5.last_error()}")
            continue

        # Get open positions
        positions = mt5.positions_get(symbol=SYMBOL)
        if not positions:
            log.info(f"No open positions for {login}.")
            continue

        # Filter by magic number
        bot_positions = [p for p in positions if p.magic == MAGIC_NUMBER]
        if not bot_positions:
            log.info(f"No open test positions (magic={MAGIC_NUMBER}) for {login}.")
            continue

        for pos in bot_positions:
            tick = mt5.symbol_info_tick(SYMBOL)
            if tick is None:
                log.error(f"Could not get tick for {SYMBOL}")
                continue

            order_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
            price = tick.bid if pos.type == mt5.POSITION_TYPE_BUY else tick.ask

            # Detect filling mode
            sym_info = mt5.symbol_info(SYMBOL)
            filling_mode = mt5.ORDER_FILLING_IOC
            if sym_info.filling_mode & 1:
                filling_mode = mt5.ORDER_FILLING_FOK
            elif sym_info.filling_mode & 2:
                filling_mode = mt5.ORDER_FILLING_IOC
            elif sym_info.filling_mode & 4:
                filling_mode = mt5.ORDER_FILLING_RETURN

            request = {
                "action":       mt5.TRADE_ACTION_DEAL,
                "symbol":       SYMBOL,
                "volume":       pos.volume,
                "type":         order_type,
                "position":     pos.ticket,
                "price":        price,
                "deviation":    20,
                "magic":        MAGIC_NUMBER,
                "comment":      "Close_ForceTest",
                "type_time":    mt5.ORDER_TIME_GTC,
                "type_filling": filling_mode,
            }

            result = mt5.order_send(request)
            if result is None:
                log.error(f"❌ order_send() returned None for ticket {pos.ticket}")
            elif result.retcode == mt5.TRADE_RETCODE_DONE:
                log.info(f"✅ Position {pos.ticket} closed successfully on account {login}!")
                closed_count += 1
                
                # Fetch recent deals to get the actual closed profit
                deal_profit = 0.0
                deals = mt5.history_deals_get(position=pos.ticket)
                if deals:
                    # Sum profit of out deals for this position
                    deal_profit = sum(d.profit for d in deals if d.entry == mt5.DEAL_ENTRY_OUT)
                else:
                    # Fallback estimate
                    if pos.type == mt5.POSITION_TYPE_BUY:
                        deal_profit = (price - pos.price_open) * pos.volume * 100000
                    else:
                        deal_profit = (pos.price_open - price) * pos.volume * 100000
                
                deal_profit = round(deal_profit, 2)
                
                # Update Supabase
                trades = supabase.table("trades").select("*").eq("user_id", user_id).eq("status", "OPEN").execute()
                if trades.data:
                    # Select the first matching open trade
                    trade_id = trades.data[0]["id"]
                    status_str = "WIN" if deal_profit >= 0 else "LOSS"
                    supabase.table("trades").update({
                        "status": status_str,
                        "profit": deal_profit,
                        "close_time": datetime.utcnow().isoformat()
                    }).eq("id", trade_id).execute()
                    log.info(f"Updated Supabase trade {trade_id} to status {status_str} with profit {deal_profit}")
                
                telegram_messages.append(
                    f"Compte: `{login}` ({'Real' if mt5_acc['server_name'] == 'OctaFX-Real' else 'Demo'})\n"
                    f"Ticket: `{pos.ticket}`\n"
                    f"Profit: `${deal_profit:.2f}`"
                )
            else:
                log.error(f"❌ Failed to close position {pos.ticket}: {result.retcode} - {result.comment}")

    mt5.shutdown()
    log.info("MT5 disconnected.")

    # Send Telegram summary
    if closed_count > 0:
        msg = f"🔴 *Vibe Trading Bot* : Trades de test fermés manuellement !\n\n" + "\n\n".join(telegram_messages)
        send_telegram(msg)
    else:
        log.info("No trades were closed.")

if __name__ == "__main__":
    run_close()
