import pandas as pd
import numpy as np
import ta
from options_pricing import OptionsPricing
from scipy.stats import norm

def add_synthetic_greeks(df, prefix=''):
    """
    Calculates synthetic Greeks for an ATM option with 1 day to expiry.
    This helps the model understand the 'Gamma Risk' and 'Theta Decay' environment.
    """
    op = OptionsPricing()
    
    # Estimate Rolling Volatility (Annualized)
    # Log returns
    log_ret = np.log(df['Close'] / df['Close'].shift(1))
    window = 20
    # 15m bars -> ~26 bars/day (6.5 hours * 4 bars/hour). 20 bars ~ 7.5 hours.
    # Annualize: sqrt(252 * 26) approx sqrt(6552) = 81
    vol = log_ret.rolling(window=window).std() * np.sqrt(252 * 26)
    vol = vol.fillna(0.20) # Default to 20%
    
    # Constants for Synthetic Option
    T = 1 / 252 # 1 Day to expiry
    r = 0.045 # Risk free rate
    
    # Vectorized Black-Scholes Greeks (Simplified for ATM)
    S = df['Close'].values
    sigma = vol.values
    
    # d1 calculation
    sqrt_T = np.sqrt(T)
    d1 = (r + 0.5 * sigma**2) * T / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T
    
    # Greeks (Call)
    delta = norm.cdf(d1)
    N_prime_d1 = norm.pdf(d1)
    gamma = N_prime_d1 / (S * sigma * sqrt_T)
    theta = -(S * sigma * N_prime_d1) / (2 * sqrt_T) / 365
    vega = S * sqrt_T * N_prime_d1 / 100
    
    # Assign to DF
    df[f'{prefix}ATM_Delta'] = delta
    df[f'{prefix}ATM_Gamma'] = gamma
    df[f'{prefix}ATM_Theta'] = theta
    df[f'{prefix}ATM_Vega'] = vega
    df[f'{prefix}ATM_IV'] = sigma
    
    return df

def add_features(df, prefix=''):
    """
    Adds technical indicators and time-based features.
    """
    df = df.copy()
    
    # Ensure we have single-level columns if MultiIndex
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
        
    # Basic cleanup
    df = df.dropna()
    
    # 1. Trend Indicators
    df[f'{prefix}EMA_20'] = ta.trend.ema_indicator(df['Close'], window=20)
    df[f'{prefix}EMA_50'] = ta.trend.ema_indicator(df['Close'], window=50)
    df[f'{prefix}EMA_20_Slope'] = df[f'{prefix}EMA_20'].diff()
    df[f'{prefix}EMA_50_Slope'] = df[f'{prefix}EMA_50'].diff()
    
    adx = ta.trend.ADXIndicator(df['High'], df['Low'], df['Close'], window=14)
    df[f'{prefix}ADX'] = adx.adx()
    df[f'{prefix}DMP'] = adx.adx_pos()
    df[f'{prefix}DMN'] = adx.adx_neg()
    df[f'{prefix}MACD'] = ta.trend.macd_diff(df['Close'])
    
    # 2. Volatility
    bb = ta.volatility.BollingerBands(df['Close'], window=20, window_dev=2)
    df[f'{prefix}BB_Width'] = bb.bollinger_wband()
    df[f'{prefix}BB_Pband'] = bb.bollinger_pband()
    df[f'{prefix}ATR'] = ta.volatility.average_true_range(df['High'], df['Low'], df['Close'], window=14)
    
    # 3. Momentum
    df[f'{prefix}RSI'] = ta.momentum.rsi(df['Close'], window=14)
    
    # 4. Returns
    df[f'{prefix}Log_Ret'] = np.log(df['Close'] / df['Close'].shift(1))
    
    # 5. Synthetic Greeks
    df = add_synthetic_greeks(df, prefix=prefix)
    
    return df

def resample_and_merge(df_15m, timeframe, prefix):
    """
    Resamples 15m data to a higher timeframe (e.g., '1H', '4H'),
    calculates features, and merges back to 15m via forward fill.
    """
    agg_dict = {
        'Open': 'first',
        'High': 'max',
        'Low': 'min',
        'Close': 'last',
        'Volume': 'sum'
    }
    
    df_resampled = df_15m.resample(timeframe).agg(agg_dict).dropna()
    df_resampled = add_features(df_resampled, prefix=prefix)
    
    # Select only feature columns to merge back
    feature_cols = [c for c in df_resampled.columns if c not in agg_dict.keys()]
    df_resampled_features = df_resampled[feature_cols]
    
    # Shift so we use CLOSED candle data
    df_resampled_features = df_resampled_features.shift(1)
    
    # Merge back to 15m
    df_merged = df_15m.join(df_resampled_features, how='left')
    df_merged = df_merged.ffill()  # Forward fill missing values
    
    return df_merged

def prepare_pair_features(df_main, df_ref, main_ticker='SPY', ref_ticker='IWM'):
    """
    Combines Main and Ref data and creates spread/correlation features.
    """
    # 1. Base Features for each
    df_main = add_features(df_main, prefix=f'{main_ticker}_')
    df_ref = add_features(df_ref, prefix=f'{ref_ticker}_')
    
    # 2. Resampled Features (1H, 4H)
    # Since base is 15m, we resample to 1h and 4h for multi-timeframe analysis
    df_main = resample_and_merge(df_main, '1h', f'{main_ticker}_1H_')
    df_main = resample_and_merge(df_main, '4h', f'{main_ticker}_4H_')
    
    # Rename base columns to match prefix pattern
    map_main = {c: f"{main_ticker}_{c}" for c in ['Open', 'High', 'Low', 'Close', 'Volume'] if c in df_main.columns}
    map_ref = {c: f"{ref_ticker}_{c}" for c in ['Open', 'High', 'Low', 'Close', 'Volume'] if c in df_ref.columns}
    
    df_main = df_main.rename(columns=map_main)
    df_ref = df_ref.rename(columns=map_ref)
    
    # Join
    df = df_main.join(df_ref, how='inner')
    
    # 3. Pair Features
    main_close = f"{main_ticker}_Close"
    ref_close = f"{ref_ticker}_Close"
    
    df['Spread_Log'] = np.log(df[main_close]) - np.log(df[ref_close])
    
    # Z-Score of Spread (Rolling)
    window = 50 
    spread_mean = df['Spread_Log'].rolling(window=window).mean()
    spread_std = df['Spread_Log'].rolling(window=window).std()
    df['Spread_Z'] = (df['Spread_Log'] - spread_mean) / spread_std
    
    # Rolling Correlation
    df[f'Corr_{main_ticker}_{ref_ticker}'] = df[main_close].rolling(window=20).corr(df[ref_close])
    
    # Target Creation: TRENDING STRATEGY
    # Predict movement over next 4 bars (1 hour = 4 * 15min bars)
    lookahead = 4 # 1 Hour (4 bars at 15m)
    future_ret = np.log(df[main_close].shift(-lookahead) / df[main_close])
    
    # Lower threshold to detect more trends (0.08% move = more sensitive)
    threshold = 0.0008  # Reduced from 0.0015 for better trend detection
    
    conditions = [
        (future_ret > threshold),
        (future_ret < -threshold)
    ]
    choices = [1, -1] 
    
    df['Target'] = np.select(conditions, choices, default=0)
    
    # Drop NaN
    df = df.dropna()
    
    return df
