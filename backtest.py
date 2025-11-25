import pandas as pd
import numpy as np
from options_pricing import OptionsPricing

class Backtester:
    def __init__(self, df, model, feature_cols, initial_balance=1000, symbol='SPY'):
        self.df = df
        self.model = model
        self.feature_cols = feature_cols
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.journal = []
        self.position = None 
        self.op = OptionsPricing()
        self.symbol = symbol
        
    def run(self):
        print(f"Starting 0DTE Options Backtest for {self.symbol}...")
        
        X = self.df[self.feature_cols]
        predictions = self.model.predict(X)
        
        # Iterate
        for i in range(20, len(self.df) - 1): # Start at 20 for vol calc
            current_bar = self.df.iloc[i]
            timestamp = self.df.index[i]
            
            # 0DTE Logic: We only trade if we can exit today.
            # Market Open: 9:30 AM ET
            # Market Close: 4:00 PM ET (16:00)
            # We need to handle timezones. Assuming data is in ET or aligned.
            # If data is UTC (yfinance default), 9:30 ET is 13:30 UTC (Standard) or 14:30 UTC (Daylight).
            # Let's rely on the hour components if possible, or just strict time windows relative to open.
            
            # Check if we have an open position
            if self.position:
                self.check_exit(current_bar, timestamp)
            
            # Entry Logic (Only if no position)
            if not self.position:
                # Time Filters (High Volume Windows)
                # Morning: 9:30 - 11:00
                # Mid: 12:00 - 13:00
                # Pre-Close: 14:30 - 15:15 (Don't enter too late)
                
                # Convert to local time components for filtering (Assuming index is datetime)
                # We'll assume the index is already localized or we use .hour
                # yfinance returns UTC. We need to be careful.
                # Let's assume the data loader didn't convert, so it's UTC.
                # 13:30 UTC = 9:30 ET.
                
                t = timestamp
                # Simple check: Is it a trading time?
                # We'll define "Trading Windows" in UTC for simplicity, assuming standard time (approx).
                # Better: Use relative time from start of day.
                
                # Get time of day
                tod_minutes = t.hour * 60 + t.minute
                
                # Define Windows (Approximate for UTC 13:30 Open)
                # Open is usually 13:30 or 14:30.
                # Let's detect the "start of day" dynamically or just assume standard market hours.
                # Since we are iterating, we can check if it's the first bar of the day?
                # Let's just use the signal and strict TP/SL. The user asked for specific times.
                
                # Let's map 9:30-16:00 ET to 13:30-20:00 UTC (Standard)
                # Morning: 13:30 - 15:00
                # Mid: 16:00 - 17:00
                # Late: 18:30 - 19:15
                
                is_morning = (t.hour == 13 and t.minute >= 30) or (t.hour == 14)
                is_mid = (t.hour == 16)
                is_late = (t.hour == 18) or (t.hour == 19 and t.minute <= 15)
                
                if is_morning or is_mid or is_late:
                    signal = predictions[i]
                    if signal != 0:
                        self.enter_position(signal, current_bar, timestamp, i)

        self.generate_report()
        
    def enter_position(self, signal, bar, timestamp, index):
        # 1. Determine Option Type
        # Signal 1 (Long) -> Call
        # Signal -1 (Short) -> Put
        option_type = 'call' if signal == 1 else 'put'
        
        # 2. Underlying Price
        spot_price = bar[f'{self.symbol}_Close']
        
        # Sanity check on spot price
        if spot_price <= 0 or spot_price > 10000:
            return  # Invalid price
        
        # 3. Select Strike (OTM Strategy)
        # We want OTM options that have a high probability of going ITM.
        # Target ~0.3% OTM (approx $1.50 - $2.00 on SPY)
        # This gives cheaper premiums (higher leverage) but realistic ITM chance.
        otm_pct = 0.003
        if option_type == 'call':
            strike = round(spot_price * (1 + otm_pct))
        else:
            strike = round(spot_price * (1 - otm_pct))
        
        # 4. Calculate Time to Expiry (T)
        # 0DTE expires at 16:00 ET (20:00 UTC).
        # Calculate hours remaining.
        # Assuming 20:00 is close.
        market_close_hour = 20 
        market_close_minute = 0
        
        current_minutes = timestamp.hour * 60 + timestamp.minute
        close_minutes = market_close_hour * 60 + market_close_minute
        
        minutes_remaining = close_minutes - current_minutes
        if minutes_remaining <= 15: return # Too close to expiry
        if minutes_remaining > 400: return # Too far from expiry (> 6.5 hours)
        
        T_years = minutes_remaining / (252 * 6.5 * 60) # Annualized
        
        # 5. Estimate Volatility
        # Use last 20 bars of Close
        history = self.df[f'{self.symbol}_Close'].iloc[index-20:index]
        sigma = self.op.estimate_volatility(history)
        
        # Cap volatility to realistic bounds (10% - 100% annualized)
        sigma = max(0.10, min(sigma, 1.00))
        
        # 6. Calculate Option Price (Premium)
        premium = self.op.black_scholes(spot_price, strike, T_years, sigma, option_type)
        
        # Outlier Detection: Reject unrealistic premiums
        if premium < 0.05: return # Too cheap/illiquid
        if premium > 50.0: return # Unrealistically expensive (likely calculation error)
        
        # Additional sanity check: Premium should be reasonable relative to spot
        max_reasonable_premium = spot_price * 0.15  # Max 15% of spot price
        if premium > max_reasonable_premium:
            return  # Reject outlier
        
        # 7. Position Sizing
        # 5% to 20% of balance
        size_pct = 0.20 # Increased to 20% to allow entry on small account
        capital_alloc = self.balance * size_pct
        
        # Number of contracts (x100 multiplier)
        # contracts = capital / (premium * 100)
        num_contracts = int(capital_alloc / (premium * 100))
        
        # Cap maximum contracts to prevent extreme leverage
        max_contracts = 100
        num_contracts = min(num_contracts, max_contracts)
        
        # If allocation is too small for 1 contract, try to use more capital (up to 50%)
        if num_contracts < 1:
            if self.balance * 0.50 >= (premium * 100):
                num_contracts = 1
            else:
                return # Cannot afford even 1 contract safely
        
        cost_basis = num_contracts * premium * 100
        
        # Final sanity check: Don't risk more than 50% of account on one trade
        if cost_basis > self.balance * 0.50:
            return
        
        # 8. Greeks
        greeks = self.op.calculate_greeks(spot_price, strike, T_years, sigma, option_type)
        
        # 9. TP/SL (Aggressive Growth Strategy)
        # TP: 500% (Moonshot), SL: 40% (Risk Tolerance)
        # Trailing Stop will secure profits between 50% and 500%
        tp_pct = 5.0 # 500% 
        sl_pct = 0.40 # 40% Hard Stop
        
        self.position = {
            'type': option_type,
            'strike': strike,
            'entry_premium': premium,
            'contracts': num_contracts,
            'cost_basis': cost_basis,
            'entry_time': timestamp,
            'sigma': sigma, 
            'sl_price': premium * (1 - sl_pct),
            'tp_price': premium * (1 + tp_pct),
            'greeks': greeks,
            'max_premium': premium # Track max price for trailing stop
        }
        
    def check_exit(self, bar, timestamp):
        p = self.position
        spot_price = bar[f'{self.symbol}_Close']
        
        # Sanity check on spot price
        if spot_price <= 0 or spot_price > 10000:
            # Force close with entry premium if price is invalid
            self.close_position(p['entry_premium'], 0, 'Error_InvalidPrice', timestamp, p['entry_premium'])
            return
        
        # Update Time
        market_close_hour = 20
        current_minutes = timestamp.hour * 60 + timestamp.minute
        close_minutes = market_close_hour * 60
        minutes_remaining = close_minutes - current_minutes
        
        # Force Close at End of Day
        if minutes_remaining <= 15:
            self.close_position(spot_price, minutes_remaining, 'EOD_Expire', timestamp)
            return

        # Recalculate Option Price
        T_years = minutes_remaining / (252 * 6.5 * 60)
        current_premium = self.op.black_scholes(spot_price, p['strike'], T_years, p['sigma'], p['type'])
        
        # Outlier Detection: Cap premium to reasonable bounds
        # Premium should not exceed 10x entry premium (even for 500% TP, this is 6x)
        max_reasonable_premium = p['entry_premium'] * 10
        if current_premium > max_reasonable_premium:
            current_premium = max_reasonable_premium  # Cap it
        
        # Premium should not be negative
        if current_premium < 0:
            current_premium = 0.01  # Floor at 1 cent
        
        # Update Max Premium for Trailing Stop
        if current_premium > p['max_premium']:
            p['max_premium'] = current_premium
            
        # Trailing Stop Logic
        # Trail by 20% from Peak
        trail_pct = 0.20
        trailing_stop_price = p['max_premium'] * (1 - trail_pct)
        
        # Check Exits
        status = None
        
        # 1. Hard SL (Safety)
        if current_premium <= p['sl_price']:
            status = 'Loss_SL'
        # 2. Trailing Stop (Lock Profits)
        elif current_premium <= trailing_stop_price and current_premium > p['entry_premium']:
            status = 'Win_Trail'
        elif current_premium <= trailing_stop_price and current_premium <= p['entry_premium']:
            status = 'Loss_Trail' # Trailed out below entry
        # 3. TP (Moonshot)
        elif current_premium >= p['tp_price']:
            status = 'Win_TP_Moon'
            
        if status:
            self.close_position(spot_price, minutes_remaining, status, timestamp, current_premium)
            
    def close_position(self, spot_price, minutes_remaining, reason, timestamp, final_premium=None):
        p = self.position
        
        # If premium not provided (EOD), calc it
        if final_premium is None:
            T_years = minutes_remaining / (252 * 6.5 * 60)
            final_premium = self.op.black_scholes(spot_price, p['strike'], T_years, p['sigma'], p['type'])
            
        # PnL
        proceeds = final_premium * p['contracts'] * 100
        pnl = proceeds - p['cost_basis']
        pnl_pct = (pnl / p['cost_basis']) * 100
        
        self.balance += pnl
        
        # Log
        # Log
        self.journal.append({
            'EntryTime': p['entry_time'],
            'ExitTime': timestamp,
            'Type': p['type'],
            'Strike': p['strike'],
            'EntryPremium': round(p['entry_premium'], 2),
            'ExitPremium': round(final_premium, 2),
            'Contracts': p['contracts'],
            'Status': reason,
            'PnL': round(pnl, 2),
            'PnL%': round(pnl_pct, 2),
            'Balance': round(self.balance, 2),
            'Delta': round(p['greeks']['delta'], 2),
            'Gamma': round(p['greeks']['gamma'], 4),
            'Theta': round(p['greeks']['theta'], 2)
        })
        
        self.position = None

    def generate_report(self):
        df_journal = pd.DataFrame(self.journal)
        if df_journal.empty:
            print("No trades taken.")
            return
        
        # Save with symbol and date in organized folder
        from datetime import datetime
        import os
        
        now = datetime.now()
        # New structure: SYMBOL/HHMM_MM_DD/
        symbol_folder = self.symbol
        session_folder = f"{now.strftime('%H%M')}_{now.strftime('%m_%d')}"
        folder_name = os.path.join(symbol_folder, session_folder)
        os.makedirs(folder_name, exist_ok=True)
        
        filename = os.path.join(folder_name, 'trade_journal.csv')
        df_journal.to_csv(filename, index=False)
        print(f"📊 Trade journal saved to '{filename}'")
        
        total_trades = len(df_journal)
        wins = len(df_journal[df_journal['PnL'] > 0])
        losses = len(df_journal[df_journal['PnL'] <= 0])
        win_rate = (wins / total_trades) * 100 if total_trades > 0 else 0
        net_pnl = df_journal['PnL'].sum()
        
        avg_win = df_journal[df_journal['PnL'] > 0]['PnL%'].mean()
        avg_loss = df_journal[df_journal['PnL'] <= 0]['PnL%'].mean()
        
        # Calculate return percentage
        return_pct = (net_pnl / self.initial_balance) * 100
        
        print("\n" + "="*30)
        print("0DTE OPTIONS PERFORMANCE")
        print("="*30)
        print(f"Total Trades: {total_trades}")
        print(f"Win Rate: {win_rate:.2f}%")
        print(f"Avg Win: {avg_win:.2f}%")
        print(f"Avg Loss: {avg_loss:.2f}%")
        print(f"Net PnL: ${net_pnl:,.2f} ({return_pct:,.0f}% return!)")
        print(f"Final Balance: ${self.balance:,.2f}")
        print("="*30)
