import data_loader
import features
import model
import backtest
import pandas as pd
import joblib
import sys

def main():
    print("🤖 Initializing Professional ML Trading Bot...")
    
    # Parse Command Line Arguments
    symbol = 'SPY'
    if len(sys.argv) > 1:
        symbol = sys.argv[1].upper()
        
    print(f"🎯 Target Asset: {symbol}")
    
    # 1. Data Ingestion
    print("\n[1/4] Loading Data...")
    # Use 15m interval for optimal 0DTE trading (yfinance limit: 60d for 15m)
    df_main = data_loader.load_data(symbol, period="60d", interval="15m")
    
    # Determine Reference Asset
    ref_symbol = 'SPY' if symbol == 'IWM' else 'IWM'
    if symbol == 'SPY': ref_symbol = 'IWM' # Default case
    
    df_ref = data_loader.load_data(ref_symbol, period="60d", interval="15m")
    
    if df_main.empty or df_ref.empty:
        print("Critical Error: Could not load data. Exiting.")
        return

    # Align data
    df_main, df_ref = data_loader.align_data(df_main, df_ref)
    print(f"Data Loaded: {len(df_main)} bars from {df_main.index[0]} to {df_main.index[-1]}")
    
    # 2. Feature Engineering
    print("\n[2/4] Engineering Features...")
    # Pass symbol as main_ticker
    df_processed = features.prepare_pair_features(df_main, df_ref, main_ticker=symbol, ref_ticker=ref_symbol)
    print(f"Features created. Dataset shape: {df_processed.shape}")
    
    # 3. Model Training
    print("\n[3/4] Training Model...")
    trained_model, feature_cols = model.train_model(df_processed)
    
    # Save with symbol and date in organized folder
    from datetime import datetime
    import os
    
    now = datetime.now()
    # New structure: SYMBOL/HHMM_MM_DD/
    symbol_folder = symbol
    session_folder = f"{now.strftime('%H%M')}_{now.strftime('%m_%d')}"  # e.g., 1230_11_25
    folder_name = os.path.join(symbol_folder, session_folder)
    os.makedirs(folder_name, exist_ok=True)
    
    model_filename = os.path.join(folder_name, 'trained_model.pkl')
    joblib.dump(trained_model, model_filename)
    print(f"Model saved to '{model_filename}'")
    
    # 4. Backtest
    print("\n[4/4] Running Backtest...")
    bt = backtest.Backtester(df_processed, trained_model, feature_cols, initial_balance=1000, symbol=symbol)
    bt.run()
    
    # Define journal file path
    journal_file = os.path.join(folder_name, 'trade_journal.csv')

    # 5. Generate Visualizations
    print("\n[5/7] Generating P&L Chart...")
    try:
        from utility import pnl_chart
        pnl_chart.create_pnl_chart(journal_file)
    except Exception as e:
        print(f"⚠️ P&L Chart generation failed: {e}")
    
    # 6. Get Live Signal
    print("\n[6/7] Fetching Live Signal...")
    try:
        from utility import predict_signal
        predict_signal.get_latest_signal(symbol)
    except Exception as e:
        print(f"⚠️ Signal prediction failed: {e}")
    
    # 7. Generate Detailed Trade Chart
    print("\n[7/7] Generating Detailed Trade Chart...")
    try:
        from utility import detail_trades
        detail_trades.create_detailed_chart(journal_file, symbol)
    except Exception as e:
        print(f"⚠️ Detailed trade chart generation failed: {e}")
    
    print("\n✅ Process Complete. All outputs saved to '{}'".format(folder_name))
    

if __name__ == "__main__":
    main()
