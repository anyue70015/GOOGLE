import streamlit as st
import pandas as pd
import numpy as np
import pandas_ta as ta
import ccxt
import yfinance as yf
from datetime import datetime, timedelta
import pytz
from streamlit_autorefresh import st_autorefresh
import requests

# --- 1. 基础配置 ---
st.set_page_config(page_title="UT Bot 实时看板", layout="wide")
BEIJING_TZ = pytz.timezone('Asia/Shanghai')

def get_now_beijing():
    return datetime.now(BEIJING_TZ)

# --- 2. 侧边栏 ---
st.sidebar.header("🛡️ 系统设置")
sct_key = st.sidebar.text_input("Server酱 Key", type="password")
sensitivity = st.sidebar.slider("敏感度", 0.1, 5.0, 1.0, 0.1)
atr_period = st.sidebar.slider("ATR 周期", 1, 30, 10)

CRYPTO_LIST = ["BTC", "ETH", "SOL", "SUI", "RENDER", "DOGE", "XRP", "UNI", "HYPE", "AAVE", "TAO", "XAG", "XAU"]
selected_cryptos = st.sidebar.multiselect("加密货币", CRYPTO_LIST, default=CRYPTO_LIST)

stock_input = st.sidebar.text_area("美股代码 (逗号分隔)", value="NVDA,AAPL,TSLA,QQQ")
custom_stocks = [s.strip().upper() for s in stock_input.split(",") if s.strip()]

selected_intervals = ["15m", "30m", "1h", "4h", "1d"]
st_autorefresh(interval=60 * 1000, key="refresh")

# --- 3. 核心算法 ---
def calculate_ut_bot(df):
    if df.empty or len(df) < atr_period + 5: return pd.DataFrame()
    
    # 统一列名
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    cols = {c.lower(): c for c in df.columns}
    df = df.rename(columns={cols['high']: 'High', cols['low']: 'Low', cols['close']: 'Close'})
    
    # 计算 UT Bot
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
    if df.empty or len(df) < 2: return "N/A", 0
    curr_p = df.iloc[-1]['Close']
    
    # 状态追溯
    buys = df[df['buy'] == True]
    sells = df[df['sell'] == True]
    l_b = buys.index[-1] if not buys.empty else None
    l_s = sells.index[-1] if not sells.empty else None
    
    now_bj = get_now_beijing().replace(tzinfo=None) # 统一用无时区北京时间对比

    def to_bj_naive(ts):
        if ts is None: return None
        if ts.tzinfo is not None:
            return ts.astimezone(BEIJING_TZ).replace(tzinfo=None)
        # 币圈数据通常是 UTC，手动加 8 小时
        return ts + timedelta(hours=8)

    l_b_bj = to_bj_naive(l_b)
    l_s_bj = to_bj_naive(l_s)

    if l_b_bj and (not l_s_bj or l_b_bj > l_s_bj):
        dur = int((now_bj - l_b_bj).total_seconds() / 60)
        return (f"🚀 BUY({dur}m)" if 0 <= dur <= 30 else "多 🟢"), curr_p
    elif l_s_bj and (not l_b_bj or l_s_bj > l_b_bj):
        dur = int((now_bj - l_s_bj).total_seconds() / 60)
        return (f"📉 SELL({dur}m)" if 0 <= dur <= 30 else "空 🔴"), curr_p
    return "维持", curr_p

# --- 4. 数据执行 ---
def fetch_all():
    exchange = ccxt.okx()
    results = []
    # 币圈
    CONTRACTS = ["TAO", "XAG", "XAU"]
    for base in selected_cryptos:
        sym = f"{base}/USDT:USDT" if base in CONTRACTS else f"{base}/USDT"
        row = {"资产": base, "持仓多空比": "N/A"}
        try:
            # 尝试抓取多空比
            url = f"https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio?ccy={base}"
            res = requests.get(url, timeout=1).json()
            if res.get('code') == '0' and res.get('data'):
                row["持仓多空比"] = float(res['data'][0]['ratio'])
        except: pass

        lp = 0
        for tf in selected_intervals:
            try:
                bars = exchange.fetch_ohlcv(sym, timeframe=tf, limit=150)
                data = pd.DataFrame(bars, columns=['Time','Open','High','Low','Close','Volume'])
                data['Time'] = pd.to_datetime(data['Time'], unit='ms')
                data.set_index('Time', inplace=True)
                df = calculate_ut_bot(data)
                status, price = get_signal_info(df)
                row[tf] = status
                if price > 0: lp = price
            except: row[tf] = "N/A"
        row["现价"] = f"{lp:.4f}"
        results.append(row)

    # 美股
    yf_map = {"15m":"15m","30m":"30m","1h":"1h","4h":"1h","1d":"1d"}
    for sym in custom_stocks:
        row = {"资产": sym, "持仓多空比": "美股"}
        lp = 0
        for tf in selected_intervals:
            try:
                data = yf.download(sym, period="10d", interval=yf_map[tf], progress=False, auto_adjust=True)
                df = calculate_ut_bot(data)
                status, price = get_signal_info(df)
                row[tf] = status
                if price > 0: lp = price
            except: row[tf] = "N/A"
        row["现价"] = f"{lp:.2f}"
        results.append(row)
    return pd.DataFrame(results)

# --- 5. 渲染 ---
if 'data_cache' not in st.session_state or st.sidebar.button("🔄 刷新数据"):
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

    # HTML 渲染确保 100% 显示所有行
    html = "<table style='width:100%; border-collapse: collapse;'>"
    html += f"<tr style='background-color: #333; color: white;'>{''.join(f'<th style=padding:10px; border:1px solid #555;>{c}</th>' for c in df.columns)}</tr>"
    for _, row in df.iterrows():
        cells = "".join(f"<td style='padding:10px; border:1px solid #444; {get_style(row[c])}'>{row[c]}</td>" for c in df.columns)
        html += f"<tr>{cells}</tr>"
    html += "</table>"
    st.write(html, unsafe_allow_html=True)
