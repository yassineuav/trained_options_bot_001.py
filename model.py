from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import classification_report, accuracy_score
import joblib
import pandas as pd
import numpy as np

def train_model(df):
    """
    Trains a RandomForest model with TimeSeriesSplit.
    """
    # Feature Selection
    # Exclude non-feature columns (OHLCV and Target)
    exclude_keywords = ['Target', 'Open', 'High', 'Low', 'Close', 'Volume']
    feature_cols = [c for c in df.columns if not any(kw in c for kw in exclude_keywords)]
    
    X = df[feature_cols]
    y = df['Target']
    
    # Time Series Split
    tscv = TimeSeriesSplit(n_splits=5)
    
    model = RandomForestClassifier(
        n_estimators=100,
        max_depth=5, # Prevent overfitting
        min_samples_leaf=10,
        random_state=42,
        n_jobs=-1,
        class_weight='balanced'
    )
    
    print("Starting Time-Series Cross-Validation...")
    for fold, (train_index, test_index) in enumerate(tscv.split(X)):
        X_train, X_test = X.iloc[train_index], X.iloc[test_index]
        y_train, y_test = y.iloc[train_index], y.iloc[test_index]
        
        model.fit(X_train, y_train)
        preds = model.predict(X_test)
        acc = accuracy_score(y_test, preds)
        print(f"Fold {fold+1} Accuracy: {acc:.4f}")
        
    # Final Train on all data
    print("Training final model on full dataset...")
    model.fit(X, y)
    
    # Feature Importance
    importances = pd.Series(model.feature_importances_, index=feature_cols).sort_values(ascending=False)
    print("\nTop 10 Features:")
    print(importances.head(10))
    
    return model, feature_cols
