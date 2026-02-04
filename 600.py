import streamlit as st
import pandas as pd
import numpy as np
import pandas_ta as ta
import ccxt
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 页面配置 ---
st.set_page_config(page_title="OKX 聚合监控 (自动刷新)", layout="wide")

# 每 10 分钟自动刷新一次页面 (600,000 毫秒)
st_autorefresh(interval=10 * 60 * 1000, key="datarefresh")

st.title("⚡ OKX 永续合约/现货 UT Bot 实时监控")

# --- 币种与映射配置 ---
# OKX 永续合约通常后缀为 /USDT:USDT 或直接用代码。这里逻辑会自动处理。
DEFAULT_SYMBOLS = [
    "AAVE/USDT:USDT", "HYPE/USDT:USDT", "BTC/USDT:USDT", "ETH/USDT:USDT", 
    "SOL/USDT:USDT", "XRP/USDT:USDT", "RENDER/USDT:USDT", "TAO/USDT:USDT", 
    "SUI/USDT:USDT", "DOGE/USDT:USDT", "UNI/USDT:USDT", "XAG/USDT"
]

# 侧边栏
st.sidebar.header("监控配置")
selected_symbols = st.sidebar.multiselect("监测清单", DEFAULT_SYMBOLS, default=DEFAULT_SYMBOLS)
selected_intervals = st.sidebar.multiselect("监测周期", ["30m", "1h", "4h", "1d"], default=["30m", "1h", "4h", "1d"])

# OKX API 实例化
exchange = ccxt.okx()

# --- 核心计算逻辑 ---
def get_okx_signal(symbol, timeframe):
    try:
        # 获取 150 根 K 线确保 ATR 预热和信号判断
        limit = 150
        bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        
        df = pd.DataFrame(bars, columns=['Timestamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
        df[['Open', 'High', 'Low', 'Close', 'Volume']] = df[['Open', 'High', 'Low', 'Close', 'Volume']].astype(float)
        
        # UT Bot 指标计算
        df['atr'] = ta.atr(df['High'], df['Low'], df['Close'], length=10)
        df = df.dropna(subset=['atr']).copy()
        
        n_loss = 1.0 * df['atr']
        src = df['Close']
        trail_stop = np.zeros(len(df))
        
        # 递归计算止损线
        for i in range(1, len(df)):
            p_stop = trail_stop[i-1]
            if src.iloc[i] > p_stop and src.iloc[i-1] > p_stop:
                trail_stop[i] = max(p_stop, src.iloc[i] - n_loss.iloc[i])
            elif src.iloc[i] < p_stop and src.iloc[i-1] < p_stop:
                trail_stop[i] = min(p_stop, src.iloc[i] + n_loss.iloc[i])
            else:
                trail_stop[i] = src.iloc[i] - n_loss.iloc[i] if src.iloc[i] > p_stop else src.iloc[i] + n_loss.iloc[i]
        
        # 获取最后 3 根 K 线来判断信号（为了让 SELL 信号保留稍久一点，比如最近 2 根内触发过都算）
        curr_p, prev_p = src.iloc[-1], src.iloc[-2]
        curr_s, prev_s = trail_stop[-1], trail_stop[-2]
        
        # 信号判定逻辑
        # 刚刚触发
        if curr_p < curr_s and prev_p >= prev_s:
            return "📉 SELL", curr_p
        if curr_p > curr_s and prev_p <= prev_s:
            return "🚀 BUY", curr_p
            
        # 状态保持
        return ("多 🟢" if curr_p > curr_s else "空 🔴"), curr_p
        
    except Exception as e:
        return f"数据缺失", 0

# --- 执行扫描 ---
# 初始化缓存
if 'last_scan' not in st.session_state:
    st.session_state.last_scan = "尚未扫描"

def run_scan():
    summary = []
    with st.spinner('正在同步 OKX 数据...'):
        for sym in selected_symbols:
            row_data = {"币种": sym}
            latest_price = 0
            for interval in selected_intervals:
                status, price = get_okx_signal(sym, interval)
                row_data[interval] = status
                if price != 0: latest_price = price
            row_data["当前价"] = f"{latest_price:.4f}"
            summary.append(row_data)
        st.session_state.okx_cache = pd.DataFrame(summary)
        st.session_state.last_scan = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

# 手动刷新按钮
if st.sidebar.button("手动刷新数据"):
    run_scan()

# 首次运行自动执行一次
if 'okx_cache' not in st.session_state:
    run_scan()

# --- 展示表格 ---
if 'okx_cache' in st.session_state:
    df_display = st.session_state.okx_cache

    def style_output(val):
        if 'BUY' in str(val): return 'background-color: #00ff0022; color: #00ff00; font-weight: bold'
        if 'SELL' in str(val): return 'background-color: #ff000022; color: #ff0000; font-weight: bold'
        if '🟢' in str(val): return 'color: #28a745'
        if '🔴' in str(val): return 'color: #dc3545'
        return ''

    st.subheader(f"信号看板 (上次更新: {st.session_state.last_scan})")
    
    # 根据币种数量动态调整高度
    table_height = (len(selected_symbols) + 1) * 40
    
    st.dataframe(
        df_display.style.applymap(style_output, subset=selected_intervals),
        use_container_width=True,
        height=min(table_height, 800) # 最高 800，超过则滚动
    )
    
    st.info("💡 系统每 10 分钟自动更新一次。'🚀 BUY' 或 '📉 SELL' 仅在穿越的第一根 K 线显示，随后转为 🟢/🔴 状态。")
