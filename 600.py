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
st.set_page_config(page_title="UT Bot 全球资产多周期看板", layout="wide")
BEIJING_TZ = pytz.timezone('Asia/Shanghai')

def get_now_beijing():
    return datetime.now(BEIJING_TZ)

# --- 2. 侧边栏配置 ---
st.sidebar.header("🛡️ 系统设置")
# 微信预警配置 (使用 Server酱: sct.ftqq.com)
sct_key = st.sidebar.text_input("Server酱 SendKey (微信预警)", type="password", help="去 sct.ftqq.com 获取")

# 参数取中间值 (Multiplier=2.0, ATR=10)
st.sidebar.subheader("策略参数 (推荐中间值)")
sensitivity = st.sidebar.slider("敏感度 (Multiplier)", 1.0, 5.0, 2.0, 0.1)
atr_period = st.sidebar.slider("ATR 周期", 1, 30, 10)

# 资产配置
CRYPTO_SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "SUI/USDT", "HYPE/USDT", "AAVE/USDT"]
GLOBAL_SYMBOLS = ["GC=F", "SI=F", "CL=F", "AAPL", "TSLA", "NVDA"] # 金、银、原油、美股

selected_cryptos = st.sidebar.multiselect("加密货币 (OKX)", CRYPTO_SYMBOLS, default=CRYPTO_SYMBOLS)
selected_global = st.sidebar.multiselect("股票/金银 (Yahoo)", GLOBAL_SYMBOLS, default=GLOBAL_SYMBOLS)

# 周期配置 (增加 15m)
selected_intervals = ["15m", "30m", "1h", "4h", "1d"]

# 每 10 分钟自动刷新
REFRESH_MINUTES = 10
st_autorefresh(interval=REFRESH_MINUTES * 60 * 1000, key="datarefresh")

# --- 3. 核心计算逻辑 ---

def send_wechat(title, content):
    if sct_key:
        url = f"https://sctapi.ftqq.com/{sct_key}.send"
        data = {"title": title, "desp": content}
        try: requests.post(url, data=data, timeout=5)
        except: pass

def calculate_ut_bot(df):
    # UT Bot 核心算法
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
    
    # 查找最近一个信号的位置
    buys = df[df['buy'] == True]
    sells = df[df['sell'] == True]
    
    last_buy_idx = buys.index[-1] if not buys.empty else -1
    last_sell_idx = sells.index[-1] if not sells.empty else -1
    
    # 时间映射
    tf_map = {"15m": 15, "30m": 30, "1h": 60, "4h": 240, "1d": 1440}
    mins_per_bar = tf_map.get(timeframe, 60)

    if last_buy_idx > last_sell_idx:
        # 计算距离现在过去了多少根 K 线
        bars_ago = len(df) - 1 - df.index.get_loc(last_buy_idx)
        duration = bars_ago * mins_per_bar
        status = f"🚀 BUY ({duration}m)" if bars_ago <= 1 else "多 🟢"
        return status, curr_p, ("BUY" if bars_ago == 0 else "")
    else:
        bars_ago = len(df) - 1 - df.index.get_loc(last_sell_idx)
        duration = bars_ago * mins_per_bar
        status = f"📉 SELL ({duration}m)" if bars_ago <= 1 else "空 🔴"
        return status, curr_p, ("SELL" if bars_ago == 0 else "")

# --- 4. 异步模拟抓取 (OKX + Yahoo) ---

def fetch_all_data():
    exchange = ccxt.okx()
    results = []
    
    # 币种处理 (OKX)
    for sym in selected_cryptos:
        row = {"资产项目": sym, "来源": "OKX"}
        latest_price = 0
        for tf in selected_intervals:
            try:
                bars = exchange.fetch_ohlcv(sym, timeframe=tf, limit=150)
                df = pd.DataFrame(bars, columns=['Time', 'Open', 'High', 'Low', 'Close', 'Volume'])
                df = calculate_ut_bot(df)
                status, price, alert = get_signal_info(df, tf)
                row[tf] = status
                if price > 0: latest_price = price
                # 微信预警触发
                if alert: 
                    send_wechat(f"⚠️ {sym} {tf} 预警", f"信号: {alert}\n价格: {price}\n时间: {get_now_beijing().strftime('%H:%M')}")
            except: row[tf] = "N/A"
        row["实时现价"] = f"{latest_price:.4f}"
        results.append(row)

    # 股票/金银处理 (Yahoo)
    for sym in selected_global:
        row = {"资产项目": sym, "来源": "Yahoo"}
        latest_price = 0
        # 映射雅虎的 interval 代码
        yf_map = {"15m": "15m", "30m": "30m", "1h": "60m", "4h": "60m", "1d": "1d"}
        for tf in selected_intervals:
            try:
                # 4h 周期雅虎不原生支持，通常用 1h 模拟或直接跳过，此处尝试获取
                data = yf.download(sym, period="60d" if "d" in tf else "7d", interval=yf_map[tf], progress=False)
                if data.empty: 
                    row[tf] = "休市"
                    continue
                df = data.copy()
                df.columns = df.columns.get_level_values(0) if isinstance(df.columns, pd.MultiIndex) else df.columns
                df = calculate_ut_bot(df)
                status, price, alert = get_signal_info(df, tf)
                row[tf] = status
                if price > 0: latest_price = price
            except: row[tf] = "N/A"
        row["实时现价"] = f"{latest_price:.2f}"
        results.append(row)
    
    return pd.DataFrame(results)

# --- 5. UI 渲染 ---

st.markdown(f"## 🛡️ UT Bot 全球多资产看板")

# 顶部状态栏
c1, c2, c3 = st.columns([1.5, 1, 1])
now_bj = get_now_beijing()
c1.metric("北京时间", now_bj.strftime('%H:%M:%S'), now_bj.strftime('%Y-%m-%d'))

# 数据刷新逻辑
if 'data_cache' not in st.session_state or st.sidebar.button("🔄 手动同步最新行情"):
    with st.spinner("同步 OKX & Yahoo 数据中..."):
        st.session_state.data_cache = fetch_all_data()

df_display = st.session_state.data_cache

if not df_display.empty:
    # 计算全市场看多占比
    all_status = df_display[selected_intervals].values.flatten()
    bulls = sum(1 for x in all_status if "多" in str(x) or "BUY" in str(x))
    total = len([x for x in all_status if x != "N/A" and x != "休市"])
    ratio = bulls / total if total > 0 else 0
    
    c2.metric("多头强度 (全市场)", f"{ratio:.1%}")
    c3.write(f"刷新倒计时: 每 {REFRESH_MINUTES} 分钟")
    st.progress(ratio)

    # 表格样式处理
    def style_cells(val):
        if 'BUY' in str(val): return 'background-color: #00ff0022; color: #00ff00; font-weight: bold; border: 1px solid #00ff00'
        if 'SELL' in str(val): return 'background-color: #ff000022; color: #ff0000; font-weight: bold; border: 1px solid #ff0000'
        if '🟢' in str(val): return 'color: #28a745'
        if '🔴' in str(val): return 'color: #dc3545'
        return 'color: #666' if val == "休市" else ''

    # 显示主表格
    st.dataframe(
        df_display.style.applymap(style_cells, subset=selected_intervals),
        use_container_width=True,
        height=int((len(df_display)+1)*35 + 10)
    )
else:
    st.warning("暂无数据，请检查网络或 API 配置")

st.sidebar.info(f"系统运行正常\n\n刷新频率：{REFRESH_MINUTES}min\n时区：Asia/Shanghai\n\n注：15m 信号在币圈极为敏感，建议配合大周期参考。")
