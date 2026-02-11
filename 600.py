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

# ==================== 1. 配置（精准对应你的要求） ====================
APP_TOKEN = "AT_3H9akFZPvOE98cPrDydWmKM4ndgT3bVH"
USER_UID = "UID_wfbEjBobfoHNLmprN3Pi5nwWb4oM"
LOG_FILE = "resonance_logs.csv"

CRYPTO_LIST = ["BTC", "ETH", "SOL", "SUI", "RENDER", "DOGE", "XRP", "HYPE", "AAVE", "TAO", "XAG", "XAU"]
CONTRACTS = {"TAO", "XAG", "XAU"}

# 你要求的两组对比（单位：分钟 -> OKX代码）
RESONANCE_GROUPS = {
    "Group1_日内(5-15-60)": ["5m", "15m", "1h"],
    "Group2_趋势(15-60-240)": ["15m", "1h", "4h"]
}

# 需要抓取的所有去重周期
INTERVALS = sorted(list(set([tf for g in RESONANCE_GROUPS.values() for tf in g])))
BEIJING_TZ = pytz.timezone('Asia/Shanghai')

# ==================== 2. 核心函数 ====================

def save_log(entry):
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
    df['sig'] = (df['pos'] != df['pos'].shift(1)) # 信号变更点
    return df

# ==================== 3. 主程序 ====================
st.set_page_config(page_title="UT Bot 两组共振对比版", layout="wide")

if "alert_logs" not in st.session_state:
    st.session_state.alert_logs = pd.read_csv(LOG_FILE).to_dict('records') if os.path.exists(LOG_FILE) else []
if "sent_cache" not in st.session_state:
    st.session_state.sent_cache = set()

ex = ccxt.okx({'enableRateLimit': True})
sens = st.sidebar.slider("敏感度", 0.5, 3.0, 1.2)
atrp = st.sidebar.slider("ATR周期", 5, 20, 10)

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
            time.sleep(0.05)
        except: all_data[base][tf] = pd.DataFrame()

# 共振逻辑处理
rows = []
for base in CRYPTO_LIST:
    row = {"资产": base}
    for g_name, g_tfs in RESONANCE_GROUPS.items():
        # 获取该组三个周期的状态
        states = []
        for tf in g_tfs:
            df = all_data[base].get(tf, pd.DataFrame())
            states.append(df.iloc[-1]['pos'] if not df.empty else "None")
        
        # 判断是否共振
        is_res = len(set(states)) == 1 and states[0] != "None"
        res_dir = states[0] if is_res else "❌"
        row[g_name] = f"**{res_dir}**"
        
        # 核心：【共振才发】+【产生新信号才发】
        # 只要组内任何一个周期刚刚发生了信号变更，且变更后达成了全组共振，即推送
        for tf in g_tfs:
            df = all_data[base].get(tf, pd.DataFrame())
            if not df.empty and df.iloc[-1]['sig'] and is_res:
                sig_time = df.index[-1].astimezone(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')
                cache_key = f"{base}_{g_name}_{res_dir}_{sig_time}"
                
                if cache_key not in st.session_state.sent_cache:
                    new_log = {"时间": sig_time, "资产": base, "组": g_name, "共振方向": res_dir, "价格": df.iloc[-1]['Close']}
                    st.session_state.alert_logs.insert(0, new_log)
                    save_log(new_log)
                    send_wx(f"🚀{g_name}共振: {base}", f"方向: {res_dir}\n价格: {new_log['价格']}")
                    st.session_state.sent_cache.add(cache_key)

    rows.append(row)

# ==================== 4. 界面渲染 ====================
st.subheader("🔥 两组周期共振实时对比")
st.table(pd.DataFrame(rows))

st.divider()
st.subheader("📜 共振历史记录 (支持币种/组独立下载)")
if st.session_state.alert_logs:
    log_df = pd.DataFrame(st.session_state.alert_logs)
    for asset in sorted(log_df["资产"].unique()):
        with st.expander(f"📂 {asset} 历史信号"):
            asset_df = log_df[log_df["资产"] == asset]
            st.dataframe(asset_df, use_container_width=True, hide_index=True)
            # 每个币种独立的下载按钮
            csv = asset_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(f"下载 {asset} 日志", csv, f"{asset}_res.csv", "text/csv", key=f"dl_{asset}")

st.sidebar.write(f"最后更新: {datetime.now(BEIJING_TZ).strftime('%H:%M:%S')}")
time.sleep(300)
st.rerun()
