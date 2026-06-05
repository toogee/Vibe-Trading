"""
╔══════════════════════════════════════════════════════════════════╗
║         FORCE TRADE TEST — Script de Diagnostic Rapide          ║
║         Bypasse TOUS les filtres (session, news, strategy)      ║
║         But: Tester si MT5 peut placer un ordre correctement    ║
╚══════════════════════════════════════════════════════════════════╝

UTILISATION:
    python backend/force_trade_test.py

Ce script va :
  1. Se connecter à MT5
  2. Se connecter à votre compte via Supabase
  3. Vérifier spread, tick, info symbole
  4. Tenter de placer un BUY GBPUSD
  5. Afficher EXACTEMENT pourquoi ça échoue (ou confirme le succès)
"""

import MetaTrader5 as mt5
import logging
import sys
import os

# Ajouter le dossier backend dans le path pour les imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import get_active_users, get_user_mt5_account, save_trade
from security import decrypt_password
from datetime import datetime

# ─── CONFIG ───────────────────────────────────────────────────────────────────
SYMBOL          = "GBPUSD"
DIRECTION       = "buy"          # <<< Changer en "sell" si ou vle teste vann
MAGIC_NUMBER    = 20240601
RISK_PERCENT    = 1.0
STOP_LOSS_PIP   = 0              # SL in pips (0 to disable)
TAKE_PROFIT_PIP = 0              # TP in pips (0 to disable)
PIP_VALUE       = 0.0001
MAX_SPREAD_PIPS = 3.0
# ──────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
log = logging.getLogger("ForceTest")

def separator(title=""):
    line = "─" * 60
    if title:
        log.info(f"┌{line}┐")
        log.info(f"│  {title:<58}│")
        log.info(f"└{line}┘")
    else:
        log.info(line)

def run_test():
    separator("ÉTAPE 1 — Connexion à MT5")
    if not mt5.initialize():
        log.error(f"❌ ÉCHEC initialize() : {mt5.last_error()}")
        log.error("   → Assurez-vous que MetaTrader 5 est ouvert et connecté.")
        return
    log.info("✅ MT5 initialisé avec succès.")

    terminal = mt5.terminal_info()
    log.info(f"   Terminal: build={terminal.build} | connected={terminal.connected} | trade_allowed={terminal.trade_allowed}")

    if not terminal.connected:
        log.error("❌ MT5 n'est PAS connecté au broker. Vérifiez votre connexion internet.")
        mt5.shutdown()
        return

    if not terminal.trade_allowed:
        log.error("❌ Le trading N'EST PAS autorisé dans MT5.")
        log.error("   → Activez 'Allow automated trading' dans MT5 → Tools → Options → Expert Advisors.")
        mt5.shutdown()
        return

    # ── Récupérer les utilisateurs Supabase ───────────────────────────────────
    separator("ÉTAPE 2 — Récupération compte Supabase")
    active_users = get_active_users()
    if not active_users:
        log.error("❌ Aucun utilisateur actif dans Supabase.")
        log.error("   → Vérifiez que l'abonnement est ACTIVE dans la table 'subscriptions'.")
        mt5.shutdown()
        return
    log.info(f"✅ {len(active_users)} utilisateur(s) actif(s) trouvé(s) : {active_users}")

    for user_id in active_users:
        separator(f"ÉTAPE 3 — Login MT5 pour user: {str(user_id)[:8]}...")
        mt5_acc = get_user_mt5_account(user_id)
        if not mt5_acc:
            log.error(f"❌ Aucun compte MT5 lié pour cet utilisateur.")
            log.error("   → Configurez le compte MT5 dans le Dashboard (MT5 Settings).")
            continue

        log.info(f"   Login ID: {mt5_acc['login_id']} | Server: {mt5_acc['server_name']}")

        try:
            plain_password = decrypt_password(mt5_acc['encrypted_password'])
        except Exception as e:
            log.error(f"❌ Échec du déchiffrement du mot de passe : {e}")
            continue

        login = int(mt5_acc['login_id'])
        server = mt5_acc['server_name']

        if not mt5.login(login=login, password=plain_password, server=server):
            err = mt5.last_error()
            log.error(f"❌ Connexion MT5 échouée pour login={login} server={server}")
            log.error(f"   Erreur MT5 : {err}")
            log.error("   → Vérifiez le login, le mot de passe, et le nom du serveur.")
            continue
        log.info(f"✅ Connecté au compte MT5 {login} sur {server}")

        # ── Info du compte ─────────────────────────────────────────────────────
        separator("ÉTAPE 4 — Info Compte & Symbole")
        account = mt5.account_info()
        if account is None:
            log.error(f"❌ Impossible de récupérer account_info() : {mt5.last_error()}")
            continue

        log.info(f"   Balance  : {account.balance:.2f} {account.currency}")
        log.info(f"   Equity   : {account.equity:.2f} {account.currency}")
        log.info(f"   Leverage : 1:{account.leverage}")
        log.info(f"   Trade mode: {account.trade_mode} (0=live, 1=demo)")

        # ── Sélection du symbole ───────────────────────────────────────────────
        if not mt5.symbol_select(SYMBOL, True):
            log.error(f"❌ Impossible de sélectionner le symbole {SYMBOL}: {mt5.last_error()}")
            continue

        sym_info = mt5.symbol_info(SYMBOL)
        if sym_info is None:
            log.error(f"❌ symbol_info({SYMBOL}) retourne None : {mt5.last_error()}")
            continue

        log.info(f"   Symbole  : {SYMBOL} | Volume min={sym_info.volume_min} | Step={sym_info.volume_step}")
        log.info(f"   Trade mode symbole: {sym_info.trade_mode} (4=full, 0=disabled)")

        if sym_info.trade_mode == 0:
            log.error(f"❌ Le trading est DÉSACTIVÉ pour le symbole {SYMBOL}.")
            log.error("   → Cherchez 'GBPUSD' dans Market Watch MT5 et vérifiez qu'il est actif.")
            continue

        # ── Tick actuel ────────────────────────────────────────────────────────
        separator("ÉTAPE 5 — Prix actuel & Spread")
        tick = mt5.symbol_info_tick(SYMBOL)
        if tick is None:
            log.error(f"❌ Impossible d'obtenir le tick pour {SYMBOL} : {mt5.last_error()}")
            log.error("   → Le marché est peut-être fermé ou le symbole n'est pas coté.")
            continue

        spread_pips = (tick.ask - tick.bid) / PIP_VALUE
        log.info(f"   Bid={tick.bid:.5f} | Ask={tick.ask:.5f} | Spread={spread_pips:.1f} pips")

        if spread_pips > MAX_SPREAD_PIPS:
            log.warning(f"⚠️  Spread élevé ({spread_pips:.1f} pips > {MAX_SPREAD_PIPS}). Test continue quand même...")
        else:
            log.info(f"✅ Spread acceptable : {spread_pips:.1f} pips")

        # ── Calcul du lot ──────────────────────────────────────────────────────
        separator("ÉTAPE 6 — Calcul du Lot & Construction de l'Ordre")
        risk_amount = account.balance * (RISK_PERCENT / 100.0)
        tick_value  = sym_info.trade_tick_value
        tick_size   = sym_info.trade_tick_size

        log.info(f"   Risque   : {risk_amount:.2f} {account.currency} ({RISK_PERCENT}%)")
        log.info(f"   tick_value={tick_value} | tick_size={tick_size}")

        if tick_value > 0 and tick_size > 0:
            ticks_per_pip = PIP_VALUE / tick_size
            loss_per_lot  = STOP_LOSS_PIP * ticks_per_pip * tick_value
            lot = risk_amount / loss_per_lot if loss_per_lot > 0 else sym_info.volume_min
            step = sym_info.volume_step
            if step > 0:
                lot = round(lot / step) * step
            lot = max(sym_info.volume_min, min(lot, sym_info.volume_max))
        else:
            lot = sym_info.volume_min
            log.warning("   ⚠️  tick_value/tick_size invalide — utilisation du lot minimum.")

        lot = float(round(lot, 2))
        log.info(f"   Lot calculé : {lot}")

        # ── Appliquer le stop level minimum du broker ─────────────────
        if STOP_LOSS_PIP == 0:
            sl = 0.0
            tp = 0.0
            log.info("   Stops désactivés (SL=0, TP=0)")
        else:
            min_dist_pips = sym_info.trade_stops_level / 10.0
            effective_sl  = max(STOP_LOSS_PIP,   min_dist_pips + 2)
            effective_tp  = max(TAKE_PROFIT_PIP, min_dist_pips + 2)
            log.info(f"   Stop level broker  : {min_dist_pips:.1f} pips minimum")
            log.info(f"   SL effectif utilisé : {effective_sl:.1f} pips")
            log.info(f"   TP effectif utilisé : {effective_tp:.1f} pips")
            
            if DIRECTION == "buy":
                sl = round(tick.ask - effective_sl * PIP_VALUE, 5)
                tp = round(tick.ask + effective_tp * PIP_VALUE, 5)
            else:
                sl = round(tick.bid + effective_sl * PIP_VALUE, 5)
                tp = round(tick.bid - effective_tp * PIP_VALUE, 5)

        if DIRECTION == "buy":
            price = tick.ask
            order_type = mt5.ORDER_TYPE_BUY
        else:
            price = tick.bid
            order_type = mt5.ORDER_TYPE_SELL

        # Auto-détecter le filling mode supporté par ce broker
        filling_mode = mt5.ORDER_FILLING_IOC  # défaut
        if sym_info.filling_mode & 1:    # FOK supporté
            filling_mode = mt5.ORDER_FILLING_FOK
        elif sym_info.filling_mode & 2:  # IOC supporté
            filling_mode = mt5.ORDER_FILLING_IOC
        elif sym_info.filling_mode & 4:  # RETURN supporté
            filling_mode = mt5.ORDER_FILLING_RETURN
        log.info(f"   Filling mode détecté: {filling_mode} (bitmask broker={sym_info.filling_mode})")

        request = {
            "action":       mt5.TRADE_ACTION_DEAL,
            "symbol":       SYMBOL,
            "volume":       lot,
            "type":         order_type,
            "price":        price,
            "sl":           sl,
            "tp":           tp,
            "deviation":    20,
            "magic":        MAGIC_NUMBER,
            "comment":      "VibeTrade_ForceTest",
            "type_time":    mt5.ORDER_TIME_GTC,
            "type_filling": filling_mode,
        }

        log.info(f"   Ordre : {DIRECTION.upper()} {lot} {SYMBOL} @ {price:.5f}")
        log.info(f"   SL={sl:.5f} | TP={tp:.5f}")

        # ── Envoi de l'ordre ───────────────────────────────────────────────────
        separator("ÉTAPE 7 — Envoi de l'Ordre au Broker")
        result = mt5.order_send(request)

        if result is None:
            log.error(f"❌ order_send() retourne None : {mt5.last_error()}")
        elif result.retcode == mt5.TRADE_RETCODE_DONE:
            log.info(f"✅✅✅ ORDRE PLACÉ AVEC SUCCÈS !")
            log.info(f"   Ticket : {result.order}")
            log.info(f"   Prix d'exécution : {result.price:.5f}")
            log.info(f"   Volume : {result.volume}")
            # Sauvegarder dans Supabase
            save_trade({
                "user_id": user_id,
                "symbol":  SYMBOL,
                "type":    DIRECTION.upper(),
                "entry":   result.price,
                "sl":      sl,
                "tp":      tp,
                "profit":  0,
                "status":  "OPEN",
                "open_time": datetime.utcnow().isoformat()
            })
            log.info("   Trade sauvegardé dans Supabase ✅")
        else:
            log.error(f"❌ ORDRE ÉCHOUÉ — retcode={result.retcode}")
            log.error(f"   Comment: {result.comment}")
            # Décodage des erreurs MT5 courantes
            codes = {
                10004: "Requête de requote — prix changé, essayez avec plus de déviation.",
                10006: "Requête rejetée par le broker.",
                10007: "Requête annulée par le trader.",
                10008: "Ordre placé mais pas encore traité.",
                10009: "Requête complétée avec succès.",
                10010: "Exécution partielle seulement.",
                10011: "Erreur de traitement de la requête.",
                10012: "Timeout de la requête.",
                10013: "Paramètres invalides dans la requête.",
                10014: "Volume invalide dans la requête.",
                10015: "Prix invalide dans la requête.",
                10016: "Stops invalides dans la requête (SL/TP).",
                10017: "Le trading est désactivé.",
                10018: "Le marché est fermé.",
                10019: "Fonds insuffisants.",
                10020: "Prix changé.",
                10021: "Aucun prix disponible pour cette requête.",
                10022: "Date d'expiration invalide.",
                10023: "L'état de l'ordre a changé.",
                10024: "Trop de requêtes envoyées.",
                10025: "Aucun changement dans la requête.",
                10026: "Autotrading désactivé sur le serveur.",
                10027: "Autotrading désactivé dans le client.",
                10028: "Requête bloquée par le broker.",
                10029: "Ordre ou position bloqué.",
                10030: "Uniquement les positions FIFO sont autorisées.",
            }
            if result.retcode in codes:
                log.error(f"   Signification : {codes[result.retcode]}")
            else:
                log.error(f"   Code inconnu. Consultez la doc MT5 pour retcode {result.retcode}.")

    separator("FIN DU TEST DE DIAGNOSTIC")
    mt5.shutdown()
    log.info("MT5 déconnecté.")

if __name__ == "__main__":
    run_test()
