import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime

# ==================== 标的列表（完整版，可自行更新） ====================
# NASDAQ 100 (前100示例，实际约100个)
NASDAQ100_TICKERS = [
    'NVDA', 'AAPL', 'GOOG', 'GOOGL', 'MSFT', 'AMZN', 'META', 'AVGO', 'TSLA', 'NFLX',
    'PLTR', 'ASML', 'COST', 'AMD', 'MU', 'CSCO', 'AZN', 'APP', 'TMUS', 'LRCX',
    'SHOP', 'AMAT', 'ISRG', 'LIN', 'PEP', 'INTU', 'QCOM', 'AMGN', 'INTC', 'BKNG',
    'PDD', 'KLAC', 'TXN', 'GILD', 'ADBE', 'ADI', 'PANW', 'HON', 'CRWD', 'ARM',
    'VRTX', 'CEG', 'CMCSA', 'ADP', 'MELI', 'DASH', 'SBUX', 'SNPS', 'CDNS', 'MAR',
    'ABNB', 'REGN', 'ORLY', 'CTAS', 'MNST', 'MRVL', 'WBD', 'MDLZ', 'CSX', 'ADSK',
    'AEP', 'FTNT', 'TRI', 'ROST', 'PCAR', 'WDAY', 'NXPI', 'PYPL', 'IDXX', 'EA',
    'ROP', 'DDOG', 'TTWO', 'FAST', 'MSTR', 'AXON', 'BKR', 'EXC', 'XEL', 'FANG',
    'TEAM', 'CCEP', 'PAYX', 'CTSH', 'KDP', 'CPRT', 'GEHC', 'ZS', 'MCHP', 'ODFL',
    'VRSK', 'CHTR', 'KHC', 'CSGP', 'DXCM', 'BIIB', 'LULU', 'ON', 'GFS', 'TTD', 'CDW'
]

# S&P 500 (前500示例，实际500个，简化列前100+)
SP500_TICKERS = [
    'NVDA', 'AAPL', 'GOOG', 'GOOGL', 'MSFT', 'AMZN', 'META', 'AVGO', 'TSLA', 'BRK.B',
    'LLY', 'WMT', 'JPM', 'V', 'ORCL', 'MA', 'XOM', 'JNJ', 'NFLX', 'PLTR',
    'ABBV', 'BAC', 'COST', 'AMD', 'HD', 'PG', 'GE', 'MU', 'CVX', 'CSCO',
    'KO', 'UNH', 'WFC', 'MS', 'IBM', 'GS', 'CAT', 'MRK', 'AXP', 'PM',
    'CRM', 'RTX', 'APP', 'TMUS', 'ABT', 'TMO', 'MCD', 'LRCX', 'C', 'AMAT',
    'DIS', 'ISRG', 'LIN', 'PEP', 'BX', 'INTU', 'QCOM', 'SCHW', 'GEV', 'AMGN',
    'T', 'INTC', 'BLK', 'BKNG', 'VZ', 'TJX', 'UBER', 'NEE', 'APH', 'ACN',
    'BA', 'ANET', 'DHR', 'KLAC', 'NOW', 'SPGI', 'TXN', 'COF', 'VRTX', 'KKR',
    'LMT', 'PH', 'CEG', 'BMY', 'CMCSA', 'NEM', 'HCA', 'ADP', 'HOOD', 'MCK',
    'CVS', 'CME', 'DASH', 'MO', 'SO', 'SBUX', 'NKE', 'CVNA', 'ICE', 'DUK',
    'MCO', 'MMC', 'GD', 'SNPS', 'WM', 'TT', 'CDNS', 'MMM', 'UPS', 'APO'
    # ... 添加其余到500
]

# 加密货币 Top 100 (直接用 -USD 格式)
CRYPTO_TOP100 = [
    'BTC-USD', 'ETH-USD', 'USDT-USD', 'BNB-USD', 'XRP-USD', 'USDC-USD', 'SOL-USD', 'TRX-USD', 'STETH-USD', 'DOGE-USD',
    'ADA-USD', 'WBTC-USD', 'BCH-USD', 'LINK-USD', 'LEO-USD', 'ZEC-USD', 'XMR-USD', 'XLM-USD', 'LTC-USD', 'AVAX-USD',
    'SHIB-USD', 'DAI-USD', 'TON-USD', 'CRO-USD', 'UNI-USD', 'PYUSD-USD', 'DOT-USD', 'MNT-USD', 'OKB-USD', 'XAUT-USD',
    'AAVE-USD', 'NEAR-USD', 'PEPE-USD', 'ETC-USD', 'HTX-USD', 'KCS-USD', 'SKY-USD', 'WLD-USD', 'APT-USD', 'GT-USD',
    'KAS-USD', 'ARB-USD', 'POL-USD', 'QNT-USD', 'FIL-USD', 'ALGO-USD', 'ATOM-USD', 'XDC-USD', 'ONDO-USD', 'WBNB-USD',
    # ... 添加其余到100
]

# ==================== 金叉检测函数 ====================
def has_golden_cross(ticker, timeframe):
    try:
        if timeframe == '4h':
            data = yf.download(ticker, period='60d', interval='1h')
            if data.empty:
                return False
            data = data.resample('4H').agg({
                'Open': 'first', 'High': 'max', 'Low': 'min',
                'Close': 'last', 'Volume': 'sum'
            }).dropna()
        elif timeframe == 'weekly':
            data = yf.download(ticker, period='2y', interval='1wk')
        else:  # daily
            data = yf.download(ticker, period='1y', interval='1d')
        
        if len(data) < 22:  # 需要至少21周期计算EMA21
            return False
        
        # 用纯pandas计算EMA
        data['EMA9'] = data['Close'].ewm(span=9, adjust=False).mean()
        data['EMA21'] = data['Close'].ewm(span=21, adjust=False).mean()
        
        # 检查最新K线金叉
        last = data.iloc[-1]
        prev = data.iloc[-2]
        return (prev['EMA9'] <= prev['EMA21']) and (last['EMA9'] > last['EMA21'])
    
    except Exception as e:
        st.error(f"下载 {ticker} 数据失败: {str(e)}")
        return False

# ==================== Streamlit 界面 ====================
st.title("EMA 金叉扫描器 (基于简单EMA交叉动量策略)")

market = st.selectbox("选择市场", ["NASDAQ 100", "S&P 500", "加密货币 Top 100"])
timeframe_display = st.selectbox("选择周期", ["daily (日线)", "weekly (周线)", "4h (4小时线)"])
tf_map = {"daily (日线)": "daily", "weekly (周线)": "weekly", "4h (4小时线)": "4h"}

if st.button("扫描金叉"):
    tickers = NASDAQ100_TICKERS if market == "NASDAQ 100" else SP500_TICKERS if market == "S&P 500" else CRYPTO_TOP100
    
    with st.spinner("扫描中... 这可能需要一段时间"):
        results = [ticker for ticker in tickers if has_golden_cross(ticker, tf_map[timeframe_display])]
        
        if results:
            st.success(f"找到 {len(results)} 个金叉标的:")
            df = pd.DataFrame({"Ticker": results})
            st.table(df)
        else:
            st.info("未找到金叉，再试试其他周期或市场。")
