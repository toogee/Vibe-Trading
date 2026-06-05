# -*- coding: utf-8 -*-
"""
sync_mt5_to_supabase.py
Script complet: lit l'historique reel MT5, nettoie Supabase, reimporte les vrais trades
"""
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '.')

import MetaTrader5 as mt5
from db import get_active_users, get_user_mt5_account, supabase
from security import decrypt_password
from datetime import datetime, timedelta, timezone
import pytz

MAGIC = 20240601
TZ    = pytz.timezone("Europe/London")

print("=" * 65)
print("  SYNC COMPLET MT5 -> SUPABASE")
print("=" * 65)

# ── Init MT5 ──────────────────────────────────────────────────────────────
if not mt5.initialize():
    print(f"Erreur MT5: {mt5.last_error()}")
    sys.exit(1)

users = get_active_users()
if not users:
    print("Aucun utilisateur actif.")
    mt5.shutdown(); sys.exit(1)

# ── Login sur chaque compte et recuperer historique ───────────────────────
all_real_trades = []

for user_id in users:
    acc = get_user_mt5_account(user_id)
    if not acc:
        continue

    login   = int(acc['login_id'])
    pwd     = decrypt_password(acc['encrypted_password'])
    server  = acc['server_name']

    if not mt5.login(login=login, password=pwd, server=server):
        print(f"Echec login {login}: {mt5.last_error()}")
        continue

    info = mt5.account_info()
    print(f"\nCompte: {login} | Balance: ${info.balance:.2f} | Equity: ${info.equity:.2f}")

    # Recuperer historique 30 derniers jours
    from_dt = datetime.now(pytz.utc) - timedelta(days=30)
    to_dt   = datetime.now(pytz.utc) + timedelta(minutes=5)
    deals   = mt5.history_deals_get(from_dt, to_dt)

    if not deals:
        print(f"  Aucun deal dans les 30 derniers jours pour {login}")
        continue

    # Filtrer deals du bot (magic=MAGIC) et fermeture seulement
    print(f"  Deals totaux trouves: {len(deals)}")
    
    # Grouper par position_id pour associer ouverture et fermeture
    positions = {}
    for deal in deals:
        if deal.magic != MAGIC:
            continue
        pid = deal.position_id
        if pid not in positions:
            positions[pid] = {"open": None, "close": None}
        if deal.entry == mt5.DEAL_ENTRY_IN:
            positions[pid]["open"] = deal
        elif deal.entry == mt5.DEAL_ENTRY_OUT:
            positions[pid]["close"] = deal

    print(f"  Positions du bot trouvees: {len(positions)}")

    for pid, pos in positions.items():
        open_deal  = pos["open"]
        close_deal = pos["close"]

        if not open_deal:
            continue

        # Determiner direction
        trade_type = "BUY" if open_deal.type == mt5.DEAL_TYPE_BUY else "SELL"

        # Determiner statut
        if close_deal:
            profit = round(close_deal.profit, 2)
            if close_deal.reason == mt5.DEAL_REASON_TP:
                status = "WIN"
                close_reason = "TP"
            elif close_deal.reason == mt5.DEAL_REASON_SL:
                status = "LOSS"
                close_reason = "SL"
            elif profit > 0:
                status = "WIN"
                close_reason = "TP"
            elif profit < 0:
                status = "LOSS"
                close_reason = "SL"
            else:
                status = "LOSS"
                close_reason = "MANUAL"
            close_time = datetime.fromtimestamp(close_deal.time, pytz.utc).isoformat()
        else:
            profit       = 0.0
            status       = "OPEN"
            close_reason = None
            close_time   = None

        open_time = datetime.fromtimestamp(open_deal.time, pytz.utc).isoformat()
        
        trade_record = {
            "user_id":   user_id,
            "symbol":    "GBPUSD",
            "type":      trade_type,
            "entry":     round(open_deal.price, 5),
            "lot_size":  round(open_deal.volume, 2),
            "profit":    profit,
            "status":    status,
            "open_time": open_time,
            "close_time": close_time,
        }

        # Afficher
        sl_tp = f"| Raison={close_reason}" if close_reason else ""
        print(
            f"  {trade_type} @ {open_deal.price:.5f} | Lot={open_deal.volume:.2f} | "
            f"Profit=${profit:.2f} | {status} {sl_tp} | {open_time[:10]}"
        )
        all_real_trades.append(trade_record)

print(f"\n{len(all_real_trades)} trade(s) reel(s) trouves au total.")

if not all_real_trades:
    print("Rien a importer.")
    mt5.shutdown(); sys.exit(0)

# ── Confirmation avant nettoyage ──────────────────────────────────────────
print(f"\n{'=' * 65}")
print(f"  ACTION: Supprimer TOUS les trades actuels dans Supabase")
print(f"          et reimporter {len(all_real_trades)} trade(s) reel(s) MT5")
print(f"{'=' * 65}")
confirm = input("\nConfirmer ? (oui/non): ").strip().lower()
if confirm not in ("oui", "o", "yes", "y"):
    print("Annule.")
    mt5.shutdown(); sys.exit(0)

# ── Supprimer vieux trades Supabase ──────────────────────────────────────
print("\nSuppression des vieux trades Supabase...")
old = supabase.table("trades").select("id").execute()
if old.data:
    for t in old.data:
        supabase.table("trades").delete().eq("id", t["id"]).execute()
    print(f"  {len(old.data)} vieux trade(s) supprime(s).")
else:
    print("  Aucun vieux trade a supprimer.")

# ── Inserer vrais trades MT5 ──────────────────────────────────────────────
print("\nInsertion des vrais trades MT5...")
success = 0
for trade in all_real_trades:
    result = supabase.table("trades").insert(trade).execute()
    if result.data:
        print(f"  OK -> {trade['type']} @ {trade['entry']} | {trade['status']} ${trade['profit']:.2f} | Lot={trade['lot_size']}")
        success += 1
    else:
        print(f"  ERREUR -> {trade}")

print(f"\n{'=' * 65}")
print(f"  SYNC TERMINE: {success}/{len(all_real_trades)} trade(s) importes")
print(f"  Le Dashboard affiche maintenant les vrais trades MT5!")
print(f"{'=' * 65}")

mt5.shutdown()
