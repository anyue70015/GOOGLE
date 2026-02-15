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
TIMEFRAME = '1m'  # 改为1分钟
SCAN_INTERVAL = 30  # 30秒扫描一次

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

# 使用secrets管理敏感信息
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
    page_title="1min 扫描器 - 实时UT信号", 
    layout="wide",
    page_icon="📊"
)

st.title("📊 1分钟多币种扫描器 (实时UT信号)")
st.caption("指标条件: EMA10 > EMA20 + SuperTrend多头 + UT Bot多头 + 价格 > VWAP")

# 侧边栏配置
with st.sidebar:
    st.header("⚙️ 扫描设置")
    scan_interval = st.number_input("扫描间隔(秒)", min_value=5, max_value=60, value=SCAN_INTERVAL)
    
    st.header("📈 指标参数")
    ut_factor = st.slider("UT Factor", 0.5, 3.0, UT_FACTOR, 0.1)
    ut_atr_len = st.slider("UT ATR长度", 5, 20, UT_ATR_LEN)
    st_atr_len = st.slider("SuperTrend ATR长度", 5, 20, ST_ATR_LEN)
    st_multiplier = st.slider("SuperTrend乘数", 1.0, 5.0, ST_MULTIPLIER, 0.5)
    
    st.header("🔔 通知设置")
    enable_telegram = st.checkbox("启用Telegram通知", value=bot is not None)
    
    # 调试选项
    st.header("🔧 显示选项")
    show_ut_details = st.checkbox("显示UT详细信息", value=True)
    show_all_logs = st.checkbox("显示所有日志", value=False)
    
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
stats_col1, stats_col2, stats_col3, stats_col4, stats_col5 = st.columns(5)

# ================= UT Bot 正确实现 =================
def calculate_ut_bot(high, low, close, factor=1.0, atr_length=10):
    """
    正确实现 UT Bot 算法
    返回: (stop_line, trend, signal, signal_type)
    - stop_line: 止损线值
    - trend: 1=多头, -1=空头
    - signal: 1=买入信号, -1=卖出信号, 0=无信号
    - signal_type: 信号类型文字描述
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

def get_ut_bot_status(high, low, close, factor=UT_FACTOR, atr_length=UT_ATR_LEN):
    """
    获取UT Bot完整状态
    返回: (is_bullish, signal_type, details)
    """
    stop_line, trend, signal = calculate_ut_bot(high, low, close, factor, atr_length)
    
    # 获取最新的值
    current_close = close.iloc[-1]
    current_stop = stop_line.iloc[-1]
    current_trend = trend.iloc[-1]
    current_signal = signal.iloc[-1]
    
    # 信号类型文字描述
    if current_signal == 1:
        signal_type = "BUY 🔥"
    elif current_signal == -1:
        signal_type = "SELL ⚠️"
    else:
        signal_type = "NONE ➖"
    
    # 趋势文字描述
    trend_type = "BULL 📈" if current_trend == 1 else "BEAR 📉"
    
    # 多头判断
    price_above_stop = current_close > current_stop
    is_bullish = price_above_stop and current_trend == 1
    
    # 详细结果
    details = {
        'close': current_close,
        'stop_line': current_stop,
        'trend': current_trend,
        'trend_type': trend_type,
        'signal': current_signal,
        'signal_type': signal_type,
        'price_above_stop': price_above_stop,
        'is_bullish': is_bullish,
        'stop_diff': ((current_close - current_stop) / current_stop * 100) if current_stop != 0 else 0
    }
    
    return is_bullish, signal_type, details

# ================= 其他函数 =================
@st.cache_data(ttl=60, show_spinner=False)  # 1分钟缓存
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
    ut_bullish, ut_signal, ut_details = get_ut_bot_status(high, low, close, ut_factor, ut_atr_len)
    
    # VWAP
    typical = (high + low + close) / 3
    vwap = (typical * volume).cumsum() / volume.cumsum()
    
    return {
        'ema10': ema10,
        'ema20': ema20,
        'st': st_result,
        'st_col': st_col,
        'st_dir_col': st_dir_col,
        'ut_bullish': ut_bullish,
        'ut_signal': ut_signal,
        'ut_details': ut_details,
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
    
    # UT Bot条件
    cond_ut = indicators['ut_bullish']
    
    # VWAP条件
    cond_vwap = close.iloc[-1] > indicators['vwap'].iloc[-1]
    
    # 综合判断
    all_green = all([cond_ema, cond_st, cond_ut, cond_vwap])
    
    return {
        'symbol': symbol,
        'price': close.iloc[-1],
        'ema': cond_ema,
        'st': cond_st,
        'ut_bullish': cond_ut,
        'ut_signal': indicators['ut_signal'],
        'ut_details': indicators['ut_details'],
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
                
                # 生成日志
                ut_details = result['ut_details']
                ut_status = "✅多头" if result['ut_bullish'] else "❌空头"
                
                log_msg = (f"{symbol}: EMA={result['ema']} | "
                          f"ST={result['st']} | "
                          f"UT={ut_status} | "
                          f"UT信号={result['ut_signal']} | "
                          f"VWAP={result['vwap']} | "
                          f"全绿={result['all_green']}")
                
                # 添加UT详细信息
                if show_ut_details:
                    log_msg += (f" [价格>止损:{ut_details['price_above_stop']}, "
                               f"趋势:{ut_details['trend_type']}, "
                               f"偏离:{ut_details['stop_diff']:.2f}%]")
                
                if result['all_green']:
                    add_log(f"✅ {log_msg}", "success")
                    triggered.append((symbol, result['price']))
                elif show_all_logs:
                    add_log(log_msg, "info")
                
                # 特别关注BUY信号
                if result['ut_signal'] == "BUY 🔥" and not result['all_green']:
                    add_log(f"⚠️ {symbol} UT BUY信号但其他条件不满足", "warning")
            
            progress_bar.progress((i + 1) / len(SYMBOLS))
            
        except Exception as e:
            add_log(f"{symbol} 处理失败: {str(e)}", "error")
    
    progress_bar.empty()
    
    # 发送通知 - 只发全绿信号
    if triggered:
        for symbol, price in triggered:
            msg = f"🚨 【全绿信号】 {symbol}\n价格: {price:.4f}\n时间: {current_time}"
            add_log(f"🎯 触发全绿信号: {symbol}", "success")
            send_telegram_message(msg)
        
        st.balloons()
    
    # 统计BUY信号
    buy_signals = [r for r in results if r['ut_signal'] == "BUY 🔥"]
    if buy_signals and show_all_logs:
        add_log(f"📊 UT BUY信号币种: {len(buy_signals)}个", "info")
        for r in buy_signals:
            add_log(f"  - {r['symbol']} (价格:{r['price']:.4f})", "info")
    
    # 保存结果
    st.session_state.scan_results = results
    
    return triggered

# ================= 显示统计 =================
with stats_col1:
    st.metric("扫描次数", st.session_state.scan_count)
with stats_col2:
    active_signals = sum(1 for r in st.session_state.scan_results if r['all_green'])
    st.metric("全绿信号", active_signals)
with stats_col3:
    ut_buy_count = sum(1 for r in st.session_state.scan_results if r.get('ut_signal') == "BUY 🔥")
    st.metric("UT BUY信号", ut_buy_count)
with stats_col4:
    ut_bullish_count = sum(1 for r in st.session_state.scan_results if r.get('ut_bullish', False))
    st.metric("UT多头", ut_bullish_count)
with stats_col5:
    st.metric("监控币种", len(SYMBOLS))

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
    
    # 提取UT详细信息
    if 'ut_details' in results_df.columns:
        results_df['UT趋势'] = results_df['ut_details'].apply(lambda x: x['trend_type'] if x else 'unknown')
        results_df['价格>止损'] = results_df['ut_details'].apply(lambda x: x['price_above_stop'] if x else False)
        results_df['偏离%'] = results_df['ut_details'].apply(lambda x: f"{x['stop_diff']:.2f}%" if x else '0%')
        results_df = results_df.drop('ut_details', axis=1)
    
    # 重命名列
    results_df = results_df.rename(columns={
        'ut_bullish': 'UT多头',
        'ut_signal': 'UT信号'
    })
    
    # 选择要显示的列
    display_cols = ['symbol', 'price', 'ema', 'st', 'UT多头', 'UT信号', 'UT趋势', '价格>止损', '偏离%', 'vwap', 'all_green', 'timestamp']
    display_cols = [col for col in display_cols if col in results_df.columns]
    
    # 高亮显示
    def highlight_rows(row):
        styles = [''] * len(row)
        if row['all_green']:
            return ['background-color: #90EE90'] * len(row)
        elif row.get('UT信号') == "BUY 🔥":
            return ['background-color: #FFE55C'] * len(row)  # 黄色高亮BUY信号
        return styles
    
    styled_df = results_df[display_cols].style.apply(highlight_rows, axis=1)
    
    st.dataframe(
        styled_df,
        use_container_width=True,
        column_config={
            'symbol': '交易对',
            'price': st.column_config.NumberColumn('价格', format='%.4f'),
            'ema': 'EMA10>20',
            'st': 'SuperTrend',
            'UT多头': 'UT多头',
            'UT信号': 'UT信号',
            'UT趋势': 'UT趋势',
            '价格>止损': '价格>止损',
            '偏离%': '偏离%',
            'vwap': 'VWAP',
            'all_green': '全绿',
            'timestamp': '时间'
        }
    )

# ================= 显示日志 =================
with log_expander:
    # 添加UT Bot说明
    st.info("""
    **UT Bot信号说明:**
    - **BUY 🔥**: 从空头转为多头的瞬间（买入信号）
    - **SELL ⚠️**: 从多头转为空头的瞬间（卖出信号）
    - **NONE ➖**: 趋势延续中
    - **UT多头**: 价格在止损线上方且趋势为多头
    - **全绿信号**: 所有指标都满足（EMA+ST+UT多头+VWAP）
    
    **注意:** UT BUY信号不等于UT多头！BUY是瞬间信号，多头是持续状态。
    """)
    
    for log in reversed(st.session_state.log_messages[-30:]):
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
**重要说明:**
- ✅ **UT信号** 显示实时的BUY/SELL/NONE（与截图一致）
- ✅ **UT多头** 显示是否为多头状态（用于全绿判断）
- ✅ **BUY信号** 用黄色高亮显示
- ✅ **全绿信号** 用绿色高亮显示
- 🔍 如果看到BUY信号但UT多头为False，说明是刚转为多头的瞬间
""")
