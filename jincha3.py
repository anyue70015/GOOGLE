import streamlit as st
import yfinance as yf
import numpy as np
import time
import pandas as pd
import random

st.set_page_config(page_title="标普500 + 纳斯达克100 + 热门ETF + 加密币 短线扫描工具", layout="wide")
st.title("标普500 + 纳斯达克100 + 热门ETF + 加密币 短线扫描工具")

# ── 新增清缓存按钮 ──
if st.button("🔄 强制刷新所有数据（清缓存 + 重新扫描）"):
    st.cache_data.clear()
    st.session_state.high_prob = []
    st.session_state.scanned_symbols = set()
    st.session_state.failed_count = 0
    st.session_state.fully_scanned = False
    st.session_state.scanning = False
    st.rerun()

st.write("点击下方「开始扫描」按钮后，扫描会自动持续进行（每50只刷新一次页面，确保进度实时同步，不会停）。速度约每只3-6秒，总800+只约需40-80分钟。请保持页面打开，不要关闭。")

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
        time.sleep(random.uniform(3, 6))  # 稳定速度，防限流
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
    except Exception as e:
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

# (ndx100, extra_etfs, gate_top200, okx_top200 保持你原来的完整列表，这里省略以节省空间，直接复制你原来的)

# 定义加密币集合
crypto_tickers = list(set(gate_top200 + okx_top200))
crypto_set = set(c.upper() for c in crypto_tickers)

sp500 = load_sp500_tickers()
all_tickers = list(set(sp500 + ndx100 + extra_etfs + crypto_tickers))
all_tickers.sort()

st.write(f"总计 {len(all_tickers)} 只（标普500 + 纳斯达克100 + 热门ETF + 加密币） | 2026年1月最新")

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
# (保持原来的显示逻辑，股票优质 + 加密币全部)

st.info(f"已扫描: {len(st.session_state.scanned_symbols)}/{len(all_tickers)} | 失败/跳过: {st.session_state.failed_count} | 已获取结果: {len(st.session_state.high_prob)}")

# ==================== 扫描逻辑（核心修复：使用scanning标志持续运行） ====================
if st.button("🚀 开始/继续全量扫描（点击后自动持续运行，不会停）"):
    st.session_state.scanning = True

if st.session_state.scanning and not st.session_state.fully_scanned:
    with st.spinner("扫描进行中（每50只刷新一次页面）..."):
        batch_size = 50
        processed_in_this_run = 0
        for sym in all_tickers:
            if processed_in_this_run >= batch_size:
                break
            if sym in st.session_state.scanned_symbols:
                continue
            status_text.text(f"正在计算 {sym} ({len(st.session_state.scanned_symbols)+1}/{len(all_tickers)})")
            progress_bar.progress((len(st.session_state.scanned_symbols) + 1) / len(all_tickers))
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
        if len(st.session_state.scanned_symbols) >= len(all_tickers):
            st.session_state.fully_scanned = True
            st.session_state.scanning = False
            st.success("扫描完成！")
        st.rerun()  # 每50只rerun，继续下一批

if st.session_state.fully_scanned:
    st.success("已完成全扫描！结果已全部更新")

if st.button("🔄 重置所有进度（从头开始）"):
    st.session_state.high_prob = []
    st.session_state.scanned_symbols = set()
    st.session_state.failed_count = 0
    st.session_state.fully_scanned = False
    st.session_state.scanning = False
    st.rerun()

st.caption("2026年1月持续运行版 | 点击开始后自动每50只一批持续跑完 | 不会停在10或50 | 稳定防卡 | 加密币全显示")
