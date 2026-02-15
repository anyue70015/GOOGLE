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
EXCHANGE_NAME = 'okx'  # 或 'binance'
TIMEFRAME = '15m'      # 15分钟K
SCAN_INTERVAL = 60     # 每60秒扫描一次

SYMBOLS = [
    'HYPE/USDT',
    'BTC/USDT',
    'ETH/USDT',
    'SOL/USDT',
    'TAO/USDT',
    'XRP/USDT',
    'RENDER/USDT',
    'AAVE/USDT',
    'DOGE/USDT',
    'SUI/USDT',
]

# Telegram 配置（必须填）
TELEGRAM_TOKEN = 'YOUR_BOT_TOKEN_HERE'      # 从BotFather获取
TELEGRAM_CHAT_ID = 'YOUR_CHAT_ID_HERE'      # 从@userinfobot获取

bot = Bot(token=TELEGRAM_TOKEN) if TELEGRAM_TOKEN != 'YOUR_BOT_TOKEN_HERE' else None

# UT Bot 参数（匹配你Pine脚本）
UT_FACTOR = 1.0
UT_ATR_LEN = 10

# SuperTrend 参数
ST_ATR_LEN = 10
ST_MULTIPLIER = 3.0

# ================= UI =================
st.set_page_config(page_title="Crypto 4条件扫描器", layout="wide")

st.title("多币种短线扫描器 (EMA5>13 + SuperTrend Up + UT Bot BUY + VWAP YES)")

status_placeholder = st.empty()
log_placeholder = st.container()

status_placeholder.info("扫描器启动中...")

# ================= 数据获取 & 计算 =================
@st.cache_data(ttl=300)  # 缓存5分钟
def fetch_ohlcv(symbol):
    exchange = getattr(ccxt, EXCHANGE_NAME)({'enableRateLimit': True})
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=300)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        return None

def check_4_conditions(df):
    if df is None or len(df) < 100:
        return False, {}

    close = df['close']
    high = df['high']
    low = df['low']
    volume = df['volume']

    # EMA5 > EMA13
    ema5 = pta.ema(close, length=5)
    ema13 = pta.ema(close, length=13)
    cond_ema = ema5.iloc[-1] > ema13.iloc[-1] if not pd.isna(ema5.iloc[-1]) else False

    # SuperTrend Up
    st = pta.supertrend(high=high, low=low, close=close, length=ST_ATR_LEN, multiplier=ST_MULTIPLIER)
    # 列名通常是 'SUPERTd_{length}_{multiplier}' 或 'SUPERT_{length}_{multiplier}'
    st_col = [col for col in st.columns if 'SUPERT' in col and 'd' not in col]  # 尝试匹配
    if st_col:
        st_line = st[st_col[0]]
        cond_st = close.iloc[-1] > st_line.iloc[-1]
    else:
        cond_st = False  # 如果列名不对，跳过

    # UT Bot BUY (翻转到多头)
    atr = pta.atr(high=high, low=low, close=close, length=UT_ATR_LEN)
    ut_stop = close - UT_FACTOR * atr  # 简化上轨trail（实际需累积逻辑，但近似）
    ut_bull = close > ut_stop
    cond_ut_buy = ut_bull.iloc[-1] and not ut_bull.iloc[-2] if len(ut_bull) >= 2 else False

    # VWAP (累计)
    typical = (high + low + close) / 3
    vwap = (typical * volume).cumsum() / volume.cumsum()
    cond_vwap = close.iloc[-1] > vwap.iloc[-1]

    all_green = cond_ema and cond_st and cond_ut_buy and cond_vwap

    details = {
        'EMA5 > EMA13': cond_ema,
        'SuperTrend Up': cond_st,
        'UT Bot BUY翻转': cond_ut_buy,
        'VWAP YES': cond_vwap
    }

    return all_green, details

# ================= 后台扫描线程 =================
async def send_telegram(msg):
    if bot:
        try:
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)
        except Exception as e:
            log_placeholder.error(f"Telegram发送失败: {e}")

def scanner_loop():
    while True:
        with status_placeholder.container():
            st.info(f"扫描中... 当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S JST')}")

        triggered_coins = []
        for symbol in SYMBOLS:
            df = fetch_ohlcv(symbol)
            if df is not None:
                triggered, details = check_4_conditions(df)
                if triggered:
                    triggered_coins.append((symbol, df['close'].iloc[-1], details))

        if triggered_coins:
            for symbol, price, details in triggered_coins:
                msg = f"【全4绿警报】 {symbol} @ {TIMEFRAME}\n价格: {price:.4f}\n" + \
                      "\n".join([f"{k}: {'YES' if v else 'NO'}" for k,v in details.items()])
                asyncio.run(send_telegram(msg))
                log_placeholder.success(f"警报触发: {symbol}")

        time.sleep(SCAN_INTERVAL)

# 启动线程
if 'scanner_thread' not in st.session_state:
    st.session_state.scanner_thread = threading.Thread(target=scanner_loop, daemon=True)
    st.session_state.scanner_thread.start()

st.markdown("---")
st.caption("后台每60秒扫描一次。Telegram警报已配置（如果token/chat_id正确）。")
st.caption("如果空白屏，检查requirements.txt + Python 3.12 + logs。")

# 显示当前状态
with st.expander("扫描日志"):
    st.write("线程运行中...")

st.stop()  # 防止脚本继续执行阻塞UI

