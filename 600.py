import streamlit as st
import pandas as pd
import numpy as np
import pandas_ta as ta
import ccxt
import yfinance as yf
from datetime import datetime
import pytz
from streamlit_autorefresh import st_autorefresh
import requests

# --- 1. 基础配置与北京时间 ---
st.set_page_config(page_title="UT Bot 混合资产看板 (OKX+Yahoo)", layout="wide")
BEIJING_TZ = pytz.timezone('Asia/Shanghai')

def get_now_beijing():
    return datetime.now(BEIJING_TZ)

# --- 2. 侧边栏配置 ---
st.sidebar.header("🛡️ 系统设置")
sct_key = st.sidebar.text_input("Server酱 SendKey (微信预警)", type="password", help="去 sct.ftqq.com 获取")

st.sidebar.subheader("策略参数 (推荐中间值)")
sensitivity = st.sidebar.slider("敏感度 (Multiplier)", 1.0, 5.0, 2.0, 0.1)
atr_period = st.sidebar.slider("ATR 周期", 1, 30, 10)

# --- 币圈配置 (TAO/XAG/XAU 自动走合约) ---
# 列表里写 Base Name 即可，代码会自动加后缀
CRYPTO_LIST = ["BTC", "ETH", "SOL", "SUI", "HYPE", "AAVE", "TAO", "XAG", "XAU"]
selected_cryptos = st.sidebar.multiselect("加密货币 (OKX)", CRYPTO_LIST, default=CRYPTO_LIST)

# --- 股票/金银配置 (上传 TXT) ---
st.sidebar.subheader("股票/外盘配置")
uploaded_file = st.sidebar.file_uploader("上传 TXT 列表 (每行一个雅虎代码)", type="txt")
custom_stocks = []
if uploaded_file is not None:
    content = uploaded_file.read().decode("utf-8")
    custom_stocks = [line.strip() for line in content.splitlines() if line.strip()]
    st.sidebar.success(f"已加载 {len(custom_stocks)} 个资产")

# 周期配置
selected_intervals = ["15m", "30m", "1h", "4h", "1d"]

# 每 10 分钟自动刷新
st_autorefresh(interval=10 * 60 * 1000, key="datarefresh")

# --- 3. 核心计算函数 ---
def calculate_ut_bot(df):
    if len(df) < atr_period: return df
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
            trail_stop[i] = src.iloc[i] - n_loss.iloc[i] if src.iloc[i] > p_stop else src.iloc[i] + n_loss.iloc[i]
    
    df['trail_stop'] = trail_stop
    df['buy'] = (df['Close'] > df['trail_stop']) & (df['Close'].shift(1) <= df['trail_stop'].shift(1))
    df['sell'] = (df['Close'] < df['trail_stop']) & (df['Close'].shift(1) >= df['trail_stop'].shift(1))
    return df

def get_signal_info(df, timeframe):
    if df.empty or len(df) < 2: return "数据缺失", 0, ""
    
    last_row = df.iloc[-1]
    curr_p = last_row['Close']
    buys, sells = df[df['buy']], df[df['sell']]
    
    last_buy_idx = buys.index[-1] if not buys.empty else -1
    last_sell_idx = sells.index[-1] if not sells.empty else -1
    
    tf_map = {"15m": 15, "30m": 30, "1h": 60, "4h": 240, "1d": 1440}
    mins_per_bar = tf_map.get(timeframe, 60)

    if last_buy_idx > last_sell_idx:
        bars_ago = len(df) - 1 - df.index.get_loc(last_buy_idx)
        status = f"🚀 BUY ({bars_ago * mins_per_bar}m)" if bars_ago <= 1 else "多 🟢"
        return status, curr_p, ("BUY" if bars_ago == 0 else "")
    else:
        bars_ago = len(df) - 1 - df.index.get_loc(last_sell_idx)
        status = f"📉 SELL ({bars_ago * mins_per_bar}m)" if bars_ago <= 1 else "空 🔴"
        return status, curr_p, ("SELL" if bars_ago == 0 else "")

def send_wechat(title, content):
    if sct_key:
        try: requests.post(f"https://sctapi.ftqq.com/{sct_key}.send", data={"title": title, "desp": content}, timeout=5)
        except: pass

# --- 4. 数据获取逻辑 ---
def fetch_all_data():
    exchange = ccxt.okx()
    results = []
    
    # 币种合约/现货逻辑
    CONTRACT_ONLY = ["TAO", "XAG", "XAU"]
    
    # 币圈 (OKX)
    for base in selected_cryptos:
        if base in CONTRACT_ONLY:
            sym = f"{base}/USDT:USDT"
            source_tag = "OKX合约"
        else:
            sym = f"{base}/USDT"
            source_tag = "OKX现货"
            
        row = {"资产项目": base, "来源": source_tag}
        lp = 0
        for tf in selected_intervals:
            try:
                bars = exchange.fetch_ohlcv(sym, timeframe=tf, limit=150)
                df = calculate_ut_bot(pd.DataFrame(bars, columns=['Time', 'Open', 'High', 'Low', 'Close', 'Volume']))
                status, price, alert = get_signal_info(df, tf)
                row[tf] = status
                if price > 0: lp = price
                if alert: 
                    send_wechat(f"⚠️ {base} {tf} 预警", f"方向: {alert}\n价格: {price}\n源: {source_tag}")
            except: row[tf] = "N/A"
        row["实时现价"] = f"{lp:.4f}"
        results.append(row)

    # 股票/金银 (Yahoo)
    yf_map = {"15m": "15m", "30m": "30m", "1h": "60m", "4h": "60m", "1d": "1d"}
    for sym in custom_stocks:
        row = {"资产项目": sym, "来源": "Yahoo"}
        lp = 0
        for tf in selected_intervals:
            try:
                # 抓取 Yahoo 数据
                data = yf.download(sym, period="5d" if "m" in tf else "60d", interval=yf_map[tf], progress=False)
                if data.empty: 
                    row[tf] = "休市"
                    continue
                df = data.copy()
                df.columns = df.columns.get_level_values(0) if isinstance(df.columns, pd.MultiIndex) else df.columns
                status, price, alert = get_signal_info(calculate_ut_bot(df), tf)
                row[tf] = status
                if price > 0: lp = price
            except: row[tf] = "N/A"
        row["实时现价"] = f"{lp:.2f}"
        results.append(row)
    
    return pd.DataFrame(results)

# --- 5. 渲染页面 ---
st.markdown("## 🛡️ UT Bot 全球资产看板 (混合数据源)")
c1, c2, c3 = st.columns([1.5, 1, 1])

now_bj = get_now_beijing()
c1.write(f"🕒 **北京时间**: {now_bj.strftime('%Y-%m-%d %H:%M:%S')}")

if 'data_cache' not in st.session_state or st.sidebar.button("🔄 立即同步行情"):
    with st.spinner("同步数据中..."):
        st.session_state.data_cache = fetch_all_data()

df_display = st.session_state.data_cache

if not df_display.empty:
    # 看多占比计算
    all_s = df_display[selected_intervals].values.flatten()
    bulls = sum(1 for x in all_s if "多" in str(x) or "BUY" in str(x))
    total = len([x for x in all_s if x not in ["N/A", "休市", "数据缺失"]])
    ratio = bulls / total if total > 0 else 0
    
    c2.metric("全市场看多强度", f"{ratio:.1%}")
    st.progress(ratio)

    def style_cells(val):
        if 'BUY' in str(val): return 'background-color: #00ff0022; color: #00ff00; font-weight: bold; border: 1px solid #00ff00'
        if 'SELL' in str(val): return 'background-color: #ff000022; color: #ff0000; font-weight: bold; border: 1px solid #ff0000'
        if '🟢' in str(val): return 'color: #28a745'
        if '🔴' in str(val): return 'color: #dc3545'
        if '休市' in str(val): return 'color: #777'
        return ''

    st.dataframe(
        df_display.style.applymap(style_cells, subset=selected_intervals),
        use_container_width=True,
        height=int((len(df_display)+1)*35 + 20)
    )
else:
    st.info("请在左侧上传 TXT 或点击同步按钮开始扫描")

st.sidebar.markdown(f"""
---
**TXT 上传指南：**
每行输入一个雅虎财经代码：
- `AAPL` (苹果)
- `GC=F` (黄金期货)
- `SI=F` (白银期货)
- `00700.HK` (腾讯)
""")
