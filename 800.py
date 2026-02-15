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
    'SOL/USDT',
    'HYPE/USDT',
    'AAVE/USDT',
    'XRP/USDT',
    'DOGE/USDT',
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
st.set_page_config(page_title="OKX 1min 全指标扫描器 - 修复版", layout="wide")
st.title("📊 OKX 1分钟全指标扫描器 (UT Bot修复版)")

# 侧边栏
with st.sidebar:
    st.header("⚙️ 参数设置")
    scan_interval = st.number_input("扫描间隔(秒)", 5, 60, SCAN_INTERVAL)
    
    st.header("📈 UT Bot参数")
    ut_factor = st.slider("UT Factor", 0.5, 3.0, UT_FACTOR, 0.1)
    ut_atr_len = st.slider("UT ATR长度", 5, 20, UT_ATR_LEN)
    
    st.header("📈 SuperTrend参数")
    st_atr_len = st.slider("ST ATR长度", 5, 20, ST_ATR_LEN)
    st_multiplier = st.slider("ST乘数", 1.0, 5.0, ST_MULTIPLIER, 0.5)
    
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

# ================= 数据获取 =================
@st.cache_data(ttl=30)
def fetch_ohlcv(symbol):
    """从OKX获取数据"""
    try:
        exchange = ccxt.okx({
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'}
        })
        ohlcv = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=200)
        if not ohlcv or len(ohlcv) < 50:
            return None
            
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        st.error(f"获取{symbol}失败: {e}")
        return None

# ================= UT Bot精确实现 =================
def calculate_ut_bot(high, low, close, factor=1.0, atr_length=10):
    """完全匹配Pine Script的UT Bot实现 - 修复版"""
    
    # 计算ATR
    atr = pta.atr(high=high, low=low, close=close, length=atr_length)
    
    # 确保数据有效
    if atr is None or len(atr) < atr_length:
        return pd.Series(index=close.index, dtype=float)
    
    length = len(close)
    ut_stop = np.zeros(length)
    
    # 初始化第一根K线
    if not np.isnan(atr.iloc[0]) and not np.isnan(close.iloc[0]):
        ut_stop[0] = close.iloc[0] - factor * atr.iloc[0]
    else:
        ut_stop[0] = close.iloc[0]
    
    # 逐根K线计算
    for i in range(1, length):
        if np.isnan(atr.iloc[i]) or np.isnan(close.iloc[i]):
            ut_stop[i] = ut_stop[i-1]
            continue
            
        if close.iloc[i] > ut_stop[i-1]:
            ut_stop[i] = max(ut_stop[i-1], close.iloc[i] - factor * atr.iloc[i])
        else:
            ut_stop[i] = min(ut_stop[i-1], close.iloc[i] + factor * atr.iloc[i])
    
    return pd.Series(ut_stop, index=close.index)

# ================= 计算所有指标 =================
def calculate_all_indicators(df):
    """计算所有Pine Script指标"""
    if df is None or len(df) < 50:
        return None
    
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
    
    # 检查NaN
    ema10_gt_20 = False
    close_gt_ema50 = False
    close_gt_ema200 = False
    
    if ema10 is not None and ema20 is not None and len(ema10) > 0 and len(ema20) > 0:
        if not pd.isna(ema10.iloc[-1]) and not pd.isna(ema20.iloc[-1]):
            ema10_gt_20 = ema10.iloc[-1] > ema20.iloc[-1]
    
    if ema50 is not None and len(ema50) > 0 and not pd.isna(ema50.iloc[-1]):
        close_gt_ema50 = close.iloc[-1] > ema50.iloc[-1]
    
    if ema200 is not None and len(ema200) > 0 and not pd.isna(ema200.iloc[-1]):
        close_gt_ema200 = close.iloc[-1] > ema200.iloc[-1]
    
    #━━━━━━━━━━━━━━━━━━━━━━
    # 2. SuperTrend
    #━━━━━━━━━━━━━━━━━━━━━━
    st_bull = False
    try:
        st = pta.supertrend(
            high=high, 
            low=low, 
            close=close, 
            length=st_atr_len, 
            multiplier=st_multiplier
        )
        
        if st is not None:
            # 查找SuperTrend列
            for col in st.columns:
                if 'SUPERT_' in col:
                    if not pd.isna(st[col].iloc[-1]):
                        st_bull = close.iloc[-1] > st[col].iloc[-1]
                    break
    except:
        pass
    
    #━━━━━━━━━━━━━━━━━━━━━━
    # 3. UT Bot (关键修复)
    #━━━━━━━━━━━━━━━━━━━━━━
    ut_stop_series = calculate_ut_bot(high, low, close, ut_factor, ut_atr_len)
    
    # 获取当前UT止损值
    current_ut_stop = ut_stop_series.iloc[-1] if not ut_stop_series.isna().all() else np.nan
    current_close = close.iloc[-1]
    
    # UT Bull状态 - 这就是UT Bot行的BUY/SELL
    ut_bull = False
    if not np.isnan(current_ut_stop) and not np.isnan(current_close):
        ut_bull = current_close > current_ut_stop
    
    # UT Bull历史
    ut_bull_history = close > ut_stop_series
    
    # UT Bull变化检测
    ut_bull_change = False
    if len(ut_bull_history) > 1:
        ut_bull_change = ut_bull_history.iloc[-1] and not ut_bull_history.iloc[-2]
    
    #━━━━━━━━━━━━━━━━━━━━━━
    # 4. BUY/SELL信号
    #━━━━━━━━━━━━━━━━━━━━━━
    buy_signal = ut_bull_change and ema10_gt_20
    
    sell_signal = False
    if len(ut_bull_history) > 1:
        sell_signal = not ut_bull_history.iloc[-1] and ut_bull_history.iloc[-2]
    
    #━━━━━━━━━━━━━━━━━━━━━━
    # 5. VWAP
    #━━━━━━━━━━━━━━━━━━━━━━
    close_gt_vwap = False
    vwap_value = np.nan
    try:
        typical = (high + low + close) / 3
        vwap = (typical * volume).cumsum() / volume.cumsum()
        if len(vwap) > 0 and not pd.isna(vwap.iloc[-1]):
            vwap_value = vwap.iloc[-1]
            close_gt_vwap = close.iloc[-1] > vwap_value
    except:
        pass
    
    #━━━━━━━━━━━━━━━━━━━━━━
    # 6. Today Pivot
    #━━━━━━━━━━━━━━━━━━━━━━
    close_gt_pivot = False
    today_pivot_value = np.nan
    try:
        last_24h = df.tail(100)  # 用最近100根代替
        if len(last_24h) > 0:
            d_high = last_24h['high'].max()
            d_low = last_24h['low'].min()
            d_close = last_24h['close'].iloc[-1]
            today_pivot_value = (d_high + d_low + d_close) / 3
            close_gt_pivot = close.iloc[-1] > today_pivot_value
    except:
        pass
    
    # 返回所有指标
    return {
        # EMA
        'ema10_gt_20': ema10_gt_20,
        'close_gt_ema50': close_gt_ema50,
        'close_gt_ema200': close_gt_ema200,
        
        # SuperTrend
        'st_bull': st_bull,
        
        # UT Bot
        'ut_bull': ut_bull,
        'ut_stop': current_ut_stop,
        'ut_bull_history': ut_bull_history,
        
        # 买卖信号
        'buy_signal': buy_signal,
        'sell_signal': sell_signal,
        
        # VWAP
        'close_gt_vwap': close_gt_vwap,
        'vwap': vwap_value,
        
        # Pivot
        'close_gt_pivot': close_gt_pivot,
        'today_pivot': today_pivot_value,
        
        # 当前价格
        'close': current_close
    }

# ================= 执行扫描 =================
def perform_scan():
    st.session_state.scan_count += 1
    current_time = datetime.now()
    
    st.session_state.scan_results = []
    buy_signals = []
    
    status = st.empty()
    status.info(f"🔄 第{st.session_state.scan_count}次扫描 {current_time.strftime('%H:%M:%S')}")
    
    progress_bar = st.progress(0)
    
    for i, symbol in enumerate(SYMBOLS):
        df = fetch_ohlcv(symbol)
        if df is not None:
            ind = calculate_all_indicators(df)
            
            if ind:
                # 全绿条件
                all_green = all([
                    ind['ema10_gt_20'],
                    ind['st_bull'],
                    ind['ut_bull'],  # 使用ut_bull
                    ind['close_gt_vwap']
                ])
                
                # 格式化价格
                if 'BTC' in symbol:
                    price_str = f"${ind['close']:,.2f}"
                    stop_str = f"${ind['ut_stop']:,.2f}" if not np.isnan(ind['ut_stop']) else "N/A"
                else:
                    price_str = f"${ind['close']:.4f}"
                    stop_str = f"${ind['ut_stop']:.4f}" if not np.isnan(ind['ut_stop']) else "N/A"
                
                # UT信号显示
                ut_signal_display = '➖'
                if ind['buy_signal']:
                    ut_signal_display = 'BUY🔥'
                elif ind['sell_signal']:
                    ut_signal_display = 'SELL⚠️'
                
                result = {
                    '交易对': symbol,
                    '时间': current_time.strftime('%H:%M:%S'),
                    '价格': price_str,
                    
                    # EMA
                    'EMA10>20': '✅' if ind['ema10_gt_20'] else '❌',
                    'EMA50': '✅' if ind['close_gt_ema50'] else '❌',
                    'EMA200': '✅' if ind['close_gt_ema200'] else '❌',
                    
                    # SuperTrend
                    'SuperTrend': '✅' if ind['st_bull'] else '❌',
                    
                    # UT Bot - 根据ut_bull显示BUY/SELL
                    'UT Bot': 'BUY' if ind['ut_bull'] else 'SELL',
                    
                    # UT信号
                    'UT信号': ut_signal_display,
                    
                    # VWAP & Pivot
                    'VWAP': '✅' if ind['close_gt_vwap'] else '❌',
                    'Pivot': '✅' if ind['close_gt_pivot'] else '❌',
                    
                    # 全绿
                    '全绿': '✅' if all_green else '❌',
                    
                    # 调试信息
                    'UT止损': stop_str,
                    '价格>止损': '✅' if ind['ut_bull'] else '❌'
                }
                
                st.session_state.scan_results.append(result)
                
                # 记录BUY信号
                if ind['buy_signal']:
                    buy_signals.append((symbol, ind['close']))
        
        progress_bar.progress((i + 1) / len(SYMBOLS))
    
    progress_bar.empty()
    status.success(f"✅ 扫描完成！{len(st.session_state.scan_results)}个币种")
    
    # 发送Telegram通知
    for symbol, price in buy_signals:
        msg = f"🚨 BUY信号 {symbol}\n价格: {price:.4f}\n时间: {current_time.strftime('%H:%M:%S')}"
        if bot and enable_telegram:
            try:
                asyncio.run(bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg))
            except:
                pass

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
        
        # UT Bot BUY用浅绿色
        if row['UT Bot'] == 'BUY':
            return ['background-color: #e8f5e8'] * len(row)
        
        # BUY信号用黄色
        if row['UT信号'] == 'BUY🔥':
            return ['background-color: #FFE55C'] * len(row)
        
        return styles
    
    # 应用样式
    styled_df = df_results.style.apply(highlight_rows, axis=1)
    
    # 显示表格
    st.dataframe(styled_df, use_container_width=True, height=600)
    
    # 统计
    st.subheader("📈 统计")
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    
    with col1:
        st.metric("总币种", len(df_results))
    with col2:
        buy_count = len(df_results[df_results['UT Bot'] == 'BUY'])
        st.metric("UT BUY状态", buy_count)
    with col3:
        sell_count = len(df_results[df_results['UT Bot'] == 'SELL'])
        st.metric("UT SELL状态", sell_count)
    with col4:
        signal_count = len(df_results[df_results['UT信号'] == 'BUY🔥'])
        st.metric("BUY信号", signal_count)
    with col5:
        green_count = len(df_results[df_results['全绿'] == '✅'])
        st.metric("全绿信号", green_count)
    with col6:
        st.metric("扫描次数", st.session_state.scan_count)

# ================= 调试信息 =================
with st.expander("🔍 调试信息"):
    st.write("### UT Bot计算逻辑")
    st.write("""
    UT Bot显示BUY的条件:
    1. 价格 > UT止损线
    2. UT止损线通过以下公式计算:
       - 如果价格 > 上一根止损: ut_stop = max(上一根止损, 价格 - factor * ATR)
       - 如果价格 < 上一根止损: ut_stop = min(上一根止损, 价格 + factor * ATR)
    """)
    
    # 显示BTC详细
    btc_data = next((r for r in st.session_state.scan_results if r['交易对'] == 'BTC/USDT'), None)
    if btc_data:
        st.write("### BTC/USDT当前状态")
        st.json({
            'UT Bot显示': btc_data['UT Bot'],
            'UT止损': btc_data['UT止损'],
            '价格>止损': btc_data['价格>止损'],
            'UT信号': btc_data['UT信号']
        })

# ================= 使用说明 =================
st.markdown("---")
st.markdown("""
### 📝 指标说明

| 列名 | 含义 |
|------|------|
| **UT Bot** | UT多空状态 - 价格>止损显示BUY，否则SELL |
| **UT信号** | 图表上的实际买卖标签 |
| **全绿** | EMA10>20 + SuperTrend多头 + UT多头 + VWAP |

### 🎯 问题修复
- ✅ 修复UT止损显示NaN的问题
- ✅ UT Bot现在正确计算价格与止损的关系
- ✅ 所有币种都有UT止损值
""")

# ================= 自动刷新 =================
time.sleep(2)
st.rerun()
