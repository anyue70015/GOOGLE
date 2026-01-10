import streamlit as st
import yfinance as yf  # 替换 requests 为 yfinance，防限流更好
import numpy as np
import time
import pandas as pd
from io import StringIO
import random  # 加随机延时

st.set_page_config(page_title="标普500 + 纳斯达克100 + 热门ETF 极品短线扫描工具", layout="wide")
st.title("标普500 + 纳斯达克100 + 热门ETF 短线扫描工具（PF7≥3.6 或 7日≥68%）")

# ── 新增清缓存按钮 ──
if st.button("🔄 强制刷新所有数据（清缓存 + 重新扫描）"):
    st.cache_data.clear()
    st.session_state.high_prob = []
    st.session_state.scanned_symbols = set()
    st.session_state.failed_count = 0
    st.session_state.fully_scanned = False  # 重置扫描标志
    st.rerun()

st.write("点击上方按钮可强制获取最新数据（尤其在美股刚收盘后推荐使用）")

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
@st.cache_data(ttl=1800, show_spinner=False)  # 缓存延长到30分钟
def fetch_yahoo_ohlcv(yahoo_symbol: str, range_str: str, interval: str = "1d"):
    try:
        # 随机延时 10-18 秒防限流
        time.sleep(random.uniform(10, 18))
        
        ticker = yf.Ticker(yahoo_symbol)
        df = ticker.history(period=range_str, interval=interval, auto_adjust=True, prepost=False)
        if df.empty or len(df) < 100:
            raise ValueError("数据不足")
        close = df['Close'].values.astype(float)
        high = df['High'].values.astype(float)
        low = df['Low'].values.astype(float)
        volume = df['Volume'].values.astype(float)
        mask = ~np.isnan(close)
        close, high, low, volume = close[mask], high[mask], low[mask], volume[mask]
        return close, high, low, volume
    except Exception as e:
        raise ValueError(f"yfinance失败: {str(e)}")

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
    yahoo_symbol = symbol.upper()
    close, high, low, volume = fetch_yahoo_ohlcv(yahoo_symbol, BACKTEST_CONFIG[cfg_key]["range"])

    macd_hist = macd_hist_np(close)
    rsi = rsi_np(close)
    atr = atr_np(high, low, close)
    obv = obv_np(close, volume)
    vol_ma20 = rolling_mean_np(volume, 20)
    atr_ma20 = rolling_mean_np(atr, 20)
    obv_ma20 = rolling_mean_np(obv, 20)

    # 5个指标的具体判断 + 记录详情
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
        "sig_details": sig_details
    }

# ==================== 完整硬编码成分股 + 热门ETF ====================
@st.cache_data(ttl=86400)
def load_sp500_tickers():
    # 2025年12月完整S&P500成分股（503只，每行15个，共34行）
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

# 新增：GATE.io 交易量前200币种（基于2026年1月数据，常见top crypto ticker）
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

# 新增：OKX 交易量前200币种（基于2026年1月数据，常见top crypto ticker，部分与Gate重叠）
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

sp500 = load_sp500_tickers()
all_tickers = list(set(sp500 + ndx100 + extra_etfs + gate_top200 + okx_top200))
all_tickers.sort()

st.write(f"总计 {len(all_tickers)} 只（标普500 + 纳斯达克100 + 热门ETF + GATE & OKX top 200 币种） | 2026年1月最新")

mode = st.selectbox("回测周期", list(BACKTEST_CONFIG.keys()), index=2)
sort_by = st.selectbox("结果排序方式", ["PF7 (盈利因子)", "7日概率"], index=0)

if 'high_prob' not in st.session_state:
    st.session_state.high_prob = []
if 'scanned_symbols' not in st.session_state:
    st.session_state.scanned_symbols = set()
if 'failed_count' not in st.session_state:
    st.session_state.failed_count = 0
if 'fully_scanned' not in st.session_state:
    st.session_state.fully_scanned = False

result_container = st.container()
progress_bar = st.progress(0)
status_text = st.empty()

if st.session_state.high_prob:
    df_all = pd.DataFrame(st.session_state.high_prob)
    
    filtered_df = df_all[(df_all['pf7'] >= 3.6) | (df_all['prob7'] >= 0.68)].copy()
    
    if filtered_df.empty:
        st.warning("当前扫描中暂无满足 PF7≥3.6 或 7日概率≥68% 的股票，继续扫描中...")
    else:
        df_display = filtered_df.copy()
        df_display['price'] = df_display['price'].round(2)
        df_display['change'] = df_display['change'].apply(lambda x: f"{x:+.2f}%")
        df_display['prob7'] = (df_display['prob7'] * 100).round(1).map("{:.1f}%".format)
        df_display['pf7'] = df_display['pf7'].round(2)
        
        if sort_by == "PF7 (盈利因子)":
            df_display = df_display.sort_values("pf7", ascending=False)
        else:
            df_display = df_display.sort_values("prob7", ascending=False)
        
        with result_container:
            st.subheader(f"短线优质股票（PF7≥3.6 或 7日概率≥68%） 共 {len(df_display)} 只  |  排序：{sort_by}")
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
                    f"得分: {row['score']}/5 - "
                    f"{detail_str} - "
                    f"**7日概率: {row['prob7']}  |  PF7: {row['pf7']}**"
                )
        
        csv_data = df_display[['symbol', 'price', 'change', 'score', 'prob7', 'pf7']].to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📄 导出结果为 CSV",
            data=csv_data,
            file_name=f"短线优质股票_PF≥3.6_or_7日≥68%_{time.strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
        
        txt_lines = []
        txt_lines.append(f"短线优质股票扫描结果")
        txt_lines.append(f"扫描时间：{time.strftime('%Y-%m-%d %H:%M')}")
        txt_lines.append(f"筛选条件：PF7 ≥ 3.6  或  7日上涨概率 ≥ 68%")
        txt_lines.append(f"回测周期：{mode}  |  排序：{sort_by}")
        txt_lines.append(f"符合股票数量：{len(df_display)} 只")
        txt_lines.append("=" * 60)
        txt_lines.append("")
        
        for _, row in df_display.iterrows():
            txt_lines.append(
                f"{row['symbol']:6} | 价格 ${row['price']:8.2f}  {row['change']:>8} | "
                f"得分 {row['score']}/5 | "
                f"7日概率 {row['prob7']:>6}  |  PF7 {row['pf7']:>5}"
            )
        
        txt_content = "\n".join(txt_lines)
        
        st.download_button(
            label="📜 导出结果为 TXT（推荐，清晰对齐）",
            data=txt_content.encode('utf-8'),
            file_name=f"短线优质股票_PF≥3.6_or_7日≥68%_{time.strftime('%Y%m%d')}.txt",
            mime="text/plain"
        )
        
        with st.expander("🔍 TXT 预览"):
            st.text(txt_content)

st.info(f"已扫描: {len(st.session_state.scanned_symbols)}/{len(all_tickers)} | 失败: {st.session_state.failed_count} | 优质股票: {len([x for x in st.session_state.high_prob if x['pf7']>=3.6 or x['prob7']>=0.68])}")

# 改成按钮触发扫描，避免部署时自动跑循环卡死
if not st.session_state.fully_scanned:
    if st.button("🚀 开始/继续全量扫描（时间较长，保持页面打开）"):
        with st.spinner("自动扫描中（保持页面打开，不要关闭）..."):
            for sym in all_tickers:
                if sym in st.session_state.scanned_symbols:
                    continue
                status_text.text(f"正在计算 {sym} ({len(st.session_state.scanned_symbols)+1}/{len(all_tickers)})")
                progress_bar.progress((len(st.session_state.scanned_symbols) + 1) / len(all_tickers))
                try:
                    metrics = compute_stock_metrics(sym, mode)
                    st.session_state.scanned_symbols.add(sym)
                    st.session_state.high_prob.append(metrics)
                    st.rerun()
                except Exception as e:
                    st.session_state.failed_count += 1
                    st.warning(f"{sym} 失败: {str(e)}")
                    st.session_state.scanned_symbols.add(sym)
                # 加大延时到12秒
                time.sleep(12)
            st.session_state.fully_scanned = True
            st.success("所有股票扫描完成！结果已更新")
            st.rerun()
else:
    st.success("已完成全扫描！如需重新扫描，请点击上方强制刷新按钮。")

if st.button("🔄 重置所有进度（从头开始）"):
    st.session_state.high_prob = []
    st.session_state.scanned_symbols = set()
    st.session_state.failed_count = 0
    st.session_state.fully_scanned = False
    st.rerun()

st.caption("2026年1月完整修复版 | 完整534只硬编码 | 已加入热门ETF + 加密币 | PF7≥3.6 或 7日≥68% | 防限流 + 按钮触发 | 稳定运行")
