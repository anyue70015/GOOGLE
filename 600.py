import streamlit as st
import pandas as pd
import numpy as np
import pandas_ta as ta
import ccxt
import requests
from datetime import datetime, timedelta
import pytz
from streamlit_autorefresh import st_autorefresh

# ==================== 1. 核心配置 ====================
APP_TOKEN = "AT_3H9akFZPvOE98cPrDydWmKM4ndgT3bVH"
USER_UID = "UID_wfbEjBobfoHNLmprN3Pi5nwWb4oM"

CRYPTO_LIST = ["BTC", "ETH", "SOL", "SUI", "RENDER", "DOGE", "XRP", "HYPE", "AAVE", "TAO", "XAG", "XAU"]
CONTRACTS = {"TAO", "XAG", "XAU"}
# 增加了 15m 监控
INTERVALS = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]
ALERT_INTERVALS = ["15m", "30m", "1h"]

BEIJING_TZ = pytz.timezone('Asia/Shanghai')

# ==================== 2. 持久化缓存 (云端大脑) ====================
@st.cache_resource
def get_global_state():
    # sent_cache: 存储已发送的指纹
    # alert_logs: 存储今日推送明细
    return {"sent_cache": {}, "alert_logs": []}

state = get_global_state()

# ==================== 3. 功能函数 ====================
def send_wx_pusher(title, body):
    if not APP_TOKEN or not USER_UID: return
    try:
        payload = {"appToken": APP_TOKEN, "content": f"{title}\n{body}", "uids": [USER_UID]}
        requests.post("https://wxpusher.zjiecode.com/api/send/message", json=payload, timeout=5)
    except: pass

def calculate_indicators(df, sensitivity, atr_period):
    if df.empty or len(df) < 50: return pd.DataFrame()
    df.columns = [str(c).capitalize() for c in df.columns]
    df['atr'] = ta.atr(df['High'], df['Low'], df['Close'], length=atr_period)
    df = df.dropna(subset=['atr']).copy()
    n_loss = sensitivity * df['atr']
    src = df['Close']
    trail_stop = np.zeros(len(df))
    for i in range(1, len(df)):
        p = trail_stop[i-1]
        if src.iloc[i] > p and src.iloc[i-1] > p: trail_stop[i] = max(p, src.iloc[i] - n_loss.iloc[i])
        elif src.iloc[i] < p and src.iloc[i-1] < p: trail_stop[i] = min(p, src.iloc[i] + n_loss.iloc[i])
        else: trail_stop[i] = src.iloc[i] - n_loss.iloc[i] if src.iloc[i] > p else src.iloc[i] + n_loss.iloc[i]
    df['trail_stop'] = trail_stop
    df['buy'] = (df['Close'] > df['trail_stop']) & (df['Close'].shift(1) <= df['trail_stop'].shift(1))
    df['sell'] = (df['Close'] < df['trail_stop']) & (df['Close'].shift(1) >= df['trail_stop'].shift(1))
    return df

def get_confirmed_signal(df):
    """获取【已收盘】K线的信号"""
    if df.empty or len(df) < 3: return "HOLD ⚪", 0, "N/A"
    
    # 取倒数第二根 (已经走完的K线)
    confirmed_k = df.iloc[-2]
    k_time = df.index[-2].astimezone(BEIJING_TZ).strftime('%m-%d %H:%M')
    
    if confirmed_k['buy']:
        return "BUY 🟢", df.iloc[-1]['Close'], k_time
    elif confirmed_k['sell']:
        return "SELL 🔴", df.iloc[-1]['Close'], k_time
    else:
        return "HOLD ⚪", df.iloc[-1]['Close'], k_time

# ==================== 4. UI 布局 ====================
st.set_page_config(page_title="UT Bot 信号专业版", layout="wide")
st_autorefresh(interval=300 * 1000, key="auto_refresh")

st.sidebar.header("🛡️ 策略核心参数")
sensitivity = st.sidebar.slider("UT Bot 敏感度", 0.1, 5.0, 1.0, 0.1)
atr_period = st.sidebar.slider("ATR 周期", 1, 30, 10)
selected_cryptos = st.sidebar.multiselect("监控品种", CRYPTO_LIST, default=CRYPTO_LIST)

# 主看板
st.markdown("<h2 style='text-align:center;'>📈 UT Bot 信号看板 (收盘确认版)</h2>", unsafe_allow_html=True)

# --- 数据处理 ---
ex = ccxt.okx({'enableRateLimit': True})
rows = []

for base in selected_cryptos:
    sym = f"{base}/USDT:USDT" if base in CONTRACTS else f"{base}/USDT"
    row = {"资产": base}
    for tf in INTERVALS:
        try:
            bars = ex.fetch_ohlcv(sym, timeframe=tf, limit=100)
            df_raw = pd.DataFrame(bars, columns=['ts','open','high','low','close','vol'])
            df_raw['ts'] = pd.to_datetime(df_raw['ts'], unit='ms').dt.tz_localize('UTC')
            df_raw.set_index('ts', inplace=True)
            
            df = calculate_indicators(df_raw, sensitivity, atr_period)
            sig, curr_price, sig_time = get_confirmed_signal(df)
            
            # 表格显示
            row[tf] = f"<b>{sig}</b>"
            
            # --- 报警逻辑 ---
            if tf in ALERT_INTERVALS and sig != "HOLD ⚪":
                cache_key = f"{base}_{tf}"
                event_id = f"{sig}_{sig_time}" # 指纹包含：方向 + K线时间
                
                if state["sent_cache"].get(cache_key) != event_id:
                    # 触发推送
                    asset_type = "合约" if base in CONTRACTS else "现货"
                    now_str = datetime.now(BEIJING_TZ).strftime('%H:%M:%S')
                    
                    title = f"🚨 {base} ({tf}) 收盘确认: {sig}"
                    body = f"当前价格: {curr_price}\n信号K线时间: {sig_time}\n推送时间: {now_str}\n类型: {asset_type}"
                    
                    send_wx_pusher(title, body)
                    
                    # 更新缓存与日志
                    state["sent_cache"][cache_key] = event_id
                    state["alert_logs"].insert(0, {
                        "时间": now_str,
                        "资产": base,
                        "周期": tf,
                        "信号": sig,
                        "确认价格": curr_price,
                        "K线时间": sig_time
                    })
        except: row[tf] = "-"
    rows.append(row)

# ==================== 5. 看板展示 ====================
# 实时信号表格
st.subheader("📊 实时市场状态")
st.write(pd.DataFrame(rows).to_html(escape=False, index=False), unsafe_allow_html=True)

st.divider()

# 日志看板
st.subheader("📜 今日累计推送明细")
col_m1, col_m2 = st.columns(2)
col_m1.metric("今日累计推送", f"{len(state['alert_logs'])} 次")
col_m2.metric("当前监控指纹数", f"{len(state['sent_cache'])} 个")

if state["alert_logs"]:
    log_df = pd.DataFrame(state["alert_logs"])
    st.table(log_df.head(20)) # 显示最近20条
else:
    st.info("暂无变盘信号推送")

st.caption(f"系统运行中 | 自动刷新时间: {datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')}")
