import streamlit as st
import yfinance as yf
import numpy as np
import time
import pandas as pd
import random
import requests
from io import StringIO

st.set_page_config(page_title="标普500 + 纳斯达克100 + 热门ETF + 加密币 + 罗素2000 短线扫描工具", layout="wide")
st.title("标普500 + 纳斯达克100 + 热门ETF + 加密币 + 罗素2000 短线扫描工具")

# ── 新增清缓存按钮 ──
if st.button("🔄 强制刷新所有数据（清缓存 + 重新扫描）"):
    st.cache_data.clear()
    st.session_state.high_prob = []
    st.session_state.scanned_symbols = set()
    st.session_state.failed_count = 0
    st.session_state.fully_scanned = False
    st.session_state.scanning = False
    st.rerun()

st.write("支持完整罗素2000（动态从iShares官网下载最新持仓CSV，约2000只）。点击「开始扫描」一次后会自动持续运行（每50只刷新一次页面，不会停）。速度约每只1.5-3秒。保持页面打开即可。")

# ==================== 扫描范围选择 ====================
scan_mode = st.selectbox("选择扫描范围", 
                         ["全部", "只扫币圈", "只扫美股大盘 (标普500 + 纳斯达克100 + ETF)", "只扫罗素2000 (完整~2000只)"])

# ==================== 动态加载罗素2000 ====================
@st.cache_data(ttl=86400)  # 每天更新一次
def load_russell2000_tickers():
    url = "https://www.ishares.com/us/products/239710/ishares-russell-2000-etf/1467271812596.ajax?fileType=csv&fileName=IWM_holdings&dataType=fund"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        df = pd.read_csv(StringIO(resp.text), skiprows=9)
        if 'Ticker' not in df.columns:
            st.error("CSV格式变化，无法解析Ticker，使用备用列表")
            return ["IWM"]
        tickers = df['Ticker'].dropna().astype(str).tolist()
        tickers = [t.strip().upper() for t in tickers if t.strip() != '-' and t.strip() != 'TICKER' and len(t.strip()) <= 5 and t.strip().isalnum()]
        tickers = list(set(tickers))  # 去重
        st.success(f"成功加载罗素2000最新持仓（{len(tickers)} 只）")
        return tickers
    except Exception as e:
        st.error(f"加载罗素2000失败: {str(e)}，使用IWM代表")
        return ["IWM"]

# ==================== 核心常量 ====================
BACKTEST_CONFIG = {
    "3个月": {"range": "3mo", "interval": "1d"},
    "6个月": {"range": "6mo", "interval": "1d"},
    "1年":  {"range": "1y",  "interval": "1d"},
    "2年":  {"range": "2y",  "interval": "1d"},
    "3年":  {"range": "3y",  "interval": "1d"},
    "5年":  {"range": "5y",  "interval": "1d"},
    "10年": {"range": "10y", "interval": "1d"},
}

# ==================== 数据拉取 ====================
@st.cache_data(ttl=1800, show_spinner=False)
def fetch_yahoo_ohlcv(yahoo_symbol: str, range_str: str, interval: str = "1d"):
    try:
        time.sleep(random.uniform(0.01, 0.02))
        ticker = yf.Ticker(yahoo_symbol)
        df = ticker.history(period=range_str, interval=interval, auto_adjust=True, prepost=False, timeout=10)
        if df.empty or len(df) < 50:
            return None, None, None, None
        close = df['Close'].values.astype(float)
        high = df['High'].values.astype(float)
        low = df['Low'].values.astype(float)
        volume = df['Volume'].values.astype(float)
        mask = ~np.isnan(close)
        close, high, low, volume = close[mask], high[mask], low[mask], volume[mask]
        if len(close) < 50:
            return None, None, None, None
        return close, high, low, volume
    except Exception:
        return None, None, None, None

# ==================== 指标函数 ====================
def ema_np(x: np.ndarray, span: int) -> np.ndarray:
    alpha = 2 / (span + 1)
    ema = np.empty_like(x)
    ema[0] = x[0]
    for i in range(1, len(x)):
        ema[i] = alpha * x[i] + (1 - alpha) * ema[i-1]
    return ema

def macd_hist_np(close: np.ndarray) -> np.ndarray:
    ema12 = ema_np(close, 12)
    ema26 = ema_np(close, 26)
    macd_line = ema12 - ema26
    signal = ema_np(macd_line, 9)
    return macd_line - signal

def rsi_np(close: np.ndarray, period: int = 14) -> np.ndarray:
    delta = np.diff(close, prepend=close[0])
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    alpha = 1 / period
    gain_ema = np.empty_like(gain)
    loss_ema = np.empty_like(loss)
    gain_ema[0] = gain[0]
    loss_ema[0] = loss[0]
    for i in range(1, len(gain)):
        gain_ema[i] = alpha * gain[i] + (1 - alpha) * gain_ema[i-1]
        loss_ema[i] = alpha * loss[i] + (1 - alpha) * loss_ema[i-1]
    rs = gain_ema / (loss_ema + 1e-9)
    return 100 - (100 / (1 + rs))

def atr_np(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    prev_close = np.roll(close, 1)
    prev_close[0] = close[0]
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))
    atr = np.empty_like(tr)
    atr[0] = tr[0]
    alpha = 1 / period
    for i in range(1, len(tr)):
        atr[i] = alpha * tr[i] + (1 - alpha) * atr[i-1]
    return atr

def rolling_mean_np(x: np.ndarray, window: int) -> np.ndarray:
    if len(x) < window:
        return np.full_like(x, np.nanmean(x) if not np.isnan(x).all() else 0)
    cumsum = np.cumsum(np.insert(x, 0, 0.0))
    ma = (cumsum[window:] - cumsum[:-window]) / window
    return np.concatenate([np.full(window-1, ma[0]), ma])

def obv_np(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
    direction = np.sign(np.diff(close, prepend=close[0]))
    return np.cumsum(direction * volume)

def backtest_with_stats(close: np.ndarray, score: np.ndarray, steps: int):
    if len(close) <= steps + 1:
        return 0.5, 0.0
    idx = np.where(score[:-steps] >= 3)[0]
    if len(idx) == 0:
        return 0.5, 0.0
    rets = close[idx + steps] / close[idx] - 1
    win_rate = (rets > 0).mean()
    pf = rets[rets > 0].sum() / abs(rets[rets <= 0].sum()) if (rets <= 0).any() else 999
    return win_rate, pf

# ==================== 核心计算 ====================
@st.cache_data(show_spinner=False)
def compute_stock_metrics(symbol: str, cfg_key: str = "1年"):
    yahoo_symbol = f"{symbol.upper()}-USD" if symbol.upper() in crypto_set else symbol.upper()
    
    close, high, low, volume = fetch_yahoo_ohlcv(yahoo_symbol, BACKTEST_CONFIG[cfg_key]["range"])
    
    if close is None:
        return None

    macd_hist = macd_hist_np(close)
    rsi = rsi_np(close)
    atr = atr_np(high, low, close)
    obv = obv_np(close, volume)
    vol_ma20 = rolling_mean_np(volume, 20)
    atr_ma20 = rolling_mean_np(atr, 20)
    obv_ma20 = rolling_mean_np(obv, 20)

    sig_macd = macd_hist[-1] > 0
    sig_vol = volume[-1] > vol_ma20[-1] * 1.1
    sig_rsi = rsi[-1] >= 60
    sig_atr = atr[-1] > atr_ma20[-1] * 1.1
    sig_obv = obv[-1] > obv_ma20[-1] * 1.05

    score = sum([sig_macd, sig_vol, sig_rsi, sig_atr, sig_obv])

    sig_details = {
        "MACD>0": sig_macd,
        "放量": sig_vol,
        "RSI≥60": sig_rsi,
        "ATR放大": sig_atr,
        "OBV上升": sig_obv
    }

    sig_macd_hist = (macd_hist > 0).astype(int)
    sig_vol_hist = (volume > vol_ma20 * 1.1).astype(int)
    sig_rsi_hist = (rsi >= 60).astype(int)
    sig_atr_hist = (atr > atr_ma20 * 1.1).astype(int)
    sig_obv_hist = (obv > obv_ma20 * 1.05).astype(int)
    score_arr = sig_macd_hist + sig_vol_hist + sig_rsi_hist + sig_atr_hist + sig_obv_hist

    prob7, pf7 = backtest_with_stats(close[:-1], score_arr[:-1], 7)

    price = close[-1]
    change = (close[-1] / close[-2] - 1) * 100 if len(close) >= 2 else 0

    return {
        "symbol": symbol.upper(),
        "price": price,
        "change": change,
        "score": score,
        "prob7": prob7,
        "pf7": pf7,
        "sig_details": sig_details,
        "is_crypto": symbol.upper() in crypto_set
    }

# ==================== 完整硬编码成分股 + 热门ETF + 加密币 ====================
@st.cache_data(ttl=86400)
def load_sp500_tickers():
    return [
        "NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "GOOG", "META", "AVGO", "TSLA", "BRK.B", "LLY", "JPM", "WMT", "V", "ORCL",
        "MA", "XOM", "JNJ", "PLTR", "BAC", "ABBV", "NFLX", "COST", "AMD", "HD", "PG", "GE", "MU", "CSCO", "UNH",
        "KO", "CVX", "WFC", "MS", "IBM", "CAT", "GS", "MRK", "AXP", "PM", "CRM", "RTX", "APP", "TMUS", "LRCX",
        "MCD", "TMO", "ABT", "C", "AMAT", "ISRG", "DIS", "LIN", "PEP", "INTU", "QCOM", "SCHW", "GEV", "AMGN", "BKNG",
        "T", "TJX", "INTC", "VZ", "BA", "UBER", "BLK", "APH", "KLAC", "NEE", "ACN", "ANET", "DHR", "TXN", "SPGI",
        "NOW", "COF", "GILD", "ADBE", "PFE", "BSX", "UNP", "LOW", "ADI", "SYK", "PGR", "PANW", "WELL", "DE", "HON",
        "ETN", "MDT", "CB", "CRWD", "BX", "PLD", "VRTX", "KKR", "NEM", "COP", "CEG", "PH", "LMT", "BMY", "HCA",
        "CMCSA", "HOOD", "ADP", "MCK", "CVS", "DASH", "CME", "SBUX", "MO", "SO", "ICE", "MCO", "GD", "MMC", "SNPS",
        "DUK", "NKE", "WM", "TT", "CDNS", "CRH", "APO", "MMM", "DELL", "USB", "UPS", "HWM", "MAR", "PNC", "ABNB",
        "AMT", "REGN", "NOC", "BK", "SHW", "RCL", "ORLY", "ELV", "GM", "CTAS", "GLW", "AON", "EMR", "FCX", "MNST",
        "ECL", "EQIX", "JCI", "CI", "TDG", "ITW", "WMB", "CMI", "WBD", "MDLZ", "FDX", "TEL", "HLT", "CSX", "AJG",
        "COR", "RSG", "NSC", "TRV", "TFC", "PWR", "CL", "COIN", "ADSK", "MSI", "STX", "WDC", "CVNA", "AEP", "SPG",
        "FTNT", "KMI", "PCAR", "ROST", "WDAY", "SRE", "AFL", "AZO", "NDAQ", "SLB", "EOG", "PYPL", "NXPI", "BDX",
        "ZTS", "LHX", "APD", "IDXX", "APD", "VST", "ALL", "DLR", "F", "MET", "URI", "O", "PSX", "EA", "D", "VLO",
        "CMG", "CAH", "MPC", "CBRE", "GWW", "ROP", "DDOG", "AME", "FAST", "TTWO", "AIG", "AMP", "AXON", "DAL", "OKE",
        "PSA", "CTVA", "MPWR", "CARR", "TGT", "ROK", "LVS", "BKR", "XEL", "MSCI", "EXC", "DHI", "YUM", "FANG", "FICO",
        "ETR", "CTSH", "PAYX", "CCL", "PEG", "KR", "PRU", "GRMN", "TRGP", "OXY", "A", "MLM", "VMC", "EL", "HIG",
        "IQV", "EBAY", "CCI", "KDP", "GEHC", "NUE", "CPRT", "WAB", "VTR", "HSY", "ARES", "STT", "UAL", "SNDK", "FISV",
        "ED", "RMD", "SYY", "KEYS", "EXPE", "MCHP", "FIS", "ACGL", "PCG", "WEC", "OTIS", "FIX", "LYV", "XYL", "EQT",
        "KMB", "ODFL", "KVUE", "HPE", "RJF", "IR", "WTW", "FITB", "MTB", "TER", "HUM", "SYF", "NRG", "VRSK", "DG",
        "VICI", "IBKR", "ROL", "MTD", "FSLR", "KHC", "CSGP", "EME", "HBAN", "ADM", "EXR", "BRO", "DOV", "ATO", "EFX",
        "TSCO", "AEE", "ULTA", "TPR", "WRB", "CHTR", "CBOE", "DTE", "BR", "NTRS", "DXCM", "EXE", "BIIB", "PPL", "AVB",
        "FE", "LEN", "CINF", "CFG", "STLD", "AWK", "VLTO", "ES", "JBL", "OMC", "GIS", "STE", "CNP", "DLTR", "LULU",
        "RF", "TDY", "STZ", "IRM", "HUBB", "EQR", "LDOS", "HAL", "PPG", "PHM", "KEY", "WAT", "EIX", "TROW", "VRSN",
        "WSM", "DVN", "ON", "L", "DRI", "NTAP", "RL", "CPAY", "HPQ", "LUV", "CMS", "IP", "LH", "PTC", "TSN",
        "SBAC", "CHD", "EXPD", "PODD", "SW", "NVR", "CNC", "TYL", "TPL", "NI", "WST", "INCY", "PFG", "CTRA", "DGX",
        "CHRW", "AMCR", "TRMB", "GPN", "JBHT", "PKG", "TTD", "MKC", "SNA", "SMCI", "IT", "CDW", "ZBH", "FTV", "ALB",
        "Q", "GPC", "LII", "PNR", "DD", "IFF", "BG", "GDDY", "TKO", "GEN", "WY", "ESS", "INVH", "LNT", "EVRG",
        "APTV", "HOLX", "DOW", "COO", "MAA", "J", "TXT", "FOXA", "FOX", "FFIV", "DECK", "PSKY", "ERIE", "BBY", "DPZ",
        "UHS", "VTRS", "EG", "BALL", "AVY", "SOLV", "LYB", "ALLE", "KIM", "HII", "NDSN", "IEX", "JKHY", "MAS", "HRL",
        "WYNN", "REG", "AKAM", "HST", "BEN", "ZBRA", "MRNA", "BF.B", "CF", "UDR", "AIZ", "CLX", "IVZ", "EPAM", "SWK",
        "CPT", "HAS", "BLDR", "ALGN", "GL", "DOC", "DAY", "BXP", "RVTY", "FDS", "SJM", "PNW", "NCLH", "MGM", "CRL",
        "AES", "BAX", "NWSA", "SWKS", "AOS", "TECH", "TAP", "HSIC", "FRT", "PAYC", "POOL", "APA", "MOS", "MTCH", "LW",
        "NWS"
    ]

ndx100 = [
    "ADBE","AMD","ABNB","ALNY","GOOGL","GOOG","AMZN","AEP","AMGN","ADI","AAPL","AMAT","APP","ARM","ASML",
    "AZN","TEAM","ADSK","ADP","AXON","BKR","BKNG","AVGO","CDNS","CHTR","CTAS","CSCO","CCEP","CTSH","CMCSA",
    "CEG","CPRT","CSGP","COST","CRWD","CSX","DDOG","DXCM","FANG","DASH","EA","EXC","FAST","FER","FTNT",
    "GEHC","GILD","HON","IDXX","INSM","INTC","INTU","ISRG","KDP","KLAC","KHC","LRCX","LIN","MAR","MRVL",
    "MELI","META","MCHP","MU","MSFT","MSTR","MDLZ","MPWR","MNST","NFLX","NVDA","NXPI","ORLY","ODFL","PCAR",
    "PLTR","PANW","PAYX","PYPL","PDD","PEP","QCOM","REGN","ROP","ROST","STX","SHOP","SBUX","SNPS","TMUS",
    "TTWO","TSLA","TXN","TRI","VRSK","VRTX","WBD","WDC","WDAY","XEL","ZS"
]

extra_etfs = [
    "SPY","QQQ","VOO","IVV","VTI","VUG","SCHG","IWM","DIA","SLV","GLD","GDX","GDXJ","SIL","SLVP",
    "RING","SGDJ","SMH","SOXX","SOXL","TQQQ","BITO","MSTR","ARKK","XLK","XLF","XLE","XLV","XLI","XLY","XLP"
]

gate_top200 = [
    "BTC", "ETH", "SOL", "USDT", "BNB", "XRP", "DOGE", "TON", "ADA", "SHIB", "AVAX", "TRX", "LINK", "DOT", "BCH",
    "NEAR", "LTC", "MATIC", "LEO", "PEPE", "UNI", "ICP", "ETC", "APT", "KAS", "XMR", "FDUSD", "STX", "FIL", "HBAR", 
    "OKB", "MNT", "CRO", "ATOM", "XLM", "ARB", "RNDR", "VET", "IMX", "MKR", "INJ", "GRT", "TAO", "AR", "OP", "FLOKI",
    "THETA", "FTM", "RUNE", "BONK", "TIA", "SEI", "JUP", "LDO", "PYTH", "CORE", "ALGO", "SUI", "GALA", "AAVE", "BEAM",
    "FLOW", "BGB", "QNT", "BSV", "EGLD", "ORDI", "DYDX", "AXS", "BTT", "FLR", "CHZ", "WLD", "STRK", "SAND", "EOS",
    "KCS", "NEO", "AKT", "ONDO", "XTZ", "CFX", "JASMY", "RON", "GT", "1000SATS", "SNX", "AGIX", "WIF", "USDD", "KLAY",
    "PENDLE", "AXL", "CHEEL", "MEW", "XEC", "GNO", "ZEC", "ENS", "NEXO", "XAUt", "CBETH", "CKB", "FRAX", "BLUR", "SUPER",
    "MINA", "SAFE", "1INCH", "NFT", "IOST", "COMP", "GMT", "LPT", "ZIL", "GLM", "KSM", "LRC", "OSMO", "DASH", "HOT",
    "ZRO", "CRV", "CELO", "KDA", "ENJ", "BAT", "QTUM", "ELF", "TURBO", "RVN", "ZRX", "SC", "ANKR", "RSR", "T", "GAL",
    "ILV", "YFI", "UMA", "API3", "SUSHI", "BAL", "BAND", "AMP", "CHR", "AUDIO", "YGG", "ONE", "TRB", "ACH", "SFP", "RIF",
    "POWR", "POLS", "ALPHA", "FOR", "FIDA", "POLS", "RAY", "STEP", "TORN", "TRIBE", "AKRO", "MLN", "GTC", "KAR", "BNC",
    "HARD", "DDX", "CREAM", "QUICK", "CQT", "SUKU", "RLY", "RAD", "FARM", "CLV", "ALCX", "MASK", "TOKE", "YLD", "DNT",
    "CELL", "GNO", "DODO", "POLS", "SWAP", "BNT", "KEEP", "NU", "TBTC", "UMA", "LON", "REQ", "MIR", "KP3R", "BANCOR",
    "PNT", "WHALE", "SRM", "OXY", "TRU", "PDEX", "BZRX", "HEGIC", "ESD", "BAC", "MTA", "VALUE", "YAX", "AMPL", "CVP",
    "RGT", "HEGIC", "CREAM", "YAM", "SASHIMI", "SUSHI", "YFV", "YFI", "UNI", "AAVE", "COMP", "BAL", "CRV", "REN", "KNC",
    "SNX", "ZRX", "BNT", "OMG", "MKR", "LRC", "BAT", "DAI", "USDC", "USDT", "TUSD", "PAX", "BUSD", "HUSD", "EURT", "XAUT",
    "DG"
]

okx_top200 = [
    "BTC", "ETH", "USDT", "SOL", "XRP", "BNB", "DOGE", "TON", "ADA", "SHIB", "AVAX", "TRX", "LINK", "DOT", "BCH",
    "NEAR", "LTC", "MATIC", "LEO", "PEPE", "UNI", "ICP", "ETC", "APT", "KAS", "XMR", "FDUSD", "STX", "FIL", "HBAR", 
    "OKB", "MNT", "CRO", "ATOM", "XLM", "ARB", "RNDR", "VET", "IMX", "MKR", "INJ", "GRT", "TAO", "AR", "OP", "FLOKI",
    "THETA", "FTM", "RUNE", "BONK", "TIA", "SEI", "JUP", "LDO", "PYTH", "CORE", "ALGO", "SUI", "GALA", "AAVE", "BEAM",
    "FLOW", "BGB", "QNT", "BSV", "EGLD", "ORDI", "DYDX", "AXS", "BTT", "FLR", "CHZ", "WLD", "STRK", "SAND", "EOS",
    "KCS", "NEO", "AKT", "ONDO", "XTZ", "CFX", "JASMY", "RON", "GT", "1000SATS", "SNX", "AGIX", "WIF", "USDD", "KLAY",
    "PENDLE", "AXL", "CHEEL", "MEW", "XEC", "GNO", "ZEC", "ENS", "NEXO", "XAUt", "CBETH", "CKB", "FRAX", "BLUR", "SUPER",
    "MINA", "SAFE", "1INCH", "NFT", "IOST", "COMP", "GMT", "LPT", "ZIL", "GLM", "KDA", "ENJ", "BAT", "QTUM", "ELF",
    "TURBO", "RVN", "ZRX", "SC", "ANKR", "RSR", "T", "GAL", "ILV", "YFI", "UMA", "API3", "SUSHI", "BAL", "BAND", "AMP",
    "CHR", "AUDIO", "YGG", "ONE", "TRB", "ACH", "SFP", "RIF", "POWR", "POLS", "ALPHA", "FOR", "FIDA", "POLS", "RAY",
    "STEP", "TORN", "TRIBE", "AKRO", "MLN", "GTC", "KAR", "BNC", "HARD", "DDX", "CREAM", "QUICK", "CQT", "SUKU", "RLY",
    "RAD", "FARM", "CLV", "ALCX", "MASK", "TOKE", "YLD", "DNT", "CELL", "GNO", "DODO", "POLS", "SWAP", "BNT", "KEEP",
    "NU", "TBTC", "UMA", "LON", "REQ", "MIR", "KP3R", "BANCOR", "PNT", "WHALE", "SRM", "OXY", "TRU", "PDEX", "BZRX",
    "HEGIC", "ESD", "BAC", "MTA", "VALUE", "YAX", "AMPL", "CVP", "RGT", "HEGIC", "CREAM", "YAM", "SASHIMI", "SUSHI",
    "YFV", "YFI", "UNI", "AAVE", "COMP", "BAL", "CRV", "REN", "KNC", "SNX", "ZRX", "BNT", "OMG", "MKR", "LRC", "BAT",
    "DAI", "USDC", "USDT", "TUSD", "PAX", "BUSD", "HUSD", "EURT", "XAUT", "DG"
]

# 定义加密币集合
crypto_tickers = list(set(gate_top200 + okx_top200))
crypto_set = set(c.upper() for c in crypto_tickers)

# 美股大盘列表
stock_etf_tickers = list(set(load_sp500_tickers() + ndx100 + extra_etfs))

# 所有列表
all_tickers = list(set(stock_etf_tickers + crypto_tickers))
all_tickers.sort()

# 根据选择设置扫描列表
if scan_mode == "全部":
    tickers_to_scan = all_tickers
    st.write(f"扫描范围：全部（总计 {len(all_tickers)} 只）")
elif scan_mode == "只扫币圈":
    tickers_to_scan = crypto_tickers
    st.write(f"扫描范围：只扫币圈（{len(crypto_tickers)} 只）")
elif scan_mode == "只扫美股大盘 (标普500 + 纳斯达克100 + ETF)":
    tickers_to_scan = stock_etf_tickers
    st.write(f"扫描范围：只扫美股大盘（{len(stock_etf_tickers)} 只）")
elif scan_mode == "只扫罗素2000 (完整~2000只)":
    tickers_to_scan = load_russell2000_tickers()
    st.write(f"扫描范围：罗素2000（完整 {len(tickers_to_scan)} 只，动态最新）")

mode = st.selectbox("回测周期", list(BACKTEST_CONFIG.keys()), index=2)
sort_by = st.selectbox("结果排序方式", ["PF7 (盈利因子)", "7日概率"], index=0)

# session_state 初始化
if 'high_prob' not in st.session_state:
    st.session_state.high_prob = []
if 'scanned_symbols' not in st.session_state:
    st.session_state.scanned_symbols = set()
if 'failed_count' not in st.session_state:
    st.session_state.failed_count = 0
if 'fully_scanned' not in st.session_state:
    st.session_state.fully_scanned = False
if 'scanning' not in st.session_state:
    st.session_state.scanning = False

progress_bar = st.progress(0)
status_text = st.empty()

# ==================== 显示结果 ====================
if st.session_state.high_prob:
    df_all = pd.DataFrame([x for x in st.session_state.high_prob if x is not None])
    
    if not df_all.empty:
        stock_df = df_all[~df_all['is_crypto']]
        crypto_df = df_all[df_all['is_crypto']]
        
        # 股票优质显示
        stock_filtered = stock_df[(stock_df['pf7'] >= 3.6) | (stock_df['prob7'] >= 0.68)].copy()
        
        # 加密币显示7日概率 > 50%
        crypto_filtered = crypto_df[crypto_df['prob7'] > 0.5].copy()
        
        if not stock_filtered.empty:
            df_display = stock_filtered.copy()
            df_display['price'] = df_display['price'].round(2)
            df_display['change'] = df_display['change'].apply(lambda x: f"{x:+.2f}%")
            df_display['prob7'] = (df_display['prob7'] * 100).round(1).map("{:.1f}%".format)
            df_display['pf7'] = df_display['pf7'].round(2)
            
            if sort_by == "PF7 (盈利因子)":
                df_display = df_display.sort_values("pf7", ascending=False)
            else:
                df_display = df_display.sort_values("prob7", ascending=False, key=lambda x: x.str.rstrip('%').astype(float))
            
            st.subheader(f"🔹 短线优质股票（PF7≥3.6 或 7日≥68%） 共 {len(df_display)} 只")
            for _, row in df_display.iterrows():
                details = row['sig_details']
                detail_str = " | ".join([
                    f"MACD>0: {'是' if details['MACD>0'] else '否'}",
                    f"放量: {'是' if details['放量'] else '否'}",
                    f"RSI≥60: {'是' if details['RSI≥60'] else '否'}",
                    f"ATR放大: {'是' if details['ATR放大'] else '否'}",
                    f"OBV上升: {'是' if details['OBV上升'] else '否'}"
                ])
                st.markdown(
                    f"**{row['symbol']}** - 价格: ${row['price']:.2f} ({row['change']}) - "
                    f"得分: {row['score']}/5 - {detail_str} - "
                    f"**7日概率: {row['prob7']} | PF7: {row['pf7']}**"
                )
        
        if not crypto_filtered.empty:
            df_display = crypto_filtered.copy()
            df_display['price'] = df_display['price'].round(2)
            df_display['change'] = df_display['change'].apply(lambda x: f"{x:+.2f}%")
            df_display['prob7'] = (df_display['prob7'] * 100).round(1).map("{:.1f}%".format)
            df_display['pf7'] = df_display['pf7'].round(2)
            
            if sort_by == "PF7 (盈利因子)":
                df_display = df_display.sort_values("pf7", ascending=False)
            else:
                df_display = df_display.sort_values("prob7", ascending=False, key=lambda x: x.str.rstrip('%').astype(float))
            
            st.subheader(f"🔹 短线优质加密币（7日概率 > 50%） 共 {len(df_display)} 只")
            for _, row in df_display.iterrows():
                details = row['sig_details']
                detail_str = " | ".join([
                    f"MACD>0: {'是' if details['MACD>0'] else '否'}",
                    f"放量: {'是' if details['放量'] else '否'}",
                    f"RSI≥60: {'是' if details['RSI≥60'] else '否'}",
                    f"ATR放大: {'是' if details['ATR放大'] else '否'}",
                    f"OBV上升: {'是' if details['OBV上升'] else '否'}"
                ])
                st.markdown(
                    f"**{row['symbol']} (加密币)** - 价格: ${row['price']:.2f} ({row['change']}) - "
                    f"得分: {row['score']}/5 - {detail_str} - "
                    f"**7日概率: {row['prob7']} | PF7: {row['pf7']}**"
                )
        
        if stock_filtered.empty and crypto_filtered.empty:
            st.warning("当前无任何满足条件的标的")

st.info(f"已扫描: {len(st.session_state.scanned_symbols)}/{len(tickers_to_scan)} | 失败/跳过: {st.session_state.failed_count} | 已获取结果: {len(st.session_state.high_prob)}")

# ==================== 扫描逻辑 ====================
if st.button("🚀 开始/继续全量扫描（点击后自动持续运行，不会停）"):
    st.session_state.scanning = True

if st.session_state.scanning and not st.session_state.fully_scanned:
    with st.spinner("扫描进行中（每50只刷新一次页面）..."):
        batch_size = 50
        processed_in_this_run = 0
        for sym in tickers_to_scan:
            if processed_in_this_run >= batch_size:
                break
            if sym in st.session_state.scanned_symbols:
                continue
            status_text.text(f"正在计算 {sym} ({len(st.session_state.scanned_symbols)+1}/{len(tickers_to_scan)})")
            progress_bar.progress((len(st.session_state.scanned_symbols) + 1) / len(tickers_to_scan))
            try:
                metrics = compute_stock_metrics(sym, mode)
                if metrics is None:
                    st.session_state.failed_count += 1
                else:
                    st.session_state.high_prob.append(metrics)
                st.session_state.scanned_symbols.add(sym)
            except Exception as e:
                st.warning(f"{sym} 异常: {str(e)}")
                st.session_state.failed_count += 1
                st.session_state.scanned_symbols.add(sym)
            processed_in_this_run += 1
        if len(st.session_state.scanned_symbols) >= len(tickers_to_scan):
            st.session_state.fully_scanned = True
            st.session_state.scanning = False
            st.success("扫描完成！")
        st.rerun()

if st.session_state.fully_scanned:
    st.success("已完成全扫描！结果已全部更新")

if st.button("🔄 重置所有进度（从头开始）"):
    st.session_state.high_prob = []
    st.session_state.scanned_symbols = set()
    st.session_state.failed_count = 0
    st.session_state.fully_scanned = False
    st.session_state.scanning = False
    st.rerun()

st.caption("2026年1月完整最终版 | 完整罗素2000动态加载 | 所有列表完整无省略 | 极速稳定 | 直接复制使用")


