import streamlit as st
import pandas as pd
import numpy as np
import pandas_ta as ta
import ccxt
import yfinance as yf
from datetime import datetime
import pytz
from streamlit_autorefresh import st_autorefresh
import requests

# --- 1. 基础配置 ---
st.set_page_config(page_title="UT Bot 终极全资产看板", layout="wide")
BEIJING_TZ = pytz.timezone('Asia/Shanghai')

def get_now_beijing():
    return datetime.now(BEIJING_TZ)

# --- 2. 侧边栏 ---
st.sidebar.header("🛡️ 系统设置")
sct_key = st.sidebar.text_input("Server酱 Key", type="password")
sensitivity = st.sidebar.slider("敏感度", 0.1, 5.0, 1.0, 0.1) # 1.0 对齐 TV
atr_period = st.sidebar.slider("ATR 周期", 1, 30, 10)

CRYPTO_LIST = ["BTC", "ETH", "SOL", "SUI", "RENDER", "DOGE", "XRP", "UNI", "HYPE", "AAVE", "TAO", "XAG", "XAU"]
selected_cryptos = st.sidebar.multiselect("加密货币", CRYPTO_LIST, default=CRYPTO_LIST)

stock_input = st.sidebar.text_area("美股代码 (逗号分隔)", value="NVDA,AAPL,TSLA,QQQ")
custom_stocks = [s.strip().upper() for s in stock_input.split(",") if s.strip()]

selected_intervals = ["15m", "30m", "1h", "4h", "1d"]
st_autorefresh(interval=60 * 1000, key="refresh")

# --- 3. 核心算法 (兼容所有数据源) ---
def calculate_ut_bot(df):
    if df.empty or len(df) < atr_period + 5: return pd.DataFrame()
    
    # 强制数据列标准化，防止 yfinance 的 MultiIndex 干扰
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    # 确保 Open, High, Low, Close 存在
    cols = {c.lower(): c for c in df.columns}
    df = df.rename(columns={cols['high']: 'High', cols['low']: 'Low', cols['close']: 'Close'})
    
    df['atr'] = ta.atr(df['High'], df['Low'], df['Close'], length=atr_period)
    df = df.dropna(subset=['atr']).copy()
    
    n_loss = sensitivity * df['atr']
    src = df['Close']
    trail_stop = np.zeros(len(df))
    
    for i in range(1, len(df)):
        p_stop = trail_stop[i-1]
        if src.iloc[i] > p_stop and src.iloc[i-1] > p_stop:
            trail_stop[i] = max(p_stop, src.iloc[i] - n_loss.iloc[i])
        elif src.iloc[i] < p_stop and src.iloc[i-1] < p_stop:
            trail_stop[i] = min(p_stop, src.iloc[i] + n_loss.iloc[i])
        else:
            trail_stop[i] = (src.iloc[i] - n_loss.iloc[i]) if src.iloc[i] > p_stop else (src.iloc[i] + n_loss.iloc[i])
    
    df['trail_stop'] = trail_stop
    df['buy'] = (df['Close'] > df['trail_stop']) & (df['Close'].shift(1) <= df['trail_stop'].shift(1))
    df['sell'] = (df['Close'] < df['trail_stop']) & (df['Close'].shift(1) >= df['trail_stop'].shift(1))
    return df

def get_signal_info(df):
    if df.empty or len(df) < 2: return "N/A", 0, ""
    curr_p = df.iloc[-1]['Close']
    
    buys = df[df['buy'] == True]
    sells = df[df['sell'] == True]
    l_b = buys.index[-1] if not buys.empty else None
    l_s = sells.index[-1] if not sells.empty else None
    
    now_bj = get_now_beijing()
    def get_mins(sig_time):
        if sig_time.tzinfo is not None:
            sig_time = sig_time.astimezone(BEIJING_TZ).replace(tzinfo=None)
        else:
            sig_time = sig_time.replace(tzinfo=None)
        return int((now_bj.replace(tzinfo=None) - sig_time).total_seconds() / 60)

    # 判断当前处于什么信号
    if l_b and (not l_s or l_b > l_s):
        dur = get_mins(l_b)
        return (f"🚀 BUY({dur}m)" if dur <= 30 else "多 🟢"), curr_p, ("BUY" if dur <= 1 else "")
    elif l_s and (not l_b or l_s > l_b):
        dur = get_mins(l_s)
        return (f"📉 SELL({dur}m)" if dur <= 30 else "空 🔴"), curr_p, ("SELL" if dur <= 1 else "")
    return "维持", curr_p, ""

def get_okx_ls_ratio(ccy):
    """尝试获取 OKX 多空比"""
    try:
        url = f"https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio?ccy={ccy.upper()}"
        res = requests.get(url, timeout=2).json()
        if res.get('code') == '0' and res.get('data'):
            return float(res['data'][0]['ratio'])
    except: pass
    return "N/A"

# --- 4. 数据执行 ---
def fetch_all():
    exchange = ccxt.okx()
    results = []
    
    # 1. 币圈
    CONTRACTS = ["TAO", "XAG", "XAU"]
    for base in selected_cryptos:
        sym = f"{base}/USDT:USDT" if base in CONTRACTS else f"{base}/USDT"
        ls = get_okx_ls_ratio(base)
        row = {"资产": base, "持仓多空比": ls}
        lp = 0
        for tf in selected_intervals:
            try:
                bars = exchange.fetch_ohlcv(sym, timeframe=tf, limit=150)
                data = pd.DataFrame(bars, columns=['Time','Open','High','Low','Close','Volume'])
                data['Time'] = pd.to_datetime(data['Time'], unit='ms')
                data.set_index('Time', inplace=True)
                df = calculate_ut_bot(data)
                status, price, _ = get_signal_info(df)
                row[tf] = status
                if price > 0: lp = price
            except: row[tf] = "N/A"
        row["现价"] = f"{lp:.4f}"
        results.append(row)

    # 2. 美股
    yf_map = {"15m":"15m","30m":"30m","1h":"1h","4h":"1h","1d":"1d"}
    for sym in custom_stocks:
        row = {"资产": sym, "持仓多空比": "美股"}
        lp = 0
        for tf in selected_intervals:
            try:
                data = yf.download(sym, period="10d" if "m" in tf else "100d", interval=yf_map[tf], progress=False, auto_adjust=True)
                if data.empty: row[tf] = "休市"; continue
                df = calculate_ut_bot(data)
                status, price, _ = get_signal_info(df)
                row[tf] = status
                if price > 0: lp = price
            except: row[tf] = "N/A"
        row["现价"] = f"{lp:.2f}"
        results.append(row)
    return pd.DataFrame(results)

# --- 5. 页面展示 ---
st.markdown("### 🛡️ UT Bot 全维资产监控 (1.0对齐版)")
if 'data_cache' not in st.session_state or st.sidebar.button("🔄 立即同步"):
    st.session_state.data_cache = fetch_all()

df = st.session_state.data_cache

if not df.empty:
    def get_style(val):
        if 'BUY' in str(val): return 'color: #00ff00; font-weight: bold; background-color: #004400'
        if 'SELL' in str(val): return 'color: #ff4444; font-weight: bold; background-color: #440000'
        if '🟢' in str(val): return 'color: #00ff00'
        if '🔴' in str(val): return 'color: #ff4444'
        if isinstance(val, float):
            if val > 1.1: return 'color: #ff4444'
            if val < 0.9: return 'color: #00ff00'
        return ''

    # 彻底解决行数限制的渲染方式
    html = "<table style='width:100%; border-collapse: collapse; text-align: left;'>"
    html += f"<tr style='background-color: #333; color: white;'>{''.join(f'<th style=padding:10px; border:1px solid #555;>{c}</th>' for c in df.columns)}</tr>"
    for _, row in df.iterrows():
        cells = "".join(f"<td style='padding:10px; border:1px solid #444; {get_style(row[c])}'>{row[c]}</td>" for c in df.columns)
        html += f"<tr>{cells}</tr>"
    html += "</table>"
    st.write(html, unsafe_allow_html=True)

st.sidebar.write(f"📊 监控状态: 币圈 {len(selected_cryptos)} | 美股 {len(custom_stocks)}")
