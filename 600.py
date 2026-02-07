import streamlit as st
import pandas as pd
import numpy as np
import pandas_ta as ta
import ccxt
import requests
from datetime import datetime
import pytz
from streamlit_autorefresh import st_autorefresh

# ==================== 1. 配置与参数 ====================
st.set_page_config(page_title="UT Bot 监控 - 修复版", layout="wide")
BEIJING_TZ = pytz.timezone('Asia/Shanghai')
st_autorefresh(interval=300 * 1000, key="refresh_5min") 

# 自动集成你的 Token
DEFAULT_APP_TOKEN = "AT_3H9akFZPvOE98cPrDydWmKM4ndgT3bVH"
DEFAULT_UID = "UID_wfbEjBobfoHNLmprN3Pi5nwWb4oM"

if 'last_alerts' not in st.session_state:
    st.session_state.last_alerts = {}

# ==================== 2. 功能函数 ====================
def send_wx_pusher(title, body):
    try:
        payload = {
            "appToken": DEFAULT_APP_TOKEN,
            "content": f"{title}\n{body}",
            "uids": [DEFAULT_UID]
        }
        requests.post("https://wxpusher.zjiecode.com/api/send/message", json=payload, timeout=5)
    except:
        pass

def calculate_indicators(df, sensitivity, atr_period):
    try:
        if df.empty or len(df) < 20: return pd.DataFrame()
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
    except:
        return pd.DataFrame()

def get_sig_details(df):
    if df.empty: return "N/A", 0, "N/A", "N/A"
    curr_p = float(df.iloc[-1]['Close'])
    rsi_val = f"{df.iloc[-1]['rsi']:.1f}" if 'rsi' in df.columns else "N/A"
    
    buys = df[df['buy']]
    sells = df[df['sell']]
    bt = buys.index[-1] if not buys.empty else None
    st_t = sells.index[-1] if not sells.empty else None
    
    if bt and (not st_t or bt > st_t): s = "BUY 🟢"
    elif st_t and (not bt or st_t > bt): s = "SELL 🔴"
    else: s = "HOLD ⚪"
    return s, curr_p, rsi_val, df.index[-1].strftime('%H:%M')

# ==================== 3. 主界面 ====================
st.sidebar.header("🛡️ 策略设置")
sensitivity = st.sidebar.slider("敏感度", 0.1, 5.0, 1.0, 0.1)
atr_period = st.sidebar.slider("ATR周期", 1, 30, 10)

CRYPTO_LIST = ["BTC", "ETH", "SOL", "SUI", "RENDER", "DOGE", "XRP", "HYPE", "AAVE", "TAO", "XAG", "XAU"]
selected_cryptos = st.sidebar.multiselect("品种", CRYPTO_LIST, default=CRYPTO_LIST)
intervals = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]

st.title("UT Bot 实时看板")
st.write(f"下次刷新时间: {datetime.now(BEIJING_TZ).strftime('%H:%M:%S')} (每5分钟)")

ex = ccxt.okx({'enableRateLimit': True, 'timeout': 15000})
contracts = {"TAO", "XAG", "XAU"}

# 构造表格数据
table_rows = []

progress_bar = st.progress(0)
for idx, base in enumerate(selected_cryptos):
    sym = f"{base}/USDT:USDT" if base in contracts else f"{base}/USDT"
    row_data = {"资产": base}
    final_price = 0
    
    for tf in intervals:
        try:
            bars = ex.fetch_ohlcv(sym, timeframe=tf, limit=60)
            df_raw = pd.DataFrame(bars, columns=['ts','o','h','l','c','v'])
            df_raw['ts'] = pd.to_datetime(df_raw['ts'], unit='ms')
            df_raw.set_index('ts', inplace=True)
            
            df = calculate_indicators(df_raw, sensitivity, atr_period)
            sig, p, rsi, ktime = get_sig_details(df)
            
            row_data[tf] = f"{sig} (RSI:{rsi})"
            final_price = p
            
            # 报警触发
            if tf in ["30m", "1h"]:
                key = (base, tf)
                last_alert = st.session_state.last_alerts.get(key, {"sig": None, "time": None})
                if sig != last_alert["sig"] and ktime != last_alert["time"] and "HOLD" not in sig:
                    send_wx_pusher(f"🚨 {base} {tf} {sig}", f"价格: {p}\n时间: {ktime}")
                    st.session_state.last_alerts[key] = {"sig": sig, "time": ktime}
        except Exception as e:
            row_data[tf] = "ERR"
    
    row_data["当前价格"] = final_price
    table_rows.append(row_data)
    progress_bar.progress((idx + 1) / len(selected_cryptos))

# 使用 Streamlit 原生 Dataframe 显示，防止 HTML 冲突
if table_rows:
    display_df = pd.DataFrame(table_rows)
    st.dataframe(display_df, use_container_width=True)
else:
    st.warning("暂无数据，请检查网络连接或 API 状态")

st.info("注：XAG, XAU 为合约数据，其余为现货。")
