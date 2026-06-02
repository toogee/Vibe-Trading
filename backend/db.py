import os
from datetime import datetime, timezone
from supabase import create_client, Client
from dotenv import load_dotenv
import logging

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY") # Service Role Key required to bypass RLS!

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Missing Supabase credentials in .env file.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def get_active_users():
    """Fetches users who have an ACTIVE subscription status."""
    try:
        response = supabase.table("subscriptions").select("user_id").eq("status", "ACTIVE").execute()
        return [sub['user_id'] for sub in response.data]
    except Exception as e:
        logging.error(f"Error fetching active users: {e}")
        return []

def get_user_mt5_account(user_id):
    """Fetches the MT5 account details for a given user."""
    try:
        response = supabase.table("mt5_accounts").select("*").eq("user_id", user_id).execute()
        if response.data and len(response.data) > 0:
            return response.data[0] # Assume one account per user for now
        return None
    except Exception as e:
        logging.error(f"Error fetching MT5 account for user {user_id}: {e}")
        return None

def save_trade(trade_data: dict):
    """Saves a trade record to the database."""
    try:
        response = supabase.table("trades").insert(trade_data).execute()
        return response.data
    except Exception as e:
        logging.error(f"Error saving trade: {e}")
        return None

def update_mt5_status(account_id: str, status: str):
    """Updates the connection status of the MT5 account in the DB."""
    try:
        supabase.table("mt5_accounts").update({"status": status}).eq("id", account_id).execute()
    except Exception as e:
        logging.error(f"Error updating MT5 status for account {account_id}: {e}")

def update_mt5_balance(account_id: str, balance: float, equity: float):
    """Updates the balance and equity of the MT5 account in the DB."""
    try:
        supabase.table("mt5_accounts").update({
            "balance": balance,
            "equity": equity
        }).eq("id", account_id).execute()
    except Exception as e:
        logging.error(f"Error updating balance for account {account_id}: {e}")

# ─── BOT CONTROL (Dashboard Start/Stop) ───────────────────────────────────────

def get_trading_enabled() -> bool:
    """Returns True if the bot is authorized to trade (set via Dashboard)."""
    try:
        response = supabase.table("bot_control").select("trading_enabled").eq("id", 1).execute()
        if response.data:
            return response.data[0].get("trading_enabled", False)
        return False
    except Exception as e:
        logging.error(f"Error reading bot_control: {e}")
        return True  # Fail-safe: continue trading if DB unreachable

def set_trading_enabled(enabled: bool):
    """Enable or disable bot trading via Dashboard toggle."""
    try:
        supabase.table("bot_control").upsert({
            "id": 1,
            "trading_enabled": enabled,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }).execute()
    except Exception as e:
        logging.error(f"Error setting bot_control: {e}")

def update_bot_heartbeat():
    """Called every 30s by the bot so Dashboard knows it's alive."""
    try:
        supabase.table("bot_control").upsert({
            "id": 1,
            "last_heartbeat": datetime.now(timezone.utc).isoformat()
        }).execute()
    except Exception as e:
        logging.error(f"Error updating heartbeat: {e}")
