import streamlit as st
import requests
import numpy as np
import pandas as pd
import time

# ================= 基础配置 =================
st.set_page_config(page_title="短线动量扫描器（增强PF版）", layout="wide")
st.title("短线动量扫描器（Volume + ATR + OBV 增强版）")

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

BACKTEST_CONFIG = {
    "3个月": "3mo",
    "6个月": "6mo",
    "1年": "1y",
    "2年": "2y"
}

ENTRY_SCORE = 5
LOOKAHEAD = 7

# ================= 数据获取 =================
@st.cache_data(ttl=3600)
def fetch_ohlcv(symbol, period):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={period}&interval=1d"
    r = requests.get(url, headers=HEADERS, timeout=15)
    data = r.json()["chart"]["result"][0]
    q = data["indicators"]["quote"][0]

    close = np.array(q["close"], float)
    high = np.array(q["high"], float)
    low = np.array(q["low"], float)
    volume = np.array(q["volume"], float)

    mask = ~np.isnan(close)
    return close[mask], high[mask], low[mask], volume[mask]

# ================= 指标函数 =================
def ema(x, span):
    return pd.Series(x).ewm(span=span, adjust=False).mean().values

def macd_hist(close):
    return ema(close,12) - ema(close,26) - ema(ema(close,12)-ema(close,26),9)

def rsi(close, period=14):
    delta = np.diff(close, prepend=close[0])
    gain = np.maximum(delta,0)
    loss = np.maximum(-delta,0)
    rs = pd.Series(gain).ewm(alpha=1/period, adjust=False).mean() / \
         (pd.Series(loss).ewm(alpha=1/period, adjust=False).mean() + 1e-9)
    return 100 - 100/(1+rs)

def atr(high, low, close, period=14):
    pc = np.roll(close,1)
    pc[0] = close[0]
    tr = np.maximum(high-low, np.maximum(abs(high-pc), abs(low-pc)))
    return pd.Series(tr).ewm(alpha=1/period, adjust=False).mean().values

def obv(close, volume):
    d = np.sign(np.diff(close, prepend=close[0]))
    return np.cumsum(d * volume)

# ================= 核心计算 =================
def compute_metrics(symbol, period):
    close, high, low, volume = fetch_ohlcv(symbol, period)
    if len(close) < 100:
        raise ValueError("数据不足")

    ma20 = pd.Series(close).rolling(20).mean().values
    ma50 = pd.Series(close).rolling(50).mean().values

    sig_macd = (macd_hist(close) > 0).astype(int)
    sig_ma20 = (close > ma20).astype(int)
    sig_ma50 = (close > ma50).astype(int)
    sig_rsi = (rsi(close) >= 60).astype(int)
    sig_up = (close > np.roll(close,5)).astype(int)

    vol_ma20 = pd.Series(volume).rolling(20).mean().values
    sig_vol = (volume > vol_ma20 * 1.1).astype(int)

    atr_v = atr(high, low, close)
    atr_ma20 = pd.Series(atr_v).rolling(20).mean().values
    sig_atr = (atr_v > atr_ma20 * 1.1).astype(int)

    obv_v = obv(close, volume)
    obv_ma20 = pd.Series(obv_v).rolling(20).mean().values
    sig_obv = (obv_v > obv_ma20 * 1.05).astype(int)

    score = (
        sig_macd + sig_ma20 + sig_ma50 +
        sig_rsi + sig_up +
        sig_vol + sig_atr + sig_obv
    )

    idx = np.where(score[:-LOOKAHEAD] >= ENTRY_SCORE)[0]
    if len(idx) < 10:
        return None

    rets = close[idx + LOOKAHEAD] / close[idx] - 1
    wins = rets[rets > 0]
    loss = rets[rets <= 0]

    prob7 = len(wins) / len(rets)
    pf7 = wins.sum() / abs(loss.sum()) if loss.sum() != 0 else np.inf

    return {
        "symbol": symbol,
        "price": close[-1],
        "change": (close[-1]/close[-2]-1)*100,
        "score": int(score[-1]),
        "prob7": prob7,
        "pf7": pf7
    }

# ================= 股票池（示例） =================
tickers = [
    "AAPL","MSFT","NVDA","AMZN","META","TSLA","GOOGL",
    "AMD","AVGO","NFLX","SPY","QQQ","SMH","SOXX"
]

# ================= UI =================
period = st.selectbox("回测周期", BACKTEST_CONFIG.keys(), index=2)
results = []

with st.spinner("扫描中..."):
    for t in tickers:
        try:
            r = compute_metrics(t, BACKTEST_CONFIG[period])
            if r:
                results.append(r)
        except:
            pass
        time.sleep(1)

if results:
    df = pd.DataFrame(results)
    df = df[(df.pf7 >= 3.6) | (df.prob7 >= 0.68)]
    df = df.sort_values("pf7", ascending=False)

    df["prob7"] = (df["prob7"]*100).round(1).astype(str)+"%"
    df["change"] = df["change"].map(lambda x:f"{x:+.2f}%")

    st.subheader(f"符合条件股票：{len(df)} 只")
    st.dataframe(df, use_container_width=True)
else:
    st.warning("暂无符合条件股票")
