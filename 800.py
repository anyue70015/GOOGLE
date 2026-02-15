import streamlit as st
import ccxt
import pandas as pd
import ta  # pip install ta
import time
import telegram  # from python-telegram-bot
from datetime import datetime

# 配置
exchange = ccxt.okx({'enableRateLimit': True})  # 或 binance
symbols = ['HYPE/USDT', 'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'ADA/USDT', 
           'XRP/USDT', 'DOT/USDT', 'LINK/USDT', 'AVAX/USDT', 'TRX/USDT']  # 你的10个

timeframe = '15m'  # 15分钟K
telegram_token = 'YOUR_BOT_TOKEN'  # 从BotFather获取
chat_id = 'YOUR_CHAT_ID'  # @userinfobot查
bot = telegram.Bot(token=telegram_token)

def fetch_ohlcv(symbol):
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=200)  # 够算EMA200
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def check_conditions(df):
    close = df['close']
    
    # EMA5 > EMA13
    ema5 = ta.trend.ema_indicator(close, window=5)
    ema13 = ta.trend.ema_indicator(close, window=13)
    cond_ema = ema5.iloc[-1] > ema13.iloc[-1]
    
    # SuperTrend Up (用ta库标准实现，factor=3, period=10)
    supertrend = ta.trend.supertrend(high=df['high'], low=df['low'], close=close, period=10, multiplier=3)
    cond_st = close.iloc[-1] > supertrend['SUPERT_10_3.0'].iloc[-1]  # 价格 > SuperTrend线
    
    # UT Bot BUY (简化翻转版，类似你的Pine逻辑)
    atr = ta.volatility.atr(high=df['high'], low=df['low'], close=close, window=10)
    factor = 1.0
    ut_stop = close - factor * atr  # 简化up trail
    # 更准需var逻辑，但pandas难模拟var，用最近翻转近似
    ut_bull = close > ut_stop
    cond_ut_buy = ut_bull.iloc[-1] and not ut_bull.iloc[-2]  # 翻转到多
    
    # VWAP (累计vwap，ta有vwap，但需volume；简化hlc3 vwap)
    typical = (df['high'] + df['low'] + close) / 3
    vwap = (typical * df['volume']).cumsum() / df['volume'].cumsum()
    cond_vwap = close.iloc[-1] > vwap.iloc[-1]
    
    all_green = cond_ema and cond_st and cond_ut_buy and cond_vwap
    return all_green, {
        'EMA5>13': cond_ema,
        'ST Up': cond_st,
        'UT BUY': cond_ut_buy,
        'VWAP YES': cond_vwap
    }

while True:
    for symbol in symbols:
        try:
            df = fetch_ohlcv(symbol)
            if len(df) < 100: continue  # 数据不够跳过
            
            triggered, details = check_conditions(df)
            if triggered:
                msg = f"全4绿警报！ {symbol} @ {timeframe}\n" + \
                      f"价格: {df['close'].iloc[-1]:.2f}\n" + \
                      "\n".join([f"{k}: {'YES' if v else 'NO'}" for k,v in details.items()])
                bot.send_message(chat_id=chat_id, text=msg)
                print(f"警报发送: {symbol}")
        except Exception as e:
            print(f"错误 {symbol}: {e}")
    
    time.sleep(60)  # 每分钟扫描一次（调整为15min收盘后更好用schedule）

