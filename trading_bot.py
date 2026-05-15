import time
import threading
import datetime
import pyotp
import urllib.request
import json
import pandas as pd
from SmartApi import SmartConnect
from config import API_KEY, CLIENT_ID, PASSWORD, TOTP_SECRET

class TradingBot:
    def __init__(self):
        self.api = None
        self.is_running = False
        self.thread = None
        
        # User defined settings
        self.symbol = "NIFTY"
        self.token = "26000" # Placeholder token for NIFTY
        self.exchange = "NSE"
        self.take_profit_target = 0.0
        self.stop_loss_target = 0.0
        self.max_trades = 5
        
        # State
        self.current_trades = 0
        self.last_price = 0.0
        self.buy_price = 0.0 # Track entry price
        self.position = 0 # 0 for none, 1 for long
        self.quantity = 0 # Track how many shares bought
        self.logs = []
        self.price_history = [] # To store local tick data for basic indicators
        self.connected = False
        
        # Chart Data State
        self.interval = "ONE_MINUTE" # Default timeframe
        self.interval_seconds = 60
        self.candles = {} # Map of minute_timestamp -> OHLC dict
        self.trade_history = [] # List of trade dicts for chart markers
        
        # AI Strategy
        self.strategy = "CONSERVATIVE"
        
        # Options Engine
        self.category = "INDICES"
        self.moneyness = "ATM"
        self.options_data = [] # Stores NFO contracts
        self.active_option = None # dict holding active option trade

    def fetch_scrip_master(self):
        self.log("Downloading Scrip Master DB... This will take a few seconds.")
        try:
            url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
            response = urllib.request.urlopen(url)
            data = json.loads(response.read())
            
            # Filter for NFO and major indices to save memory
            self.options_data = [
                item for item in data 
                if item.get("exch_seg") == "NFO" 
                and item.get("name") in ["NIFTY", "BANKNIFTY"]
                and item.get("instrumenttype") == "OPTIDX"
            ]
            self.log(f"Options Engine Ready. Loaded {len(self.options_data)} contracts.")
        except Exception as e:
            self.log(f"Error loading Options Database: {e}")

    def log(self, message):
        msg = f"[{time.strftime('%H:%M:%S')}] {message}"
        print(msg)
        self.logs.append(msg)
        if len(self.logs) > 50:
            self.logs.pop(0)

    def login(self):
        try:
            if not all([API_KEY, CLIENT_ID, PASSWORD, TOTP_SECRET]) or API_KEY == "YOUR_API_KEY_HERE":
                self.log("Error: Missing API Credentials in config.py")
                return False
                
            self.log("Connecting to SmartAPI...")
            self.api = SmartConnect(api_key=API_KEY)
            
            # Generate TOTP
            totp = pyotp.TOTP(TOTP_SECRET).now()
            
            # Login
            data = self.api.generateSession(CLIENT_ID, PASSWORD, totp)
            
            if data['status']:
                self.connected = True
                self.log(f"Login Successful! Welcome {CLIENT_ID}")
                
                # Run Scrip Master download in a background thread so it doesn't block login
                threading.Thread(target=self.fetch_scrip_master, daemon=True).start()
                
                self.get_historical_data() # Fetch initial chart data
                return True
            else:
                self.log(f"Login Failed: {data.get('message')}")
                return False
                
        except Exception as e:
            self.log(f"Connection Error: {str(e)}")
            return False

    def update_settings(self, settings):
        category = settings.get('category', 'INDICES')
        symbol_input = settings.get('symbol', 'NIFTY').upper()
        
        old_symbol = getattr(self, 'symbol', '')
        
        # Hardcoded Token Map for Demo
        TOKEN_MAP = {
            "NIFTY": {"token": "26000", "exchange": "NSE", "symbol": "NIFTY"},
            "BANKNIFTY": {"token": "26009", "exchange": "NSE", "symbol": "BANKNIFTY"},
            "SENSEX": {"token": "99926000", "exchange": "BSE", "symbol": "SENSEX"},
            "RELIANCE": {"token": "2885", "exchange": "NSE", "symbol": "RELIANCE"},
            "TCS": {"token": "11536", "exchange": "NSE", "symbol": "TCS"},
            "HDFCBANK": {"token": "1333", "exchange": "NSE", "symbol": "HDFCBANK"},
            "INFY": {"token": "1594", "exchange": "NSE", "symbol": "INFY"},
            "ICICIBANK": {"token": "4963", "exchange": "NSE", "symbol": "ICICIBANK"},
            "SBIN": {"token": "3045", "exchange": "NSE", "symbol": "SBIN"},
            "BHARTIARTL": {"token": "10604", "exchange": "NSE", "symbol": "BHARTIARTL"},
            "ITC": {"token": "1660", "exchange": "NSE", "symbol": "ITC"},
            "LART": {"token": "11483", "exchange": "NSE", "symbol": "LT"},
            "BAJFINANCE": {"token": "317", "exchange": "NSE", "symbol": "BAJFINANCE"}
        }

        token_info = TOKEN_MAP.get(symbol_input)
        if token_info:
            self.symbol = token_info["symbol"]
            self.token = token_info["token"]
            self.exchange = token_info["exchange"]
        else:
            self.symbol = symbol_input
            self.exchange = "NSE"
            
        self.investment_amount = float(settings.get('investmentAmount', 10000))
        self.take_profit_target = float(settings.get('takeProfit', 0))
        self.stop_loss_target = float(settings.get('stopLoss', 0))
        self.max_trades = int(settings.get('maxTrades', 5))
        self.strategy = settings.get('strategy', self.strategy)
        self.moneyness = settings.get('moneyness', self.moneyness)
        self.category = category
        
        old_interval = self.interval
        self.interval = settings.get('interval', self.interval)
        interval_map = {"ONE_MINUTE": 60, "FIVE_MINUTE": 300, "FIFTEEN_MINUTE": 900, "ONE_HOUR": 3600, "ONE_DAY": 86400}
        self.interval_seconds = interval_map.get(self.interval, 60)
        
        self.log(f"Settings updated: Symbol={self.symbol}, Strategy={self.strategy}, Invest={self.investment_amount}")
        
        if (old_interval != self.interval or old_symbol != self.symbol) and self.connected:
            self.get_historical_data()

    def get_historical_data(self):
        if not self.connected:
            return
            
        try:
            self.log(f"Fetching historical data for {self.interval}...")
            now = datetime.datetime.now()
            if self.interval == "ONE_MINUTE":
                from_date = now - datetime.timedelta(days=3)
            elif self.interval == "FIVE_MINUTE":
                from_date = now - datetime.timedelta(days=10)
            elif self.interval == "FIFTEEN_MINUTE":
                from_date = now - datetime.timedelta(days=30)
            elif self.interval == "ONE_HOUR":
                from_date = now - datetime.timedelta(days=90)
            else: # ONE_DAY
                from_date = now - datetime.timedelta(days=365)
                
            historicParam={
                "exchange": self.exchange,
                "symboltoken": self.token,
                "interval": self.interval,
                "fromdate": from_date.strftime("%Y-%m-%d %H:%M"), 
                "todate": now.strftime("%Y-%m-%d %H:%M")
            }
            
            self.log(f"API Request: {historicParam}")
            
            response = self.api.getCandleData(historicParam)
            
            if response and response.get('status') and response.get('data'):
                self.candles.clear()
                self.price_history.clear()
                
                for row in response['data']:
                    # Format: '2026-05-11T09:15:00+05:30'
                    ts_str = row[0].replace("+05:30", "")
                    try:
                        dt_obj = datetime.datetime.fromisoformat(ts_str)
                        ts = int(dt_obj.timestamp())
                        
                        self.candles[ts] = {
                            "time": ts,
                            "open": row[1],
                            "high": row[2],
                            "low": row[3],
                            "close": row[4]
                        }
                        self.price_history.append(row[4])
                    except Exception as e:
                        self.log(f"Error parsing date {ts_str}: {e}")
                self.log(f"Fetched {len(self.candles)} historical candles.")
            else:
                self.log(f"Historical API Error: {response}")
        except Exception as e:
            self.log(f"Error fetching historical data: {str(e)}")

    def get_ltp(self):
        if not self.connected:
            return 0.0
        try:
            # Note: You need the correct symboltoken for the instrument.
            # You usually get this from Angel One's instrument list JSON.
            data = self.api.ltpData(self.exchange, f"{self.symbol}-EQ", self.token)
            if data and data.get('data'):
                return data['data']['ltp']
            return 0.0
        except Exception as e:
            self.log(f"Error fetching LTP: {str(e)}")
            return 0.0

    def calculate_rsi(self, series, period=14):
        if len(series) < period + 1:
            return 50 # Default neutral
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs.iloc[-1]))

    def calculate_ema(self, series, period):
        if len(series) < period:
            return series.iloc[-1] if not series.empty else 0
        return series.ewm(span=period, adjust=False).mean().iloc[-1]

    def calculate_macd(self, series, fast_period=12, slow_period=26, signal_period=9):
        if len(series) < slow_period + signal_period:
            return 0, 0
        ema_fast = series.ewm(span=fast_period, adjust=False).mean()
        ema_slow = series.ewm(span=slow_period, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
        return macd_line.iloc[-1], signal_line.iloc[-1]

    def calculate_bollinger_bands(self, series, period=20, std_dev=2):
        if len(series) < period:
            return 0, 0, 0
        sma = series.rolling(window=period).mean()
        rolling_std = series.rolling(window=period).std()
        upper_band = sma + (rolling_std * std_dev)
        lower_band = sma - (rolling_std * std_dev)
        return upper_band.iloc[-1], sma.iloc[-1], lower_band.iloc[-1]

    def get_strike_step(self, symbol):
        return 100 if symbol == "BANKNIFTY" else 50

    def find_option_token(self, spot_symbol, spot_ltp, option_type, moneyness):
        if not self.options_data:
            return None, None, 0
            
        step = self.get_strike_step(spot_symbol)
        atm_strike = round(spot_ltp / step) * step
        target_strike = atm_strike
        
        if option_type == "CE":
            if moneyness == "ITM": target_strike -= step * 2
            elif moneyness == "OTM": target_strike += step * 2
        else: # PE
            if moneyness == "ITM": target_strike += step * 2
            elif moneyness == "OTM": target_strike -= step * 2

        # Sort by expiry date, then try to match the strike exactly
        try:
            # Simple simulation of finding nearest expiry strike match
            # In a real environment, you'd parse item['expiry'] into datetime and find nearest
            for item in self.options_data:
                if item["name"] == spot_symbol and float(item["strike"]) == target_strike * 100 and item["symbol"].endswith(option_type):
                    return item["token"], item["symbol"], target_strike
        except Exception as e:
            self.log(f"Error finding token: {e}")
            
        return None, None, target_strike

    def analyze_market(self, ltp):
        # We store recent prices to calculate basic indicators locally
        self.price_history.append(ltp)
        if len(self.price_history) > 100:
            self.price_history.pop(0)
            
        if len(self.price_history) < 35: # Need enough data for 26 EMA + 9 MACD signal
            return "HOLD" # Not enough data
            
        # Convert to pandas Series for calculation
        prices = pd.Series(self.price_history)
        
        # Strategy: Multi-Indicator Condition
        ema_fast = self.calculate_ema(prices, 9)
        ema_slow = self.calculate_ema(prices, 21)
        rsi = self.calculate_rsi(prices, 14)
        macd_line, macd_signal = self.calculate_macd(prices)
        bb_upper, bb_mid, bb_lower = self.calculate_bollinger_bands(prices)
        
        # Log indicator status occasionally
        if time.time() % 30 < 5:
            self.log(f"[{self.strategy}] EMA:{ema_fast:.1f} RSI:{rsi:.1f} MACD:{macd_line:.1f} BB:{bb_lower:.1f}")

        # Signal Logic
        if self.position == 0:
            bullish = False
            bearish = False
            
            if self.strategy == "AGGRESSIVE":
                if ema_fast > ema_slow and macd_line > macd_signal and macd_line > 0: bullish = True
                if ema_fast < ema_slow and macd_line < macd_signal and macd_line < 0: bearish = True
            elif self.strategy == "BALANCED":
                if ema_fast > ema_slow and rsi > 50: bullish = True
                if ema_fast < ema_slow and rsi < 50: bearish = True
            elif self.strategy == "CONSERVATIVE":
                if ema_fast > ema_slow and macd_line > macd_signal and 40 < rsi < 70 and ltp < bb_mid: bullish = True
                if ema_fast < ema_slow and macd_line < macd_signal and 40 < rsi < 70 and ltp > bb_mid: bearish = True

            if bullish:
                self.log(f"Bullish Setup Triggered! ({self.strategy})")
                return "BUY_CE" if self.category == "OPTIONS" else "BUY"
            if bearish:
                self.log(f"Bearish Setup Triggered! ({self.strategy})")
                return "BUY_PE" if self.category == "OPTIONS" else "HOLD"
            
        return "HOLD"

    def check_risk_management(self):
        if self.position == 1:
            if self.active_option:
                try:
                    opt_data = self.api.ltpData("NFO", self.active_option["symbol"], self.active_option["token"])
                    if opt_data and opt_data.get('data'):
                        opt_ltp = opt_data['data']['ltp']
                        profit = (opt_ltp - self.active_option["entry_price"]) * self.active_option["qty"]
                        
                        if self.take_profit_target > 0 and profit >= self.take_profit_target:
                            self.log(f"Take Profit hit! {self.active_option['symbol']} Profit: +{profit:.2f}")
                            self.execute_trade("SELL_OPTION", current_opt_price=opt_ltp)
                        elif self.stop_loss_target > 0 and profit <= -self.stop_loss_target:
                            self.log(f"Stop Loss hit! {self.active_option['symbol']} Loss: {profit:.2f}")
                            self.execute_trade("SELL_OPTION", current_opt_price=opt_ltp)
                except Exception as e:
                    self.log(f"Error checking option risk: {e}")
            else:
                profit = (self.last_price - self.buy_price) * self.quantity
                if self.take_profit_target > 0 and profit >= self.take_profit_target:
                    self.log(f"Take Profit hit! Profit: +{profit:.2f}")
                    self.execute_trade("SELL")
                elif self.stop_loss_target > 0 and profit <= -self.stop_loss_target:
                    self.log(f"Stop Loss hit! Loss: {profit:.2f}")
                    self.execute_trade("SELL")

    def execute_trade(self, signal, current_opt_price=None):
        if signal.startswith("BUY") and self.current_trades >= self.max_trades:
            self.log("Max trades limit reached for today. Skipping.")
            return
            
        timestamp = int(time.time())
        
        if signal in ["BUY_CE", "BUY_PE"]:
            option_type = "CE" if signal == "BUY_CE" else "PE"
            opt_token, opt_symbol, target_strike = self.find_option_token(self.symbol, self.last_price, option_type, self.moneyness)
            
            if not opt_token:
                self.log(f"Could not find {self.moneyness} {option_type} for {self.symbol} at {target_strike} strike.")
                return
                
            try:
                opt_data = self.api.ltpData("NFO", opt_symbol, opt_token)
                if not opt_data or not opt_data.get('data'):
                    self.log(f"Failed to fetch premium for {opt_symbol}")
                    return
                opt_price = opt_data['data']['ltp']
            except Exception as e:
                self.log(f"Error fetching option premium: {e}")
                return
                
            qty = int(self.investment_amount / opt_price) if opt_price > 0 else 0
            
            if qty < 1:
                self.log(f"Investment ₹{self.investment_amount} too low for {opt_symbol} (₹{opt_price}). Try OTM.")
                return
                
            self.position = 1
            self.active_option = {
                "token": opt_token,
                "symbol": opt_symbol,
                "entry_price": opt_price,
                "qty": qty,
                "type": option_type
            }
            self.current_trades += 1
            
            self.log(f"Executing {signal} for {qty} qty of {opt_symbol} at ₹{opt_price}")
            
            self.trade_history.append({
                "time": timestamp,
                "price": self.last_price, # Chart spot price
                "type": "BUY",
                "qty": qty,
                "pnl": 0,
                "opt_symbol": opt_symbol,
                "opt_price": opt_price
            })
            
        elif signal == "SELL_OPTION" and self.active_option:
            pnl = (current_opt_price - self.active_option["entry_price"]) * self.active_option["qty"]
            self.log(f"Executing SELL for {self.active_option['qty']} qty of {self.active_option['symbol']} at ₹{current_opt_price}")
            
            self.trade_history.append({
                "time": timestamp,
                "price": self.last_price,
                "type": "SELL",
                "qty": self.active_option["qty"],
                "pnl": round(pnl, 2),
                "opt_symbol": self.active_option["symbol"]
            })
            self.position = 0
            self.active_option = None
            
        elif signal == "BUY":
            # Calculate how many shares we can buy with the investment amount
            qty = int(self.investment_amount / self.last_price)
            if qty < 1:
                self.log(f"Investment ₹{self.investment_amount} is too low to buy 1 share of {self.symbol} at ₹{self.last_price}. Trade Skipped.")
                return
                
            self.position = 1
            self.buy_price = self.last_price
            self.quantity = qty
            self.current_trades += 1
            
            self.log(f"Executing BUY for {self.quantity} qty of {self.symbol} at ₹{self.last_price}")
            
            self.trade_history.append({
                "time": timestamp,
                "price": self.last_price,
                "type": "BUY",
                "qty": self.quantity,
                "pnl": 0
            })
            self.log(f"Trade executed. Total trades: {self.current_trades}/{self.max_trades}")
            
        elif signal == "SELL":
            # PNL is (Sell Price - Buy Price) * Quantity
            pnl = (self.last_price - self.buy_price) * self.quantity
            
            self.log(f"Executing SELL for {self.quantity} qty of {self.symbol} at ₹{self.last_price}")
            
            self.trade_history.append({
                "time": timestamp,
                "price": self.last_price,
                "type": "SELL",
                "qty": self.quantity,
                "pnl": round(pnl, 2)
            })
            self.position = 0
            self.buy_price = 0.0
            self.quantity = 0
            self.log("Position Closed.")

    def trading_loop(self):
        self.log("Trading bot started.")
        while self.is_running:
            try:
                # 1. Fetch Market Data
                self.last_price = self.get_ltp()
                
                if self.last_price > 0:
                    # Update OHLC Candles based on interval
                    current_time = int(time.time())
                    minute_ts = current_time - (current_time % self.interval_seconds)

                    
                    if minute_ts not in self.candles:
                        # New candle
                        self.candles[minute_ts] = {
                            "time": minute_ts,
                            "open": self.last_price,
                            "high": self.last_price,
                            "low": self.last_price,
                            "close": self.last_price
                        }
                    else:
                        # Update current candle
                        candle = self.candles[minute_ts]
                        candle["high"] = max(candle["high"], self.last_price)
                        candle["low"] = min(candle["low"], self.last_price)
                        candle["close"] = self.last_price
                
                # 2. Analyze Market
                signal = self.analyze_market(self.last_price)
                
                # 3. Check Risk Management (Take Profit / Stop Loss)
                self.check_risk_management()
                
                # 4. Execute Trade
                if signal.startswith('BUY') and self.position == 0:
                    self.execute_trade(signal)
                    
            except Exception as e:
                self.log(f"Error in trading loop: {str(e)}")
                
            time.sleep(5) # Wait 5 seconds before next cycle to avoid rate limits
            
        self.log("Trading bot stopped.")

    def start(self):
        if self.is_running:
            return
        
        if not self.connected:
            if not self.login():
                return
                
        self.is_running = True
        self.thread = threading.Thread(target=self.trading_loop)
        self.thread.daemon = True
        self.thread.start()

    def stop(self):
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=2)
            
    def get_status(self):
        # Convert candles dict to sorted list
        candle_list = [self.candles[ts] for ts in sorted(self.candles.keys())]
        
        return {
            "isRunning": self.is_running,
            "connected": self.connected,
            "symbol": self.symbol,
            "lastPrice": self.last_price,
            "currentTrades": self.current_trades,
            "maxTrades": self.max_trades,
            "logs": self.logs[-10:], # Return last 10 logs
            "candles": candle_list,
            "tradeHistory": self.trade_history
        }
