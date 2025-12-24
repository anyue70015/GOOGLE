import streamlit as st
import requests
import numpy as np
import time
import pandas as pd
from io import StringIO

# ==================== 页面设置 ====================
st.set_page_config(page_title="标普500 + 纳斯达克100 大盘扫描工具", layout="wide")
st.title("标普500 + 纳斯达克100 扫描工具（7日盈利概率 ≥75%）")

# ==================== 原代码所有常量和函数（完整复制） ====================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
}

BACKTEST_OPTIONS = ["3个月", "6个月", "1年", "2年", "3年", "5年", "10年"]
BACKTEST_CONFIG = {
    "3个月": {"range": "3mo", "interval": "1d", "steps_per_day": 1},
    "6个月": {"range": "6mo", "interval": "1d", "steps_per_day": 1},
    "1年":  {"range": "1y",  "interval": "1d", "steps_per_day": 1},
    "2年":  {"range": "2y",  "interval": "1d", "steps_per_day": 1},
    "3年":  {"range": "3y",  "interval": "1d", "steps_per_day": 1},
    "5年":  {"range": "5y",  "interval": "1d", "steps_per_day": 1},
    "10年": {"range": "10y", "interval": "1d", "steps_per_day": 1},
}

def format_symbol_for_yahoo(symbol: str) -> str:
    sym = symbol.strip().upper()
    if sym.isdigit() and len(sym) == 6:
        if sym.startswith(("600", "601", "603", "605", "688")):
            return f"{sym}.SS"
        if sym.startswith(("000", "001", "002", "003", "300", "301")):
            return f"{sym}.SZ"
    return sym

@st.cache_data(ttl=300, show_spinner=False)
def get_current_price(yahoo_symbol: str):
    url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={yahoo_symbol}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        data = resp.json()["quoteResponse"]["result"][0]
        price = data.get("regularMarketPrice") or data.get("regularMarketPreviousClose")
        change = data.get("regularMarketChangePercent", 0) * 100
        return float(price), float(change)
    except Exception:
        return None, None

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_yahoo_ohlcv(yahoo_symbol: str, range_str: str, interval: str):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}?range={range_str}&interval={interval}"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()["chart"]["result"][0]
    quote = data["indicators"]["quote"][0]
    close = np.array(quote["close"], dtype=float)
    high = np.array(quote["high"], dtype=float)
    low = np.array(quote["low"], dtype=float)
    volume = np.array(quote["volume"], dtype=float)
    mask = ~np.isnan(close)
    close, high, low, volume = close[mask], high[mask], low[mask], volume[mask]
    if len(close) < 80:
        raise ValueError("数据不足")
    return close, high, low, volume

def ema_np(x: np.ndarray, span: int) -> np.ndarray:
    alpha = 2 / (span + 1)
    ema = np.empty_like(x)
    ema[0] = x[0]
    for i in range(1, len(x)):
        ema[i] = alpha * x[i] + (1 - alpha) * ema[i-1]
    return ema

def macd_hist_np(close: np.ndarray) -> np.ndarray:
    ema12 = ema_np(close, 12)
    ema26 = ema_np(close, 26)
    macd_line = ema12 - ema26
    signal = ema_np(macd_line, 9)
    return macd_line - signal

def rsi_np(close: np.ndarray, period: int = 14) -> np.ndarray:
    delta = np.diff(close, prepend=close[0])
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    alpha = 1 / period
    gain_ema = np.empty_like(gain)
    loss_ema = np.empty_like(loss)
    gain_ema[0] = gain[0]
    loss_ema[0] = loss[0]
    for i in range(1, len(gain)):
        gain
