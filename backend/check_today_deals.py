import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '.')

import MetaTrader5 as mt5
from db import get_active_users, get_user_mt5_account
from security import decrypt_password
from datetime import datetime, timedelta
import pytz

MAGIC = 20240601

if not mt5.initialize():
    print(f"Erreur MT5: {mt5.last_error()}")
    sys.exit(1)

users = get_active_users()
for user_id in users:
    acc = get_user_mt5_account(user_id)
    if not acc: continue
    
    login = int(acc['login_id'])
    pwd = decrypt_password(acc['encrypted_password'])
    server = acc['server_name']
    
    if not mt5.login(login=login, password=pwd, server=server):
        print(f"Echec login {login}")
        continue
        
    print(f"--- Login {login} ---")
    
    from_dt = datetime.now(pytz.utc) - timedelta(days=2)
    to_dt = datetime.now(pytz.utc) + timedelta(minutes=60)
    
    deals = mt5.history_deals_get(from_dt, to_dt)
    if deals:
        print(f"Found {len(deals)} total deals in the last 2 days:")
        for d in deals[-10:]: # Print last 10 deals
            deal_time = datetime.fromtimestamp(d.time, pytz.utc)
            dt_str = deal_time.strftime("%Y-%m-%d %H:%M:%S")
            print(f"  Deal: {d.ticket} | Time: {dt_str} | Magic: {d.magic} | Type: {d.type} | Entry: {d.entry} | Profit: {d.profit} | Price: {d.price}")
            
    # Also check if there are open positions
    positions = mt5.positions_get()
    if positions:
        print(f"Open Positions: {len(positions)}")
        for p in positions:
            print(f"  Pos: {p.ticket} | Magic: {p.magic} | Type: {p.type} | Profit: {p.profit}")
    else:
        print("No open positions.")

mt5.shutdown()
