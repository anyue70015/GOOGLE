import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta  # <-- Added this
from datetime import datetime

# 你的 ticker 列表（同之前）
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
    'MCO', 'MMC', 'GD', 'SNPS', 'WM', 'TT', 'CDNS', 'MMM', 'UPS', 'APO',
    'CRH', 'DELL', 'MAR', 'USB', 'HWM', 'ABNB', 'AMT', 'PNC', 'NOC', 'BK',
    'SHW', 'REGN', 'ELV', 'ORLY', 'GM', 'RCL', 'AON', 'EQIX', 'CTAS', 'GLW',
    'MNST', 'TDG', 'EMR', 'ECL', 'CI', 'WMB', 'JCI', 'FCX', 'WBD', 'ITW',
    'CMI', 'SPG', 'MDLZ', 'FDX', 'CSX', 'TEL', 'HLT', 'AJG', 'RSG', 'COR',
    'NSC', 'TRV', 'MSI', 'CL', 'TFC', 'PWR', 'ADSK', 'AEP', 'KMI', 'COIN',
    'STX', 'FTNT', 'WDC', 'ROST', 'AFL', 'SRE', 'PCAR', 'SLB', 'EOG',
    'WDAY', 'AZO', 'NDAQ', 'ZTS', 'BDX', 'APD', 'LHX', 'VST', 'NXPI', 'PYPL',
    'ALL', 'DLR', 'IDXX', 'ARES', 'F', 'MET', 'O', 'PSX', 'URI', 'EA',
    'D', 'VLO', 'EW', 'CMG', 'MPC', 'CAH', 'GWW', 'ROP', 'DDOG', 'TTWO',
    'AME', 'CBRE', 'OKE', 'AIG', 'FAST', 'PSA', 'AMP', 'CTVA', 'AXON', 'DAL',
    'BKR', 'CARR', 'TGT', 'EXC', 'LVS', 'ROK', 'XEL', 'MPWR', 'MSCI', 'FANG',
    'DHI', 'YUM', 'ETR', 'TKO', 'OXY', 'PAYX', 'CCL', 'FICO', 'PEG', 'CTSH',
    'XYZ', 'TRGP', 'KR', 'PRU', 'EBAY', 'GRMN', 'CCI', 'A', 'HIG', 'IQV',
    'KDP', 'CPRT', 'EL', 'VMC', 'MLM', 'GEHC', 'NUE', 'HSY', 'VTR', 'WAB',
    'UAL', 'FISV', 'STT', 'ED', 'PCG', 'SYY', 'RMD', 'KEYS', 'SNDK', 'EXPE',
    'ACGL', 'MCHP', 'FIS', 'WEC', 'OTIS', 'KMB', 'EQT', 'XYL', 'LYV', 'KVUE',
    'FIX', 'ODFL', 'FOXA', 'HPE', 'RJF', 'WTW', 'IR', 'VRSK', 'MTB', 'FITB',
    'HUM', 'FOX', 'NRG', 'CHTR', 'TER', 'VICI', 'SYF', 'DG', 'ROL', 'EXR',
    'KHC', 'IBKR', 'CSGP', 'MTD', 'FSLR', 'ADM', 'EME', 'BRO', 'HBAN', 'ATO',
    'AEE', 'ULTA', 'DTE', 'DOV', 'WRB', 'EFX', 'TSCO', 'EXE', 'CBOE', 'TPR',
    'BR', 'PPL', 'DXCM', 'FE', 'NTRS', 'BIIB', 'AVB', 'CINF', 'AWK', 'OMC',
    'LEN', 'ES', 'CFG', 'CNP', 'STE', 'GIS', 'VLTO', 'STLD', 'EQR', 'IRM',
    'DLTR', 'LULU', 'JBL', 'STZ', 'TDY', 'HAL', 'RF', 'HUBB', 'EIX', 'LDOS',
    'PPG', 'DVN', 'PHM', 'WAT', 'VRSN', 'KEY', 'TROW', 'ON', 'L', 'RL',
    'LUV', 'WSM', 'CMS', 'NTAP', 'DRI', 'CPAY', 'IP', 'LH', 'PTC', 'NVR',
    'TSN', 'SBAC', 'HPQ', 'CNC', 'SW', 'CHD', 'CTRA', 'PODD', 'EXPD', 'NI',
    'TPL', 'WST', 'TYL', 'INCY', 'PFG', 'DGX', 'AMCR', 'CHRW', 'TRMB', 'JBHT',
    'PKG', 'TTD', 'GPN', 'MKC', 'IT', 'SNA', 'ZBH', 'CDW', 'FTV', 'SMCI',
    'ESS', 'IFF', 'BG', 'GPC', 'Q', 'INVH', 'WY', 'PNR', 'LII', 'DD', 'GEN',
    'LNT', 'EVRG', 'MAA', 'ALB', 'DOW', 'HOLX', 'APTV', 'COO', 'J', 'TXT',
    'NWS', 'DECK', 'ERIE', 'FFIV', 'PSKY', 'NWSA', 'VTRS', 'EG', 'BALL',
    'DPZ', 'AVY', 'BBY', 'LYB', 'KIM', 'SOLV', 'ALLE', 'UHS', 'NDSN', 'HII',
    'IEX', 'UDR', 'JKHY', 'MAS', 'HRL', 'REG', 'AKAM', 'BEN', 'WYNN', 'HST',
    'ZBRA', 'CLX', 'BF.B', 'CF', 'AIZ', 'BXP', 'CPT', 'IVZ', 'MRNA', 'HAS',
    'SWK', 'DOC', 'BLDR', 'EPAM', 'ALGN', 'GL', 'DAY', 'RVTY', 'FDS', 'PNW',
    'SJM', 'AES', 'NCLH', 'MGM', 'BAX', 'CRL', 'SWKS', 'AOS', 'TAP', 'TECH',
    'MOH', 'HSIC', 'PAYC', 'FRT', 'APA', 'POOL', 'ARE', 'CPB', 'CAG', 'DVA',
    'GNRC', 'MOS', 'MTCH', 'LW'
]

CRYPTO_TOP100 = [
    'BTC', 'ETH', 'USDT', 'BNB', 'XRP', 'USDC', 'SOL', 'TRX', 'STETH', 'DOGE',
    'FIGR_HELOC', 'ADA', 'WBT', 'BCH', 'WSTETH', 'WBTC', 'WBETH', 'WEETH', 'USDS', 'BSC-USD',
    'LINK', 'LEO', 'ZEC', 'WETH', 'XMR', 'XLM', 'CBBTC', 'USDE', 'LTC', 'AVAX',
    'HYPE', 'CC', 'SUI', 'HBAR', 'USDT0', 'SHIB', 'DAI', 'SUSDS', 'TON', 'WLFI',
    'CRO', 'UNI', 'PYUSD', 'SUSDE', 'USD1', 'DOT', 'MNT', 'RAIN', 'M', 'BGB',
    'OKB', 'XAUT', 'AAVE', 'TAO', 'USDF', 'NEAR', 'PEPE', 'ETC', 'WETH', 'JITOSOL',
    'BUIDL', 'PI', 'ASTER', 'ENA', 'ICP', 'PAXG', 'SOL', 'USYC', 'HTX', 'USDG',
    'JLP', 'KCS', 'HASH', 'SKY', 'NIGHT', 'WLD', 'APT', 'SYRUPUSDC', 'BFUSD', 'BNSOL',
    'USDC', 'RLUSD', 'PUMP', 'RETH', 'ONDO', 'WBNB', 'GT', 'KAS', 'ARB', 'POL',
    'RSETH', 'QNT', 'FIL', 'ALGO', 'JAAA', 'WSTETH', 'ATOM', 'XDC', 'FBTC', 'TRUMP'
]

# For crypto, append '-USD' for yfinance
CRYPTO_TICKERS = [f"{ticker}-USD" for ticker in CRYPTO_TOP100]

def check_signals(ticker: str, timeframe: str = 'daily'):
    try:
        if timeframe == '4h':
            data = yf.download(ticker, period='90d', interval='1h', progress=False)
            if len(data) < 100:
                return None
            data = data.resample('4H').agg({
                'Open': 'first', 'High': 'max', 'Low': 'min',
                'Close': 'last', 'Volume': 'sum'
            }).dropna()
        else:
            interval_map = {'daily': '1d', 'weekly': '1wk'}
            data = yf.download(ticker, period='2y', interval=interval_map[timeframe], progress=False)
        
        if len(data) < 50:
            return None
        
        close = data['Close']
        data['EMA9'] = close.ta.ema(length=9)
        data['EMA21'] = close.ta.ema(length=21)
        data = data.dropna()
        
        if len(data) < 5:
            return None
        
        signals = []
        last = data.iloc[-1]
        recent = data.iloc[-5:]  # 最近5根K线
        
        # 1. 最近3-5根K线内是否有金叉（包括最近一根）
        cross_found = False
        cross_date = None
        for i in range(1, len(recent)):
            prev = recent.iloc[i-1]
            curr = recent.iloc[i]
            if prev['EMA9'] <= prev['EMA21'] and curr['EMA9'] > curr['EMA21']:  # 包含等于，避免遗漏
                signals.append("最近5根K线内发生金叉")
                cross_found = True
                cross_date = curr.name.strftime('%Y-%m-%d')
                break
        
        # 2. 当前处于金叉后强势状态：EMA9 > EMA21 且 Close > EMA9
        if last['EMA9'] > last['EMA21'] and last['Close'] > last['EMA9']:
            signals.append("金叉后强势（EMA9 > EMA21 且价格在上方）")
        
        # 3. EMA9 从下方快速接近 EMA21
        if last['EMA9'] < last['EMA21']:
            gap_pct = (last['EMA21'] - last['EMA9']) / last['EMA21'] * 100
            if gap_pct < 3:  # 小于3%视为接近（可调整）
                # 检查EMA9是否在上升（最近3根平均变化 >0）
                ema9_change = data['EMA9'].diff().iloc[-3:].mean()
                if ema9_change > 0:
                    signals.append(f"EMA9快速接近EMA21（差距 {gap_pct:.2f}%）")
        
        if signals:
            return {
                'ticker': ticker.replace('-USD', '') if 'USD' in ticker else ticker,
                'signals': "; ".join(signals),
                'close_price': round(last['Close'], 2),
                'cross_date': cross_date if cross_found else '-'
            }
        return None
    
    except Exception:
        return None

st.set_page_config(page_title="高级 EMA9/21 信号扫描器", layout="wide")
st.title("?? 高级 EMA 9/21 信号扫描器（多条件版）")

st.markdown("""
### 新增功能：
- **最近5根K线内金叉**（不再只看最新一根）
- **金叉后强势资产**：EMA9 > EMA21 且价格在EMA9上方（当前多头趋势强势股）
- **即将金叉**：EMA9 从下方快速接近 EMA21（差距<3% 且 EMA9上升）
""")

market = st.selectbox("选择市场", ["NASDAQ 100", "S&P 500", "Crypto Top 100"])
timeframe = st.selectbox("选择时间周期", ["daily", "weekly", "4h"])

if st.button("?? 开始扫描多条件信号"):
    if market == "NASDAQ 100":
        tickers = NASDAQ100_TICKERS
    elif market == "S&P 500":
        tickers = SP500_TICKERS
    else:
        tickers = CRYPTO_TICKERS
    
    st.info(f"正在扫描 {len(tickers)} 个资产（{timeframe}周期）... 需要几分钟")
    progress_bar = st.progress(0)
    results = []
    
    for i, ticker in enumerate(tickers):
        signal_data = check_signals(ticker, timeframe)
        if signal_data:
            results.append(signal_data)
        progress_bar.progress((i + 1) / len(tickers))
    
    progress_bar.empty()
    
    if results:
        st.success(f"?? 找到 {len(results)} 个符合条件的资产！")
        df = pd.DataFrame(results)
        df = df[['ticker', 'signals', 'close_price', 'cross_date']]
        df.columns = ['Ticker', '信号描述', '最新价格', '金叉日期（约）']
        st.dataframe(df.sort_values(by='信号描述'), use_container_width=True)
        
        # 可选：导出CSV
        csv = df.to_csv(index=False).encode()
        st.download_button("?? 下载结果 CSV", csv, "ema_signals.csv", "text/csv")
    else:
        st.warning("?? 当前条件下未找到符合信号的资产（市场可能处于高位，多头已确立）")

st.caption("""
- 数据来源：Yahoo Finance  
- '即将金叉' 阈值可自行调整（当前<3%差距）  
- 当前市场（2026年1月）处于牛市后期，多数资产已处于“金叉后强势”或无新信号  
- 建议在市场回调后使用“即将金叉”功能捕捉新机会
""")
