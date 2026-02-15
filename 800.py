import streamlit as st
import ccxt
import pandas as pd
import pandas_ta as pta
import time
from datetime import datetime
from telegram import Bot
import asyncio
import numpy as np

# ================= 配置 =================
EXCHANGE_NAME = 'okx'
TIMEFRAME = '1m'
SCAN_INTERVAL = 30

SYMBOLS = [
    'BTC/USDT',
    'ETH/USDT',
    'SOL/USDT',  # 重点关注SOL
    'HYPE/USDT',
    'AAVE/USDT',
    'XRP/USDT',
    'DOGE/USDT',
]

# Telegram配置
TELEGRAM_TOKEN = st.secrets.get("TELEGRAM_TOKEN", "YOUR_BOT_TOKEN_HERE")
TELEGRAM_CHAT_ID = st.secrets.get("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID_HERE")

# 指标参数
UT_FACTOR = 1.0
UT_ATR_LEN = 10
ST_ATR_LEN = 10
ST_MULTIPLIER = 3.0

# ================= 初始化 =================
def init_bot():
    if TELEGRAM_TOKEN and TELEGRAM_TOKEN != "YOUR_BOT_TOKEN_HERE":
        try:
            return Bot(token=TELEGRAM_TOKEN)
        except:
            return None
    return None

bot = init_bot()

# ================= UI =================
st.set_page_config(page_title="OKX 1min - 精确匹配图表", layout="wide")
st.title("📊 精确匹配你的图表 (SOL应该显示SuperTrend YES, UT Bot BUY)")

# 侧边栏
with st.sidebar:
    st.header("⚙️ 参数")
    scan_interval = st.number_input("扫描间隔(秒)", 5, 60, SCAN_INTERVAL)
    
    st.header("📈 指标参数")
    ut_factor = st.slider("UT Factor", 0.5, 3.0, UT_FACTOR, 0.1)
    ut_atr_len = st.slider("UT ATR长度", 5, 20, UT_ATR_LEN)
    st_atr_len = st.slider("ST ATR长度", 5, 20, ST_ATR_LEN)
    st_multiplier = st.slider("ST乘数", 1.0, 5.0, ST_MULTIPLIER, 0.5)
    
    if st.button("🔄 立即扫描"):
        st.session_state.manual_scan = True

# 初始化
if 'last_scan_time' not in st.session_state:
    st.session_state.last_scan_time = 0
if 'manual_scan' not in st.session_state:
    st.session_state.manual_scan = False
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = []
if 'scan_count' not in st.session_state:
    st.session_state.scan_count = 0
if 'debug_data' not in st.session_state:
    st.session_state.debug_data = {}

# ================= 数据获取 =================
@st.cache_data(ttl=10)
def fetch_ohlcv(symbol):
    try:
        exchange = ccxt.okx({
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'}
        })
        ohlcv = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=200)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        return None

# ================= UT Bot精确实现 =================
def calculate_ut_bot_exact(high, low, close, factor=1.0, atr_length=10):
    """完全匹配Pine Script的UT Bot"""
    atr = pta.atr(high=high, low=low, close=close, length=atr_length)
    
    length = len(close)
    ut_stop = np.zeros(length)
    ut_stop[0] = close.iloc[0] - factor * atr.iloc[0]
    
    for i in range(1, length):
        if close.iloc[i] > ut_stop[i-1]:
            ut_stop[i] = max(ut_stop[i-1], close.iloc[i] - factor * atr.iloc[i])
        else:
            ut_stop[i] = min(ut_stop[i-1], close.iloc[i] + factor * atr.iloc[i])
    
    return pd.Series(ut_stop, index=close.index)

# ================= 计算指标 =================
def calculate_indicators(df, symbol):
    """计算所有指标，专门匹配你的图表"""
    
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
    
    ema10_gt_20 = ema10.iloc[-1] > ema20.iloc[-1] if not pd.isna(ema10.iloc[-1]) and not pd.isna(ema20.iloc[-1]) else False
    close_gt_ema50 = close.iloc[-1] > ema50.iloc[-1] if not pd.isna(ema50.iloc[-1]) else False
    close_gt_ema200 = close.iloc[-1] > ema200.iloc[-1] if not pd.isna(ema200.iloc[-1]) else False
    
    #━━━━━━━━━━━━━━━━━━━━━━
    # 2. SuperTrend (关键修复)
    #━━━━━━━━━━━━━━━━━━━━━━
    st = pta.supertrend(
        high=high, 
        low=low, 
        close=close, 
        length=st_atr_len, 
        multiplier=st_multiplier
    )
    
    # 打印所有列名用于调试
    if symbol == 'SOL/USDT':
        st.session_state.debug_data['st_columns'] = list(st.columns)
    
    # 查找SuperTrend列 - 多种可能
    super_trend_col = None
    super_trend_dir_col = None
    
    for col in st.columns:
        if f'SUPERT_{st_atr_len}_{st_multiplier:.1f}' in col:
            super_trend_col = col
        elif 'SUPERTd' in col:
            super_trend_dir_col = col
    
    # 如果没有找到标准列名，尝试其他格式
    if not super_trend_col:
        for col in st.columns:
            if 'SUPERT_' in col and not 'd' in col:
                super_trend_col = col
                break
    
    # SuperTrend多头判断
    st_bull = False
    super_trend_value = None
    
    if super_trend_col and super_trend_col in st.columns:
        super_trend_value = st[super_trend_col].iloc[-1]
        if not pd.isna(super_trend_value):
            st_bull = close.iloc[-1] > super_trend_value
    
    # 如果找不到价格列，使用方向列
    if not st_bull and super_trend_dir_col and super_trend_dir_col in st.columns:
        st_bull = st[super_trend_dir_col].iloc[-1] == 1
    
    #━━━━━━━━━━━━━━━━━━━━━━
    # 3. UT Bot (关键修复)
    #━━━━━━━━━━━━━━━━━━━━━━
    ut_stop_series = calculate_ut_bot_exact(high, low, close, ut_factor, ut_atr_len)
    current_ut_stop = ut_stop_series.iloc[-1]
    
    # UT Bot多头判断 - 这就是图表上显示的BUY/SELL
    ut_bull = close.iloc[-1] > current_ut_stop
    
    # UT历史用于信号
    ut_bull_history = close > ut_stop_series
    ut_bull_change = False
    if len(ut_bull_history) > 1:
        ut_bull_change = ut_bull_history.iloc[-1] and not ut_bull_history.iloc[-2]
    
    #━━━━━━━━━━━━━━━━━━━━━━
    # 4. 买卖信号
    #━━━━━━━━━━━━━━━━━━━━━━
    buy_signal = ut_bull_change and ema10_gt_20
    sell_signal = False
    if len(ut_bull_history) > 1:
        sell_signal = not ut_bull_history.iloc[-1] and ut_bull_history.iloc[-2]
    
    #━━━━━━━━━━━━━━━━━━━━━━
    # 5. VWAP
    #━━━━━━━━━━━━━━━━━━━━━━
    typical = (high + low + close) / 3
    vwap = (typical * volume).cumsum() / volume.cumsum()
    vwap_value = vwap.iloc[-1] if len(vwap) > 0 else None
    close_gt_vwap = close.iloc[-1] > vwap_value if vwap_value is not None else False
    
    #━━━━━━━━━━━━━━━━━━━━━━
    # 6. Today Pivot
    #━━━━━━━━━━━━━━━━━━━━━━
    last_24h = df.tail(100)
    d_high = last_24h['high'].max()
    d_low = last_24h['low'].min()
    d_close = last_24h['close'].iloc[-1]
    today_pivot = (d_high + d_low + d_close) / 3
    close_gt_pivot = close.iloc[-1] > today_pivot
    
    # 保存调试数据
    if symbol == 'SOL/USDT':
        st.session_state.debug_data = {
            'close': close.iloc[-1],
            'ut_stop': current_ut_stop,
            'ut_bull': ut_bull,
            'super_trend_value': super_trend_value,
            'st_bull': st_bull,
            'ema10': ema10.iloc[-1],
            'ema20': ema20.iloc[-1],
            'vwap': vwap_value,
            'pivot': today_pivot
        }
    
    return {
        'ema10_gt_20': ema10_gt_20,
        'close_gt_ema50': close_gt_ema50,
        'close_gt_ema200': close_gt_ema200,
        'st_bull': st_bull,
        'ut_bull': ut_bull,
        'ut_stop': current_ut_stop,
        'buy_signal': buy_signal,
        'sell_signal': sell_signal,
        'close_gt_vwap': close_gt_vwap,
        'vwap': vwap_value,
        'close_gt_pivot': close_gt_pivot,
        'today_pivot': today_pivot,
        'close': close.iloc[-1]
    }

# ================= 执行扫描 =================
def perform_scan():
    st.session_state.scan_count += 1
    current_time = datetime.now()
    
    st.session_state.scan_results = []
    
    status = st.empty()
    status.info(f"🔄 第{st.session_state.scan_count}次扫描 {current_time.strftime('%H:%M:%S')}")
    
    progress_bar = st.progress(0)
    
    for i, symbol in enumerate(SYMBOLS):
        df = fetch_ohlcv(symbol)
        if df is not None and len(df) >= 50:
            ind = calculate_indicators(df, symbol)
            
            # 格式化价格
            if 'BTC' in symbol:
                price_str = f"${ind['close']:,.2f}"
                stop_str = f"${ind['ut_stop']:,.2f}" if not np.isnan(ind['ut_stop']) else "N/A"
            else:
                price_str = f"${ind['close']:.4f}"
                stop_str = f"${ind['ut_stop']:.4f}" if not np.isnan(ind['ut_stop']) else "N/A"
            
            # UT信号显示
            ut_signal = '—'
            if ind['buy_signal']:
                ut_signal = 'BUY🔥'
            elif ind['sell_signal']:
                ut_signal = 'SELL⚠️'
            
            # 全绿判断
            all_green = all([
                ind['ema10_gt_20'],
                ind['st_bull'],
                ind['ut_bull'],
                ind['close_gt_vwap']
            ])
            
            result = {
                '交易对': symbol,
                '时间': current_time.strftime('%H:%M:%S'),
                '价格': price_str,
                'EMA10>20': '✅' if ind['ema10_gt_20'] else '❌',
                'EMA50': '✅' if ind['close_gt_ema50'] else '❌',
                'EMA200': '✅' if ind['close_gt_ema200'] else '❌',
                'SuperTrend': '✅' if ind['st_bull'] else '❌',  # 这里应该是YES/NO
                'UT Bot': 'BUY' if ind['ut_bull'] else 'SELL',  # 这里应该是BUY/SELL
                'UT信号': ut_signal,
                'VWAP': '✅' if ind['close_gt_vwap'] else '❌',
                'Pivot': '✅' if ind['close_gt_pivot'] else '❌',
                '全绿': '✅' if all_green else '❌',
                'UT止损': stop_str,
                '价格>止损': '✅' if ind['ut_bull'] else '❌'
            }
            
            st.session_state.scan_results.append(result)
        
        progress_bar.progress((i + 1) / len(SYMBOLS))
    
    progress_bar.empty()
    status.success(f"✅ 完成！")

# ================= 主循环 =================
current_time = time.time()
if st.session_state.manual_scan or (current_time - st.session_state.last_scan_time > scan_interval):
    perform_scan()
    st.session_state.last_scan_time = current_time
    st.session_state.manual_scan = False

# ================= 显示结果 =================
if st.session_state.scan_results:
    st.subheader("📊 扫描结果")
    
    # 转换为DataFrame并高亮SOL
    df_results = pd.DataFrame(st.session_state.scan_results)
    
    def highlight_sol(row):
        if row['交易对'] == 'SOL/USDT':
            return ['background-color: #90EE90'] * len(row)
        return [''] * len(row)
    
    styled_df = df_results.style.apply(highlight_sol, axis=1)
    st.dataframe(styled_df, use_container_width=True, height=400)

# ================= SOL详细调试 =================
st.subheader("🔍 SOL/USDT 详细调试")

if st.session_state.debug_data:
    d = st.session_state.debug_data
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("当前价格", f"${d['close']:.4f}")
        st.metric("UT止损", f"${d['ut_stop']:.4f}")
        st.metric("UT状态", "BUY ✅" if d['ut_bull'] else "SELL ❌")
    
    with col2:
        st.metric("SuperTrend值", f"${d['super_trend_value']:.4f}" if d['super_trend_value'] else "N/A")
        st.metric("SuperTrend状态", "YES ✅" if d['st_bull'] else "NO ❌")
        st.metric("EMA10", f"${d['ema10']:.4f}")
    
    with col3:
        st.metric("EMA20", f"${d['ema20']:.4f}")
        st.metric("VWAP", f"${d['vwap']:.4f}" if d['vwap'] else "N/A")
        st.metric("Pivot", f"${d['pivot']:.4f}")
    
    # 显示应该是什么
    st.write("### 应该显示的数值")
    st.json({
        "你的图表显示": {
            "EMA10>20": "YES",
            "SuperTrend": "YES",
            "UT Bot": "BUY"
        },
        "当前计算": {
            "EMA10>20": "YES" if d['ema10'] > d['ema20'] else "NO",
            "SuperTrend": "YES" if d['st_bull'] else "NO",
            "UT Bot": "BUY" if d['ut_bull'] else "SELL"
        }
    })
    
    # 如果还是不匹配，显示计算过程
    if not d['st_bull']:
        st.error("SuperTrend计算可能有问题")
        st.write(f"最后价格: {d['close']:.4f}")
        st.write(f"SuperTrend值: {d['super_trend_value']:.4f}")
        st.write(f"价格 > SuperTrend: {d['close'] > d['super_trend_value'] if d['super_trend_value'] else False}")
    
    if not d['ut_bull']:
        st.error("UT Bot计算可能有问题")
        st.write(f"最后价格: {d['close']:.4f}")
        st.write(f"UT止损: {d['ut_stop']:.4f}")
        st.write(f"价格 > UT止损: {d['close'] > d['ut_stop']}")

# ================= 图表对比 =================
st.subheader("📊 与你的图表对比")

col1, col2 = st.columns(2)

with col1:
    st.write("### 你的图表显示")
    chart_data = pd.DataFrame({
        '指标': ['EMA10>20', 'SuperTrend', 'UT Bot', 'VWAP', 'Pivot'],
        '状态': ['YES', 'YES', 'BUY', 'NO', 'NO']
    })
    st.dataframe(chart_data)

with col2:
    st.write("### 当前扫描器显示")
    sol_data = next((r for r in st.session_state.scan_results if r['交易对'] == 'SOL/USDT'), None)
    if sol_data:
        scanner_data = pd.DataFrame({
            '指标': ['EMA10>20', 'SuperTrend', 'UT Bot', 'VWAP', 'Pivot'],
            '状态': [
                sol_data['EMA10>20'],
                sol_data['SuperTrend'],
                sol_data['UT Bot'],
                sol_data['VWAP'],
                sol_data['Pivot']
            ]
        })
        st.dataframe(scanner_data)

# ================= 自动刷新 =================
time.sleep(2)
st.rerun()
