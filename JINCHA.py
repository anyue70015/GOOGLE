import streamlit as st
import yfinance as yf
import pandas as pd

# ==================== 标的列表（可自行扩展） ====================
NASDAQ100_TICKERS = [
    'AAPL', 'MSFT', 'GOOG', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA', 'AVGO', 'COST',
    'NFLX', 'AMD', 'ADBE', 'PEP', 'LIN', 'TMUS', 'CSCO', 'QCOM', 'TXN', 'AMAT',
    'INTU', 'MU', 'LRCX', 'ISRG', 'ADP', 'KLAC', 'PANW', 'SNPS', 'CDNS', 'MAR',
    # 添加更多到100个
]

SP500_TICKERS = [
    'AAPL', 'MSFT', 'NVDA', 'GOOG', 'GOOGL', 'AMZN', 'META', 'BRK.B', 'LLY', 'AVGO',
    'JPM', 'TSLA', 'UNH', 'V', 'XOM', 'MA', 'PG', 'JNJ', 'HD', 'MRK',
    # 添加更多到500个
]

CRYPTO_TOP100 = [
    'BTC-USD', 'ETH-USD', 'USDT-USD', 'BNB-USD', 'SOL-USD', 'XRP-USD', 'USDC-USD',
    'DOGE-USD', 'ADA-USD', 'TRX-USD', 'AVAX-USD', 'SHIB-USD', 'LINK-USD', 'DOT-USD',
    # 添加更多到100个
]

# ==================== 金叉检测函数（使用 pandas 内置 EMA） ====================
def has_golden_cross(ticker, timeframe='daily'):
    try:
        # 下载数据
        if timeframe == '4h':
            data = yf.download(ticker, period='60d', interval='1h', progress=False)
            if data.empty or len(data) < 100:
                return False
            # 重采样为4小时K线
            data = data.resample('4H').agg({
                'Open': 'first',
                'High': 'max',
                'Low': 'min',
                'Close': 'last',
                'Volume': 'sum'
            }).dropna()
        elif timeframe == 'weekly':
            data = yf.download(ticker, period='2y', interval='1wk', progress=False)
        else:  # daily
            data = yf.download(ticker, period='1y', interval='1d', progress=False)

        if len(data) < 22:
            return False

        # 使用 pandas 内置 ewm 计算 EMA（完全替代 ta.ema）
        data['EMA9'] = data['Close'].ewm(span=9, adjust=False).mean()
        data['EMA21'] = data['Close'].ewm(span=21, adjust=False).mean()

        # 判断最新一根K线是否发生金叉
        prev = data.iloc[-2]
        last = data.iloc[-1]
        return prev['EMA9'] <= prev['EMA21'] and last['EMA9'] > last['EMA21']

    except Exception as e:
        # st.warning(f"{ticker} 数据获取失败")  # 可选：显示错误
        return False

# ==================== Streamlit 界面 ====================
st.title("📈 EMA9/21 金叉扫描器")
st.markdown("扫描纳斯达克100、标普500、加密货币Top100中最新发生金叉的标的（日线/周线/4小时线）")

col1, col2 = st.columns(2)
with col1:
    market = st.selectbox("选择市场", ["NASDAQ 100", "S&P 500", "加密货币 Top 100"])
with col2:
    timeframe = st.selectbox("选择周期", ["daily（日线）", "weekly（周线）", "4h（4小时线）"])

if st.button("🔍 开始扫描", type="primary"):
    if market == "NASDAQ 100":
        tickers = NASDAQ100_TICKERS
    elif market == "S&P 500":
        tickers = SP500_TICKERS
    else:
        tickers = CRYPTO_TOP100

    with st.spinner(f"正在扫描 {len(tickers)} 个标的（{timeframe}周期），请稍等..."):
        results = []
        progress_bar = st.progress(0)
        for i, ticker in enumerate(tickers):
            if has_golden_cross(ticker, timeframe):
                results.append(ticker)
            progress_bar.progress((i + 1) / len(tickers))

        progress_bar.empty()

    if results:
        st.success(f"🎯 找到 {len(results)} 个金叉信号！")
        st.dataframe(pd.DataFrame({"Ticker": results}), use_container_width=True)
    else:
        st.info("当前条件下未找到金叉信号，建议换周期或稍后再试。")

st.caption("数据来源：Yahoo Finance | 金叉定义：EMA9 上穿 EMA21（最新K线确认）")
