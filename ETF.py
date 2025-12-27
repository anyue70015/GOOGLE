import streamlit as st
import requests
import numpy as np
import time
import pandas as pd
from io import StringIO

st.set_page_config(page_title="标普500 + 纳斯达克100 + 热门ETF 极品短线扫描工具", layout="wide")
st.title("标普500 + 纳斯达克100 + 热门ETF 短线扫描工具（PF7≥3.6 或 7日≥68%）")

# ==================== 核心常量 ====================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
}

BACKTEST_CONFIG = {
    "3个月": {"range": "3mo", "interval": "1d"},
    "6个月": {"range": "6mo", "interval": "1d"},
    "1年":  {"range": "1y",  "interval": "1d"},
    "2年":  {"range": "2y",  "interval": "1d"},
    "3年":  {"range": "3y",  "interval": "1d"},
    "5年":  {"range": "5y",  "interval": "1d"},
    "10年": {"range": "10y", "interval": "1d"},
}

# ==================== 数据拉取（保持原版requests方式） ====================
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_yahoo_ohlcv(yahoo_symbol: str, range_str: str, interval: str = "1d"):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}?range={range_str}&interval={interval}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json()["chart"]["result"][0]
        quote = data["indicators"]["quote"][0]
        close = np.array(quote["close"], dtype=float)
        high = np.array(quote["high"], dtype=float)
        low = np.array(quote["low"], dtype=float)
        volume = np.array(quote["volume"], dtype=float)
        mask = ~np.isnan(close)
        close, high, low, volume = close[mask], high[mask], low[mask], volume[mask]
        if len(close) < 100:
            raise ValueError("数据不足")
        return close, high, low, volume
    except Exception as e:
        raise ValueError(f"请求失败: {str(e)}")

# ==================== 指标函数（完全保留原版） ====================
# （ema_np, macd_hist_np, rsi_np, atr_np, rolling_mean_np, obv_np, backtest_with_stats 全部复制你的原代码，这里省略以节省空间，但请完整保留）

# ==================== 核心计算（完全保留） ====================
@st.cache_data(show_spinner=False)
def compute_stock_metrics(symbol: str, cfg_key: str = "1年"):
    yahoo_symbol = symbol.upper()
    close, high, low, volume = fetch_yahoo_ohlcv(yahoo_symbol, BACKTEST_CONFIG[cfg_key]["range"], BACKTEST_CONFIG[cfg_key]["interval"])

    macd_hist = macd_hist_np(close)
    rsi = rsi_np(close)
    atr = atr_np(high, low, close)
    obv = obv_np(close, volume)
    vol_ma20 = rolling_mean_np(volume, 20)
    atr_ma20 = rolling_mean_np(atr, 20)
    obv_ma20 = rolling_mean_np(obv, 20)

    sig_macd = (macd_hist > 0).astype(int)[-1]
    sig_vol = (volume[-1] > vol_ma20[-1] * 1.1).astype(int)
    sig_rsi = (rsi[-1] >= 60).astype(int)
    sig_atr = (atr[-1] > atr_ma20[-1] * 1.1).astype(int)
    sig_obv = (obv[-1] > obv_ma20[-1] * 1.05).astype(int)
    score = sig_macd + sig_vol + sig_rsi + sig_atr + sig_obv

    sig_macd_hist = (macd_hist > 0).astype(int)
    sig_vol_hist = (volume > vol_ma20 * 1.1).astype(int)
    sig_rsi_hist = (rsi >= 60).astype(int)
    sig_atr_hist = (atr > atr_ma20 * 1.1).astype(int)
    sig_obv_hist = (obv > obv_ma20 * 1.05).astype(int)
    score_arr = sig_macd_hist + sig_vol_hist + sig_rsi_hist + sig_atr_hist + sig_obv_hist

    prob7, pf7 = backtest_with_stats(close[:-1], score_arr[:-1], 7)

    price = close[-1]
    change = (close[-1] / close[-2] - 1) * 100 if len(close) >= 2 else 0

    return {
        "symbol": symbol.upper(),
        "price": price,
        "change": change,
        "score": score,
        "prob7": prob7,
        "pf7": pf7,
    }

# ==================== 加载成分股 + 新增热门ETF ====================
@st.cache_data(ttl=86400)
def load_sp500_tickers():
    url = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
    try:
        resp = requests.get(url, headers=HEADERS)
        resp.raise_for_status()
        df = pd.read_csv(StringIO(resp.text))
        return df['Symbol'].tolist()
    except:
        return []  # 防止加载失败卡住

# Nasdaq 100 (2025最新)
ndx100 = [ ... ]  # 保持你原列表

# 新增热门ETF（2025强势）
extra_etfs = [
    "SPY","QQQ","VOO","IVV","VTI","VUG","SCHG","IWM","DIA",
    "SLV","GLD","GDX","GDXJ","SIL","SLVP",
    "SMH","SOXX","SOXL","TQQQ","BITO","MSTR","ARKK","XLK","XLV"
]

sp500 = load_sp500_tickers()
all_tickers = list(set(sp500 + ndx100 + extra_etfs))
all_tickers.sort()

st.write(f"总计 {len(all_tickers)} 只（标普500 + 纳斯达克100 + 热门ETF） | 2025年12月最新")

# ==================== 界面与自动扫描逻辑（完全保留你的原版） ====================
# （mode, sort_by, session_state, 结果显示, 导出, 自动扫描循环 全部复制你原来的代码）

# 自动扫描部分只改一处：
for sym in all_tickers:
    if sym in st.session_state.scanned_symbols:
        continue
    try:
        metrics = compute_stock_metrics(sym, mode)  # 正确传两个参数！
        ...
    except Exception as e:
        ...
    time.sleep(8)  # 保持原延时
