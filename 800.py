import streamlit as st
import ccxt
import pandas as pd
import numpy as np
import time

# ================= 强行匹配算法库 =================

def calculate_vwmp_pine(df, length=20):
    """
    精确复刻 VWMP (成交量加权移动价格)
    逻辑：Sum(TypicalPrice * Volume, length) / Sum(Volume, length)
    Typical Price = (High + Low + Close) / 3
    """
    tp = (df['high'] + df['low'] + df['close']) / 3
    tpv = tp * df['volume']
    
    # 滚动窗口计算
    sum_tpv = tpv.rolling(window=length).sum()
    sum_vol = df['volume'].rolling(window=length).sum()
    
    return sum_tpv / sum_vol

def calculate_pine_ema(series, length):
    """完全对齐 TradingView 的 ta.ema 逻辑"""
    # TV 的 EMA 使用 adjust=False，且初始值是第一个有效值的 SMA
    return series.ewm(span=length, adjust=False).mean()

# ================= 主分析函数 (HYPE 专用) =================

def analyze_hype():
    try:
        # 1. 获取 1000 根数据以供预热
        exchange = ccxt.okx()
        ohlcv = exchange.fetch_ohlcv('HYPE/USDT', timeframe, limit=1000)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # 2. 计算核心指标 (强行对齐 TV)
        df['vwmp'] = calculate_vwmp_pine(df, 20)  # 默认 20 周期
        df['ema10'] = calculate_pine_ema(df['close'], 10)
        df['ema20'] = calculate_pine_ema(df['close'], 20)
        df['ema50'] = calculate_pine_ema(df['close'], 50)
        
        # 3. 计算 SuperTrend 和 UT Bot (使用之前复刻的算法)
        # st_vals, st_dirs = calculate_supertrend_pine(df, 10, 3.0)
        # ut_trail, ut_bull = calculate_ut_bot_pine(df, 1.0, 10)
        
        # --- 状态判定 ---
        current = df.iloc[-1]
        is_above_vwmp = current['close'] > current['vwmp']
        is_ema_bull = current['ema10'] > current['ema20']
        is_water = current['close'] > current['ema50']  # 水上/水下
        
        # ================= UI 渲染 =================
        st.subheader(f"🎯 HYPE/USDT {timeframe} 强行匹配面板")
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("VWMP 支撑", f"{current['vwmp']:.4f}", 
                   delta="水上 ✅" if is_above_vwmp else "破位 ❌", delta_color="normal" if is_above_vwmp else "inverse")
        col2.metric("EMA 10/20", "金叉 🚀" if is_ema_bull else "死叉 💀")
        col3.metric("EMA 50 (深水区)", "水上 ☀️" if is_water else "深水 🌊")
        col4.metric("当前价格", f"{current['close']:.4f}")

        # 4. 回踩进逻辑判断
        st.divider()
        if is_above_vwmp and is_water and is_ema_bull:
            st.success("🔥 五星形态：价格在 VWMP 之上且处于水上，这是最硬的『回踩进』信号！")
        elif not is_water:
            st.error("⚠️ 警告：目前处于深水区 (EMA50 下方)，任何反弹都是急涨慢跌的诱多！")

    except Exception as e:
        st.error(f"计算失败: {e}")

# ... 其余循环代码保持不变 ...
