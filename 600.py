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
st.set_page_config(page_title="UT Bot + RSI/EMA 看板", layout="wide")
BEIJING_TZ = pytz.timezone('Asia/Shanghai')
st_autorefresh(interval=600 * 1000, key="refresh_10min")  # 10分钟自动刷新

# 侧边栏
st.sidebar.header("🛡️ 设置")
sensitivity = st.sidebar.slider("UT Bot 敏感度", 0.1, 5.0, 1.0, 0.1)
atr_period = st.sidebar.slider("ATR 周期", 1, 30, 10)

CRYPTO_LIST = ["BTC", "ETH", "SOL", "SUI", "RENDER", "DOGE", "XRP", "HYPE", "AAVE", "TAO", "XAG", "XAU"]
selected_cryptos = st.sidebar.multiselect("币种", CRYPTO_LIST, default=CRYPTO_LIST)

st.sidebar.header("🚨 微信报警（仅1h级别）")
weixin_key = st.sidebar.text_input("Server酱 SendKey 或 企业微信 webhook URL", type="password")
alert_min = st.sidebar.number_input("新信号报警阈值（分钟）", 1, 60, 10)

intervals = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]

# 计算指标
def calculate_indicators(df):
    if df.empty or len(df) < 50:
        return pd.DataFrame()
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
    df['ema5'] = ta.ema(df['Close'], length=5)
    df['ema13'] = ta.ema(df['Close'], length=13)
    df['ema20'] = ta.ema(df['Close'], length=20)
    df['ema50'] = ta.ema(df['Close'], length=50)
    
    df['ema_cross'] = np.where(
        (df['ema5'] > df['ema13']) & (df['ema5'].shift(1) <= df['ema13'].shift(1)), "金叉 🟢",
        np.where(
            (df['ema5'] < df['ema13']) & (df['ema5'].shift(1) >= df['ema13'].shift(1)), "死叉 🔴",
            "无交叉"
        )
    )
    
    return df

# 获取信号 + 指标（分离趋势状态）
def get_sig(df, tf):
    if df.empty:
        return "N/A", None, None, "N/A", "N/A", "N/A", "N/A"
    
    curr_p = float(df.iloc[-1]['Close'])
    rsi_val = f"{df.iloc[-1]['rsi']:.1f}" if pd.notna(df.iloc[-1]['rsi']) else "N/A"
    
    # EMA20/50 整体趋势
    trend = "N/A"
    if pd.notna(df.iloc[-1]['ema20']) and pd.notna(df.iloc[-1]['ema50']):
        if curr_p > df.iloc[-1]['ema20'] > df.iloc[-1]['ema50']:
            trend = "多头 🟢"
        elif curr_p < df.iloc[-1]['ema20'] < df.iloc[-1]['ema50']:
            trend = "空头 🔴"
        else:
            trend = "震荡 ⚪"
    
    ema_cross = df.iloc[-1]['ema_cross'] if pd.notna(df.iloc[-1]['ema_cross']) else "N/A"
    
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
    
    sig = "维持"
    alert_d = None
    if lb_u and (not ls_u or lb_u > ls_u):
        sig = f"🚀 BUY({dur_b}m)" if dur_b <= 30 else "多 🟢"
        if dur_b <= alert_min: alert_d = dur_b
    elif ls_u and (not lb_u or ls_u > lb_u):
        sig = f"📉 SELL({dur_s}m)" if dur_s <= 30 else "空 🔴"
        if dur_s <= alert_min: alert_d = dur_s
    
    return sig, curr_p, alert_d, rsi_val, ema_cross, trend

# 多空比
def get_ls(base):
    try:
        url = f"https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol={base.upper()}USDT&period=5m&limit=1"
        r = requests.get(url, timeout=5).json()
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
        if key.startswith("http"):
            requests.post(key, json={"msgtype": "text", "text": {"content": f"{title}\n{body}"}}, timeout=5)
        else:
            requests.post(f"https://sctapi.ftqq.com/{key}.send", data={"title": title, "desp": body}, timeout=5)
    except:
        pass

# HTML 表格 - 新布局：趋势单独一列，其他三项三行细线分隔
def render_table(df):
    def cell_style_trend(value):
        s = str(value)
        if '多头' in s or '🟢' in s: return 'color:#0f0; font-weight:bold; background:#00440033; text-align:center;'
        if '空头' in s or '🔴' in s: return 'color:#f44; font-weight:bold; background:#44000033; text-align:center;'
        return 'text-align:center;'

    def cell_style_other(value):
        s = str(value)
        if 'BUY' in s or '金叉' in s or '🟢' in s: return 'color:#0f0; font-weight:bold;'
        if 'SELL' in s or '死叉' in s or '🔴' in s: return 'color:#f44; font-weight:bold;'
        if 'RSI' in s:
            try:
                v = float(s.split(':')[1])
                if v > 70: return 'color:#ff0;'
                if v < 30: return 'color:#0ff;'
            except:
                pass
        return ''

    html = '<table style="width:100%; border-collapse:collapse; font-family:monospace; font-size:0.95em;">'
    html += '<tr style="background:#222; color:#fff;">'
    for c in df.columns:
        html += f'<th style="padding:8px; border:1px solid #444;">{c}</th>'
    html += '</tr>'
    
    for _, row in df.iterrows():
        html += '<tr>'
        for c in df.columns:
            val = row[c]
            if c in intervals:  # 时间框架列用新布局
                # 假设格式已改为 "信号 | RSI:xx | EMA:xx" 但我们重新组织
                parts = str(val).split(' | ')
                sig_part = parts[0] if len(parts) > 0 else ""
                rsi_part = parts[1] if len(parts) > 1 else ""
                ema_part = ' | '.join(parts[2:]) if len(parts) > 2 else ""
                
                content = f'''
                <div style="border:1px solid #555; padding:4px; min-height:80px; display:flex; flex-direction:column; justify-content:space-between;">
                    <div style="border-bottom:1px solid #444; padding-bottom:4px; {cell_style_other(sig_part)}">{sig_part or "—"}</div>
                    <div style="border-bottom:1px solid #444; padding:4px 0; {cell_style_other(rsi_part)}">{rsi_part or "—"}</div>
                    <div style="padding-top:4px; {cell_style_other(ema_part)}">{ema_part or "—"}</div>
                </div>
                '''
                html += f'<td style="padding:4px; border:1px solid #444; vertical-align:top;">{content}</td>'
            elif c == "多空比(5m)":
                style = cell_style_trend(val)
                html += f'<td style="padding:8px; border:1px solid #444; {style}">{val}</td>'
            elif c == "趋势":
                style = cell_style_trend(val)
                html += f'<td style="padding:8px; border:1px solid #444; {style}">{val}</td>'
            else:
                html += f'<td style="padding:8px; border:1px solid #444;">{val}</td>'
        html += '</tr>'
    html += '</table>'
    st.markdown(html, unsafe_allow_html=True)

# 主界面
st.title("UT Bot + RSI/EMA/金叉看板（10分钟自动刷新）")

if st.button("🔄 立即刷新数据"):
    st.rerun()

components.html("""
<div style="font-size:1.3em; color:#aaa; margin:1em 0; text-align:center;">
  下次自动刷新倒计时: <span id="cd">600</span> 秒
</div>
<script>
let s=600; const t=document.getElementById('cd');
setInterval(()=>{s--; t.textContent=s; if(s<=0)s=600;},1000);
</script>
""", height=80)

with st.spinner("加载最新数据..."):
    ex = ccxt.okx({'enableRateLimit': True, 'timeout': 10000})
    rows = []
    contracts = {"TAO", "XAG", "XAU"}
    
    for base in selected_cryptos:
        sym = f"{base}/USDT:USDT" if base in contracts else f"{base}/USDT"
        row = {"资产": base, "多空比(5m)": get_ls(base)}
        price = None
        
        for tf in intervals:
            try:
                bars = ex.fetch_ohlcv(sym, timeframe=tf, limit=200)
                if not bars:
                    row[tf] = "无"
                    continue
                df_ohlcv = pd.DataFrame(bars, columns=['timestamp','open','high','low','close','volume'])
                df_ohlcv['timestamp'] = pd.to_datetime(df_ohlcv['timestamp'], unit='ms')
                df_ohlcv.set_index('timestamp', inplace=True)
                processed_df = calculate_indicators(df_ohlcv)
                sig, p, dur, rsi, ema_cross, trend = get_sig(processed_df, tf)
                row[tf] = f"{sig} | {rsi} | EMA:{ema_cross}"
                if p is not None and p > 0:
                    price = p
                
                if tf == "1h" and dur is not None and weixin_key:
                    title = f"[{base} 1H] 新信号"
                    body = f"信号: {sig}\n价格: {p:.4f}\nRSI: {rsi}\nEMA金叉/死叉: {ema_cross}\n趋势: {trend}\n距今: {dur}分钟前\n多空比: {row['多空比(5m)']}"
                    send_alert(weixin_key, title, body)
            except:
                row[tf] = "err"
        
        row["现价"] = f"{price:.4f}" if price is not None else "N/A"
        row["趋势"] = trend  # 新增独立趋势列（可选，如果你想分离）
        rows.append(row)
    
    result_df = pd.DataFrame(rows)
    render_table(result_df)

st.caption(f"最后更新: {datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')}")
st.info("· 趋势状态独立列 · 时间框架内三行细线分隔（信号/RSI/EMA）· 手动刷新按钮 · 10分钟自动")
