import streamlit as st
import ccxt
import pandas as pd
import pandas_ta as pta
import time
from datetime import datetime, timedelta
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ================= 配置 =================
EXCHANGE_NAME = 'okx'
SCAN_INTERVAL = 10

SYMBOLS = ['BTC/USDT', 'HYPE/USDT', 'ETH/USDT', 'SOL/USDT']

# 指标参数
UT_FACTOR = 1.0
UT_ATR_LEN = 10
ST_ATR_LEN = 10
ST_MULTIPLIER = 3.0

# ================= UI =================
st.set_page_config(
    page_title="币圈指标匹配器", 
    layout="wide"
)

st.title("📊 币圈指标匹配器 - VWAP修复版")

# 侧边栏
with st.sidebar:
    st.header("⚙️ 参数设置")
    
    symbol = st.selectbox("交易对", SYMBOLS, index=0)
    
    timeframe = st.selectbox(
        "时间框架",
        ['1m', '5m', '15m', '1h', '4h'],
        index=0
    )
    
    # VWAP计算方法选择
    vwap_method = st.radio(
        "VWAP计算方法",
        ['🌙 从今日0点开始 (UTC)', '📈 从起点累积', '📊 7天连续'],
        index=0,
        help="选择VWAP的计算方式"
    )
    
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
def fetch_market_data(symbol, timeframe, limit=500):
    """获取市场数据"""
    try:
        exchange = ccxt.okx({'enableRateLimit': True})
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df['date'] = df['timestamp'].dt.date
        df['hour_utc'] = df['timestamp'].dt.hour
        return df
    except Exception as e:
        st.error(f"获取数据失败: {e}")
        return None

# ================= VWAP计算方法1: 从今日0点开始 (UTC) =================
def calculate_vwap_from_today_utc(df):
    """
    从今日0点UTC开始计算VWAP
    匹配TradingView的ta.vwap行为
    """
    # 获取今日UTC时间
    now_utc = datetime.utcnow()
    today_utc = now_utc.date()
    
    # 筛选今日UTC的数据
    today_data = df[df['timestamp'].dt.date == today_utc].copy()
    
    if len(today_data) < 2:
        # 今日数据不足，返回None
        return None, len(today_data), f"今日数据不足({len(today_data)}根)"
    
    # 计算VWAP
    typical = (today_data['high'] + today_data['low'] + today_data['close']) / 3
    volume = today_data['volume']
    
    cumulative_pv = (typical * volume).cumsum()
    cumulative_volume = volume.cumsum()
    
    vwap_values = cumulative_pv / cumulative_volume
    current_vwap = vwap_values.iloc[-1]
    
    return current_vwap, len(today_data), f"今日{len(today_data)}根K线"

# ================= VWAP计算方法2: 从起点累积 =================
def calculate_vwap_from_start(df, lookback=200):
    """从起点累积VWAP"""
    data = df.tail(lookback).copy()
    
    if len(data) < 10:
        return None, len(data), "数据不足"
    
    typical = (data['high'] + data['low'] + data['close']) / 3
    volume = data['volume']
    
    cumulative_pv = (typical * volume).cumsum()
    cumulative_volume = volume.cumsum()
    
    vwap_values = cumulative_pv / cumulative_volume
    current_vwap = vwap_values.iloc[-1]
    
    hours = (data['timestamp'].iloc[-1] - data['timestamp'].iloc[0]).total_seconds() / 3600
    
    return current_vwap, len(data), f"覆盖{hours:.1f}小时"

# ================= VWAP计算方法3: 7天连续 =================
def calculate_vwap_7day(df):
    """7天连续VWAP"""
    end = df['timestamp'].max()
    start = end - timedelta(days=7)
    
    data = df[df['timestamp'] >= start].copy()
    
    if len(data) < 10:
        return None, len(data), "数据不足"
    
    typical = (data['high'] + data['low'] + data['close']) / 3
    volume = data['volume']
    
    cumulative_pv = (typical * volume).cumsum()
    cumulative_volume = volume.cumsum()
    
    vwap_values = cumulative_pv / cumulative_volume
    current_vwap = vwap_values.iloc[-1]
    
    return current_vwap, len(data), f"覆盖{len(data)}根K线"

# ================= 计算所有指标 =================
def calculate_all_indicators(df):
    """计算所有指标"""
    close = df['close'].iloc[-1]
    high = df['high']
    low = df['low']
    volume = df['volume']
    
    # EMA
    ema10 = pta.ema(df['close'], length=10)
    ema20 = pta.ema(df['close'], length=20)
    ema50 = pta.ema(df['close'], length=50)
    
    ema10_gt_20 = False
    close_gt_ema50 = False
    
    if ema10 is not None and ema20 is not None:
        if len(ema10) > 0 and len(ema20) > 0:
            if not pd.isna(ema10.iloc[-1]) and not pd.isna(ema20.iloc[-1]):
                ema10_gt_20 = ema10.iloc[-1] > ema20.iloc[-1]
    
    if ema50 is not None and len(ema50) > 0:
        if not pd.isna(ema50.iloc[-1]):
            close_gt_ema50 = close > ema50.iloc[-1]
    
    # SuperTrend
    st_bull = False
    try:
        st = pta.supertrend(high=high, low=low, close=df['close'], 
                           length=ST_ATR_LEN, multiplier=ST_MULTIPLIER)
        for col in st.columns:
            if 'SUPERT_' in col and not 'd' in col:
                st_bull = close > st[col].iloc[-1]
                break
    except:
        pass
    
    # UT Bot简化版
    atr = pta.atr(high=high, low=low, close=df['close'], length=UT_ATR_LEN)
    ut_stop = close - UT_FACTOR * atr.iloc[-1] if atr is not None else close
    ut_bull = close > ut_stop
    
    # Today Pivot
    today = datetime.utcnow().date()
    today_data = df[df['timestamp'].dt.date == today]
    if len(today_data) > 0:
        d_high = today_data['high'].max()
        d_low = today_data['low'].min()
        d_close = today_data['close'].iloc[-1]
        pivot = (d_high + d_low + d_close) / 3
    else:
        pivot = close
    
    close_gt_pivot = close > pivot
    
    return {
        'close': close,
        'ema10_gt_20': ema10_gt_20,
        'close_gt_ema50': close_gt_ema50,
        'st_bull': st_bull,
        'ut_bull': ut_bull,
        'close_gt_pivot': close_gt_pivot,
        'pivot': pivot
    }

# ================= 主分析函数 =================
def analyze_market():
    """主分析函数"""
    df = fetch_market_data(symbol, timeframe)
    
    if df is None or len(df) < 20:
        st.error("数据不足")
        return
    
    current_price = df['close'].iloc[-1]
    current_time = df['timestamp'].iloc[-1]
    
    # 显示基本信息
    st.subheader(f"📊 {symbol} - {timeframe} - {current_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("当前价格", f"${current_price:,.2f}" if 'BTC' in symbol else f"${current_price:.4f}")
    with col2:
        st.metric("24h最高", f"${df['high'].tail(1440).max():,.2f}" if 'BTC' in symbol else f"${df['high'].tail(1440).max():.4f}")
    with col3:
        st.metric("24h最低", f"${df['low'].tail(1440).min():,.2f}" if 'BTC' in symbol else f"${df['low'].tail(1440).min():.4f}")
    
    # ================= VWAP三种方法对比 =================
    st.subheader("🔄 VWAP三种计算方法对比")
    
    vwap1, bars1, status1 = calculate_vwap_from_today_utc(df)
    vwap2, bars2, status2 = calculate_vwap_from_start(df, 200)
    vwap3, bars3, status3 = calculate_vwap_7day(df)
    
    comparison_data = []
    
    if vwap1:
        comparison_data.append({
            '计算方法': '🌙 从今日0点开始 (UTC)',
            'VWAP值': f"${vwap1:,.2f}" if 'BTC' in symbol else f"${vwap1:.4f}",
            '价格>VWAP': '✅ YES' if current_price > vwap1 else '❌ NO',
            '使用K线': f"{bars1}根",
            '说明': status1
        })
    
    if vwap2:
        comparison_data.append({
            '计算方法': '📈 从起点累积',
            'VWAP值': f"${vwap2:,.2f}" if 'BTC' in symbol else f"${vwap2:.4f}",
            '价格>VWAP': '✅ YES' if current_price > vwap2 else '❌ NO',
            '使用K线': f"{bars2}根",
            '说明': status2
        })
    
    if vwap3:
        comparison_data.append({
            '计算方法': '📊 7天连续',
            'VWAP值': f"${vwap3:,.2f}" if 'BTC' in symbol else f"${vwap3:.4f}",
            '价格>VWAP': '✅ YES' if current_price > vwap3 else '❌ NO',
            '使用K线': f"{bars3}根",
            '说明': status3
        })
    
    if comparison_data:
        df_comp = pd.DataFrame(comparison_data)
        st.dataframe(df_comp, use_container_width=True)
    
    # ================= 计算其他指标 =================
    st.subheader("📊 其他指标")
    
    ind = calculate_all_indicators(df)
    
    # 选择正确的VWAP用于图表对比
    if vwap_method == '🌙 从今日0点开始 (UTC)' and vwap1:
        selected_vwap = vwap1
        selected_method = vwap_method
    elif vwap_method == '📈 从起点累积' and vwap2:
        selected_vwap = vwap2
        selected_method = vwap_method
    elif vwap_method == '📊 7天连续' and vwap3:
        selected_vwap = vwap3
        selected_method = vwap_method
    else:
        selected_vwap = vwap1 if vwap1 else (vwap2 if vwap2 else vwap3)
        selected_method = "默认"
    
    # 创建指标表格
    indicator_data = [
        {'指标': 'EMA10 > EMA20', '状态': 'YES' if ind['ema10_gt_20'] else 'NO'},
        {'指标': 'EMA50', '状态': 'YES' if ind['close_gt_ema50'] else 'NO'},
        {'指标': 'SuperTrend', '状态': 'YES' if ind['st_bull'] else 'NO'},
        {'指标': 'UT Bot', '状态': 'BUY' if ind['ut_bull'] else 'SELL'},
        {'指标': 'VWAP', '状态': 'YES' if current_price > selected_vwap else 'NO'},
        {'指标': 'Today Pivot', '状态': 'YES' if ind['close_gt_pivot'] else 'NO'}
    ]
    
    df_indicators = pd.DataFrame(indicator_data)
    st.dataframe(df_indicators, use_container_width=True)
    
    # ================= 图表 =================
    st.subheader("📈 价格与VWAP图表")
    
    fig = go.Figure()
    
    # 价格线
    fig.add_trace(go.Scatter(
        x=df['timestamp'].tail(100),
        y=df['close'].tail(100),
        mode='lines',
        name='价格',
        line=dict(color='blue', width=2)
    ))
    
    # VWAP线
    if selected_vwap:
        fig.add_hline(
            y=selected_vwap,
            line_dash="dash",
            line_color="purple",
            annotation_text=f"VWAP: ${selected_vwap:,.2f}" if 'BTC' in symbol else f"VWAP: ${selected_vwap:.4f}",
            annotation_position="top right"
        )
    
    fig.update_layout(
        title=f'{symbol} {timeframe} - {selected_method}',
        xaxis_title='时间',
        yaxis_title='价格',
        height=400,
        template='plotly_dark'
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # ================= 匹配度检查 =================
    st.subheader("🎯 与你的图表对比")
    
    matches = []
    
    # 你的图表显示
    chart_display = {
        'EMA10 > EMA20': 'NO',
        'EMA50': 'NO',
        'SuperTrend': 'NO',
        'UT Bot': 'SELL',
        'VWAP': 'NO',
        'Today Pivot': 'NO'
    }
    
    current_display = {
        'EMA10 > EMA20': 'YES' if ind['ema10_gt_20'] else 'NO',
        'EMA50': 'YES' if ind['close_gt_ema50'] else 'NO',
        'SuperTrend': 'YES' if ind['st_bull'] else 'NO',
        'UT Bot': 'BUY' if ind['ut_bull'] else 'SELL',
        'VWAP': 'YES' if current_price > selected_vwap else 'NO',
        'Today Pivot': 'YES' if ind['close_gt_pivot'] else 'NO'
    }
    
    for key in chart_display:
        matches.append({
            '指标': key,
            '图表显示': chart_display[key],
            '当前计算': current_display[key],
            '匹配': '✅' if chart_display[key] == current_display[key] else '❌'
        })
    
    df_matches = pd.DataFrame(matches)
    st.dataframe(df_matches, use_container_width=True)
    
    all_match = all([m['匹配'] == '✅' for m in matches])
    if all_match:
        st.success("✅ 完全匹配你的图表！")
    else:
        st.warning("⚠️ 部分指标不匹配，请调整VWAP计算方法")

# ================= 主循环 =================
current_time = time.time()
if st.session_state.manual_scan or (current_time - st.session_state.last_scan_time > scan_interval):
    analyze_market()
    st.session_state.last_scan_time = current_time
    st.session_state.manual_scan = False

# ================= 自动刷新 =================
time.sleep(2)
st.rerun()
