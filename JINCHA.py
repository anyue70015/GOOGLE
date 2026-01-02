import streamlit as st
import yfinance as yf
import pandas as pd

# 股票列表（可自行更新）
NASDAQ100_TICKERS = ['NVDA', 'AAPL', 'GOOG', 'MSFT', 'AMZN', 'META', 'TSLA', ...]  # 完整列表同之前

SP500_TICKERS = ['NVDA', 'AAPL', 'MSFT', ...]  # 同之前

CRYPTO_TOP100 = ['BTC-USD', 'ETH-USD', 'USDT-USD', 'BNB-USD', ...]  # 直接用 -USD 格式

# 金叉检测函数（用纯pandas计算EMA）
def has_golden_cross(ticker, timeframe='daily'):
    try:
        if timeframe == '4h':
            data = yf.download(ticker, period='60d', interval='1h')
            if data.empty:
                return False
            data = data.resample('4H').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()
        elif timeframe == 'weekly':
            data = yf.download(ticker, period='2y', interval='1wk')
        else:  # daily
            data = yf.download(ticker, period='1y', interval='1d')
        
        if len(data) < 22:
            return False
        
        # 纯pandas计算EMA
        data['EMA9'] = data['Close'].ewm(span=9, adjust=False).mean()
        data['EMA21'] = data['Close'].ewm(span=21, adjust=False).mean()
        
        # 最新K线金叉：前一根 EMA9 <= EMA21，当前 EMA9 > EMA21
        last = data.iloc[-1]
        prev = data.iloc[-2]
        return (prev['EMA9'] <= prev['EMA21']) and (last['EMA9'] > last['EMA21'])
    
    except Exception as e:
        st.error(f"{ticker} 下载失败: {e}")
        return False

# Streamlit界面
st.title("EMA9/21 金叉扫描器（基于Pine Script策略）")

market = st.selectbox("选择市场", ["NASDAQ 100", "S&P 500", "加密货币 Top 100"])
timeframe = st.selectbox("选择周期", ["daily（日线）", "weekly（周线）", "4h（4小时线）"])
tf_map = {"daily（日线）": "daily", "weekly（周线）": "weekly", "4h（4小时线）": "4h"}

if st.button("开始扫描"):
    tickers = NASDAQ100_TICKERS if market == "NASDAQ 100" else SP500_TICKERS if market == "S&P 500" else CRYPTO_TOP100
    
    with st.spinner(f"正在扫描 {len(tickers)} 个标的... 可能需要1-3分钟"):
        results = [ticker for ticker in tickers if has_golden_cross(ticker, tf_map[timeframe])]
    
    if results:
        st.success(f"在 {timeframe} 周期找到 {len(results)} 个金叉信号！")
        st.dataframe(pd.DataFrame({"Ticker": results}))
    else:
        st.info("当前没有找到金叉信号，再等等或换个周期试试~")

st.caption("数据来源：Yahoo Finance | 金叉定义：EMA9 上穿 EMA21")
