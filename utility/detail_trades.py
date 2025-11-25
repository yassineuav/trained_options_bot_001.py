import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import yfinance as yf
import sys
import os
from datetime import datetime, timedelta

def plot_candlesticks(ax, df):
    """
    Plots candlestick chart on the given axes.
    """
    # Reset index to get integer indices for x-axis (avoids gaps)
    df = df.reset_index()
    
    # Define colors
    col_up = '#26a69a' # Green
    col_down = '#ef5350' # Red
    
    # Plot Up Candles
    up = df[df['Close'] >= df['Open']]
    ax.bar(up.index, up['Close'] - up['Open'], width=0.6, bottom=up['Open'], color=col_up, alpha=1.0)
    ax.vlines(up.index, up['Low'], up['High'], color=col_up, linewidth=1)
    
    # Plot Down Candles
    down = df[df['Close'] < df['Open']]
    ax.bar(down.index, down['Close'] - down['Open'], width=0.6, bottom=down['Open'], color=col_down, alpha=1.0)
    ax.vlines(down.index, down['Low'], down['High'], color=col_down, linewidth=1)
    
    return df # Return df with reset index for mapping

def create_detailed_chart(csv_file, symbol=None):
    # 1. Load Trade Journal
    try:
        journal = pd.read_csv(csv_file)
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return

    if journal.empty:
        print("Journal is empty.")
        return
        
    # Ensure EntryTime and ExitTime are datetime
    # Check if EntryTime exists (backward compatibility)
    if 'EntryTime' not in journal.columns:
        print("Error: 'EntryTime' column missing. Please re-run backtest to generate new journal format.")
        return
        
    journal['EntryTime'] = pd.to_datetime(journal['EntryTime'])
    journal['ExitTime'] = pd.to_datetime(journal['ExitTime'])
    
    # 2. Determine Symbol and Date Range
    if not symbol:
        # Try to infer from filename
        base = os.path.basename(csv_file)
        parts = base.split('_')
        if len(parts) >= 3:
            symbol = parts[2] # trade_journal_SYMBOL_DATE.csv
        else:
            symbol = 'SPY' # Default
            
    print(f"Generating chart for {symbol}...")
    
    # Get range
    start_date = journal['EntryTime'].min() - timedelta(days=2)
    end_date = journal['ExitTime'].max() + timedelta(days=1)
    
    # 3. Fetch Price Data
    print(f"Fetching data from {start_date} to {end_date}...")
    df_price = yf.download(symbol, start=start_date, end=end_date, interval='1h', progress=False, auto_adjust=True)
    
    if df_price.empty:
        print("Error: No price data found.")
        return
        
    # Flatten MultiIndex columns if present (yfinance update)
    if isinstance(df_price.columns, pd.MultiIndex):
        df_price.columns = df_price.columns.get_level_values(0)
        
    # 4. Plotting
    # We'll plot the last 100 bars or a specific window. 
    # Since there are many trades, let's plot the last 5 days of trading activity.
    # Or plot the whole thing? 1 year is too much for detailed view.
    # Let's plot the last 10 trades context.
    
    last_trades = journal.tail(10)
    if last_trades.empty: return
    
    plot_start = last_trades['EntryTime'].min() - timedelta(days=1)
    plot_end = last_trades['ExitTime'].max() + timedelta(hours=4)
    
    subset = df_price.loc[plot_start:plot_end].copy()
    if subset.empty:
        print("No data in the trade window.")
        return
        
    # Setup Figure
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(16, 9))
    
    # Plot Candlesticks
    subset_reset = plot_candlesticks(ax, subset)
    
    # Map timestamps to x-indices
    time_to_idx = {t: i for i, t in enumerate(subset.index)}
    
    # Overlay Trades
    for _, trade in last_trades.iterrows():
        entry_time = trade['EntryTime']
        exit_time = trade['ExitTime']
        
        # Find closest indices
        # We need to handle exact match or closest
        # Since we downloaded 1h data, timestamps should match if aligned.
        # But yfinance timestamps might be slightly different (timezone).
        # Let's try to match by nearest.
        
        try:
            # Find index of nearest timestamp in subset
            start_idx = subset.index.get_indexer([entry_time], method='nearest')[0]
            end_idx = subset.index.get_indexer([exit_time], method='nearest')[0]
            
            # Get price levels
            # We don't have exact entry price in journal, but we can estimate from strike/premium or just use the bar's close.
            # Actually, we want to draw the box based on Strike? 
            # The user image shows P/$235.
            # Let's draw the box from Entry Price to Exit Price?
            # Or just mark the trade.
            # Let's use the Strike price as a reference level, or the underlying price at entry.
            # We can get underlying price from subset at start_idx.
            
            entry_price = subset.iloc[start_idx]['Close']
            exit_price = subset.iloc[end_idx]['Close']
            
            # Color: Green if PnL > 0, Red if PnL <= 0
            is_win = trade['PnL'] > 0
            color = '#00ff00' if is_win else '#ff0000'
            fill_color = color
            
            # Draw Box/Rectangle covering the trade duration
            # Width = end_idx - start_idx
            # Height? Let's make it cover the price movement or a fixed height relative to price.
            # Let's draw a rectangle from Entry Price to Exit Price.
            
            rect_width = max(1, end_idx - start_idx)
            rect_height = exit_price - entry_price
            
            # If height is 0 (same bar), make it visible
            if abs(rect_height) < 0.1: rect_height = 0.5 if is_win else -0.5
            
            # Draw Rectangle
            rect = plt.Rectangle((start_idx, entry_price), rect_width, rect_height, 
                                 facecolor=fill_color, alpha=0.3, edgecolor=color)
            ax.add_patch(rect)
            
            # Draw Line connecting Entry to Exit
            ax.plot([start_idx, end_idx], [entry_price, exit_price], color=color, linestyle='--', linewidth=1)
            
            # Annotation Text
            # Format: (Call/Put) / $Strike / PnL%
            # Example: C / $245 / +50%
            type_str = "C" if trade['Type'] == 'call' else "P"
            pnl_str = f"{trade['PnL%']:+.0f}%"
            text = f"{type_str} / ${trade['Strike']} / {pnl_str}"
            
            # Position text above or below
            text_y = max(entry_price, exit_price) + (subset['High'].max() - subset['Low'].min()) * 0.02
            
            ax.text(start_idx, text_y, text, color='white', fontsize=9, fontweight='bold',
                    bbox=dict(facecolor=color, alpha=0.5, edgecolor='none', pad=2))
            
        except Exception as e:
            print(f"Skipping trade at {entry_time}: {e}")
            continue

    # Formatting
    ax.set_title(f"Detailed Trade Analysis: {symbol} (Last 10 Trades)", fontsize=16, fontweight='bold')
    ax.set_ylabel("Price")
    ax.grid(True, alpha=0.1)
    
    # Format X-Axis
    # Show date labels every N bars
    step = max(1, len(subset) // 10)
    ax.set_xticks(range(0, len(subset), step))
    ax.set_xticklabels([d.strftime('%m-%d %H:%M') for d in subset.index[::step]], rotation=45)
    
    plt.tight_layout()
    
    # Save
    # Use the same directory as the CSV file
    csv_dir = os.path.dirname(csv_file)
    output_file = os.path.join(csv_dir if csv_dir else '.', 'detail_chart.png')
    
    plt.savefig(output_file, dpi=150)
    print(f"📸 Detailed Chart saved to '{output_file}'")
    plt.show()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python detail_trades.py <csv_file>")
    else:
        create_detailed_chart(sys.argv[1])
