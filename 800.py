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
SCAN_INTERVAL = 60

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

TELEGRAM_TOKEN = 'YOUR_BOT_TOKEN_HERE'  # 改成你的
TELEGRAM_CHAT_ID = 'YOUR_CHAT_ID_HERE'

bot = Bot(token=TELEGRAM_TOKEN) if TELEGRAM_TOKEN != 'YOUR_BOT_TOKEN_HERE' else None

UT_FACTOR = 1.0
UT_ATR_LEN = 10
ST_ATR_LEN = 10
ST_MULTIPLIER = 3.0

# ================= UI =================
st.set_page_config(page_title="5min 扫描器 - 强制日志版", layout="wide")

st.title("5分钟多币种扫描器 (EMA10>20 + SuperTrend Up + UT Bot 多头 + VWAP YES)")

status = st.empty()
log = st.container()

status.info("启动中...")

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
        log.error(f"拉数据失败 {symbol}: {str(e)}")
        return None

def check_and_log(symbol):
    df = fetch_ohlcv(symbol)
    if df is None or len(df) < 100:
        log.write(f"{symbol}: 数据不足或失败")
        return False, {}

    close = df['close']
    high = df['high']
    low = df['low']
    volume = df['volume']

    ema10 = pta.ema(close, length=10)
    ema20 = pta.ema(close, length=20)
    cond_ema = ema10.iloc[-1] > ema20.iloc[-1] if not pd.isna(ema10.iloc[-1]) else False

    st = pta.supertrend(high=high, low=low, close=close, length=ST_ATR_LEN, multiplier=ST_MULTIPLIER)
    cond_st = False
    if 'SUPERT_10_3.0' in st.columns:
        cond_st = close.iloc[-1] > st['SUPERT_10_3.0'].iloc[-1]
    elif 'SUPERTd_10_3.0' in st.columns:
        cond_st = st['SUPERTd_10_3.0'].iloc[-1] < 0  # 方向 <0 表示up

    atr = pta.atr(high=high, low=low, close=close, length=UT_ATR_LEN)
    ut_stop = close - UT_FACTOR * atr
    ut_bull = close > ut_stop
    cond_ut_buy = ut_bull.iloc[-1]

    typical = (high + low + close) / 3
    vwap = (typical * volume).cumsum() / volume.cumsum()
    cond_vwap = close.iloc[-1] > vwap.iloc[-1]

    all_green = cond_ema and cond_st and cond_ut_buy and cond_vwap

    details = {
        'EMA10>20': cond_ema,
        'ST Up': cond_st,
        'UT 多头': cond_ut_buy,
        'VWAP YES': cond_vwap
    }

    log_msg = f"{symbol} ({TIMEFRAME}): " + " | ".join([f"{k}={ 'YES' if v else 'NO' }" for k,v in details.items()]) + f" | 全绿? {all_green}"
    log.write(log_msg)

    return all_green, details

# ================= 扫描函数 =================
def run_scan():
    status.info(f"扫描中... {datetime.now().strftime('%Y-%m-%d %H:%M:%S JST')}")
    triggered = []
    for symbol in SYMBOLS:
        all_green, details = check_and_log(symbol)
        if all_green:
            triggered.append((symbol, fetch_ohlcv(symbol)['close'].iloc[-1], details))

    if triggered:
        for symbol, price, details in triggered:
            msg = f"【5min 全绿】 {symbol} 价格 {price:.4f}\n" + "\n".join([f"{k}: YES" for k,v in details.items() if v])
            log.success(f"触发: {symbol}")
            if bot:
                bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)

# 后台循环
def background_scanner():
    while True:
        run_scan()
        time.sleep(SCAN_INTERVAL)

# 启动
if 'scanner_running' not in st.session_state:
    st.session_state.scanner_running = True
    threading.Thread(target=background_scanner, daemon=True).start()

# 手动测试按钮
if st.button("立即扫描一次（测试）"):
    run_scan()

st.markdown("---")
st.caption("每60秒自动扫描。页面会实时显示每个币的4条件状态。")
st.caption("如果日志有'ST Up=NO'，检查SuperTrend列名；如果无任何币日志，检查ccxt拉数据。")
st.caption("Telegram token/chat_id填错不会报错，但不会发消息。")

with st.expander("扫描日志"):
    st.write("等待扫描...")

st.stop()
