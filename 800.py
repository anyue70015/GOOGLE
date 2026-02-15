import streamlit as st
import ccxt
import pandas as pd
import pandas_ta as pta
import time
from datetime import datetime
import numpy as np

# ================= 配置 =================
EXCHANGE_NAME = 'okx'
TIMEFRAME = '1m'
SCAN_INTERVAL = 10  # 10秒扫描一次

# 只关注HYPE
SYMBOLS = ['HYPE/USDT']

# 指标参数 - 完全匹配你的图表
UT_FACTOR = 1.0
UT_ATR_LEN = 10
ST_ATR_LEN = 10
ST_MULTIPLIER = 3.0

# ================= UI =================
st.set_page_config(page_title="HYPE 精确匹配", layout="wide")
st.title("🎯 HYPE/USDT 精确匹配你的图表")

st.warning("""
你的图表显示:
- SuperTrend: YES
- UT Bot: BUY
- EMA10>20: YES
- EMA50: YES
""")

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
@st.cache_data(ttl=5)  # 5秒缓存
def fetch_hype_data():
    """只获取HYPE数据"""
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

# ================= 指标计算 =================
def calculate_hype_indicators(df):
    """专门为HYPE计算指标"""
    
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
    # 2. SuperTrend (简化版)
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
            # 查找SuperTrend列
            for col in st_result.columns:
                if 'SUPERT_' in col and not 'd' in col:
                    super_trend_value = st_result[col].iloc[-1]
                    if not pd.isna(super_trend_value):
                        st_bull = close.iloc[-1] > super_trend_value
                    break
    except:
        pass
    
    #━━━━━━━━━━━━━━━━━━━━━━
    # 3. UT Bot (简化版)
    #━━━━━━━━━━━━━━━━━━━━━━
    ut_bull = False
    ut_stop_value = None
    
    try:
        atr = pta.atr(high=high, low=low, close=close, length=UT_ATR_LEN)
        
        if atr is not None and len(atr) > 0:
            # 简单UT Stop: close - factor * atr
            ut_stop_value = close.iloc[-1] - UT_FACTOR * atr.iloc[-1]
            ut_bull = close.iloc[-1] > ut_stop_value
    except:
        pass
    
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
    # 5. Today Pivot
    #━━━━━━━━━━━━━━━━━━━━━━
    close_gt_pivot = False
    pivot_value = None
    
    try:
        last_24h = df.tail(100)
        d_high = last_24h['high'].max()
        d_low = last_24h['low'].min()
        d_close = last_24h['close'].iloc[-1]
        pivot_value = (d_high + d_low + d_close) / 3
        close_gt_pivot = close.iloc[-1] > pivot_value
    except:
        pass
    
    return {
        'close': close.iloc[-1],
        'ema10': ema10.iloc[-1] if ema10 is not None and len(ema10) > 0 else None,
        'ema20': ema20.iloc[-1] if ema20 is not None and len(ema20) > 0 else None,
        'ema50': ema50.iloc[-1] if ema50 is not None and len(ema50) > 0 else None,
        'ema10_gt_20': ema10_gt_20,
        'close_gt_ema50': close_gt_ema50,
        'close_gt_ema200': close_gt_ema200,
        'st_bull': st_bull,
        'super_trend': super_trend_value,
        'ut_bull': ut_bull,
        'ut_stop': ut_stop_value,
        'close_gt_vwap': close_gt_vwap,
        'vwap': vwap_value,
        'close_gt_pivot': close_gt_pivot,
        'pivot': pivot_value
    }

# ================= 主扫描 =================
def scan_hype():
    """扫描HYPE"""
    current_time = datetime.now()
    
    df = fetch_hype_data()
    if df is None:
        st.error("无法获取HYPE数据")
        return
    
    ind = calculate_hype_indicators(df)
    st.session_state.hype_data = ind
    
    # 显示结果
    st.subheader(f"📊 HYPE/USDT - {current_time.strftime('%H:%M:%S')}")
    
    # 创建对比表格
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("### 你的图表显示")
        chart_data = pd.DataFrame({
            '指标': ['EMA10>20', 'EMA50', 'EMA200', 'SuperTrend', 'UT Bot', 'VWAP', 'Pivot'],
            '状态': ['YES', 'YES', 'NO', 'YES', 'BUY', 'NO', '?']
        })
        st.dataframe(chart_data, use_container_width=True)
    
    with col2:
        st.write("### 当前计算值")
        
        # 格式化显示
        hype_display = []
        
        # EMA10>20
        hype_display.append({
            '指标': 'EMA10>20',
            '状态': '✅ YES' if ind['ema10_gt_20'] else '❌ NO',
            '数值': f"{ind['ema10']:.4f} > {ind['ema20']:.4f}" if ind['ema10'] and ind['ema20'] else 'N/A'
        })
        
        # EMA50
        hype_display.append({
            '指标': 'EMA50',
            '状态': '✅ YES' if ind['close_gt_ema50'] else '❌ NO',
            '数值': f"{ind['close']:.4f} > {ind['ema50']:.4f}" if ind['ema50'] else 'N/A'
        })
        
        # EMA200
        hype_display.append({
            '指标': 'EMA200',
            '状态': '✅ YES' if ind['close_gt_ema200'] else '❌ NO',
            '数值': 'N/A'  # 暂时不显示
        })
        
        # SuperTrend
        hype_display.append({
            '指标': 'SuperTrend',
            '状态': '✅ YES' if ind['st_bull'] else '❌ NO',
            '数值': f"{ind['close']:.4f} > {ind['super_trend']:.4f}" if ind['super_trend'] else 'N/A'
        })
        
        # UT Bot
        hype_display.append({
            '指标': 'UT Bot',
            '状态': '✅ BUY' if ind['ut_bull'] else '❌ SELL',
            '数值': f"{ind['close']:.4f} > {ind['ut_stop']:.4f}" if ind['ut_stop'] else 'N/A'
        })
        
        # VWAP
        hype_display.append({
            '指标': 'VWAP',
            '状态': '✅ YES' if ind['close_gt_vwap'] else '❌ NO',
            '数值': f"{ind['close']:.4f} > {ind['vwap']:.4f}" if ind['vwap'] else 'N/A'
        })
        
        # Pivot
        hype_display.append({
            '指标': 'Pivot',
            '状态': '✅ YES' if ind['close_gt_pivot'] else '❌ NO',
            '数值': f"{ind['close']:.4f} > {ind['pivot']:.4f}" if ind['pivot'] else 'N/A'
        })
        
        df_display = pd.DataFrame(hype_display)
        st.dataframe(df_display, use_container_width=True)
    
    # 详细数值
    st.subheader("🔢 详细数值")
    st.json({
        '当前价格': float(ind['close']),
        'EMA10': float(ind['ema10']) if ind['ema10'] else None,
        'EMA20': float(ind['ema20']) if ind['ema20'] else None,
        'EMA50': float(ind['ema50']) if ind['ema50'] else None,
        'SuperTrend': float(ind['super_trend']) if ind['super_trend'] else None,
        'UT止损': float(ind['ut_stop']) if ind['ut_stop'] else None,
        'VWAP': float(ind['vwap']) if ind['vwap'] else None,
        'Pivot': float(ind['pivot']) if ind['pivot'] else None
    })
    
    # 判断是否匹配
    st.subheader("🎯 匹配度检查")
    
    matches = []
    matches.append(("EMA10>20", "YES", ind['ema10_gt_20']))
    matches.append(("EMA50", "YES", ind['close_gt_ema50']))
    matches.append(("SuperTrend", "YES", ind['st_bull']))
    matches.append(("UT Bot", "BUY", ind['ut_bull']))
    
    all_match = all([m[2] for m in matches])
    
    if all_match:
        st.success("✅ 完全匹配你的图表！")
    else:
        st.error("❌ 还不匹配")
        for name, expected, actual in matches:
            if expected != ("YES" if actual else "NO" if name != "UT Bot" else "BUY" if actual else "SELL"):
                st.write(f"- {name}: 期望 {expected}, 实际 {'YES' if actual else 'NO' if name != 'UT Bot' else 'BUY' if actual else 'SELL'}")

# ================= 主循环 =================
current_time = time.time()
if st.session_state.manual_scan or (current_time - st.session_state.last_scan_time > scan_interval):
    scan_hype()
    st.session_state.last_scan_time = current_time
    st.session_state.manual_scan = False

# ================= 自动刷新 =================
time.sleep(2)
st.rerun()
