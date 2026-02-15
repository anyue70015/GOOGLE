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
EXCHANGE_NAME = 'okx'  # 使用OKX
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
st.set_page_config(page_title="OKX 1min 全指标扫描器", layout="wide")
st.title("📊 OKX 1分钟全指标扫描器 (匹配Pine Script)")

# 侧边栏
with st.sidebar:
    st.header("⚙️ 参数设置")
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

# ================= 数据获取 =================
@st.cache_data(ttl=30)
def fetch_ohlcv(symbol):
    """从OKX获取数据"""
    exchange = ccxt.okx({
        'enableRateLimit': True,
        'options': {'defaultType': 'spot'}
    })
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=200)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        st.error(f"获取{symbol}失败: {e}")
        return None

# ================= UT Bot精确实现 =================
def calculate_ut_bot(high, low, close, factor=1.0, atr_length=10):
    """完全匹配Pine Script的UT Bot实现"""
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

# ================= 计算所有指标 =================
def calculate_all_indicators(df):
    """计算所有Pine Script指标"""
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
    
    ema10_gt_20 = ema10.iloc[-1] > ema20.iloc[-1]
    close_gt_ema50 = close.iloc[-1] > ema50.iloc[-1]
    close_gt_ema200 = close.iloc[-1] > ema200.iloc[-1]
    
    #━━━━━━━━━━━━━━━━━━━━━━
    # 2. SuperTrend
    #━━━━━━━━━━━━━━━━━━━━━━
    st = pta.supertrend(
        high=high, 
        low=low, 
        close=close, 
        length=st_atr_len, 
        multiplier=st_multiplier
    )
    
    # 找到SuperTrend列
    st_col = None
    for col in st.columns:
        if 'SUPERT_' in col:
            st_col = col
            break
    
    super_trend = st[st_col] if st_col else pd.Series(index=close.index)
    st_bull = close.iloc[-1] > super_trend.iloc[-1] if st_col else False
    
    #━━━━━━━━━━━━━━━━━━━━━━
    # 3. UT Bot (关键修复)
    #━━━━━━━━━━━━━━━━━━━━━━
    ut_stop = calculate_ut_bot(high, low, close, ut_factor, ut_atr_len)
    ut_bull = close.iloc[-1] > ut_stop.iloc[-1]  # 这就是UT Bot行的BUY/SELL
    
    # UT Bull变化检测
    ut_bull_history = close > ut_stop
    ut_bull_change = ut_bull_history & ~ut_bull_history.shift(1).fillna(False)
    
    #━━━━━━━━━━━━━━━━━━━━━━
    # 4. BUY/SELL信号 (图表上的标签)
    #━━━━━━━━━━━━━━━━━━━━━━
    buy_signal = ut_bull_change.iloc[-1] and ema10_gt_20
    sell_signal = (~ut_bull_history).iloc[-1] and ut_bull_history.shift(1).fillna(False).iloc[-1]
    
    #━━━━━━━━━━━━━━━━━━━━━━
    # 5. VWAP
    #━━━━━━━━━━━━━━━━━━━━━━
    typical = (high + low + close) / 3
    vwap = (typical * volume).cumsum() / volume.cumsum()
    close_gt_vwap = close.iloc[-1] > vwap.iloc[-1]
    
    #━━━━━━━━━━━━━━━━━━━━━━
    # 6. Today Pivot (简化版)
    #━━━━━━━━━━━━━━━━━━━━━━
    last_24h = df.tail(1440)
    if len(last_24h) > 0:
        d_high = last_24h['high'].max()
        d_low = last_24h['low'].min()
        d_close = last_24h['close'].iloc[-1]
        today_pivot = (d_high + d_low + d_close) / 3
    else:
        today_pivot = close.iloc[-1]
    
    close_gt_pivot = close.iloc[-1] > today_pivot
    
    # 返回所有指标
    return {
        # EMA
        'ema10_gt_20': ema10_gt_20,
        'close_gt_ema50': close_gt_ema50,
        'close_gt_ema200': close_gt_ema200,
        
        # SuperTrend
        'st_bull': st_bull,
        
        # UT Bot (核心)
        'ut_bull': ut_bull,  # 这是UT Bot行的状态
        'ut_stop': ut_stop.iloc[-1],
        'ut_bull_history': ut_bull_history,
        
        # 买卖信号
        'buy_signal': buy_signal,
        'sell_signal': sell_signal,
        
        # VWAP
        'close_gt_vwap': close_gt_vwap,
        'vwap': vwap.iloc[-1],
        
        # Pivot
        'close_gt_pivot': close_gt_pivot,
        'today_pivot': today_pivot,
        
        # 当前价格
        'close': close.iloc[-1]
    }

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
    buy_signals = []
    
    status = st.empty()
    status.info(f"🔄 第{st.session_state.scan_count}次扫描 {current_time.strftime('%H:%M:%S')}")
    
    progress_bar = st.progress(0)
    
    for i, symbol in enumerate(SYMBOLS):
        df = fetch_ohlcv(symbol)
        if df is not None and len(df) >= 50:
            ind = calculate_all_indicators(df)
            
            # 全绿条件
            all_green = all([
                ind['ema10_gt_20'],
                ind['st_bull'],
                ind['ut_bull'],  # 注意：这里是ut_bull，不是buy_signal
                ind['close_gt_vwap']
            ])
            
            result = {
                '交易对': symbol,
                '时间': current_time.strftime('%H:%M:%S'),
                '价格': f"${ind['close']:,.2f}" if 'BTC' in symbol else f"${ind['close']:.4f}",
                
                # EMA
                'EMA10>20': '✅' if ind['ema10_gt_20'] else '❌',
                'EMA50': '✅' if ind['close_gt_ema50'] else '❌',
                'EMA200': '✅' if ind['close_gt_ema200'] else '❌',
                
                # SuperTrend
                'SuperTrend': '✅' if ind['st_bull'] else '❌',
                
                # UT Bot - 这就是图表上显示BUY/SELL的那一行
                'UT Bot': 'BUY' if ind['ut_bull'] else 'SELL',
                
                # 实际买卖信号
                'UT信号': 'BUY🔥' if ind['buy_signal'] else ('SELL⚠️' if ind['sell_signal'] else '➖'),
                
                # VWAP & Pivot
                'VWAP': '✅' if ind['close_gt_vwap'] else '❌',
                'Pivot': '✅' if ind['close_gt_pivot'] else '❌',
                
                # 全绿信号
                '全绿': '✅' if all_green else '❌',
                
                # 调试信息
                'UT止损': f"${ind['ut_stop']:,.2f}",
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
        send_telegram_message(msg)
        st.balloons()

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
        st.metric("UT BUY状态", len(df_results[df_results['UT Bot'] == 'BUY']))
    with col3:
        st.metric("UT SELL状态", len(df_results[df_results['UT Bot'] == 'SELL']))
    with col4:
        st.metric("BUY信号", len(df_results[df_results['UT信号'] == 'BUY🔥']))
    with col5:
        st.metric("全绿信号", len(df_results[df_results['全绿'] == '✅']))
    with col6:
        st.metric("扫描次数", st.session_state.scan_count)

# ================= 调试信息 =================
with st.expander("🔍 查看BTC详细调试"):
    btc_data = next((r for r in st.session_state.scan_results if r['交易对'] == 'BTC/USDT'), None)
    if btc_data:
        st.write("### BTC/USDT当前状态")
        st.json({
            '价格': btc_data['价格'],
            'UT Bot状态': btc_data['UT Bot'],
            'UT信号': btc_data['UT信号'],
            '价格>止损': btc_data['价格>止损'],
            'UT止损': btc_data['UT止损'],
            '全绿': btc_data['全绿']
        })
        
        # 判断逻辑说明
        st.write("### UT Bot判断逻辑")
        st.write("图表UT Bot行显示规则：")
        st.write("- **BUY**: 价格 > UT止损线")
        st.write("- **SELL**: 价格 < UT止损线")
        
        # 从BTC数据中提取数值
        price_str = btc_data['价格'].replace('$', '').replace(',', '')
        stop_str = btc_data['UT止损'].replace('$', '').replace(',', '')
        
        if price_str and stop_str:
            price = float(price_str)
            stop = float(stop_str)
            st.write(f"当前价格: {price:,.2f}")
            st.write(f"UT止损: {stop:,.2f}")
            st.write(f"价格 > 止损: {price > stop}")
            st.write(f"所以UT Bot显示: **{'BUY' if price > stop else 'SELL'}**")

# ================= 使用说明 =================
st.markdown("---")
st.markdown("""
### 📝 指标说明（完全匹配Pine Script）

| 列名 | 含义 | 对应Pine Script |
|------|------|-----------------|
| **UT Bot** | UT多空状态 | `f_ut_row(5, "UT Bot", utBull)` - 显示BUY/SELL |
| **UT信号** | 实际买卖信号 | 图表上的BUY/SELL标签 |
| **全绿** | 所有条件满足 | EMA10>20 + SuperTrend多头 + UT多头 + VWAP |

### 🎯 当前重点
- **UT Bot列**应该和你的图表完全一致
- 如果BTC价格69,058 > UT止损，就显示BUY
- 使用OKX数据源，匹配你的设置
""")

# ================= 自动刷新 =================
time.sleep(2)
st.rerun()
