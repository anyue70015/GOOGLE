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

# 配置
st.set_page_config(page_title="UT Bot 加密看板", layout="wide")
BEIJING_TZ = pytz.timezone('Asia/Shanghai')
st_autorefresh(interval=60 * 1000, key="refresh_1min")

# 侧边栏
st.sidebar.header("🛡️ 设置")
sensitivity = st.sidebar.slider("敏感度", 0.1, 5.0, 1.0, 0.1)
atr_period = st.sidebar.slider("ATR 周期", 1, 30, 10)

CRYPTO_LIST = ["BTC", "ETH", "SOL", "SUI", "RENDER", "DOGE", "XRP", "HYPE", "AAVE", "TAO", "XAG", "XAU"]
selected_cryptos = st.sidebar.multiselect("币种", CRYPTO_LIST, default=CRYPTO_LIST)

st.sidebar.header("🚨 微信报警")
weixin_key = st.sidebar.text_input("Server酱 SendKey 或 企业微信 webhook URL", type="password")
alert_min = st.sidebar.number_input("新信号报警阈值（分钟）", 1, 60, 10)

intervals = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]

# UT Bot 计算
def calculate_ut_bot(df):
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
    return df

# 信号判断 + 报警准备
def get_sig(df):
    if df.empty: return "N/A", None, None
    curr_p = float(df.iloc[-1]['Close'])
    buys = df[df['buy']]
    sells = df[df['sell']]
    lb = buys.index[-1] if not buys.empty else None
    ls = sells.index[-1] if not sells.empty else None
    
    now = datetime.now(pytz.utc)
    def to_utc(ts):
        if ts is None: return None
        return ts if ts.tzinfo else pytz.utc.localize(ts)
    
    lb_u, ls_u, now_u = to_utc(lb), to_utc(ls), to_utc(now)
    dur_b = int((now_u - lb_u).total_seconds() / 60) if lb_u else 999
    dur_s = int((now_u - ls_u).total_seconds() / 60) if ls_u else 999
    
    if lb_u and (not ls_u or lb_u > ls_u):
        sig = f"🚀 BUY({dur_b}m)" if dur_b <= 30 else "多 🟢"
        alert_d = dur_b if dur_b <= alert_min else None
    elif ls_u and (not lb_u or ls_u > lb_u):
        sig = f"📉 SELL({dur_s}m)" if dur_s <= 30 else "空 🔴"
        alert_d = dur_s if dur_s <= alert_min else None
    else:
        sig, alert_d = "维持", None
    return sig, curr_p, alert_d

# 币安多空比
def get_ls(ccy):
    try:
        url = f"https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol={ccy.upper()}USDT&period=5m&limit=1"
        r = requests.get(url, timeout=3).json()
        if r and isinstance(r, list) and 'longShortRatio' in r[0]:
            ratio = float(r[0]['longShortRatio'])
            emoji = "🟢" if ratio > 1.2 else "🔴" if ratio < 0.8 else "⚪"
            return f"{ratio:.2f} {emoji}"
    except:
        pass
    return "N/A"

# 发送微信
def send_alert(key, title, body):
    if not key: return
    try:
        if key.startswith("http"):  # 企业微信 webhook
            requests.post(key, json={"msgtype": "text", "text": {"content": f"{title}\n{body}"}}, timeout=5)
        else:  # Server酱
            requests.post(f"https://sctapi.ftqq.com/{key}.send", data={"title": title, "desp": body}, timeout=5)
    except:
        pass

# HTML 表格渲染（方案2核心）
def render_table(df):
    def cell_style(v):
        s = str(v)
        if 'BUY' in s or '🟢' in s: return 'color:#0f0; font-weight:bold; background:#00440033;'
        if 'SELL' in s or '🔴' in s: return 'color:#f44; font-weight:bold; background:#44000033;'
        if '多空比' in v.name and '🟢' in s: return 'color:#0f8;'
        if '多空比' in v.name and '🔴' in s: return 'color:#f66;'
        return ''
    
    html = '<table style="width:100%; border-collapse:collapse; font-family:monospace;">'
    html += '<tr style="background:#222; color:#fff;">' + ''.join(f'<th style="padding:8px; border:1px solid #444;">{c}</th>' for c in df.columns) + '</tr>'
    
    for _, row in df.iterrows():
        cells = ''.join(f'<td style="padding:8px; border:1px solid #444; {cell_style(row[c])}">{row[c]}</td>' for c in df.columns)
        html += f'<tr>{cells}</tr>'
    html += '</table>'
    st.markdown(html, unsafe_allow_html=True)

# 主界面
st.title("UT Bot 加密货币信号看板（1分钟刷新）")

# 倒计时
components.html("""
<div style="font-size:1.3em; color:#aaa; margin:1em 0;">
  下次刷新倒计时: <span id="cd">60</span> 秒
</div>
<script>
let s=60; const t=document.getElementById('cd');
setInterval(()=>{s--; t.textContent=s; if(s<=0)s=60;},1000);
</script>
""", height=80)

with st.spinner("加载数据..."):
    ex = ccxt.okx({'enableRateLimit': True, 'timeout': 10000})
    rows = []
    contracts = {"TAO", "XAG", "XAU"}
    
    for base in selected_cryptos:
        sym = f"{base}/USDT:USDT" if base in contracts else f"{base}/USDT"
        row = {"资产": base, "多空比(5m)": get_ls(base)}
        price = None
        
        for tf in intervals:
            try:
                bars = ex.fetch_ohlcv(sym, timeframe=tf, limit=150)
                if not bars: 
                    row[tf] = "无"
                    continue
                df_ohlcv = pd.DataFrame(bars, columns=['timestamp','open','high','low','close','volume'])
                df_ohlcv['timestamp'] = pd.to_datetime(df_ohlcv['timestamp'], unit='ms')
                df_ohlcv.set_index('timestamp', inplace=True)
                sig, p, dur = get_sig(calculate_ut_bot(df_ohlcv))
                row[tf] = sig
                if p is not None and p > 0:
                    price = p
                if dur is not None and weixin_key:
                    title = f"[{base} {tf}] 新信号"
                    body = f"{sig}\n价格: {p:.4f}\n距今: {dur}分钟前\n多空比: {row['多空比(5m)']}"
                    send_alert(weixin_key, title, body)
            except:
                row[tf] = "err"
        
        row["现价"] = f"{price:.4f}" if price else "N/A"
        rows.append(row)
    
    result_df = pd.DataFrame(rows)
    render_table(result_df)

st.caption(f"更新时间: {datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')}")
