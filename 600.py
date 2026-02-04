import streamlit as st
import pandas as pd
import numpy as np
import pandas_ta as ta
import ccxt
from datetime import datetime

# --- 页面配置 ---
st.set_page_config(page_title="OKX UT Bot 实时监控", layout="wide")

st.title("⚡ OKX 实时 UT Bot 多周期监控")

# --- OKX 币种映射 ---
# OKX 的格式是 BTC/USDT，贵金属通常需要特定品种或在 OKX 下交易杠杆/永续
DEFAULT_SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "AAVE/USDT", "HYPE/USDT",
    "XRP/USDT", "RENDER/USDT", "TAO/USDT", "SUI/USDT", "DOGE/USDT", "UNI/USDT"
]

st.sidebar.header("OKX 监控配置")
selected_symbols = st.sidebar.multiselect("监测清单", DEFAULT_SYMBOLS, default=DEFAULT_SYMBOLS)
selected_intervals = st.sidebar.multiselect("监测周期", ["30m", "1h", "4h", "1d"], default=["30m", "1h", "4h", "1d"])

# OKX API 实例化 (无需 API Key 即可获取 K 线)
exchange = ccxt.okx()

# --- 核心逻辑 ---
def get_okx_signal(symbol, timeframe):
    try:
        # 获取 100 根 K 线确保 ATR 准确
        # OKX fetch_ohlcv: [timestamp, open, high, low, close, volume]
        limit = 100
        bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        
        df = pd.DataFrame(bars, columns=['Timestamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
        df['Close'] = df['Close'].astype(float)
        df['High'] = df['High'].astype(float)
        df['Low'] = df['Low'].astype(float)
        
        # 计算 UT Bot 指标
        df['atr'] = ta.atr(df['High'], df['Low'], df['Close'], length=10)
        df = df.dropna(subset=['atr']).copy()
        
        n_loss = 1.0 * df['atr']
        src = df['Close']
        trail_stop = np.zeros(len(df))
        
        # 递归计算
        for i in range(1, len(df)):
            p_stop = trail_stop[i-1]
            if src.iloc[i] > p_stop and src.iloc[i-1] > p_stop:
                trail_stop[i] = max(p_stop, src.iloc[i] - n_loss.iloc[i])
            elif src.iloc[i] < p_stop and src.iloc[i-1] < p_stop:
                trail_stop[i] = min(p_stop, src.iloc[i] + n_loss.iloc[i])
            else:
                trail_stop[i] = src.iloc[i] - n_loss.iloc[i] if src.iloc[i] > p_stop else src.iloc[i] + n_loss.iloc[i]
        
        # 最新状态判定
        curr_p, prev_p = src.iloc[-1], src.iloc[-2]
        curr_s, prev_s = trail_stop[-1], trail_stop[-2]
        
        # 成交量检查
        vol_ma = df['Volume'].rolling(10).mean().iloc[-1]
        is_vol_surge = df['Volume'].iloc[-1] > (vol_ma * 1.5)

        if curr_p > curr_s and prev_p <= prev_s:
            return f"🚀 BUY" + (" (放量)" if is_vol_surge else ""), curr_p
        elif curr_p < curr_s and prev_p >= prev_s:
            return "📉 SELL", curr_p
        else:
            status = "多 🟢" if curr_p > curr_s else "空 🔴"
            return status, curr_p
    except Exception as e:
        return f"错误: {str(e)[:10]}", 0

# --- 执行扫描 ---
if st.sidebar.button("同步 OKX 数据扫描"):
    with st.spinner('正在连接 OKX 全球服务器...'):
        summary = []
        for sym in selected_symbols:
            row_data = {"币种": sym}
            latest_price = 0
            
            for interval in selected_intervals:
                # 注意：OKX 的 1h 是 '1h'，4h 是 '4h'，1d 是 '1d'
                status, price = get_okx_signal(sym, interval)
                row_data[interval] = status
                if price != 0: latest_price = price
            
            row_data["OKX现价"] = f"{latest_price:.4f}"
            summary.append(row_data)
        
        st.session_state.okx_cache = pd.DataFrame(summary)

# --- 样式渲染 ---
if 'okx_cache' in st.session_state:
    df_display = st.session_state.okx_cache

    def style_output(val):
        if 'BUY' in str(val): return 'background-color: #00ff0022; color: #00ff00; font-weight: bold'
        if 'SELL' in str(val): return 'background-color: #ff000022; color: #ff0000; font-weight: bold'
        if '🟢' in str(val): return 'color: #28a745'
        if '🔴' in str(val): return 'color: #dc3545'
        return ''

    st.subheader(f"OKX 行情看板 (更新于: {datetime.now().strftime('%H:%M:%S')})")
    st.dataframe(
        df_display.style.applymap(style_output, subset=selected_intervals),
        use_container_width=True
    )
