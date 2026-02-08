import streamlit as st
import pandas as pd
import numpy as np
import pandas_ta as ta
import ccxt
import requests
from datetime import datetime
import pytz
import time

# ==================== 1. 核心配置 ====================
APP_TOKEN = "AT_3H9akFZPvOE98cPrDydWmKM4ndgT3bVH"
USER_UID = "UID_wfbEjBobfoHNLmprN3Pi5nwWb4oM"

# 根据你的记录：TAO, XAG, XAU 是合约，其余是现货
CRYPTO_LIST = ["BTC", "ETH", "SOL", "SUI", "RENDER", "DOGE", "XRP", "HYPE", "AAVE", "TAO", "XAG", "XAU"]
CONTRACTS = {"TAO", "XAG", "XAU"}
INTERVALS = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]
ALERT_INTERVALS = ["15m", "30m", "1h"]

RESONANCE_MAP = {"15m": "1h", "30m": "4h", "1h": "4h"}
BEIJING_TZ = pytz.timezone('Asia/Shanghai')

# ==================== 2. 逻辑函数 ====================

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
    
    # OBV & 成交量均值
    df['obv'] = ta.obv(df['Close'], df['Volume'])
    df['vol_avg'] = df['Volume'].shift(1).rolling(window=5).mean()
    return df

# ==================== 3. 主程序 ====================
st.set_page_config(page_title="UT Bot Pro 最终修正版", layout="wide")

# 原生刷新
if "last_update" not in st.session_state:
    st.session_state.last_update = time.time()

refresh_sec = 300 
time_passed = time.time() - st.session_state.last_update
if time_passed > refresh_sec:
    st.session_state.last_update = time.time()
    st.rerun()

st.sidebar.caption(f"🔄 刷新倒计时: {max(0, int(refresh_sec - time_passed))}s")

@st.cache_resource
def get_global_state():
    return {"sent_cache": {}, "alert_logs": []}

state = get_global_state()
ex = ccxt.okx({'enableRateLimit': True})

# 修正语法错误：将赋值提出来
selected_cryptos = st.sidebar.multiselect("品种选择", CRYPTO_LIST, default=CRYPTO_LIST)
sens = st.sidebar.slider("敏感度", 0.1, 5.0, 1.0)
atrp = st.sidebar.slider("ATR周期", 1, 30, 10)

# 抓取数据
all_data = {}
for base in selected_cryptos:
    sym = f"{base}/USDT:USDT" if base in CONTRACTS else f"{base}/USDT"
    all_data[base] = {}
    for tf in INTERVALS:
        try:
            bars = ex.fetch_ohlcv(sym, timeframe=tf, limit=100)
            df = pd.DataFrame(bars, columns=['ts','open','high','low','close','volume'])
            df['ts'] = pd.to_datetime(df['ts'], unit='ms').dt.tz_localize('UTC')
            df.set_index('ts', inplace=True)
            all_data[base][tf] = calculate_indicators(df, sens, atrp)
        except: 
            all_data[base][tf] = pd.DataFrame()

# 构建展示与推送逻辑
rows = []
for base in selected_cryptos:
    # 确定当前实时价格
    price_now = "N/A"
    for t_val in ["1m", "5m", "15m"]:
        if not all_data[base][t_val].empty:
            price_now = all_data[base][t_val].iloc[-1]['Close']
            break
            
    row_data = {"资产": base, "实时价格": f"<b>{price_now}</b>"}
    
    for tf in INTERVALS:
        df = all_data[base][tf]
        if df.empty:
            row_data[tf] = "-"
            continue
        
        latest = df.iloc[-1]
        color = "#00ff00" if latest['Close'] > latest['trail_stop'] else "#ff0000"
        status_text = "BUY 🟢" if color == "#00ff00" else "SELL 🔴"
        row_data[tf] = f"<div style='color:{color}; font-weight:bold;'>{status_text}</div><div style='font-size:0.8em; color:#888;'>止损:{latest['trail_stop']:.2f}</div>"
        
        # 信号判断
        if tf in ALERT_INTERVALS:
            sig_k = df.iloc[-2]
            signal = "NONE"
            if sig_k['buy_signal']: signal = "BUY 🟢"
            elif sig_k['sell_signal']: signal = "SELL 🔴"
            
            if signal != "NONE":
                sig_time = df.index[-2].astimezone(BEIJING_TZ).strftime('%m-%d %H:%M')
                cache_key = f"{base}_{tf}_{sig_time}"
                
                if cache_key not in state["sent_cache"]:
                    # 计算过滤标签
                    vol_r = sig_k['Volume'] / sig_k['vol_avg'] if sig_k['vol_avg'] > 0 else 1.0
                    vol_tag = "⚡放量" if vol_r >= 1.2 else "☁️缩量"
                    obv_up = df['obv'].iloc[-2] > df['obv'].iloc[-3]
                    obv_tag = "📈流入" if obv_up else "📉流出"
                    
                    # 共振判断
                    p_tf = RESONANCE_MAP.get(tf)
                    p_df = all_data[base].get(p_tf, pd.DataFrame())
                    p_status = "BUY" if (not p_df.empty and p_df.iloc[-1]['Close'] > p_df.iloc[-1]['trail_stop']) else "SELL"
                    sync_tag = "🔗共振" if signal.startswith(p_status) else "⚠️逆势"
                    
                    # 写入日志
                    state["alert_logs"].insert(0, {
                        "时间": datetime.now(BEIJING_TZ).strftime('%H:%M:%S'),
                        "资产": base, "周期": tf, "信号": signal,
                        "能量": f"{vol_r:.1f}x {vol_tag}",
                        "OBV": obv_tag, "共振": sync_tag,
                        "信号价格": sig_k['Close'],
                        "信号时间": sig_time,
                        "最新价格": price_now
                    })
                    state["sent_cache"][cache_key] = True
                    send_wx_pusher(f"{base}({tf}){signal}|{vol_tag}", f"价格:{sig_k['Close']}\n{sync_tag}|{obv_tag}")

    rows.append(row_data)

# ==================== 4. 渲染 ====================
st.markdown("<h3 style='text-align:center;'>🚀 UT Bot 多重过滤系统</h3>", unsafe_allow_html=True)
if rows:
    disp_df = pd.DataFrame(rows)
    st.write(disp_df[["资产", "实时价格"] + INTERVALS].to_html(escape=False, index=False), unsafe_allow_html=True)

st.divider()
st.subheader("📜 推送日志（已修复 OBV/时间 显示）")
if state["alert_logs"]:
    log_show = pd.DataFrame(state["alert_logs"])
    # 明确指定列顺序
    st.table(log_show[["时间", "资产", "周期", "信号", "能量", "OBV", "共振", "信号价格", "信号时间", "最新价格"]])
