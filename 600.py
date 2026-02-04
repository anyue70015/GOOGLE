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

# --- 1. 基础配置与北京时间 ---
st.set_page_config(page_title="UT Bot 实时科学看板", layout="wide")
BEIJING_TZ = pytz.timezone('Asia/Shanghai')

def get_now_beijing():
    return datetime.now(BEIJING_TZ)

# --- 2. 侧边栏配置 ---
st.sidebar.header("🛡️ 系统设置")
sct_key = st.sidebar.text_input("Server酱 SendKey (微信预警)", type="password")

st.sidebar.subheader("策略参数")
sensitivity = st.sidebar.slider("敏感度 (Multiplier)", 1.0, 5.0, 2.0, 0.1)
atr_period = st.sidebar.slider("ATR 周期", 1, 30, 10)

# 币种配置
CRYPTO_LIST = ["BTC", "ETH", "SOL", "SUI", "RENDER", "DOGE", "XRP", "UNI", "HYPE", "AAVE", "TAO", "XAG", "XAU"]
selected_cryptos = st.sidebar.multiselect("加密货币 (OKX)", CRYPTO_LIST, default=CRYPTO_LIST)

# 股票上传
st.sidebar.subheader("股票/外盘配置")
uploaded_file = st.sidebar.file_uploader("上传 TXT 列表", type="txt")
custom_stocks = []
if uploaded_file:
    custom_stocks = [line.strip() for line in uploaded_file.read().decode("utf-8").splitlines() if line.strip()]

selected_intervals = ["15m", "30m", "1h", "4h", "1d"]
# 调快自动刷新频率，建议 1 分钟刷一次，这样倒计时才会动态跳动
st_autorefresh(interval=1 * 60 * 1000, key="datarefresh")

# --- 3. 核心算法 ---
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
    """
    精确计算信号持续时间，超过30分钟则隐藏强力警报显示
    """
    if df.empty or len(df) < 2: return "N/A", 0, ""
    
    last_row = df.iloc[-1]
    curr_p = last_row['Close']
    
    # 获取最近一次信号的时间戳 (转换为北京时间对比)
    buys = df[df['buy'] == True]
    sells = df[df['sell'] == True]
    
    l_b_idx = buys.index[-1] if not buys.empty else None
    l_s_idx = sells.index[-1] if not sells.empty else None
    
    now_bj = get_now_beijing()
    
    # 辅助函数：计算信号到现在过了多少分钟
    def get_duration_mins(signal_time):
        # 确保信号时间是带有时区的
        if signal_time.tzinfo is None:
            signal_time = signal_time.replace(tzinfo=pytz.utc).astimezone(BEIJING_TZ)
        else:
            signal_time = signal_time.astimezone(BEIJING_TZ)
        diff = now_bj - signal_time
        return int(diff.total_seconds() / 60)

    # 判断当前处于什么趋势
    if (l_b_idx is not None and l_s_idx is None) or (l_b_idx is not None and l_b_idx > l_s_idx):
        # 处于买入趋势
        duration = get_duration_mins(l_b_idx)
        # 如果报警超过 30 分钟，不再显示 🚀 BUY，恢复为 多 🟢
        if duration <= 30:
            status = f"🚀 BUY ({duration}m)"
            alert_type = "BUY" if duration == 0 else "" # 仅在触发那一刻发微信
        else:
            status = "多 🟢"
            alert_type = ""
        return status, curr_p, alert_type
    elif (l_s_idx is not None and l_b_idx is None) or (l_s_idx is not None and l_s_idx > l_b_idx):
        # 处于卖出趋势
        duration = get_duration_mins(l_s_idx)
        if duration <= 30:
            status = f"📉 SELL ({duration}m)"
            alert_type = "SELL" if duration == 0 else ""
        else:
            status = "空 🔴"
            alert_type = ""
        return status, curr_p, alert_type
    
    return "维持", curr_p, ""

def get_okx_ls_ratio(symbol):
    try:
        base = symbol.split('/')[0]
        url = f"https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio?instId={base}-USDT"
        res = requests.get(url, timeout=5).json()
        if res['code'] == '0': return res['data'][0]['ratio']
    except: pass
    return "N/A"

def send_wechat(t, c):
    if sct_key: 
        try: requests.post(f"https://sctapi.ftqq.com/{sct_key}.send", data={"title":t, "desp":c})
        except: pass

# --- 4. 数据获取 ---
def fetch_data():
    exchange = ccxt.okx()
    results = []
    CONTRACT_LIST = ["TAO", "XAG", "XAU"] 

    for base in selected_cryptos:
        is_contract = base in CONTRACT_LIST
        sym = f"{base}/USDT:USDT" if is_contract else f"{base}/USDT"
        ls_ratio = get_okx_ls_ratio(base)
        row = {"资产": base, "来源": "合约" if is_contract else "现货", "多空比": ls_ratio}
        lp = 0
        for tf in selected_intervals:
            try:
                # 获取数据，确保 Index 是 Datetime 类型方便计算
                bars = exchange.fetch_ohlcv(sym, timeframe=tf, limit=150)
                df = pd.DataFrame(bars, columns=['Time','Open','High','Low','Close','Volume'])
                df['Time'] = pd.to_datetime(df['Time'], unit='ms')
                df.set_index('Time', inplace=True)
                
                df = calculate_ut_bot(df)
                status, price, alert = get_signal_info(df, tf)
                row[tf] = status
                if price > 0: lp = price
                # 微信仅在 duration 为 0 的那一刻发一次
                if alert: send_wechat(f"UT信号: {base} {tf}", f"方向: {alert}\n价格: {price}\n多空比: {ls_ratio}")
            except: row[tf] = "N/A"
        row["现价"] = f"{lp:.4f}"
        results.append(row)

    # 股票/金银逻辑
    yf_map = {"15m":"15m","30m":"30m","1h":"60m","4h":"60m","1d":"1d"}
    for sym in custom_stocks:
        row = {"资产": sym, "来源": "Yahoo", "多空比": "--"}
        lp = 0
        for tf in selected_intervals:
            try:
                data = yf.download(sym, period="5d" if "m" in tf else "60d", interval=yf_map[tf], progress=False)
                if data.empty: row[tf] = "休市"; continue
                df = calculate_ut_bot(data.copy())
                df.columns = df.columns.get_level_values(0) if isinstance(df.columns, pd.MultiIndex) else df.columns
                status, price, _ = get_signal_info(df, tf)
                row[tf] = status
                if price > 0: lp = price
            except: row[tf] = "N/A"
        row["现价"] = f"{lp:.2f}"
        results.append(row)
    return pd.DataFrame(results)

# --- 5. 页面展示 ---
st.markdown("## 🛡️ UT Bot 实时监控 (30分钟报警消失模式)")
c1, c2 = st.columns([2, 1])
now = get_now_beijing()
c1.write(f"🕒 当前北京时间: {now.strftime('%H:%M:%S')}")

# 手动同步或自动同步
if 'data_cache' not in st.session_state or st.sidebar.button("🔄 立即同步行情"):
    st.session_state.data_cache = fetch_data()

df = st.session_state.data_cache
if not df.empty:
    # 进度条
    all_s = df[selected_intervals].values.flatten()
    bulls = sum(1 for x in all_status if "多" in str(x) or "BUY" in str(x))
    total = len([x for x in all_s if x not in ["N/A", "休市"]])
    ratio = bulls/total if total > 0 else 0
    st.progress(ratio, text=f"市场多头占比: {ratio:.1%}")

    def style_c(val):
        if 'BUY' in str(val): return 'background-color: #00ff0033; color: #00ff00; font-weight: bold; border-radius: 5px'
        if 'SELL' in str(val): return 'background-color: #ff000033; color: #ff0000; font-weight: bold; border-radius: 5px'
        if '🟢' in str(val): return 'color: #28a745'
        if '🔴' in str(val): return 'color: #dc3545'
        return ''

    st.dataframe(df.style.applymap(style_c, subset=selected_intervals), use_container_width=True)

st.sidebar.write(f"💡 自动刷新已设为 1 分钟/次")
