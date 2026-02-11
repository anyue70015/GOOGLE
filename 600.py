import streamlit as st
import pandas as pd
import numpy as np
import pandas_ta as ta
import ccxt
import requests
import os  # 新增：用于文件操作
from datetime import datetime, timedelta
import pytz
import time

# ==================== 1. 核心配置 ====================
APP_TOKEN = "AT_3H9akFZPvOE98cPrDydWmKM4ndgT3bVH"
USER_UID = "UID_wfbEjBobfoHNLmprN3Pi5nwWb4oM"
LOG_FILE = "trade_logs.csv"  # 关键：本地保存的文件名

CRYPTO_LIST = ["BTC", "ETH", "SOL", "SUI", "RENDER", "DOGE", "XRP", "HYPE", "AAVE", "TAO", "XAG", "XAU"]
CONTRACTS = {"TAO", "XAG", "XAU"}
INTERVALS = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]
ALERT_INTERVALS = ["15m", "30m", "1h"]

RESONANCE_GROUPS = {
    "group1": ["4h", "1h", "15m"],
    "group2": ["1h", "15m", "5m"]
}

BEIJING_TZ = pytz.timezone('Asia/Shanghai')

# ==================== 2. 持久化逻辑函数 ====================

def load_persistent_logs():
    """从硬盘读取历史日志"""
    if os.path.exists(LOG_FILE):
        try:
            return pd.read_csv(LOG_FILE).to_dict('records')
        except:
            return []
    return []

def save_log_to_disk(new_entry):
    """将新信号追加到硬盘文件"""
    df = pd.DataFrame([new_entry])
    # 如果文件不存在，写表头；如果存在，只追加内容
    header = not os.path.exists(LOG_FILE)
    df.to_csv(LOG_FILE, mode='a', index=False, header=header, encoding='utf-8-sig')

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
    trail_stop[0] = src.iloc[0] - n_loss.iloc[0]
    for i in range(1, len(df)):
        p = trail_stop[i-1]
        if src.iloc[i] > p and src.iloc[i-1] > p: trail_stop[i] = max(p, src.iloc[i] - n_loss.iloc[i])
        elif src.iloc[i] < p and src.iloc[i-1] < p: trail_stop[i] = min(p, src.iloc[i] + n_loss.iloc[i])
        else: trail_stop[i] = src.iloc[i] - n_loss.iloc[i] if src.iloc[i] > p else src.iloc[i] + n_loss.iloc[i]
    df['trail_stop'] = trail_stop
    df['buy_signal'] = (df['Close'] > df['trail_stop']) & (df['Close'].shift(1) <= df['trail_stop'].shift(1))
    df['sell_signal'] = (df['Close'] < df['trail_stop']) & (df['Close'].shift(1) >= df['trail_stop'].shift(1))
    return df

# ==================== 3. 主程序 ====================
st.set_page_config(page_title="UT Bot Pro 永久保存版", layout="wide")

# 初始化状态（增加硬盘读取）
if "alert_logs" not in st.session_state:
    st.session_state.alert_logs = load_persistent_logs()
if "sent_cache" not in st.session_state:
    st.session_state.sent_cache = {f"{log['资产']}_{log['周期']}_{log['时间']}": True for log in st.session_state.alert_logs}

ex = ccxt.okx({'enableRateLimit': True})

# 侧边栏
selected_cryptos = st.sidebar.multiselect("品种选择", CRYPTO_LIST, default=CRYPTO_LIST)
sens = st.sidebar.slider("敏感度", 0.1, 5.0, 1.0)
atrp = st.sidebar.slider("ATR周期", 1, 30, 10)
refresh_sec = st.sidebar.selectbox("自动刷新(秒)", [60, 300, 600], index=1)

# 获取行情并分析（主体逻辑保持不变）
all_data = {}
for base in selected_cryptos:
    sym = f"{base}-USDT-SWAP" if base in CONTRACTS else f"{base}/USDT"
    all_data[base] = {}
    for tf in INTERVALS:
        try:
            bars = ex.fetch_ohlcv(sym, timeframe=tf, limit=100)
            df = pd.DataFrame(bars, columns=['ts','open','high','low','close','volume'])
            df.set_index(pd.to_datetime(df['ts'], unit='ms').dt.tz_localize('UTC'), inplace=True)
            all_data[base][tf] = calculate_indicators(df, sens, atrp)
        except: all_data[base][tf] = pd.DataFrame()

# 生成看板和处理新信号
rows = []
for base in selected_cryptos:
    p_df = all_data[base].get("15m", pd.DataFrame())
    price_now = p_df.iloc[-1]['Close'] if not p_df.empty else "N/A"
    row_data = {"资产": base, "实时价格": f"<b>{price_now}</b>"}
    
    for tf in INTERVALS:
        df = all_data[base].get(tf, pd.DataFrame())
        if df.empty: row_data[tf] = "-"; continue
        
        latest = df.iloc[-1]
        color = "#00ff00" if latest['Close'] > latest['trail_stop'] else "#ff0000"
        row_data[tf] = f"<div style='color:{color};font-weight:bold;'>{'BUY 🟢' if color=='#00ff00' else 'SELL 🔴'}</div>"

        # 触发新信号
        if tf in ALERT_INTERVALS and (latest['buy_signal'] or latest['sell_signal']):
            sig_time = df.index[-1].astimezone(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')
            cache_key = f"{base}_{tf}_{sig_time}"
            
            if cache_key not in st.session_state.sent_cache:
                signal = "BUY 🟢" if latest['buy_signal'] else "SELL 🔴"
                log_entry = {"时间": sig_time, "资产": base, "周期": tf, "信号": signal, "价格": latest['Close']}
                
                # 1. 存入内存
                st.session_state.alert_logs.insert(0, log_entry)
                # 2. 存入硬盘（即使崩溃数据也在）
                save_log_to_disk(log_entry)
                # 3. 推送
                send_wx_pusher(f"{base} {tf} {signal}", f"价格: {latest['Close']}")
                st.session_state.sent_cache[cache_key] = True
    rows.append(row_data)

# ==================== 4. 渲染界面 ====================
st.write(pd.DataFrame(rows).to_html(escape=False, index=False), unsafe_allow_html=True)

st.divider()
st.subheader("📜 永久日志（已实时保存至 trade_logs.csv）")

if st.session_state.alert_logs:
    df_display = pd.DataFrame(st.session_state.alert_logs)
    for asset in sorted(df_display["资产"].unique()):
        with st.expander(f"📈 {asset}"):
            asset_df = df_display[df_display["资产"] == asset]
            for tf in sorted(asset_df["周期"].unique(), reverse=True):
                p_df = asset_df[asset_df["周期"] == tf]
                st.dataframe(p_df, use_container_width=True, hide_index=True)
                st.download_button(f"下载 {asset}_{tf}", p_df.to_csv(index=False).encode('utf-8-sig'), f"{asset}_{tf}.csv", "text/csv", key=f"dl_{asset}_{tf}_{time.time()}")

time.sleep(refresh_sec)
st.rerun()
