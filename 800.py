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
EXCHANGE_NAME = 'binance'  # 改为Binance匹配你的截图
TIMEFRAME = '1m'
SCAN_INTERVAL = 30

SYMBOLS = [
    'BTC/USDT',  # 只测试BTC先
    'HYPE/USDT',
    'ETH/USDT',
    'SOL/USDT',
]

# Telegram配置
TELEGRAM_TOKEN = st.secrets.get("TELEGRAM_TOKEN", "YOUR_BOT_TOKEN_HERE")
TELEGRAM_CHAT_ID = st.secrets.get("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID_HERE")

# 指标参数 - 完全匹配Pine Script
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
st.set_page_config(page_title="UT Bot修复版 - 匹配图表", layout="wide")
st.title("📊 UT Bot修复版 (应该显示BUY)")

# 侧边栏
with st.sidebar:
    st.header("⚙️ 参数")
    scan_interval = st.number_input("扫描间隔(秒)", 5, 60, SCAN_INTERVAL)
    
    st.header("📈 UT参数")
    ut_factor = st.slider("UT Factor", 0.5, 3.0, UT_FACTOR, 0.1)
    ut_atr_len = st.slider("UT ATR长度", 5, 20, UT_ATR_LEN)
    
    if st.button("🔄 立即扫描"):
        st.session_state.manual_scan = True

# 初始化
if 'last_scan_time' not in st.session_state:
    st.session_state.last_scan_time = 0
if 'manual_scan' not in st.session_state:
    st.session_state.manual_scan = False
if 'btc_data' not in st.session_state:
    st.session_state.btc_data = None
if 'debug_info' not in st.session_state:
    st.session_state.debug_info = {}

# ================= UT Bot精确实现 =================
def calculate_ut_bot_exact(high, low, close, factor=1.0, atr_length=10):
    """
    完全匹配Pine Script的UT Bot实现
    """
    # 计算ATR
    atr = pta.atr(high=high, low=low, close=close, length=atr_length)
    
    # 初始化UT Stop
    length = len(close)
    ut_stop = np.zeros(length)
    ut_stop[0] = close.iloc[0] - factor * atr.iloc[0]
    
    # UT Bull状态
    ut_bull = np.zeros(length, dtype=bool)
    ut_bull[0] = close.iloc[0] > ut_stop[0]
    
    # 按照Pine Script逻辑逐根K线计算
    for i in range(1, length):
        # 计算UT Stop - 完全按照Pine Script
        # utStop := close > utStop[1] ? math.max(utStop[1], close - utFactor * atr) : math.min(utStop[1], close + utFactor * atr)
        if close.iloc[i] > ut_stop[i-1]:
            ut_stop[i] = max(ut_stop[i-1], close.iloc[i] - factor * atr.iloc[i])
        else:
            ut_stop[i] = min(ut_stop[i-1], close.iloc[i] + factor * atr.iloc[i])
        
        # UT Bull状态: close > utStop
        ut_bull[i] = close.iloc[i] > ut_stop[i]
    
    return pd.Series(ut_stop, index=close.index), pd.Series(ut_bull, index=close.index)

# ================= 数据获取 =================
@st.cache_data(ttl=10)  # 10秒缓存，更实时
def fetch_ohlcv(symbol):
    try:
        exchange = ccxt.binance({
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'}
        })
        ohlcv = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=100)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        st.error(f"获取{symbol}失败: {e}")
        return None

# ================= 只分析BTC =================
def analyze_btc():
    """专门分析BTC，显示详细调试信息"""
    
    # 获取BTC数据
    df = fetch_ohlcv('BTC/USDT')
    if df is None or len(df) < 30:
        st.error("无法获取BTC数据")
        return
    
    # 计算UT Bot
    ut_stop, ut_bull = calculate_ut_bot_exact(
        df['high'], df['low'], df['close'], 
        ut_factor, ut_atr_len
    )
    
    # 当前值
    current_close = df['close'].iloc[-1]
    current_stop = ut_stop.iloc[-1]
    current_bull = ut_bull.iloc[-1]
    
    # 最后10根K线数据
    last_10 = pd.DataFrame({
        '时间': df['timestamp'].tail(10).dt.strftime('%H:%M:%S'),
        '收盘价': df['close'].tail(10).round(2),
        'UT止损': ut_stop.tail(10).round(2),
        '价格>止损': ut_bull.tail(10),
        'UT状态': ut_bull.tail(10).map({True: 'BUY', False: 'SELL'})
    })
    
    # 保存到session_state
    st.session_state.btc_data = {
        'close': current_close,
        'stop': current_stop,
        'bull': current_bull,
        'last_10': last_10,
        'df': df,
        'ut_stop': ut_stop,
        'ut_bull': ut_bull
    }

# ================= 主循环 =================
current_time = time.time()
if st.session_state.manual_scan or (current_time - st.session_state.last_scan_time > scan_interval):
    analyze_btc()
    st.session_state.last_scan_time = current_time
    st.session_state.manual_scan = False

# ================= 显示结果 =================
st.subheader("🎯 BTC/USDT UT Bot状态")

if st.session_state.btc_data:
    data = st.session_state.btc_data
    
    # 创建三列显示关键指标
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "当前价格", 
            f"${data['close']:,.2f}",
            delta=None
        )
    
    with col2:
        st.metric(
            "UT止损线", 
            f"${data['stop']:,.2f}",
            delta=None
        )
    
    with col3:
        diff = ((data['close'] - data['stop']) / data['stop'] * 100)
        st.metric(
            "偏离", 
            f"{diff:+.2f}%",
            delta=None
        )
    
    with col4:
        # 这里就是关键 - 根据ut_bull显示BUY/SELL
        status = "BUY ✅" if data['bull'] else "SELL ❌"
        status_color = "green" if data['bull'] else "red"
        st.markdown(
            f"<h3 style='color: {status_color}; text-align: center;'>UT状态: {status}</h3>", 
            unsafe_allow_html=True
        )
    
    # 显示最后10根K线的详细数据
    st.subheader("📊 最后10根K线分析")
    
    # 添加高亮
    def highlight_buy(row):
        if row['UT状态'] == 'BUY':
            return ['background-color: #90EE90'] * len(row)
        return [''] * len(row)
    
    styled_df = data['last_10'].style.apply(highlight_buy, axis=1)
    st.dataframe(styled_df, use_container_width=True)
    
    # 绘制图表
    st.subheader("📈 价格与UT止损线")
    
    # 准备图表数据
    chart_df = pd.DataFrame({
        '时间': data['df']['timestamp'].tail(30).dt.strftime('%H:%M'),
        '价格': data['df']['close'].tail(30),
        'UT止损': data['ut_stop'].tail(30)
    }).set_index('时间')
    
    st.line_chart(chart_df)
    
    # 调试信息
    with st.expander("🔍 调试信息"):
        st.write("### 当前计算详情")
        st.write(f"- 最后价格: {data['close']:.2f}")
        st.write(f"- 最后止损: {data['stop']:.2f}")
        st.write(f"- 价格 > 止损: {data['bull']}")
        st.write(f"- 偏离百分比: {((data['close'] - data['stop']) / data['stop'] * 100):.4f}%")
        
        # 显示最后几根K线的原始数据
        st.write("### 最后5根K线原始数据")
        last_5_raw = data['df'][['timestamp', 'open', 'high', 'low', 'close']].tail(5)
        last_5_raw['timestamp'] = last_5_raw['timestamp'].dt.strftime('%H:%M:%S')
        st.dataframe(last_5_raw)
        
        st.write("### UT Stop计算过程")
        calc_data = []
        for i in range(-5, 0):
            idx = data['df'].index[i]
            calc_data.append({
                '位置': i,
                'close': data['df']['close'].iloc[i],
                'ut_stop': data['ut_stop'].iloc[i],
                'bull': data['ut_bull'].iloc[i]
            })
        st.dataframe(pd.DataFrame(calc_data))

else:
    st.info("等待首次扫描...")

# ================= 手动测试 =================
st.markdown("---")
st.subheader("🧪 手动测试")

col1, col2 = st.columns(2)

with col1:
    test_price = st.number_input("测试价格", value=69000.0, step=10.0)
    test_stop = st.number_input("测试止损", value=68950.0, step=10.0)
    
    if st.button("测试UT状态"):
        test_bull = test_price > test_stop
        st.write(f"测试结果: {'BUY' if test_bull else 'SELL'}")
        st.write(f"价格 > 止损: {test_bull}")

with col2:
    st.write("### 判断逻辑")
    st.write("UT Bot行显示:")
    st.write("- **BUY**: 价格 > UT止损线")
    st.write("- **SELL**: 价格 < UT止损线")
    st.write("")
    st.write("所以如果价格是69,058，止损是69,006：")
    st.write("69,058 > 69,006 = **BUY** ✅")

# ================= 自动刷新 =================
time.sleep(2)
st.rerun()
