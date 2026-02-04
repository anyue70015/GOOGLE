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
st.set_page_config(page_title="UT Bot 科学看板", layout="wide")
BEIJING_TZ = pytz.timezone('Asia/Shanghai')

def get_now_beijing():
    return datetime.now(BEIJING_TZ)

# --- 2. 侧边栏 ---
st.sidebar.header("🛡️ 系统设置")
sct_key = st.sidebar.text_input("Server酱 Key", type="password")
sensitivity = st.sidebar.slider("敏感度", 1.0, 5.0, 2.0, 0.1)
atr_period = st.sidebar.slider("ATR 周期", 1, 30, 10)

# 币种列表：TAO, XAG, XAU 强制合约，其余现货
CRYPTO_LIST = ["BTC", "ETH", "SOL", "SUI", "RENDER", "DOGE", "XRP", "UNI", "HYPE", "AAVE", "TAO", "XAG", "XAU"]
selected_cryptos = st.sidebar.multiselect("加密货币", CRYPTO_LIST, default=CRYPTO_LIST)

uploaded_file = st.sidebar.file_uploader("上传股票 TXT", type="txt")
custom_stocks = [line.strip() for line in uploaded_file.read().decode("utf-8").splitlines() if line.strip()] if uploaded_file else []

selected_intervals = ["15m", "30m", "1h", "4h", "1d"]
st_autorefresh(interval=60 * 1000, key="refresh") # 1分钟刷一次

# --- 3. 核心计算 ---
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
            trail_stop[i] = src.iloc[i] - n_loss.iloc[i] if src.iloc[i] > p_stop else src.iloc[i] + n_loss.iloc[i]
    df['trail_stop'] = trail_stop
    df['buy'] = (df['Close'] > df['trail_stop']) & (df['Close'].shift(1) <= df['trail_stop'].shift(1))
    df['sell'] = (df['Close'] < df['trail_stop']) & (df['Close'].shift(1) >= df['trail_stop'].shift(1))
    return df

def get_signal_info(df, timeframe):
    if df.empty or len(df) < 2: return "N/A", 0, ""
    curr_p = df.iloc[-1]['Close']
    buys, sells = df[df['buy']], df[df['sell']]
    l_b = buys.index[-1] if not buys.empty else None
    l_s = sells.index[-1] if not sells.empty else None
    now_bj = get_now_beijing()

    def get_mins(sig_time):
        if sig_time.tzinfo is None: sig_time = sig_time.replace(tzinfo=pytz.utc).astimezone(BEIJING_TZ)
        return int((now_bj - sig_time).total_seconds() / 60)

    if l_b and (not l_s or l_b > l_s):
        dur = get_mins(l_b)
        return (f"🚀 BUY ({dur}m)" if dur <= 30 else "多 🟢"), curr_p, ("BUY" if dur <= 1 else "")
    elif l_s and (not l_b or l_s > l_b):
        dur = get_mins(l_s)
        return (f"📉 SELL ({dur}m)" if dur <= 30 else "空 🔴"), curr_p, ("SELL" if dur <= 1 else "")
    return "维持", curr_p, ""

def get_okx_ls_ratio(symbol):
    """强化版 OKX 多空人数比抓取"""
    try:
        # 使用 OKX V5 统计接口，instId 需为合约格式
        instId = f"{symbol}-USDT-SWAP"
        url = f"https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio?instId={instId}"
        headers = {"Content-Type": "application/json"}
        res = requests.get(url, headers=headers, timeout=5).json()
        if res.get('code') == '0' and len(res.get('data', [])) > 0:
            return float(res['data'][0]['ratio'])
    except: pass
    return "N/A"

def send_wechat(t, c):
    if sct_key: requests.post(f"https://sctapi.ftqq.com/{sct_key}.send", data={"title":t, "desp":c})

# --- 4. 数据采集 ---
def fetch_data():
    exchange = ccxt.okx()
    results = []
    CONTRACT_ONLY = ["TAO", "XAG", "XAU"] # 你的特殊规则

    for base in selected_cryptos:
        is_con = base in CONTRACT_ONLY
        sym = f"{base}/USDT:USDT" if is_con else f"{base}/USDT"
        ls = get_okx_ls_ratio(base)
        row = {"资产": base, "持仓多空比": ls}
        lp = 0
        for tf in selected_intervals:
            try:
                bars = exchange.fetch_ohlcv(sym, timeframe=tf, limit=100)
                df = pd.DataFrame(bars, columns=['Time','Open','High','Low','Close','Volume'])
                df['Time'] = pd.to_datetime(df['Time'], unit='ms')
                df.set_index('Time', inplace=True)
                df = calculate_ut_bot(df)
                status, price, alert = get_signal_info(df, tf)
                row[tf] = status
                if price > 0: lp = price
                if alert: send_wechat(f"UT: {base} {tf}", f"信号: {alert}\n价格: {price}\n多空比: {ls}")
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

# --- 5. 页面渲染 ---
st.markdown("### 🛡️ UT Bot 科学看板 (无滚动条直选版)")
now = get_now_beijing()
st.write(f"🕒 更新时间: {now.strftime('%H:%M:%S')} | 多空占比衡量市场冷热，多空比衡量主力意图")

if 'cache' not in st.session_state or st.sidebar.button("🔄 同步"):
    st.session_state.cache = fetch_data()

df = st.session_state.cache
if not df.empty:
    # 进度条
    all_v = df[selected_intervals].values.flatten()
    bulls = sum(1 for x in all_v if "多" in str(x) or "BUY" in str(x))
    total = len([x for x in all_v if x not in ["N/A", "休市"]])
    st.progress(bulls/total if total > 0 else 0, text=f"全市场走牛比例: {bulls/total:.1%}")

    # 样式美化
    def color_df(v):
        if 'BUY' in str(v): return 'color: #00ff00; font-weight: bold; background-color: #004400'
        if 'SELL' in str(v): return 'color: #ff4444; font-weight: bold; background-color: #440000'
        if '🟢' in str(v): return 'color: #00ff00'
        if '🔴' in str(v): return 'color: #ff4444'
        # 多空比逻辑：散户多(>1)显红，散户空(<1)显绿
        if isinstance(v, float):
            if v > 1.1: return 'color: #ff4444'
            if v < 0.9: return 'color: #00ff00'
        return ''

    # 使用 st.table 代替 st.dataframe，解决滚动条问题
    st.table(df.style.applymap(color_df))

st.sidebar.markdown("""
**多空比 (LS Ratio) 指南：**
- **数值 > 1.2**：散户疯狂做多，主力可能反向收割 (看空信号 ⚠️)
- **数值 < 0.8**：散户集体看空，主力可能拉升 (看多信号 ✅)
""")
