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

# ==================== 1. 函数定义 ====================
def send_wx_pusher(app_token, uid, title, body):
    if not app_token or not uid:
        return
    try:
        payload = {
            "appToken": app_token,
            "content": f"{title}\n{body}",
            "summary": title[:100],
            "uids": [uid]
        }
        response = requests.post("https://wxpusher.zjiecode.com/api/send/message", json=payload, timeout=5)
        if response.status_code == 200:
            res_json = response.json()
            if res_json.get("code") == 1000:
                st.toast("推送成功", icon="✅")
            else:
                st.toast(f"推送失败: {res_json.get('msg')}", icon="⚠️")
    except Exception as e:
        st.toast(f"WxPusher 异常: {str(e)}", icon="❌")

def calculate_indicators(df, sensitivity, atr_period):
    if df.empty or len(df) < 50:
        return pd.DataFrame()
    
    df.columns = [str(c).capitalize() for c in df.columns]
    
    # UT Bot 核心逻辑
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
    
    # 辅助指标
    df['rsi'] = ta.rsi(df['Close'], length=14)
    df['ema20'] = ta.ema(df['Close'], length=20)
    df['ema50'] = ta.ema(df['Close'], length=50)
    
    # MACD
    macd = ta.macd(df['Close'], fast=12, slow=26, signal=9)
    df['macd_dif'] = macd['MACD_12_26_9']
    df['macd_dea'] = macd['MACDs_12_26_9']
    
    return df

def get_sig(df):
    if df.empty:
        return "N/A", None, "N/A", "N/A", "N/A"
    
    curr_p = float(df.iloc[-1]['Close'])
    rsi_val = f"{df.iloc[-1]['rsi']:.1f}" if pd.notna(df.iloc[-1]['rsi']) else "N/A"
    
    # 趋势判断
    if curr_p > df.iloc[-1]['ema20'] > df.iloc[-1]['ema50']:
        trend = "多头 🟢"
    elif curr_p < df.iloc[-1]['ema20'] < df.iloc[-1]['ema50']:
        trend = "空头 🔴"
    else:
        trend = "震荡 ⚪"
    
    # 信号状态获取
    buys = df[df['buy']]
    sells = df[df['sell']]
    lb_time = buys.index[-1] if not buys.empty else None
    ls_time = sells.index[-1] if not sells.empty else None
    
    # 确定当前是多还是空
    if lb_time and (not ls_time or lb_time > ls_time):
        sig = "BUY 🟢"
    elif ls_time and (not lb_time or ls_time > lb_time):
        sig = "SELL 🔴"
    else:
        sig = "HOLD ⚪"
        
    return sig, curr_p, rsi_val, trend, df.index[-1].strftime('%Y-%m-%d %H:%M')

def get_ls_ratio(base):
    try:
        url = f"https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol={base.upper()}USDT&period=5m&limit=1"
        r = requests.get(url, timeout=5).json()
        if r and isinstance(r, list):
            ratio = float(r[0]['longShortRatio'])
            emoji = "🟢" if ratio > 1.2 else "🔴" if ratio < 0.8 else "⚪"
            return f"{ratio:.2f} {emoji}"
    except:
        pass
    return "N/A"

# ==================== 2. UI 配置 ====================
st.set_page_config(page_title="UT Bot 极速看板", layout="wide")
BEIJING_TZ = pytz.timezone('Asia/Shanghai')
st_autorefresh(interval=300 * 1000, key="refresh_5min")

if 'last_alerts' not in st.session_state:
    st.session_state.last_alerts = {} # Key: (base, tf), Value: {"sig": "BUY/SELL", "time": "K线时间"}

# 侧边栏
st.sidebar.header("🛡️ 策略参数")
sensitivity = st.sidebar.slider("UT Bot 敏感度", 0.1, 5.0, 1.0, 0.1)
atr_period = st.sidebar.slider("ATR 周期", 1, 30, 10)

CRYPTO_LIST = ["BTC", "ETH", "SOL", "SUI", "RENDER", "DOGE", "XRP", "HYPE", "AAVE", "TAO", "XAG", "XAU"]
selected_cryptos = st.sidebar.multiselect("监控品种", CRYPTO_LIST, default=CRYPTO_LIST)

st.sidebar.header("🚨 报警配置")
app_token = st.sidebar.text_input("WxPusher AppToken", type="password", value="AT_3H9akFZPvOE98cPrDydWmKM4ndgT3bVH")
user_uid = st.sidebar.text_input("WxPusher UID", type="password", value="UID_wfbEjBobfoHNLmprN3Pi5nwWb4oM")
force_test_alert = st.sidebar.checkbox("强制推送（调试用）", value=False)

intervals = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]

# ==================== 3. 主逻辑 ====================
st.markdown("<h3 style='text-align:center;'>UT Bot 实时清算看板</h3>", unsafe_allow_html=True)

# 倒计时显示
components.html("""
<div style="font-size:1em; color:#888; text-align:center;">
  距下次刷新: <span id="cd" style="font-weight:bold; color:#0f0;">300</span> 秒
</div>
<script>
let s=300; const t=document.getElementById('cd');
setInterval(()=>{s--; t.textContent=s; if(s<=0)s=300;},1000);
</script>
""", height=30)

ex = ccxt.okx({'enableRateLimit': True, 'timeout': 10000})
rows = []
contracts = {"TAO", "XAG", "XAU"}

with st.spinner("正在抓取全球市场数据..."):
    for base in selected_cryptos:
        sym = f"{base}/USDT:USDT" if base in contracts else f"{base}/USDT"
        ls_ratio = get_ls_ratio(base)
        row = {"资产": base, "多空比(5m)": ls_ratio}
        
        for tf in intervals:
            try:
                # 获取数据
                bars = ex.fetch_ohlcv(sym, timeframe=tf, limit=100)
                df_ohlcv = pd.DataFrame(bars, columns=['ts','open','high','low','close','vol'])
                df_ohlcv['ts'] = pd.to_datetime(df_ohlcv['ts'], unit='ms')
                df_ohlcv.set_index('ts', inplace=True)
                
                # 计算指标
                pdf = calculate_indicators(df_ohlcv, sensitivity, atr_period)
                sig, price, rsi, trend, k_time = get_sig(pdf)
                
                row[tf] = f"{sig}<br>RSI:{rsi}"
                
                # --- 核心报警触发逻辑 ---
                if tf in ["30m", "1h"] and app_token and user_uid:
                    key = (base, tf)
                    last_info = st.session_state.last_alerts.get(key, {"sig": None, "time": None})
                    
                    # 只有当信号类型改变，且是新的一根K线时触发
                    is_new_signal = sig != last_info["sig"]
                    is_new_kline = k_time != last_info["time"]
                    
                    if force_test_alert or (is_new_signal and is_new_kline):
                        if "HOLD" not in sig:
                            title = f"🚨 {base} {tf} 信号变动: {sig}"
                            body = f"价格: {price}\nRSI: {rsi}\n趋势: {trend}\n多空比: {ls_ratio}\n时间: {k_time}"
                            send_wx_pusher(app_token, user_uid, title, body)
                            
                            # 更新状态锁，防止同一根K线重复报警
                            st.session_state.last_alerts[key] = {"sig": sig, "time": k_time}
                            
            except Exception as e:
                row[tf] = "数据延迟"
        
        rows.append(row)

# 表格渲染
res_df = pd.DataFrame(rows)
st.write(res_df.to_html(escape=False, index=False), unsafe_allow_html=True)

st.caption(f"最后更新: {datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')}")

