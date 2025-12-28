"""
quant_us.py
一个干净、可审计的美股量化扫描工具
Author: ChatGPT
"""

import requests
import numpy as np
import pandas as pd
from typing import List, Dict

HEADERS = {"User-Agent": "Mozilla/5.0"}

# =====================================================
# 数据获取（Yahoo Finance, OHLCV）
# =====================================================
def fetch_ohlcv(symbol: str, years: int = 1) -> pd.DataFrame:
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{symbol}?range={years}y&interval=1d"
    )
    r = requests.get(url, headers=HEADERS, timeout=15)
    j = r.json()

    if j["chart"]["result"] is None:
        return None

    q = j["chart"]["result"][0]["indicators"]["quote"][0]
    df = pd.DataFrame(q)
    df = df.dropna()
    if len(df) < 120:
        return None
    return df.reset_index(drop=True)


# =====================================================
# 指标函数（全部“当日可见”）
# =====================================================
def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = ema(gain, period)
    avg_loss = ema(loss, period)
    rs = avg_gain / (avg_loss + 1e-9)
    return 100 - (100 / (1 + rs))


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    tr = pd.concat(
        [
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return ema(tr, period)


def obv(df: pd.DataFrame) -> pd.Series:
    direction = np.sign(df["close"].diff()).fillna(0)
    return (direction * df["volume"]).cumsum()


# =====================================================
# 核心策略（定义清楚）
# =====================================================
def compute_signals(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # MACD
    ema12 = ema(df["close"], 12)
    ema26 = ema(df["close"], 26)
    macd = ema12 - ema26
    signal = ema(macd, 9)
    df["macd_hist"] = macd - signal

    # RSI
    df["rsi"] = rsi(df["close"], 14)

    # MA
    df["ma20"] = df["close"].rolling(20).mean()
    df["ma50"] = df["close"].rolling(50).mean()

    # ===== 入场评分（当日收盘已知）=====
    df["score"] = (
        (df["macd_hist"] > 0).astype(int)
        + (df["close"] > df["ma20"] * 1.02).astype(int)
        + (df["rsi"] >= 60).astype(int)
        + (df["close"] > df["ma50"]).astype(int)
    )

    return df


# =====================================================
# 回测（严格时间顺序）
# =====================================================
def backtest_pf(
    df: pd.DataFrame,
    hold_days: int = 7,
    score_threshold: int = 3,
) -> Dict:
    df = df.copy()

    # 丢掉 warm-up 区
    df = df.iloc[60:].reset_index(drop=True)

    entries = []
    returns = []

    for i in range(len(df) - hold_days):
        if df.loc[i, "score"] >= score_threshold:
            entry_price = df.loc[i, "close"]
            exit_price = df.loc[i + hold_days, "close"]
            ret = exit_price / entry_price - 1
            entries.append(i)
            returns.append(ret)

    if len(returns) < 10:
        return None

    rets = np.array(returns)
    wins = rets[rets > 0]
    loss = rets[rets <= 0]

    pf = wins.sum() / abs(loss.sum()) if loss.sum() != 0 else np.inf
    winrate = len(wins) / len(rets)

    return {
        "trades": len(rets),
        "pf": round(pf, 3),
        "winrate": round(winrate, 3),
        "avg_ret": round(rets.mean(), 4),
    }


# =====================================================
# 增强分析（不改变原始样本）
# =====================================================
def enhancement_analysis(df: pd.DataFrame, hold_days: int = 7) -> Dict:
    df = df.copy()

    df["atr"] = atr(df)
    df["atr_ma20"] = df["atr"].rolling(20).mean()
    df["obv"] = obv(df)
    df["obv_ma20"] = df["obv"].rolling(20).mean()
    df["vol_ma20"] = df["volume"].rolling(20).mean()

    df = df.iloc[60:].reset_index(drop=True)

    enhanced_rets = []

    for i in range(len(df) - hold_days):
        if (
            df.loc[i, "score"] >= 3
            and df.loc[i, "volume"] > df.loc[i, "vol_ma20"]
            and df.loc[i, "atr"] > df.loc[i, "atr_ma20"]
            and df.loc[i, "obv"] > df.loc[i, "obv_ma20"]
        ):
            ret = df.loc[i + hold_days, "close"] / df.loc[i, "close"] - 1
            enhanced_rets.append(ret)

    if len(enhanced_rets) < 5:
        return None

    rets = np.array(enhanced_rets)
    wins = rets[rets > 0]
    loss = rets[rets <= 0]

    pf = wins.sum() / abs(loss.sum()) if loss.sum() != 0 else np.inf
    winrate = len(wins) / len(rets)

    return {
        "trades": len(rets),
        "pf": round(pf, 3),
        "winrate": round(winrate, 3),
    }


# =====================================================
# 扫描入口
# =====================================================
def scan(symbols: List[str]):
    results = []
    for s in symbols:
        df = fetch_ohlcv(s)
        if df is None:
            continue

        df = compute_signals(df)
        base = backtest_pf(df)
        enh = enhancement_analysis(df)

        if base:
            results.append(
                {
                    "symbol": s,
                    "pf": base["pf"],
                    "winrate": base["winrate"],
                    "trades": base["trades"],
                    "pf_enh": enh["pf"] if enh else None,
                    "winrate_enh": enh["winrate"] if enh else None,
                }
            )

    return pd.DataFrame(results)


# =====================================================
# CLI 运行
# =====================================================
if __name__ == "__main__":
    symbols = ["AAPL", "NVDA", "MSFT", "AMD", "TSLA"]
    df = scan(symbols)
    print(df.sort_values("pf", ascending=False))
