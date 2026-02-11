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

# TAO, XAG, XAU 是合约，其余是现货
CRYPTO_LIST = ["BTC", "ETH", "SOL", "SUI", "RENDER", "DOGE", "XRP", "HYPE", "AAVE", "TAO", "XAG", "XAU"]
CONTRACTS = {"TAO", "XAG", "XAU"}

# 你要求的两组对比 (单位：分钟)
RESONANCE_GROUPS = {
    "Group1_日内(5-15-60)": ["5m", "15m", "1h"],
    "Group2_趋势(15-60-240)": ["15m", "1h", "4h"]
}

INTERVALS = ["5m", "15m", "1h", "4h"]
BEIJING_TZ = pytz.timezone('Asia/Shanghai')

# ==================== 2. 持久化与核心算法 ====================

def load_logs():
    if os.path.exists(LOG_FILE):
        try: return pd.read_csv(LOG_FILE).to_dict('records')
        except: return []
    return []

def save_log_to_disk(entry):
    df = pd.DataFrame([entry])
    header = not os.path.exists(LOG_FILE)
    df.to_csv(LOG_FILE, mode='a', index=False, header=header, encoding='utf-8-sig')

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

def send_wx(title, body):
    try:
        payload = {"appToken": APP_TOKEN, "content": f"{title}\n{body}", "uids": [USER_UID]}
        requests.post("https://wxpusher.zjiecode.com/api/send/message", json=payload, timeout=5)
    except: pass

# ==================== 3. 主程序逻辑 ====================
st.set_page_config(page_title="UT Bot 两组共振对比系统", layout="wide")

if "alert_logs" not in st.session_state:
    st.session_state.alert_logs = load_logs()
if "sent_cache" not in st.session_state:
    # 启动时根据历史记录填充缓存，防止重启重复发送
    st.session_state.sent_cache = {f"{l['资产']}_{l['组别']}_{l['时间'][:16]}" for l in st.session_state.alert_logs}

ex = ccxt.okx({'enableRateLimit': True})
sens = st.sidebar.slider("敏感度", 0.1, 5.0, 1.2)
atrp = st.sidebar.slider("ATR周期", 1, 30, 10)
refresh_sec = st.sidebar.selectbox("刷新频率", [60, 300, 600], index=1)

# 数据获取
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

# 核心：信号处理与共振对比
rows = []
for base in CRYPTO_LIST:
    p_15m = all_data[base].get("15m", pd.DataFrame())
    price_now = p_15m.iloc[-1]['Close'] if not p_15m.empty else "N/A"
    row = {"资产": base, "实时价格": f"<b>{price_now}</b>"}

    for g_name, g_tfs in RESONANCE_GROUPS.items():
        # 提取该组状态
        states = []
        is_data_ok = True
        for tf in g_tfs:
            df = all_data[base].get(tf, pd.DataFrame())
            if not df.empty: states.append(df.iloc[-1]['pos'])
            else: is_data_ok = False; break
        
        # 严格共振判定
        is_res = is_data_ok and len(set(states)) == 1
        res_dir = states[0] if is_res else "None"
        
        # 看板颜色
        color = "#00ff00" if res_dir == "BUY" else "#ff0000" if res_dir == "SELL" else "#888"
        row[g_name] = f"<span style='color:{color};font-weight:bold;'>{res_dir}</span>"
        
        # 发送触发逻辑：共振达成 + 至少有一个周期刚出信号
        if is_res:
            has_new_sig = any([all_data[base][tf].iloc[-1]['sig_change'] for tf in g_tfs if not all_data[base][tf].empty])
            if has_new_sig:
                sig_time = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')
                cache_key = f"{base}_{g_name}_{sig_time[:16]}"
                
                if cache_key not in st.session_state.sent_cache:
                    log_entry = {"时间": sig_time, "资产": base, "组别": g_name, "方向": res_dir, "价格": price_now}
                    st.session_state.alert_logs.insert(0, log_entry)
                    save_log_to_disk(log_entry)
                    send_wx(f"🚀{g_name}共振: {base}", f"方向: {res_dir}\n价格: {price_now}")
                    st.session_state.sent_cache.add(cache_key)
    rows.append(row)

# ==================== 4. 渲染 ====================
st.markdown("<h3 style='text-align:center;'>🚀 UT Bot 两组周期共振对比看板</h3>", unsafe_allow_html=True)
st.write(pd.DataFrame(rows).to_html(escape=False, index=False), unsafe_allow_html=True)

st.divider()
st.subheader("📜 分组共振历史日志")

if st.session_state.alert_logs:
    df_logs = pd.DataFrame(st.session_state.alert_logs)
    tab1, tab2 = st.tabs(["Group1 日内记录 (5-15-60)", "Group2 趋势记录 (15-60-240)"])
    
    with tab1:
        g1_data = df_logs[df_logs["组别"].str.contains("Group1")]
        if not g1_data.empty:
            for asset in sorted(g1_data["资产"].unique()):
                with st.expander(f"📦 {asset} G1 历史"):
                    a_df = g1_data[g1_data["资产"] == asset]
                    st.dataframe(a_df, use_container_width=True, hide_index=True)
                    st.download_button(f"导出 {asset} G1", a_df.to_csv(index=False).encode('utf-8-sig'), f"{asset}_G1.csv", "text/csv", key=f"dl_g1_{asset}")
        else: st.info("Group1 暂无信号")

    with tab2:
        g2_data = df_logs[df_logs["组别"].str.contains("Group2")]
        if not g2_data.empty:
            for asset in sorted(g2_data["资产"].unique()):
                with st.expander(f"📦 {asset} G2 历史"):
                    a_df = g2_data[g2_data["资产"] == asset]
                    st.dataframe(a_df, use_container_width=True, hide_index=True)
                    st.download_button(f"导出 {asset} G2", a_df.to_csv(index=False).encode('utf-8-sig'), f"{asset}_G2.csv", "text/csv", key=f"dl_g2_{asset}")
        else: st.info("Group2 暂无信号")
else:
    st.info("系统监控中，等待严格共振信号触发...")

st.sidebar.caption(f"最后刷新: {datetime.now(BEIJING_TZ).strftime('%H:%M:%S')}")
time.sleep(refresh_sec)
st.rerun()
