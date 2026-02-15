import streamlit as st
import ccxt
import pandas as pd
import pandas_ta as pta
import time
from datetime import datetime, timedelta
from telegram import Bot
import asyncio
import numpy as np

# ================= 配置 =================
EXCHANGE_NAME = 'okx'
TIMEFRAME = '1m'
SCAN_INTERVAL = 30

SYMBOLS = [
    'HYPE/USDT',
    'BTC/USDT',
    'ETH/USDT',
    'SOL/USDT',
    'AAVE/USDT',
    'XRP/USDT',
    'DOGE/USDT',
    'TAO/USDT',
    'RENDER/USDT',
    'SUI/USDT',
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
st.set_page_config(page_title="1min UT Bot调试器", layout="wide")
st.title("🔍 UT Bot信号调试器")
st.caption("直接对比：图表显示BUY vs 代码显示SELL")

# 侧边栏
with st.sidebar:
    st.header("⚙️ 参数")
    scan_interval = st.number_input("扫描间隔(秒)", 5, 60, SCAN_INTERVAL)
    show_all = st.checkbox("显示所有币种", value=True)
    debug_mode = st.checkbox("调试模式", value=True)
    
    if st.button("🔄 立即扫描"):
        st.session_state.manual_scan = True

# 初始化session_state
if 'last_scan_time' not in st.session_state:
    st.session_state.last_scan_time = 0
if 'manual_scan' not in st.session_state:
    st.session_state.manual_scan = False
if 'scan_data' not in st.session_state:
    st.session_state.scan_data = {}

# ================= UT Bot多种实现对比 =================
def ut_bot_simplified(high, low, close, factor=1.0, atr_length=10):
    """
    简化版UT Bot - 最基础的实现
    只比较价格和止损线
    """
    atr = pta.atr(high=high, low=low, close=close, length=atr_length)
    stop_line = close - factor * atr
    return stop_line

def ut_bot_tradingview_style(high, low, close, factor=1.0, atr_length=10):
    """
    模拟TradingView的UT Bot算法
    """
    atr = pta.atr(high=high, low=low, close=close, length=atr_length)
    
    length = len(close)
    stop = np.zeros(length)
    trend = np.zeros(length)
    signal = np.zeros(length)
    
    for i in range(1, length):
        # 计算止损线
        if close.iloc[i] > stop[i-1]:
            stop[i] = max(stop[i-1], close.iloc[i] - factor * atr.iloc[i])
        else:
            stop[i] = min(stop[i-1], close.iloc[i] + factor * atr.iloc[i])
        
        # 确定趋势
        if close.iloc[i] > stop[i]:
            trend[i] = 1
        else:
            trend[i] = -1
        
        # 信号：趋势变化时
        if i > 1 and trend[i] != trend[i-1]:
            signal[i] = trend[i]  # 1=买入, -1=卖出
    
    return pd.Series(stop, index=close.index), pd.Series(trend, index=close.index), pd.Series(signal, index=close.index)

def ut_bot_alternative(high, low, close, factor=1.0, atr_length=10):
    """
    另一种常见实现
    """
    atr = pta.atr(high=high, low=low, close=close, length=atr_length)
    
    length = len(close)
    stop = np.zeros(length)
    trend = np.ones(length)
    
    for i in range(1, length):
        # 基础止损
        base_stop = close.iloc[i] - factor * atr.iloc[i] if trend[i-1] == 1 else close.iloc[i] + factor * atr.iloc[i]
        
        # 平滑止损
        if close.iloc[i] > stop[i-1]:
            stop[i] = max(stop[i-1], base_stop)
        else:
            stop[i] = min(stop[i-1], base_stop)
        
        # 趋势
        trend[i] = 1 if close.iloc[i] > stop[i] else -1
    
    # 信号：趋势变化点
    signal = pd.Series(0, index=close.index)
    signal[trend != pd.Series(trend).shift(1)] = trend
    
    return pd.Series(stop, index=close.index), pd.Series(trend, index=close.index), signal

# ================= 数据获取 =================
@st.cache_data(ttl=30)
def fetch_ohlcv(symbol):
    exchange = ccxt.okx({'enableRateLimit': True})
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=100)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except:
        return None

# ================= 分析函数 =================
def analyze_ut_bot(symbol, df):
    """全面分析UT Bot"""
    if df is None or len(df) < 30:
        return None
    
    high = df['high']
    low = df['low']
    close = df['close']
    
    # 获取最后5根K线
    last_5 = df.tail(5).copy()
    
    # 多种UT Bot实现
    stop1 = ut_bot_simplified(high, low, close)
    stop2, trend2, signal2 = ut_bot_tradingview_style(high, low, close)
    stop3, trend3, signal3 = ut_bot_alternative(high, low, close)
    
    # 计算ATR
    atr = pta.atr(high=high, low=low, close=close, length=UT_ATR_LEN)
    
    # 当前值
    current_close = close.iloc[-1]
    current_atr = atr.iloc[-1]
    
    # 分析结果
    result = {
        'symbol': symbol,
        'timestamp': df['timestamp'].iloc[-1],
        'close': current_close,
        'atr': current_atr,
        'stop_simple': stop1.iloc[-1],
        'stop_tv': stop2.iloc[-1],
        'stop_alt': stop3.iloc[-1],
        'trend_tv': 'BULL' if trend2.iloc[-1] == 1 else 'BEAR',
        'signal_tv': 'BUY' if signal2.iloc[-1] == 1 else ('SELL' if signal2.iloc[-1] == -1 else 'NONE'),
        'trend_alt': 'BULL' if trend3.iloc[-1] == 1 else 'BEAR',
        'signal_alt': 'BUY' if signal3.iloc[-1] == 1 else ('SELL' if signal3.iloc[-1] == -1 else 'NONE'),
    }
    
    # 添加最后5根K线数据用于调试
    last_5_data = []
    for i in range(len(last_5)):
        idx = last_5.index[i]
        last_5_data.append({
            'time': last_5['timestamp'].iloc[i].strftime('%H:%M'),
            'close': last_5['close'].iloc[i],
            'stop_tv': stop2.loc[idx],
            'trend_tv': 'BULL' if trend2.loc[idx] == 1 else 'BEAR',
            'signal_tv': 'BUY' if signal2.loc[idx] == 1 else ('SELL' if signal2.loc[idx] == -1 else 'NONE'),
        })
    
    result['last_5'] = last_5_data
    
    return result

# ================= 主扫描 =================
def perform_scan():
    current_time = datetime.now()
    
    st.session_state.scan_data = {}
    
    status = st.empty()
    status.info(f"🔄 扫描中... {current_time.strftime('%H:%M:%S')}")
    
    progress_bar = st.progress(0)
    
    for i, symbol in enumerate(SYMBOLS):
        df = fetch_ohlcv(symbol)
        if df is not None:
            result = analyze_ut_bot(symbol, df)
            if result:
                st.session_state.scan_data[symbol] = result
        
        progress_bar.progress((i + 1) / len(SYMBOLS))
    
    progress_bar.empty()
    status.success(f"✅ 扫描完成！{len(st.session_state.scan_data)}个币种")

# ================= 主循环 =================
current_time = time.time()
if st.session_state.manual_scan or (current_time - st.session_state.last_scan_time > scan_interval):
    perform_scan()
    st.session_state.last_scan_time = current_time
    st.session_state.manual_scan = False

# ================= 显示结果 =================
if st.session_state.scan_data:
    st.subheader("📊 UT Bot对比分析")
    
    # 创建表格数据
    table_data = []
    for symbol, data in st.session_state.scan_data.items():
        # 判断哪个实现最可能匹配你的图表
        price_vs_stop_tv = data['close'] > data['stop_tv']
        price_vs_stop_simple = data['close'] > data['stop_simple']
        
        table_data.append({
            '交易对': symbol,
            '当前价格': f"{data['close']:.4f}",
            'ATR': f"{data['atr']:.4f}",
            'TV趋势': data['trend_tv'],
            'TV信号': data['signal_tv'],
            'TV价格>止损': '✅' if price_vs_stop_tv else '❌',
            'TV止损价': f"{data['stop_tv']:.4f}",
            '简化版信号': 'BUY' if price_vs_stop_simple else 'SELL',
            '时间': data['timestamp'].strftime('%H:%M:%S')
        })
    
    df_display = pd.DataFrame(table_data)
    st.dataframe(df_display, use_container_width=True)
    
    # ================= 详细调试 =================
    if debug_mode:
        st.subheader("🔍 详细调试（最后5根K线）")
        
        # 选择要调试的币种
        selected = st.selectbox("选择币种查看详细", list(st.session_state.scan_data.keys()))
        
        if selected:
            data = st.session_state.scan_data[selected]
            
            st.write(f"### {selected} 最后5根K线")
            
            # 显示K线数据
            kline_df = pd.DataFrame(data['last_5'])
            st.dataframe(kline_df, use_container_width=True)
            
            # 绘制图表
            st.write("### 价格和止损线")
            
            # 创建图表数据
            chart_data = []
            for k in data['last_5']:
                chart_data.append({
                    '时间': k['time'],
                    '收盘价': k['close'],
                    'TV止损线': k['stop_tv']
                })
            
            chart_df = pd.DataFrame(chart_data)
            
            # 使用Streamlit的线图
            st.line_chart(chart_df.set_index('时间'))
            
            # 显示当前状态
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("当前价格", f"{data['close']:.4f}")
            with col2:
                st.metric("TV止损线", f"{data['stop_tv']:.4f}")
            with col3:
                diff = ((data['close'] - data['stop_tv']) / data['stop_tv'] * 100)
                st.metric("偏离", f"{diff:.2f}%")
            
            # 判断逻辑
            st.write("### 信号判断逻辑")
            
            if data['signal_tv'] == 'BUY':
                st.success("✅ TV算法: BUY信号")
            elif data['signal_tv'] == 'SELL':
                st.error("❌ TV算法: SELL信号")
            else:
                st.info("➖ TV算法: 无信号")
            
            # 解释为什么显示SELL
            st.write("### 为什么显示SELL？")
            
            reasons = []
            if not price_vs_stop_tv:
                reasons.append("❌ 价格低于止损线")
            if data['trend_tv'] == 'BEAR':
                reasons.append("❌ 趋势为空头")
            if data['signal_tv'] == 'SELL':
                reasons.append("❌ 最新信号是SELL")
            elif data['signal_tv'] == 'NONE' and data['trend_tv'] == 'BEAR':
                reasons.append("❌ 处于空头趋势中")
            
            if reasons:
                for r in reasons:
                    st.write(r)
            else:
                st.success("✅ 应该是BUY信号！")
    
    # ================= 统计 =================
    st.subheader("📈 统计")
    
    tv_buy = sum(1 for d in st.session_state.scan_data.values() if d['signal_tv'] == 'BUY')
    tv_sell = sum(1 for d in st.session_state.scan_data.values() if d['signal_tv'] == 'SELL')
    tv_none = sum(1 for d in st.session_state.scan_data.values() if d['signal_tv'] == 'NONE')
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("TV BUY信号", tv_buy)
    with col2:
        st.metric("TV SELL信号", tv_sell)
    with col3:
        st.metric("TV 无信号", tv_none)
    with col4:
        st.metric("总币种", len(st.session_state.scan_data))

# ================= 自动刷新 =================
time.sleep(2)
st.rerun()

# ================= 手动控制 =================
st.markdown("---")
if st.button("停止自动刷新"):
    st.stop()
