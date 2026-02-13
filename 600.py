import streamlit as st
import pandas as pd
import numpy as np
import pandas_ta as ta
import ccxt
import requests
import os
from datetime import datetime
import pytz
import time
from concurrent.futures import ThreadPoolExecutor

# ==================== 1. 核心配置 ====================
APP_TOKEN = "AT_3H9akFZPvOE98cPrDydWmKM4ndgT3bVH0"
USER_UID = "UID_wfbEjBobfoHNLmprN3Pi5nwWb4oM0"
LOG_FILE = "trade_resonance_master.csv"

# 纯现货监控名单 (已移除合约干扰，专注高价值资产)
CRYPTO_LIST = ["BTC", "ETH", "SOL", "SUI", "RENDER", "DOGE", "XRP", "AAVE", "TAO"]
BEIJING_TZ = pytz.timezone('Asia/Shanghai')

RESONANCE_GROUPS = {
    "Group1_短线(5-15-60)": ["5m", "15m", "1h"],
    "Group2_趋势(15-60-240)": ["15m", "1h", "4h"]
}

# ==================== 2. 功能函数 (增强版) ====================

def fetch_data_threaded(base, tf, ex):
    """单品种数据抓取逻辑"""
    try:
        sym = f"{base}/USDT"
        bars = ex.fetch_ohlcv(sym, timeframe=tf, limit=150)
        df = pd.DataFrame(bars, columns=['ts','open','high','low','close','volume'])
        df.set_index(pd.to_datetime(df['ts'], unit='ms').dt.tz_localize('UTC'), inplace=True)
        return tf, df
    except:
        return tf, pd.DataFrame()

def calculate_indicators(df, sens, atrp, rsi_p, m_f, m_s, m_sig, obv_p):
    """核心计算：UT Bot + 乖离率 + 动态指标"""
    if df.empty or len(df) < 50: return pd.DataFrame()
    
    # 1. UT Bot 基础逻辑
    df.columns = [str(c).capitalize() for c in df.columns]
    df['atr'] = ta.atr(df['High'], df['Low'], df['Close'], length=atrp)
    df = df.dropna(subset=['atr']).copy()
    
    n_loss = sens * df['atr']
    src = df['Close']
    trail_stop = np.zeros(len(df))
    for i in range(1, len(df)):
        p = trail_stop[i-1]
        if src.iloc[i] > p and src.iloc[i-1] > p: trail_stop[i] = max(p, src.iloc[i] - n_loss.iloc[i])
        elif src.iloc[i] < p and src.iloc[i-1] < p: trail_stop[i] = min(p, src.iloc[i] + n_loss.iloc[i])
        else: trail_stop[i] = src.iloc[i] - n_loss.iloc[i] if src.iloc[i] > p else src.iloc[i] + n_loss.iloc[i]
    
    df['ts'] = trail_stop
    df['pos'] = np.where(df['Close'] > df['ts'], "BUY", "SELL")
    
    # 2. 【老兵核心】乖离率判定 (防止追高)
    # 计算当前价偏离支撑线(ts)的百分比
    df['bias'] = (df['Close'] - df['ts']).abs() / df['ts'] * 100
    
    # 3. 辅助指标
    df['rsi'] = ta.rsi(df['Close'], length=rsi_p)
    macd = ta.macd(df['Close'], fast=m_f, slow=m_s, signal=m_sig)
    df['macd_hist'] = macd.iloc[:, 1]
    df['obv'] = ta.obv(df['Close'], df['Volume'])
    df['obv_sma'] = ta.sma(df['obv'], length=obv_p)
    
    return df

def send_wx(title, body):
    payload = {"appToken": APP_TOKEN, "content": f"{title}\n{body}", "uids": [USER_UID]}
    try: requests.post("https://wxpusher.zjiecode.com/api/send/message", json=payload, timeout=5)
    except: pass

# ==================== 3. Streamlit UI ====================
st.set_page_config(page_title="UT Bot 终极版", layout="wide")
st.sidebar.header("🛡️ 老兵风控参数")

sens = st.sidebar.slider("UT敏感度", 0.5, 4.0, 1.2)
max_bias = st.sidebar.slider("🔥 最大允许追高乖离(%)", 0.5, 5.0, 1.8, 0.1)
vol_mult = st.sidebar.slider("成交量放大倍数", 1.0, 3.0, 1.2)

# 初始化 session
if "alert_logs" not in st.session_state: st.session_state.alert_logs = []
if "positions" not in st.session_state: st.session_state.positions = {}

ex = ccxt.binance({'enableRateLimit': True}) # 使用币安现货接口

# ==================== 4. 数据处理循环 ====================
now_str = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')
rows = []

for base in CRYPTO_LIST:
    # 多线程抓取不同周期
    symbol_data = {}
    with ThreadPoolExecutor(max_workers=7) as executor:
        futures = [executor.submit(fetch_data_threaded, base, tf, ex) for tf in ["5m", "15m", "1h", "4h", "1d"]]
        for f in futures:
            tf, df = f.result()
            symbol_data[tf] = calculate_indicators(df, sens, 10, 14, 12, 26, 9, 20)

    if "15m" not in symbol_data or symbol_data["15m"].empty: continue
    
    curr_price = symbol_data["15m"].iloc[-1]['Close']
    row = {"资产": base, "实时价格": f"<b>{curr_price}</b>"}
    
    # 检查共振
    for g_name, g_tfs in RESONANCE_GROUPS.items():
        try:
            # 基础共振判断
            tf_data = [symbol_data[tf] for tf in g_tfs if not symbol_data[tf].empty]
            if len(tf_data) < 3: continue
            
            last_rows = [d.iloc[-1] for d in tf_data]
            directions = [r['pos'] for r in last_rows]
            
            # 1. 基础方向共振
            if len(set(directions)) == 1:
                direction = directions[0]
                
                # 2. 【核心过滤】乖离率校验 (取最小周期)
                bias_val = last_rows[0]['bias']
                bias_ok = bias_val <= max_bias
                
                # 3. 指标二次确认
                rsi_val = last_rows[0]['rsi']
                rsi_ok = (rsi_val > 50 if direction == "BUY" else rsi_val < 50)
                
                # 触发信号
                if bias_ok and rsi_ok:
                    cache_key = f"{base}_{g_name}_{direction}_{now_str[:16]}"
                    if cache_key not in [l.get('key') for l in st.session_state.alert_logs]:
                        msg = f"信号: {direction}\n价格: {curr_price}\n乖离: {bias_val:.2f}%"
                        st.session_state.alert_logs.insert(0, {"时间": now_str, "资产": base, "类型": g_name, "方向": direction, "价格": curr_price, "key": cache_key})
                        send_wx(f"🚀 {base} {g_name} 共振", msg)
                        st.session_state.positions[base] = {"entry": curr_price, "dir": direction, "ts": last_rows[0]['ts']}

            row[g_name] = f"<span style='color:{('#00ff00' if directions[0]=='BUY' else '#ff0000')}'>{directions[0]}</span>"
        except:
            row[g_name] = "ERR"

    rows.append(row)

# ==================== 5. 渲染 ====================
st.markdown(f"### 🎯 汰弱留强 · 现货共振看板 ({now_str})")
st.write(pd.DataFrame(rows).to_html(escape=False, index=False), unsafe_allow_html=True)

if st.session_state.alert_logs:
    st.divider()
    st.subheader("📜 实时监控日志 (已启用乖离率过滤)")
    st.table(pd.DataFrame(st.session_state.alert_logs).drop(columns=['key']).head(10))

time.sleep(60)
st.rerun()
