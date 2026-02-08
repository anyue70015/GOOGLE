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

# ==================== 1. 核心配置 ====================
APP_TOKEN = "AT_3H9akFZPvOE98cPrDydWmKM4ndgT3bVH"
USER_UID = "UID_wfbEjBobfoHNLmprN3Pi5nwWb4oM"

# 资产分类（根据你的要求：TAO, XAG, XAU 为合约，其余为现货）
CRYPTO_LIST = ["BTC", "ETH", "SOL", "SUI", "RENDER", "DOGE", "XRP", "HYPE", "AAVE", "TAO", "XAG", "XAU"]
CONTRACTS = {"TAO", "XAG", "XAU"}
INTERVALS = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]

# ==================== 2. 函数定义 ====================
def send_wx_pusher(title, body):
    """发送微信推送"""
    if not APP_TOKEN or not USER_UID:
        return
    try:
        payload = {
            "appToken": APP_TOKEN,
            "content": f"{title}\n{body}",
            "summary": title[:100],
            "uids": [USER_UID]
        }
        response = requests.post("https://wxpusher.zjiecode.com/api/send/message", json=payload, timeout=5)
        if response.status_code == 200:
            res_json = response.json()
            if res_json.get("code") == 1000:
                st.toast(f"推送成功: {title}", icon="✅")
            else:
                st.toast(f"推送失败: {res_json.get('msg')}", icon="⚠️")
    except Exception as e:
        st.toast(f"WxPusher 异常: {str(e)}", icon="❌")

def calculate_indicators(df, sensitivity, atr_period):
    """计算 UT Bot 核心逻辑"""
    if df.empty or len(df) < 50:
        return pd.DataFrame()
    
    df.columns = [str(c).capitalize() for c in df.columns]
    
    # UT Bot 逻辑
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
    
    return df

def get_sig(df):
    """解析信号和趋势"""
    if df.empty:
        return "HOLD ⚪", None, "N/A", "N/A", "N/A"
    
    curr_p = float(df.iloc[-1]['Close'])
    rsi_val = f"{df.iloc[-1]['rsi']:.1f}" if pd.notna(df.iloc[-1]['rsi']) else "N/A"
    
    # 趋势判断
    if curr_p > df.iloc[-1]['ema20'] > df.iloc[-1]['ema50']:
        trend = "多头 🟢"
    elif curr_p < df.iloc[-1]['ema20'] < df.iloc[-1]['ema50']:
        trend = "空头 🔴"
    else:
        trend = "震荡 ⚪"
    
    # 获取最近的 Buy/Sell 信号
    buys = df[df['buy']]
    sells = df[df['sell']]
    lb_time = buys.index[-1] if not buys.empty else None
    ls_time = sells.index[-1] if not sells.empty else None
    
    if lb_time and (not ls_time or lb_time > ls_time):
        sig = "BUY 🟢"
    elif ls_time and (not lb_time or ls_time > lb_time):
        sig = "SELL 🔴"
    else:
        sig = "HOLD ⚪"
        
    return sig, curr_p, rsi_val, trend, df.index[-1].strftime('%Y-%m-%d %H:%M')

def get_ls_ratio(base):
    """获取多空比数据"""
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

# ==================== 3. Streamlit UI ====================
st.set_page_config(page_title="UT Bot Pro 看板", layout="wide")
BEIJING_TZ = pytz.timezone('Asia/Shanghai')

# 自动刷新 (5分钟)
st_autorefresh(interval=300 * 1000, key="auto_refresh_logic")

# 报警状态锁 (持久化信号状态)
if 'last_alerts' not in st.session_state:
    st.session_state.last_alerts = {}

# 侧边栏
st.sidebar.header("🛡️ 策略参数")
sensitivity = st.sidebar.slider("UT Bot 敏感度", 0.1, 5.0, 1.0, 0.1)
atr_period = st.sidebar.slider("ATR 周期", 1, 30, 10)
selected_cryptos = st.sidebar.multiselect("监控品种", CRYPTO_LIST, default=CRYPTO_LIST)

st.sidebar.header("⚙️ 报警状态")
force_test_alert = st.sidebar.checkbox("强制推送调试", value=False)
st.sidebar.success("WxPusher 配置已激活")

# 主界面显示
st.markdown("<h3 style='text-align:center;'>UT Bot 实时信号清算看板</h3>", unsafe_allow_html=True)
components.html("""
<div style="font-size:1em; color:#888; text-align:center;">
    刷新倒计时: <span id="cd" style="font-weight:bold; color:#0f0;">300</span>s
</div>
<script>
let s=300; const t=document.getElementById('cd');
setInterval(()=>{s--; t.textContent=s; if(s<=0)s=300;},1000);
</script>
""", height=30)

# ==================== 4. 主循环逻辑 ====================
ex = ccxt.okx({'enableRateLimit': True, 'timeout': 10000})
rows = []

with st.spinner("同步全球市场数据中..."):
    for base in selected_cryptos:
        # 自动识别合约/现货
        sym = f"{base}/USDT:USDT" if base in CONTRACTS else f"{base}/USDT"
        ls_ratio = get_ls_ratio(base)
        row = {"资产": base, "多空比(5m)": ls_ratio}
        
        for tf in INTERVALS:
            try:
                # 抓取数据
                bars = ex.fetch_ohlcv(sym, timeframe=tf, limit=100)
                df_ohlcv = pd.DataFrame(bars, columns=['ts','open','high','low','close','vol'])
                df_ohlcv['ts'] = pd.to_datetime(df_ohlcv['ts'], unit='ms')
                df_ohlcv.set_index('ts', inplace=True)
                
                # 计算指标
                pdf = calculate_indicators(df_ohlcv, sensitivity, atr_period)
                sig, price, rsi, trend, k_time = get_sig(pdf)
                
                row[tf] = f"<b>{sig}</b><br><small>RSI: {rsi}</small>"
                
                # --- 优化后的报警逻辑 ---
                if tf in ["30m", "1h"]:
                    alert_key = f"{base}_{tf}"
                    last_sig = st.session_state.last_alerts.get(alert_key)
                    
                    # 只有当信号确实发生了 BUY <-> SELL 的改变时触发
                    # 或者是强制调试模式
                    is_flipped = last_sig is not None and last_sig != sig
                    is_first_signal = last_sig is None and "HOLD" not in sig
                    
                    if force_test_alert or is_flipped or is_first_signal:
                        if "HOLD" not in sig:
                            asset_mark = "🔥合约" if base in CONTRACTS else "💰现货"
                            title = f"{asset_mark} {base} {tf} 信号转为: {sig}"
                            body = f"最新价格: {price}\nRSI: {rsi}\n当前趋势: {trend}\n多空比: {ls_ratio}\n数据时间: {k_time}"
                            
                            send_wx_pusher(title, body)
                            
                            # 更新缓存状态，确保本周期内该信号不再重复发
                            st.session_state.last_alerts[alert_key] = sig
                            
            except Exception:
                row[tf] = "RPC延迟"
        
        rows.append(row)

# ==================== 5. 渲染展示 ====================
res_df = pd.DataFrame(rows)
st.write(res_df.to_html(escape=False, index=False), unsafe_allow_html=True)

st.divider()
st.caption(f"🔧 自动运行中 | 最后同步时间: {datetime.now(BEIJING_TZ).strftime('%H:%M:%S')}")
