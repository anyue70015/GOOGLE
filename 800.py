import streamlit as st
import ccxt
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta

# ================= 配置 =================
EXCHANGE_NAME = 'okx'
SCAN_INTERVAL = 10

# 只关注HYPE
SYMBOLS = ['HYPE/USDT']

# 原始参数
ST_ATR_LEN = 10
ST_MULTIPLIER = 3.0
UT_FACTOR = 1.0
UT_ATR_LEN = 10

# ================= UI =================
st.set_page_config(page_title="HYPE 多时间框架匹配器", layout="wide")
st.title("🎯 HYPE/USDT - 选择你的时间框架")

# 侧边栏 - 时间框架选择
with st.sidebar:
    st.header("⚙️ 时间框架选择")
    
    timeframe = st.selectbox(
        "选择你的图表时间框架",
        ['1m', '5m', '15m', '30m', '1h', '4h'],
        index=0,  # 默认1分钟
        help="选择与你图表相同的时间框架"
    )
    
    st.header("📊 原始参数")
    st.write(f"SuperTrend ATR: {ST_ATR_LEN}")
    st.write(f"SuperTrend乘数: {ST_MULTIPLIER}")
    st.write(f"UT Factor: {UT_FACTOR}")
    st.write(f"UT ATR: {UT_ATR_LEN}")
    
    if st.button("🔄 立即扫描", use_container_width=True):
        st.session_state.manual_scan = True

# 初始化
if 'last_scan_time' not in st.session_state:
    st.session_state.last_scan_time = 0
if 'manual_scan' not in st.session_state:
    st.session_state.manual_scan = False

# ================= 数据获取 =================
@st.cache_data(ttl=5)
def fetch_hype_data(tf='1m'):
    """获取指定时间框架的HYPE数据"""
    try:
        exchange = ccxt.okx({'enableRateLimit': True})
        
        # 根据时间框架获取足够的数据
        limit = 500 if tf in ['1m', '5m'] else 300
        ohlcv = exchange.fetch_ohlcv('HYPE/USDT', tf, limit=limit)
        
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        st.error(f"获取数据失败: {e}")
        return None

# ================= Pine Script ATR (RMA) =================
def calculate_pine_atr(high, low, close, length=10):
    """Pine Script的RMA算法"""
    # 计算True Range
    tr = pd.DataFrame({
        'hl': high - low,
        'hc': abs(high - close.shift()),
        'lc': abs(low - close.shift())
    }).max(axis=1)
    
    # RMA平滑
    alpha = 1.0 / length
    rma = np.zeros(len(tr))
    rma[0] = tr.iloc[0]
    
    for i in range(1, len(tr)):
        rma[i] = alpha * tr.iloc[i] + (1 - alpha) * rma[i-1]
    
    return pd.Series(rma, index=close.index)

# ================= Pine Script SuperTrend =================
def calculate_supertrend_pine(high, low, close, length=10, multiplier=3.0):
    """完全匹配Pine Script的SuperTrend"""
    atr = calculate_pine_atr(high, low, close, length)
    
    n = len(close)
    supertrend = np.zeros(n)
    trend = np.zeros(n)
    
    # 初始化
    supertrend[0] = (high.iloc[0] + low.iloc[0]) / 2
    
    for i in range(1, n):
        # 上下轨
        upper = (high.iloc[i] + low.iloc[i]) / 2 + multiplier * atr.iloc[i]
        lower = (high.iloc[i] + low.iloc[i]) / 2 - multiplier * atr.iloc[i]
        
        # SuperTrend逻辑
        if supertrend[i-1] == upper:
            supertrend[i] = lower if close.iloc[i] <= supertrend[i-1] else upper
        else:
            supertrend[i] = upper if close.iloc[i] >= supertrend[i-1] else lower
        
        # 趋势: 1=上升, -1=下降
        trend[i] = 1 if close.iloc[i] > supertrend[i] else -1
    
    return pd.Series(supertrend, index=close.index), pd.Series(trend, index=close.index)

# ================= Pine Script UT Bot =================
def calculate_ut_bot_pine(high, low, close, factor=1.0, atr_length=10):
    """完全匹配Pine Script的UT Bot"""
    atr = calculate_pine_atr(high, low, close, atr_length)
    
    n = len(close)
    ut_stop = np.zeros(n)
    ut_stop[0] = close.iloc[0] - factor * atr.iloc[0]
    
    for i in range(1, n):
        if close.iloc[i] > ut_stop[i-1]:
            ut_stop[i] = max(ut_stop[i-1], close.iloc[i] - factor * atr.iloc[i])
        else:
            ut_stop[i] = min(ut_stop[i-1], close.iloc[i] + factor * atr.iloc[i])
    
    ut_stop_series = pd.Series(ut_stop, index=close.index)
    ut_bull = close > ut_stop_series
    
    return ut_stop_series, ut_bull

# ================= VWAP从今日0点 =================
def calculate_vwap_today(df):
    """从今日0点UTC开始计算VWAP"""
    today = datetime.utcnow().date()
    today_data = df[df['timestamp'].dt.date == today]
    
    if len(today_data) < 2:
        return None
    
    typical = (today_data['high'] + today_data['low'] + today_data['close']) / 3
    volume = today_data['volume']
    
    vwap = (typical * volume).sum() / volume.sum()
    return vwap

# ================= Today Pivot =================
def calculate_pivot(df):
    """计算Today Pivot"""
    today = datetime.utcnow().date()
    today_data = df[df['timestamp'].dt.date == today]
    
    if len(today_data) > 0:
        high = today_data['high'].max()
        low = today_data['low'].min()
        close = today_data['close'].iloc[-1]
        pivot = (high + low + close) / 3
    else:
        pivot = df['close'].iloc[-1]
    
    return pivot

# ================= 主分析 =================
def analyze():
    df = fetch_hype_data(timeframe)
    if df is None:
        return
    
    close = df['close']
    high = df['high']
    low = df['low']
    
    current_price = close.iloc[-1]
    current_time = df['timestamp'].iloc[-1]
    
    # EMA
    ema10 = close.ewm(span=10, adjust=False).mean()
    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    
    ema10_gt_20 = ema10.iloc[-1] > ema20.iloc[-1]
    close_gt_ema50 = current_price > ema50.iloc[-1]
    
    # SuperTrend (Pine版本)
    st_values, st_trend = calculate_supertrend_pine(high, low, close, ST_ATR_LEN, ST_MULTIPLIER)
    st_bull = st_trend.iloc[-1] == 1
    st_current = st_values.iloc[-1]
    
    # UT Bot (Pine版本)
    ut_stop, ut_bull = calculate_ut_bot_pine(high, low, close, UT_FACTOR, UT_ATR_LEN)
    ut_bull_current = ut_bull.iloc[-1]
    ut_stop_current = ut_stop.iloc[-1]
    
    # VWAP
    vwap = calculate_vwap_today(df)
    close_gt_vwap = current_price > vwap if vwap else False
    
    # Pivot
    pivot = calculate_pivot(df)
    close_gt_pivot = current_price > pivot
    
    # ================= 显示结果 =================
    st.subheader(f"📊 HYPE/USDT - {timeframe} - {current_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    
    # 创建两列对比
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("### 📋 你的图表显示")
        chart_data = pd.DataFrame({
            '指标': ['EMA10>20', 'EMA50', 'SuperTrend', 'UT Bot', 'VWAP', 'Pivot'],
            '状态': ['NO', 'NO', 'YES', 'SELL', 'NO', 'NO']
        })
        st.dataframe(chart_data, use_container_width=True)
    
    with col2:
        st.write("### 💻 当前计算值")
        current_data = pd.DataFrame({
            '指标': ['EMA10>20', 'EMA50', 'SuperTrend', 'UT Bot', 'VWAP', 'Pivot'],
            '状态': [
                'NO' if not ema10_gt_20 else 'YES',
                'NO' if not close_gt_ema50 else 'YES',
                'YES' if st_bull else 'NO',
                'SELL' if not ut_bull_current else 'BUY',
                'NO' if not close_gt_vwap else 'YES',
                'NO' if not close_gt_pivot else 'YES'
            ]
        })
        st.dataframe(current_data, use_container_width=True)
    
    # ================= 详细数值 =================
    st.subheader("🔢 详细数值")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("当前价格", f"${current_price:.4f}")
        st.metric("UT止损", f"${ut_stop_current:.4f}")
        st.metric("价格-UT止损", f"${current_price - ut_stop_current:.4f}")
    
    with col2:
        st.metric("SuperTrend值", f"${st_current:.4f}")
        st.metric("价格-SuperTrend", f"${current_price - st_current:.4f}")
        st.metric("SuperTrend状态", "YES ✅" if st_bull else "NO ❌")
    
    with col3:
        st.metric("VWAP", f"${vwap:.4f}" if vwap else "N/A")
        st.metric("Pivot", f"${pivot:.4f}")
        st.metric("今日K线数", f"{len(df[df['timestamp'].dt.date == datetime.utcnow().date()])}根")
    
    # ================= 匹配度检查 =================
    st.subheader("🎯 匹配度检查")
    
    matches = [
        {'指标': 'EMA10>20', '期望': 'NO', '实际': 'NO' if not ema10_gt_20 else 'YES', '匹配': '✅' if not ema10_gt_20 else '❌'},
        {'指标': 'EMA50', '期望': 'NO', '实际': 'NO' if not close_gt_ema50 else 'YES', '匹配': '✅' if not close_gt_ema50 else '❌'},
        {'指标': 'SuperTrend', '期望': 'YES', '实际': 'YES' if st_bull else 'NO', '匹配': '✅' if st_bull else '❌'},
        {'指标': 'UT Bot', '期望': 'SELL', '实际': 'SELL' if not ut_bull_current else 'BUY', '匹配': '✅' if not ut_bull_current else '❌'},
        {'指标': 'VWAP', '期望': 'NO', '实际': 'NO' if not close_gt_vwap else 'YES', '匹配': '✅' if not close_gt_vwap else '❌'},
        {'指标': 'Pivot', '期望': 'NO', '实际': 'NO' if not close_gt_pivot else 'YES', '匹配': '✅' if not close_gt_pivot else '❌'}
    ]
    
    df_matches = pd.DataFrame(matches)
    st.dataframe(df_matches, use_container_width=True)
    
    all_match = all([m['匹配'] == '✅' for m in matches])
    if all_match:
        st.success(f"✅ 完全匹配你的{timeframe}图表！")
        st.balloons()
    else:
        st.warning(f"⚠️ {timeframe}图表部分指标不匹配")
        
        # 显示不匹配的指标
        mismatches = [m['指标'] for m in matches if m['匹配'] == '❌']
        if mismatches:
            st.write(f"不匹配的指标: {', '.join(mismatches)}")
            
            # 提供调整建议
            if 'SuperTrend' in mismatches:
                st.info("💡 SuperTrend不匹配")
                st.write(f"当前SuperTrend值: {st_current:.4f}")
                st.write(f"当前价格: {current_price:.4f}")
                st.write(f"价格 > SuperTrend: {current_price > st_current}")
                st.write(f"所以SuperTrend应该显示: {'YES' if current_price > st_current else 'NO'}")
            
            if 'UT Bot' in mismatches:
                st.info("💡 UT Bot不匹配")
                st.write(f"当前UT止损: {ut_stop_current:.4f}")
                st.write(f"价格 > UT止损: {current_price > ut_stop_current}")
                st.write(f"所以UT Bot应该显示: {'BUY' if current_price > ut_stop_current else 'SELL'}")

# ================= 主循环 =================
current_time = time.time()
if st.session_state.manual_scan or (current_time - st.session_state.last_scan_time > SCAN_INTERVAL):
    analyze()
    st.session_state.last_scan_time = current_time
    st.session_state.manual_scan = False

# ================= 自动刷新 =================
time.sleep(2)
st.rerun()
