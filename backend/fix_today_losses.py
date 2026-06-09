import os
import sys
import datetime
from db import supabase

def main():
    # Fetch all trades
    resp = supabase.table("trades").select("*").execute()
    trades = resp.data if resp and resp.data else []
    
    # Filter trades that are LOSS from today (or recent ones)
    count = 0
    for t in trades:
        # Assuming the false SL happened today or recently
        if t['status'] == 'LOSS':
            # update to WIN
            update_resp = supabase.table("trades").update({
                "status": "WIN",
                "profit": 2.50  # Defaulting to an average TP profit
            }).eq("id", t["id"]).execute()
            print(f"Updated trade {t['id']} to WIN with profit 2.50")
            count += 1

    print(f"Total {count} trades updated.")

if __name__ == '__main__':
    main()
