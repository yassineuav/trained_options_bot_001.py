import pandas as pd
import numpy as np
import yfinance as yf
import joblib
import matplotlib.pyplot as plt
import features
from options_pricing import OptionsPricing
from datetime import datetime, timedelta
import sys
import warnings

# Suppress matplotlib's internal FutureWarnings (library issue, not our code)
warnings.filterwarnings('ignore', category=FutureWarning, module='matplotlib')

def get_latest_signal(symbol='SPY'):
    print(f"🚀 Fetching Live Market Data for {symbol}...")
    
    # Determine reference symbol
    ref_symbol = 'SPY' if symbol == 'IWM' else 'IWM'
    if symbol == 'SPY': ref_symbol = 'IWM'
    
    # Fetch enough data for feature engineering (need ~200 bars for rolling windows)
    # Use 15m interval to match training data
    df_main = yf.download(symbol, period='60d', interval='15m', progress=False, auto_adjust=True)
    df_ref = yf.download(ref_symbol, period='60d', interval='15m', progress=False, auto_adjust=True)
    
    if df_main.empty or df_ref.empty:
        print("Error: No data fetched.")
        return

    # Align
    common_index = df_main.index.intersection(df_ref.index)
    df_main = df_main.loc[common_index]
    df_ref = df_ref.loc[common_index]
    
    # Feature Engineering
    print("🧠 Processing Features...")
    df_processed = features.prepare_pair_features(df_main, df_ref, main_ticker=symbol, ref_ticker=ref_symbol)
    
    if df_processed.empty:
        print("Error: Not enough data for features.")
        return

    # Load Model
    print("🔮 Loading AI Model...")
    
    # Try to load symbol-specific model from folder first
    import os
    now = datetime.now()
    # New structure: SYMBOL/HHMM_MM_DD/ - try to find latest session
    symbol_folder = symbol
    session_folder = f"{now.strftime('%H%M')}_{now.strftime('%m_%d')}"
    folder_name = os.path.join(symbol_folder, session_folder)
    model_filename = os.path.join(folder_name, 'trained_model.pkl')
    
    try:
        model = joblib.load(model_filename)
        print(f"Loaded model: {model_filename}")
    except:
        # Try to find any model in symbol folder (latest session)
        try:
            if os.path.exists(symbol_folder):
                sessions = sorted([d for d in os.listdir(symbol_folder) if os.path.isdir(os.path.join(symbol_folder, d))], reverse=True)
                if sessions:
                    latest_session = sessions[0]
                    folder_name = os.path.join(symbol_folder, latest_session)
                    models = [f for f in os.listdir(folder_name) if f.startswith('trained_model') and f.endswith('.pkl')]
                    if models:
                        model_filename = os.path.join(folder_name, models[0])
                        model = joblib.load(model_filename)
                        print(f"Loaded model: {model_filename}")
                    else:
                        raise FileNotFoundError
                else:
                    raise FileNotFoundError
            else:
                raise FileNotFoundError
        except:
            print(f"Error: No model found. Please train first with: python main.py {symbol}")
            return

    # Get Latest Data Point
    last_row = df_processed.iloc[[-1]]
    last_price = last_row[f'{symbol}_Close'].values[0]
    last_time = last_row.index[0]
    
    # Predict - use same feature selection as training
    # Exclude OHLCV and Target columns
    exclude_keywords = ['Target', 'Open', 'High', 'Low', 'Close', 'Volume']
    feature_cols = [c for c in df_processed.columns if not any(kw in c for kw in exclude_keywords)]
    
    X_new = last_row[feature_cols]
    
    prediction = model.predict(X_new)[0]
    probs = model.predict_proba(X_new)[0]
    
    # Probability of the predicted class
    classes = model.classes_
    print(f"Model Classes: {classes}")
    print(f"Probabilities: {probs}")
    
    # Map probs to labels
    prob_map = {c: p*100 for c, p in zip(classes, probs)}
    print(f"Bearish: {prob_map.get(-1, 0):.2f}% | Neutral: {prob_map.get(0, 0):.2f}% | Bullish: {prob_map.get(1, 0):.2f}%")
    
    print(f"\n🔎 ANALYSIS FOR {last_time} (Latest Closed Bar)")
    print(f"Current {symbol} Price: ${last_price:.2f}")
    
    # Use probability-based decision (more sensitive to trends)
    bullish_prob = prob_map.get(1, 0)
    bearish_prob = prob_map.get(-1, 0)
    neutral_prob = prob_map.get(0, 0)
    
    # Lower threshold to 25% to detect more signals
    confidence_threshold = 25.0
    
    # Check recent price momentum for trend confirmation
    recent_bars = df_main.iloc[-20:]  # Last 20 bars (5 hours)
    # Handle potential MultiIndex columns from yfinance
    if isinstance(recent_bars.columns, pd.MultiIndex):
        close_col = ('Close', df_main.columns.get_level_values(1)[0]) if len(df_main.columns.levels) > 1 else 'Close'
    else:
        close_col = 'Close'
    price_change_pct = ((recent_bars[close_col].iloc[-1] - recent_bars[close_col].iloc[0]) / recent_bars[close_col].iloc[0]) * 100
    
    # Determine signal based on probabilities
    if bullish_prob >= confidence_threshold and bullish_prob > bearish_prob:
        prediction = 1
        win_prob = bullish_prob
    elif bearish_prob >= confidence_threshold and bearish_prob > bullish_prob:
        prediction = -1
        win_prob = bearish_prob
    # Override: If strong price momentum detected (>0.5% move), follow the trend
    elif abs(price_change_pct) > 0.5:
        if price_change_pct > 0:
            prediction = 1
            win_prob = max(bullish_prob, 30.0)  # Minimum 30% confidence
            print(f"📈 Strong Bullish Momentum Detected: +{price_change_pct:.2f}% (Last 5 hours)")
        else:
            prediction = -1
            win_prob = max(bearish_prob, 30.0)
            print(f"📉 Strong Bearish Momentum Detected: {price_change_pct:.2f}% (Last 5 hours)")
    else:
        prediction = 0
        win_prob = neutral_prob
    
    if prediction == 0:
        print("Signal: NEUTRAL (No Trade Triggered)")
        print("Market is currently consolidating or trend is weak.")
        generate_chart(df_main, last_row, 0, 0, 0, 0, symbol, 50, 0, 0)
        return
    
    direction = "BULLISH (Call)" if prediction == 1 else "BEARISH (Put)"
    print(f"Signal: {direction}")
    
    print(f"Confidence: {win_prob:.2f}%")
    
    # Option Selection (0.3% OTM)
    op = OptionsPricing()
    otm_pct = 0.003
    if prediction == 1:
        strike = round(last_price * (1 + otm_pct))
        opt_type = 'call'
    else:
        strike = round(last_price * (1 - otm_pct))
        opt_type = 'put'
        
    print(f"Recommended Option: {symbol} {strike} {opt_type.upper()}")
    
    # Calculate Theoretical Entry/Exit
    T_years = 1 / 252 # 1 Day
    sigma = 0.15 # Approx IV
    
    entry_premium = op.black_scholes(last_price, strike, T_years, sigma, opt_type)
    
    # Strategy Targets
    tp_pct = 5.0 # 500%
    sl_pct = 0.40 # 40%
    
    tp_premium = entry_premium * (1 + tp_pct)
    sl_premium = entry_premium * (1 - sl_pct)
    
    print(f"Est. Entry Premium: ${entry_premium:.2f}")
    print(f"Target Premium (500%): ${tp_premium:.2f}")
    print(f"Stop Loss Premium (-40%): ${sl_premium:.2f}")
    
    # Calculate 1-Hour Price Prediction
    # Based on model confidence and historical volatility
    predicted_move_pct = win_prob / 100 * 0.005  # Scale by confidence (max 0.5% move)
    if prediction == 1:
        predicted_price_1h = last_price * (1 + predicted_move_pct)
        stop_price_1h = last_price * (1 - 0.002)  # 0.2% stop
    else:
        predicted_price_1h = last_price * (1 - predicted_move_pct)
        stop_price_1h = last_price * (1 + 0.002)  # 0.2% stop
    
    print(f"\n📊 1-HOUR PRICE PREDICTION:")
    print(f"Current Price: ${last_price:.2f}")
    print(f"Predicted Target (1H): ${predicted_price_1h:.2f} ({'+' if prediction == 1 else '-'}{predicted_move_pct*100:.2f}%)")
    print(f"Stop Loss Level: ${stop_price_1h:.2f}")
    print(f"Risk/Reward Ratio: {abs(predicted_price_1h - last_price) / abs(stop_price_1h - last_price):.2f}:1")
    
    # Charting
    generate_chart(df_main, last_row, prediction, strike, tp_pct, sl_pct, symbol, win_prob, predicted_price_1h, stop_price_1h, output_folder=folder_name)

def generate_chart(df, last_row, signal, strike, tp_pct, sl_pct, symbol, confidence=50, target_price=0, stop_price=0, output_folder=None):
    # Plot last 50 bars
    subset = df.iloc[-50:]
    last_price = last_row[f'{symbol}_Close'].values[0]
    last_time = last_row.index[0]
    
    fig, ax = plt.subplots(figsize=(14, 7))
    plt.style.use('dark_background')
    
    # Plot Price
    ax.plot(subset.index, subset['Close'], color='#00d4ff', label=f'{symbol} Price', linewidth=2, alpha=0.8)
    
    # Plot Signal Point
    color = '#00ff00' if signal == 1 else '#ff0000'
    marker = '^' if signal == 1 else 'v'
    if signal != 0:
        ax.scatter(last_time, last_price, color=color, s=200, marker=marker, label='Entry Point', zorder=5, edgecolors='white', linewidths=2)
    
    # Draw 1-Hour Prediction Box
    next_time = last_time + timedelta(hours=1)
    
    if signal != 0:
        # Use actual predicted prices
        if target_price == 0:  # Fallback if not provided
            move_pct = 0.005
            target_price = last_price * (1 + move_pct) if signal == 1 else last_price * (1 - move_pct)
            stop_price = last_price * (1 - move_pct/3) if signal == 1 else last_price * (1 + move_pct/3)
        
        # Draw prediction box
        # Convert time difference to matplotlib date units
        import matplotlib.dates as mdates
        box_width_days = (next_time - last_time).total_seconds() / 86400  # Convert to days for matplotlib
        box_height = abs(target_price - last_price)
        box_bottom = min(last_price, target_price)
        
        # Prediction zone (green for bullish, red for bearish)
        rect = plt.Rectangle((mdates.date2num(last_time), last_price), box_width_days, target_price - last_price,
                             facecolor=color, alpha=0.2, edgecolor=color, linewidth=2, linestyle='--')
        ax.add_patch(rect)
        
        # Draw trend arrow
        arrow_props = dict(arrowstyle='->', lw=3, color=color)
        ax.annotate('', xy=(next_time, target_price), xytext=(last_time, last_price),
                   arrowprops=arrow_props, zorder=10)
        
        # Draw stop loss line
        ax.hlines(stop_price, last_time, next_time, colors='red', linestyles='solid', linewidth=2, label='Stop Loss', alpha=0.7)
        
        # Add labels
        mid_time = last_time + timedelta(minutes=30)
        # Fix Series float conversion warning
        price_range = subset['Close'].max() - subset['Close'].min()
        ax.text(mid_time, target_price + price_range * 0.02,
               f'Target: ${target_price:.2f}', color='white', fontsize=11, fontweight='bold',
               bbox=dict(boxstyle='round', facecolor=color, alpha=0.7), ha='center')
        
        ax.text(mid_time, stop_price - price_range * 0.02,
               f'Stop: ${stop_price:.2f}', color='white', fontsize=10,
               bbox=dict(boxstyle='round', facecolor='darkred', alpha=0.7), ha='center')
        
        # Confidence indicator
        confidence_text = f'{confidence:.0f}% Confidence'
        ax.text(0.02, 0.98, confidence_text, transform=ax.transAxes,
               fontsize=12, verticalalignment='top',
               bbox=dict(boxstyle='round', facecolor='black', alpha=0.8, edgecolor=color, linewidth=2),
               color=color, fontweight='bold')
    
    # Annotations (removed emojis to fix font warning)
    signal_text = 'BULLISH ▲' if signal == 1 else ('BEARISH ▼' if signal == -1 else 'NEUTRAL ─')
    title_color = '#00ff00' if signal == 1 else ('#ff0000' if signal == -1 else '#ffaa00')
    
    ax.set_title(f"{signal_text} Signal | {symbol} ${last_price:.2f} | Next 1 Hour Prediction",
                fontsize=16, color=title_color, fontweight='bold', pad=20)
    ax.set_xlabel("Time", fontsize=12)
    ax.set_ylabel("Price ($)", fontsize=12)
    ax.legend(loc='upper left', fontsize=10)
    ax.grid(True, alpha=0.15, linestyle='--')
    
    # Format y-axis
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:.2f}'))
    
    plt.tight_layout()
    
    # Save with symbol and date in organized folder
    import os
    now = datetime.now()
    
    if output_folder:
        folder_name = output_folder
    else:
        # New structure: SYMBOL/HHMM_MM_DD/
        symbol_folder = symbol
        session_folder = f"{now.strftime('%H%M')}_{now.strftime('%m_%d')}"
        folder_name = os.path.join(symbol_folder, session_folder)
        
    os.makedirs(folder_name, exist_ok=True)
    
    filename = os.path.join(folder_name, 'signal_chart.png')
    plt.savefig(filename, dpi=150, bbox_inches='tight')
    print(f"📸 Chart saved to '{filename}'")

if __name__ == "__main__":
    # Parse command line argument
    symbol = 'SPY'
    if len(sys.argv) > 1:
        symbol = sys.argv[1].upper()
    
    get_latest_signal(symbol)
