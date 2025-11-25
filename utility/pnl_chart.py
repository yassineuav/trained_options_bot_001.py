import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import sys
import os
from datetime import datetime

def create_pnl_chart(csv_file):
    """
    Creates a candlestick-style P&L chart from trade journal.
    Green bars for winning trades, red bars for losing trades.
    """
    # Read the trade journal
    try:
        df = pd.read_csv(csv_file)
    except FileNotFoundError:
        print(f"Error: File '{csv_file}' not found.")
        return
    
    if df.empty:
        print("Error: Trade journal is empty.")
        return
    
    # Convert DateTime to datetime objects
    # Handle new format (ExitTime) vs old format (DateTime)
    if 'ExitTime' in df.columns:
        df['DateTime'] = pd.to_datetime(df['ExitTime'])
    elif 'DateTime' in df.columns:
        df['DateTime'] = pd.to_datetime(df['DateTime'])
    else:
        print("Error: Could not find 'ExitTime' or 'DateTime' column.")
        return
    
    # Create figure with dark background
    plt.style.use('dark_background')
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 10), gridspec_kw={'height_ratios': [3, 1]})
    
    # === Chart 1: P&L Candlesticks ===
    
    # Prepare data for candlestick-style bars
    for idx, row in df.iterrows():
        # Determine color based on P&L
        color = '#00ff00' if row['PnL'] > 0 else '#ff0000'
        alpha = 0.8
        
        # Draw vertical line (wick) from entry to exit premium
        entry_prem = row['EntryPremium']
        exit_prem = row['ExitPremium']
        
        # Bar height represents P&L percentage
        pnl_pct = row['PnL%']
        
        # Draw bar
        ax1.bar(idx, pnl_pct, color=color, alpha=alpha, width=0.8, edgecolor='white', linewidth=0.5)
    
    # Add horizontal line at 0%
    ax1.axhline(y=0, color='white', linestyle='--', linewidth=1, alpha=0.5)
    
    # Add TP and SL reference lines
    ax1.axhline(y=500, color='green', linestyle=':', linewidth=1, alpha=0.3, label='TP Target (500%)')
    ax1.axhline(y=-40, color='red', linestyle=':', linewidth=1, alpha=0.3, label='SL (-40%)')
    
    # Formatting
    ax1.set_ylabel('P&L %', fontsize=12, fontweight='bold')
    ax1.set_title('Trade P&L Distribution (Candlestick View)', fontsize=14, fontweight='bold')
    ax1.grid(True, alpha=0.2, axis='y')
    ax1.legend(loc='upper right')
    
    # Set x-axis labels (show every 10th trade)
    tick_positions = range(0, len(df), max(1, len(df) // 20))
    tick_labels = [f"#{i+1}" for i in tick_positions]
    ax1.set_xticks(tick_positions)
    ax1.set_xticklabels(tick_labels, rotation=45)
    
    # === Chart 2: Cumulative Balance ===
    
    # Calculate cumulative balance
    balance_curve = df['Balance'].values
    
    # Plot balance curve
    ax2.plot(range(len(balance_curve)), balance_curve, color='#00ffff', linewidth=2, label='Account Balance')
    ax2.fill_between(range(len(balance_curve)), balance_curve, alpha=0.3, color='#00ffff')
    
    # Add starting balance line
    ax2.axhline(y=balance_curve[0] - df.iloc[0]['PnL'], color='yellow', linestyle='--', linewidth=1, alpha=0.5, label='Starting Balance')
    
    # Formatting
    ax2.set_xlabel('Trade Number', fontsize=12, fontweight='bold')
    ax2.set_ylabel('Balance ($)', fontsize=12, fontweight='bold')
    ax2.set_title('Cumulative Account Balance', fontsize=14, fontweight='bold')
    ax2.grid(True, alpha=0.2)
    ax2.legend(loc='upper left')
    
    # Format y-axis with commas
    ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))
    
    # Set x-axis labels
    ax2.set_xticks(tick_positions)
    ax2.set_xticklabels(tick_labels, rotation=45)
    
    # Add statistics box
    total_trades = len(df)
    wins = len(df[df['PnL'] > 0])
    losses = len(df[df['PnL'] <= 0])
    win_rate = (wins / total_trades) * 100 if total_trades > 0 else 0
    avg_win = df[df['PnL'] > 0]['PnL%'].mean()
    avg_loss = df[df['PnL'] <= 0]['PnL%'].mean()
    net_pnl = df['PnL'].sum()
    final_balance = balance_curve[-1]
    initial_balance = balance_curve[0] - df.iloc[0]['PnL']
    return_pct = (net_pnl / initial_balance) * 100
    
    stats_text = f"""
    Total Trades: {total_trades}
    Wins: {wins} | Losses: {losses}
    Win Rate: {win_rate:.1f}%
    Avg Win: {avg_win:.1f}%
    Avg Loss: {avg_loss:.1f}%
    Net P&L: ${net_pnl:,.2f} ({return_pct:,.0f}% return!)
    Final Balance: ${final_balance:,.2f}
    """
    
    # Add text box
    props = dict(boxstyle='round', facecolor='black', alpha=0.8, edgecolor='cyan')
    ax1.text(0.02, 0.98, stats_text, transform=ax1.transAxes, fontsize=10,
             verticalalignment='top', bbox=props, family='monospace', color='cyan')
    
    plt.tight_layout()
    
    # Save chart
    # Use the same directory as the CSV file
    csv_dir = os.path.dirname(csv_file)
    output_file = os.path.join(csv_dir if csv_dir else '.', 'pnl_chart.png')
    
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f"📊 P&L Chart saved to '{output_file}'")
    
    # Show plot
    plt.show()

def main():
    """
    Main function to handle command line arguments.
    """
    if len(sys.argv) < 2:
        print("Usage: python pnl_chart.py <path_to_trade_journal.csv>")
        print("Example: python pnl_chart.py SPY_11_24_2025/trade_journal_SPY_20251124.csv")
        print("\nOr specify symbol to auto-find today's journal:")
        print("Example: python pnl_chart.py SPY")
        return
    
    arg = sys.argv[1]
    
    # Check if argument is a file path or symbol
    if arg.endswith('.csv'):
        csv_file = arg
    else:
        # Assume it's a symbol, find latest session
        symbol = arg.upper()
        now = datetime.now()
        
        # New structure: SYMBOL/TIME_DATE/
        if os.path.exists(symbol):
            sessions = sorted([d for d in os.listdir(symbol) if os.path.isdir(os.path.join(symbol, d))], reverse=True)
            if sessions:
                latest_session = sessions[0]
                folder = os.path.join(symbol, latest_session)
                journals = [f for f in os.listdir(folder) if f.startswith('trade_journal') and f.endswith('.csv')]
                if journals:
                    csv_file = os.path.join(folder, journals[0])
                else:
                    print(f"Error: No trade journal found in '{folder}'")
                    return
            else:
                print(f"Error: No sessions found for {symbol}")
                return
        else:
            print(f"Error: Symbol folder '{symbol}' not found")
            print(f"Please run: python main.py {symbol}")
            return
    
    create_pnl_chart(csv_file)

if __name__ == "__main__":
    main()
