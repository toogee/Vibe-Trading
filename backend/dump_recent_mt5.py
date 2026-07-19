# -*- coding: utf-8 -*-
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '.')

import MetaTrader5 as mt5
from db import get_active_users, get_user_mt5_account
from security import decrypt_password
from datetime import datetime, timedelta
import pytz

if not mt5.initialize():
    print(f"Erreur MT5: {mt5.last_error()}")
    sys.exit(1)

users = get_active_users()
if not users:
    sys.exit(1)

acc = get_user_mt5_account(users[0])
login = int(acc['login_id'])
pwd = decrypt_password(acc['encrypted_password'])
server = acc['server_name']

if not mt5.login(login=login, password=pwd, server=server):
    print(f"Echec login {login}")
    sys.exit(1)

from_dt = datetime.now(pytz.utc) - timedelta(days=5)
to_dt = datetime.now(pytz.utc) + timedelta(hours=24)
deals = mt5.history_deals_get(from_dt, to_dt)

print("=== DEALS RECENTS SANS FILTRE (5 jours) ===")
if deals:
    for d in deals:
        if d.entry == mt5.DEAL_ENTRY_IN: continue # Ignorer les ouvertures pures
        dt = datetime.fromtimestamp(d.time, pytz.utc).strftime("%Y-%m-%d %H:%M:%S")
        type_str = "BUY" if d.type == mt5.DEAL_TYPE_BUY else "SELL" if d.type == mt5.DEAL_TYPE_SELL else "OTHER"
        print(f"{dt} | Ticket={d.ticket} | PosID={d.position_id} | Magic={d.magic} | {type_str} | Lot={d.volume} | Price={d.price} | Profit={d.profit:.2f} | Reason={d.reason}")
else:
    print("Aucun deal trouve.")

mt5.shutdown()
