import time
import logging
from datetime import datetime
from db import get_active_users, get_user_mt5_account, save_trade, update_mt5_status
from security import decrypt_password
from mt5_handler import MT5Handler

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def run_trading_cycle():
    """Main function that iterates through active users and executes trades."""
    logging.info("Starting Trading Engine Cycle...")
    
    # 1. Fetch all ACTIVE users
    active_users = get_active_users()
    logging.info(f"Found {len(active_users)} active users.")

    for user_id in active_users:
        logging.info(f"Processing user: {user_id}")
        
        # 2. Get MT5 credentials
        mt5_acc = get_user_mt5_account(user_id)
        if not mt5_acc:
            logging.warning(f"User {user_id} has no MT5 account configured. Skipping.")
            continue
        
        try:
            # 3. Decrypt MT5 password
            plain_password = decrypt_password(mt5_acc['encrypted_password'])
            
            # 4. Connect to MT5
            handler = MT5Handler(
                login=int(mt5_acc['login_id']),
                password=plain_password,
                server=mt5_acc['server_name']
            )
            
            if handler.connect():
                update_mt5_status(mt5_acc['id'], 'CONNECTED')
                
                # 5. Execute Trade (London Session Logic - Simplified for Demo)
                # In production, add exact time checks (6:00 AM - 12:00 PM GMT)
                trade_result = handler.execute_trade(symbol="GBPUSD", action="BUY")
                
                if trade_result:
                    # Add user ID to the trade payload
                    trade_result['user_id'] = user_id
                    
                    # 6. Save trade to database
                    save_trade(trade_result)
                    logging.info(f"Trade saved for user {user_id}")
                
                # 7. Disconnect Safely
                handler.disconnect()
                update_mt5_status(mt5_acc['id'], 'DISCONNECTED')
            else:
                update_mt5_status(mt5_acc['id'], 'ERROR')
                
        except Exception as e:
            logging.error(f"Error processing user {user_id}: {e}")
            update_mt5_status(mt5_acc['id'], 'ERROR')
            
        # Optional: Sleep briefly between accounts to avoid terminal overload
        time.sleep(2)

    logging.info("Trading Cycle Complete.")

if __name__ == "__main__":
    # Example scheduling: Run every morning or via cron
    # For testing, we run it once immediately.
    run_trading_cycle()
