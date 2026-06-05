# -*- coding: utf-8 -*-
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '.')

from db import get_active_users, supabase

USER_ID = get_active_users()[0]

# LES VRAIS DEALS DU COMPTE (sans les depots ni les trades manuels)
trades = [
    {
        "type": "SELL", "entry": 1.34718, "sl": 1.34718, "tp": 1.34718, "lot_size": 0.02, 
        "profit": 2.22, "status": "WIN", 
        "open_time": "2026-06-02T17:00:00+00:00", "close_time": "2026-06-02T17:17:02+00:00"
    },
    {
        "type": "BUY", "entry": 1.34284, "sl": 1.34284, "tp": 1.34284, "lot_size": 0.03, 
        "profit": 2.43, "status": "WIN", 
        "open_time": "2026-06-03T13:00:00+00:00", "close_time": "2026-06-03T13:05:31+00:00"
    },
    {
        "type": "SELL", "entry": 1.34648, "sl": 1.34648, "tp": 1.34648, "lot_size": 0.05, 
        "profit": -1.00, "status": "LOSS", 
        "open_time": "2026-06-05T10:00:00+00:00", "close_time": "2026-06-05T10:21:51+00:00"
    },
    {
        "type": "BUY", "entry": 1.34146, "sl": 1.34146, "tp": 1.34146, "lot_size": 0.02, 
        "profit": -1.36, "status": "LOSS", 
        "open_time": "2026-06-05T11:00:00+00:00", "close_time": "2026-06-05T11:12:36+00:00"
    },
    {
        "type": "BUY", "entry": 1.34212, "sl": 1.34212, "tp": 1.34212, "lot_size": 0.02, 
        "profit": -1.26, "status": "LOSS", 
        "open_time": "2026-06-05T11:15:00+00:00", "close_time": "2026-06-05T11:20:44+00:00"
    },
    {
        "type": "BUY", "entry": 1.34078, "sl": 1.34078, "tp": 1.34078, "lot_size": 0.02, 
        "profit": 2.60, "status": "WIN", 
        "open_time": "2026-06-05T11:25:00+00:00", "close_time": "2026-06-05T11:28:21+00:00"
    }
]

print("1. Suppression des trades existants...")
res_del = supabase.table("trades").delete().eq("user_id", USER_ID).execute()
print(f"  {len(res_del.data)} trades supprimes.")

print("2. Insertion des vrais trades...")
success = 0
for t in trades:
    record = {
        "user_id": USER_ID,
        "symbol": "GBPUSD",
        "type": t["type"],
        "entry": t["entry"],
        "sl": t["sl"],
        "tp": t["tp"],
        "lot_size": t["lot_size"],
        "profit": t["profit"],
        "status": t["status"],
        "open_time": t["open_time"],
        "close_time": t["close_time"],
    }
    res_ins = supabase.table("trades").insert(record).execute()
    if res_ins.data:
        success += 1
        print(f"  Insere: {t['type']} {t['lot_size']} | Profit: {t['profit']}")

print(f"\nTERMINE ! {success} / {len(trades)} trades inseres.")
