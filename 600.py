import streamlit as st
import pandas as pd
import numpy as np
import pandas_ta as ta
import ccxt
import requests
from datetime import datetime
import pytz
from streamlit_autorefresh import st_autorefresh

# ==================== 1. 核心配置 ====================
APP_TOKEN = "AT_3H9akFZPvOE98cPrDydWmKM4ndgT3bVH"
USER_UID = "UID_wfbEjBobfoHNLmprN3Pi5nwWb4oM"

CRYPTO_LIST = ["BTC", "ETH", "SOL", "SUI", "RENDER", "DOGE", "XRP", "HYPE", "AAVE", "TAO", "XAG", "XAU"]
CONTRACTS = {"TAO", "XAG", "XAU"}
INTERVALS = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]
ALERT_INTERVALS = ["15m", "30m", "1h"]

# 定义共振对应关系：当前周期 -> 需要检查的上级周期
RESONANCE_MAP = {
    "15m": "1h",
    "30m": "4h",
    "1h": "4h"
}

BEIJING_TZ = pytz.timezone('Asia/Shanghai')

# ==================== 2. 核心函数 ====================

def send_wx_pusher(title, body):
    if not APP_TOKEN or not USER_UID: return
    try:
        payload = {"appToken": APP_TOKEN, "content": f"{title}\n{body}", "uids": [USER_UID]}
        requests.post("https://wxpusher.zjiecode.com/api/send/message", json=payload, timeout=5)
    except: pass

def calculate_indicators(df, sensitivity, atr_period):
    if df.empty or len(df) < 50: return pd.DataFrame()
    df.columns = [str(c).capitalize() for c in df.columns]
    
    # UT Bot 计算
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
    df['buy_signal'] = (df['Close'] > df['trail_stop']) & (df['Close'].shift(1) <= df['trail_stop'].shift(1))
    df['sell_signal'] = (df['Close'] < df['trail_stop']) & (df['Close'].shift(1) >= df['trail_stop'].shift(1))
    
    # OBV 计算
    df['obv'] = ta.obv(df['Close'], df['Volume'])
    
    # 成交量均值（前5根）
    df['vol_avg'] = df['Volume'].shift(1).rolling(window=5).mean()
    
    return df

def get_status_data(df):
    """获取该周期的当前状态 (BUY/SELL) 和最新价格"""
    if df.empty: return "N/A", 0
    latest = df.iloc[-1]
    status = "BUY" if latest['Close'] > latest['trail_stop'] else "SELL"
    return status, latest['Close']

# ==================== 3. 主程序 ====================
st.set_page_config(page_title="UT Bot Pro 增强版", layout="wide")
st_autorefresh(interval=300 * 1000, key="pro_refresh")

@st.cache_resource
def get_global_state():
    return {"sent_cache": {}, "alert_logs": []}

state = get_global_state()
ex = ccxt.okx({'enableRateLimit': True})

st.markdown("<h2 style='text-align:center;'>🚀 UT Bot 策略增强看板</h2>", unsafe_allow_html=True)

# 侧边栏参数
sensitivity = st.sidebar.slider("敏感度", 0.1, 5.0, 1.0, 0.1)
atr_period = st.sidebar.slider("ATR周期", 1, 30, 10)
selected_cryptos = st.sidebar.multiselect("品种", CRYPTO_LIST, default=CRYPTO_LIST)

rows = []
all_data = {} # 存储所有品种所有周期的DF

# 第一遍循环：抓取所有数据并计算指标
for base in selected_cryptos:
    sym = f"{base}/USDT:USDT" if base in CONTRACTS else f"{base}/USDT"
    all_data[base] = {}
    for tf in INTERVALS:
        try:
            bars = ex.fetch_ohlcv(sym, timeframe=tf, limit=100)
            df = pd.DataFrame(bars, columns=['ts','open','high','low','close','volume'])
            df['ts'] = pd.to_datetime(df['ts'], unit='ms').dt.tz_localize('UTC')
            df.set_index('ts', inplace=True)
            all_data[base][tf] = calculate_indicators(df, sensitivity, atr_period)
        except:
            all_data[base][tf] = pd.DataFrame()

# 第二遍循环：逻辑判断与行构建
for base in selected_cryptos:
    row = {"资产": base, "实时价格": "N/A"}
    
    for tf in INTERVALS:
        df = all_data[base].get(tf, pd.DataFrame())
        if df.empty:
            row[tf] = "-"
            continue
            
        latest = df.iloc[-1]
        stop_price = f"{latest['trail_stop']:.4f}".rstrip('0').rstrip('.')
        curr_price = latest['Close']
        row["实时价格"] = f"<b>{curr_price}</b>"
        
        # 基础状态显示
        if curr_price > latest['trail_stop']:
            status_html = f"<div style='color:#00ff00; font-weight:bold;'>BUY 🟢</div>"
        else:
            status_html = f"<div style='color:#ff0000; font-weight:bold;'>SELL 🔴</div>"
        row[tf] = f"{status_html}<div style='font-size:0.8em; color:#888;'>离场:{stop_price}</div>"
        
        # 信号推送逻辑
        if tf in ALERT_INTERVALS:
            sig_k = df.iloc[-2] # 确认信号看倒数第二根
            k_time = df.index[-2].astimezone(BEIJING_TZ).strftime('%m-%d %H:%M')
            
            # 基础翻转判断
            signal = "NONE"
            if sig_k['buy_signal']: signal = "BUY 🟢"
            elif sig_k['sell_signal']: signal = "SELL 🔴"
            
            if signal != "NONE":
                cache_key = f"{base}_{tf}"
                event_id = f"{signal}_{k_time}"
                
                if state["sent_cache"].get(cache_key) != event_id:
                    # --- 增强过滤逻辑 ---
                    # 1. 能量标签 (1.2倍)
                    vol_ratio = sig_k['Volume'] / sig_k['vol_avg'] if sig_k['vol_avg'] > 0 else 0
                    vol_tag = "⚡放量" if vol_ratio >= 1.2 else "☁️缩量"
                    
                    # 2. OBV方向 (当前OBV vs 前一根)
                    obv_up = df['obv'].iloc[-2] > df['obv'].iloc[-3]
                    obv_tag = "📈资金流入" if obv_up else "📉资金流出"
                    
                    # 3. 大周期共振
                    parent_tf = RESONANCE_MAP.get(tf)
                    parent_status, _ = get_status_data(all_data[base].get(parent_tf, pd.DataFrame()))
                    is_sync = (signal.startswith(parent_status))
                    sync_tag = "🔗共振" if is_sync else "⚠️逆势"
                    
                    # 发送推送
                    title = f"🚨 {base}({tf}) {signal} | {vol_tag}"
                    body = (f"价格: {curr_price}\n"
                            f"能量: {vol_ratio:.2f}倍 ({vol_tag})\n"
                            f"资金: {obv_tag}\n"
                            f"趋势: {parent_tf}级{parent_status} ({sync_tag})\n"
                            f"K线时间: {k_time}")
                    
                    send_wx_pusher(title, body)
                    state["sent_cache"][cache_key] = event_id
                    state["alert_logs"].insert(0, {
                        "时间": datetime.now(BEIJING_TZ).strftime('%H:%M:%S'),
                        "资产": base, "周期": tf, "信号": signal, 
                        "能量": f"{vol_ratio:.1f}x", "共振": sync_tag, "价格": curr_price
                    })
    rows.append(row)

# ==================== 4. UI 渲染 ====================
if rows:
    df_display = pd.DataFrame(rows)
    cols = ["资产", "实时价格"] + INTERVALS
    st.write(df_display[cols].to_html(escape=False, index=False), unsafe_allow_html=True)

st.divider()
st.subheader("📜 推送明细记录 (含放量/共振标签)")
if state["alert_logs"]:
    st.table(pd.DataFrame(state["alert_logs"]).head(15))
