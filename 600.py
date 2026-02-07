import streamlit as st
import pandas as pd
import numpy as np
import pandas_ta as ta
import ccxt
import requests
from datetime import datetime
import pytz
from streamlit_autorefresh import st_autorefresh

# ==================== 1. 基础配置 (集成你的 Token) ====================
st.set_page_config(page_title="UT Bot 看板", layout="wide")
BEIJING_TZ = pytz.timezone('Asia/Shanghai')
st_autorefresh(interval=300 * 1000, key="refresh_5min") 

# 直接写死你的 Token
APP_TOKEN = "AT_3H9akFZPvOE98cPrDydWmKM4ndgT3bVH"
UID = "UID_wfbEjBobfoHNLmprN3Pi5nwWb4oM"

if 'last_alerts' not in st.session_state:
    st.session_state.last_alerts = {}

# ==================== 2. 功能函数 ====================
def send_wx(title, body):
    try:
        url = "https://wxpusher.zjiecode.com/api/send/message"
        data = {"appToken": APP_TOKEN, "content": f"{title}\n{body}", "uids": [UID]}
        requests.post(url, json=data, timeout=5)
    except: pass

def calculate_indicators(df, sensitivity, atr_period):
    # 这里保持你最初的计算代码
    df.columns = [str(c).capitalize() for c in df.columns]
    df['atr'] = ta.atr(df['High'], df['Low'], df['Close'], length=atr_period)
    df = df.dropna(subset=['atr']).copy()
    n_loss = sensitivity * df['atr']
    src = df['Close']
    trail_stop = np.zeros(len(df))
    for i in range(1, len(df)):
        p = trail_stop[i-1]
        if src.iloc[i] > p and src.iloc[i-1] > p:
            trail_stop[i] = max(p, src.iloc[i] - n_loss.iloc[i])
        elif src.iloc[i] < p and src.iloc[i-1] < p:
            trail_stop[i] = min(p, src.iloc[i] + n_loss.iloc[i])
        else:
            trail_stop[i] = src.iloc[i] - n_loss.iloc[i] if src.iloc[i] > p else src.iloc[i] + n_loss.iloc[i]
    df['trail_stop'] = trail_stop
    df['buy'] = (df['Close'] > df['trail_stop']) & (df['Close'].shift(1) <= df['trail_stop'].shift(1))
    df['sell'] = (df['Close'] < df['trail_stop']) & (df['Close'].shift(1) >= df['trail_stop'].shift(1))
    df['rsi'] = ta.rsi(df['Close'], length=14)
    return df

# ==================== 3. 主逻辑 ====================
ex = ccxt.okx({'enableRateLimit': True})
# TAO, XAG, XAU 是合约
CRYPTO_LIST = ["BTC", "ETH", "SOL", "SUI", "RENDER", "DOGE", "XRP", "HYPE", "AAVE", "TAO", "XAG", "XAU"]
intervals = ["5m", "15m", "30m", "1h", "4h"]

rows = []
for base in CRYPTO_LIST:
    # 回归你最初的 Symbol 拼接逻辑
    if base in ["TAO", "XAG", "XAU"]:
        sym = f"{base}/USDT:USDT"
    else:
        sym = f"{base}/USDT"
    
    row = {"资产": base}
    current_price = 0
    
    for tf in intervals:
        try:
            bars = ex.fetch_ohlcv(sym, timeframe=tf, limit=100)
            df = calculate_indicators(pd.DataFrame(bars, columns=['ts','o','h','l','c','v']), 1.0, 10)
            
            # 获取最新状态
            last_row = df.iloc[-1]
            ktime = last_row.name # 或 df.index[-1]
            
            # 确定信号
            buys = df[df['buy']]
            sells = df[df['sell']]
            last_b = buys.index[-1] if not buys.empty else 0
            last_s = sells.index[-1] if not sells.empty else 0
            
            sig = "BUY 🟢" if last_b > last_s else "SELL 🔴"
            row[tf] = f"{sig} (RSI:{last_row['rsi']:.1f})"
            current_price = last_row['Close']
            
            # --- 报警触发逻辑 ---
            if tf in ["30m", "1h"]:
                key = (base, tf)
                # 状态锁：对比信号颜色和K线时间
                last_alert = st.session_state.last_alerts.get(key, {"sig": None, "time": None})
                if sig != last_alert["sig"]:
                    send_wx(f"🚨 {base} {tf} 变号！", f"最新: {sig}\n价格: {current_price}")
                    st.session_state.last_alerts[key] = {"sig": sig, "time": ktime}
        except:
            row[tf] = "ERR"
            
    # 价格放在最后一列
    row["实时价格"] = current_price
    rows.append(row)

st.table(pd.DataFrame(rows))
