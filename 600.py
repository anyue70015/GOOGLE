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

# 资产列表
CRYPTO_LIST = ["BTC", "ETH", "SOL", "SUI", "RENDER", "DOGE", "XRP", "AAVE", "TAO", "HYPE"]
BEIJING_TZ = pytz.timezone('Asia/Shanghai')

RESONANCE_GROUPS = {
    "Group1_短线(5-15-60)": ["5m", "15m", "1h"],
    "Group2_趋势(15-60-240)": ["15m", "1h", "4h"]
}

# ==================== 2. 防卡死功能函数 ====================

def fetch_data_safe(base, tf, ex):
    """带异常处理的数据抓取"""
    try:
        # 使用统一格式，减少解析错误
        sym = f"{base}/USDT"
        bars = ex.fetch_ohlcv(sym, timeframe=tf, limit=100)
        if not bars: return tf, pd.DataFrame()
        df = pd.DataFrame(bars, columns=['ts','open','high','low','close','volume'])
        df['ts'] = pd.to_datetime(df['ts'], unit='ms').dt.tz_localize('UTC')
        df.set_index('ts', inplace=True)
        return tf, df
    except Exception as e:
        return tf, pd.DataFrame()

def calculate_ut_bot_pro(df, sens, atrp=10):
    """带乖离率计算的 UT Bot"""
    if df.empty or len(df) < 50: return pd.DataFrame()
    
    # 统一列名
    df.columns = [str(c).capitalize() for c in df.columns]
    
    # 计算 ATR 和 Trail Stop
    df['atr'] = ta.atr(df['High'], df['Low'], df['Close'], length=atrp)
    df = df.dropna(subset=['atr']).copy()
    
    n_loss = sens * df['atr']
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
    
    df['ts'] = trail_stop
    df['pos'] = np.where(df['Close'] > df['ts'], "BUY", "SELL")
    df['bias'] = (df['Close'] - df['ts']).abs() / df['ts'] * 100
    df['rsi'] = ta.rsi(df['Close'], length=14)
    
    return df

# ==================== 3. 主程序 ====================
st.set_page_config(page_title="UT Bot 实战看板", layout="wide")

# 初始化缓存，防止由于刷新导致的记录消失
if "alert_logs" not in st.session_state: st.session_state.alert_logs = []

st.sidebar.title("🛠️ 参数设置")
sens = st.sidebar.slider("敏感度", 0.1, 5.0, 1.2)
max_bias = st.sidebar.slider("最大允许乖离(%)", 0.5, 5.0, 1.8)

# 交易所初始化
ex = ccxt.binance({'enableRateLimit': True})

now_str = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')
st.markdown(f"### 🚀 多重共振实时监控 ({now_str})")

rows = []

# --- 数据抓取与计算 ---
with st.spinner('正在同步全球交易所数据...'):
    for base in CRYPTO_LIST:
        symbol_results = {}
        # 为每个币种开启多线程抓取所有周期，解决卡顿
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_tf = {executor.submit(fetch_data_safe, base, tf, ex): tf for tf in ["5m", "15m", "1h", "4h"]}
            for future in future_to_tf:
                tf, df = future.result()
                symbol_results[tf] = calculate_ut_bot_pro(df, sens)

        # 构建展示行
        p_15m = symbol_results.get("15m", pd.DataFrame())
        price_now = p_15m.iloc[-1]['Close'] if not p_15m.empty else "N/A"
        
        row = {"资产": base, "当前价格": price_now}
        
        # 判断共振
        for g_name, g_tfs in RESONANCE_GROUPS.items():
            try:
                states = [symbol_results[tf].iloc[-1]['pos'] for tf in g_tfs if not symbol_results[tf].empty]
                if len(states) == 3 and len(set(states)) == 1:
                    direction = states[0]
                    color = "green" if direction == "BUY" else "red"
                    
                    # 检查乖离率（防追高）
                    curr_bias = symbol_results[g_tfs[0]].iloc[-1]['bias']
                    if curr_bias > max_bias:
                        row[g_name] = f"⚠️ <span style='color:{color}'>{direction} (过热)</span>"
                    else:
                        row[g_name] = f"✅ <span style='color:{color}; font-weight:bold;'>{direction}</span>"
                        # 信号记录与发送（此处可加去重逻辑）
                else:
                    row[g_name] = "⏳ 扫描中"
            except:
                row[g_name] = "❌ 数据缺失"
        
        rows.append(row)

# --- 渲染表格 ---
if rows:
    df_display = pd.DataFrame(rows)
    st.write(df_display.to_html(escape=False, index=False), unsafe_allow_html=True)
else:
    st.error("无法获取数据，请检查网络连接或API限制")

# --- 日志显示 ---
st.divider()
st.subheader("📜 历史信号日志")
if st.session_state.alert_logs:
    st.table(pd.DataFrame(st.session_state.alert_logs).head(10))
else:
    st.info("当前暂无触发信号，系统正在持续监控...")

# 每60秒自动刷新
time.sleep(60)
st.rerun()
