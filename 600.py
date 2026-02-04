import pandas as pd
import numpy as np
import pandas_ta as ta
import yfinance as yf
import requests
import time
from datetime import datetime

# --- 配置区 ---
SEND_KEY = '你的Server酱SendKey' # 替换为你的Key
SYMBOLS = ["BTC-USD", "ETH-USD", "SOL-USD", "NVDA", "AAPL"]
INTERVALS = {
    "30m": "30m",
    "1h": "60m",
    "4h": "720m", # yfinance 4h 有时不稳定，可用 60m 聚合或 1h
    "1d": "1d"
}

# --- 消息推送函数 ---
def send_wechat(title, content):
    url = f"https://sctapi.ftqq.com/{SEND_KEY}.send"
    data = {"title": title, "desp": content}
    try:
        requests.post(url, data=data)
    except Exception as e:
        print(f"推送失败: {e}")

# --- 核心计算逻辑 ---
def get_signal(symbol, interval):
    # 根据周期调整下载范围
    period = "7d" if "m" in interval else "100d"
    df = yf.download(symbol, period=period, interval=interval, progress=False)
    if len(df) < 20: return None
    
    df = df.copy()
    
    # 1. UT Bot 逻辑
    key_value = 1
    atr_period = 10
    df['atr'] = ta.atr(df['High'], df['Low'], df['Close'], length=atr_period)
    n_loss = key_value * df['atr']
    
    src = df['Close']
    trail_stop = np.zeros(len(df))
    for i in range(1, len(df)):
        p_stop = trail_stop[i-1]
        if src.iloc[i] > p_stop and src.iloc[i-1] > p_stop:
            trail_stop[i] = max(p_stop, src.iloc[i] - n_loss.iloc[i])
        elif src.iloc[i] < p_stop and src.iloc[i-1] < p_stop:
            trail_stop[i] = min(p_stop, src.iloc[i] + n_loss.iloc[i])
        else:
            trail_stop[i] = src.iloc[i] - n_loss.iloc[i] if src.iloc[i] > p_stop else src.iloc[i] + n_loss.iloc[i]
    
    # 2. 成交量过滤逻辑 (当前成交量 > 过去10个周期均值的1.5倍)
    df['vol_ma'] = df['Volume'].rolling(window=10).mean()
    is_vol_surge = df['Volume'].iloc[-1] > (df['vol_ma'].iloc[-1] * 1.5)
    
    # 3. 信号判定
    curr_price = src.iloc[-1]
    prev_price = src.iloc[-2]
    curr_stop = trail_stop[-1]
    prev_stop = trail_stop[-2]
    
    signal = None
    if curr_price > curr_stop and prev_price <= prev_stop:
        # 买入信号 + 检查成交量
        vol_status = "放量确认 ✅" if is_vol_surge else "缩量博弈 ⚠️"
        signal = f"🚀 BUY ({vol_status})"
    elif curr_price < curr_stop and prev_price >= prev_stop:
        signal = "📉 SELL"
        
    return signal, curr_price

# --- 主循环监测 ---
def monitor():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 开启多周期扫描...")
    
    for symbol in SYMBOLS:
        for label, interval in INTERVALS.items():
            result = get_signal(symbol, interval)
            if not result: continue
            
            signal, price = result
            if signal:
                msg_title = f"{signal}: {symbol} ({label})"
                msg_content = (
                    f"币种: {symbol}\n"
                    f"周期: {label}\n"
                    f"当前价格: {price:.2f}\n"
                    f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"注: UT Bot 穿越触发。"
                )
                print(f"找到信号! {msg_title}")
                send_wechat(msg_title, msg_content)
                
    print("扫描结束，等待下一轮。")

if __name__ == "__main__":
    # 建议每 15 或 30 分钟运行一次
    while True:
        monitor()
        time.sleep(1800) # 每 30 分钟扫描一次
