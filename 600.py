import streamlit as st
import pandas as pd
import numpy as np
import pandas_ta as ta
import yfinance as yf
from datetime import datetime

# --- 页面配置 ---
st.set_page_config(page_title="UT Bot Pro 监控面板", layout="wide")

st.title("🛡️ UT Bot 多周期共振扫描仪")

# --- 初始化监测列表 ---
DEFAULT_SYMBOLS = [
    "AAVE-USD", "HYPE-USD", "BTC-USD", "ETH-USD", "SOL-USD", 
    "XRP-USD", "RENDER-USD", "TAO-USD", "SUI-USD", "DOGE-USD", 
    "XAG-USD", "XAU-USD", "UNI-USD"
]

# --- 侧边栏配置 ---
st.sidebar.header("配置中心")
selected_symbols = st.sidebar.multiselect("监测清单", DEFAULT_SYMBOLS, default=DEFAULT_SYMBOLS)
selected_intervals = st.sidebar.multiselect("监测周期", ["30m", "1h", "4h", "1d"], default=["30m", "1h", "4h", "1d"])

# 时间映射
INTERVAL_MAP = {"30m": "30m", "1h": "60m", "4h": "1h", "1d": "1d"}

# --- 核心逻辑 ---
def get_signal_status(symbol, interval):
    """计算单个周期下的信号状态"""
    try:
        period = "7d" if "m" in interval else "200d"
        df = yf.download(symbol, period=period, interval=interval, progress=False, auto_adjust=True)
        if df.empty or len(df) < 20: return "数据缺失"
        
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # UT Bot 计算
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
        
        # 信号判断
        curr_p, prev_p = src.iloc[-1], src.iloc[-2]
        curr_s, prev_s = trail_stop[-1], trail_stop[-2]
        
        # 成交量
        vol_ma = df['Volume'].rolling(10).mean().iloc[-1]
        is_vol_surge = df['Volume'].iloc[-1] > (vol_ma * 1.5)

        if curr_p > curr_s and prev_p <= prev_s:
            return f"🚀 BUY" + (" (放量)" if is_vol_surge else "")
        elif curr_p < curr_s and prev_p >= prev_s:
            return "📉 SELL"
        else:
            return "多 🟢" if curr_p > curr_s else "空 🔴"
    except:
        return "错误"

# --- 执行扫描 ---
if st.sidebar.button("开始全量扫描") or 'data_cache' not in st.session_state:
    with st.spinner('正在调取各交易所 API 数据...'):
        summary = []
        for sym in selected_symbols:
            row_data = {"币种": sym}
            # 获取当前实时价格
            current_data = yf.Ticker(sym).history(period="1d")
            row_data["当前价"] = f"{current_data['Close'].iloc[-1]:.4f}" if not current_data.empty else "N/A"
            
            # 遍历每个选中的周期
            for interval in selected_intervals:
                row_data[interval] = get_signal_status(sym, INTERVAL_MAP[interval])
            summary.append(row_data)
        
        st.session_state.data_cache = pd.DataFrame(summary)

# --- 展示表格 ---
if 'data_cache' in st.session_state:
    df_display = st.session_state.data_cache

    # 样式定义
    def highlight_signals(val):
        if 'BUY' in str(val): return 'background-color: #155724; color: #d4edda; font-weight: bold'
        if 'SELL' in str(val): return 'background-color: #721c24; color: #f8d7da; font-weight: bold'
        if '🟢' in str(val): return 'color: #28a745'
        if '🔴' in str(val): return 'color: #dc3545'
        return ''

    st.subheader(f"信号看板 (更新于: {datetime.now().strftime('%H:%M:%S')})")
    st.dataframe(
        df_display.style.applymap(highlight_signals, subset=selected_intervals),
        use_container_width=True,
        height=(len(selected_symbols) + 1) * 38
    )

    # 底部说明
    st.caption("注：'多 🟢' 表示当前处于上涨趋势中，'🚀 BUY' 表示本周期刚刚触发买入信号。")
