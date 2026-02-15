import streamlit as st
import ccxt
import pandas as pd
import pandas_ta as pta
import time
from datetime import datetime
from telegram import Bot
import asyncio

# ================= 配置 =================
EXCHANGE_NAME = 'okx'
TIMEFRAME = '5m'
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
    page_title="5min 扫描器", 
    layout="wide",
    page_icon="📊"
)

st.title("📊 5分钟多币种扫描器")
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
stats_col1, stats_col2, stats_col3 = st.columns(3)

# ================= 函数 =================
@st.cache_data(ttl=120, show_spinner=False)
def fetch_ohlcv(symbol):
    """获取OHLCV数据"""
    exchange = getattr(ccxt, EXCHANGE_NAME)({
        'enableRateLimit': True,
        'options': {'defaultType': 'spot'}  # 或 'future' 根据需要
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
            # 异步发送
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
    # 保持最近100条日志
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
    
    # SuperTrend - 动态列名
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
    
    # UT Bot
    atr = pta.atr(high=high, low=low, close=close, length=ut_atr_len)
    ut_stop = close - ut_factor * atr
    
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
        'vwap': vwap
    }

def check_conditions(symbol, df, indicators):
    """检查所有条件"""
    if df is None or len(df) < 50:
        return None
    
    close = df['close']
    
    # EMA条件
    cond_ema = False
    if not indicators['ema10'].isna().iloc[-1] and not indicators['ema20'].isna().iloc[-1]:
        cond_ema = indicators['ema10'].iloc[-1] > indicators['ema20'].iloc[-1]
    
    # SuperTrend条件
    cond_st = False
    if indicators['st_col'] and indicators['st_col'] in indicators['st'].columns:
        cond_st = close.iloc[-1] > indicators['st'][indicators['st_col']].iloc[-1]
    elif indicators['st_dir_col'] and indicators['st_dir_col'] in indicators['st'].columns:
        cond_st = indicators['st'][indicators['st_dir_col']].iloc[-1] == 1  # 1表示上升
    
    # UT条件
    cond_ut = close.iloc[-1] > indicators['ut_stop'].iloc[-1]
    
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
                log_msg = (f"{symbol}: EMA={result['ema']} | "
                          f"ST={result['st']} | UT={result['ut']} | "
                          f"VWAP={result['vwap']} | 全绿={result['all_green']}")
                
                if result['all_green']:
                    add_log(f"✅ {log_msg}", "success")
                    triggered.append((symbol, result['price']))
                else:
                    add_log(log_msg, "info")
            
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
            'ema': 'EMA',
            'st': 'SuperTrend',
            'ut': 'UT Bot',
            'vwap': 'VWAP',
            'all_green': '全绿',
            'timestamp': '时间'
        }
    )

# ================= 显示日志 =================
with log_expander:
    for log in reversed(st.session_state.log_messages[-20:]):  # 显示最近20条
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
