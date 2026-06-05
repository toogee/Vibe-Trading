# -*- coding: utf-8 -*-
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '.')

import MetaTrader5 as mt5
from db import get_active_users, get_user_mt5_account
from security import decrypt_password
from datetime import datetime

if not mt5.initialize():
    print(f"Erreur MT5: {mt5.last_error()}")
    sys.exit(1)

users = get_active_users()
acc = get_user_mt5_account(users[0])
login = int(acc['login_id'])
pwd = decrypt_password(acc['encrypted_password'])
server = acc['server_name']

if not mt5.login(login=login, password=pwd, server=server):
    print(f"Echec login {login}")
    sys.exit(1)

info = mt5.account_info()
print(f"Compte: {login} | Balance: {info.balance}")

# DUMP COMPLET SANS FILTRE DE DATE (depuis 2020 jusqu'a 2030)
from_dt = datetime(2020, 1, 1)
to_dt = datetime(2030, 1, 1)
deals = mt5.history_deals_get(from_dt, to_dt)

print("\n=== TOUS LES DEALS DE FERMETURE DU COMPTE ===")
if deals:
    count = 0
    for d in deals:
        if d.entry == mt5.DEAL_ENTRY_IN: continue
        if d.profit == 0 and d.reason != mt5.DEAL_REASON_TP and d.reason != mt5.DEAL_REASON_SL: continue # skip deposits
        
        # d.time is timestamp
        dt = datetime.fromtimestamp(d.time).strftime("%Y-%m-%d %H:%M:%S")
        type_str = "BUY" if d.type == mt5.DEAL_TYPE_BUY else "SELL" if d.type == mt5.DEAL_TYPE_SELL else "OTHER"
        print(f"{dt} | Ticket={d.ticket} | Magic={d.magic} | {type_str} | Lot={d.volume} | Price={d.price} | Profit={d.profit:.2f} | Reason={d.reason}")
        count += 1
    print(f"\nTotal: {count} deals")
else:
    print("Aucun deal trouve du tout.")

mt5.shutdown()
