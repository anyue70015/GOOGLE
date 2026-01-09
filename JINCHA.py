import streamlit as st
import requests
import numpy as np
import time
import pandas as pd
from io import StringIO
import concurrent.futures
import threading
from queue import Queue
import datetime

st.set_page_config(page_title="罗素2000 极品短线扫描工具", layout="wide")
st.title("罗素2000 短线扫描工具（PF7≥3.6 或 7日≥68%）")

# ==================== 核心常量 ====================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
}

BACKTEST_CONFIG = {
    "3个月": {"range": "3mo", "interval": "1d"},
    "6个月": {"range": "6mo", "interval": "1d"},
    "1年":  {"range": "1y",  "interval": "1d"},
    "2年":  {"range": "2y",  "interval": "1d"},
    "3年":  {"range": "3y",  "interval": "1d"},
    "5年":  {"range": "5y",  "interval": "1d"},
    "10年": {"range": "10y", "interval": "1d"},
}

# ==================== 实时扫描管理器 ====================
class RealTimeScanner:
    def __init__(self):
        self.results_queue = Queue()
        self.scanning_active = False
        self.current_symbol = ""
        self.last_update_time = time.time()
        self.update_interval = 0.5  # 更新间隔（秒）
        
    def start_scan(self, symbols):
        self.scanning_active = True
        self.symbols_to_scan = symbols.copy()
        self.scanned_count = 0
        self.total_count = len(symbols)
        
        # 启动扫描线程
        thread = threading.Thread(target=self._scan_thread, args=(symbols,))
        thread.daemon = True
        thread.start()
    
    def _scan_thread(self, symbols):
        """后台扫描线程"""
        for symbol in symbols:
            if not self.scanning_active:
                break
                
            self.current_symbol = symbol
            try:
                metrics = compute_stock_metrics(symbol, st.session_state.get('mode', '1年'))
                self.results_queue.put(('success', symbol, metrics))
            except Exception as e:
                self.results_queue.put(('error', symbol, str(e)))
            
            self.scanned_count += 1
            time.sleep(1)  # 避免请求过快
        
        self.results_queue.put(('complete', None, None))
    
    def get_updates(self):
        """获取最新的扫描结果"""
        updates = []
        while not self.results_queue.empty():
            updates.append(self.results_queue.get())
        return updates
    
    def stop_scan(self):
        self.scanning_active = False

# 初始化扫描器
if 'scanner' not in st.session_state:
    st.session_state.scanner = RealTimeScanner()

# ==================== 数据拉取 ====================
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_yahoo_ohlcv(yahoo_symbol: str, range_str: str, interval: str = "1d"):
    """获取雅虎财经OHLCV数据"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}?range={range_str}&interval={interval}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()["chart"]["result"][0]
        quote = data["indicators"]["quote"][0]
        close = np.array(quote["close"], dtype=float)
        high = np.array(quote["high"], dtype=float)
        low = np.array(quote["low"], dtype=float)
        volume = np.array(quote["volume"], dtype=float)
        
        mask = ~np.isnan(close)
        close, high, low, volume = close[mask], high[mask], low[mask], volume[mask]
        
        if len(close) < 100:
            raise ValueError("数据不足")
        return close, high, low, volume
    except Exception as e:
        raise ValueError(f"请求失败: {str(e)}")

# ==================== 指标函数（保持不变）====================
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
    tr = np.maximum(high - low, 
                   np.maximum(np.abs(high - prev_close), 
                             np.abs(low - prev_close)))
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
    gains = rets[rets > 0]
    losses = rets[rets <= 0]
    if len(losses) > 0:
        pf = abs(gains.sum() / losses.sum()) if len(gains) > 0 else 0
    else:
        pf = 999 if len(gains) > 0 else 0
    return win_rate, pf

# ==================== 核心计算 ====================
@st.cache_data(show_spinner=False)
def compute_stock_metrics(symbol: str, cfg_key: str = "1年"):
    """计算股票的各项指标"""
    yahoo_symbol = symbol.upper()
    
    try:
        close, high, low, volume = fetch_yahoo_ohlcv(
            yahoo_symbol, 
            BACKTEST_CONFIG[cfg_key]["range"]
        )
    except Exception as e:
        raise ValueError(f"数据获取失败: {str(e)}")
    
    macd_hist = macd_hist_np(close)
    rsi = rsi_np(close)
    atr = atr_np(high, low, close)
    obv = obv_np(close, volume)
    vol_ma20 = rolling_mean_np(volume, 20)
    atr_ma20 = rolling_mean_np(atr, 20)
    obv_ma20 = rolling_mean_np(obv, 20)
    
    sig_macd = int(macd_hist[-1] > 0)
    sig_vol = int(volume[-1] > vol_ma20[-1] * 1.1)
    sig_rsi = int(rsi[-1] >= 60)
    sig_atr = int(atr[-1] > atr_ma20[-1] * 1.1)
    sig_obv = int(obv[-1] > obv_ma20[-1] * 1.05)
    score = sig_macd + sig_vol + sig_rsi + sig_atr + sig_obv
    
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
        "price": round(price, 2),
        "change": round(change, 2),
        "score": score,
        "prob7": round(prob7, 4),
        "pf7": round(pf7, 2),
        "rsi": round(rsi[-1], 1),
        "scan_time": datetime.datetime.now().strftime("%H:%M:%S")
    }

# ==================== 加载成分股 ====================
@st.cache_data(ttl=86400)
def load_russell2000_tickers():
    """加载罗素2000成分股"""
    # 使用备用静态数据，避免网络问题
    try:
        # 尝试从iShares官方数据源
        url = "https://www.ishares.com/us/products/239710/ishares-russell-2000-etf/1467271812596.ajax?fileType=csv&fileName=IWM_holdings&dataType=fund"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        
        lines = resp.text.splitlines()
        start_idx = 0
        for i, line in enumerate(lines):
            if 'Ticker' in line and 'Name' in line:
                start_idx = i
                break
        
        csv_text = "\n".join(lines[start_idx:])
        df = pd.read_csv(StringIO(csv_text))
        
        ticker_col = 'Ticker' if 'Ticker' in df.columns else 'Symbol'
        tickers = df[ticker_col].dropna().astype(str).str.strip().tolist()
        tickers = [t for t in tickers if t != '-' and t != 'nan' and 1 <= len(t) <= 6]
        
        return sorted(set(tickers))
        
    except Exception as e:
        st.warning(f"使用备用数据源: {str(e)}")
        # 返回部分常见罗素2000股票作为示例
        return ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'JPM', 'V', 'JNJ', 
                'WMT', 'PG', 'HD', 'BAC', 'MA', 'DIS', 'NFLX', 'ADBE', 'CRM', 'PYPL',
                'ABT', 'PEP', 'CMCSA', 'TMO', 'AVGO', 'COST', 'DHR', 'MCD', 'NKE', 'LIN']

# ==================== 界面布局 ====================
# 初始化session state
if 'high_prob' not in st.session_state:
    st.session_state.high_prob = []
if 'failed_symbols' not in st.session_state:
    st.session_state.failed_symbols = []
if 'mode' not in st.session_state:
    st.session_state.mode = "1年"
if 'last_update' not in st.session_state:
    st.session_state.last_update = time.time()

# 加载股票列表
all_tickers = load_russell2000_tickers()

col1, col2, col3 = st.columns([2, 2, 1])

with col1:
    st.session_state.mode = st.selectbox("回测周期", list(BACKTEST_CONFIG.keys()), index=2)

with col2:
    sort_by = st.selectbox("结果排序方式", ["PF7 (盈利因子)", "7日概率", "综合得分", "最新扫描"], index=3)

with col3:
    auto_refresh = st.checkbox("实时刷新", value=True)

# 控制按钮区域
control_col1, control_col2, control_col3 = st.columns(3)

with control_col1:
    if st.button("▶️ 开始实时扫描", type="primary"):
        if not st.session_state.scanner.scanning_active:
            st.session_state.high_prob = []
            st.session_state.failed_symbols = []
            st.session_state.scanner.start_scan(all_tickers)
            st.rerun()

with control_col2:
    if st.button("⏸️ 暂停扫描"):
        st.session_state.scanner.stop_scan()
        st.rerun()

with control_col3:
    if st.button("🔄 重置进度"):
        st.session_state.high_prob = []
        st.session_state.failed_symbols = []
        st.session_state.scanner.stop_scan()
        st.session_state.scanner = RealTimeScanner()
        st.rerun()

# ==================== 实时进度显示 ====================
st.divider()

# 创建进度显示区域
progress_container = st.container()
results_container = st.container()

with progress_container:
    scanner = st.session_state.scanner
    
    if scanner.scanning_active:
        current_time = datetime.datetime.now().strftime("%H:%M:%S")
        col_prog1, col_prog2, col_prog3, col_prog4 = st.columns(4)
        
        with col_prog1:
            st.metric("🔄 扫描状态", "进行中", delta="实时")
        
        with col_prog2:
            progress = scanner.scanned_count / scanner.total_count if scanner.total_count > 0 else 0
            st.metric("📊 扫描进度", f"{scanner.scanned_count}/{scanner.total_count}")
            st.progress(progress)
        
        with col_prog3:
            current_symbol = scanner.current_symbol if scanner.current_symbol else "等待开始"
            st.metric("🔍 当前股票", current_symbol)
        
        with col_prog4:
            success_count = len(st.session_state.high_prob)
            st.metric("✅ 成功扫描", success_count)
        
        st.caption(f"最后更新: {current_time}")
    else:
        st.info("👆 点击'开始实时扫描'按钮开始扫描Russell 2000成分股")

# ==================== 实时结果更新逻辑 ====================
# 定期检查扫描结果
if auto_refresh or st.session_state.scanner.scanning_active:
    # 获取最新的扫描结果
    updates = st.session_state.scanner.get_updates()
    
    for update_type, symbol, data in updates:
        if update_type == 'success':
            st.session_state.high_prob.append(data)
        elif update_type == 'error':
            st.session_state.failed_symbols.append((symbol, data))
        elif update_type == 'complete':
            st.success(f"🎉 扫描完成！共扫描 {scanner.scanned_count} 只股票")
            st.session_state.scanner.scanning_active = False
    
    # 如果扫描正在进行中，设置自动刷新
    if st.session_state.scanner.scanning_active:
        time.sleep(0.5)
        st.rerun()
    elif updates:  # 如果有新结果，但扫描已停止
        st.rerun()

# ==================== 结果显示 ====================
with results_container:
    if st.session_state.high_prob:
        df_all = pd.DataFrame(st.session_state.high_prob)
        
        # 添加筛选条件滑块
        col_filter1, col_filter2 = st.columns(2)
        with col_filter1:
            min_pf7 = st.slider("最小PF7", 0.0, 10.0, 3.6, 0.1)
        with col_filter2:
            min_prob = st.slider("最小7日概率%", 0, 100, 68, 1) / 100
        
        # 筛选
        mask = (df_all['pf7'] >= min_pf7) | (df_all['prob7'] >= min_prob)
        filtered_df = df_all[mask].copy()
        
        if filtered_df.empty:
            st.warning(f"暂无满足条件的股票（PF7≥{min_pf7} 或 7日概率≥{min_prob*100}%）")
        else:
            # 格式化显示
            df_display = filtered_df.copy()
            df_display['price_display'] = df_display['price'].apply(lambda x: f"${x:,.2f}")
            df_display['change_display'] = df_display['change'].apply(lambda x: f"{x:+.2f}%")
            df_display['prob7_percent'] = (df_display['prob7'] * 100).round(1)
            df_display['prob7_display'] = df_display['prob7_percent'].apply(lambda x: f"{x:.1f}%")
            df_display['pf7_display'] = df_display['pf7'].apply(lambda x: f"{x:.2f}")
            
            # 根据排序方式排序
            if sort_by == "PF7 (盈利因子)":
                df_display = df_display.sort_values("pf7", ascending=False)
                sort_text = "PF7降序"
            elif sort_by == "7日概率":
                df_display = df_display.sort_values("prob7", ascending=False)
                sort_text = "7日概率降序"
            elif sort_by == "综合得分":
                df_display['composite'] = df_display['pf7'] * 0.7 + df_display['prob7'] * 0.3
                df_display = df_display.sort_values("composite", ascending=False)
                sort_text = "综合评分降序"
            else:  # 最新扫描
                df_display = df_display.sort_values("scan_time", ascending=False)
                sort_text = "最新扫描"
            
            # 显示结果
            st.subheader(f"📊 实时扫描结果 ({len(filtered_df)}/{len(df_all)} 符合条件) | 排序: {sort_text}")
            
            # 使用columns创建卡片式布局
            cols_per_row = 3
            items = df_display.to_dict('records')
            
            for i in range(0, len(items), cols_per_row):
                cols = st.columns(cols_per_row)
                for j in range(cols_per_row):
                    idx = i + j
                    if idx < len(items):
                        item = items[idx]
                        with cols[j]:
                            # 创建卡片
                            card_color = "green" if item['score'] >= 4 else "orange" if item['score'] >= 3 else "gray"
                            
                            st.markdown(f"""
                            <div style="border:1px solid {card_color}; border-radius:10px; padding:15px; margin:5px; background:#f9f9f9;">
                                <h4 style="margin:0; color:{card_color};">{item['symbol']}</h4>
                                <p style="margin:5px 0; font-size:18px;">
                                    <b>{item['price_display']}</b> <span style="color:{'green' if item['change'] >= 0 else 'red'}">{item['change_display']}</span>
                                </p>
                                <p style="margin:5px 0;">
                                    🎯 <b>得分: {item['score']}/5</b> | 
                                    📈 RSI: {item['rsi']}
                                </p>
                                <p style="margin:5px 0;">
                                    🔥 <b>PF7: {item['pf7_display']}</b> | 
                                    📊 7日概率: {item['prob7_display']}
                                </p>
                                <p style="margin:5px 0; font-size:12px; color:#666;">
                                    扫描时间: {item['scan_time']}
                                </p>
                            </div>
                            """, unsafe_allow_html=True)
            
            # 统计信息
            st.divider()
            col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
            
            with col_stat1:
                st.metric("平均PF7", f"{filtered_df['pf7'].mean():.2f}")
            with col_stat2:
                st.metric("平均7日概率", f"{filtered_df['prob7'].mean()*100:.1f}%")
            with col_stat3:
                st.metric("平均得分", f"{filtered_df['score'].mean():.1f}/5")
            with col_stat4:
                st.metric("失败次数", len(st.session_state.failed_symbols))
            
            # 导出功能
            if st.button("📥 导出CSV结果"):
                csv = df_display[['symbol', 'price', 'change', 'score', 'pf7', 'prob7', 'rsi', 'scan_time']].to_csv(index=False)
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                st.download_button(
                    label="下载CSV文件",
                    data=csv,
                    file_name=f"russell2000_real_time_{timestamp}.csv",
                    mime="text/csv"
                )

# ==================== 页脚信息 ====================
st.divider()
st.caption(f"""
**系统状态:** {'🟢 实时扫描中' if st.session_state.scanner.scanning_active else '🟡 待机中'} | 
**数据源:** Yahoo Finance | **最后扫描:** {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**提示:** 扫描期间请保持页面打开，实时结果将自动更新。
""")

# 添加JavaScript自动刷新（增强实时性）
if auto_refresh and st.session_state.scanner.scanning_active:
    st.markdown("""
    <script>
    // 每2秒自动刷新一次页面
    setTimeout(function(){
        window.location.reload();
    }, 2000);
    </script>
    """, unsafe_allow_html=True)
