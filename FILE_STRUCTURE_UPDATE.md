# File Structure Restructuring Update

## ✅ Changes Implemented

The project file saving mechanism has been restructured to organize outputs by **Symbol** and **Session Timestamp**.

### New Folder Structure
```
patterns detected/
├── {SYMBOL}/                  (e.g., SPY/)
│   └── {HHMM}_{MM}_{DD}/      (e.g., 1230_11_25/)
│       ├── trained_model.pkl
│       ├── trade_journal.csv
│       ├── pnl_chart.png
│       ├── signal_chart.png
│       └── detail_chart.png
```

### Updated Scripts

1.  **`main.py`**
    - Creates the session folder: `{SYMBOL}/{HHMM}_{MM}_{DD}/`
    - Saves the trained model as `trained_model.pkl`.
    - Saves the trade journal as `trade_journal.csv`.

2.  **`backtest.py`**
    - Saves `trade_journal.csv` in the session folder.

3.  **`utility/predict_signal.py`**
    - Loads `trained_model.pkl` from the session folder.
    - Saves `signal_chart.png` in the same session folder.

4.  **`utility/pnl_chart.py`**
    - Saves `pnl_chart.png` in the same directory as the input CSV file.

5.  **`utility/detail_trades.py`**
    - Saves `detail_chart.png` in the same directory as the input CSV file.

## 🚀 How to Use

Run the main script as usual:
```bash
python main.py SPY
```
All outputs will be automatically organized into a new timestamped folder under `SPY/`.

## Example Output
For a run at 12:30 PM on Nov 25:
`SPY/1230_11_25/` will contain all 5 output files.
