import streamlit as st
import pandas as pd
import numpy as np
import pandas_ta as ta
import ccxt
import requests
from datetime import datetime
import pytz
import time
from streamlit_autorefresh import st_autorefresh
import streamlit.components.v1 as components

# --- 配置 ---
st.set_page_config(page_title="UT Bot 币安数据版（加密专用）", layout="wide")

BEIJING_TZ = pytz.timezone('Asia/Shanghai')

# 自动刷新：60秒（1分钟）
st_autorefresh(interval=60 * 1000, key="data_refresh")

# --- 侧边栏 ---
st.sidebar.header("🛡️ 系统设置")
sensitivity = st.sidebar.slider("敏感度 (Key Value)", 0.1, 5.0, 1.0, 0.1)
atr_period = st.sidebar.slider("ATR 周期", 1, 30, 10)

CRYPTO_LIST = ["BTC", "ETH", "SOL", "SUI", "RENDER", "DOGE", "XRP", "HYPE", "AAVE", "TAO", "XAG", "XAU"]
selected_cryptos = st.sidebar.multiselect("加密货币清单", CRYPTO_LIST, default=CRYPTO_LIST)

# 微信报警配置（推荐用 Server酱 或 企业微信 webhook）
st.sidebar.header("🚨 微信报警设置")
weixin_key = st.sidebar.text_input("Server酱 SendKey 或 企业微信 webhook key", type="password", value="")
alert_min_duration = st.sidebar.number_input("新信号多少分钟内报警 (默认10)", 1, 60, 10)

selected_intervals = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]  # 新增 1m 和 5m

# --- 核心算法 ---
def calculate_ut_bot(df):
    if df.empty or len(df) < 20: return pd.DataFrame()
    df.columns = [str(c).capitalize() for c in df.columns]
    
    df['atr'] = ta.atr(df['High'], df['Low'], df['Close'], length=atr_period)
    df = df.dropna(subset=['atr']).copy()
    n_loss = sensitivity * df['atr']
    src = df['Close']
    trail_stop = np.zeros(len(df))
    for i in range(1, len(df)):
        p_stop = trail_stop[i-1]
        if src.iloc[i] > p_stop and src.iloc[i-1] > p_stop:
            trail_stop[i] = max(p_stop, src.iloc[i] - n_loss.iloc[i])
        elif src.iloc[i] < p_stop and src.iloc[i-1] < p_stop:
            trail_stop[i] = min(p_stop, src.iloc[i] + n_loss.iloc[i])
        else:
            trail_stop[i] = (src.iloc[i] - n_loss.iloc[i]) if src.iloc[i] > p_stop else (src.iloc[i] + n_loss.iloc[i])
    df['trail_stop'] = trail_stop
    df['buy'] = (df['Close'] > df['trail_stop']) & (df['Close'].shift(1) <= df['trail_stop'].shift(1))
    df['sell'] = (df['Close'] < df['trail_stop']) & (df['Close'].shift(1) >= df['trail_stop'].shift(1))
    return df

def get_sig(df):
    if df.empty: return "N/A", None, None
    curr_p = float(df.iloc[-1]['Close'])
    buys = df[df['buy']]
    sells = df[df['sell']]
    last_buy_idx = buys.index[-1] if not buys.empty else None
    last_sell_idx = sells.index[-1] if not sells.empty else None
    
    now = datetime.now(pytz.utc)
    def ensure_utc(ts):
        if ts is None: return None
        if ts.tzinfo is None: return pytz.utc.localize(ts)
        return ts.astimezone(pytz.utc)

    lb_u = ensure_utc(last_buy_idx)
    ls_u = ensure_utc(last_sell_idx)
    now_u = ensure_utc(now)
    
    dur_buy = int((now_u - lb_u).total_seconds() / 60) if lb_u else 9999
    dur_sell = int((now_u - ls_u).total_seconds() / 60) if ls_u else 9999
    
    if lb_u and (not ls_u or lb_u > ls_u):
        sig = f"🚀 BUY({dur_buy}m)" if dur_buy <= 30 else "多 🟢"
        return sig, curr_p, dur_buy if dur_buy <= alert_min_duration else None
    elif ls_u and (not lb_u or ls_u > lb_u):
        sig = f"📉 SELL({dur_sell}m)" if dur_sell <= 30 else "空 🔴"
        return sig, curr_p, dur_sell if dur_sell <= alert_min_duration else None
    return "维持", curr_p, None

def get_binance_ls(ccy):
    try:
        url = f"https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol={ccy.upper()}USDT&period=5m&limit=1"
        res = requests.get(url, timeout=3).json()
        if res and isinstance(res, list) and 'longShortRatio' in res[0]:
            ratio = float(res[0]['longShortRatio'])
            color = "🟢" if ratio > 1.2 else "🔴" if ratio < 0.8 else "⚪"
            return f"{ratio:.2f} {color}"
    except:
        pass
    return "N/A"

def send_weixin_alert(key, title, content):
    if not key:
        return False
    try:
        # Server酱格式（最常用）
        url = f"https://sctapi.ftqq.com/{key}.send"
        data = {"title": title, "desp": content}
        requests.post(url, data=data, timeout=5)
        return True
    except:
        # 企业微信 webhook 备用（如果 key 是完整 url）
        if key.startswith("https://"):
            try:
                requests.post(key, json={"msgtype": "text", "text": {"content": f"{title}\n{content}"}}, timeout=5)
                return True
            except:
                pass
    return False

# --- 主程序 ---
st.title("🛡️ UT Bot 加密货币看板（1分钟自动刷新）")

# 倒计时显示
countdown_placeholder = st.empty()

# JavaScript 倒计时（简单实现）
components.html(
    """
    <div id="countdown" style="font-size:1.2em; color:#aaa; margin-bottom:1em;">
        下次刷新倒计时: <span id="timer">60</span> 秒
    </div>
    <script>
    let seconds = 60;
    const timer = document.getElementById('timer');
    const interval = setInterval(() => {
        seconds--;
        timer.textContent = seconds;
        if (seconds <= 0) {
            seconds = 60;
        }
    }, 1000);
    </script>
    """,
    height=80
)

if st.button("🔄 立即同步数据"):
    pass  # 按钮只是手动触发，实际靠 autorefresh

with st.spinner("正在加载最新数据..."):
    ex = ccxt.okx({'enableRateLimit': True})
    c_res = []
    CONTRACTS = ["TAO", "XAG", "XAU"]  # 这些用永续合约
    
    for base in selected_cryptos:
        sym = f"{base}/USDT:USDT" if base in CONTRACTS else f"{base}/USDT"
        row = {"资产": base, "币安多空比 (5m)": get_binance_ls(base)}
        lp = None
        
        for tf in selected_intervals:
            try:
                bars = ex.fetch_ohlcv(sym, tf, limit=150)
                if not bars:
                    row[tf] = "无数据"
                    continue
                data = pd.DataFrame(bars, columns=['Time','Open','High','Low','Close','Volume'])
                data['Time'] = pd.to_datetime(data['Time'], unit='ms')
                data.set_index('Time', inplace=True)
                sig, price, alert_dur = get_sig(calculate_ut_bot(data))
                row[tf] = sig
                if price is not None and price > 0:
                    lp = price  # 用最后一个成功的 price
                # 微信报警
                if alert_dur is not None and weixin_key:
                    title = f"UT Bot 信号 - {base} {tf}"
                    content = f"信号: {sig}\n价格: {price:.4f}\n距信号: {alert_dur}分钟前\n多空比: {row['币安多空比 (5m)']}"
                    send_weixin_alert(weixin_key, title, content)
            except Exception as e:
                row[tf] = "错误"
        
        row["现价"] = f"{lp:.4f}" if lp is not None else "N/A"
        c_res.append(row)
    
    df = pd.DataFrame(c_res)
    
    # 样式函数（增强多空比颜色）
    def style_cell(v):
        s = str(v)
        if 'BUY' in s or '🟢' in s: return 'color:#00ff00; font-weight:bold; background:#00440044'
        if 'SELL' in s or '🔴' in s: return 'color:#ff4444; font-weight:bold; background:#44000044'
        if '多空比' in v.name and '🟢' in s: return 'color:#00ff88'
        if '多空比' in v.name and '🔴' in s: return 'color:#ff6666'
        return ''
    
    # 显示表格
    st.dataframe(
        df.style.map(style_cell),
        use_container_width=True,
        column_config={col: col for col in df.columns}
    )

st.caption(f"最后更新: {datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')}")
st.info("1分钟自动刷新 · 新 BUY/SELL 信号（10分钟内）会推送微信（需配置 key）")
