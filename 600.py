import streamlit as st
import pandas as pd
import numpy as np
import pandas_ta as ta
import ccxt
import yfinance as yf
from datetime import datetime
import pytz
import requests
from streamlit_autorefresh import st_autorefresh

# --- 1. 配置 ---
st.set_page_config(page_title="UT Bot 币股双维看板", layout="wide")
BEIJING_TZ = pytz.timezone('Asia/Shanghai')
st_autorefresh(interval=60 * 1000, key="refresh")

# --- 2. 侧边栏 ---
st.sidebar.header("🛡️ 系统设置")
sensitivity = st.sidebar.slider("敏感度", 0.1, 5.0, 1.0, 0.1)
atr_period = st.sidebar.slider("ATR 周期", 1, 30, 10)

CRYPTO_LIST = ["BTC", "ETH", "SOL", "SUI", "RENDER", "DOGE", "XRP", "UNI", "HYPE", "AAVE", "TAO", "XAG", "XAU"]
selected_cryptos = st.sidebar.multiselect("加密货币清单", CRYPTO_LIST, default=CRYPTO_LIST)

stock_input = st.sidebar.text_area("美股代码", value="NVDA,AAPL,TSLA,QQQ")
custom_stocks = [s.strip().upper() for s in stock_input.split(",") if s.strip()]

selected_intervals = ["15m", "30m", "1h", "4h", "1d"]

# --- 3. 核心算法 ---
def calculate_ut_bot(df):
    if df.empty or len(df) < 20: return pd.DataFrame()
    df.columns = [str(c).capitalize() for c in df.columns]
    # 处理 yfinance 的索引
    if 'Close' not in df.columns and isinstance(df.columns, pd.Index):
        df = df.copy() # 防止 SettingWithCopyWarning
    
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

def get_sig(df, is_crypto=True):
    if df.empty: return "N/A", 0
    curr_p = df.iloc[-1]['Close']
    buys, sells = df[df['buy']], df[df['sell']]
    l_b = buys.index[-1] if not buys.empty else None
    l_s = sells.index[-1] if not sells.empty else None
    now = datetime.now(pytz.utc) if is_crypto else datetime.now(BEIJING_TZ)
    
    # 统一转换时间对比
    def to_utc(ts):
        if ts is None: return None
        if ts.tzinfo is None: return pytz.utc.localize(ts)
        return ts.astimezone(pytz.utc)

    l_b_u, l_s_u, now_u = to_utc(l_b), to_utc(l_s), to_utc(now)

    if l_b_u and (not l_s_u or l_b_u > l_s_u):
        dur = int((now_u - l_b_u).total_seconds() / 60)
        return (f"🚀 BUY({dur}m)" if 0 <= dur <= 30 else "多 🟢"), curr_p
    elif l_s_u and (not l_b_u or l_s_u > l_b_u):
        dur = int((now_u - l_s_u).total_seconds() / 60)
        return (f"📉 SELL({dur}m)" if 0 <= dur <= 30 else "空 🔴"), curr_p
    return "维持", curr_p

def get_ls(ccy):
    """尝试多域名绕过获取多空比"""
    headers = {'User-Agent': 'Mozilla/5.0'}
    for domain in ["www.okx.com", "aws.okx.com"]:
        try:
            url = f"https://{domain}/api/v5/rubik/stat/contracts/long-short-account-ratio?ccy={ccy.upper()}"
            res = requests.get(url, headers=headers, timeout=2).json()
            if res.get('code') == '0': return res['data'][0]['ratio']
        except: continue
    return "N/A"

# --- 4. 渲染函数 ---
def render_table(df):
    def style(v):
        if 'BUY' in str(v): return 'color:#00ff00; font-weight:bold; background:#004400'
        if 'SELL' in str(v): return 'color:#ff4444; font-weight:bold; background:#440000'
        if '🟢' in str(v): return 'color:#00ff00'
        if '🔴' in str(v): return 'color:#ff4444'
        return ''
    html = "<table style='width:100%; border-collapse:collapse;'>"
    html += f"<tr style='background:#333; color:white;'>{''.join(f'<th style=padding:10px; border:1px solid #555;>{c}</th>' for c in df.columns)}</tr>"
    for _, row in df.iterrows():
        html += "<tr>" + "".join(f"<td style='padding:10px; border:1px solid #444; {style(row[c])}'>{row[c]}</td>" for c in df.columns) + "</tr>"
    st.write(html + "</table>", unsafe_allow_html=True)

# --- 5. 主逻辑 ---
st.title("🛡️ UT Bot 币股分离监控系统")

# 币圈板块
st.header("🪙 加密货币市场")
if st.button("🔄 同步币圈"):
    ex = ccxt.okx()
    c_res = []
    CONTRACTS = ["TAO", "XAG", "XAU"]
    for base in selected_cryptos:
        sym = f"{base}/USDT:USDT" if base in CONTRACTS else f"{base}/USDT"
        row = {"资产": base, "持仓多空比": get_ls(base)}
        lp = 0
        for tf in selected_intervals:
            try:
                data = pd.DataFrame(ex.fetch_ohlcv(sym, tf, limit=150), columns=['Time','Open','High','Low','Close','Volume'])
                data['Time'] = pd.to_datetime(data['Time'], unit='ms')
                data.set_index('Time', inplace=True)
                df_res = calculate_ut_bot(data)
                row[tf], lp = get_sig(df_res, True)
            except: row[tf] = "N/A"
        row["现价"] = f"{lp:.4f}"
        c_res.append(row)
    st.session_state.c_df = pd.DataFrame(c_res)

if 'c_df' in st.session_state:
    render_table(st.session_state.c_df)

st.markdown("---")

# 美股板块
st.header("🇺🇸 美股/指数市场")
if st.button("🔄 同步美股"):
    s_res = []
    yf_tf = {"15m":"15m","30m":"30m","1h":"1h","4h":"1h","1d":"1d"}
    for sym in custom_stocks:
        row = {"资产": sym}
        lp = 0
        for tf in selected_intervals:
            try:
                data = yf.download(sym, period="10d", interval=yf_tf[tf], progress=False, auto_adjust=True)
                df_res = calculate_ut_bot(data)
                row[tf], lp = get_sig(df_res, False)
            except: row[tf] = "N/A"
        row["现价"] = f"{lp:.2f}"
        s_res.append(row)
    st.session_state.s_df = pd.DataFrame(s_res)

if 's_df' in st.session_state:
    render_table(st.session_state.s_df)
