import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
from datetime import datetime

# Hardcoded lists (update as needed)
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

# Function to detect golden cross
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
        
        data['EMA9'] = ta.ema(data['Close'], length=9)
        data['EMA21'] = ta.ema(data['Close'], length=21)
        
        # Check last bar for crossover
        last = data.iloc[-1]
        prev = data.iloc[-2]
        return (prev['EMA9'] < prev['EMA21']) and (last['EMA9'] > last['EMA21'])
    
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
        tickers = CRYPTO_TICKERS
    
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