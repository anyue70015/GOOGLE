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
st.set_page_config(page_title="UT Bot 终极看板 (TV 1.0 对齐版)", layout="wide")
BEIJING_TZ = pytz.timezone('Asia/Shanghai')

def get_now_beijing():
    return datetime.now(BEIJING_TZ)

# --- 2. 侧边栏 ---
st.sidebar.header("🛡️ 系统设置")
sct_key = st.sidebar.text_input("Server酱 SendKey", type="password")

# 默认参数已根据你的反馈调整为 1.0 / 10
sensitivity = st.sidebar.slider("敏感度 (Key Value)", 1.0, 5.0, 1.0, 0.1)
atr_period = st.sidebar.slider("ATR 周期", 1, 30, 10)

CRYPTO_LIST = ["BTC", "ETH", "SOL", "SUI", "RENDER", "DOGE", "XRP", "UNI", "HYPE", "AAVE", "TAO", "XAG", "XAU"]
selected_cryptos = st.sidebar.multiselect("加密货币 (OKX)", CRYPTO_LIST, default=CRYPTO_LIST)

uploaded_file = st.sidebar.file_uploader("上传股票 TXT", type="txt")
custom_stocks = [line.strip() for line in uploaded_file.read().decode("utf-8").splitlines() if line.strip()] if uploaded_file else []

selected_intervals = ["15m", "30m", "1h", "4h", "1d"]
st_autorefresh(interval=60 * 1000, key="refresh") # 1分钟刷新

# --- 3. 核心算法 (严格对齐 TV 版) ---
def calculate_ut_bot(df):
    if len(df) < atr_period: return df
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

def get_signal_info(df, timeframe):
    if df.empty or len(df) < 2: return "N/A", 0, ""
    curr_p = df.iloc[-1]['Close']
    
    # 状态追溯逻辑
    buys = df[df['buy'] == True]
    sells = df[df['sell'] == True]
    l_b_idx = buys.index[-1] if not buys.empty else None
    l_s_idx = sells.index[-1] if not sells.empty else None
    
    now_bj = get_now_beijing()
    def get_duration(sig_time):
        if sig_time.tzinfo is None: sig_time = sig_time.replace(tzinfo=pytz.utc).astimezone(BEIJING_TZ)
        return int((now_bj - sig_time).total_seconds() / 60)

    if l_b_idx and (not l_s_idx or l_b_idx > l_s_idx):
        dur = get_duration(l_b_idx)
        if dur <= 30: return f"🚀 BUY({dur}m)", curr_p, ("BUY" if dur <= 1 else "")
        return "多 🟢", curr_p, ""
    elif l_s_idx and (not l_b_idx or l_s_idx > l_b_idx):
        dur = get_duration(l_s_idx)
        if dur <= 30: return f"📉 SELL({dur}m)", curr_p, ("SELL" if dur <= 1 else "")
        return "空 🔴", curr_p, ""
    return "维持", curr_p, ""

def get_okx_ls_ratio(base_symbol):
    """
    云端专用绕过逻辑：尝试多个域名抓取多空比
    """
    base = base_symbol.upper()
    urls = [
        f"https://aws.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio?ccy={base}",
        f"https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio?ccy={base}"
    ]
    for url in urls:
        try:
            res = requests.get(url, timeout=3).json()
            if res.get('code') == '0' and res.get('data'):
                return float(res['data'][0]['ratio'])
        except: continue
    return "N/A"

# --- 4. 数据抓取逻辑 ---
def fetch_data():
    exchange = ccxt.okx()
    results = []
    # TAO, XAG, XAU 是合约，其他全现货
    CONTRACT_ONLY = ["TAO", "XAG", "XAU"]

    for base in selected_cryptos:
        is_con = base in CONTRACT_ONLY
        sym = f"{base}/USDT:USDT" if is_con else f"{base}/USDT"
        ls = get_okx_ls_ratio(base)
        row = {"资产": base, "持仓多空比": ls}
        lp = 0
        for tf in selected_intervals:
            try:
                # 抓取 200 根，确保 ATR 算法跑稳
                bars = exchange.fetch_ohlcv(sym, timeframe=tf, limit=200)
                df = pd.DataFrame(bars, columns=['Time','Open','High','Low','Close','Volume'])
                df['Time'] = pd.to_datetime(df['Time'], unit='ms').dt.tz_localize('UTC').dt.tz_convert(BEIJING_TZ)
                df.set_index('Time', inplace=True)
                df = calculate_ut_bot(df)
                status, price, alert = get_signal_info(df, tf)
                row[tf] = status
                if price > 0: lp = price
                if alert: 
                    msg = f"信号: {alert}\n价格: {price}\n多空比: {ls}\n源: {'合约' if is_con else '现货'}"
                    requests.post(f"https://sctapi.ftqq.com/{sct_key}.send", data={"title": f"UT:{base}-{tf}", "desp": msg})
            except: row[tf] = "N/A"
        row["现价"] = f"{lp:.4f}"
        results.append(row)

    for sym in custom_stocks:
        row = {"资产": sym, "持仓多空比": "--"}
        lp = 0
        for tf in selected_intervals:
            try:
                data = yf.download(sym, period="5d", interval="15m" if "m" in tf else "1d", progress=False)
                df = calculate_ut_bot(data.copy())
                status, price, _ = get_signal_info(df, tf)
                row[tf] = status
                if price > 0: lp = price
            except: row[tf] = "N/A"
        row["现价"] = f"{lp:.2f}"
        results.append(row)
    return pd.DataFrame(results)

# --- 5. 渲染页面 ---
st.markdown("### 🛡️ UT Bot 科学看板 (TV校准版)")
now = get_now_beijing()
st.write(f"🕒 更新时间: {now.strftime('%H:%M:%S')} | 参数: {sensitivity}/{atr_period}")

if 'cache' not in st.session_state or st.sidebar.button("🔄 同步行情"):
    st.session_state.cache = fetch_data()

df = st.session_state.cache
if not df.empty:
    all_v = df[selected_intervals].values.flatten()
    bulls = sum(1 for x in all_v if "多" in str(x) or "BUY" in str(x))
    total = len([x for x in all_v if x not in ["N/A", "休市"]])
    st.progress(bulls/total if total > 0 else 0, text=f"全市场看多占比: {bulls/total:.1%}")

    def style_cells(v):
        if 'BUY' in str(v): return 'color: #00ff00; font-weight: bold; background-color: #004400'
        if 'SELL' in str(v): return 'color: #ff4444; font-weight: bold; background-color: #440000'
        if '🟢' in str(v): return 'color: #00ff00'
        if '🔴' in str(v): return 'color: #ff4444'
        if isinstance(v, (float)):
            if v > 1.1: return 'color: #ff4444; font-weight: bold'
            if v < 0.9: return 'color: #00ff00; font-weight: bold'
        return ''

    st.table(df.style.applymap(style_cells))

st.sidebar.markdown(f"**当前规则：**\n- TAO/XAG/XAU: 合约\n- 其他: 现货\n- 报警: 30分钟后自动消失")
