import streamlit as st
import pandas as pd
import numpy as np
import pandas_ta as ta
import ccxt
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 1. 页面配置与自动刷新 ---
st.set_page_config(page_title="UT Bot OKX 实时监控", layout="wide")
# 每 10 分钟自动刷新一次页面 (600,000 毫秒)
st_autorefresh(interval=10 * 60 * 1000, key="datarefresh")

st.title("🛡️ UT Bot 混合数据源看板 (OKX 实时)")

# --- 2. 币种与数据源精细化配置 ---
# 规则：现货用 代码/USDT，合约用 代码/USDT:USDT
SYMBOLS_CONFIG = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "AAVE/USDT", 
    "HYPE/USDT", "XRP/USDT", "RENDER/USDT", "SUI/USDT", 
    "DOGE/USDT", "UNI/USDT", 
    "TAO/USDT:USDT",  # TAO 仅在合约中有数据
    "XAG/USDT:USDT",  # 白银 仅在合约中有数据
    "XAU/USDT:USDT"   # 黄金 仅在合约中有数据
]

st.sidebar.header("仪表盘设置")
selected_symbols = st.sidebar.multiselect("监测清单", SYMBOLS_CONFIG, default=SYMBOLS_CONFIG)
selected_intervals = st.sidebar.multiselect("周期", ["30m", "1h", "4h", "1d"], default=["30m", "1h", "4h", "1d"])

# 实例化 OKX
exchange = ccxt.okx()

# --- 3. 核心算法函数 ---
def get_okx_data(symbol, timeframe):
    try:
        # 获取 150 根 K 线确保 ATR 算法稳定
        bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=150)
        df = pd.DataFrame(bars, columns=['Timestamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
        df[['Open', 'High', 'Low', 'Close', 'Volume']] = df[['Open', 'High', 'Low', 'Close', 'Volume']].astype(float)
        
        # UT Bot 计算逻辑 (Key Value = 1, ATR Period = 10)
        df['atr'] = ta.atr(df['High'], df['Low'], df['Close'], length=10)
        df = df.dropna(subset=['atr']).copy()
        
        n_loss = 1.0 * df['atr']
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
        
        curr_p, prev_p = src.iloc[-1], src.iloc[-2]
        curr_s, prev_s = trail_stop[-1], trail_stop[-2]
        
        # 信号逻辑判断
        if curr_p < curr_s and prev_p >= prev_s:
            return "📉 SELL", curr_p
        elif curr_p > curr_s and prev_p <= prev_s:
            return "🚀 BUY", curr_p
        return ("多 🟢" if curr_p > curr_s else "空 🔴"), curr_p
    except Exception:
        return "数据缺失", 0

# --- 4. 扫描执行逻辑 ---
if 'okx_cache' not in st.session_state or st.sidebar.button("手动同步行情"):
    summary = []
    with st.spinner('正在从 OKX 同步最新 K 线数据...'):
        for sym in selected_symbols:
            # 简化显示名称：将 BTC/USDT:USDT 缩减为 BTC/USDT
            display_name = sym.split(':')[0]
            row_data = {"币种": display_name}
            latest_price = 0
            for inv in selected_intervals:
                status, price = get_okx_data(sym, inv)
                row_data[inv] = status
                if price != 0: latest_price = price
            row_data["现价"] = f"{latest_price:.4f}"
            summary.append(row_data)
        st.session_state.okx_cache = pd.DataFrame(summary)
        st.session_state.last_time = datetime.now().strftime('%H:%M:%S')

# --- 5. 网页前端渲染 ---
if 'okx_cache' in st.session_state:
    st.markdown(f"### 📊 实时信号看板 (上次更新: {st.session_state.last_time})")
    
    # 定义单元格颜色样式
    def style_func(val):
        if 'BUY' in str(val): return 'background-color: #00ff0022; color: #00ff00; font-weight: bold'
        if 'SELL' in str(val): return 'background-color: #ff000022; color: #ff0000; font-weight: bold'
        if '🟢' in str(val): return 'color: #28a745'
        if '🔴' in str(val): return 'color: #dc3545'
        return ''

    # 动态计算表格高度：每行约 40 像素
    table_height = (len(st.session_state.okx_cache) + 1) * 40
    
    st.dataframe(
        st.session_state.okx_cache.style.applymap(style_func, subset=selected_intervals),
        use_container_width=True,
        height=min(table_height, 1000)
    )

st.sidebar.markdown(f"**当前监测状态:** 运行中")
st.sidebar.write(f"监测总数: {len(selected_symbols)} 个品种")
