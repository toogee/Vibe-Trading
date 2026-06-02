# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

"""Script pou sync trades feme nan Supabase — korije profit $0.00"""
import sys, os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '.')
import MetaTrader5 as mt5
from db import get_active_users, get_user_mt5_account, supabase
from security import decrypt_password
from datetime import datetime, timezone
import pytz

# Connecter MT5
mt5.initialize()
users = get_active_users()
acc = get_user_mt5_account(users[0])
mt5.login(int(acc['login_id']), decrypt_password(acc['encrypted_password']), acc['server_name'])

print("=== SYNC TRADES FERMES → SUPABASE ===\n")

# Chercher dans l'historique MT5 d'aujourd'hui
tz = pytz.timezone("Europe/London")
today = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
today_utc = today.astimezone(pytz.utc)
now_utc = datetime.now(pytz.utc)

deals = mt5.history_deals_get(today_utc, now_utc)
if deals:
    print(f"Deals trouves dans historique MT5 : {len(deals)}")
    for deal in deals:
        typ = "BUY" if deal.type == 0 else "SELL" if deal.type == 1 else "OTHER"
        print(f"  Deal {deal.ticket} | {typ} | profit={deal.profit:.2f} | magic={deal.magic}")
else:
    print("Aucun deal dans l'historique aujourd'hui.")

print()

# Chercher les trades OPEN dans Supabase
open_trades = supabase.table("trades").select("*").eq("status", "OPEN").execute()
print(f"Trades OPEN dans Supabase : {len(open_trades.data)}")
for t in open_trades.data:
    print(f"  ID={t['id']} | {t['type']} {t['symbol']} @ {t['entry']} | profit={t['profit']}")

print()

# Verifier si le trade test (ticket 56905453347) est dans l'historique
if deals:
    for deal in deals:
        if deal.magic == 20240601 and deal.profit != 0:
            print(f"Trade Vibe trouve: ticket={deal.ticket} profit={deal.profit:.2f}")
            # Mettre a jour le premier trade OPEN dans Supabase
            if open_trades.data:
                trade_id = open_trades.data[0]['id']
                result = supabase.table("trades").update({
                    "status": "WIN" if deal.profit > 0 else "LOSS",
                    "profit": round(deal.profit, 2),
                    "close_time": datetime.now(timezone.utc).isoformat()
                }).eq("id", trade_id).execute()
                print(f"✅ Trade {trade_id} mis a jour → {'WIN' if deal.profit > 0 else 'LOSS'} ${deal.profit:.2f}")
            break
    else:
        print("Aucun trade Vibe avec profit trouve dans historique.")
        # Mettre a jour manuellement basé sur ce qu'on sait (TP = 1.34718, entry = 1.34607)
        # Profit approximatif = 11 pips * 0.02 lots = ~$0.22 pour un micro lot
        if open_trades.data:
            print("\nMise a jour manuelle basee sur TP atteint...")
            # Verifier l'equity actuelle
            acc_info = mt5.account_info()
            print(f"Balance actuelle : {acc_info.balance:.2f}")
            # Chercher dans closed orders
            orders = mt5.history_orders_get(today_utc, now_utc)
            if orders:
                for o in orders:
                    print(f"  Order {o.ticket} | state={o.state} | profit n/a")

print()
mt5.shutdown()
print("Done.")
