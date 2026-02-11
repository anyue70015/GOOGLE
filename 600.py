import streamlit as st
import pandas as pd
import numpy as np
import pandas_ta as ta
import ccxt.async_support as ccxt  # 切换为异步库
import requests
import asyncio
from datetime import datetime, timedelta
import pytz
import time

# ==================== 1. 核心配置 ====================
APP_TOKEN = "AT_3H9akFZPvOE98cPrDydWmKM4ndgT3bVH"
USER_UID = "UID_wfbEjBobfoHNLmprN3Pi5nwWb4oM"

CRYPTO_LIST = ["BTC", "ETH", "SOL", "SUI", "RENDER", "DOGE", "XRP", "HYPE", "AAVE", "TAO"]
CONTRACTS = {"TAO", "XAG", "XAU"} # TAO, XAG, XAU 走合约，其余现货
INTERVALS = ["5m", "15m", "1h", "4h", "1d"]
ALERT_INTERVALS = ["15m", "1h"]

# 定义三周期共振组
RESONANCE_GROUPS = {
    "长线组(15万目标)": ["4h", "1h", "15m"],
    "日内组(波段交易)": ["1h", "15m", "5m"]
}

BEIJING_TZ = pytz.timezone('Asia/Shanghai')

# ==================== 2. 核心逻辑函数 ====================

def send_wx_pusher(title, body):
    if not APP_TOKEN or not USER_UID: return
    try:
        payload = {"appToken": APP_TOKEN, "content": f"{title}\n{body}", "uids": [USER_UID]}
        requests.post("https://wxpusher.zjiecode.com/api/send/message", json=payload, timeout=5)
    except: pass

def calculate_indicators(df, sensitivity, atr_period):
    if df.empty or len(df) < 50: return pd.DataFrame()
    df.columns = [str(c).capitalize() for c in df.columns]
    
    # UT Bot 核心算法：ATR 动态追踪止损
    df['atr'] = ta.atr(df['High'], df['Low'], df['Close'], length=atr_period)
    df = df.dropna(subset=['atr']).copy()
    n_loss = sensitivity * df['atr']
    src = df['Close']
    trail_stop = np.zeros(len(df))
    
    for i in range(1, len(df)):
        p = trail_stop[i-1]
        if src.iloc[i] > p and src.iloc[i-1] > p: 
            trail_stop[i] = max(p, src.iloc[i] - n_loss.iloc[i])
        elif src.iloc[i] < p and src.iloc[i-1] < p: 
            trail_stop[i] = min(p, src.iloc[i] + n_loss.iloc[i])
        else: 
            trail_stop[i] = src.iloc[i] - n_loss.iloc[i] if src.iloc[i] > p else src.iloc[i] + n_loss.iloc[i]
    
    df['trail_stop'] = trail_stop
    df['status'] = np.where(df['Close'] > df['trail_stop'], "BUY", "SELL")
    df['obv'] = ta.obv(df['Close'], df['Volume'])
    df['vol_avg'] = df['Volume'].shift(1).rolling(window=5).mean()
    return df

# ==================== 3. 异步并发抓取优化 ====================

async def fetch_single_data(exchange, symbol, tf):
    try:
        bars = await exchange.fetch_ohlcv(symbol, timeframe=tf, limit=100)
        df = pd.DataFrame(bars, columns=['ts','open','high','low','close','volume'])
        df['ts'] = pd.to_datetime(df['ts'], unit='ms').dt.tz_localize('UTC')
        df.set_index('ts', inplace=True)
        return symbol, tf, df
    except Exception as e:
        return symbol, tf, pd.DataFrame()

async def get_all_data_async(symbols, intervals, sens, atrp):
    exchange = ccxt.okx({'enableRateLimit': True})
    tasks = []
    for base in symbols:
        sym = f"{base}-USDT-SWAP" if base in CONTRACTS else f"{base}/USDT"
        for tf in intervals:
            tasks.append(fetch_single_data(exchange, sym, tf))
    
    results = await asyncio.gather(*tasks)
    await exchange.close()
    
    final_data = {}
    for sym_full, tf, df in results:
        base = sym_full.split('/')[0].split('-')[0]
        if base not in final_data: final_data[base] = {}
        final_data[base][tf] = calculate_indicators(df, sens, atrp)
    return final_data

# ==================== 4. Streamlit UI 渲染 ====================

st.set_page_config(page_title="UT Bot Pro 2026 优化版", layout="wide")

# 侧边栏配置
sens = st.sidebar.slider("策略敏感度 (山寨建议1.5+)", 0.5, 3.0, 1.2)
atrp = st.sidebar.slider("ATR周期", 5, 20, 10)
refresh_rate = st.sidebar.selectbox("自动刷新频率", [60, 300, 600], index=1)

# 初始化 Session State
if "alert_logs" not in st.session_state: st.session_state.alert_logs = []
if "sent_cache" not in st.session_state: st.session_state.sent_cache = {}

# 执行异步抓取
with st.spinner('⚡ 正在同步全球行情数据...'):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    all_data = loop.run_until_complete(get_all_data_async(CRYPTO_LIST, INTERVALS, sens, atrp))

# 渲染实时看板
st.markdown("### 📊 实时多周期共振看板")
rows = []
for base in CRYPTO_LIST:
    price = all_data.get(base, {}).get("15m", pd.DataFrame())
    price_now = price.iloc[-1]['Close'] if not price.empty else "N/A"
    
    row = {"资产": base, "实时价格": f"**{price_now}**"}
    for tf in INTERVALS:
        df = all_data.get(base, {}).get(tf, pd.DataFrame())
        if df.empty:
            row[tf] = "-"
        else:
            curr = df.iloc[-1]
            color = "green" if curr['status'] == "BUY" else "red"
            row[tf] = f":{color}[{curr['status']}]"
            
            # 信号推送逻辑（三周期共振检测）
            if tf in ALERT_INTERVALS:
                for g_name, g_tfs in RESONANCE_GROUPS.items():
                    if tf in g_tfs:
                        statuses = [all_data[base][gt].iloc[-1]['status'] for gt in g_tfs if not all_data[base][gt].empty]
                        if len(statuses) == 3 and len(set(statuses)) == 1: # 三个周期方向完全一致
                            sig_key = f"{base}_{tf}_{statuses[0]}_{df.index[-1]}"
                            if sig_key not in st.session_state.sent_cache:
                                # 触发推送
                                send_wx_pusher(f"🚀 {g_name}共振: {base}", f"方向: {statuses[0]}\n价格: {price_now}\n周期: {tf}")
                                st.session_state.sent_cache[sig_key] = True
                                st.session_state.alert_logs.insert(0, {
                                    "时间": datetime.now(BEIJING_TZ).strftime("%H:%M:%S"),
                                    "资产": base, "组": g_name, "方向": statuses[0], "价格": price_now
                                })

    rows.append(row)

st.table(pd.DataFrame(rows))

# 推送日志
st.divider()
st.subheader("🔔 共振警报历史 (24h)")
if st.session_state.alert_logs:
    st.dataframe(pd.DataFrame(st.session_state.alert_logs), use_container_width=True)
else:
    st.info("目前暂无共振信号，请耐心等待 15m/1h 级别确认...")

# 自动刷新
time.sleep(refresh_rate)
st.rerun()
