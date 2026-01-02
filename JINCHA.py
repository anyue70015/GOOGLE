import streamlit as st
import yfinance as yf
import pandas as pd

# ... (请保留之前的 NASDAQ100_TICKERS, SP500_TICKERS, CRYPTO_TOP100 列表内容) ...

def scan_markets(tickers, timeframe, signal_type):
    interval_map = {'daily': '1d', 'weekly': '1wk', '4h': '1h'}
    period_map = {'daily': '1y', 'weekly': '2y', '4h': '60d'}
    
    # 批量下载数据
    data = yf.download(tickers, period=period_map[timeframe], interval=interval_map[timeframe], group_by='ticker', threads=True)
    
    results = []
    
    for ticker in tickers:
        try:
            if len(tickers) > 1:
                df = data[ticker].dropna()
            else:
                df = data.dropna()

            if timeframe == '4h':
                df = df.resample('4H').agg({
                    'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
                }).dropna()

            if len(df) < 22:
                continue

            # 计算 EMA
            ema9 = df['Close'].ewm(span=9, adjust=False).mean()
            ema21 = df['Close'].ewm(span=21, adjust=False).mean()
            
            prev_9, last_9 = ema9.iloc[-2], ema9.iloc[-1]
            prev_21, last_21 = ema21.iloc[-2], ema21.iloc[-1]

            # 信号识别逻辑
            if signal_type == "金叉 (Bullish)":
                # 9 上穿 21
                if prev_9 <= prev_21 and last_9 > last_21:
                    results.append(ticker)
            elif signal_type == "死叉 (Bearish)":
                # 9 下穿 21
                if prev_9 >= prev_21 and last_9 < last_21:
                    results.append(ticker)
                    
        except Exception:
            continue
            
    return results

# --- Streamlit UI 界面 ---
st.set_page_config(page_title="EMA 趋势扫描器", layout="wide")
st.title("📈 EMA 9/21 趋势信号扫描器")

# 第一排设置
col1, col2, col3 = st.columns(3)
with col1:
    market = st.selectbox("1. 选择市场", ["NASDAQ 100", "S&P 500", "Crypto Top 100"])
with col2:
    timeframe = st.selectbox("2. 选择时间周期", ["daily", "weekly", "4h"])
with col3:
    signal_type = st.radio("3. 信号类型", ["金叉 (Bullish)", "死叉 (Bearish)"], horizontal=True)

# 按钮样式颜色区分
btn_label = f"开始扫描 {signal_type}"
if st.button(btn_label, use_container_width=True):
    ticker_list = {
        "NASDAQ 100": NASDAQ100_TICKERS, 
        "S&P 500": SP500_TICKERS, 
        "Crypto Top 100": CRYPTO_TOP100
    }[market]
    
    with st.spinner(f"正在识别 {market} 中的 {signal_type} 信号..."):
        matches = scan_markets(ticker_list, timeframe, signal_type)
        
        if matches:
            color = "green" if "金叉" in signal_type else "red"
            st.markdown(f"### 🚀 找到以下目标 ({len(matches)} 个):")
            
            # 结果展示
            cols = st.columns(6)
            for i, ticker in enumerate(matches):
                with cols[i % 6]:
                    if color == "green":
                        st.success(f"**{ticker}**")
                    else:
                        st.error(f"**{ticker}**")
        else:
            st.info(f"当前市场和周期内未发现新的 {signal_type} 信号。")

st.divider()
st.caption("注：该工具仅供参考，不构成投资建议。4h 数据由 1h 数据重采样生成。")
