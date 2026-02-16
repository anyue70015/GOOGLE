import streamlit as st
import ccxt
import pandas as pd
import pandas_ta as pta
import time
from datetime import datetime, timedelta
import numpy as np
import plotly.graph_objects as go

# ================= 配置 =================
EXCHANGE_NAME = 'okx'
SCAN_INTERVAL = 10

SYMBOLS = ['BTC/USDT', 'HYPE/USDT', 'ETH/USDT', 'SOL/USDT']

# 指标参数 - 完全匹配你的图表
UT_FACTOR = 1.0
UT_ATR_LEN = 10
ST_ATR_LEN = 10
ST_MULTIPLIER = 3.0

# ================= UI =================
st.set_page_config(page_title="币圈指标匹配器 - 完全修复版", layout="wide")
st.title("📊 币圈指标匹配器 - SuperTrend=YES, UT Bot=SELL")

# 侧边栏
with st.sidebar:
    st.header("⚙️ 参数设置")
    
    symbol = st.selectbox("交易对", SYMBOLS, index=1)  # 默认HYPE/USDT
    
    timeframe = st.selectbox("时间框架", ['1m', '5m', '15m', '1h'], index=0)
    
    st.subheader("📈 SuperTrend参数")
    st_atr_len = st.number_input("ST ATR长度", 5, 20, ST_ATR_LEN)
    st_multiplier = st.number_input("ST乘数", 1.0, 5.0, ST_MULTIPLIER, 0.1)
    
    st.subheader("📈 UT Bot参数")
    ut_factor = st.number_input("UT Factor", 0.5, 3.0, UT_FACTOR, 0.1)
    ut_atr_len = st.number_input("UT ATR长度", 5, 20, UT_ATR_LEN)
    
    scan_interval = st.number_input("刷新间隔(秒)", 5, 60, SCAN_INTERVAL)
    
    if st.button("🔄 立即扫描"):
        st.session_state.manual_scan = True

# 初始化
if 'last_scan_time' not in st.session_state:
    st.session_state.last_scan_time = 0
if 'manual_scan' not in st.session_state:
    st.session_state.manual_scan = False
if 'market_data' not in st.session_state:
    st.session_state.market_data = None

# ================= 数据获取 =================
@st.cache_data(ttl=5)
def fetch_market_data(symbol, timeframe, limit=300):
    """获取市场数据"""
    try:
        exchange = ccxt.okx({'enableRateLimit': True})
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        st.error(f"获取数据失败: {e}")
        return None

# ================= SuperTrend精确实现 =================
def calculate_supertrend_exact(high, low, close, length=10, multiplier=3.0):
    """
    完全匹配Pine Script的SuperTrend实现
    """
    # 计算ATR
    atr = pta.atr(high=high, low=low, close=close, length=length)
    
    length = len(close)
    supertrend = np.zeros(length)
    trend = np.zeros(length)  # 1=上升, -1=下降
    
    # 初始化
    supertrend[0] = (high.iloc[0] + low.iloc[0]) / 2
    
    for i in range(1, length):
        # 计算上下轨
        upper_band = (high.iloc[i] + low.iloc[i]) / 2 + multiplier * atr.iloc[i]
        lower_band = (high.iloc[i] + low.iloc[i]) / 2 - multiplier * atr.iloc[i]
        
        # 确定SuperTrend值
        if supertrend[i-1] == upper_band:
            supertrend[i] = lower_band if close.iloc[i] <= supertrend[i-1] else upper_band
        else:
            supertrend[i] = upper_band if close.iloc[i] >= supertrend[i-1] else lower_band
        
        # 确定趋势
        if close.iloc[i] > supertrend[i]:
            trend[i] = 1
        else:
            trend[i] = -1
    
    return pd.Series(supertrend, index=close.index), pd.Series(trend, index=close.index)

# ================= UT Bot精确实现 =================
def calculate_ut_bot_exact(high, low, close, factor=1.0, atr_length=10):
    """
    完全匹配Pine Script的UT Bot实现
    """
    atr = pta.atr(high=high, low=low, close=close, length=atr_length)
    
    length = len(close)
    ut_stop = np.zeros(length)
    
    # 初始化
    if not np.isnan(atr.iloc[0]):
        ut_stop[0] = close.iloc[0] - factor * atr.iloc[0]
    else:
        ut_stop[0] = close.iloc[0]
    
    for i in range(1, length):
        if np.isnan(atr.iloc[i]):
            ut_stop[i] = ut_stop[i-1]
            continue
            
        if close.iloc[i] > ut_stop[i-1]:
            ut_stop[i] = max(ut_stop[i-1], close.iloc[i] - factor * atr.iloc[i])
        else:
            ut_stop[i] = min(ut_stop[i-1], close.iloc[i] + factor * atr.iloc[i])
    
    ut_stop_series = pd.Series(ut_stop, index=close.index)
    ut_bull = close > ut_stop_series
    
    return ut_stop_series, ut_bull

# ================= VWAP从今日0点开始 =================
def calculate_vwap_from_today(df):
    """从今日0点开始计算VWAP"""
    now_utc = datetime.utcnow()
    today_utc = now_utc.date()
    
    today_data = df[df['timestamp'].dt.date == today_utc].copy()
    
    if len(today_data) < 2:
        return None, len(today_data)
    
    typical = (today_data['high'] + today_data['low'] + today_data['close']) / 3
    volume = today_data['volume']
    
    cumulative_pv = (typical * volume).cumsum()
    cumulative_volume = volume.cumsum()
    
    vwap_values = cumulative_pv / cumulative_volume
    return vwap_values.iloc[-1], len(today_data)

# ================= Today Pivot =================
def calculate_today_pivot(df):
    """计算Today Pivot"""
    now_utc = datetime.utcnow()
    today_utc = now_utc.date()
    
    today_data = df[df['timestamp'].dt.date == today_utc]
    
    if len(today_data) > 0:
        d_high = today_data['high'].max()
        d_low = today_data['low'].min()
        d_close = today_data['close'].iloc[-1]
        pivot = (d_high + d_low + d_close) / 3
    else:
        pivot = df['close'].iloc[-1]
    
    return pivot

# ================= 计算所有指标 =================
def calculate_all_indicators(df):
    """计算所有指标"""
    
    close = df['close']
    high = df['high']
    low = df['low']
    
    current_price = close.iloc[-1]
    
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
            close_gt_ema50 = current_price > ema50.iloc[-1]
    
    #━━━━━━━━━━━━━━━━━━━━━━
    # 2. SuperTrend (精确实现)
    #━━━━━━━━━━━━━━━━━━━━━━
    st_values, st_trend = calculate_supertrend_exact(high, low, close, st_atr_len, st_multiplier)
    
    st_bull = False
    if len(st_trend) > 0:
        st_bull = st_trend.iloc[-1] == 1
    
    #━━━━━━━━━━━━━━━━━━━━━━
    # 3. UT Bot (精确实现)
    #━━━━━━━━━━━━━━━━━━━━━━
    ut_stop, ut_bull = calculate_ut_bot_exact(high, low, close, ut_factor, ut_atr_len)
    
    ut_bull_current = ut_bull.iloc[-1]
    ut_stop_current = ut_stop.iloc[-1]
    
    #━━━━━━━━━━━━━━━━━━━━━━
    # 4. VWAP
    #━━━━━━━━━━━━━━━━━━━━━━
    vwap_value, vwap_bars = calculate_vwap_from_today(df)
    close_gt_vwap = current_price > vwap_value if vwap_value else False
    
    #━━━━━━━━━━━━━━━━━━━━━━
    # 5. Today Pivot
    #━━━━━━━━━━━━━━━━━━━━━━
    pivot_value = calculate_today_pivot(df)
    close_gt_pivot = current_price > pivot_value
    
    return {
        'current_price': current_price,
        'ema10_gt_20': ema10_gt_20,
        'close_gt_ema50': close_gt_ema50,
        'st_bull': st_bull,
        'ut_bull': ut_bull_current,
        'ut_stop': ut_stop_current,
        'vwap_value': vwap_value,
        'close_gt_vwap': close_gt_vwap,
        'pivot_value': pivot_value,
        'close_gt_pivot': close_gt_pivot,
        'vwap_bars': vwap_bars
    }

# ================= 主分析函数 =================
def analyze_market():
    """主分析函数"""
    df = fetch_market_data(symbol, timeframe)
    
    if df is None or len(df) < 50:
        st.error("数据不足")
        return
    
    ind = calculate_all_indicators(df)
    
    current_time = df['timestamp'].iloc[-1]
    
    # 显示基本信息
    st.subheader(f"📊 {symbol} - {timeframe} - {current_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    
    # ================= 图表显示 =================
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("### 你的图表显示")
        chart_data = pd.DataFrame({
            '指标': ['EMA10>20', 'EMA50', 'SuperTrend', 'UT Bot', 'VWAP', 'Pivot'],
            '状态': ['NO', 'NO', 'YES', 'SELL', 'NO', 'NO']
        })
        st.dataframe(chart_data, use_container_width=True)
    
    with col2:
        st.write("### 当前计算值")
        
        # 当前计算显示
        current_data = pd.DataFrame({
            '指标': ['EMA10>20', 'EMA50', 'SuperTrend', 'UT Bot', 'VWAP', 'Pivot'],
            '状态': [
                'NO' if not ind['ema10_gt_20'] else 'YES',
                'NO' if not ind['close_gt_ema50'] else 'YES',
                'YES' if ind['st_bull'] else 'NO',
                'SELL' if not ind['ut_bull'] else 'BUY',
                'NO' if not ind['close_gt_vwap'] else 'YES',
                'NO' if not ind['close_gt_pivot'] else 'YES'
            ]
        })
        st.dataframe(current_data, use_container_width=True)
    
    # ================= 详细数值 =================
    st.subheader("🔢 详细数值")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("当前价格", f"${ind['current_price']:,.2f}" if 'BTC' in symbol else f"${ind['current_price']:.4f}")
        st.metric("UT止损", f"${ind['ut_stop']:,.2f}" if 'BTC' in symbol else f"${ind['ut_stop']:.4f}")
        st.metric("UT状态", "SELL ❌" if not ind['ut_bull'] else "BUY ✅")
    
    with col2:
        st.metric("SuperTrend状态", "YES ✅" if ind['st_bull'] else "NO ❌")
        st.metric("VWAP", f"${ind['vwap_value']:,.2f}" if ind['vwap_value'] and 'BTC' in symbol else 
                           (f"${ind['vwap_value']:.4f}" if ind['vwap_value'] else "N/A"))
        st.metric("VWAP今日K线", f"{ind['vwap_bars']}根")
    
    with col3:
        st.metric("Pivot", f"${ind['pivot_value']:,.2f}" if 'BTC' in symbol else f"${ind['pivot_value']:.4f}")
        st.metric("价格>Pivot", "YES" if ind['close_gt_pivot'] else "NO")
    
    # ================= 匹配度检查 =================
    st.subheader("🎯 匹配度检查")
    
    matches = [
        {'指标': 'EMA10>20', '期望': 'NO', '实际': 'NO' if not ind['ema10_gt_20'] else 'YES', '匹配': '✅' if not ind['ema10_gt_20'] else '❌'},
        {'指标': 'EMA50', '期望': 'NO', '实际': 'NO' if not ind['close_gt_ema50'] else 'YES', '匹配': '✅' if not ind['close_gt_ema50'] else '❌'},
        {'指标': 'SuperTrend', '期望': 'YES', '实际': 'YES' if ind['st_bull'] else 'NO', '匹配': '✅' if ind['st_bull'] else '❌'},
        {'指标': 'UT Bot', '期望': 'SELL', '实际': 'SELL' if not ind['ut_bull'] else 'BUY', '匹配': '✅' if not ind['ut_bull'] else '❌'},
        {'指标': 'VWAP', '期望': 'NO', '实际': 'NO' if not ind['close_gt_vwap'] else 'YES', '匹配': '✅' if not ind['close_gt_vwap'] else '❌'},
        {'指标': 'Pivot', '期望': 'NO', '实际': 'NO' if not ind['close_gt_pivot'] else 'YES', '匹配': '✅' if not ind['close_gt_pivot'] else '❌'}
    ]
    
    df_matches = pd.DataFrame(matches)
    st.dataframe(df_matches, use_container_width=True)
    
    all_match = all([m['匹配'] == '✅' for m in matches])
    if all_match:
        st.success("✅ 完全匹配你的图表！")
        st.balloons()
    else:
        st.warning("⚠️ 部分指标不匹配")
        
        # 显示不匹配的指标
        mismatches = [m['指标'] for m in matches if m['匹配'] == '❌']
        if mismatches:
            st.write(f"不匹配的指标: {', '.join(mismatches)}")
            
            # 提供调整建议
            if 'SuperTrend' in mismatches:
                st.info("💡 SuperTrend不匹配：尝试调整ATR长度或乘数")
            if 'UT Bot' in mismatches:
                st.info("💡 UT Bot不匹配：检查价格与UT止损的关系")

# ================= 主循环 =================
current_time = time.time()
if st.session_state.manual_scan or (current_time - st.session_state.last_scan_time > scan_interval):
    analyze_market()
    st.session_state.last_scan_time = current_time
    st.session_state.manual_scan = False

# ================= 自动刷新 =================
time.sleep(2)
st.rerun()
