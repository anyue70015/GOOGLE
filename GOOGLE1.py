import pandas as pd
import numpy as np
import requests
from typing import List, Dict

# 配置
HEADERS = {"User-Agent": "Mozilla/5.0"}

# ========================================================
# 获取OHLCV数据（美股数据）
# ========================================================
def fetch_ohlcv(symbol: str, period: str = "1y") -> pd.DataFrame:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={period}&interval=1d"
    response = requests.get(url, headers=HEADERS)
    data = response.json()
    
    if "chart" not in data or data["chart"]["result"] is None:
        return None
    
    # 提取数据
    df = pd.DataFrame(data["chart"]["result"][0]["indicators"]["quote"][0])
    df["timestamp"] = pd.to_datetime(data["chart"]["result"][0]["timestamp"], unit="s")
    df.set_index("timestamp", inplace=True)
    df = df.dropna()  # 去除缺失数据
    return df


# ========================================================
# 计算技术指标
# ========================================================
def ema(df: pd.DataFrame, column: str, span: int) -> pd.Series:
    return df[column].ewm(span=span, adjust=False).mean()


def rsi(df: pd.DataFrame, column: str, period: int = 14) -> pd.Series:
    delta = df[column].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=period, min_periods=1).mean()
    avg_loss = loss.rolling(window=period, min_periods=1).mean()
    rs = avg_gain / (avg_loss + 1e-9)
    return 100 - (100 / (1 + rs))


def macd(df: pd.DataFrame, column: str) -> pd.DataFrame:
    ema12 = ema(df, column, 12)
    ema26 = ema(df, column, 26)
    macd_line = ema12 - ema26
    signal_line = ema(macd_line, column, 9)
    return macd_line, signal_line


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df['high'], df['low'], df['close']
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(window=period, min_periods=1).mean()


def obv(df: pd.DataFrame) -> pd.Series:
    direction = np.sign(df["close"].diff()).fillna(0)
    return (direction * df["volume"]).cumsum()


# ========================================================
# 策略信号生成
# ========================================================
def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    
    # 计算技术指标
    df["macd"], df["macd_signal"] = macd(df, "close")
    df["rsi"] = rsi(df, "close")
    df["ema20"] = ema(df, "close", 20)
    df["ema50"] = ema(df, "close", 50)
    df["atr14"] = atr(df)
    df["obv"] = obv(df)

    # 信号生成：满足以下条件为买入信号
    df["buy_signal"] = (df["macd"] > df["macd_signal"]) & (df["rsi"] < 30) & (df["close"] > df["ema20"]) & (df["obv"] > df["obv"].rolling(20).mean())
    
    # 卖出信号
    df["sell_signal"] = (df["macd"] < df["macd_signal"]) & (df["rsi"] > 70) & (df["close"] < df["ema20"]) & (df["obv"] < df["obv"].rolling(20).mean())

    return df


# ========================================================
# 回测函数
# ========================================================
def backtest(df: pd.DataFrame, initial_cash: float = 10000, hold_days: int = 7) -> Dict:
    df = df.copy()
    df["cash"] = initial_cash
    df["position"] = 0
    df["capital"] = initial_cash
    df["returns"] = 0.0

    # 用于记录买入卖出
    for i in range(len(df) - hold_days):
        if df["buy_signal"].iloc[i]:  # 如果是买入信号
            df["position"].iloc[i + hold_days] = df["capital"].iloc[i] / df["close"].iloc[i]
            df["capital"].iloc[i + hold_days] = 0  # 将资金冻结
            
        if df["sell_signal"].iloc[i]:  # 如果是卖出信号
            df["capital"].iloc[i + hold_days] = df["position"].iloc[i] * df["close"].iloc[i]
            df["position"].iloc[i + hold_days] = 0  # 清空持仓
            
        df["returns"].iloc[i + hold_days] = (df["capital"].iloc[i + hold_days] - df["capital"].iloc[i]) / df["capital"].iloc[i]

    # 计算累计收益与回报指标
    df["pf"] = df["returns"].cumsum()
    total_return = df["returns"].sum()
    winrate = len(df[df["returns"] > 0]) / len(df[df["returns"].notna()])
    
    return {
        "total_return": total_return,
        "pf": df["pf"].iloc[-1],
        "winrate": winrate,
        "total_trades": len(df[df["returns"].notna()])
    }


# ========================================================
# 扫描所有股票，获取最终回测结果
# ========================================================
def scan(symbols: List[str]) -> pd.DataFrame:
    results = []
    
    for symbol in symbols:
        df = fetch_ohlcv(symbol)
        if df is None:
            continue
        df = generate_signals(df)
        result = backtest(df)
        results.append({
            "symbol": symbol,
            "total_return": result["total_return"],
            "pf": result["pf"],
            "winrate": result["winrate"],
            "total_trades": result["total_trades"]
        })
    
    return pd.DataFrame(results)


# ========================================================
# 主函数（测试用例）
# ========================================================
if __name__ == "__main__":
    symbols = ["AAPL", "MSFT", "GOOG", "TSLA", "AMZN"]  # 你可以修改这里的股票
    result = scan(symbols)
    print(result.sort_values(by="pf", ascending=False))
