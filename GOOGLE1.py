import pandas as pd
import numpy as np
import talib
import yfinance as yf

# 计算MACD指标
def macd(df: pd.DataFrame, column: str = "close", fast=12, slow=26, signal=9) -> pd.Series:
    # 确保列存在
    if column not in df.columns:
        raise KeyError(f"列 '{column}' 不存在于数据中")
    
    fast_ema = df[column].ewm(span=fast, min_periods=fast).mean()
    slow_ema = df[column].ewm(span=slow, min_periods=slow).mean()
    macd_line = fast_ema - slow_ema
    macd_signal = macd_line.ewm(span=signal, min_periods=signal).mean()
    return macd_line, macd_signal

# 计算EMA指标
def ema(df: pd.DataFrame, column: str = "close", window: int = 20) -> pd.Series:
    # 确保列存在
    if column not in df.columns:
        raise KeyError(f"列 '{column}' 不存在于数据中")
    return df[column].ewm(span=window, adjust=False).mean()

# 计算RSI
def rsi(df: pd.DataFrame, column: str = "close", window: int = 14) -> pd.Series:
    return talib.RSI(df[column], timeperiod=window)

# 计算ATR
def atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    return talib.ATR(df['high'], df['low'], df['close'], timeperiod=window)

# 计算OBV
def obv(df: pd.DataFrame) -> pd.Series:
    return talib.OBV(df['close'], df['volume'])

# 生成信号
def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # 确保每个列都有数据
    required_columns = ['close', 'high', 'low', 'volume']
    for col in required_columns:
        if col not in df.columns:
            raise KeyError(f"数据缺少必要的列: {col}")
    
    # 计算指标
    df["macd"], df["macd_signal"] = macd(df, "close")
    df["rsi"] = rsi(df, "close")
    df["ema20"] = ema(df, "close", 20)
    df["ema50"] = ema(df, "close", 50)
    df["atr14"] = atr(df)
    df["obv"] = obv(df)

    # 生成信号：当MACD线上穿信号线，RSI低于30，价格高于20日EMA，OBV上升时买入
    df["buy_signal"] = (df["macd"] > df["macd_signal"]) & (df["rsi"] < 30) & (df["close"] > df["ema20"]) & (df["obv"] > df["obv"].rolling(20).mean())
    # 当MACD线下穿信号线，RSI高于70，价格低于20日EMA，OBV下降时卖出
    df["sell_signal"] = (df["macd"] < df["macd_signal"]) & (df["rsi"] > 70) & (df["close"] < df["ema20"]) & (df["obv"] < df["obv"].rolling(20).mean())

    return df

# 获取美股数据
def fetch_data(symbol: str, start: str, end: str) -> pd.DataFrame:
    # 使用yfinance获取数据
    df = yf.download(symbol, start=start, end=end)
    return df

# 扫描多个股票，生成信号
def scan(symbols: list, start: str, end: str) -> pd.DataFrame:
    all_results = []
    
    for symbol in symbols:
        df = fetch_data(symbol, start, end)
        signals = generate_signals(df)
        signals['symbol'] = symbol
        all_results.append(signals)

    # 合并所有股票的数据
    return pd.concat(all_results)

# 示例股票池
symbols = ['AAPL', 'GOOGL', 'MSFT', 'AMZN', 'TSLA']

# 执行扫描
start_date = '2020-01-01'
end_date = '2021-01-01'
result = scan(symbols, start_date, end_date)

# 显示结果
print(result[['symbol', 'close', 'macd', 'macd_signal', 'rsi', 'ema20', 'ema50', 'atr14', 'obv', 'buy_signal', 'sell_signal']].tail())
