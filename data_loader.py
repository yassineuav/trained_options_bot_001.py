import yfinance as yf
import pandas as pd
import os

def load_data(symbol, period="60d", interval="15m", start_date=None, end_date=None):
    """
    Loads data for a given symbol.
    Tries to load from local CSV first (e.g., 'SPY_15m.csv'),
    otherwise downloads from yfinance.
    
    Note: yfinance 15m data is limited to the last 60 days.
    For 5 years of 15m data, you must provide a CSV file.
    """
    file_path = f"{symbol}_{interval}.csv"
    
    if os.path.exists(file_path):
        print(f"Loading {symbol} data from {file_path}...")
        df = pd.read_csv(file_path, parse_dates=['Datetime'], index_col='Datetime')
        # Filter by date if provided
        if start_date:
            df = df[df.index >= start_date]
        if end_date:
            df = df[df.index <= end_date]
        return df
    
    print(f"Downloading {symbol} data from yfinance (Limit: 60d for 15m)...")
   
    # We will fetch the maximum available if period is long.
    
    try:
        df = yf.download(symbol, period=period, interval=interval, progress=False, auto_adjust=True)
        if df.empty:
            raise ValueError("No data downloaded.")
        
        # Ensure index is Datetime
        if not isinstance(df.index, pd.DatetimeIndex):
             df.index = pd.to_datetime(df.index)
             
        # Save for future use
        # df.to_csv(file_path) # Optional: don't overwrite if testing different periods
        return df
    except Exception as e:
        print(f"Error downloading {symbol}: {e}")
        return pd.DataFrame()

def align_data(df1, df2):
    """
    Aligns two dataframes on their index (Datetime).
    """
    common_index = df1.index.intersection(df2.index)
    return df1.loc[common_index], df2.loc[common_index]
