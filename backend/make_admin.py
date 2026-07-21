import sys, os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '.')

from db import supabase

email_to_promote = "michelsonmichel99@yahoo.fr"

print(f"Ap eseye mete kont {email_to_promote} kòm ADMIN...")

try:
    # Update the profile role to 'admin' in Supabase
    response = supabase.table("profiles").update({"role": "admin"}).eq("email", email_to_promote).execute()
    if response.data and len(response.data) > 0:
        print(f"✅ SIKSÈ! Kont {email_to_promote} la mete kòm ADMIN ak siksè nan tab Profiles la!")
        print(f"Detay profile: {response.data[0]}")
    else:
        print(f"❌ KONT SA A PA PÒKO KREYE: Pa gen okenn kont ki gen imel {email_to_promote} nan tab Profiles la.")
        print("Asire w ou te enskri (Sign Up) ak imel sa a sou sit la anvan ou kouri script sa a.")
except Exception as e:
    print(f"❌ ERÈ pandan aktyalizasyon a: {e}")
