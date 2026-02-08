import streamlit as st
import pandas as pd
import numpy as np
import pandas_ta as ta
import ccxt
import requests
from datetime import datetime
import pytz
from streamlit_autorefresh import st_autorefresh

# ==================== 1. 核心配置 ====================
APP_TOKEN = "AT_3H9akFZPvOE98cPrDydWmKM4ndgT3bVH"
USER_UID = "UID_wfbEjBobfoHNLmprN3Pi5nwWb4oM"

CRYPTO_LIST = ["BTC", "ETH", "SOL", "SUI", "RENDER", "DOGE", "XRP", "HYPE", "AAVE", "TAO", "XAG", "XAU"]
CONTRACTS = {"TAO", "XAG", "XAU"}
INTERVALS = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]
ALERT_INTERVALS = ["15m", "30m", "1h"]

BEIJING_TZ = pytz.timezone('Asia/Shanghai')

# ==================== 2. 函数定义 (必须放在调用前) ====================

def send_wx_pusher(title, body):
    """发送微信推送"""
    if not APP_TOKEN or not USER_UID: return
    try:
        payload = {"appToken": APP_TOKEN, "content": f"{title}\n{body}", "uids": [USER_UID]}
        requests.post("https://wxpusher.zjiecode.com/api/send/message", json=payload, timeout=5)
    except: pass

def get_ok_ls_ratio(ex, base):
    """获取 OKX 多空人数比"""
    try:
        # OKX 助推大户多空比接口
        inst_id = f"{base}-USDT-SWAP"
        params = {'instId': inst_id, 'period': '5m'}
        res = ex.publicGetRubikStatLongShortAccountRatio(params)
        if res['code'] == '0' and len(res['data']) > 0:
            ratio = float(res['data'][0][1])
            if ratio > 1.05: return f"{ratio:.2f} 偏多 🟢"
            elif ratio < 0.95: return f"{ratio:.2f} 偏空 🔴"
            else: return f"{ratio:.2f} 均衡 ⚪"
    except: pass
    return "N/A"

def calculate_indicators(df, sensitivity, atr_period):
    """计算 UT Bot 指标"""
    if df.empty or len(df) < 50: return pd.DataFrame()
    df.columns = [str(c).capitalize() for c in df.columns]
    df['atr'] = ta.atr(df['High'], df['Low'], df['Close'], length=atr_period)
    df = df.dropna(subset=['atr']).copy()
    n_loss = sensitivity * df['atr']
    src = df['Close']
    trail_stop = np.zeros(len(df))
    for i in range(1, len(df)):
        p = trail_stop[i-1]
        if src.iloc[i] > p and src.iloc[i-1] > p: trail_stop[i] = max(p, src.iloc[i] - n_loss.iloc[i])
        elif src.iloc[i] < p and src.iloc[i-1] < p: trail_stop[i] = min(p, src.iloc[i] + n_loss.iloc[i])
        else: trail_stop[i] = src.iloc[i] - n_loss.iloc[i] if src.iloc[i] > p else src.iloc[i] + n_loss.iloc[i]
    df['trail_stop'] = trail_stop
    df['buy_signal'] = (df['Close'] > df['trail_stop']) & (df['Close'].shift(1) <= df['trail_stop'].shift(1))
    df['sell_signal'] = (df['Close'] < df['trail_stop']) & (df['Close'].shift(1) >= df['trail_stop'].shift(1))
    return df

def get_status_and_signal(df):
    """解析表格状态与翻转报警信号"""
    if df.empty or len(df) < 3: return "N/A", "NONE", 0, "N/A"
    
    latest = df.iloc[-1]
    stop_price = f"{latest['trail_stop']:.4f}".rstrip('0').rstrip('.')
    
    # 1. 确定实时红绿状态 (去掉HOLD)
    if latest['Close'] > latest['trail_stop']:
        current_status = f"<div style='color:#00ff00; font-weight:bold;'>BUY 🟢</div><div style='font-size:0.8em; color:#888;'>离场:{stop_price}</div>"
    else:
        current_status = f"<div style='color:#ff0000; font-weight:bold;'>SELL 🔴</div><div style='font-size:0.8em; color:#888;'>离场:{stop_price}</div>"
    
    # 2. 确定翻转信号 (收盘确认: 倒数第二根)
    confirmed_k = df.iloc[-2]
    k_time = df.index[-2].astimezone(BEIJING_TZ).strftime('%m-%d %H:%M')
    alert_sig = "NONE"
    if confirmed_k['buy_signal']: alert_sig = "BUY 🟢"
    elif confirmed_k['sell_signal']: alert_sig = "SELL 🔴"
    
    return current_status, alert_sig, df.iloc[-1]['Close'], k_time

# ==================== 3. 持久化缓存 ====================
@st.cache_resource
def get_global_state():
    return {"sent_cache": {}, "alert_logs": []}

state = get_global_state()

# ==================== 4. 主程序界面 ====================
st.set_page_config(page_title="UT Bot 稳定版", layout="wide")
st_autorefresh(interval=300 * 1000, key="refresh_control")

# 侧边栏
st.sidebar.header("🛡️ 策略配置")
sensitivity = st.sidebar.slider("敏感度", 0.1, 5.0, 1.0, 0.1)
atr_period = st.sidebar.slider("ATR周期", 1, 30, 10)
selected_cryptos = st.sidebar.multiselect("监控品种", CRYPTO_LIST, default=CRYPTO_LIST)

st.markdown("<h2 style='text-align:center;'>📈 UT Bot 实时多空监控 (OKX数据源)</h2>", unsafe_allow_html=True)

# 交易所初始化
ex = ccxt.okx({'enableRateLimit': True})
rows = []

# --- 主循环逻辑 ---
for base in selected_cryptos:
    sym = f"{base}/USDT:USDT" if base in CONTRACTS else f"{base}/USDT"
    
    # 1. 先获取多空比数据 (函数已在上方定义，不再报错)
    ls_status = get_ok_ls_ratio(ex, base)
    
    # 2. 初始化行
    row = {"资产": base, "实时价格": "N/A", "多空比(5m)": ls_status}
    
    price_captured = False
    for tf in INTERVALS:
        try:
            # 获取行情
            bars = ex.fetch_ohlcv(sym, timeframe=tf, limit=100)
            df_raw = pd.DataFrame(bars, columns=['ts','open','high','low','close','vol'])
            df_raw['ts'] = pd.to_datetime(df_raw['ts'], unit='ms').dt.tz_localize('UTC')
            df_raw.set_index('ts', inplace=True)
            
            # 计算指标与状态
            df = calculate_indicators(df_raw, sensitivity, atr_period)
            status_html, alert_sig, curr_price, sig_time = get_status_and_signal(df)
            
            # 设置第一列实时价格
            if not price_captured:
                row["实时价格"] = f"<b style='font-size:1.1em; color:#00ffff;'>{curr_price}</b>"
                price_captured = True
            
            row[tf] = status_html
            
            # 翻转推送逻辑
            if tf in ALERT_INTERVALS and alert_sig != "NONE":
                cache_key = f"{base}_{tf}"
                event_id = f"{alert_sig}_{sig_time}"
                if state["sent_cache"].get(cache_key) != event_id:
                    send_wx_pusher(f"🚨 {base} ({tf}) 信号翻转: {alert_sig}", 
                                   f"触发价格: {curr_price}\n多空状态: {ls_status}\n信号时间: {sig_time}")
                    state["sent_cache"][cache_key] = event_id
                    state["alert_logs"].insert(0, {
                        "时间": datetime.now(BEIJING_TZ).strftime('%H:%M:%S'),
                        "资产": base, "周期": tf, "信号": alert_sig, 
                        "信号时间": sig_time, "实时价格": curr_price
                    })
        except: row[tf] = "-"
    rows.append(row)

# ==================== 5. 最终渲染 ====================
if rows:
    df_display = pd.DataFrame(rows)
    # 显式规定列的顺序：资产 -> 实时价格 -> 多空比 -> 时间周期列
    col_order = ["资产", "实时价格", "多空比(5m)"] + INTERVALS
    df_display = df_display[col_order]
    st.write(df_display.to_html(escape=False, index=False), unsafe_allow_html=True)

st.divider()
st.subheader("📜 今日推送记录 (最后一行含实时价格)")
if state["alert_logs"]:
    # 表格显示历史日志
    st.table(pd.DataFrame(state["alert_logs"]).head(20))
else:
    st.info("系统持续运行中，正在监控信号翻转...")

st.caption(f"最后更新: {datetime.now(BEIJING_TZ).strftime('%H:%M:%S')}")
