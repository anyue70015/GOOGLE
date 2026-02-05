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
st.set_page_config(page_title="UT Bot + RSI/EMA 加密看板", layout="wide")
BEIJING_TZ = pytz.timezone('Asia/Shanghai')
st_autorefresh(interval=60 * 1000, key="refresh_1min")  # 1分钟刷新

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

# UT Bot + RSI/EMA 计算
def calculate_indicators(df):
    if df.empty or len(df) < 50:
        return pd.DataFrame()
    df.columns = [str(c).capitalize() for c in df.columns]
    
    # UT Bot
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
    
    # RSI & EMA
    df['rsi'] = ta.rsi(df['Close'], length=14)
    df['ema20'] = ta.ema(df['Close'], length=20)
    df['ema50'] = ta.ema(df['Close'], length=50)
    
    return df

# 获取信号 + EMA状态 + 报警准备
def get_sig(df, tf):
    if df.empty:
        return "N/A", None, None, "N/A", "N/A"
    curr_p = float(df.iloc[-1]['Close'])
    rsi_val = f"{df.iloc[-1]['rsi']:.1f}" if pd.notna(df.iloc[-1]['rsi']) else "N/A"
    
    # EMA 排列状态
    ema_status = "N/A"
    if pd.notna(df.iloc[-1]['ema20']) and pd.notna(df.iloc[-1]['ema50']):
        if curr_p > df.iloc[-1]['ema20'] > df.iloc[-1]['ema50']:
            ema_status = "多头排列 🟢"
        elif curr_p < df.iloc[-1]['ema20'] < df.iloc[-1]['ema50']:
            ema_status = "空头排列 🔴"
        else:
            ema_status = "震荡 ⚪"
    
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
        if dur_b <= alert_min:
            alert_d = dur_b
    elif ls_u and (not lb_u or ls_u > lb_u):
        sig = f"📉 SELL({dur_s}m)" if dur_s <= 30 else "空 🔴"
        if dur_s <= alert_min:
            alert_d = dur_s
    
    return sig, curr_p, alert_d, rsi_val, ema_status

# 多空比（多交易所聚合，简化用 Binance 主 + 模拟补充）
def get_ls_multi(base):
    ratios = []
    try:
        # Binance
        url_b = f"https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol={base.upper()}USDT&period=5m&limit=1"
        r_b = requests.get(url_b, timeout=3).json()
        if r_b and 'longShortRatio' in r_b[0]:
            ratio_b = float(r_b[0]['longShortRatio'])
            ratios.append(f"Bin:{ratio_b:.2f}{'🟢' if ratio_b>1.2 else '🔴' if ratio_b<0.8 else ''}")
    except:
        pass
    
    # Gate/OKX 补充（实际用 CoinGlass 聚合页抓取或 Bybit API，这里模拟/占位）
    # 如果有 API key，可换成真实请求；当前用 N/A 占位或固定补充
    ratios.append("Gate:N/A")  # Gate 无免费公开 endpoint，可用 Coinglass
    ratios.append("OKX:N/A")   # 同上
    
    return " | ".join(ratios) if ratios else "N/A"

# 发送微信（仅1h触发）
def send_alert(key, title, body):
    if not key: return
    try:
        if key.startswith("http"):
            requests.post(key, json={"msgtype": "text", "text": {"content": f"{title}\n{body}"}}, timeout=5)
        else:
            requests.post(f"https://sctapi.ftqq.com/{key}.send", data={"title": title, "desp": body}, timeout=5)
    except:
        pass

# HTML 表格渲染
def render_table(df):
    def cell_style(col_name, value):
        s = str(value) if pd.notna(value) else ""
        if 'BUY' in s or '🟢' in s:
            return 'color:#0f0; font-weight:bold; background:#00440033;'
        if 'SELL' in s or '🔴' in s:
            return 'color:#f44; font-weight:bold; background:#44000033;'
        if '多空比' in col_name:
            if '🟢' in s: return 'color:#0f8; font-weight:bold;'
            if '🔴' in s: return 'color:#f66; font-weight:bold;'
        if 'RSI' in col_name:
            v = float(s) if s != "N/A" else 50
            if v > 70: return 'color:#ff0; background:#44000033;'  # 超买
            if v < 30: return 'color:#0ff; background:#00440033;'  # 超卖
        return ''
    
    html = '<table style="width:100%; border-collapse:collapse; font-family:monospace; font-size:0.95em;">'
    html += '<tr style="background:#222; color:#fff;">' + ''.join(f'<th style="padding:8px; border:1px solid #444;">{c}</th>' for c in df.columns) + '</tr>'
    
    for _, row in df.iterrows():
        cells = ''.join(
            f'<td style="padding:8px; border:1px solid #444; {cell_style(c, row[c])}">{row[c]}</td>'
            for c in df.columns
        )
        html += f'<tr>{cells}</tr>'
    html += '</table>'
    st.markdown(html, unsafe_allow_html=True)

# 主界面
st.title("UT Bot + RSI/EMA 多空比看板（1分钟刷新）")

components.html("""
<div style="font-size:1.3em; color:#aaa; margin:1em 0; text-align:center;">
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
        row = {"资产": base, "多空比(聚合)": get_ls_multi(base)}
        price = None
        
        for tf in intervals:
            try:
                bars = ex.fetch_ohlcv(sym, timeframe=tf, limit=200)  # 多取点给 EMA50
                if not bars:
                    row[tf] = "无"
                    continue
                df_ohlcv = pd.DataFrame(bars, columns=['timestamp','open','high','low','close','volume'])
                df_ohlcv['timestamp'] = pd.to_datetime(df_ohlcv['timestamp'], unit='ms')
                df_ohlcv.set_index('timestamp', inplace=True)
                processed_df = calculate_indicators(df_ohlcv)
                sig, p, dur, rsi, ema_st = get_sig(processed_df, tf)
                row[tf] = f"{sig} | RSI:{rsi} | {ema_st}"
                if p is not None and p > 0:
                    price = p
                
                # 仅 1h 级别报警
                if tf == "1h" and dur is not None and weixin_key:
                    title = f"[{base} 1H] 新信号"
                    body = f"信号: {sig}\n价格: {p:.4f}\nRSI: {rsi}\nEMA: {ema_st}\n距今: {dur}分钟前\n多空比: {row['多空比(聚合)']}"
                    send_alert(weixin_key, title, body)
            except:
                row[tf] = "err"
        
        row["现价"] = f"{price:.4f}" if price is not None else "N/A"
        rows.append(row)
    
    result_df = pd.DataFrame(rows)
    render_table(result_df)

st.caption(f"更新: {datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')}")
st.info("· 1分钟刷新 · 仅1h BUY/SELL 信号报警 · 多空比聚合（Bin主+Gate/OKX补充） · RSI超买>70黄 超卖<30青")
