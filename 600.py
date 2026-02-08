import streamlit as st
import pandas as pd
import numpy as np
import pandas_ta as ta
import ccxt
import requests
from datetime import datetime
import pytz
from streamlit_autorefresh import st_autorefresh
import streamlit.components.v1 as components

# ==================== 1. 核心配置 ====================
APP_TOKEN = "AT_3H9akFZPvOE98cPrDydWmKM4ndgT3bVH"
USER_UID = "UID_wfbEjBobfoHNLmprN3Pi5nwWb4oM"

CRYPTO_LIST = ["BTC", "ETH", "SOL", "SUI", "RENDER", "DOGE", "XRP", "HYPE", "AAVE", "TAO", "XAG", "XAU"]
CONTRACTS = {"TAO", "XAG", "XAU"}
INTERVALS = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]

# ==================== 2. 函数定义 ====================
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

def get_signal_data(df):
    """获取最新状态"""
    if df.empty or len(df) < 2: return "HOLD ⚪", 0, "N/A"
    
    # 判定当前信号
    buys = df[df['buy']]
    sells = df[df['sell']]
    last_buy_time = buys.index[-1] if not buys.empty else None
    last_sell_time = sells.index[-1] if not sells.empty else None

    if last_buy_time and (not last_sell_time or last_buy_time > last_sell_time):
        sig = "BUY 🟢"
        sig_time = last_buy_time.strftime('%Y%m%d%H%M')
    elif last_sell_time and (not last_buy_time or last_sell_time > last_buy_time):
        sig = "SELL 🔴"
        sig_time = last_sell_time.strftime('%Y%m%d%H%M')
    else:
        sig = "HOLD ⚪"
        sig_time = "0"
        
    return sig, df.iloc[-1]['Close'], sig_time

# ==================== 3. 核心：防止重复发送的内存锁 ====================
# 使用 @st.cache_resource 确保即便页面刷新，这个字典也不会被清空
@st.cache_resource
def get_sent_cache():
    return {} # 格式: { "BTC_30m": "SELL_202602081230" }

sent_cache = get_sent_cache()

# ==================== 4. UI 界面 ====================
st.set_page_config(page_title="UT Bot 零骚扰版", layout="wide")
st_autorefresh(interval=300 * 1000, key="auto_refresh")

st.sidebar.header("🛡️ 策略参数")
sensitivity = st.sidebar.slider("敏感度", 0.1, 5.0, 1.0, 0.1)
atr_period = st.sidebar.slider("ATR周期", 1, 30, 10)
selected_cryptos = st.sidebar.multiselect("品种", CRYPTO_LIST, default=CRYPTO_LIST)

st.markdown(f"### UT Bot 实时看板 (监控中: {len(selected_cryptos)} 个品种)")

# ==================== 5. 主逻辑 ====================
ex = ccxt.okx({'enableRateLimit': True})
rows = []

for base in selected_cryptos:
    sym = f"{base}/USDT:USDT" if base in CONTRACTS else f"{base}/USDT"
    row = {"资产": base}
    
    for tf in INTERVALS:
        try:
            bars = ex.fetch_ohlcv(sym, timeframe=tf, limit=100)
            df_raw = pd.DataFrame(bars, columns=['ts','open','high','low','close','vol'])
            df_raw['ts'] = pd.to_datetime(df_raw['ts'], unit='ms')
            df_raw.set_index('ts', inplace=True)
            
            df = calculate_indicators(df_raw, sensitivity, atr_period)
            sig, price, sig_time = get_signal_data(df)
            row[tf] = f"<b>{sig}</b>"
            
            # --- 彻底修复：报警防刷逻辑 ---
            if tf in ["30m", "1h"] and sig != "HOLD ⚪":
                cache_key = f"{base}_{tf}"
                # 唯一标识：方向 + 信号触发的时间戳
                # 只有当 (方向变了) 或者 (时间戳变了) 才会触发
                current_event_id = f"{sig}_{sig_time}"
                
                if sent_cache.get(cache_key) != current_event_id:
                    asset_type = "合约" if base in CONTRACTS else "现货"
                    send_wx_pusher(
                        f"🚨 {base} ({tf}) {sig}", 
                        f"价格: {price}\n时间: {sig_time}\n类型: {asset_type}\n状态: 信号确认"
                    )
                    # 写入全局缓存
                    sent_cache[cache_key] = current_event_id
                    st.toast(f"已推送 {base} {tf} 信号", icon="✉️")
                    
        except Exception as e:
            row[tf] = "-"
    rows.append(row)

st.write(pd.DataFrame(rows).to_html(escape=False, index=False), unsafe_allow_html=True)
st.caption(f"全局缓存中的信号数: {len(sent_cache)} | 刷新时间: {datetime.now().strftime('%H:%M:%S')}")
