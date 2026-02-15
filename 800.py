import streamlit as st
import ccxt
import pandas as pd
import pandas_ta as pta
import time
from datetime import datetime, timedelta
import numpy as np

# ================= 配置 =================
EXCHANGE_NAME = 'okx'
TIMEFRAME = '1m'
SCAN_INTERVAL = 10

SYMBOLS = ['HYPE/USDT']

# 指标参数
UT_FACTOR = 1.0
UT_ATR_LEN = 10
ST_ATR_LEN = 10
ST_MULTIPLIER = 3.0

# ================= UI =================
st.set_page_config(page_title="HYPE 精确匹配 - 修复版", layout="wide")
st.title("🎯 HYPE/USDT - UT Bot和Pivot修复版")

# 侧边栏
with st.sidebar:
    st.header("⚙️ 参数")
    scan_interval = st.number_input("扫描间隔(秒)", 5, 30, SCAN_INTERVAL)
    
    if st.button("🔄 立即扫描"):
        st.session_state.manual_scan = True

# 初始化
if 'last_scan_time' not in st.session_state:
    st.session_state.last_scan_time = 0
if 'manual_scan' not in st.session_state:
    st.session_state.manual_scan = False
if 'hype_data' not in st.session_state:
    st.session_state.hype_data = None

# ================= 数据获取 =================
@st.cache_data(ttl=5)
def fetch_hype_data():
    """获取HYPE数据"""
    try:
        exchange = ccxt.okx({
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'}
        })
        ohlcv = exchange.fetch_ohlcv('HYPE/USDT', TIMEFRAME, limit=200)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        st.error(f"获取数据失败: {e}")
        return None

# ================= UT Bot精确实现 (完全匹配Pine Script) =================
def calculate_ut_bot_exact(high, low, close, factor=1.0, atr_length=10):
    """
    完全匹配Pine Script的UT Bot算法
    """
    # 计算ATR
    atr = pta.atr(high=high, low=low, close=close, length=atr_length)
    
    length = len(close)
    ut_stop = np.zeros(length)
    ut_stop[:] = np.nan  # 初始化为NaN，匹配Pine的na
    
    # 第一根K线
    if not np.isnan(atr.iloc[0]):
        ut_stop[0] = close.iloc[0] - factor * atr.iloc[0]
    
    # 逐根计算 - 完全按照Pine Script逻辑
    for i in range(1, length):
        if np.isnan(ut_stop[i-1]) or np.isnan(atr.iloc[i]):
            if not np.isnan(atr.iloc[i]):
                ut_stop[i] = close.iloc[i] - factor * atr.iloc[i]
            continue
        
        # Pine Script逻辑:
        # utStop := close > utStop[1] ? math.max(utStop[1], close - utFactor * atr) : math.min(utStop[1], close + utFactor * atr)
        if close.iloc[i] > ut_stop[i-1]:
            ut_stop[i] = max(ut_stop[i-1], close.iloc[i] - factor * atr.iloc[i])
        else:
            ut_stop[i] = min(ut_stop[i-1], close.iloc[i] + factor * atr.iloc[i])
    
    ut_stop_series = pd.Series(ut_stop, index=close.index)
    ut_bull = close > ut_stop_series
    ut_bear = close < ut_stop_series
    
    return ut_stop_series, ut_bull, ut_bear

# ================= Today Pivot精确实现 =================
def calculate_today_pivot(df):
    """
    计算Today Pivot (使用日线数据)
    """
    # 获取今天的日期
    today = datetime.now().date()
    
    # 筛选今天的数据
    today_data = df[df['timestamp'].dt.date == today]
    
    if len(today_data) > 0:
        # 使用今天的最高最低和最新收盘
        d_high = today_data['high'].max()
        d_low = today_data['low'].min()
        d_close = today_data['close'].iloc[-1]
    else:
        # 如果没有今天的数据，使用最近的数据
        d_high = df['high'].tail(100).max()
        d_low = df['low'].tail(100).min()
        d_close = df['close'].iloc[-1]
    
    # Pivot = (High + Low + Close) / 3
    pivot = (d_high + d_low + d_close) / 3
    
    return pivot, d_high, d_low, d_close

# ================= 计算所有指标 =================
def calculate_indicators(df):
    """计算所有指标"""
    
    close = df['close']
    high = df['high']
    low = df['low']
    volume = df['volume']
    
    #━━━━━━━━━━━━━━━━━━━━━━
    # 1. EMA
    #━━━━━━━━━━━━━━━━━━━━━━
    ema10 = pta.ema(close, length=10)
    ema20 = pta.ema(close, length=20)
    ema50 = pta.ema(close, length=50)
    
    ema10_gt_20 = False
    close_gt_ema50 = False
    
    if ema10 is not None and ema20 is not None:
        if len(ema10) > 0 and len(ema20) > 0:
            if not pd.isna(ema10.iloc[-1]) and not pd.isna(ema20.iloc[-1]):
                ema10_gt_20 = ema10.iloc[-1] > ema20.iloc[-1]
    
    if ema50 is not None and len(ema50) > 0:
        if not pd.isna(ema50.iloc[-1]):
            close_gt_ema50 = close.iloc[-1] > ema50.iloc[-1]
    
    #━━━━━━━━━━━━━━━━━━━━━━
    # 2. SuperTrend
    #━━━━━━━━━━━━━━━━━━━━━━
    st_bull = False
    super_trend_value = None
    
    try:
        st_result = pta.supertrend(
            high=high, 
            low=low, 
            close=close, 
            length=ST_ATR_LEN, 
            multiplier=ST_MULTIPLIER
        )
        
        if st_result is not None:
            for col in st_result.columns:
                if 'SUPERT_' in col and not 'd' in col:
                    super_trend_value = st_result[col].iloc[-1]
                    if not pd.isna(super_trend_value):
                        st_bull = close.iloc[-1] > super_trend_value
                    break
    except:
        pass
    
    #━━━━━━━━━━━━━━━━━━━━━━
    # 3. UT Bot (精确匹配)
    #━━━━━━━━━━━━━━━━━━━━━━
    ut_stop_series, ut_bull, ut_bear = calculate_ut_bot_exact(high, low, close, UT_FACTOR, UT_ATR_LEN)
    
    ut_bull_current = ut_bull.iloc[-1]
    ut_bear_current = ut_bear.iloc[-1]
    ut_stop_current = ut_stop_series.iloc[-1]
    
    #━━━━━━━━━━━━━━━━━━━━━━
    # 4. VWAP
    #━━━━━━━━━━━━━━━━━━━━━━
    close_gt_vwap = False
    vwap_value = None
    
    try:
        typical = (high + low + close) / 3
        vwap = (typical * volume).cumsum() / volume.cumsum()
        if len(vwap) > 0:
            vwap_value = vwap.iloc[-1]
            close_gt_vwap = close.iloc[-1] > vwap_value
    except:
        pass
    
    #━━━━━━━━━━━━━━━━━━━━━━
    # 5. Today Pivot (精确匹配)
    #━━━━━━━━━━━━━━━━━━━━━━
    pivot_value, d_high, d_low, d_close = calculate_today_pivot(df)
    close_gt_pivot = close.iloc[-1] > pivot_value
    
    return {
        'close': close.iloc[-1],
        'ema10': ema10.iloc[-1] if ema10 is not None and len(ema10) > 0 else None,
        'ema20': ema20.iloc[-1] if ema20 is not None and len(ema20) > 0 else None,
        'ema50': ema50.iloc[-1] if ema50 is not None and len(ema50) > 0 else None,
        'ema10_gt_20': ema10_gt_20,
        'close_gt_ema50': close_gt_ema50,
        'st_bull': st_bull,
        'super_trend': super_trend_value,
        'ut_bull': ut_bull_current,
        'ut_bear': ut_bear_current,
        'ut_stop': ut_stop_current,
        'close_gt_vwap': close_gt_vwap,
        'vwap': vwap_value,
        'close_gt_pivot': close_gt_pivot,
        'pivot': pivot_value,
        'd_high': d_high,
        'd_low': d_low,
        'd_close': d_close
    }

# ================= 显示结果 =================
def display_results(ind):
    """显示结果"""
    
    st.subheader("📊 HYPE/USDT 当前状态")
    
    # 创建表格
    data = []
    
    # EMA10>20
    data.append({
        '指标': 'EMA10>20',
        '状态': 'YES' if ind['ema10_gt_20'] else 'NO',
        '数值': f"{ind['ema10']:.4f} > {ind['ema20']:.4f}" if ind['ema10'] and ind['ema20'] else 'N/A'
    })
    
    # EMA50
    data.append({
        '指标': 'EMA50',
        '状态': 'YES' if ind['close_gt_ema50'] else 'NO',
        '数值': f"{ind['close']:.4f} > {ind['ema50']:.4f}" if ind['ema50'] else 'N/A'
    })
    
    # SuperTrend
    data.append({
        '指标': 'SuperTrend',
        '状态': 'YES' if ind['st_bull'] else 'NO',
        '数值': f"{ind['close']:.4f} > {ind['super_trend']:.4f}" if ind['super_trend'] else 'N/A'
    })
    
    # UT Bot - 根据ut_bull显示BUY/SELL
    data.append({
        '指标': 'UT Bot',
        '状态': 'BUY' if ind['ut_bull'] else 'SELL',
        '数值': f"{ind['close']:.4f} > {ind['ut_stop']:.4f} = {ind['ut_bull']}"
    })
    
    # VWAP
    data.append({
        '指标': 'VWAP',
        '状态': 'YES' if ind['close_gt_vwap'] else 'NO',
        '数值': f"{ind['close']:.4f} > {ind['vwap']:.4f}" if ind['vwap'] else 'N/A'
    })
    
    # Today Pivot
    data.append({
        '指标': 'Today Pivot',
        '状态': 'YES' if ind['close_gt_pivot'] else 'NO',
        '数值': f"{ind['close']:.4f} > {ind['pivot']:.4f}"
    })
    
    df_display = pd.DataFrame(data)
    st.dataframe(df_display, use_container_width=True)
    
    # 详细数值
    st.subheader("🔢 详细数值")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("当前价格", f"${ind['close']:.4f}")
        st.metric("UT止损", f"${ind['ut_stop']:.4f}")
        st.metric("UT状态", "BUY" if ind['ut_bull'] else "SELL")
    
    with col2:
        st.metric("SuperTrend", f"${ind['super_trend']:.4f}" if ind['super_trend'] else "N/A")
        st.metric("ST状态", "YES" if ind['st_bull'] else "NO")
        st.metric("VWAP", f"${ind['vwap']:.4f}" if ind['vwap'] else "N/A")
    
    with col3:
        st.metric("Today Pivot", f"${ind['pivot']:.4f}")
        st.metric("日高", f"${ind['d_high']:.4f}")
        st.metric("日低", f"${ind['d_low']:.4f}")
    
    # UT Bot详细计算
    st.subheader("🔍 UT Bot计算过程")
    st.write(f"""
    **ATR计算:**
    - 使用最近{UT_ATR_LEN}根K线计算ATR
    - UT止损 = 根据价格与上一根止损的关系动态计算
    
    **当前值:**
    - 价格: {ind['close']:.4f}
    - UT止损: {ind['ut_stop']:.4f}
    - 价格 > UT止损: {ind['close'] > ind['ut_stop']}
    
    **因此UT Bot显示: {'BUY' if ind['ut_bull'] else 'SELL'}**
    """)
    
    # Pivot详细计算
    st.subheader("📊 Today Pivot计算过程")
    st.write(f"""
    **Pivot公式:** (日高 + 日低 + 最新收盘) / 3
    
    **今日数据:**
    - 日高: {ind['d_high']:.4f}
    - 日低: {ind['d_low']:.4f}
    - 最新收盘: {ind['d_close']:.4f}
    
    **计算结果:**
    - Pivot = ({ind['d_high']:.4f} + {ind['d_low']:.4f} + {ind['d_close']:.4f}) / 3 = {ind['pivot']:.4f}
    - 当前价格 > Pivot: {ind['close'] > ind['pivot']}
    
    **因此Pivot显示: {'YES' if ind['close_gt_pivot'] else 'NO'}**
    """)

# ================= 主扫描 =================
def scan_hype():
    """扫描HYPE"""
    current_time = datetime.now()
    
    df = fetch_hype_data()
    if df is None:
        st.error("无法获取HYPE数据")
        return
    
    ind = calculate_indicators(df)
    st.session_state.hype_data = ind
    
    st.subheader(f"📊 HYPE/USDT - {current_time.strftime('%H:%M:%S')}")
    display_results(ind)

# ================= 主循环 =================
current_time = time.time()
if st.session_state.manual_scan or (current_time - st.session_state.last_scan_time > scan_interval):
    scan_hype()
    st.session_state.last_scan_time = current_time
    st.session_state.manual_scan = False

# ================= 自动刷新 =================
time.sleep(2)
st.rerun()
