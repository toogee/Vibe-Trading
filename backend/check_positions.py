import sys, os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '.')
import MetaTrader5 as mt5
from db import get_active_users, get_user_mt5_account
from security import decrypt_password

mt5.initialize()
users = get_active_users()
acc = get_user_mt5_account(users[0])
mt5.login(int(acc['login_id']), decrypt_password(acc['encrypted_password']), acc['server_name'])

# Verifier stop level minimum du broker
sym = mt5.symbol_info('GBPUSD')
stops_level_pips = sym.trade_stops_level / 10.0
print(f"=== STOP LEVEL MINIMUM BROKER ===")
print(f"  stops_level (points) : {sym.trade_stops_level}")
print(f"  stops_level (pips)   : {stops_level_pips:.1f} pips")
print(f"  SL actuel du bot     : 5 pips  --> {'OK' if stops_level_pips <= 5 else 'TROP PROCHE! Augmenter SL'}")
print(f"  TP actuel du bot     : 11 pips --> {'OK' if stops_level_pips <= 11 else 'TROP PROCHE!'}")

# Verifier positions ouvertes
positions = mt5.positions_get(symbol='GBPUSD')
print("\n=== POSITIONS OUVERTES GBPUSD ===")
if positions:
    for p in positions:
        typ = "BUY" if p.type == 0 else "SELL"
        sl_ok = "OK" if p.sl != 0 else "!!! SL MANQUANT !!!"
        tp_ok = "OK" if p.tp != 0 else "!!! TP MANQUANT !!!"
        print(f"  Ticket : {p.ticket}")
        print(f"  Type   : {typ}  | Volume: {p.volume}")
        print(f"  Open   : {p.price_open:.5f}")
        print(f"  SL     : {p.sl:.5f}  [{sl_ok}]")
        print(f"  TP     : {p.tp:.5f}  [{tp_ok}]")
        print(f"  Profit : {p.profit:.2f} USD")
        print()
else:
    print("  Aucune position ouverte. (Trade test deja ferme)")

mt5.shutdown()
