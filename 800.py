import streamlit as st
import ccxt
import pandas as pd
import pandas_ta as pta
import time
from datetime import datetime, timedelta
import numpy as np

# ================= 配置 =================
EXCHANGE_NAME = 'okx'
SCAN_INTERVAL = 10

SYMBOLS = ['HYPE/USDT']

# 指标参数
UT_FACTOR = 1.0
UT_ATR_LEN = 10
ST_ATR_LEN = 10
ST_MULTIPLIER = 3.0

# ================= UI =================
st.set_page_config(page_title="多时间框架匹配器", layout="wide")
st.title("📊 多时间框架指标匹配器")

# 侧边栏 - 时间框架选择
with st.sidebar:
    st.header("⚙️ 参数设置")
    
    TIMEFRAME = st.selectbox(
        "时间框架",
        ['1m', '5m', '15m', '1h'],
        index=0
    )
    
    scan_interval = st.number_input("扫描间隔(秒)", 5, 30, SCAN_INTERVAL)
    
    st.header("📈 指标参数")
    ut_factor = st.slider("UT Factor", 0.5, 3.0, UT_FACTOR, 0.1)
    ut_atr_len = st.slider("UT ATR长度", 5, 20, UT_ATR_LEN)
    
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
def fetch_hype_data(timeframe='1m'):
    """获取指定时间框架的HYPE数据"""
    try:
        exchange = ccxt.okx({
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'}
        })
        
        # 根据时间框架获取足够的数据
        limit = {
            '1m': 200,
            '5m': 200,
            '15m': 200,
            '1h': 200
        }.get(timeframe, 200)
        
        ohlcv = exchange.fetch_ohlcv('HYPE/USDT', timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        st.error(f"获取数据失败: {e}")
        return None

# ================= 时间框架自适应的VWAP =================
def calculate_daily_vwap_adaptive(df, timeframe='1m'):
    """
    时间框架自适应的日线VWAP计算
    """
    today = datetime.now().date()
    today_data = df[df['timestamp'].dt.date == today]
    
    # 根据时间框架设置最小K线要求
    min_bars_required = {
        '1m': 30,   # 30分钟数据
        '5m': 12,   # 60分钟数据
        '15m': 8,   # 120分钟数据
        '1h': 4     # 4小时数据
    }.get(timeframe, 10)
    
    st.info(f"📊 {timeframe} - 今日已有 {len(today_data)} 根K线，需要至少 {min_bars_required} 根")
    
    if len(today_data) < min_bars_required:
        # 数据不足，使用昨日数据补充
        yesterday = today - timedelta(days=1)
        yesterday_data = df[df['timestamp'].dt.date == yesterday]
        today_data = pd.concat([yesterday_data.tail(min_bars_required - len(today_data)), today_data])
        st.warning(f"⚠️ 今日数据不足，补充昨日数据后共 {len(today_data)} 根")
    
    if len(today_data) == 0:
        return None
    
    # 计算VWAP
    typical_prices = (today_data['high'] + today_data['low'] + today_data['close']) / 3
    volume = today_data['volume']
    
    cumulative_pv = (typical_prices * volume).cumsum()
    cumulative_volume = volume.cumsum()
    
    vwap_values = cumulative_pv / cumulative_volume
    
    return vwap_values.iloc[-1]

# ================= UT Bot自适应 =================
def calculate_ut_bot_adaptive(high, low, close, factor=1.0, atr_length=10, timeframe='1m'):
    """
    时间框架自适应的UT Bot
    """
    # 根据时间框架调整ATR长度
    atr_length_adj = {
        '1m': atr_length,
        '5m': max(6, atr_length // 2),
        '15m': max(4, atr_length // 3),
        '1h': max(3, atr_length // 4)
    }.get(timeframe, atr_length)
    
    st.info(f"📈 UT Bot - 原始ATR长度: {atr_length}, 调整后: {atr_length_adj}")
    
    atr = pta.atr(high=high, low=low, close=close, length=atr_length_adj)
    
    length = len(close)
    ut_stop = np.zeros(length)
    ut_stop[:] = np.nan
    
    if not np.isnan(atr.iloc[0]):
        ut_stop[0] = close.iloc[0] - factor * atr.iloc[0]
    
    for i in range(1, length):
        if np.isnan(ut_stop[i-1]) or np.isnan(atr.iloc[i]):
            if not np.isnan(atr.iloc[i]):
                ut_stop[i] = close.iloc[i] - factor * atr.iloc[i]
            continue
        
        if close.iloc[i] > ut_stop[i-1]:
            ut_stop[i] = max(ut_stop[i-1], close.iloc[i] - factor * atr.iloc[i])
        else:
            ut_stop[i] = min(ut_stop[i-1], close.iloc[i] + factor * atr.iloc[i])
    
    ut_stop_series = pd.Series(ut_stop, index=close.index)
    ut_bull = close > ut_stop_series
    
    return ut_stop_series, ut_bull

# ================= Today Pivot (时间框架无关) =================
def calculate_today_pivot(df):
    """计算Today Pivot（与时间框架无关）"""
    today = datetime.now().date()
    today_data = df[df['timestamp'].dt.date == today]
    
    if len(today_data) > 0:
        d_high = today_data['high'].max()
        d_low = today_data['low'].min()
        d_close = today_data['close'].iloc[-1]
    else:
        d_high = df['high'].tail(100).max()
        d_low = df['low'].tail(100).min()
        d_close = df['close'].iloc[-1]
    
    pivot = (d_high + d_low + d_close) / 3
    
    return pivot, d_high, d_low, d_close

# ================= 计算所有指标 =================
def calculate_indicators(df, timeframe='1m'):
    """计算所有指标"""
    
    close = df['close']
    high = df['high']
    low = df['low']
    
    #━━━━━━━━━━━━━━━━━━━━━━
    # 1. EMA
    #━━━━━━━━━━━━━━━━━━━━━━
    ema10 = pta.ema(close, length=10)
    ema20 = pta.ema(close, length=20)
    ema50 = pta.ema(close, length=50)
    ema200 = pta.ema(close, length=200)
    
    ema10_gt_20 = False
    close_gt_ema50 = False
    close_gt_ema200 = False
    
    if ema10 is not None and ema20 is not None:
        if len(ema10) > 0 and len(ema20) > 0:
            if not pd.isna(ema10.iloc[-1]) and not pd.isna(ema20.iloc[-1]):
                ema10_gt_20 = ema10.iloc[-1] > ema20.iloc[-1]
    
    if ema50 is not None and len(ema50) > 0:
        if not pd.isna(ema50.iloc[-1]):
            close_gt_ema50 = close.iloc[-1] > ema50.iloc[-1]
    
    if ema200 is not None and len(ema200) > 0:
        if not pd.isna(ema200.iloc[-1]):
            close_gt_ema200 = close.iloc[-1] > ema200.iloc[-1]
    
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
    # 3. UT Bot (自适应)
    #━━━━━━━━━━━━━━━━━━━━━━
    ut_stop_series, ut_bull = calculate_ut_bot_adaptive(
        high, low, close, UT_FACTOR, UT_ATR_LEN, timeframe
    )
    
    ut_bull_current = ut_bull.iloc[-1]
    ut_stop_current = ut_stop_series.iloc[-1]
    
    #━━━━━━━━━━━━━━━━━━━━━━
    # 4. 日线VWAP (自适应)
    #━━━━━━━━━━━━━━━━━━━━━━
    vwap_value = calculate_daily_vwap_adaptive(df, timeframe)
    close_gt_vwap = close.iloc[-1] > vwap_value if vwap_value is not None else False
    
    #━━━━━━━━━━━━━━━━━━━━━━
    # 5. Today Pivot
    #━━━━━━━━━━━━━━━━━━━━━━
    pivot_value, d_high, d_low, d_close = calculate_today_pivot(df)
    close_gt_pivot = close.iloc[-1] > pivot_value
    
    return {
        'close': close.iloc[-1],
        'ema10': ema10.iloc[-1] if ema10 is not None and len(ema10) > 0 else None,
        'ema20': ema20.iloc[-1] if ema20 is not None and len(ema20) > 0 else None,
        'ema50': ema50.iloc[-1] if ema50 is not None and len(ema50) > 0 else None,
        'ema200': ema200.iloc[-1] if ema200 is not None and len(ema200) > 0 else None,
        'ema10_gt_20': ema10_gt_20,
        'close_gt_ema50': close_gt_ema50,
        'close_gt_ema200': close_gt_ema200,
        'st_bull': st_bull,
        'super_trend': super_trend_value,
        'ut_bull': ut_bull_current,
        'ut_stop': ut_stop_current,
        'vwap': vwap_value,
        'close_gt_vwap': close_gt_vwap,
        'pivot': pivot_value,
        'close_gt_pivot': close_gt_pivot,
        'd_high': d_high,
        'd_low': d_low,
        'd_close': d_close
    }

# ================= 显示结果 =================
def display_results(ind, timeframe):
    """显示结果"""
    
    st.subheader(f"📊 HYPE/USDT - {timeframe} - {datetime.now().strftime('%H:%M:%S')}")
    
    # 创建显示表格
    data = []
    
    # EMA10>20
    data.append({
        '指标': 'EMA10>20',
        '状态': 'NO' if not ind['ema10_gt_20'] else 'YES',
        '数值': f"{ind['ema10']:.4f} > {ind['ema20']:.4f} = {ind['ema10_gt_20']}"
    })
    
    # EMA50
    data.append({
        '指标': 'EMA50',
        '状态': 'NO' if not ind['close_gt_ema50'] else 'YES',
        '数值': f"{ind['close']:.4f} > {ind['ema50']:.4f} = {ind['close_gt_ema50']}"
    })
    
    # EMA200
    data.append({
        '指标': 'EMA200',
        '状态': 'YES' if ind['close_gt_ema200'] else 'NO',
        '数值': f"{ind['close']:.4f} > {ind['ema200']:.4f} = {ind['close_gt_ema200']}"
    })
    
    # SuperTrend
    data.append({
        '指标': 'SuperTrend',
        '状态': 'NO' if not ind['st_bull'] else 'YES',
        '数值': f"{ind['close']:.4f} > {ind['super_trend']:.4f} = {ind['st_bull']}"
    })
    
    # UT Bot
    data.append({
        '指标': 'UT Bot',
        '状态': 'SELL' if not ind['ut_bull'] else 'BUY',
        '数值': f"{ind['close']:.4f} > {ind['ut_stop']:.4f} = {ind['ut_bull']}"
    })
    
    # VWAP
    data.append({
        '指标': 'VWAP',
        '状态': 'NO' if not ind['close_gt_vwap'] else 'YES',
        '数值': f"{ind['close']:.4f} > {ind['vwap']:.4f} = {ind['close_gt_vwap']}"
    })
    
    # Pivot
    data.append({
        '指标': 'Pivot',
        '状态': 'NO' if not ind['close_gt_pivot'] else 'YES',
        '数值': f"{ind['close']:.4f} > {ind['pivot']:.4f} = {ind['close_gt_pivot']}"
    })
    
    df_display = pd.DataFrame(data)
    st.dataframe(df_display, use_container_width=True)
    
    # 详细数值
    st.subheader("🔢 详细数值")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("当前价格", f"${ind['close']:.4f}")
        st.metric("UT止损", f"${ind['ut_stop']:.4f}")
        st.metric("UT状态", "SELL" if not ind['ut_bull'] else "BUY")
    
    with col2:
        st.metric("SuperTrend", f"${ind['super_trend']:.4f}" if ind['super_trend'] else "N/A")
        st.metric("ST状态", "NO" if not ind['st_bull'] else "YES")
        st.metric("日线VWAP", f"${ind['vwap']:.4f}" if ind['vwap'] else "N/A")
    
    with col3:
        st.metric("Pivot", f"${ind['pivot']:.4f}")
        st.metric("VWAP状态", "NO" if not ind['close_gt_vwap'] else "YES")
        st.metric("Pivot状态", "NO" if not ind['close_gt_pivot'] else "YES")

# ================= 主扫描 =================
def scan_hype():
    """扫描HYPE"""
    df = fetch_hype_data(TIMEFRAME)
    if df is None:
        st.error("无法获取HYPE数据")
        return
    
    ind = calculate_indicators(df, TIMEFRAME)
    st.session_state.hype_data = ind
    
    display_results(ind, TIMEFRAME)

# ================= 主循环 =================
current_time = time.time()
if st.session_state.manual_scan or (current_time - st.session_state.last_scan_time > scan_interval):
    scan_hype()
    st.session_state.last_scan_time = current_time
    st.session_state.manual_scan = False

# ================= 自动刷新 =================
time.sleep(2)
st.rerun()
