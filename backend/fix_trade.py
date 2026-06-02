import sys, os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '.')
from db import supabase
from datetime import datetime, timezone

TRADE_ID = "1bcd36bf-e6bf-49e6-a39c-e1990b0b478c"

# Trade TP hit: entry=1.34607, TP=1.34718 -> profit ~$2 sur 0.02 lots
# Valeur confirmee: TP touche, bot en profit
result = supabase.table("trades").update({
    "status": "WIN",
    "profit": 2.22,
    "close_time": datetime.now(timezone.utc).isoformat()
}).eq("id", TRADE_ID).execute()

print("Trade mis a jour:", result.data)
print("Dashboard va maintenant afficher le bon profit!")
