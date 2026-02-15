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
st.set_page_config(page_title="1min 扫描器 - Pine Script匹配版", layout="wide")
st.title("📊 1分钟扫描器 (完全匹配Pine Script)")

# 侧边栏
with st.sidebar:
    st.header("⚙️ 参数")
    scan_interval = st.number_input("扫描间隔(秒)", 5, 60, SCAN_INTERVAL)
    
    st.header("📈 指标参数")
    ut_factor = st.slider("UT Factor", 0.5, 3.0, UT_FACTOR, 0.1)
    ut_atr_len = st.slider("UT ATR长度", 5, 20, UT_ATR_LEN)
    st_atr_len = st.slider("SuperTrend ATR长度", 5, 20, ST_ATR_LEN)
    st_multiplier = st.slider("SuperTrend乘数", 1.0, 5.0, ST_MULTIPLIER, 0.5)
    
    st.header("🔔 通知")
    enable_telegram = st.checkbox("启用Telegram", value=bot is not None)
    
    if st.button("🔄 立即扫描"):
        st.session_state.manual_scan = True

# 初始化session_state
if 'last_scan_time' not in st.session_state:
    st.session_state.last_scan_time = 0
if 'manual_scan' not in st.session_state:
    st.session_state.manual_scan = False
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = []
if 'scan_count' not in st.session_state:
    st.session_state.scan_count = 0

# ================= Pine Script指标实现 =================
def calculate_pine_indicators(df):
    """
    完全匹配Pine Script指标计算
    """
    close = df['close']
    high = df['high']
    low = df['low']
    volume = df['volume']
    
    #━━━━━━━━━━━━━━━━━━━━━━
    # EMA (完全匹配Pine)
    #━━━━━━━━━━━━━━━━━━━━━━
    ema10 = pta.ema(close, length=10)
    ema20 = pta.ema(close, length=20)
    ema50 = pta.ema(close, length=50)
    ema200 = pta.ema(close, length=200)
    
    # EMA CROSS
    ema_bull_cross = (ema10 > ema20) & (ema10.shift(1) <= ema20.shift(1))
    ema_bear_cross = (ema10 < ema20) & (ema10.shift(1) >= ema20.shift(1))
    
    #━━━━━━━━━━━━━━━━━━━━━━
    # SUPERTREND (完全匹配Pine)
    #━━━━━━━━━━━━━━━━━━━━━━
    st = pta.supertrend(
        high=high, 
        low=low, 
        close=close, 
        length=st_atr_len, 
        multiplier=st_multiplier
    )
    
    # 找到SuperTrend列
    st_col = f'SUPERT_{st_atr_len}_{st_multiplier:.1f}'
    if st_col not in st.columns:
        # 尝试其他可能的列名
        for col in st.columns:
            if 'SUPERT_' in col:
                st_col = col
                break
    
    super_trend = st[st_col] if st_col in st.columns else pd.Series(index=close.index)
    st_bull = close > super_trend
    
    #━━━━━━━━━━━━━━━━━━━━━━
    # UT BOT (完全匹配Pine Script算法)
    #━━━━━━━━━━━━━━━━━━━━━━
    atr = pta.atr(high=high, low=low, close=close, length=ut_atr_len)
    
    # 初始化UT Stop数组
    ut_stop = np.zeros(len(close))
    ut_stop[0] = close.iloc[0] - ut_factor * atr.iloc[0]
    
    # 按照Pine Script逻辑计算UT Stop
    for i in range(1, len(close)):
        if close.iloc[i] > ut_stop[i-1]:
            ut_stop[i] = max(ut_stop[i-1], close.iloc[i] - ut_factor * atr.iloc[i])
        else:
            ut_stop[i] = min(ut_stop[i-1], close.iloc[i] + ut_factor * atr.iloc[i])
    
    ut_stop_series = pd.Series(ut_stop, index=close.index)
    ut_bull = close > ut_stop_series
    ut_bear = close < ut_stop_series
    
    # UT Bull变化检测 (用于信号)
    ut_bull_change = ut_bull & ~ut_bull.shift(1).fillna(False)
    
    #━━━━━━━━━━━━━━━━━━━━━━
    # BUY/SELL 信号 (完全匹配Pine)
    #━━━━━━━━━━━━━━━━━━━━━━
    # buySignal = utBull and not utBull[1] and ema10 > ema20
    buy_signal = ut_bull_change & (ema10 > ema20)
    
    # sellSignal = utBear and not utBear[1]
    sell_signal = ut_bear & ~ut_bear.shift(1).fillna(False)
    
    #━━━━━━━━━━━━━━━━━━━━━━
    # VWAP (完全匹配Pine)
    #━━━━━━━━━━━━━━━━━━━━━━
    typical = (high + low + close) / 3
    vwap = (typical * volume).cumsum() / volume.cumsum()
    
    #━━━━━━━━━━━━━━━━━━━━━━
    # TODAY PIVOT (简化版，因为没有日线数据)
    #━━━━━━━━━━━━━━━━━━━━━━
    # 使用最近24小时的high/low/close模拟
    last_24h = df.tail(1440)  # 1分钟K线，1440根=24小时
    if len(last_24h) > 0:
        d_high = last_24h['high'].max()
        d_low = last_24h['low'].min()
        d_close = last_24h['close'].iloc[-1]
        today_pivot = (d_high + d_low + d_close) / 3
    else:
        today_pivot = close.iloc[-1]
    
    return {
        'ema10': ema10,
        'ema20': ema20,
        'ema50': ema50,
        'ema200': ema200,
        'ema10_gt_20': ema10.iloc[-1] > ema20.iloc[-1],
        'close_gt_ema50': close.iloc[-1] > ema50.iloc[-1],
        'close_gt_ema200': close.iloc[-1] > ema200.iloc[-1],
        'super_trend': super_trend,
        'st_bull': st_bull.iloc[-1],
        'ut_stop': ut_stop_series,
        'ut_bull': ut_bull.iloc[-1],  # 这个是UT Bot行显示的状态
        'ut_bull_history': ut_bull,
        'buy_signal': buy_signal.iloc[-1],  # 这个是BUY标签
        'sell_signal': sell_signal.iloc[-1],  # 这个是SELL标签
        'vwap': vwap.iloc[-1],
        'close_gt_vwap': close.iloc[-1] > vwap.iloc[-1],
        'today_pivot': today_pivot,
        'close_gt_pivot': close.iloc[-1] > today_pivot,
        'close': close.iloc[-1]
    }

# ================= 数据获取 =================
@st.cache_data(ttl=30)
def fetch_ohlcv(symbol):
    exchange = ccxt.okx({'enableRateLimit': True})
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=200)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        st.error(f"获取{symbol}失败: {e}")
        return None

# ================= 发送Telegram =================
def send_telegram_message(message):
    if bot and enable_telegram:
        try:
            asyncio.run(bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message))
        except:
            pass

# ================= 执行扫描 =================
def perform_scan():
    st.session_state.scan_count += 1
    current_time = datetime.now()
    
    st.session_state.scan_results = []
    signals = []
    
    status = st.empty()
    status.info(f"🔄 第{st.session_state.scan_count}次扫描 {current_time.strftime('%H:%M:%S')}")
    
    progress_bar = st.progress(0)
    
    for i, symbol in enumerate(SYMBOLS):
        df = fetch_ohlcv(symbol)
        if df is not None and len(df) >= 50:
            indicators = calculate_pine_indicators(df)
            
            result = {
                'symbol': symbol,
                '时间': current_time.strftime('%H:%M:%S'),
                '价格': indicators['close'],
                'EMA10>20': '✅' if indicators['ema10_gt_20'] else '❌',
                'EMA50': '✅' if indicators['close_gt_ema50'] else '❌',
                'EMA200': '✅' if indicators['close_gt_ema200'] else '❌',
                'SuperTrend': '✅' if indicators['st_bull'] else '❌',
                'UT Bot': 'BUY' if indicators['ut_bull'] else 'SELL',  # 匹配Pine的UT Bot行
                'UT信号': 'BUY🔥' if indicators['buy_signal'] else ('SELL⚠️' if indicators['sell_signal'] else 'NONE'),  # 实际买卖标签
                'VWAP': '✅' if indicators['close_gt_vwap'] else '❌',
                'Today Pivot': '✅' if indicators['close_gt_pivot'] else '❌',
                '全绿': '✅' if all([
                    indicators['ema10_gt_20'],
                    indicators['st_bull'],
                    indicators['ut_bull'],  # 注意：这里是ut_bull，不是buy_signal
                    indicators['close_gt_vwap']
                ]) else '❌'
            }
            
            st.session_state.scan_results.append(result)
            
            # 检查是否有BUY信号
            if indicators['buy_signal']:
                signals.append(('BUY', symbol, indicators['close']))
            
            # 检查是否有SELL信号
            if indicators['sell_signal']:
                signals.append(('SELL', symbol, indicators['close']))
        
        progress_bar.progress((i + 1) / len(SYMBOLS))
    
    progress_bar.empty()
    status.success(f"✅ 完成！扫描{len(st.session_state.scan_results)}个币种")
    
    # 发送Telegram通知（只发BUY信号）
    for signal_type, symbol, price in signals:
        if signal_type == 'BUY':
            msg = f"🚨 BUY信号 {symbol}\n价格: {price:.4f}\n时间: {current_time.strftime('%H:%M:%S')}"
            send_telegram_message(msg)

# ================= 主循环 =================
current_time = time.time()
if st.session_state.manual_scan or (current_time - st.session_state.last_scan_time > scan_interval):
    perform_scan()
    st.session_state.last_scan_time = current_time
    st.session_state.manual_scan = False

# ================= 显示结果 =================
if st.session_state.scan_results:
    st.subheader("📊 扫描结果")
    
    # 转换为DataFrame
    df_results = pd.DataFrame(st.session_state.scan_results)
    
    # 定义颜色函数
    def highlight_rows(row):
        styles = [''] * len(row)
        
        # 全绿行用绿色
        if row['全绿'] == '✅':
            return ['background-color: #90EE90'] * len(row)
        
        # UT Bot BUY用黄色
        if row['UT信号'] == 'BUY🔥':
            return ['background-color: #FFE55C'] * len(row)
        
        return styles
    
    # 应用样式
    styled_df = df_results.style.apply(highlight_rows, axis=1)
    
    # 显示表格
    st.dataframe(styled_df, use_container_width=True)
    
    # 统计
    st.subheader("📈 统计")
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric("总币种", len(df_results))
    with col2:
        st.metric("UT BUY状态", len(df_results[df_results['UT Bot'] == 'BUY']))
    with col3:
        st.metric("BUY信号", len(df_results[df_results['UT信号'] == 'BUY🔥']))
    with col4:
        st.metric("SELL信号", len(df_results[df_results['UT信号'] == 'SELL⚠️']))
    with col5:
        st.metric("全绿信号", len(df_results[df_results['全绿'] == '✅']))

# ================= 说明 =================
st.markdown("---")
st.markdown("""
### 📝 重要说明（完全匹配Pine Script）

| 列名 | 含义 | 对应Pine Script |
|------|------|-----------------|
| **UT Bot** | UT多空状态 | `f_ut_row(5, "UT Bot", utBull)` - 显示BUY/SELL文本 |
| **UT信号** | 实际买卖信号 | `buySignal` / `sellSignal` - 显示BUY🔥/SELL⚠️标签 |
| **全绿** | 所有指标满足 | EMA10>20 + SuperTrend多头 + UT多头 + VWAP |

**关键区别:**
- UT Bot行显示的是**状态**（BUY=价格>止损，SELL=价格<止损）
- 图表上的BUY/SELL标签是**信号**（状态变化时出现）
""")

# ================= 自动刷新 =================
time.sleep(2)
st.rerun()
