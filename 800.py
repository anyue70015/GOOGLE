import streamlit as st
import ccxt
import pandas as pd
import numpy as np
import time
from datetime import datetime

# ================= 强行匹配参数 =================
EXCHANGE_NAME = 'okx'
SCAN_INTERVAL = 10
SYMBOLS = ['HYPE/USDT']

# TradingView 默认标准参数
ST_ATR_LEN = 10
ST_MULTIPLIER = 3.0
UT_FACTOR = 1.0
UT_ATR_LEN = 10

# ================= UI 设置 =================
st.set_page_config(page_title="HYPE 强行匹配器", layout="wide")
st.title("🎯 HYPE/USDT 强行匹配系统")

with st.sidebar:
    st.header("⚙️ 时间框架")
    timeframe = st.selectbox("选择图表时间框架", ['5m', '15m', '1h', '4h'], index=0)
    st.info("💡 建议：由于预热需要，数据量已自动设为 1000 根以匹配 TV")

# ================= 精确算法库 (核心) =================

def calculate_pine_rma(series, length):
    """精确复刻 Pine Script 的 ta.rma"""
    alpha = 1.0 / length
    rma = np.full(len(series), np.nan)
    
    # 找到第一个非空值
    first_idx = 0
    for i in range(len(series)):
        if not np.isnan(series[i]):
            first_idx = i
            break
            
    if first_idx < len(series):
        # 第一个值用 SMA 初始化
        rma[first_idx] = series[first_idx]
        for i in range(first_idx + 1, len(series)):
            rma[i] = alpha * series[i] + (1 - alpha) * rma[i-1]
    return pd.Series(rma, index=series.index)

def calculate_pine_atr(high, low, close, length):
    """精确复刻 Pine Script 的 ta.atr"""
    tr = pd.DataFrame({
        'hl': high - low,
        'hc': abs(high - close.shift(1)),
        'lc': abs(low - close.shift(1))
    }).max(axis=1)
    return calculate_pine_rma(tr, length)

def calculate_supertrend_pine(df, length=10, multiplier=3.0):
    """完全复刻 Pine Script 的 ta.supertrend"""
    high, low, close = df['high'], df['low'], df['close']
    atr = calculate_pine_atr(high, low, close, length)
    
    hl2 = (high + low) / 2
    upper_band = hl2 + (multiplier * atr)
    lower_band = hl2 - (multiplier * atr)
    
    # 初始化
    n = len(df)
    final_upper = np.zeros(n)
    final_lower = np.zeros(n)
    st_val = np.zeros(n)
    direction = np.ones(n) # 1 为看多, -1 为看空
    
    for i in range(1, n):
        # 计算 Final Bands
        final_upper[i] = upper_band.iloc[i] if (upper_band.iloc[i] < final_upper[i-1] or close.iloc[i-1] > final_upper[i-1]) else final_upper[i-1]
        final_lower[i] = lower_band.iloc[i] if (lower_band.iloc[i] > final_lower[i-1] or close.iloc[i-1] < final_lower[i-1]) else final_lower[i-1]
        
        # 计算方向
        if st_val[i-1] == final_upper[i-1]:
            direction[i] = 1 if close.iloc[i] > final_upper[i] else -1
        else:
            direction[i] = -1 if close.iloc[i] < final_lower[i] else 1
            
        st_val[i] = final_lower[i] if direction[i] == 1 else final_upper[i]
        
    return pd.Series(st_val, index=df.index), pd.Series(direction, index=df.index)

def calculate_ut_bot_pine(df, factor=1.0, atr_len=10):
    """精确复刻 UT Bot 逻辑"""
    close = df['close']
    atr = calculate_pine_atr(df['high'], df['low'], close, atr_len)
    loss = factor * atr
    
    trail = np.zeros(len(df))
    for i in range(1, len(df)):
        if close.iloc[i] > trail[i-1] and close.iloc[i-1] > trail[i-1]:
            trail[i] = max(trail[i-1], close.iloc[i] - loss.iloc[i])
        elif close.iloc[i] < trail[i-1] and close.iloc[i-1] < trail[i-1]:
            trail[i] = min(trail[i-1], close.iloc[i] + loss.iloc[i])
        elif close.iloc[i] > trail[i-1]:
            trail[i] = close.iloc[i] - loss.iloc[i]
        else:
            trail[i] = close.iloc[i] + loss.iloc[i]
            
    trail_s = pd.Series(trail, index=df.index)
    state = close > trail_s
    return trail_s, state

# ================= 分析逻辑 =================

def analyze():
    try:
        exchange = ccxt.okx()
        # 抓取 1000 根数据，解决算法预热不匹配问题
        ohlcv = exchange.fetch_ohlcv('HYPE/USDT', timeframe, limit=1000)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        
        current_price = df['close'].iloc[-1]
        
        # 1. 计算 SuperTrend
        st_vals, st_dirs = calculate_supertrend_pine(df, ST_ATR_LEN, ST_MULTIPLIER)
        is_st_bull = st_dirs.iloc[-1] == 1
        
        # 2. 计算 UT Bot
        ut_trail, ut_bull = calculate_ut_bot_pine(df, UT_FACTOR, UT_ATR_LEN)
        is_ut_buy = ut_bull.iloc[-1]
        
        # 3. 结果呈现
        st.subheader(f"📊 HYPE/USDT {timeframe} 实战信号")
        c1, c2, c3 = st.columns(3)
        
        with c1:
            st.metric("当前价格", f"{current_price:.4f}")
            status = "🚀 多头" if is_st_bull and is_ut_buy else "📉 整理/空头"
            st.write(f"**综合状态：{status}**")
            
        with c2:
            st.metric("SuperTrend", f"{st_vals.iloc[-1]:.4f}", 
                      delta="YES" if is_st_bull else "NO", delta_color="normal" if is_st_bull else "inverse")
            
        with c3:
            st.metric("UT Bot 止损", f"{ut_trail.iloc[-1]:.4f}", 
                      delta="BUY" if is_ut_buy else "SELL", delta_color="normal" if is_ut_buy else "inverse")

        # 匹配检查逻辑
        st.divider()
        st.write("### 🛡️ 交易员 20 天持有期建议")
        if is_st_bull and is_ut_buy:
            st.success("🔥 信号完全共振！ADX 强劲时可回踩入场。")
        else:
            st.warning("⚠️ 信号不统一，目前处于震荡洗盘期，建议观望。")

    except Exception as e:
        st.error(f"分析出错: {e}")

# ================= 自动循环 =================
analyze()
time.sleep(5)
st.rerun()
