import MetaTrader5 as mt5
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class MT5Handler:
    def __init__(self, login: int, password: str, server: str):
        self.login = login
        self.password = password
        self.server = server
        self.connected = False

    def connect(self) -> bool:
        """Initializes and connects to the MT5 terminal."""
        if not mt5.initialize():
            logging.error(f"mt5.initialize() failed, error code: {mt5.last_error()}")
            return False

        authorized = mt5.login(
            login=self.login,
            password=self.password,
            server=self.server
        )

        if not authorized:
            logging.error(f"failed to connect at account {self.login}, error code: {mt5.last_error()}")
            self.connected = False
            return False

        self.connected = True
        logging.info(f"Successfully connected to MT5 account {self.login}")
        return True

    def disconnect(self):
        """Disconnects the MT5 terminal."""
        if self.connected:
            mt5.shutdown()
            self.connected = False
            logging.info(f"Disconnected from MT5 account {self.login}")

    def execute_trade(self, symbol="GBPUSD", action="BUY", lot_size=0.1, sl_pips=20, tp_pips=40):
        """Executes a simple trade based on Vibe Trading rules."""
        if not self.connected:
            logging.error("Cannot trade, MT5 is not connected.")
            return None

        # Check if symbol is available
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            logging.error(f"{symbol} not found")
            return None
            
        if not symbol_info.visible:
            if not mt5.symbol_select(symbol, True):
                logging.error(f"symbol_select({symbol}) failed")
                return None

        # Determine price and types based on BUY/SELL
        point = mt5.symbol_info(symbol).point
        
        if action == "BUY":
            order_type = mt5.ORDER_TYPE_BUY
            price = mt5.symbol_info_tick(symbol).ask
            sl = price - (sl_pips * 10 * point) # Assuming 5-digit broker
            tp = price + (tp_pips * 10 * point)
        else:
            order_type = mt5.ORDER_TYPE_SELL
            price = mt5.symbol_info_tick(symbol).bid
            sl = price + (sl_pips * 10 * point)
            tp = price - (tp_pips * 10 * point)

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(lot_size),
            "type": order_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": 20,
            "magic": 234000,
            "comment": "Vibe Trading Bot",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        # Send order
        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logging.error(f"Order failed, retcode={result.retcode}")
            return None
        
        logging.info(f"Order successfully placed for {symbol}: Ticket={result.order}")
        
        # Return trade details for saving to database
        return {
            "symbol": symbol,
            "type": action,
            "entry": price,
            "sl": sl,
            "tp": tp,
            "profit": 0, # Initial profit is 0
            "status": "OPEN",
            "open_time": datetime.utcnow().isoformat()
        }
