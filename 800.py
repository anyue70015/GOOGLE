import streamlit as st
import ccxt
import pandas as pd
import pandas_ta as pta
import time
from datetime import datetime
from telegram import Bot

# ================= 配置 =================
EXCHANGE_NAME = 'okx'
TIMEFRAME = '5m'
SCAN_INTERVAL = 60  # 秒，建议60-120，避免API限速

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

TELEGRAM_TOKEN = 'YOUR_BOT_TOKEN_HERE'   # 必须替换
TELEGRAM_CHAT_ID = 'YOUR_CHAT_ID_HERE'

bot = Bot(token=TELEGRAM_TOKEN) if TELEGRAM_TOKEN != 'YOUR_BOT_TOKEN_HERE' else None

UT_FACTOR = 1.0
UT_ATR_LEN = 10
ST_ATR_LEN = 10
ST_MULTIPLIER = 3.0

# ================= UI =================
st.set_page_config(page_title="5min 扫描器 - 稳定版", layout="wide")

st.title("5分钟多币种扫描器 (EMA10>20 + SuperTrend Up + UT Bot 多头 + VWAP YES)")

status = st.empty()
log_container = st.container()

# session_state 初始化
if 'last_scan_time' not in st.session_state:
    st.session_state.last_scan_time = 0
    st.session_state.scan_count = 0

# ================= 函数 =================
@st.cache_data(ttl=120)
def fetch_ohlcv(symbol):
    exchange = getattr(ccxt, EXCHANGE_NAME)({'enableRateLimit': True})
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=500)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        log_container.error(f"拉取失败 {symbol}: {str(e)}")
        return None

def perform_scan():
    st.session_state.scan_count += 1
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S JST')
    status.info(f"第 {st.session_state.scan_count} 次扫描 ({current_time})")

    triggered = []
    for symbol in SYMBOLS:
        df = fetch_ohlcv(symbol)
        if df is None or len(df) < 100:
            log_container.write(f"{symbol}: 数据不足")
            continue

        close = df['close']
        high = df['high']
        low = df['low']
        volume = df['volume']

        # EMA10 > EMA20
        ema10 = pta.ema(close, length=10)
        ema20 = pta.ema(close, length=20)
        cond_ema = ema10.iloc[-1] > ema20.iloc[-1] if not pd.isna(ema10.iloc[-1]) else False

        # SuperTrend Up
        st = pta.supertrend(high=high, low=low, close=close, length=ST_ATR_LEN, multiplier=ST_MULTIPLIER)
        cond_st = False
        if 'SUPERT_10_3.0' in st.columns:
            cond_st = close.iloc[-1] > st['SUPERT_10_3.0'].iloc[-1]
        elif 'SUPERTd_10_3.0' in st.columns:
            cond_st = st['SUPERTd_10_3.0'].iloc[-1] < 0

        # UT Bot 多头区
        atr = pta.atr(high=high, low=low, close=close, length=UT_ATR_LEN)
        ut_stop = close - UT_FACTOR * atr
        ut_bull = close > ut_stop
        cond_ut_buy = ut_bull.iloc[-1]

        # VWAP
        typical = (high + low + close) / 3
        vwap = (typical * volume).cumsum() / volume.cumsum()
        cond_vwap = close.iloc[-1] > vwap.iloc[-1]

        all_green = cond_ema and cond_st and cond_ut_buy and cond_vwap

        log_msg = f"{symbol}: EMA10>20={cond_ema} | ST Up={cond_st} | UT 多头={cond_ut_buy} | VWAP={cond_vwap} | 全绿={all_green}"
        log_container.write(log_msg)

        if all_green:
            triggered.append((symbol, close.iloc[-1], {'EMA': cond_ema, 'ST': cond_st, 'UT': cond_ut_buy, 'VWAP': cond_vwap}))

    if triggered:
        for symbol, price, details in triggered:
            msg = f"【5min 全绿】 {symbol} 价格 {price:.4f}\n" + "\n".join([f"{k}: YES" for k in details])
            log_container.success(f"警报: {symbol}")
            if bot:
                bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)

# ================= 主循环控制 =================
current_time = time.time()
if current_time - st.session_state.last_scan_time > SCAN_INTERVAL:
    perform_scan()
    st.session_state.last_scan_time = current_time

# 自动刷新
time.sleep(5)  # 小延迟防止太快rerun
st.rerun()

# 手动按钮
if st.button("立即扫描一次"):
    perform_scan()

st.caption("页面每几秒自动刷新扫描。日志实时显示每个币状态。")
st.caption("如果日志无输出，检查Manage app logs (ccxt错误/API限速/token错)。")
