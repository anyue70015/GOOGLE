import requests
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# 常量
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# 1. 从Yahoo Finance获取股票OHLCV数据
def fetch_ohlcv(symbol: str, period: str = "1y") -> pd.DataFrame:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={period}&interval=1d"
    try:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()  # 检查请求是否成功
        data = response.json()

        if "chart" not in data or data["chart"]["result"] is None:
            print(f"错误：{symbol}没有可用数据")
            return None
        
        df = pd.DataFrame(data["chart"]["result"][0]["indicators"]["quote"][0])
        df["timestamp"] = pd.to_datetime(data["chart"]["result"][0]["timestamp"], unit="s")
        df.set_index("timestamp", inplace=True)
        df = df.dropna()  # 去掉缺失数据
        return df
    
    except requests.exceptions.RequestException as e:
        print(f"获取{symbol}数据时出错：{e}")
        return None

# 2. 计算技术指标

# 计算MACD指标
def macd(df: pd.DataFrame, column: str = "close", fast=12, slow=26, signal=9) -> pd.Series:
    fast_ema = df[column].ewm(span=fast, min_periods=fast).mean()
    slow_ema = df[column].ewm(span=slow, min_periods=slow).mean()
    macd_line = fast_ema - slow_ema
    macd_signal = macd_line.ewm(span=signal, min_periods=signal).mean()
    return macd_line, macd_signal

# 计算RSI指标
def rsi(df: pd.DataFrame, column: str = "close", period: int = 14) -> pd.Series:
    delta = df[column].diff(1)
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# 计算EMA指标
def ema(df: pd.DataFrame, column: str = "close", window: int = 20) -> pd.Series:
    return df[column].ewm(span=window, min_periods=window).mean()

# 计算ATR指标
def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

# 计算OBV指标
def obv(df: pd.DataFrame) -> pd.Series:
    obv = np.sign(df['close'].diff()) * df['volume']
    return obv.cumsum()

# 3. 根据技术指标生成买卖信号
def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

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

# 4. 回测策略：模拟资金变化，评估策略表现
def backtest(df: pd.DataFrame, initial_cash: float = 10000, hold_days: int = 7) -> dict:
    df = df.copy()
    df["cash"] = initial_cash
    df["position"] = 0
    df["capital"] = initial_cash
    df["returns"] = 0.0
    df["buy_price"] = np.nan
    df["sell_price"] = np.nan

    for i in range(1, len(df)):
        # 买入信号
        if df["buy_signal"].iloc[i] and df["position"].iloc[i-1] == 0:
            df.loc[df.index[i], "position"] = df["cash"].iloc[i-1] // df["close"].iloc[i]
            df.loc[df.index[i], "buy_price"] = df["close"].iloc[i]
            df.loc[df.index[i], "cash"] = df["cash"].iloc[i-1] - df["position"].iloc[i] * df["buy_price"].iloc[i]

        # 卖出信号
        elif df["sell_signal"].iloc[i] and df["position"].iloc[i-1] > 0:
            df.loc[df.index[i], "cash"] = df["position"].iloc[i-1] * df["close"].iloc[i]
            df.loc[df.index[i], "sell_price"] = df["close"].iloc[i]
            df.loc[df.index[i], "position"] = 0

        # 计算资本（现金 + 持仓市值）
        df.loc[df.index[i], "capital"] = df["cash"].iloc[i] + df["position"].iloc[i] * df["close"].iloc[i]

    # 计算表现指标
    df["returns"] = df["capital"].pct_change()
    total_returns = df["returns"].sum()
    final_capital = df["capital"].iloc[-1]

    return {
        "total_returns": total_returns,
        "final_capital": final_capital,
        "capital_curve": df["capital"],
    }

# 5. 绘制资本曲线（回测结果）
def plot_capital_curve(capital_curve: pd.Series):
    plt.figure(figsize=(10, 6))
    plt.plot(capital_curve, label="资本曲线")
    plt.title("回测资本曲线")
    plt.xlabel("日期")
    plt.ylabel("资本 ($)")
    plt.legend()
    plt.grid(True)
    plt.show()

# 6. 主函数
def main(symbol: str):
    df = fetch_ohlcv(symbol)
    if df is not None:
        df = generate_signals(df)
        result = backtest(df)
        print(f"总收益率: {result['total_returns'] * 100:.2f}%")
        print(f"最终资本: ${result['final_capital']:.2f}")
        plot_capital_curve(result["capital_curve"])

if __name__ == "__main__":
    symbol = "AAPL"  # 示例：苹果股票
    main(symbol)
