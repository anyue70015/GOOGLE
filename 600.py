import streamlit as st
import pandas as pd
import numpy as np
import pandas_ta as ta
import yfinance as yf
from datetime import datetime

# --- 页面配置 ---
st.set_page_config(page_title="UT Bot 多周期扫描器", layout="wide")

st.title("📈 UT Bot 多周期实时监测看板")
st.sidebar.header("控制面板")

# --- 配置参数 ---
SYMBOLS = st.sidebar.multiselect(
    "选择监测币种/股票",
    ["BTC-USD", "ETH-USD", "SOL-USD", "DOGE-USD", "NVDA", "AAPL", "TSLA", "MSFT"],
    default=["BTC-USD", "ETH-USD", "SOL-USD", "NVDA"]
)

INTERVALS = {
    "30m": "30m",
    "1h": "60m",
    "4h": "1h", # 简便起见使用1h模拟
    "1d": "1d"
}

SEND_KEY = st.sidebar.text_input("Server酱 SendKey (可选)", type="password")

# --- 核心计算函数 ---
def get_ut_signal(symbol, interval):
    try:
        period = "7d" if "m" in interval else "200d"
        df = yf.download(symbol, period=period, interval=interval, progress=False, auto_adjust=True)
        
        if df.empty or len(df) < 20:
            return None

        # 处理多级索引
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        df = df.dropna().copy()
        
        # 计算指标
        df['atr'] = ta.atr(df['High'], df['Low'], df['Close'], length=10)
        df = df.dropna(subset=['atr']).copy()
        
        n_loss = 1.0 * df['atr'] # Key Value = 1
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
        
        # 量能检查
        vol_ma = df['Volume'].rolling(window=10).mean().iloc[-1]
        is_vol_surge = df['Volume'].iloc[-1] > (vol_ma * 1.5)
        
        curr_price = src.iloc[-1]
        prev_price = src.iloc[-2]
        curr_stop = trail_stop[-1]
        prev_stop = trail_stop[-2]
        
        # 逻辑判断
        status = "看涨 🟢" if curr_price > curr_stop else "看跌 🔴"
        signal = "无"
        if curr_price > curr_stop and prev_price <= prev_stop:
            signal = "🚀 BUY" + (" (放量)" if is_vol_surge else "")
        elif curr_price < curr_stop and prev_price >= prev_stop:
            signal = "📉 SELL"
            
        return {
            "代码": symbol,
            "周期": interval,
            "价格": f"{curr_price:.2f}",
            "趋势": status,
            "信号": signal,
            "止损参考": f"{curr_stop:.2f}",
            "更新时间": datetime.now().strftime("%H:%M:%S")
        }
    except:
        return None

# --- UI 触发逻辑 ---
if st.sidebar.button("立即扫描行情"):
    st.write(f"最后更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = []
    progress_bar = st.progress(0)
    
    total_tasks = len(SYMBOLS) * len(INTERVALS)
    count = 0
    
    for s in SYMBOLS:
        for label, inv in INTERVALS.items():
            res = get_ut_signal(s, inv)
            if res:
                results.append(res)
            count += 1
            progress_bar.progress(count / total_tasks)
            
    if results:
        report_df = pd.DataFrame(results)
        
        # 样式美化
        def color_signal(val):
            if 'BUY' in val: return 'background-color: #00ff0022; color: #00ff00'
            if 'SELL' in val: return 'background-color: #ff000022; color: #ff0000'
            return ''

        st.dataframe(
            report_df.style.applymap(color_signal, subset=['信号']),
            use_container_width=True,
            height=600
        )
        
        # 重点提取 BUY 信号
        buys = report_df[report_df['信号'].str.contains('BUY')]
        if not buys.empty:
            st.success("检测到潜在买入机会！")
            st.toast("发现新买入信号！", icon="🚀")
    else:
        st.warning("未抓取到数据，请检查网络或代码。")
else:
    st.info("点击左侧按钮开始扫描多周期信号。")
