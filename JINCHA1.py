import streamlit as st
import yfinance as yf
import numpy as np
import time
import pandas as pd
import random
import requests
from io import StringIO
import concurrent.futures
from queue import Queue
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import requests.exceptions

st.set_page_config(page_title="标普500 + 纳斯达克100 + 热门ETF + 加密币 + 罗素2000 短线扫描工具", layout="wide")
st.title("标普500 + 纳斯达克100 + 热门ETF + 加密币 + 罗素2000 短线扫描工具")

# 清缓存按钮
if st.button("🔄 强制刷新所有数据（清缓存 + 重新扫描）"):
    st.cache_data.clear()
    st.session_state.high_prob = []
    st.session_state.scanned_symbols = set()
    st.session_state.failed_count = 0
    st.session_state.fully_scanned = False
    st.session_state.scanning = False
    st.rerun()

st.write("支持完整罗素2000（动态加载）。并发多线程加速。流动性过滤已改为**近1个月日均交易额 < 5000万美元**。")

# 扫描范围选择
scan_mode = st.selectbox("选择扫描范围", 
                         ["全部", "只扫币圈", "只扫美股大盘 (标普500 + 纳斯达克100 + ETF)", "只扫罗素2000 (完整~2000只)"])

# 动态加载罗素2000
@st.cache_data(ttl=86400)
def load_russell2000_tickers():
    url = "https://www.ishares.com/us/products/239710/ishares-russell-2000-etf/1467271812596.ajax?fileType=csv&fileName=IWM_holdings&dataType=fund"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"}
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        df = pd.read_csv(StringIO(resp.text), skiprows=9)
        if 'Ticker' not in df.columns:
            st.error("CSV格式变化，使用备用")
            return ["IWM"]
        tickers = df['Ticker'].dropna().astype(str).tolist()
        tickers = [t.strip().upper() for t in tickers if t.strip() != '-' and t.strip() != 'TICKER' and len(t.strip()) <= 5 and t.strip().isalnum()]
        tickers = list(set(tickers))
        st.success(f"罗素2000加载成功：{len(tickers)} 只")
        return tickers
    except Exception as e:
        st.error(f"加载失败: {e}，使用IWM")
        return ["IWM"]

# 回测周期配置（只用days，用于切片）
BACKTEST_CONFIG = {
    "3个月": {"days": 90},
    "6个月": {"days": 180},
    "1年":  {"days": 365},
    "2年":  {"days": 730},
    "3年":  {"days": 1095},
    "5年":  {"days": 1825},
    "10年": {"days": 3650},
}

# 数据拉取（加重试 + 缩短sleep）
@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=3, max=45),
    retry=retry_if_exception_type((requests.exceptions.RequestException, Exception)),
    reraise=True
)
@st.cache_data(ttl=1800, show_spinner=False)
def fetch_long_history(yahoo_symbol: str):
    try:
        time.sleep(random.uniform(0.6, 1.8))  # 缩短sleep，配合并发
        ticker = yf.Ticker(yahoo_symbol)
        df = ticker.history(period="5y", interval="1d", auto_adjust=True, prepost=False, timeout=15)
        if df.empty or len(df) < 100:
            return None
        return df.dropna(subset=['Close', 'High', 'Low', 'Volume'])
    except Exception:
        return None

# 指标函数（不变）
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

# 核心计算（流动性过滤改为近1个月）
@st.cache_data(show_spinner=False)
def compute_stock_metrics(symbol: str, cfg_key: str = "1年"):
    is_crypto = symbol.upper() in crypto_set
    yahoo_symbol = f"{symbol.upper()}-USD" if is_crypto else symbol.upper()
    
    df_long = fetch_long_history(yahoo_symbol)
    if df_long is None:
        return None
    
    days = BACKTEST_CONFIG[cfg_key]["days"]
    min_len = days + 60
    if len(df_long) < min_len:
        return None
    df = df_long.tail(min_len)
    
    close = df['Close'].values.astype(float)
    high = df['High'].values.astype(float)
    low = df['Low'].values.astype(float)
    volume = df['Volume'].values.astype(float)
    
    # 改动：近1个月平均日交易额（约30个交易日）
    recent_df = df_long.tail(30)
    if len(recent_df) < 15:  # 太少数据，不考虑
        return None
    avg_daily_dollar_vol_recent = (recent_df['Volume'] * recent_df['Close']).mean()
    if avg_daily_dollar_vol_recent < 50_000_000:
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
        "is_crypto": is_crypto
    }

# 完整成分股列表（sp500 + ndx100 + etfs + crypto）
sp500 = [
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
    "ZTS", "LHX", "APD", "IDXX", "VST", "ALL", "DLR", "F", "MET", "URI", "O", "PSX", "EA", "D", "VLO",
    "CMG", "CAH", "MPC", "CBRE", "GWW", "ROP", "DDOG", "AME", "FAST", "TTWO", "AIG", "AMP", "AXON", "DAL", "OKE",
    "PSA", "CTVA", "MPWR", "CARR", "TGT", "ROK", "LVS", "BKR", "XEL", "MSCI", "EXC", "DHI", "YUM", "FANG", "FICO",
    "ETR", "CTSH", "PAYX", "CCL", "PEG", "KR", "PRU", "GRMN", "TRGP", "OXY", "A", "MLM", "VMC", "EL", "HIG",
    "IQV", "EBAY", "CCI", "KDP", "GEHC", "NUE", "CPRT", "WAB", "VTR", "HSY", "ARES", "STT", "UAL", "FISV",
    "ED", "RMD", "SYY", "KEYS", "EXPE", "MCHP", "FIS", "ACGL", "PCG", "WEC", "OTIS", "FIX", "LYV", "XYL", "EQT",
    "KMB", "ODFL", "KVUE", "HPE", "RJF", "IR", "WTW", "FITB", "MTB", "TER", "HUM", "SYF", "NRG", "VRSK", "DG",
    "VICI", "IBKR", "ROL", "MTD", "FSLR", "KHC", "CSGP", "EME", "HBAN", "ADM", "EXR", "BRO", "DOV", "ATO", "EFX",
    "TSCO", "AEE", "ULTA", "TPR", "WRB", "CHTR", "CBOE", "DTE", "BR", "NTRS", "DXCM", "BIIB", "PPL", "AVB",
    "FE", "LEN", "CINF", "CFG", "STLD", "AWK", "VLTO", "ES", "JBL", "OMC", "GIS", "STE", "CNP", "DLTR", "LULU",
    "RF", "TDY", "STZ", "IRM", "HUBB", "EQR", "LDOS", "HAL", "PPG", "PHM", "KEY", "WAT", "EIX", "TROW", "VRSN",
    "WSM", "DVN", "ON", "L", "DRI", "NTAP", "RL", "CPAY", "HPQ", "LUV", "CMS", "IP", "LH", "PTC", "TSN",
    "SBAC", "CHD", "EXPD", "PODD", "SW", "NVR", "CNC", "TYL", "TPL", "NI", "WST", "INCY", "PFG", "CTRA", "DGX",
    "CHRW", "AMCR", "TRMB", "GPN", "JBHT", "PKG", "TTD", "MKC", "SNA", "SMCI", "IT", "CDW", "ZBH", "FTV", "ALB",
    "GPC", "LII", "PNR", "DD", "IFF", "BG", "GDDY", "TKO", "GEN", "WY", "ESS", "INVH", "LNT", "EVRG",
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
    "POWR", "POLS", "ALPHA", "FOR", "FIDA", "RAY", "STEP", "TORN", "TRIBE", "AKRO", "MLN", "GTC", "KAR", "BNC",
    "HARD", "DDX", "CREAM", "QUICK", "CQT", "SUKU", "RLY", "RAD", "FARM", "CLV", "ALCX", "MASK", "TOKE", "YLD", "DNT",
    "CELL", "DODO", "SWAP", "BNT", "KEEP", "NU", "TBTC", "LON", "REQ", "MIR", "KP3R", "BANCOR", "PNT", "WHALE", "SRM",
    "TRU", "PDEX", "BZRX", "HEGIC", "ESD", "BAC", "MTA", "VALUE", "YAX", "AMPL", "CVP", "RGT", "YAM", "SASHIMI",
    "YFV", "OMG", "DAI", "USDC", "TUSD", "PAX", "BUSD", "HUSD", "EURT", "XAUT", "DG"
]

crypto_tickers = list(set(gate_top200))
crypto_set = set(c.upper() for c in crypto_tickers)

stock_etf_tickers = list(set(sp500 + ndx100 + extra_etfs))

all_tickers = list(set(stock_etf_tickers + crypto_tickers))
all_tickers.sort()

# 设置扫描列表
if scan_mode == "全部":
    tickers_to_scan = all_tickers
    st.write(f"扫描范围：全部（{len(all_tickers)} 只）")
elif scan_mode == "只扫币圈":
    tickers_to_scan = crypto_tickers
    st.write(f"扫描范围：币圈（{len(crypto_tickers)} 只）")
elif scan_mode == "只扫美股大盘 (标普500 + 纳斯达克100 + ETF)":
    tickers_to_scan = stock_etf_tickers
    st.write(f"扫描范围：美股大盘（{len(stock_etf_tickers)} 只）")
elif scan_mode == "只扫罗素2000 (完整~2000只)":
    tickers_to_scan = load_russell2000_tickers()
    st.write(f"扫描范围：罗素2000（{len(tickers_to_scan)} 只）")

mode = st.selectbox("回测周期", list(BACKTEST_CONFIG.keys()), index=2)
sort_by = st.selectbox("排序方式", ["PF7 (盈利因子)", "7日概率"], index=0)

# session_state
for k in ['high_prob', 'scanned_symbols', 'failed_count', 'fully_scanned', 'scanning']:
    if k not in st.session_state:
        if k == 'high_prob':
            st.session_state[k] = []
        elif k == 'scanned_symbols':
            st.session_state[k] = set()
        elif k == 'failed_count':
            st.session_state[k] = 0
        else:
            st.session_state[k] = False

progress_bar = st.progress(0)
status_text = st.empty()

# 显示结果
if st.session_state.high_prob:
    df_all = pd.DataFrame([x for x in st.session_state.high_prob if x is not None])
    
    if not df_all.empty:
        stock_df = df_all[~df_all['is_crypto']].copy()
        crypto_df = df_all[df_all['is_crypto']].copy()
        
        super_stock = stock_df[(stock_df['pf7'] > 4.0) & (stock_df['prob7'] > 0.70)].copy()
        normal_stock = stock_df[((stock_df['pf7'] >= 3.6) | (stock_df['prob7'] >= 0.68)) & ~stock_df['symbol'].isin(super_stock['symbol'])].copy()
        
        super_crypto = crypto_df[(crypto_df['pf7'] > 4.0) & (crypto_df['prob7'] > 0.70)].copy()
        normal_crypto = crypto_df[(crypto_df['prob7'] > 0.5) & ~crypto_df['symbol'].isin(super_crypto['symbol'])].copy()
        
        def format_and_sort(df):
            df = df.copy()
            df['price'] = df['price'].round(2)
            df['change'] = df['change'].apply(lambda x: f"{x:+.2f}%")
            df['prob7_fmt'] = (df['prob7'] * 100).round(1).map("{:.1f}%".format)
            df['pf7'] = df['pf7'].round(2)
            if sort_by == "PF7 (盈利因子)":
                df = df.sort_values("pf7", ascending=False)
            else:
                df = df.sort_values("prob7", ascending=False)
            return df
        
        if not super_stock.empty:
            df_s = format_and_sort(super_stock)
            st.subheader(f"🔥 超级优质股票（PF>4 & 7日>70%） {len(df_s)} 只")
            for _, row in df_s.iterrows():
                d = row['sig_details']
                detail_str = " | ".join([f"{k}:{'是' if v else '否'}" for k,v in d.items()])
                st.markdown(f"**🔥 {row['symbol']}** - ${row['price']:.2f} ({row['change']}) - 得分{row['score']}/5 - {detail_str} - **7日{row['prob7_fmt']} | PF{row['pf7']}**")
        
        if not normal_stock.empty:
            df_n = format_and_sort(normal_stock)
            st.subheader(f"🔹 优质股票 {len(df_n)} 只")
            for _, row in df_n.iterrows():
                d = row['sig_details']
                detail_str = " | ".join([f"{k}:{'是' if v else '否'}" for k,v in d.items()])
                st.markdown(f"**{row['symbol']}** - ${row['price']:.2f} ({row['change']}) - 得分{row['score']}/5 - {detail_str} - **7日{row['prob7_fmt']} | PF{row['pf7']}**")
        
        if not super_crypto.empty:
            df_sc = format_and_sort(super_crypto)
            st.subheader(f"🔥 超级优质加密 {len(df_sc)} 只")
            for _, row in df_sc.iterrows():
                d = row['sig_details']
                detail_str = " | ".join([f"{k}:{'是' if v else '否'}" for k,v in d.items()])
                st.markdown(f"**🔥 {row['symbol']}** - ${row['price']:.2f} ({row['change']}) - 得分{row['score']}/5 - {detail_str} - **7日{row['prob7_fmt']} | PF{row['pf7']}**")
        
        if not normal_crypto.empty:
            df_nc = format_and_sort(normal_crypto)
            st.subheader(f"🔹 优质加密 {len(df_nc)} 只")
            for _, row in df_nc.iterrows():
                d = row['sig_details']
                detail_str = " | ".join([f"{k}:{'是' if v else '否'}" for k,v in d.items()])
                st.markdown(f"**{row['symbol']}** - ${row['price']:.2f} ({row['change']}) - 得分{row['score']}/5 - {detail_str} - **7日{row['prob7_fmt']} | PF{row['pf7']}**")
        
        if not (super_stock.empty and normal_stock.empty and super_crypto.empty and normal_crypto.empty):
            pass
        else:
            st.warning("暂无满足条件的标的")

st.info(f"总标的 {len(tickers_to_scan)} | 已扫描 {len(st.session_state.scanned_symbols)} | 有结果 {len(st.session_state.high_prob)} | 失败/低流动性 {st.session_state.failed_count}")

# 并发扫描
if st.button("🚀 开始/继续扫描"):
    st.session_state.scanning = True

if st.session_state.scanning and not st.session_state.fully_scanned:
    with st.spinner("并发扫描中..."):
        remaining = [s for s in tickers_to_scan if s not in st.session_state.scanned_symbols]
        if not remaining:
            st.session_state.fully_scanned = True
            st.session_state.scanning = False
            st.success("完成！")
            st.rerun()

        batch = remaining[:250]  # 更大批次
        q = Queue()
        processed = 0

        def task(sym):
            nonlocal processed
            try:
                m = compute_stock_metrics(sym, mode)
                q.put((sym, m))
            except:
                q.put((sym, None))
            finally:
                processed += 1

        with concurrent.futures.ThreadPoolExecutor(max_workers=15) as ex:  # 提高到15
            list(ex.map(task, batch))  # 简化写法，阻塞等待本批完成

        # 收集本批结果
        while not q.empty():
            sym, metrics = q.get()
            st.session_state.scanned_symbols.add(sym)
            if metrics:
                st.session_state.high_prob.append(metrics)
            else:
                st.session_state.failed_count += 1

        progress_bar.progress(len(st.session_state.scanned_symbols) / len(tickers_to_scan))
        status_text.text(f"进度 {len(st.session_state.scanned_symbols)} / {len(tickers_to_scan)}")
        st.rerun()

if st.session_state.fully_scanned:
    st.success("扫描全部完成")

if st.button("重置进度"):
    st.session_state.high_prob = []
    st.session_state.scanned_symbols = set()
    st.session_state.failed_count = 0
    st.session_state.fully_scanned = False
    st.session_state.scanning = False
    st.rerun()

st.caption("2026-01-15 最终优化版 | 近1个月流动性过滤 | 并发15线程 + 缩短sleep | 直接运行")
