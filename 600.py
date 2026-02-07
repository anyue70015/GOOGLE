import streamlit as st
import pandas as pd
import numpy as np
import pandas_ta as ta
import ccxt
import requests
from datetime import datetime
import pytz
from streamlit_autorefresh import st_autorefresh
import streamlit.components.v1 as components

# ==================== 1. 配置与参数 ====================
st.set_page_config(page_title="UT Bot 极速看板", layout="wide")
BEIJING_TZ = pytz.timezone('Asia/Shanghai')
st_autorefresh(interval=300 * 1000, key="refresh_5min") # 5分钟刷新

# 集成你的 WxPusher 信息
DEFAULT_APP_TOKEN = "AT_3H9akFZPvOE98cPrDydWmKM4ndgT3bVH"
DEFAULT_UID = "UID_wfbEjBobfoHNLmprN3Pi5nwWb4oM"

# 状态初始化
if 'last_alerts' not in st.session_state:
    st.session_state.last_alerts = {} 

# ==================== 2. 核心功能函数 ====================
def send_wx_pusher(title, body):
    try:
        payload = {
            "appToken": DEFAULT_APP_TOKEN,
            "content": f"{title}\n{body}",
            "summary": title[:100],
            "uids": [DEFAULT_UID]
        }
        requests.post("https://wxpusher.zjiecode.com/api/send/message", json=payload, timeout=5)
        st.toast(f"微信报警已发出: {title}", icon="🔔")
    except Exception as e:
        st.error(f"推送异常: {str(e)}")

def calculate_indicators(df, sensitivity, atr_period):
    if df.empty or len(df) < 50: return pd.DataFrame()
    df.columns = [str(c).capitalize() for c in df.columns]
    
    # UT Bot 计算
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
    df['ema20'] = ta.ema(df['Close'], length=20)
    df['ema50'] = ta.ema(df['Close'], length=50)
    return df

def get_sig_details(df):
    if df.empty: return "N/A", 0, "N/A", "N/A", "N/A"
    curr_p = float(df.iloc[-1]['Close'])
    rsi_val = f"{df.iloc[-1]['rsi']:.1f}"
    
    # 趋势判定
    if curr_p > df.iloc[-1]['ema20'] > df.iloc[-1]['ema50']: t = "多头 🟢"
    elif curr_p < df.iloc[-1]['ema20'] < df.iloc[-1]['ema50']: t = "空头 🔴"
    else: t = "震荡 ⚪"
    
    # 获取最新信号方向
    buys = df[df['buy']]
    sells = df[df['sell']]
    bt = buys.index[-1] if not buys.empty else None
    st_t = sells.index[-1] if not sells.empty else None
    
    if bt and (not st_t or bt > st_t): s = "BUY 🟢"
    elif st_t and (not bt or st_t > bt): s = "SELL 🔴"
    else: s = "HOLD ⚪"
    
    return s, curr_p, rsi_val, t, df.index[-1].strftime('%Y-%m-%d %H:%M')

# ==================== 3. 主页面布局 ====================
st.sidebar.header("🛡️ 核心设置")
sensitivity = st.sidebar.slider("UT Bot 敏感度", 0.1, 5.0, 1.0, 0.1)
atr_period = st.sidebar.slider("ATR 周期", 1, 30, 10)

CRYPTO_LIST = ["BTC", "ETH", "SOL", "SUI", "RENDER", "DOGE", "XRP", "HYPE", "AAVE", "TAO", "XAG", "XAU"]
selected_cryptos = st.sidebar.multiselect("品种", CRYPTO_LIST, default=CRYPTO_LIST)
intervals = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]

st.markdown("<h3 style='text-align:center;'>UT Bot 贵金属 & 加密货币监控</h3>", unsafe_allow_html=True)

# 倒计时
components.html(f"""
<div style="font-size:1em; color:#888; text-align:center;">
  刷新倒计时: <span id="cd" style="font-weight:bold; color:#ff4b4b;">300</span> 秒
</div>
<script>
let s=300; const t=document.getElementById('cd');
setInterval(()=>{{s--; t.textContent=s; if(s<=0)s=300;}},1000);
</script>
""", height=30)

# ==================== 4. 数据抓取与显示 ====================
ex = ccxt.okx({'enableRateLimit': True, 'timeout': 10000})
rows = []
contracts = {"TAO", "XAG", "XAU"}

with st.spinner("正在获取最新报价..."):
    for base in selected_cryptos:
        sym = f"{base}/USDT:USDT" if base in contracts else f"{base}/USDT"
        row = {"资产": f"**{base}**"}
        last_price = "N/A"
        current_trend = "N/A"
        
        for tf in intervals:
            try:
                bars = ex.fetch_ohlcv(sym, timeframe=tf, limit=100)
                df = calculate_indicators(pd.DataFrame(bars, columns=['ts','o','h','l','c','v']).assign(ts=lambda x: pd.to_datetime(x['ts'], unit='ms')).set_index('ts'), sensitivity, atr_period)
                sig, p, rsi, trend, ktime = get_sig_details(df)
                
                # 记录最后一次循环的价格和趋势
                last_price = p
                current_trend = trend
                
                # 格式化表格显示
                color = "#00ff00" if "BUY" in sig else "#ff4b4b" if "SELL" in sig else "#888"
                row[tf] = f"<div style='color:{color}; font-weight:bold;'>{sig}</div><div style='font-size:0.8em; color:#aaa;'>RSI:{rsi}</div>"
                
                # --- 报警触发：仅限 30m 和 1h ---
                if tf in ["30m", "1h"]:
                    key = (base, tf)
                    last_alert = st.session_state.last_alerts.get(key, {"sig": None, "time": None})
                    
                    if sig != last_alert["sig"] and ktime != last_alert["time"] and "HOLD" not in sig:
                        title = f"🚨 {base} ({tf}) {sig}!"
                        body = f"价格: {p}\nRSI: {rsi}\n趋势: {trend}\n时间: {ktime} (UTC)"
                        send_wx_pusher(title, body)
                        st.session_state.last_alerts[key] = {"sig": sig, "time": ktime}
                        
            except:
                row[tf] = "<span style='color:#444;'>-</span>"

        # 价格显示在最后
        row["当前趋势"] = current_trend
        row["实时价格"] = f"<b style='color:#f0b90b;'>{last_price}</b>"
        rows.append(row)

# 渲染表格
df_final = pd.DataFrame(rows)
st.write(df_final.to_html(escape=False, index=False), unsafe_allow_html=True)

st.caption(f"数据源: OKX | 最后更新: {datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')}")
