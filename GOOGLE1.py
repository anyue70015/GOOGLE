import streamlit as st
import requests
import numpy as np
import time

st.set_page_config(page_title="币圈回测信号面板 (Yahoo Finance)", layout="wide")

st.markdown(
    '''
    <style>
    body { background:#05060a; }
    .main { background:#05060a; padding-top:10px !important; }
    h1 { font-size:26px !important; font-weight:700 !important; margin-bottom:6px !important; }

    .card {
        background:#14151d;
        border-radius:14px;
        padding:14px 16px 12px;
        border:1px solid #262736;
        box-shadow:0 18px 36px rgba(0,0,0,0.45);
        color:#f5f5f7;
        font-size:13px;
        transition:0.15s;
        margin-bottom:18px;
    }
    .card:hover {
        transform:translateY(-3px);
        box-shadow:0 26px 48px rgba(0,0,0,0.6);
    }

    .card-section {
        display:flex;
        justify-content:space-between;
        align-items:flex-end;
        gap:10px;
    }
    .section-divider {
        border-bottom:1px solid #1f2030;
        margin:10px 0;
    }

    .symbol-line {
        display:flex;
        gap:10px;
        align-items:center;
        font-size:19px;
        margin-bottom:2px;
    }
    .symbol-name { font-weight:800; }
    .symbol-ticker {
        font-size:12px;
        color:#9ca3af;
        padding:2px 6px;
        border:1px solid #262736;
        border-radius:10px;
        background:#0d0e13;
    }
    .symbol-price {
        font-size:19px;
    }
    .change-up { color:#4ade80; font-size:14px; }
    .change-down { color:#fb7185; font-size:14px; }

    .indicator-grid {
        display:flex;
        flex-direction:column;
        gap:8px;
        margin-top:4px;
    }
    .indicator-item {
        display:flex;
        align-items:center;
        justify-content:space-between;
        width:100%;
        background:#191b27;
        border:1px solid #202233;
        border-radius:10px;
        padding:8px 10px;
        font-size:12px;
        color:#d4d4d8;
    }
    .dot { width:6px;height:6px;border-radius:2px;display:inline-block;margin-left:6px; }
    .dot-bull { background:#4ade80; box-shadow:0 0 0 1px rgba(74,222,128,0.25); }
    .dot-neutral { background:#facc15; box-shadow:0 0 0 1px rgba(250,204,21,0.25); }
    .dot-bear { background:#fb7185; box-shadow:0 0 0 1px rgba(251,113,133,0.25); }

    .label { color:#9ca3af; }
    .prob-good { color:#4ade80; font-weight:600; }
    .prob-mid { color:#facc15; font-weight:600; }
    .prob-bad { color:#fb7185; font-weight:600; }

    .score{
        font-size:12px;
        color:#9ca3af;
        margin-top:8px;
        display:flex;
        align-items:center;
        gap:8px;
    }
    .score-label{
        font-size:13px;
        font-weight:700;
        color:#e5e7eb;
        min-width:70px;
    }
    .dot-score{
        width:9px;
        height:9px;
        border-radius:50%;
        display:inline-block;
        margin-right:2px;
    }
    .dot-score-buy{ background:#4ade80; }
    .dot-score-hold{ background:#facc15; }
    .dot-score-sell{ background:#fb7185; }
    .dot-score-off{ background:#4b5563; }
    .advice-text{
        font-size:13px;
        font-weight:600;
    }
    .advice-buy{ color:#4ade80; }
    .advice-hold{ color:#facc15; }
    .advice-sell{ color:#fb7185; }
    .profit-row { font-size:12px; }
    </style>
    ''',
    unsafe_allow_html=True,
)

st.title("币圈回测信号面板 (Yahoo Finance API)")

# ==================== 配置 ====================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
}

# 币种映射 (Yahoo 标准符号)
YAHOO_CRYPTO = {
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "SOL": "SOL-USD",
    "BNB": "BNB-USD",
    "XRP": "XRP-USD",
    "DOGE": "DOGE-USD",
    "ADA": "ADA-USD",
    "AVAX": "AVAX-USD",
    "TRX": "TRX-USD",
    "LINK": "LINK-USD",
    "DOT": "DOT-USD",
    "TON": "TON11419-USD",
    "SUI": "SUI-USD",
    "PEPE": "PEPE24478-USD",
    "WIF": "WIF-USD",
    "SHIB": "SHIB-USD",
}

CHINESE_NAMES = {
    "BTC-USD": "比特币",
    "ETH-USD": "以太坊",
    "SOL-USD": "Solana",
    "BNB-USD": "币安币",
    "XRP-USD": "瑞波币",
    "DOGE-USD": "狗狗币",
    "ADA-USD": "艾达币",
    "AVAX-USD": "雪崩协议",
    "TRX-USD": "波场",
    "LINK-USD": "Chainlink",
    "DOT-USD": "波卡",
}

def format_yahoo_crypto(symbol: str) -> str:
    sym = symbol.strip().upper()
    return YAHOO_CRYPTO.get(sym, f"{sym}-USD")

@st.cache_data(ttl=60, show_spinner=False)
def get_current_price(yahoo_symbol: str):
    url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={yahoo_symbol}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        data = resp.json()["quoteResponse"]["result"][0]
        price = data.get("regularMarketPrice") or data.get("regularMarketPreviousClose")
        change = data.get("regularMarketChangePercent", 0.0)
        return price, change
    except Exception:
        return None, None

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_yahoo_ohlcv(yahoo_symbol: str, range_str: str = "1y"):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}?range={range_str}&interval=1d"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        result = resp.json()["chart"]["result"][0]
        quote = result["indicators"]["quote"][0]
        close = np.array(quote["close"], dtype=float)
        high = np.array(quote["high"], dtype=float)
        low = np.array(quote["low"], dtype=float)
        volume = np.array(quote["volume"], dtype=float)
        mask = ~np.isnan(close)
        close = close[mask]
        high = high[mask]
        low = low[mask]
        volume = volume[mask]
        if len(close) < 50:
            raise ValueError("历史数据不足")
        return close, high, low, volume
    except Exception as e:
        raise ValueError(f"Yahoo 数据获取失败: {str(e)}")

# ==================== 指标函数 ====================
def ema_np(x: np.ndarray, span: int):
    alpha = 2 / (span + 1)
    ema = np.empty_like(x)
    ema[0] = x[0]
    for i in range(1, len(x)):
        ema[i] = alpha * x[i] + (1 - alpha) * ema[i-1]
    return ema

def macd_hist_np(close):
    ema12 = ema_np(close, 12)
    ema26 = ema_np(close, 26)
    macd_line = ema12 - ema26
    signal = ema_np(macd_line, 9)
    return macd_line - signal

def rsi_np(close, period=14):
    delta = np.diff(close, prepend=close[0])
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    alpha = 1 / period
    gain_ema = np.empty_like(gain)
    loss_ema = np.empty_like(loss)
    gain_ema[0] = gain[0]
    loss_ema[0] = loss[0]
    for i in range(1, len(gain)):
        gain_ema[i] = alpha * gain[i] + (1 - alpha) * gain_ema[i-1]
        loss_ema[i] = alpha * loss[i] + (1 - alpha) * loss_ema[i-1]
    rs = gain_ema / (loss_ema + 1e-9)
    return 100 - (100 / (1 + rs))

def atr_np(high, low, close, period=14):
    prev_close = np.roll(close, 1)
    prev_close[0] = close[0]
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))
    atr = np.empty_like(tr)
    atr[0] = tr[0]
    alpha = 1 / period
    for i in range(1, len(tr)):
        atr[i] = alpha * tr[i] + (1 - alpha) * atr[i-1]
    return atr

def rolling_mean_np(x, window):
    if len(x) < window:
        return np.full_like(x, np.mean(x))
    cumsum = np.cumsum(np.insert(x, 0, 0))
    ma = (cumsum[window:] - cumsum[:-window]) / window
    return np.concatenate([np.full(window-1, ma[0]), ma])

def obv_np(close, volume):
    direction = np.sign(np.diff(close, prepend=close[0]))
    return np.cumsum(direction * volume)

def backtest_with_stats(close, score, steps):
    if len(close) <= steps + 1:
        return 0.5, 0.0, 0.0, 0.0
    idx = np.where(score[:-steps] >= 3)[0]
    if len(idx) == 0:
        return 0.5, 0.0, 0.0, 0.0
    rets = close[idx + steps] / close[idx] - 1
    win_rate = np.mean(rets > 0)
    pf = rets[rets > 0].sum() / abs(rets[rets <= 0].sum()) if np.any(rets <= 0) else 999
    avg_win = np.mean(rets[rets > 0]) * 100 if np.any(rets > 0) else 0.0
    avg_loss = np.mean(rets[rets <= 0]) * 100 if np.any(rets <= 0) else 0.0
    return win_rate, pf, avg_win, avg_loss

def prob_class(p):
    if p >= 0.65: return "prob-good"
    if p >= 0.45: return "prob-mid"
    return "prob-bad"

def decide_advice(prob, pf):
    if prob >= 0.60 and pf >= 1.2:
        kind = "buy"
        intensity = 3 + (1 if prob > 0.65 else 0) + (1 if pf > 1.6 else 0)
    elif prob <= 0.40 and pf <= 0.8:
        kind = "sell"
        intensity = 3 + (1 if prob < 0.35 else 0) + (1 if pf < 0.6 else 0)
    else:
        kind = "hold"
        intensity = 3
    intensity = max(1, min(5, intensity))
    label = {"buy": "建议买入", "sell": "建议卖出", "hold": "观望"}[kind]
    return label, intensity, kind

# ==================== 主计算函数 ====================
@st.cache_data(show_spinner=False)
def compute_crypto_metrics(symbol: str):
    yahoo_symbol = format_yahoo_crypto(symbol)
    display_name = CHINESE_NAMES.get(yahoo_symbol, symbol.upper())

    price, change = get_current_price(yahoo_symbol)
    close, high, low, volume = fetch_yahoo_ohlcv(yahoo_symbol)

    macd_hist = macd_hist_np(close)
    rsi = rsi_np(close)
    atr = atr_np(high, low, close)
    obv = obv_np(close, volume)
    vol_ma20 = rolling_mean_np(volume, 20)
    atr_ma20 = rolling_mean_np(atr, 20)
    obv_ma20 = rolling_mean_np(obv, 20)

    sig_macd = (macd_hist > 0).astype(int)
    sig_vol = (volume > vol_ma20 * 1.1).astype(int)
    sig_rsi = (rsi >= 60).astype(int)
    sig_atr = (atr > atr_ma20 * 1.1).astype(int)
    sig_obv = (obv > obv_ma20 * 1.05).astype(int)
    score_arr = sig_macd + sig_vol + sig_rsi + sig_atr + sig_obv

    prob7, pf7, avg_win7, avg_loss7 = backtest_with_stats(close, score_arr, 7)
    prob30, pf30, avg_win30, avg_loss30 = backtest_with_stats(close, score_arr, 30)

    final_price = price if price is not None else close[-1]
    final_change = change if change is not None else 0.0

    indicators = [
        {"name": "MACD 多头/空头", "status": "bull" if macd_hist[-1] > 0 else "bear", "desc": ""},
        {"name": "成交量相对20日均量", "status": "bull" if volume[-1] > vol_ma20[-1]*1.1 else "bear" if volume[-1] < vol_ma20[-1]*0.9 else "neutral", "desc": f"1.10 / {volume[-1]/vol_ma20[-1]:.2f}"},
        {"name": "RSI 区间", "status": "bull" if rsi[-1] >= 60 else "bear" if rsi[-1] <= 40 else "neutral", "desc": f"60.0 / {rsi[-1]:.1f}"},
        {"name": "ATR 波动率", "status": "bull" if atr[-1] > atr_ma20[-1]*1.1 else "bear" if atr[-1] < atr_ma20[-1]*0.9 else "neutral", "desc": f"1.10 / {atr[-1]/atr_ma20[-1]:.2f}"},
        {"name": "OBV 资金趋势", "status": "bull" if obv[-1] > obv_ma20[-1]*1.05 else "bear" if obv[-1] < obv_ma20[-1]*0.95 else "neutral", "desc": f"1.05 / {obv[-1]/obv_ma20[-1]:.2f}"},
    ]

    return {
        "symbol": symbol.upper(),
        "display_name": display_name,
        "price": final_price,
        "change": final_change,
        "prob7": prob7,
        "prob30": prob30,
        "pf7": pf7,
        "pf30": pf30,
        "avg_win7": avg_win7,
        "avg_loss7": avg_loss7,
        "avg_win30": avg_win30,
        "avg_loss30": avg_loss30
