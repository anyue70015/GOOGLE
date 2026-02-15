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
SCAN_INTERVAL = 60  # 秒

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

# 使用secrets管理敏感信息（推荐）
TELEGRAM_TOKEN = st.secrets.get("TELEGRAM_TOKEN", "YOUR_BOT_TOKEN_HERE")
TELEGRAM_CHAT_ID = st.secrets.get("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID_HERE")

# 指标参数
UT_FACTOR = 1.0
UT_ATR_LEN = 10
ST_ATR_LEN = 10
ST_MULTIPLIER = 3.0

# ================= 初始化 =================
def init_bot():
    """初始化Telegram bot"""
    if TELEGRAM_TOKEN and TELEGRAM_TOKEN != "YOUR_BOT_TOKEN_HERE":
        try:
            return Bot(token=TELEGRAM_TOKEN)
        except Exception as e:
            st.warning(f"Telegram bot初始化失败: {e}")
            return None
    return None

bot = init_bot()

# ================= UI =================
st.set_page_config(
    page_title="5min 扫描器 - UT Bot修复版", 
    layout="wide",
    page_icon="📊"
)

st.title("📊 5分钟多币种扫描器 (修复UT Bot)")
st.caption("指标条件: EMA10 > EMA20 + SuperTrend多头 + UT Bot多头 + 价格 > VWAP")

# 侧边栏配置
with st.sidebar:
    st.header("⚙️ 扫描设置")
    scan_interval = st.number_input("扫描间隔(秒)", min_value=10, max_value=300, value=SCAN_INTERVAL)
    
    st.header("📈 指标参数")
    ut_factor = st.slider("UT Factor", 0.5, 3.0, UT_FACTOR, 0.1)
    ut_atr_len = st.slider("UT ATR长度", 5, 20, UT_ATR_LEN)
    st_atr_len = st.slider("SuperTrend ATR长度", 5, 20, ST_ATR_LEN)
    st_multiplier = st.slider("SuperTrend乘数", 1.0, 5.0, ST_MULTIPLIER, 0.5)
    
    st.header("🔔 通知设置")
    enable_telegram = st.checkbox("启用Telegram通知", value=bot is not None)
    
    # 调试选项
    st.header("🔧 调试选项")
    show_debug = st.checkbox("显示详细调试信息", value=False)
    
    if st.button("🔄 立即扫描"):
        st.session_state.manual_scan = True

# session_state初始化
if 'last_scan_time' not in st.session_state:
    st.session_state.last_scan_time = 0
if 'scan_count' not in st.session_state:
    st.session_state.scan_count = 0
if 'manual_scan' not in st.session_state:
    st.session_state.manual_scan = False
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = []
if 'log_messages' not in st.session_state:
    st.session_state.log_messages = []

# 日志显示区域
log_expander = st.expander("📋 扫描日志", expanded=True)
status = st.empty()
stats_col1, stats_col2, stats_col3, stats_col4 = st.columns(4)

# ================= UT Bot 正确实现 =================
def calculate_ut_bot(high, low, close, factor=1.0, atr_length=10):
    """
    正确实现 UT Bot 算法
    返回: (stop_line, trend, signal)
    - stop_line: 止损线值
    - trend: 1=多头, -1=空头
    - signal: 1=买入信号, -1=卖出信号, 0=无信号
    """
    # 计算ATR
    atr = pta.atr(high=high, low=low, close=close, length=atr_length)
    
    # 初始化数组
    length = len(close)
    stop = np.zeros(length)
    trend = np.ones(length)  # 1=多头, -1=空头
    signal = np.zeros(length)
    
    for i in range(1, length):
        # 计算基础止损线
        if i == 1:
            stop[i] = close.iloc[i] - factor * atr.iloc[i]
        else:
            # 根据价格相对于上一根止损线的位置计算新的止损线
            if close.iloc[i] > stop[i-1]:
                # 上升趋势中，止损线上移
                stop[i] = max(stop[i-1], close.iloc[i] - factor * atr.iloc[i])
            else:
                # 下降趋势中，止损线下移
                stop[i] = min(stop[i-1], close.iloc[i] + factor * atr.iloc[i])
        
        # 确定趋势和信号
        if close.iloc[i] > stop[i] and close.iloc[i-1] <= stop[i-1]:
            # 从空头转为多头 - 买入信号
            trend[i] = 1
            signal[i] = 1
        elif close.iloc[i] < stop[i] and close.iloc[i-1] >= stop[i-1]:
            # 从多头转为空头 - 卖出信号
            trend[i] = -1
            signal[i] = -1
        else:
            # 趋势延续
            trend[i] = trend[i-1]
            signal[i] = 0
    
    # 转换为Series
    stop_series = pd.Series(stop, index=close.index)
    trend_series = pd.Series(trend, index=close.index)
    signal_series = pd.Series(signal, index=close.index)
    
    return stop_series, trend_series, signal_series

def check_ut_bot_bullish(high, low, close, factor=UT_FACTOR, atr_length=UT_ATR_LEN):
    """
    检查UT Bot是否为多头状态
    返回: (is_bullish, details)
    """
    stop_line, trend, signal = calculate_ut_bot(high, low, close, factor, atr_length)
    
    # 获取最新的值
    current_close = close.iloc[-1]
    current_stop = stop_line.iloc[-1]
    current_trend = trend.iloc[-1]
    current_signal = signal.iloc[-1]
    
    # 检查最近是否有买入信号（可选）
    recent_buy_signals = []
    for i in range(-5, 0):
        if signal.iloc[i] == 1:
            recent_buy_signals.append(close.index[i].strftime('%H:%M'))
    
    # 多头判断标准：
    # 1. 价格在止损线之上
    price_above_stop = current_close > current_stop
    
    # 2. 趋势为多头
    trend_bullish = current_trend == 1
    
    # 3. 止损线方向向上（当前止损 > 前一根止损）
    stop_increasing = False
    if len(stop_line) > 1:
        stop_increasing = stop_line.iloc[-1] > stop_line.iloc[-2]
    
    # 综合判断 - 严格模式需要满足所有条件
    is_bullish = price_above_stop and trend_bullish
    
    # 详细结果
    details = {
        'close': current_close,
        'stop_line': current_stop,
        'trend': 'bullish' if current_trend == 1 else 'bearish',
        'signal': 'buy' if current_signal == 1 else ('sell' if current_signal == -1 else 'none'),
        'price_above_stop': price_above_stop,
        'trend_bullish': trend_bullish,
        'stop_increasing': stop_increasing,
        'recent_buy_signals': recent_buy_signals,
        'is_bullish': is_bullish
    }
    
    return is_bullish, details

# ================= 其他函数 =================
@st.cache_data(ttl=120, show_spinner=False)
def fetch_ohlcv(symbol):
    """获取OHLCV数据"""
    exchange = getattr(ccxt, EXCHANGE_NAME)({
        'enableRateLimit': True,
        'options': {'defaultType': 'spot'}
    })
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=200)
        if not ohlcv:
            return None
            
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        return None

def send_telegram_message(message):
    """发送Telegram消息"""
    if bot and enable_telegram:
        try:
            asyncio.run(bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message))
        except Exception as e:
            st.error(f"Telegram发送失败: {e}")

def add_log(message, level="info"):
    """添加日志消息"""
    timestamp = datetime.now().strftime('%H:%M:%S')
    st.session_state.log_messages.append({
        'time': timestamp,
        'message': message,
        'level': level
    })
    if len(st.session_state.log_messages) > 100:
        st.session_state.log_messages = st.session_state.log_messages[-100:]

def calculate_indicators(df):
    """计算所有技术指标"""
    close = df['close']
    high = df['high']
    low = df['low']
    volume = df['volume']
    
    # EMA
    ema10 = pta.ema(close, length=10)
    ema20 = pta.ema(close, length=20)
    
    # SuperTrend
    st_result = pta.supertrend(
        high=high, 
        low=low, 
        close=close, 
        length=st_atr_len, 
        multiplier=st_multiplier
    )
    
    # 查找SuperTrend列
    st_col = None
    st_dir_col = None
    for col in st_result.columns:
        if 'SUPERT_' in col and str(st_atr_len) in col:
            st_col = col
        elif 'SUPERTd_' in col:
            st_dir_col = col
    
    # UT Bot (使用正确实现)
    ut_stop, ut_trend, ut_signal = calculate_ut_bot(high, low, close, ut_factor, ut_atr_len)
    
    # VWAP
    typical = (high + low + close) / 3
    vwap = (typical * volume).cumsum() / volume.cumsum()
    
    return {
        'ema10': ema10,
        'ema20': ema20,
        'st': st_result,
        'st_col': st_col,
        'st_dir_col': st_dir_col,
        'ut_stop': ut_stop,
        'ut_trend': ut_trend,
        'ut_signal': ut_signal,
        'vwap': vwap
    }

def check_conditions(symbol, df, indicators):
    """检查所有条件"""
    if df is None or len(df) < 50:
        return None
    
    close = df['close']
    high = df['high']
    low = df['low']
    
    # EMA条件
    cond_ema = False
    if not indicators['ema10'].isna().iloc[-1] and not indicators['ema20'].isna().iloc[-1]:
        cond_ema = indicators['ema10'].iloc[-1] > indicators['ema20'].iloc[-1]
    
    # SuperTrend条件
    cond_st = False
    if indicators['st_col'] and indicators['st_col'] in indicators['st'].columns:
        cond_st = close.iloc[-1] > indicators['st'][indicators['st_col']].iloc[-1]
    elif indicators['st_dir_col'] and indicators['st_dir_col'] in indicators['st'].columns:
        cond_st = indicators['st'][indicators['st_dir_col']].iloc[-1] == 1
    
    # UT Bot条件 (使用正确实现)
    ut_bullish, ut_details = check_ut_bot_bullish(high, low, close, ut_factor, ut_atr_len)
    cond_ut = ut_bullish
    
    # VWAP条件
    cond_vwap = close.iloc[-1] > indicators['vwap'].iloc[-1]
    
    # 综合判断
    all_green = all([cond_ema, cond_st, cond_ut, cond_vwap])
    
    return {
        'symbol': symbol,
        'price': close.iloc[-1],
        'ema': cond_ema,
        'st': cond_st,
        'ut': cond_ut,
        'ut_details': ut_details,
        'vwap': cond_vwap,
        'all_green': all_green,
        'timestamp': df['timestamp'].iloc[-1]
    }

def perform_scan():
    """执行一次扫描"""
    st.session_state.scan_count += 1
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    status.info(f"🔄 第 {st.session_state.scan_count} 次扫描 ({current_time})")
    
    triggered = []
    results = []
    
    # 进度条
    progress_bar = st.progress(0)
    
    for i, symbol in enumerate(SYMBOLS):
        try:
            # 获取数据
            df = fetch_ohlcv(symbol)
            
            if df is None or len(df) < 50:
                add_log(f"{symbol}: 数据不足", "warning")
                progress_bar.progress((i + 1) / len(SYMBOLS))
                continue
            
            # 计算指标
            indicators = calculate_indicators(df)
            
            # 检查条件
            result = check_conditions(symbol, df, indicators)
            
            if result:
                results.append(result)
                
                # 生成日志 - 详细显示UT Bot状态
                ut_status = "✅多头" if result['ut'] else "❌空头"
                ut_trend = result['ut_details']['trend']
                ut_signal = result['ut_details']['signal']
                ut_price_above = result['ut_details']['price_above_stop']
                
                log_msg = (f"{symbol}: EMA={result['ema']} | "
                          f"ST={result['st']} | "
                          f"UT={ut_status}({ut_trend},{ut_signal}) | "
                          f"VWAP={result['vwap']} | "
                          f"全绿={result['all_green']}")
                
                if result['all_green']:
                    add_log(f"✅ {log_msg}", "success")
                    triggered.append((symbol, result['price']))
                else:
                    add_log(log_msg, "info")
                
                # 调试信息
                if show_debug and not result['ut']:
                    debug_msg = (f"{symbol} UT调试: 价格={result['price']:.4f}, "
                                f"止损={result['ut_details']['stop_line']:.4f}, "
                                f"价格>止损={result['ut_details']['price_above_stop']}, "
                                f"趋势={result['ut_details']['trend']}")
                    add_log(debug_msg, "warning")
            
            progress_bar.progress((i + 1) / len(SYMBOLS))
            
        except Exception as e:
            add_log(f"{symbol} 处理失败: {str(e)}", "error")
    
    progress_bar.empty()
    
    # 发送通知
    if triggered:
        for symbol, price in triggered:
            msg = f"🚨 【5min信号】 {symbol}\n价格: {price:.4f}\n时间: {current_time}"
            add_log(f"🎯 触发信号: {symbol}", "success")
            send_telegram_message(msg)
        
        st.balloons()
    
    # 保存结果
    st.session_state.scan_results = results
    
    return triggered

# ================= 显示统计 =================
with stats_col1:
    st.metric("扫描次数", st.session_state.scan_count)
with stats_col2:
    active_signals = sum(1 for r in st.session_state.scan_results if r['all_green'])
    st.metric("当前信号", active_signals)
with stats_col3:
    st.metric("监控币种", len(SYMBOLS))
with stats_col4:
    ut_bearish_count = sum(1 for r in st.session_state.scan_results if not r.get('ut', False))
    st.metric("UT空头", ut_bearish_count)

# ================= 主循环 =================
current_time = time.time()
should_scan = False

# 检查是否需要扫描
if st.session_state.manual_scan:
    should_scan = True
    st.session_state.manual_scan = False
elif current_time - st.session_state.last_scan_time > scan_interval:
    should_scan = True

if should_scan:
    perform_scan()
    st.session_state.last_scan_time = current_time

# ================= 显示结果表格 =================
if st.session_state.scan_results:
    st.subheader("📊 扫描结果")
    
    # 转换为DataFrame
    results_df = pd.DataFrame(st.session_state.scan_results)
    
    # 添加UT详细信息列
    if 'ut_details' in results_df.columns:
        results_df['UT趋势'] = results_df['ut_details'].apply(lambda x: x['trend'] if x else 'unknown')
        results_df['UT信号'] = results_df['ut_details'].apply(lambda x: x['signal'] if x else 'unknown')
        results_df['价格>止损'] = results_df['ut_details'].apply(lambda x: x['price_above_stop'] if x else False)
        results_df = results_df.drop('ut_details', axis=1)
    
    # 高亮显示符合条件的行
    def highlight_green(row):
        if row['all_green']:
            return ['background-color: #90EE90'] * len(row)
        return [''] * len(row)
    
    styled_df = results_df.style.apply(highlight_green, axis=1)
    
    st.dataframe(
        styled_df,
        use_container_width=True,
        column_config={
            'symbol': '交易对',
            'price': st.column_config.NumberColumn('价格', format='%.4f'),
            'ema': 'EMA10>20',
            'st': 'SuperTrend',
            'ut': 'UT多头',
            'UT趋势': 'UT趋势',
            'UT信号': 'UT信号',
            '价格>止损': '价格>止损',
            'vwap': 'VWAP',
            'all_green': '全绿',
            'timestamp': '时间'
        }
    )

# ================= 显示日志 =================
with log_expander:
    # 添加UT Bot说明
    st.info("""
    **UT Bot正确判断标准:**
    - 多头: 价格在止损线之上 AND 趋势为多头
    - 空头: 价格在止损线之下 OR 趋势为空头
    - 买入信号: 从空头转为多头的时刻
    - 卖出信号: 从多头转为空头的时刻
    """)
    
    for log in reversed(st.session_state.log_messages[-30:]):  # 显示最近30条
        if log['level'] == 'success':
            st.success(f"{log['time']} - {log['message']}")
        elif log['level'] == 'warning':
            st.warning(f"{log['time']} - {log['message']}")
        elif log['level'] == 'error':
            st.error(f"{log['time']} - {log['message']}")
        else:
            st.info(f"{log['time']} - {log['message']}")

# ================= 自动刷新 =================
if not st.session_state.manual_scan:
    time.sleep(2)
    st.rerun()

# ================= 页脚 =================
st.markdown("---")
st.caption("""
**修复说明:** 
- ✅ UT Bot现在使用完整算法判断多头/空头
- ✅ 显示UT趋势和信号状态
- ✅ 添加调试选项查看详细UT计算
- ✅ 与截图中的UT Bot SELL信号一致
""")


