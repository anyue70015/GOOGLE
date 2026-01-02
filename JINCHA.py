import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime

# Hardcoded lists (update as needed; I've kept them complete based on prior versions)
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
    'TRGP', 'KR', 'PRU', 'EBAY', 'GRMN', 'CCI', 'A', 'HIG', 'IQV',
    'KDP', 'CPRT', 'EL', 'VMC', 'MLM', 'GEHC', 'NUE', 'HSY', 'VTR', 'WAB',
    'UAL', 'STT', 'ED', 'PCG', 'SYY', 'RMD', 'KEYS', 'EXPE',
    'ACGL', 'MCHP', 'FIS', 'WEC', 'OTIS', 'KMB', 'EQT', 'XYL', 'LYV', 'KVUE',
    'ODFL', 'HPE', 'RJF', 'WTW', 'IR', 'VRSK', 'MTB', 'FITB',
    'HUM', 'NRG', 'CHTR', 'TER', 'VICI', 'SYF', 'DG', 'ROL', 'EXR',
    'KHC', 'IBKR', 'CSGP', 'MTD', 'FSLR', 'ADM', 'EME', 'BRO', 'HBAN', 'ATO',
    'AEE', 'ULTA', 'DTE', 'DOV', 'WRB', 'EFX', 'TSCO', 'CBOE', 'TPR',
    'BR', 'PPL', 'DXCM', 'FE', 'NTRS', 'BIIB', 'AVB', 'CINF', 'AWK', 'OMC',
    'LEN', 'ES', 'CFG', 'CNP', 'STE', 'GIS', 'VLTO', 'STLD', 'EQR', 'IRM',
    'DLTR', 'LULU', 'JBL', 'STZ', 'TDY', 'HAL', 'RF', 'HUBB', 'EIX', 'LDOS',
    'PPG', 'DVN', 'PHM', 'WAT', 'VRSN', 'KEY', 'TROW', 'ON', 'L', 'RL',
    'LUV', 'WSM', 'CMS', 'NTAP', 'DRI', 'CPAY', 'IP', 'LH', 'PTC', 'NVR',
    'TSN', 'SBAC', 'HPQ', 'CNC', 'SW', 'CHD', 'CTRA', 'PODD', 'EXPD', 'NI',
    'TPL', 'WST', 'TYL', 'INCY', 'PFG', 'DGX', 'AMCR', 'CHRW', 'TRMB', 'JBHT',
    'PKG', 'TTD', 'GPN', 'MKC', 'IT', 'SNA', 'ZBH', 'CDW', 'FTV', 'SMCI',
    'ESS', 'IFF', 'BG', 'GPC', 'INVH', 'WY', 'PNR', 'LII', 'DD', 'GEN',
    'LNT', 'EVRG', 'MAA', 'ALB', 'DOW', 'HOLX', 'APTV', 'COO', 'J', 'TXT',
    'DECK', 'ERIE', 'FFIV', 'NWSA', 'VTRS', 'EG', 'BALL',
    'DPZ', 'AVY', 'BBY', 'LYB', 'KIM', 'SOLV', 'ALLE', 'UHS', 'NDSN', 'HII',
    'IEX', 'UDR', 'JKHY', 'MAS', 'HRL', 'REG', 'AKAM', 'BEN', 'WYNN', 'HST',
    'ZBRA', 'CLX', 'CF', 'AIZ', 'BXP', 'CPT', 'IVZ', 'MRNA', 'HAS',
    'SWK', 'DOC', 'BLDR', 'EPAM', 'ALGN', 'GL', 'DAY', 'RVTY', 'FDS', 'PNW',
    'SJM', 'AES', 'NCLH', 'MGM', 'BAX', 'CRL', 'SWKS', 'AOS', 'TAP', 'TECH',
    'MOH', 'HSIC', 'PAYC', 'FRT', 'APA', 'POOL', 'ARE', 'CPB', 'CAG', 'DVA',
    'GNRC', 'MOS', 'MTCH', 'LW'
]

CRYPTO_TOP100 = [
    'BTC-USD', 'ETH-USD', 'USDT-USD', 'BNB-USD', 'XRP-USD', 'USDC-USD', 'SOL-USD', 'TRX-USD', 'STETH-USD', 'DOGE-USD',
    'ADA-USD', 'WBTC-USD', 'BCH-USD', 'LINK-USD', 'LEO-USD', 'ZEC-USD', 'XMR-USD', 'XLM-USD', 'LTC-USD', 'AVAX-USD',
    'SHIB-USD', 'DAI-USD', 'TON-USD', 'CRO-USD', 'UNI-USD', 'PYUSD-USD', 'DOT-USD', 'MNT-USD', 'OKB-USD', 'XAUT-USD',
    'AAVE-USD', 'NEAR-USD', 'PEPE-USD', 'ETC-USD', 'HTX-USD', 'KCS-USD', 'SKY-USD', 'WLD-USD', 'APT-USD', 'GT-USD',
    'KAS-USD', 'ARB-USD', 'POL-USD', 'QNT-USD', 'FIL-USD', 'ALGO-USD', 'ATOM-USD', 'XDC-USD', 'ONDO-USD', 'WBNB-USD',
    'RETH-USD', 'PI-USD', 'ENA-USD', 'ICP-USD', 'PAXG-USD', 'JLP-USD', 'BUIDL-USD', 'JITOSOL-USD', 'BNSOL-USD', 'SUSDE-USD',
    'USDE-USD', 'USDF-USD', 'BFUSD-USD', 'SYRUPUSDC-USD', 'USDG-USD', 'USYC-USD', 'USDS-USD', 'BSC-USD', 'WSTETH-USD', 'WBETH-USD',
    'WEETH-USD', 'CBBTC-USD', 'WETH-USD', 'SUSDS-USD', 'USD1-USD', 'RAIN-USD', 'M-USD', 'BGB-USD', 'TAO-USD', 'HYPE-USD',
    'CC-USD', 'SUI-USD', 'HBAR-USD', 'USDT0-USD', 'PI-USD', 'ASTER-USD', 'WLFI-USD', 'HASH-USD', 'NIGHT-USD', 'PUMP-USD',
    'RSETH-USD', 'JAAA-USD', 'WSTETH-USD', 'FBTC-USD', 'TRUMP-USD'
]

# Function to detect golden cross (using pure pandas for EMA)
def has_golden_cross(ticker, timeframe):
    try:
        if timeframe == '4h':
            # yfinance doesn't have direct 4h, so get 1h and resample
            data = yf.download(ticker, period='60d', interval='1h')
            if data.empty:
                return False
            data = data.resample('4H').agg({
                'Open': 'first',
                'High': 'max',
                'Low': 'min',
                'Close': 'last',
                'Volume': 'sum'
            }).dropna()
        else:
            interval_map = {'daily': '1d', 'weekly': '1wk'}
            data = yf.download(ticker, period='1y', interval=interval_map[timeframe])
        
        if len(data) < 22:  # Need at least 21 periods for EMA21
            return False
        
        # Compute EMA using pandas ewm
        data['EMA9'] = data['Close'].ewm(span=9, adjust=False).mean()
        data['EMA21'] = data['Close'].ewm(span=21, adjust=False).mean()
        
        # Check last bar for crossover
        last = data.iloc[-1]
        prev = data.iloc[-2]
        return (prev['EMA9'] <= prev['EMA21']) and (last['EMA9'] > last['EMA21'])
    
    except Exception:
        return False

# Streamlit app
st.title("EMA Golden Cross Scanner (Based on Pine Script Strategy)")

market = st.selectbox("Select Market", ["NASDAQ 100", "S&P 500", "Crypto Top 100"])
timeframe = st.selectbox("Select Timeframe", ["daily", "weekly", "4h"])

if st.button("Scan for Golden Cross"):
    if market == "NASDAQ 100":
        tickers = NASDAQ100_TICKERS
    elif market == "S&P 500":
        tickers = SP500_TICKERS
    else:
        tickers = CRYPTO_TOP100
    
    with st.spinner("Scanning... This may take a while for large lists."):
        results = []
        for ticker in tickers:
            if has_golden_cross(ticker, timeframe):
                results.append(ticker)
        
        if results:
            st.success(f"Found {len(results)} assets with recent EMA9/21 Golden Cross on {timeframe} timeframe:")
            df = pd.DataFrame({"Ticker": results})
            st.table(df)
        else:
            st.info("No golden crosses found in the selected market and timeframe.")
