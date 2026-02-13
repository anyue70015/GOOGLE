import streamlit as st
import pandas as pd
import numpy as np
import ccxt
import requests
import os
from datetime import datetime
import pytz
import time

# ==================== 1. 核心配置 ====================
APP_TOKEN = "AT_3H9akFZPvOE98cPrDydWmKM4ndgT3bVH0"
USER_UID = "UID_wfbEjBobfoHNLmprN3Pi5nwWb4oM0"
LOG_FILE = "trade_resonance_master.csv"

CRYPTO_LIST = ["BTC", "ETH", "SOL", "SUI", "RENDER", "DOGE", "XRP", "HYPE", "AAVE", "TAO", "XAG", "XAU"]
CONTRACTS = {"TAO", "XAG", "XAU"}

DISPLAY_INTERVALS = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]

RESONANCE_GROUPS = {
    "Group1_短线(5-15-60)": ["5m", "15m", "1h"],
    "Group2_趋势(15-60-240)": ["15m", "1h", "4h"]
}
MAJOR_LEVELS = ["1h", "4h", "1d"]

BEIJING_TZ = pytz.timezone('Asia/Shanghai')

# ==================== 2. 功能函数 ====================

def load_logs():
    if os.path.exists(LOG_FILE):
        try:
            return pd.read_csv(LOG_FILE, encoding='utf-8-sig').to_dict('records')
        except:
            return []
    return []

def save_log_to_disk(entry):
    df = pd.DataFrame([entry])
    header = not os.path.exists(LOG_FILE)
    df.to_csv(LOG_FILE, mode='a', index=False, header=header, encoding='utf-8-sig')

def send_wx(title, body):
    try:
        payload = {
            "appToken": APP_TOKEN,
            "content": f"{title}\n{body}",
            "uids": [USER_UID]
        }
        requests.post("https://wxpusher.zjiecode.com/api/send/message", json=payload, timeout=5)
    except:
        pass

def calculate_ut_bot(df, sensitivity, atr_period):
    if df.empty:
        return pd.DataFrame()
    
    df.columns = [c.lower() for c in df.columns]
    
    # TR 计算
    tr = np.maximum.reduce([
        df['high'] - df['low'],
        (df['high'] - df['close'].shift()).abs(),
        (df['low'] - df['close'].shift()).abs()
    ])
    
    # 使用 ewm 近似 Wilder ATR（更稳定，NaN 更少）
    df['atr'] = tr.ewm(alpha=1/atr_period, min_periods=1, adjust=False).mean()
    
    n_loss = sensitivity * df['atr'].fillna(method='ffill').fillna(0)
    
    src = df['close']
    trail_stop = pd.Series(np.nan, index=df.index)
    trail_stop.iloc[0] = src.iloc[0]   # 初始值
    
    for i in range(1, len(df)):
        p = trail_stop.iloc[i-1]
        if np.isnan(p):
            trail_stop.iloc[i] = src.iloc[i]
            continue
            
        if src.iloc[i] > p and src.iloc[i-1] > p:
            trail_stop.iloc[i] = max(p, src.iloc[i] - n_loss.iloc[i])
        elif src.iloc[i] < p and src.iloc[i-1] < p:
            trail_stop.iloc[i] = min(p, src.iloc[i] + n_loss.iloc[i])
        else:
            trail_stop.iloc[i] = src.iloc[i] - n_loss.iloc[i] if src.iloc[i] > p else src.iloc[i] + n_loss.iloc[i]
    
    df['ts'] = trail_stop.fillna(src)  # 填充 NaN 防止 pos 计算出错
    df['pos'] = np.where(df['close'] > df['ts'], "BUY", "SELL")
    
    # sig_change 计算（更鲁棒）
    df['sig_change'] = False
    if len(df) >= 2:
        df['sig_change'].iloc[1:] = df['pos'].iloc[1:] != df['pos'].iloc[:-1]
    
    return df

def rsi_manual(close, period=14):
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period, min_periods=1).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period, min_periods=1).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def macd_manual(close, fast=12, slow=26, signal=9):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist

def obv_manual(close, volume):
    direction = np.sign(close.diff())
    obv = (direction * volume).fillna(0).cumsum()
    return obv

# ==================== 3. 主程序 ====================
st.set_page_config(page_title="UT Bot 多重看板+分列日志版", layout="wide")

if "alert_logs" not in st.session_state:
    st.session_state.alert_logs = load_logs()
if "sent_cache" not in st.session_state:
    st.session_state.sent_cache = {
        f"{l['资产']}_{l['类型']}_{l['时间'][:16]}" 
        for l in st.session_state.alert_logs if '类型' in l
    }

ex = ccxt.okx({
    'enableRateLimit': True,
    'defaultType': 'swap'
})

sens = st.sidebar.slider("敏感度", 0.1, 5.0, 1.0)
atrp = st.sidebar.slider("ATR周期", 1, 30, 10)

tp_ratio = st.sidebar.slider("止盈比率 (%)", 0.1, 10.0, 2.0) / 100
sl_ratio = st.sidebar.slider("止损比率 (%)", 0.1, 10.0, 1.0) / 100

rsi_period = st.sidebar.slider("RSI周期", 5, 30, 14)
rsi_buy_thresh = st.sidebar.slider("RSI BUY阈值 (>)", 30, 70, 50)
rsi_sell_thresh = st.sidebar.slider("RSI SELL阈值 (<)", 30, 70, 50)
macd_fast = st.sidebar.slider("MACD快线", 5, 20, 12)
macd_slow = st.sidebar.slider("MACD慢线", 20, 40, 26)
macd_signal = st.sidebar.slider("MACD信号线", 5, 15, 9)
atr_mult_thresh = st.sidebar.slider("ATR波动阈值倍数", 0.5, 2.0, 0.8)
obv_sma_period = st.sidebar.slider("OBV SMA周期", 5, 50, 20)

# 抓取数据 - 增强鲁棒性
all_data = {}
for base in CRYPTO_LIST:
    sym = f"{base}-USDT-SWAP" if base in CONTRACTS else f"{base}/USDT"
    all_data[base] = {}
    for tf in DISPLAY_INTERVALS:
        try:
            bars = ex.fetch_ohlcv(
                sym,
                timeframe=tf,
                limit=150,
                params={'category': 'swap'}
            )
            if not bars:
                raise ValueError("No data returned")
                
            df = pd.DataFrame(bars, columns=['ts','open','high','low','close','volume'])
            df['ts'] = pd.to_datetime(df['ts'], unit='ms', utc=True)
            df.set_index('ts', inplace=True)
            df = calculate_ut_bot(df, sens, atrp)
            
            if not df.empty:
                df['rsi'] = rsi_manual(df['close'], rsi_period)
                macd_line, macd_sig, _ = macd_manual(df['close'], macd_fast, macd_slow, macd_signal)
                df['macd'] = macd_line
                df['macd_signal'] = macd_sig
                df['obv'] = obv_manual(df['close'], df['volume'])
                df['obv_sma'] = df['obv'].rolling(obv_sma_period, min_periods=1).mean()
                df['atr_sma'] = df['atr'].rolling(atrp, min_periods=1).mean()
            
            all_data[base][tf] = df
            
        except Exception as e:
            st.sidebar.error(f"{base} {tf} 抓取失败: {str(e)[:80]}")
            all_data[base][tf] = pd.DataFrame()

# 生成看板
rows = []
now_str = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')

if "positions" not in st.session_state:
    st.session_state.positions = {}

for base in CRYPTO_LIST:
    p_15m = all_data[base].get("15m", pd.DataFrame())
    price_now = p_15m['close'].iloc[-1] if not p_15m.empty else "N/A"
    
    row = {"资产": base, "实时价格": f"<b>{price_now}</b>" if price_now != "N/A" else "N/A"}
    
    for tf in DISPLAY_INTERVALS:
        df = all_data[base].get(tf, pd.DataFrame())
        if df.empty:
            row[tf] = "-"
            continue
        curr = df.iloc[-1]
        color = "#00ff00" if curr['pos'] == "BUY" else "#ff0000"
        row[tf] = f"<div style='color:{color};font-weight:bold;'>{curr['pos']}</div><div style='font-size:0.75em;color:#888;'>Stop:{curr['ts']:.2f}</div>"
    
    rows.append(row)

    # 信号逻辑（共振 + 大周期） - 这里保持原样，重点先让表格显示
    # ... （省略信号逻辑部分，与你之前版本相同，确认表格先正常后再调试信号）

    # 止盈止损监控（同上）

# 渲染
st.markdown("<h3 style='text-align:center;'>🚀 UT Bot 多重过滤共振监控</h3>", unsafe_allow_html=True)

if rows:
    df_display = pd.DataFrame(rows)
    st.write(df_display.to_html(escape=False, index=False), unsafe_allow_html=True)
else:
    st.error("没有生成任何行数据，请检查数据抓取部分")

st.divider()
st.subheader("📜 分列历史日志")

if st.session_state.alert_logs:
    # ... 日志渲染部分保持不变 ...
    pass
else:
    st.info("监控运行中，暂无触发信号...")

st.sidebar.caption(f"最后刷新: {now_str}")
time.sleep(120)
st.rerun()
