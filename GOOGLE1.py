import streamlit as st
import requests
import numpy as np
import time
import pandas as pd

st.set_page_config(page_title="短线扫描-完整连续版", layout="wide")
st.title("🚀 短线扫描工具（完整股票池连续扫描）")

# ==================== 完整的股票池 ====================
FULL_STOCK_POOL = [
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
    "NWS", "ADBE", "AMD", "ABNB", "ALNY", "GOOGL", "GOOG", "AMZN", "AEP", "AMGN", "ADI", "AAPL", "AMAT", "APP", "ARM", "ASML",
    "AZN", "TEAM", "ADSK", "ADP", "AXON", "BKR", "BKNG", "AVGO", "CDNS", "CHTR", "CTAS", "CSCO", "CCEP", "CTSH", "CMCSA",
    "CEG", "CPRT", "CSGP", "COST", "CRWD", "CSX", "DDOG", "DXCM", "FANG", "DASH", "EA", "EXC", "FAST", "FER", "FTNT",
    "GEHC", "GILD", "HON", "IDXX", "INSM", "INTC", "INTU", "ISRG", "KDP", "KLAC", "KHC", "LRCX", "LIN", "MAR", "MRVL",
    "MELI", "META", "MCHP", "MU", "MSFT", "MSTR", "MDLZ", "MPWR", "MNST", "NFLX", "NVDA", "NXPI", "ORLY", "ODFL", "PCAR",
    "PLTR", "PANW", "PAYX", "PYPL", "PDD", "PEP", "QCOM", "REGN", "ROP", "ROST", "STX", "SHOP", "SBUX", "SNPS", "TMUS",
    "TTWO", "TSLA", "TXN", "TRI", "VRSK", "VRTX", "WBD", "WDC", "WDAY", "XEL", "ZS", "SPY", "QQQ", "VOO", "IVV", "VTI", 
    "VUG", "SCHG", "IWM", "DIA", "SLV", "GLD", "GDX", "GDXJ", "SIL", "SLVP", "RING", "SGDJ", "SMH", "SOXX", "SOXL", 
    "TQQQ", "BITO", "MSTR", "ARKK", "XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP"
]

# 去重并排序
ALL_STOCKS = sorted(list(set(FULL_STOCK_POOL)))
st.write(f"**总股票数量**: {len(ALL_STOCKS)} 只")

# ==================== 核心算法 ====================
HEADERS = {"User-Agent": "Mozilla/5.0"}

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_stock_data(symbol):
    """获取股票数据"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1y&interval=1d"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        data = resp.json()
        
        if "chart" not in data or "result" not in data["chart"]:
            return None
            
        result = data["chart"]["result"][0]
        quote = result["indicators"]["quote"][0]
        
        # 提取收盘价
        close_prices = []
        for i in range(len(quote["close"])):
            if quote["close"][i] is not None:
                close_prices.append(quote["close"][i])
        
        if len(close_prices) < 60:
            return None
            
        return np.array(close_prices)
    except Exception as e:
        return None

def analyze_stock(symbol):
    """分析股票 - 使用第一段代码的科学算法"""
    close = fetch_stock_data(symbol)
    if close is None:
        return None
    
    price = close[-1]
    change = (close[-1] / close[-2] - 1) * 100 if len(close) >= 2 else 0
    
    # 使用更科学的算法（类似第一段代码）
    if len(close) > 100:
        # 1. 计算MACD
        def ema(x, span):
            alpha = 2 / (span + 1)
            result = np.empty_like(x)
            result[0] = x[0]
            for i in range(1, len(x)):
                result[i] = alpha * x[i] + (1 - alpha) * result[i-1]
            return result
        
        ema12 = ema(close, 12)
        ema26 = ema(close, 26)
        macd_line = ema12 - ema26
        signal_line = ema(macd_line, 9)
        macd_hist = macd_line - signal_line
        
        # 2. 计算RSI
        delta = np.diff(close, prepend=close[0])
        gain = np.where(delta > 0, delta, 0.0)
        loss = np.where(delta < 0, -delta, 0.0)
        avg_gain = ema(gain, 14)
        avg_loss = ema(loss, 14)
        rs = avg_gain / (avg_loss + 1e-9)
        rsi = 100 - (100 / (1 + rs))
        
        # 3. 移动平均
        def rolling_mean(x, window):
            if len(x) < window:
                return np.full_like(x, np.mean(x))
            return pd.Series(x).rolling(window=window, min_periods=1).mean().values
        
        ma20 = rolling_mean(close, 20)
        ma50 = rolling_mean(close, 50)
        
        # 4. 信号判断（5个指标）
        signal1 = macd_hist[-1] > 0  # MACD柱状图为正
        signal2 = close[-1] > ma20[-1] * 1.02  # 价格在20日线上方2%
        signal3 = rsi[-1] >= 60  # RSI >= 60
        signal4 = close[-1] > ma50[-1]  # 价格在50日线上方
        signal5 = change > 0  # 当日上涨
        
        score = sum([signal1, signal2, signal3, signal4, signal5])
        
        # 5. 回测计算（7日）
        if len(close) > 30:
            # 生成历史信号
            hist_signals = (
                (macd_hist > 0).astype(int) +
                (close > rolling_mean(close, 20) * 1.02).astype(int) +
                (rsi >= 60).astype(int) +
                (close > rolling_mean(close, 50)).astype(int)
            )
            
            # 找到信号点（score >= 3）
            idx = np.where(hist_signals[:-7] >= 3)[0]
            
            if len(idx) > 0:
                # 计算7日后回报
                returns = close[idx + 7] / close[idx] - 1
                win_rate = np.mean(returns > 0)
                
                # 计算PF7（与第一段代码相同）
                positive = returns[returns > 0]
                negative = returns[returns <= 0]
                
                if len(negative) > 0 and abs(negative.sum()) > 1e-9:
                    pf7 = positive.sum() / abs(negative.sum())
                else:
                    pf7 = 999.0 if len(positive) > 0 else 1.0
            else:
                win_rate = 0.5
                pf7 = 1.0
        else:
            win_rate = 0.5
            pf7 = 1.0
    else:
        # 数据不足时使用简化算法
        if len(close) > 20:
            ma20 = np.mean(close[-20:])
            ma5 = np.mean(close[-5:])
            
            signal1 = price > ma20
            signal2 = price > ma5
            signal3 = change > 0
            signal4 = ma5 > ma20
            signal5 = price > np.percentile(close[-30:], 70) if len(close) > 30 else True
            
            score = sum([signal1, signal2, signal3, signal4, signal5])
            
            # 简化回测
            returns = []
            for i in range(len(close) - 7):
                ret = close[i + 7] / close[i] - 1
                returns.append(ret)
            
            returns = np.array(returns)
            win_rate = np.mean(returns > 0)
            
            positive = returns[returns > 0]
            negative = returns[returns <= 0]
            
            if len(negative) > 0 and abs(negative.sum()) > 0.0001:
                pf7 = positive.sum() / abs(negative.sum())
            else:
                pf7 = 999 if len(positive) > 0 else 1
        else:
            score = 1
            win_rate = 0.5
            pf7 = 1.0
    
    return {
        'symbol': symbol,
        'price': price,
        'change': change,
        'score': score,
        'prob7': win_rate,
        'pf7': pf7,
        'data_points': len(close)
    }

# ==================== 连续扫描引擎 ====================
st.sidebar.header("⚙️ 设置")

# 选择扫描模式
scan_mode = st.sidebar.radio(
    "扫描模式",
    ["完整扫描所有股票", "自定义扫描范围", "仅扫描热门股票"]
)

if scan_mode == "自定义扫描范围":
    start_idx = st.sidebar.number_input("起始索引", 0, len(ALL_STOCKS)-1, 0)
    end_idx = st.sidebar.number_input("结束索引", 0, len(ALL_STOCKS)-1, min(49, len(ALL_STOCKS)-1))
    if end_idx < start_idx:
        end_idx = start_idx + 49
    stocks_to_scan = ALL_STOCKS[start_idx:end_idx+1]
elif scan_mode == "仅扫描热门股票":
    # 前50只热门股票
    stocks_to_scan = ALL_STOCKS[:50]
else:
    stocks_to_scan = ALL_STOCKS

st.write(f"**本次扫描**: {len(stocks_to_scan)} 只股票")

# 显示部分股票
if len(stocks_to_scan) <= 30:
    st.write("股票列表:", ", ".join(stocks_to_scan))
else:
    st.write("股票列表（前30只）:", ", ".join(stocks_to_scan[:30]) + "...")

# ==================== 关键：真正的连续扫描 ====================
# 初始化session state
if 'scan_data' not in st.session_state:
    st.session_state.scan_data = {
        'results': [],
        'completed': set(),
        'failed': set(),
        'is_scanning': False,
        'current_index': 0,
        'start_time': None,
        'batch_size': 10  # 每批扫描10只
    }

# 控制按钮
col1, col2, col3, col4 = st.columns(4)
with col1:
    start_btn = st.button("🚀 开始连续扫描", type="primary", use_container_width=True)
with col2:
    pause_btn = st.button("⏸️ 暂停", use_container_width=True)
with col3:
    resume_btn = st.button("▶️ 继续", use_container_width=True)
with col4:
    reset_btn = st.button("🔄 重置", use_container_width=True)

if start_btn:
    st.session_state.scan_data = {
        'results': [],
        'completed': set(),
        'failed': set(),
        'is_scanning': True,
        'current_index': 0,
        'start_time': time.time(),
        'batch_size': 10
    }

if pause_btn:
    st.session_state.scan_data['is_scanning'] = False

if resume_btn:
    st.session_state.scan_data['is_scanning'] = True

if reset_btn:
    st.session_state.scan_data = {
        'results': [],
        'completed': set(),
        'failed': set(),
        'is_scanning': False,
        'current_index': 0,
        'start_time': None,
        'batch_size': 10
    }
    st.rerun()

# ==================== 扫描引擎 ====================
def scan_engine():
    """扫描引擎 - 真正的连续扫描"""
    scan_data = st.session_state.scan_data
    
    if not scan_data['is_scanning']:
        return
    
    # 检查是否已完成所有股票
    if scan_data['current_index'] >= len(stocks_to_scan):
        scan_data['is_scanning'] = False
        return
    
    # 创建进度显示
    progress_container = st.empty()
    
    with progress_container.container():
        # 计算进度
        progress = scan_data['current_index'] / len(stocks_to_scan)
        st.progress(progress)
        
        # 计算预计剩余时间
        if scan_data['start_time']:
            elapsed = time.time() - scan_data['start_time']
            if scan_data['current_index'] > 0:
                time_per_stock = elapsed / scan_data['current_index']
                remaining = (len(stocks_to_scan) - scan_data['current_index']) * time_per_stock
                st.write(f"预计剩余时间: {remaining/60:.1f}分钟")
        
        st.write(f"扫描进度: {scan_data['current_index']}/{len(stocks_to_scan)}")
    
    # 扫描当前批次
    batch_size = scan_data['batch_size']
    batch_end = min(scan_data['current_index'] + batch_size, len(stocks_to_scan))
    
    results_container = st.empty()
    batch_results = []
    
    with results_container.container():
        for i in range(scan_data['current_index'], batch_end):
            symbol = stocks_to_scan[i]
            
            # 显示当前扫描状态
            st.write(f"正在扫描 {symbol} ({i+1}/{len(stocks_to_scan)})")
            
            # 扫描股票
            result = analyze_stock(symbol)
            
            if result:
                scan_data['results'].append(result)
                batch_results.append(result)
                scan_data['completed'].add(symbol)
                st.success(f"✓ {symbol}: 得分{result['score']}/5, PF7={result['pf7']:.2f}")
            else:
                scan_data['failed'].add(symbol)
                st.warning(f"✗ {symbol}: 数据获取失败")
            
            # 更新索引
            scan_data['current_index'] = i + 1
            
            # 短暂延迟避免API限制
            time.sleep(1.2)
        
        # 显示本批结果摘要
        if batch_results:
            st.info(f"✅ 批次完成，本批扫描 {len(batch_results)} 只股票")
    
    # 保存session state
    st.session_state.scan_data = scan_data
    
    # 如果还在扫描状态，继续下一批
    if scan_data['is_scanning'] and scan_data['current_index'] < len(stocks_to_scan):
        # 批次间稍长延迟
        time.sleep(2)
        st.rerun()
    elif scan_data['current_index'] >= len(stocks_to_scan):
        # 扫描完成
        scan_data['is_scanning'] = False
        st.session_state.scan_data = scan_data
        st.balloons()
        st.success("🎉 所有股票扫描完成！")

# 运行扫描引擎
if st.session_state.scan_data['is_scanning']:
    scan_engine()

# ==================== 结果显示 ====================
if st.session_state.scan_data['results']:
    st.subheader(f"📊 扫描结果 ({len(st.session_state.scan_data['results'])}/{len(stocks_to_scan)})")
    
    df = pd.DataFrame(st.session_state.scan_data['results'])
    
    # 筛选条件
    col_filter, col_sort = st.columns(2)
    with col_filter:
        filter_option = st.selectbox(
            "筛选条件",
            [
                "显示全部", 
                "优质(PF7≥3.6且胜率≥68%)", 
                "PF7≥3.6", 
                "胜率≥68%", 
                "得分≥4",
                "潜力股(PF7≥5.0)"
            ]
        )
    
    with col_sort:
        sort_option = st.selectbox(
            "排序方式",
            ["PF7降序", "胜率降序", "得分降序", "价格变化"]
        )
    
    # 应用筛选
    if filter_option == "优质(PF7≥3.6且胜率≥68%)":
        filtered_df = df[(df['pf7'] >= 3.6) & (df['prob7'] >= 0.68)]
    elif filter_option == "PF7≥3.6":
        filtered_df = df[df['pf7'] >= 3.6]
    elif filter_option == "胜率≥68%":
        filtered_df = df[df['prob7'] >= 0.68]
    elif filter_option == "得分≥4":
        filtered_df = df[df['score'] >= 4]
    elif filter_option == "潜力股(PF7≥5.0)":
        filtered_df = df[df['pf7'] >= 5.0]
    else:
        filtered_df = df
    
    # 应用排序
    if sort_option == "PF7降序":
        filtered_df = filtered_df.sort_values('pf7', ascending=False)
    elif sort_option == "胜率降序":
        filtered_df = filtered_df.sort_values('prob7', ascending=False)
    elif sort_option == "得分降序":
        filtered_df = filtered_df.sort_values('score', ascending=False)
    else:
        filtered_df = filtered_df.sort_values('change', ascending=False)
    
    # 显示结果
    if not filtered_df.empty:
        st.write(f"**找到 {len(filtered_df)} 只符合条件的股票**")
        
        # 分页显示
        page_size = 20
        total_pages = (len(filtered_df) + page_size - 1) // page_size
        page_number = st.number_input("页码", 1, total_pages, 1)
        
        start_idx = (page_number - 1) * page_size
        end_idx = min(page_number * page_size, len(filtered_df))
        
        for idx in range(start_idx, end_idx):
            row = filtered_df.iloc[idx]
            
            # 颜色编码
            score_color = "#00cc00" if row['score'] >= 4 else "#ff9900" if row['score'] >= 3 else "#ff4444"
            pf_color = "#00cc00" if row['pf7'] >= 5 else "#ff9900" if row['pf7'] >= 3 else "#ff4444"
            
            st.markdown(f"""
            <div style="border-left: 5px solid {score_color}; padding: 10px; margin: 5px 0; background: #f8f9fa;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <strong style="font-size: 16px;">{row['symbol']}</strong>
                        <span style="margin-left: 10px;">${row['price']:.2f} ({row['change']:+.2f}%)</span>
                    </div>
                    <div style="text-align: right;">
                        <span style="background-color: {score_color}; color: white; padding: 2px 8px; border-radius: 10px; margin-right: 8px; font-size: 12px;">
                            得分: {row['score']}/5
                        </span>
                        <span style="background-color: {pf_color}; color: white; padding: 2px 8px; border-radius: 10px; font-size: 12px;">
                            PF7: {row['pf7']:.2f}
                        </span>
                    </div>
                </div>
                <div style="margin-top: 4px; font-size: 13px; color: #666;">
                    胜率: <strong>{row['prob7']*100:.1f}%</strong>
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        # 统计信息
        st.write("---")
        col_stat1, col_stat2, col_stat3 = st.columns(3)
        with col_stat1:
            st.metric("平均PF7", f"{filtered_df['pf7'].mean():.2f}")
        with col_stat2:
            st.metric("平均胜率", f"{filtered_df['prob7'].mean()*100:.1f}%")
        with col_stat3:
            st.metric("平均得分", f"{filtered_df['score'].mean():.2f}")
        
        # SNDK特别分析
        if 'SNDK' in filtered_df['symbol'].values:
            st.write("---")
            st.subheader("🔬 SNDK详细对比")
            sndk_data = filtered_df[filtered_df['symbol'] == 'SNDK'].iloc[0]
            
            col_sndk1, col_sndk2, col_sndk3 = st.columns(3)
            with col_sndk1:
                st.metric("当前算法PF7", f"{sndk_data['pf7']:.2f}")
            with col_sndk2:
                st.metric("原始第一段代码", "7.53", delta=f"{sndk_data['pf7']-7.53:+.2f}")
            with col_sndk3:
                st.metric("原始第二段代码", "6.32", delta=f"{sndk_data['pf7']-6.32:+.2f}")
        
        # 导出功能
        st.write("---")
        if st.button("📥 导出CSV报告"):
            csv_data = filtered_df[['symbol', 'price', 'change', 'score', 'prob7', 'pf7']].copy()
            csv_data['prob7'] = (csv_data['prob7'] * 100).round(1)
            csv_str = csv_data.to_csv(index=False)
            
            st.download_button(
                "点击下载CSV",
                csv_str,
                f"stock_scan_results_{time.strftime('%Y%m%d_%H%M')}.csv",
                "text/csv"
            )
    
    else:
        st.warning("暂无符合筛选条件的股票")

# ==================== 状态面板 ====================
st.sidebar.write("---")
st.sidebar.subheader("📈 扫描状态")

scan_data = st.session_state.scan_data

if scan_data['is_scanning']:
    st.sidebar.info("🔄 扫描进行中...")
    progress = scan_data['current_index'] / len(stocks_to_scan)
    st.sidebar.progress(progress)
    st.sidebar.write(f"进度: {scan_data['current_index']}/{len(stocks_to_scan)}")
    st.sidebar.write(f"成功: {len(scan_data['results'])}")
    st.sidebar.write(f"失败: {len(scan_data['failed'])}")
elif scan_data['current_index'] > 0:
    if scan_data['current_index'] >= len(stocks_to_scan):
        st.sidebar.success("✅ 扫描完成")
    else:
        st.sidebar.warning("⏸️ 扫描已暂停")
    st.sidebar.write(f"已完成: {scan_data['current_index']}/{len(stocks_to_scan)}")
else:
    st.sidebar.info("⏳ 等待开始扫描")

# 显示失败股票
if scan_data['failed']:
    with st.sidebar.expander("查看失败股票"):
        failed_list = list(scan_data['failed'])
        st.write(", ".join(sorted(failed_list)[:20]))
        if len(failed_list) > 20:
            st.write(f"...等 {len(failed_list)} 只")

# 继续扫描按钮
if (scan_data['current_index'] < len(stocks_to_scan) and 
    not scan_data['is_scanning'] and 
    scan_data['current_index'] > 0):
    
    st.write("---")
    remaining = len(stocks_to_scan) - scan_data['current_index']
    st.write(f"### 继续扫描 ({remaining} 只股票待扫描)")
    
    if st.button("▶️ 继续扫描剩余股票"):
        scan_data['is_scanning'] = True
        st.session_state.scan_data = scan_data
        st.rerun()

# 使用说明
with st.expander("📖 使用说明"):
    st.markdown("""
    ### 🚀 真正的连续扫描工具
    
    **使用方法：**
    1. 选择扫描模式（推荐"完整扫描所有股票"）
    2. 点击 **"开始连续扫描"**
    3. 工具会自动连续扫描所有股票
    4. 可以随时暂停、继续或重置
    
    **特点：**
    - ✅ **真正连续**：一次点击，自动扫描直到完成
    - ✅ **完整股票池**：包含你提供的所有股票（500+只）
    - ✅ **科学算法**：使用与第一段代码相似的科学算法
    - ✅ **进度保存**：中途刷新不会丢失进度
    - ✅ **批量处理**：每批10只，效率高
    
    **扫描速度：**
    - 每只股票约1.2秒
    - 每批10只约12秒
    - 扫描100只股票约2分钟
    - 完整500+只股票约10分钟
    
    **注意：**
    - 扫描过程中可以刷新页面
    - 建议保持网络稳定
    - 扫描完成后会自动显示结果
    """)

st.caption(f"💡 点击'开始连续扫描'后，请等待工具自动完成所有 {len(stocks_to_scan)} 只股票的扫描。")
