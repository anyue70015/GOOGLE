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
st.set_page_config(page_title="UT Bot 全维看板", layout="wide")
BEIJING_TZ = pytz.timezone('Asia/Shanghai')

def get_now_beijing():
    return datetime.now(BEIJING_TZ)

# --- 2. 侧边栏 ---
st.sidebar.header("🛡️ 系统设置")
sct_key = st.sidebar.text_input("Server酱 Key", type="password")
sensitivity = st.sidebar.slider("敏感度", 1.0, 5.0, 1.0, 0.1) # 默认 1.0 对齐 TV
atr_period = st.sidebar.slider("ATR 周期", 1, 30, 10)

# 加密货币清单
CRYPTO_LIST = ["BTC", "ETH", "SOL", "SUI", "RENDER", "DOGE", "XRP", "UNI", "HYPE", "AAVE", "TAO", "XAG", "XAU"]
selected_cryptos = st.sidebar.multiselect("加密货币", CRYPTO_LIST, default=CRYPTO_LIST)

# 股票清单：直接输入代码，如 NVDA, AAPL, TSLA
st.sidebar.subheader("美股/指数配置")
stock_input = st.sidebar.text_area("输入美股代码 (逗号分隔)", value="NVDA,AAPL,TSLA,QQQ,IXIC")
custom_stocks = [s.strip().upper() for s in stock_input.split(",") if s.strip()]

selected_intervals = ["15m", "30m", "1h", "4h", "1d"]
st_autorefresh(interval=60 * 1000, key="refresh")

# --- 3. 核心算法 (严格对齐 TV) ---
def calculate_ut_bot(df):
    if len(df) < atr_period + 5: return pd.DataFrame()
    # 强制重命名列名，防止 yfinance 返回多级索引
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
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
    
    # 查找最近的买卖点
    buys = df[df['buy'] == True]
    sells = df[df['sell'] == True]
    l_b = buys.index[-1] if not buys.empty else None
    l_s = sells.index[-1] if not sells.empty else None
    
    now_bj = get_now_beijing()
    def get_mins(sig_time):
        # 统一转为无时区北京时间进行计算
        if sig_time.tzinfo is not None:
            sig_time = sig_time.astimezone(BEIJING_TZ).replace(tzinfo=None)
        return int((now_bj.replace(tzinfo=None) - sig_time).total_seconds() / 60)

    if l_b and (not l_s or l_b > l_s):
        dur = get_mins(l_b)
        return (f"🚀 BUY({dur}m)" if dur <= 30 else "多 🟢"), curr_p, ("BUY" if dur <= 1 else "")
    elif l_s and (not l_b or l_s > l_b):
        dur = get_mins(l_s)
        return (f"📉 SELL({dur}m)" if dur <= 30 else "空 🔴"), curr_p, ("SELL" if dur <= 1 else "")
    return "维持", curr_p, ""

# --- 4. 数据采集 ---
def fetch_data():
    exchange = ccxt.okx()
    results = []
    
    # 加密货币处理
    CONTRACT_LIST = ["TAO", "XAG", "XAU"]
    for base in selected_cryptos:
        sym = f"{base}/USDT:USDT" if base in CONTRACT_LIST else f"{base}/USDT"
        row = {"资产": base, "持仓多空比": "--"} # 多空比云端暂设为--防止死锁
        lp = 0
        for tf in selected_intervals:
            try:
                bars = exchange.fetch_ohlcv(sym, timeframe=tf, limit=150)
                df = calculate_ut_bot(pd.DataFrame(bars, columns=['Time','Open','High','Low','Close','Volume']))
                status, price, _ = get_signal_info(df)
                row[tf] = status
                if price > 0: lp = price
            except: row[tf] = "失败"
        row["现价"] = f"{lp:.4f}"
        results.append(row)

    # 美股处理 (修正版)
    yf_map = {"15m":"15m","30m":"30m","1h":"1h","4h":"1h","1d":"1d"} # 4h用1h模拟
    for sym in custom_stocks:
        row = {"资产": sym, "持仓多空比": "美股"}
        lp = 0
        for tf in selected_intervals:
            try:
                # 抓取数据，增加 auto_adjust=True 避免分拆导致的跳空
                data = yf.download(sym, period="60d", interval=yf_map[tf], progress=False, auto_adjust=True)
                if data.empty: row[tf] = "休市"; continue
                df = calculate_ut_bot(data)
                status, price, _ = get_signal_info(df)
                row[tf] = status
                if price > 0: lp = price
            except: row[tf] = "N/A"
        row["现价"] = f"{lp:.2f}"
        results.append(row)
    return pd.DataFrame(results)

# --- 5. 渲染 ---
st.markdown("### 🛡️ UT Bot 全资产实时看板 (1.0对齐版)")
if 'cache' not in st.session_state or st.sidebar.button("🔄 同步"):
    st.session_state.cache = fetch_data()

df = st.session_state.cache
if not df.empty:
    def style_table(v):
        if 'BUY' in str(v): return 'color: #00ff00; font-weight: bold; background-color: #004400'
        if 'SELL' in str(v): return 'color: #ff4444; font-weight: bold; background-color: #440000'
        if '🟢' in str(v): return 'color: #00ff00'
        if '🔴' in str(v): return 'color: #ff4444'
        return ''

    # 使用 HTML 渲染，确保不限制行数，全部显示
    html = "<table style='width:100%; border-collapse: collapse; text-align: left;'>"
    html += f"<tr style='background-color: #333; color: white;'>{''.join(f'<th style=padding:8px; border:1px solid #555;>{c}</th>' for c in df.columns)}</tr>"
    for _, row in df.iterrows():
        cells = "".join(f"<td style='padding:8px; border:1px solid #444; {style_table(row[c])}'>{row[c]}</td>" for c in df.columns)
        html += f"<tr>{cells}</tr>"
    html += "</table>"
    st.write(html, unsafe_allow_html=True)
