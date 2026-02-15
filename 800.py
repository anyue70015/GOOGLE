import streamlit as st
import ccxt
import pandas as pd
import pandas_ta as pta
import time
import threading
from datetime import datetime
from telegram import Bot
import asyncio

# ================= 配置 =================
EXCHANGE_NAME = 'okx'
TIMEFRAME = '5m'          # 已改成5分钟
SCAN_INTERVAL = 60        # 秒

SYMBOLS = [
    'HYPE/USDT',
    'BTC/USDT',
    'ETH/USDT',
    'SOL/USDT',
    'ADA/USDT',
    'XRP/USDT',
    'DOT/USDT',
    'LINK/USDT',
    'AVAX/USDT',
    'TRX/USDT',
]

# Telegram（填你的）
TELEGRAM_TOKEN = 'YOUR_BOT_TOKEN_HERE'
TELEGRAM_CHAT_ID = 'YOUR_CHAT_ID_HERE'

bot = Bot(token=TELEGRAM_TOKEN) if TELEGRAM_TOKEN != 'YOUR_BOT_TOKEN_HERE' else None

# 参数（匹配你图表）
UT_FACTOR = 1.0
UT_ATR_LEN = 10
ST_ATR_LEN = 10
ST_MULTIPLIER = 3.0

# ================= UI =================
st.set_page_config(page_title="5min 4条件扫描器", layout="wide")

st.title("5分钟多币种扫描器 (EMA10>20 + SuperTrend Up + UT Bot 多头 + VWAP YES)")

status_placeholder = st.empty()
log_placeholder = st.container()

status_placeholder.info("扫描器启动中...")

# ================= 数据 & 计算 =================
@st.cache_data(ttl=120)
def fetch_ohlcv(symbol):
    exchange = getattr(ccxt, EXCHANGE_NAME)({'enableRateLimit': True})
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=500)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        log_placeholder.error(f"拉数据失败 {symbol}: {e}")
        return None

def check_4_conditions(df, symbol):
    if df is None or len(df) < 100:
        return False, {}

    close = df['close']
    high = df['high']
    low = df['low']
    volume = df['volume']

    # EMA10 > EMA20 (匹配你图表)
    ema10 = pta.ema(close, length=10)
    ema20 = pta.ema(close, length=20)
    cond_ema = ema10.iloc[-1] > ema20.iloc[-1] if not pd.isna(ema10.iloc[-1]) else False

    # SuperTrend Up
    st = pta.supertrend(high=high, low=low, close=close, length=ST_ATR_LEN, multiplier=ST_MULTIPLIER)
    st_cols = st.columns
    st_line_col = None
    for col in st_cols:
        if 'SUPERT' in col and 'd' not in col:  # 值列如 SUPERT_10_3.0
            st_line_col = col
            break
    if st_line_col:
        st_line = st[st_line_col]
        cond_st = close.iloc[-1] > st_line.iloc[-1]
    else:
        cond_st = False  # 列名失败

    # UT Bot 多头区 (改成持续YES，匹配你图BUY)
    atr = pta.atr(high=high, low=low, close=close, length=UT_ATR_LEN)
    ut_stop = close - UT_FACTOR * atr   # 简化上轨
    ut_bull = close > ut_stop
    cond_ut_buy = ut_bull.iloc[-1] if len(ut_bull) > 0 else False

    # VWAP
    typical = (high + low + close) / 3
    vwap = (typical * volume).cumsum() / volume.cumsum()
    cond_vwap = close.iloc[-1] > vwap.iloc[-1]

    all_green = cond_ema and cond_st and cond_ut_buy and cond_vwap

    details = {
        'EMA10 > EMA20': cond_ema,
        'SuperTrend Up': cond_st,
        'UT Bot 多头': cond_ut_buy,
        'VWAP YES': cond_vwap
    }

    # 每轮日志输出（关键调试）
    log_msg = f"{symbol} ({TIMEFRAME}): " + " | ".join([f"{k}={ 'YES' if v else 'NO' }" for k,v in details.items()]) + f" | 全绿? {all_green}"
    log_placeholder.write(log_msg)

    return all_green, details

# ================= 后台扫描 =================
async def send_telegram(msg):
    if bot:
        try:
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)
        except Exception as e:
            log_placeholder.error(f"Telegram失败: {e}")

def scanner_loop():
    while True:
        status_placeholder.info(f"扫描中... {datetime.now().strftime('%Y-%m-%d %H:%M:%S JST')}")

        triggered = []
        for symbol in SYMBOLS:
            df = fetch_ohlcv(symbol)
            if df is not None:
                all_green, details = check_4_conditions(df, symbol)
                if all_green:
                    triggered.append((symbol, df['close'].iloc[-1], details))

        if triggered:
            for symbol, price, details in triggered:
                msg = f"【5min 全绿警报】 {symbol}\n价格: {price:.4f}\n" + \
                      "\n".join([f"{k}: {'YES' if v else 'NO'}" for k,v in details.items()])
                asyncio.run(send_telegram(msg))
                log_placeholder.success(f"触发: {symbol} - {msg}")

        time.sleep(SCAN_INTERVAL)

# 启动线程
if 'scanner_thread' not in st.session_state:
    st.session_state.scanner_thread = threading.Thread(target=scanner_loop, daemon=True)
    st.session_state.scanner_thread.start()

st.markdown("---")
st.caption("每60秒扫描一次。日志显示每个币状态。Telegram需正确token/chat_id。")
st.caption("调试提示：看日志中每个币的4条件，如果全YES但没警报，检查Telegram配置或ccxt数据。")

with st.expander("扫描日志"):
    st.write("线程运行中... 详细状态在上方实时刷新。")

st.stop()
