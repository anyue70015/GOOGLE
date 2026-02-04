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

# --- 1. 基础配置与北京时间 ---
st.set_page_config(page_title="UT Bot 终极科学看板", layout="wide")
BEIJING_TZ = pytz.timezone('Asia/Shanghai')

def get_now_beijing():
    return datetime.now(BEIJING_TZ)

# --- 2. 侧边栏配置 ---
st.sidebar.header("🛡️ 系统设置")
sct_key = st.sidebar.text_input("Server酱 SendKey", type="password")

st.sidebar.subheader("策略参数")
sensitivity = st.sidebar.slider("敏感度 (Multiplier)", 1.0, 5.0, 2.0, 0.1)
atr_period = st.sidebar.slider("ATR 周期", 1, 30, 10)

# 资产清单
CRYPTO_LIST = ["BTC", "ETH", "SOL", "SUI", "RENDER", "DOGE", "XRP", "UNI", "HYPE", "AAVE", "TAO", "XAG", "XAU"]
selected_cryptos = st.sidebar.multiselect("加密货币", CRYPTO_LIST, default=CRYPTO_LIST)

uploaded_file = st.sidebar.file_uploader("上传股票 TXT (每行一个代码)", type="txt")
custom_stocks = []
if uploaded_file:
    custom_stocks = [line.strip() for line in uploaded_file.read().decode("utf-8").splitlines() if line.strip()]

selected_intervals = ["15m", "30m", "1h", "4h", "1d"]
# 1分钟自动刷新，确保倒计时跳动
st_autorefresh(interval=60 * 1000, key="datarefresh")

# --- 3. 核心算法逻辑 ---
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
    buys, sells = df[df['buy'] == True], df[df['sell'] == True]
    l_b_idx = buys.index[-1] if not buys.empty else None
    l_s_idx = sells.index[-1] if not sells.empty else None
    now_bj = get_now_beijing()

    def get_duration_mins(sig_time):
        if sig_time.tzinfo is None: sig_time = sig_time.replace(tzinfo=pytz.utc).astimezone(BEIJING_TZ)
        return int((now_bj - sig_time).total_seconds() / 60)

    if l_b_idx and (not l_s_idx or l_b_idx > l_s_idx):
        dur = get_duration_mins(l_b_idx)
        if dur <= 30: return f"🚀 BUY({dur}m)", curr_p, ("BUY" if dur <= 1 else "")
        return "多 🟢", curr_p, ""
    elif l_s_idx and (not l_b_idx or l_s_idx > l_b_idx):
        dur = get_duration_mins(l_s_idx)
        if dur <= 30: return f"📉 SELL({dur}m)", curr_p, ("SELL" if dur <= 1 else "")
        return "空 🔴", curr_p, ""
    return "维持", curr_p, ""

def get_okx_ls_ratio(base_symbol):
    """
    修正后的多空比函数：使用 ccy 参数避免 50014 错误
    """
    try:
        url = f"https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio?ccy={base_symbol}"
        res = requests.get(url, timeout=5).json()
        if res.get('code') == '0' and res.get('data'):
            return float(res['data'][0]['ratio'])
    except: pass
    return "N/A"

def send_wechat(t, c):
    if sct_key: requests.post(f"https://sctapi.ftqq.com/{sct_key}.send", data={"title":t, "desp":c})

# --- 4. 数据抓取 ---
def fetch_data():
    exchange = ccxt.okx()
    results = []
    CONTRACT_LIST = ["TAO", "XAG", "XAU"]

    for base in selected_cryptos:
        is_con = base in CONTRACT_LIST
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
                if alert: send_wechat(f"UT信号: {base} {tf}", f"信号: {alert}\n价格: {price}\n多空比: {ls}")
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

# --- 5. 渲染 ---
st.markdown("### 🛡️ UT Bot 混合资产实时看板")
c1, c2 = st.columns([2, 1])
now = get_now_beijing()
c1.write(f"🕒 北京时间: {now.strftime('%H:%M:%S')}")

if 'cache' not in st.session_state or st.sidebar.button("🔄 同步行情"):
    st.session_state.cache = fetch_data()

df = st.session_state.cache
if not df.empty:
    all_v = df[selected_intervals].values.flatten()
    bulls = sum(1 for x in all_v if "多" in str(x) or "BUY" in str(x))
    total = len([x for x in all_v if x not in ["N/A", "休市"]])
    ratio = bulls/total if total > 0 else 0
    st.progress(ratio, text=f"全市场走牛比例 (多头强度): {ratio:.1%}")

    def style_cells(v):
        # 信号颜色
        if 'BUY' in str(v): return 'color: #00ff00; font-weight: bold; background-color: #004400'
        if 'SELL' in str(v): return 'color: #ff4444; font-weight: bold; background-color: #440000'
        if '🟢' in str(v): return 'color: #00ff00'
        if '🔴' in str(v): return 'color: #ff4444'
        # 多空比颜色：散户多(>1)显红，散户空(<1)显绿
        if isinstance(v, (int, float)):
            if v > 1.1: return 'color: #ff4444; font-weight: bold'
            if v < 0.9: return 'color: #00ff00; font-weight: bold'
        return ''

    # 使用 st.table 强制展开所有行，彻底去掉内部滚动条
    st.table(df.style.applymap(style_cells))

st.sidebar.info("💡 提示：多空比数据每分钟自动更新一次，若显示为 N/A 请检查网络。")
