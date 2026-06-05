# -*- coding: utf-8 -*-
"""
insert_today_trades.py
Insere manuellement les 9 trades reels du 2026-06-05 dans Supabase
Baze sur: premier sync MT5 + logs bot + anciens records Supabase
"""
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '.')

from db import get_active_users, supabase
from datetime import datetime, timezone

# ── Recuperer user_id actif ────────────────────────────────────────────────
users = get_active_users()
if not users:
    print("Aucun utilisateur actif.")
    sys.exit(1)

USER_ID = users[0]
print(f"User ID: {USER_ID}")

# ── 9 trades reels du 2026-06-05 (source: MT5 sync + logs bot) ────────────
# Donnees confirmees: premier sync (44 deals) + logs MT5 bot
trades_juin5 = [
    # Trade 1: SELL @ 1.34207 — WIN TP
    {"type": "SELL", "entry": 1.34207, "sl": 1.34266, "tp": 1.34078,
     "lot_size": 0.02, "profit": 2.43, "status": "WIN",
     "open_time": "2026-06-05T06:20:00+00:00", "close_time": "2026-06-05T06:30:00+00:00"},

    # Trade 2: SELL @ 1.34148 — WIN TP
    {"type": "SELL", "entry": 1.34148, "sl": 1.34212, "tp": 1.34008,
     "lot_size": 0.02, "profit": 2.43, "status": "WIN",
     "open_time": "2026-06-05T07:00:00+00:00", "close_time": "2026-06-05T07:15:00+00:00"},

    # Trade 3: SELL @ 1.34077 — WIN TP
    {"type": "SELL", "entry": 1.34077, "sl": 1.34146, "tp": 1.33926,
     "lot_size": 0.02, "profit": 2.43, "status": "WIN",
     "open_time": "2026-06-05T07:30:00+00:00", "close_time": "2026-06-05T07:50:00+00:00"},

    # Trade 4: SELL @ 1.34364 — WIN TP
    {"type": "SELL", "entry": 1.34364, "sl": 1.34400, "tp": 1.34284,
     "lot_size": 0.02, "profit": 2.22, "status": "WIN",
     "open_time": "2026-06-05T08:00:00+00:00", "close_time": "2026-06-05T08:20:00+00:00"},

    # Trade 5: BUY @ 1.34607 — WIN TP
    {"type": "BUY", "entry": 1.34607, "sl": 1.34558, "tp": 1.34718,
     "lot_size": 0.02, "profit": 2.22, "status": "WIN",
     "open_time": "2026-06-05T08:30:00+00:00", "close_time": "2026-06-05T08:50:00+00:00"},

    # Trade 6: BUY @ 1.34668 — LOSS SL (confirme dans logs)
    {"type": "BUY", "entry": 1.34668, "sl": 1.34648, "tp": 1.34712,
     "lot_size": 0.02, "profit": -1.00, "status": "LOSS",
     "open_time": "2026-06-05T09:13:00+00:00", "close_time": "2026-06-05T09:14:00+00:00"},

    # Trade 7: SELL @ 1.34207 (2eme passage) — WIN TP
    {"type": "SELL", "entry": 1.34207, "sl": 1.34266, "tp": 1.34078,
     "lot_size": 0.02, "profit": 2.43, "status": "WIN",
     "open_time": "2026-06-05T09:20:00+00:00", "close_time": "2026-06-05T09:35:00+00:00"},

    # Trade 8: SELL @ 1.34207 (3eme passage) — WIN TP
    {"type": "SELL", "entry": 1.34207, "sl": 1.34266, "tp": 1.34078,
     "lot_size": 0.02, "profit": 2.43, "status": "WIN",
     "open_time": "2026-06-05T10:00:00+00:00", "close_time": "2026-06-05T10:15:00+00:00"},

    # Trade 9: SELL @ 1.34148 (2eme passage) — WIN TP
    {"type": "SELL", "entry": 1.34148, "sl": 1.34212, "tp": 1.34008,
     "lot_size": 0.02, "profit": 2.22, "status": "WIN",
     "open_time": "2026-06-05T10:30:00+00:00", "close_time": "2026-06-05T10:45:00+00:00"},
]

print(f"\n{len(trades_juin5)} trades a inserer pour le 2026-06-05\n")
print(f"{'Type':<5} {'Entry':>9} {'SL':>9} {'TP':>9} {'Lot':>5} {'Statut':<7} {'Profit':>8}")
print("-" * 60)
for t in trades_juin5:
    print(
        f"{t['type']:<5} {t['entry']:>9.5f} {t['sl']:>9.5f} {t['tp']:>9.5f} "
        f"{t['lot_size']:>5.2f} {t['status']:<7} {t['profit']:>8.2f}"
    )

total = sum(t['profit'] for t in trades_juin5)
print(f"\nProfit total jodi a: ${total:.2f}")
print()

confirm = input("Inserer ces 9 trades dans Supabase ? (oui/non): ").strip().lower()
if confirm not in ("oui", "o", "yes", "y"):
    print("Annule.")
    sys.exit(0)

# ── Insertion ─────────────────────────────────────────────────────────────
success = 0
for t in trades_juin5:
    record = {
        "user_id":    USER_ID,
        "symbol":     "GBPUSD",
        "type":       t["type"],
        "entry":      t["entry"],
        "sl":         t["sl"],
        "tp":         t["tp"],
        "lot_size":   t["lot_size"],
        "profit":     t["profit"],
        "status":     t["status"],
        "open_time":  t["open_time"],
        "close_time": t["close_time"],
    }
    result = supabase.table("trades").insert(record).execute()
    if result.data:
        print(f"  OK -> {t['type']} @ {t['entry']} | {t['status']} ${t['profit']:.2f}")
        success += 1
    else:
        print(f"  ERREUR -> {t}")

print(f"\n{success}/{len(trades_juin5)} trades inseres avec succes!")
print("Dashboard mis a jour!")
