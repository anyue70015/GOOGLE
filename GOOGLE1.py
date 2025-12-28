import streamlit as st
import requests
import numpy as np
import pandas as pd
import time

st.set_page_config(page_title="短线扫描 · 生产级", layout="wide")
st.title("🚀 短线扫描（入场等价 · PF增强）")

HEADERS = {"User-Agent": "Mozilla/5.0"}

# =====================================================
# 股票池（示例：你可直接替换为你原来的完整池）
# =====================================================
STOCKS = ["SNDK", "NVDA", "AAPL", "MSFT", "AMD", "TSLA", "META", "AMZN"]

# =====================================================
# 数据获取（OHLCV）
# =====================================================
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_stock_data(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1y&interval=1d"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        j = r.json()
        if j["chart"]["result"] is None:
            return None

        q = j["chart"]["result"][0]["indicators"]["quote"][0]

        close = np.array(q["close"], float)
        high = np.array(q["high"], float)
        low = np.array(q["low"], float)
        volume = np.array(q["volume"], float)

        mask = ~np.isnan(close)
        close, high, low, volume = close[mask], high[mask], low[mask], volume[mask]

        if len(close) < 120:
            return None

        return {"close": close, "high": high, "low": low, "volume": volume}
    except:
        return None

# =====================================================
# EMA（与你第一段等价）
# =====================================================
def ema(x, span):
    a = 2 / (span + 1)
    y = np.zeros_like(x)
    y[0] = x[0]
    for i in range(1, len(x)):
        y[i] = a * x[i] + (1 - a) * y[i - 1]
    return y

# =====================================================
# 核心分析（入场不变）
# =====================================================
def analyze_stock(symbol):
    data = fetch_stock_data(symbol)
    if data is None:
        return None

    close, high, low, volume = (
        data["close"], data["high"], data["low"], data["volume"]
    )

    price = close[-1]
    change = (close[-1] / close[-2] - 1) * 100

    # ========== 第一段：入场逻辑（严禁改） ==========
    ema12 = ema(close, 12)
    ema26 = ema(close, 26)
    macd = ema12 - ema26
    signal = ema(macd, 9)
    macd_hist = macd - signal

    delta = np.diff(close, prepend=close[0])
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)

    avg_gain = ema(gain, 14)
    avg_loss = ema(loss, 14)
    rs = avg_gain / (avg_loss + 1e-9)
    rsi = 100 - 100 / (1 + rs)

    ma20 = pd.Series(close).rolling(20).mean().values
    ma50 = pd.Series(close).rolling(50).mean().values

    score = (
        (macd_hist > 0).astype(int) +
        (close > ma20 * 1.02).astype(int) +
        (rsi >= 60).astype(int) +
        (close > ma50).astype(int)
    )

    entry_idx = np.where(score[:-7] >= 3)[0]
    if len(entry_idx) < 10:
        return None

    # ========== 原始 PF7 ==========
    rets = close[entry_idx + 7] / close[entry_idx] - 1
    win = rets[rets > 0]
    loss = rets[rets <= 0]

    pf7_raw = win.sum() / abs(loss.sum()) if loss.sum() != 0 else np.inf
    prob7_raw = len(win) / len(rets)

    # ========== 增强因子（不改入场） ==========
    vol_ma20 = pd.Series(volume).rolling(20).mean().values
    cond_vol = volume > vol_ma20 * 1.1

    tr = np.maximum(
        high - low,
        np.maximum(abs(high - np.roll(close, 1)),
                   abs(low - np.roll(close, 1)))
    )
    tr[0] = high[0] - low[0]
    atr = pd.Series(tr).ewm(alpha=1/14, adjust=False).mean().values
    atr_ma20 = pd.Series(atr).rolling(20).mean().values
    cond_atr = atr > atr_ma20

    obv = np.zeros(len(close))
    for i in range(1, len(close)):
        obv[i] = obv[i-1] + (volume[i] if close[i] > close[i-1]
                             else -volume[i] if close[i] < close[i-1] else 0)
    obv_ma20 = pd.Series(obv).rolling(20).mean().values
    cond_obv = obv > obv_ma20

    mask = cond_vol[entry_idx] & cond_atr[entry_idx] & cond_obv[entry_idx]
    rets_e = rets[mask]

    if len(rets_e) >= 5:
        win_e = rets_e[rets_e > 0]
        loss_e = rets_e[rets_e <= 0]
        pf7_enh = win_e.sum() / abs(loss_e.sum()) if loss_e.sum() != 0 else np.inf
        prob7_enh = len(win_e) / len(rets_e)
    else:
        pf7_enh, prob7_enh = None, None

    return {
        "symbol": symbol,
        "price": price,
        "change": change,
        "entries": len(entry_idx),
        "pf7_raw": pf7_raw,
        "prob7_raw": prob7_raw,
        "pf7_enh": pf7_enh,
        "prob7_enh": prob7_enh
    }

# =====================================================
# 扫描
# =====================================================
if st.button("🚀 开始扫描"):
    rows = []
    for s in STOCKS:
        st.write(f"扫描 {s}")
        r = analyze_stock(s)
        if r:
            rows.append(r)
        time.sleep(1)

    if rows:
        df = pd.DataFrame(rows)
        st.dataframe(df.sort_values("pf7_raw", ascending=False))
