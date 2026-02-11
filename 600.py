import streamlit as st
import pandas as pd
import numpy as np
import pandas_ta as ta
import ccxt
import requests
import os
from datetime import datetime, timedelta
import pytz
import time

# ==================== 1. 核心配置 ====================
APP_TOKEN = "AT_3H9akFZPvOE98cPrDydWmKM4ndgT3bVH"
USER_UID = "UID_wfbEjBobfoHNLmprN3Pi5nwWb4oM"
LOG_FILE = "trade_resonance_master.csv"

CRYPTO_LIST = ["BTC", "ETH", "SOL", "SUI", "RENDER", "DOGE", "XRP", "HYPE", "AAVE", "TAO", "XAG", "XAU"]
CONTRACTS = {"TAO", "XAG", "XAU"}

# 你要求的两组共振
RESONANCE_GROUPS = {
    "Group1_短线(5-15-60)": ["5m", "15m", "1h"],
    "Group2_趋势(15-60-240)": ["15m", "1h", "4h"]
}

# 监控的大周期列表 (不管共振，出信号就发)
MAJOR_LEVELS = ["1h", "4h", "1d"]

INTERVALS = ["5m", "15m", "1h", "4h", "1d"]
BEIJING_TZ = pytz.timezone('Asia/Shanghai')

# ==================== 2. 功能函数 ====================

def load_logs():
    if os.path.exists(LOG_FILE):
        try: return pd.read_csv(LOG_FILE).to_dict('records')
        except: return []
    return []

def save_log_to_disk(entry):
    df = pd.DataFrame([entry])
    header = not os.path.exists(LOG_FILE)
    df.to_csv(LOG_FILE, mode='a', index=False, header=header, encoding='utf-8-sig')

def send_wx(title, body):
    try:
        payload = {"appToken": APP_TOKEN, "content": f"{title}\n{body}", "uids": [USER_UID]}
        requests.post("https://wxpusher.zjiecode.com/api/send/message", json=payload, timeout=5)
    except: pass

def calculate_ut_bot(df, sensitivity, atr_period):
    if df.empty or len(df) < 50: return pd.DataFrame()
    df.columns = [str(c).capitalize() for c in df.columns]
    df['atr'] = ta.atr(df['High'], df['Low'], df['Close'], length=atr_period)
    df = df.dropna(subset=['atr']).copy()
    n_loss = sensitivity * df['atr']
    src, trail_stop = df['Close'], np.zeros(len(df))
    for i in range(1, len(df)):
        p = trail_stop[i-1]
        if src.iloc[i] > p and src.iloc[i-1] > p: trail_stop[i] = max(p, src.iloc[i] - n_loss.iloc[i])
        elif src.iloc[i] < p and src.iloc[i-1] < p: trail_stop[i] = min(p, src.iloc[i] + n_loss.iloc[i])
        else: trail_stop[i] = src.iloc[i] - n_loss.iloc[i] if src.iloc[i] > p else src.iloc[i] + n_loss.iloc[i]
    df['ts'] = trail_stop
    df['pos'] = np.where(df['Close'] > df['ts'], "BUY", "SELL")
    df['sig_change'] = (df['pos'] != df['pos'].shift(1))
    return df

# ==================== 3. 主程序 ====================
st.set_page_config(page_title="UT Bot 两组共振+大周期全控版", layout="wide")

if "alert_logs" not in st.session_state:
    st.session_state.alert_logs = load_logs()
if "sent_cache" not in st.session_state:
    st.session_state.sent_cache = {f"{l['资产']}_{l['类型']}_{l['时间'][:16]}" for l in st.session_state.alert_logs if '类型' in l}

ex = ccxt.okx({'enableRateLimit': True})
sens = st.sidebar.slider("敏感度", 0.1, 5.0, 1.2)
atrp = st.sidebar.slider("ATR周期", 1, 30, 10)

# 数据抓取
all_data = {}
for base in CRYPTO_LIST:
    sym = f"{base}-USDT-SWAP" if base in CONTRACTS else f"{base}/USDT"
    all_data[base] = {}
    for tf in INTERVALS:
        try:
            bars = ex.fetch_ohlcv(sym, timeframe=tf, limit=100)
            df = pd.DataFrame(bars, columns=['ts','open','high','low','close','volume'])
            df.set_index(pd.to_datetime(df['ts'], unit='ms').dt.tz_localize('UTC'), inplace=True)
            all_data[base][tf] = calculate_ut_bot(df, sens, atrp)
        except: all_data[base][tf] = pd.DataFrame()

# 信号处理核心逻辑
rows = []
now_str = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')

for base in CRYPTO_LIST:
    p_15m = all_data[base].get("15m", pd.DataFrame())
    price_now = p_15m.iloc[-1]['Close'] if not p_15m.empty else "N/A"
    row = {"资产": base, "实时价格": f"<b>{price_now}</b>"}

    # --- 逻辑 A: 两组共振监控 (5/15/60m) ---
    for g_name, g_tfs in RESONANCE_GROUPS.items():
        states = []
        is_data_ok = True
        for tf in g_tfs:
            df = all_data[base].get(tf, pd.DataFrame())
            if not df.empty: states.append(df.iloc[-1]['pos'])
            else: is_data_ok = False; break
        
        is_res = is_data_ok and len(set(states)) == 1
        res_dir = states[0] if is_res else "None"
        color = "#00ff00" if res_dir == "BUY" else "#ff0000" if res_dir == "SELL" else "#888"
        row[g_name] = f"<span style='color:{color};font-weight:bold;'>{res_dir}</span>"
        
        # 共振才发信息
        if is_res:
            has_new_sig = any([all_data[base][tf].iloc[-1]['sig_change'] for tf in g_tfs if not all_data[base][tf].empty])
            if has_new_sig:
                cache_key = f"{base}_{g_name}_{now_str[:16]}"
                if cache_key not in st.session_state.sent_cache:
                    log_entry = {"时间": now_str, "资产": base, "类型": g_name, "方向": res_dir, "价格": price_now}
                    st.session_state.alert_logs.insert(0, log_entry)
                    save_log_to_disk(log_entry)
                    send_wx(f"🔗共振报警({g_name})", f"资产: {base}\n方向: {res_dir}\n价格: {price_now}")
                    st.session_state.sent_cache.add(cache_key)

    # --- 逻辑 B: 大周期单周期监控 (1h以上不管共振都发) ---
    for tf in MAJOR_LEVELS:
        df = all_data[base].get(tf, pd.DataFrame())
        if not df.empty:
            curr = df.iloc[-1]
            if curr['sig_change']:
                cache_key = f"{base}_{tf}_{now_str[:16]}"
                if cache_key not in st.session_state.sent_cache:
                    log_entry = {"时间": now_str, "资产": base, "类型": f"大周期_{tf}", "方向": curr['pos'], "价格": price_now}
                    st.session_state.alert_logs.insert(0, log_entry)
                    save_log_to_disk(log_entry)
                    send_wx(f"📢大周期报警({tf})", f"资产: {base}\n方向: {curr['pos']}\n价格: {price_now}")
                    st.session_state.sent_cache.add(cache_key)
    
    rows.append(row)

# ==================== 4. 渲染界面 ====================
st.markdown("<h3 style='text-align:center;'>🚀 UT Bot 多重过滤共振系统</h3>", unsafe_allow_html=True)
st.write(pd.DataFrame(rows).to_html(escape=False, index=False), unsafe_allow_html=True)

st.divider()
st.subheader("📜 分类日志 (永久保存)")
if st.session_state.alert_logs:
    df_logs = pd.DataFrame(st.session_state.alert_logs)
    t1, t2, t3 = st.tabs(["Group1 信号", "Group2 信号", "大周期 信号"])
    
    with t1:
        d = df_logs[df_logs["类型"].str.contains("Group1")]; st.dataframe(d, use_container_width=True, hide_index=True)
    with t2:
        d = df_logs[df_logs["类型"].str.contains("Group2")]; st.dataframe(d, use_container_width=True, hide_index=True)
    with t3:
        d = df_logs[df_logs["类型"].str.contains("大周期")]; st.dataframe(d, use_container_width=True, hide_index=True)
    
    # 按币种下载逻辑
    st.write("### 📥 按资产下载历史记录")
    asset_to_dl = st.selectbox("选择资产下载 CSV", CRYPTO_LIST)
    dl_df = df_logs[df_logs["资产"] == asset_to_dl]
    st.download_button(f"下载 {asset_to_dl} 历史数据", dl_df.to_csv(index=False).encode('utf-8-sig'), f"{asset_to_dl}_full_log.csv")
else:
    st.info("等待信号中...")

time.sleep(300)
st.rerun()
