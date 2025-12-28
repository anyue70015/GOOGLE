import requests
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from typing import Dict

# Constants
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# 1. Fetch OHLCV Data from Yahoo Finance API
def fetch_ohlcv(symbol: str, period: str = "1y") -> pd.DataFrame:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={period}&interval=1d"
    try:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()  # Check for request errors
        data = response.json()

        # Check if the response contains the expected data
        if "chart" not in data or data["chart"]["result"] is None:
            print(f"Error: No data available for {symbol}")
            return None
        
        # Create DataFrame from the response
        df = pd.DataFrame(data["chart"]["result"][0]["indicators"]["quote"][0])
        df["timestamp"] = pd.to_datetime(data["chart"]["result"][0]["timestamp"], unit="s")
        df.set_index("timestamp", inplace=True)
        df = df.dropna()  # Remove rows with missing data
        return df
    
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data for {symbol}: {e}")
        return None

# 2. Calculate Technical Indicators

# Moving Average Convergence Divergence (MACD)
def macd(df: pd.DataFrame, column: str = "close", fast=12, slow=26, signal=9) -> pd.Series:
    fast_ema = df[column].ewm(span=fast, min_periods=fast).mean()
    slow_ema = df[column].ewm(span=slow, min_periods=slow).mean()
    macd_line = fast_ema - slow_ema
    macd_signal = macd_line.ewm(span=signal, min_periods=signal).mean()
    return macd_line, macd_signal

# Relative Strength Index (RSI)
def rsi(df: pd.DataFrame, column: str = "close", period: int = 14) -> pd.Series:
    delta = df[column].diff(1)
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# Exponential Moving Average (EMA)
def ema(df: pd.DataFrame, column: str = "close", window: int = 20) -> pd.Series:
    return df[column].ewm(span=window, min_periods=window).mean()

# Average True Range (ATR)
def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

# On-Balance Volume (OBV)
def obv(df: pd.DataFrame) -> pd.Series:
    obv = np.sign(df['close'].diff()) * df['volume']
    return obv.cumsum()

# 3. Generate Buy/Sell Signals Based on Indicators
def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # Calculate Indicators
    df["macd"], df["macd_signal"] = macd(df, "close")
    df["rsi"] = rsi(df, "close")
    df["ema20"] = ema(df, "close", 20)
    df["ema50"] = ema(df, "close", 50)
    df["atr14"] = atr(df)
    df["obv"] = obv(df)

    # Generate signals: Buy when MACD crosses above, Sell when MACD crosses below
    df["buy_signal"] = (df["macd"] > df["macd_signal"]) & (df["rsi"] < 30) & (df["close"] > df["ema20"]) & (df["obv"] > df["obv"].rolling(20).mean())
    df["sell_signal"] = (df["macd"] < df["macd_signal"]) & (df["rsi"] > 70) & (df["close"] < df["ema20"]) & (df["obv"] < df["obv"].rolling(20).mean())

    return df

# 4. Backtest Function: Evaluate Strategy Performance
def backtest(df: pd.DataFrame, initial_cash: float = 10000, hold_days: int = 7) -> Dict:
    df = df.copy()
    df["cash"] = initial_cash
    df["position"] = 0
    df["capital"] = initial_cash
    df["returns"] = 0.0
    df["buy_price"] = np.nan
    df["sell_price"] = np.nan

    for i in range(1, len(df)):
        # Buy signal
        if df["buy_signal"].iloc[i] and df["position"].iloc[i-1] == 0:
            df.loc[df.index[i], "position"] = df["cash"].iloc[i-1] // df["close"].iloc[i]
            df.loc[df.index[i], "buy_price"] = df["close"].iloc[i]
            df.loc[df.index[i], "cash"] = df["cash"].iloc[i-1] - df["position"].iloc[i] * df["buy_price"].iloc[i]

        # Sell signal
        elif df["sell_signal"].iloc[i] and df["position"].iloc[i-1] > 0:
            df.loc[df.index[i], "cash"] = df["position"].iloc[i-1] * df["close"].iloc[i]
            df.loc[df.index[i], "sell_price"] = df["close"].iloc[i]
            df.loc[df.index[i], "position"] = 0

        # Calculate capital (cash + position value)
        df.loc[df.index[i], "capital"] = df["cash"].iloc[i] + df["position"].iloc[i] * df["close"].iloc[i]

    # Performance metrics
    df["returns"] = df["capital"].pct_change()
    total_returns = df["returns"].sum()
    final_capital = df["capital"].iloc[-1]

    return {
        "total_returns": total_returns,
        "final_capital": final_capital,
        "capital_curve": df["capital"],
    }

# 5. Plot Capital Curve (Performance Over Time)
def plot_capital_curve(capital_curve: pd.Series):
    plt.figure(figsize=(10, 6))
    plt.plot(capital_curve, label="Capital Curve")
    plt.title("Backtest Capital Curve")
    plt.xlabel("Date")
    plt.ylabel("Capital ($)")
    plt.legend()
    plt.grid(True)
    plt.show()

# 6. Main Function for Running the Strategy
def main(symbol: str):
    df = fetch_ohlcv(symbol)
    if df is not None:
        df = generate_signals(df)
        result = backtest(df)
        print(f"Total Returns: {result['total_returns'] * 100:.2f}%")
        print(f"Final Capital: ${result['final_capital']:.2f}")
        plot_capital_curve(result["capital_curve"])

if __name__ == "__main__":
    symbol = "AAPL"  # Example: Apple Stock
    main(symbol)
