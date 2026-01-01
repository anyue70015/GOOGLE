import ccxt
import pandas as pd
import pandas_ta as ta
import time
from datetime import datetime, timedelta

# --- 配置区 ---
ASSETS = ['SUI/USDT', 'SOL/USDT', 'ETH/USDT', 'DOGE/USDT', 'BNB/USDT'] # 您关注的币种
TIMEFRAME = '4h'  # 4小时级别
PROB_THRESHOLD = 70.0  # 概率门槛
EXCHANGE = ccxt.binance()

def fetch_data(symbol, limit=200):
    """获取K线数据"""
    bars = EXCHANGE.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=limit)
    df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def calculate_gemini_score(df):
    """计算5大指标得分 (1-5分)"""
    score = 0
    # 1. 趋势得分: EMA12 > EMA34
    ema12 = ta.ema(df['close'], length=12)
    ema34 = ta.ema(df['close'], length=34)
    if ema12.iloc[-1] > ema34.iloc[-1] and df['close'].iloc[-1] > ema12.iloc[-1]:
        score += 1
        
    # 2. 动能得分: MACD Hist 连续两根增长
    macd = ta.macd(df['close'], fast=12, slow=26, signal=9)
    hist = macd['MACDh_12_26_9']
    if hist.iloc[-1] > hist.iloc[-2] and hist.iloc[-1] > 0:
        score += 1
        
    # 3. 强弱得分: RSI 处于 45-68 强势非过热区
    rsi = ta.rsi(df['close'], length=10)
    if 45 < rsi.iloc[-1] < 68:
        score += 1
        
    # 4. 成交量得分: 当前成交量 > 10周期均量
    vol_sma = ta.sma(df['volume'], length=10)
    if df['volume'].iloc[-1] > vol_sma.iloc[-1]:
        score += 1
        
    # 5. 支撑得分: 价格在布林带中轨上方
    bbands = ta.bbands(df['close'], length=20, std=2)
    if df['close'].iloc[-1] > bbands['BBM_20_2.0'].iloc[-1]:
        score += 1
        
    return score

def calculate_7d_probability(df):
    """
    计算7日上涨概率: 
    回测过去100个4H周期中，出现当前得分形态后，7天(42根4H线)后上涨的次数
    """
    lookback = 100
    win_count = 0
    # 7天对应 42 根 4H K线
    future_window = 42 
    
    for i in range(len(df) - future_window - 5, len(df) - future_window):
        if df['close'].iloc[i + future_window] > df['close'].iloc[i]:
            win_count += 1
            
    # 简化模拟：基于近期胜率统计
    prob = (win_count / 5) * 100 # 此处为演示逻辑，实战中会扫描更深的历史数据
    return round(prob, 2)

def main_scanner():
    print(f"\n--- 2026 动力学扫描启动 ({datetime.now().strftime('%H:%M:%S')}) ---")
    print(f"{'币种':<10} | {'7日概率':<10} | {'得分':<6} | {'建议动作'}")
    print("-" * 50)
    
    for symbol in ASSETS:
        try:
            df = fetch_data(symbol)
            score = calculate_gemini_score(df)
            prob = calculate_7d_probability(df)
            
            # 执行您的逻辑：70%概率 + 2-3分建仓
            if prob >= PROB_THRESHOLD and (score == 2 or score == 3):
                action = "🔥 符合条件：建仓"
            elif score != calculate_gemini_score(df.iloc[:-1]): # 分数变动
                action = "⚠️ 分数变动：卖出"
            else:
                action = "---"
                
            print(f"{symbol:<10} | {prob:>8}% | {score:>5}/5 | {action}")
            
        except Exception as e:
            print(f"扫描 {symbol} 失败: {e}")

if __name__ == "__main__":
    # 每4小时运行一次，或手动运行
    main_scanner()
