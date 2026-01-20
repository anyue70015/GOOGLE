import streamlit as st
import numpy as np
import time
import pandas as pd
import random
import akshare as ak
import yfinance as yf
import os
import json
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# 设置页面配置
st.set_page_config(page_title="科创板 + 创业板短线扫描工具", layout="wide")
st.title("科创板 + 创业板短线扫描工具 (yFinance数据源完整版)")

# ==================== 配置常量 ====================
BACKTEST_CONFIG = {
    "3个月": {"days": 90},
    "6个月": {"days": 180},
    "1年": {"days": 365},
    "2年": {"days": 730},
}

# 进度文件路径
PROGRESS_FILE = "kcb_cyb_scan_progress_yf.json"
CACHE_DIR = ".cache"

# 创建缓存目录
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

# ==================== 初始化session_state ====================
def init_session_state():
    """初始化所有session_state变量"""
    defaults = {
        'high_prob': [],
        'scanned_symbols': set(),
        'failed_count': 0,
        'fully_scanned': False,
        'scanning': False,
        'paused': False,
        'progress_loaded': False,
        'scan_start_time': None,
        'total_scanned': 0
    }
    
    for key, value in defaults.items():
        if key not in st.session_state:
            if isinstance(value, set):
                st.session_state[key] = value.copy()
            else:
                st.session_state[key] = value

init_session_state()

# ==================== 进度管理 ====================
def load_progress():
    """加载扫描进度"""
    if os.path.exists(PROGRESS_FILE) and not st.session_state.progress_loaded:
        try:
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            st.session_state.high_prob = data.get("high_prob", [])
            st.session_state.scanned_symbols = set(data.get("scanned_symbols", []))
            st.session_state.failed_count = data.get("failed_count", 0)
            st.session_state.fully_scanned = data.get("fully_scanned", False)
            st.session_state.total_scanned = data.get("total_scanned", 0)
            st.session_state.progress_loaded = True
            
            st.success(f"已加载历史进度：已扫描 {len(st.session_state.scanned_symbols)} 只股票")
            return True
        except Exception as e:
            st.warning(f"进度加载失败: {e}，将重新开始扫描")
    return False

def save_progress():
    """保存扫描进度"""
    try:
        data = {
            "high_prob": st.session_state.high_prob,
            "scanned_symbols": list(st.session_state.scanned_symbols),
            "failed_count": st.session_state.failed_count,
            "fully_scanned": st.session_state.fully_scanned,
            "total_scanned": st.session_state.total_scanned,
            "last_saved": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        temp_file = f"{PROGRESS_FILE}.tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        os.replace(temp_file, PROGRESS_FILE)
        return True
    except Exception as e:
        st.error(f"进度保存失败: {e}")
        return False

# 加载历史进度
load_progress()

# ==================== 控制面板 ====================
st.markdown("---")
col1, col2, col3, col4 = st.columns(4)

with col1:
    if st.button("🔄 清缓存 & 重新开始", use_container_width=True):
        st.cache_data.clear()
        for file in os.listdir(CACHE_DIR):
            try:
                os.remove(os.path.join(CACHE_DIR, file))
            except:
                pass
        
        st.session_state.high_prob = []
        st.session_state.scanned_symbols = set()
        st.session_state.failed_count = 0
        st.session_state.fully_scanned = False
        st.session_state.scanning = False
        st.session_state.paused = False
        st.session_state.total_scanned = 0
        
        if os.path.exists(PROGRESS_FILE):
            os.remove(PROGRESS_FILE)
        
        st.rerun()

with col2:
    if st.button("📊 仅显示结果", use_container_width=True):
        st.session_state.scanning = False
        st.session_state.paused = False
        st.rerun()

with col3:
    if st.session_state.scanning and not st.session_state.paused:
        if st.button("⏸️ 暂停扫描", use_container_width=True):
            st.session_state.paused = True
            save_progress()
            st.rerun()

with col4:
    if st.session_state.paused:
        if st.button("▶️ 继续扫描", use_container_width=True):
            st.session_state.paused = False
            st.rerun()

st.markdown("---")

# ==================== 股票池加载 ====================
@st.cache_data(ttl=1800, show_spinner="正在加载股票列表...")
def load_stock_pool():
    """加载科创板(688)和创业板(300)的股票池"""
    try:
        st.info("正在从AKShare获取实时行情数据...")
        
        # 获取全市场实时行情
        df = ak.stock_zh_a_spot_em()
        if df.empty:
            st.error("无法获取行情数据")
            return [], {}
        
        # 数据清洗和格式化
        df['代码'] = df['代码'].astype(str).str.zfill(6)
        df['名称'] = df['名称'].astype(str)
        df['成交额'] = pd.to_numeric(df['成交额'], errors='coerce').fillna(0)
        
        # 筛选科创板和创业板
        mask_kcb = df['代码'].str.startswith('688')
        mask_cyb = df['代码'].str.startswith('300')
        
        df_kcb = df[mask_kcb].copy()
        df_cyb = df[mask_cyb].copy()
        
        # 按成交额排序并取前300名
        if not df_kcb.empty:
            df_kcb = df_kcb.sort_values('成交额', ascending=False).head(300)
        if not df_cyb.empty:
            df_cyb = df_cyb.sort_values('成交额', ascending=False).head(300)
        
        # 合并
        df_combined = pd.concat([df_kcb, df_cyb], ignore_index=True)
        
        if df_combined.empty:
            st.error("未找到符合条件的股票")
            return [], {}
        
        # 提取代码和名称
        tickers = df_combined['代码'].tolist()
        names = dict(zip(df_combined['代码'], df_combined['名称']))
        
        st.success(f"成功加载 {len(tickers)} 只股票（科创板: {len(df_kcb)}只, 创业板: {len(df_cyb)}只）")
        
        return tickers, names
        
    except Exception as e:
        st.error(f"加载股票池失败: {str(e)}")
        # 返回一些示例股票作为后备
        sample_tickers = ["688981", "300750", "688111", "300059", "688126", "300760"]
        sample_names = {
            "688981": "中芯国际", "300750": "宁德时代",
            "688111": "金山办公", "300059": "东方财富",
            "688126": "沪硅产业", "300760": "迈瑞医疗"
        }
        return sample_tickers, sample_names

# 加载股票池
tickers_to_scan, stock_names = load_stock_pool()

if not tickers_to_scan:
    st.error("无法加载股票列表，请检查网络连接后重试")
    st.stop()

st.markdown(f"**扫描范围**: {len(tickers_to_scan)} 只股票（科创板 + 创业板成交额前300）")

# ==================== yfinance数据获取 ====================
def get_yfinance_symbol(symbol):
    """将A股代码转换为yfinance格式"""
    if symbol.startswith('6'):
        return f"{symbol}.SS"  # 上海交易所
    elif symbol.startswith('3') or symbol.startswith('0'):
        return f"{symbol}.SZ"  # 深圳交易所
    else:
        return symbol

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_stock_data_yf(symbol, period_days):
    """
    使用yfinance获取股票历史数据
    返回: (close_prices, high_prices, low_prices, volumes, success_flag, error_msg)
    """
    try:
        yf_symbol = get_yfinance_symbol(symbol)
        
        # 计算开始日期（增加60天缓冲）
        end_date = datetime.now()
        start_date = end_date - timedelta(days=period_days + 60)
        
        # yfinance的period参数
        if period_days <= 90:
            period = "3mo"
        elif period_days <= 180:
            period = "6mo"
        elif period_days <= 365:
            period = "1y"
        else:
            period = "2y"
        
        # 下载数据
        ticker = yf.Ticker(yf_symbol)
        df = ticker.history(period=period, interval="1d")
        
        if df.empty or len(df) < 30:
            return None, None, None, None, False, f"数据不足 ({len(df)}天)"
        
        # 检查数据质量
        if df['Close'].isnull().any() or df['Volume'].isnull().any():
            return None, None, None, None, False, "数据存在空值"
        
        # 转换为numpy数组
        close = df['Close'].values.astype(float)
        high = df['High'].values.astype(float)
        low = df['Low'].values.astype(float)
        volume = df['Volume'].values.astype(float)
        
        # 确保数据按时间升序排列
        if len(df) > 1 and df.index[-1] < df.index[-2]:
            df = df.sort_index(ascending=True)
            close = df['Close'].values.astype(float)
            high = df['High'].values.astype(float)
            low = df['Low'].values.astype(float)
            volume = df['Volume'].values.astype(float)
        
        return close, high, low, volume, True, "成功"
        
    except Exception as e:
        error_msg = str(e)
        return None, None, None, None, False, f"yfinance错误: {error_msg}"

# ==================== 备用数据源（AKShare） ====================
@st.cache_data(ttl=1800, show_spinner=False)
def fetch_stock_data_ak(symbol, period_days):
    """备用数据源：AKShare"""
    try:
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=period_days + 60)).strftime("%Y%m%d")
        
        df = ak.stock_zh_a_hist(
            symbol=symbol,
            period="daily",
            start_date=start_date,
            end_date=end_date,
            adjust="qfq",
            timeout=15
        )
        
        if df.empty or len(df) < 30:
            return None, None, None, None, False, "数据不足"
        
        # 转换为numpy数组
        close = df['收盘'].values.astype(float)
        high = df['最高'].values.astype(float)
        low = df['最低'].values.astype(float)
        volume = df['成交量'].values.astype(float) * 100
        
        return close, high, low, volume, True, "成功"
        
    except Exception as e:
        return None, None, None, None, False, f"AKShare错误: {str(e)}"

def fetch_stock_data_with_fallback(symbol, period_days):
    """
    获取股票数据，优先使用yfinance，失败时使用AKShare
    """
    # 尝试yfinance
    close, high, low, volume, success, msg = fetch_stock_data_yf(symbol, period_days)
    
    if success:
        return close, high, low, volume
    
    # yfinance失败，尝试AKShare
    st.warning(f"{symbol} yfinance获取失败({msg})，尝试AKShare...")
    close, high, low, volume, success, msg = fetch_stock_data_ak(symbol, period_days)
    
    if success:
        return close, high, low, volume
    
    # 两个数据源都失败
    st.error(f"{symbol} 数据获取失败: {msg}")
    return None, None, None, None

# ==================== 技术指标计算 ====================
def calculate_ema(prices, period):
    """计算指数移动平均线"""
    if len(prices) < period:
        return np.full_like(prices, np.nan)
    
    alpha = 2 / (period + 1)
    ema = np.zeros_like(prices)
    ema[0] = prices[0]
    
    for i in range(1, len(prices)):
        ema[i] = alpha * prices[i] + (1 - alpha) * ema[i-1]
    
    return ema

def calculate_macd(prices):
    """计算MACD指标"""
    ema12 = calculate_ema(prices, 12)
    ema26 = calculate_ema(prices, 26)
    
    macd_line = ema12 - ema26
    signal_line = calculate_ema(macd_line, 9)
    histogram = macd_line - signal_line
    
    return macd_line, signal_line, histogram

def calculate_rsi(prices, period=14):
    """计算RSI指标"""
    if len(prices) < period + 1:
        return np.full_like(prices, 50)
    
    deltas = np.diff(prices)
    seed = deltas[:period]
    
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period
    
    rs = up / (down + 1e-10)
    rsi = np.zeros_like(prices)
    rsi[:period] = 100 - 100 / (1 + rs)
    
    for i in range(period, len(prices)):
        delta = deltas[i-1]
        
        if delta > 0:
            up_val = delta
            down_val = 0
        else:
            up_val = 0
            down_val = -delta
        
        up = (up * (period - 1) + up_val) / period
        down = (down * (period - 1) + down_val) / period
        
        rs = up / (down + 1e-10)
        rsi[i] = 100 - 100 / (1 + rs)
    
    return rsi

def calculate_atr(high, low, close, period=14):
    """计算ATR指标"""
    if len(high) < period + 1:
        return np.full_like(close, np.nan)
    
    tr = np.zeros_like(close)
    tr[0] = high[0] - low[0]
    
    for i in range(1, len(close)):
        hl = high[i] - low[i]
        hc = abs(high[i] - close[i-1])
        lc = abs(low[i] - close[i-1])
        tr[i] = max(hl, hc, lc)
    
    atr = np.zeros_like(close)
    atr[period-1] = np.mean(tr[:period])
    
    for i in range(period, len(close)):
        atr[i] = (atr[i-1] * (period - 1) + tr[i]) / period
    
    return atr

def calculate_obv(close, volume):
    """计算OBV指标"""
    obv = np.zeros_like(close)
    obv[0] = volume[0] if close[0] >= close[0] else -volume[0]
    
    for i in range(1, len(close)):
        if close[i] > close[i-1]:
            obv[i] = obv[i-1] + volume[i]
        elif close[i] < close[i-1]:
            obv[i] = obv[i-1] - volume[i]
        else:
            obv[i] = obv[i-1]
    
    return obv

def calculate_rolling_mean(data, window):
    """计算滚动平均值"""
    if len(data) < window:
        return np.full_like(data, np.mean(data) if len(data) > 0 else 0)
    
    result = np.zeros_like(data)
    for i in range(len(data)):
        start_idx = max(0, i - window + 1)
        result[i] = np.mean(data[start_idx:i+1])
    
    return result

# ==================== 回测统计 ====================
def backtest_strategy(close_prices, signal_scores, lookforward_days=7):
    """
    回测策略表现
    返回: (胜率, 盈亏比, 交易次数)
    """
    if len(close_prices) <= lookforward_days + 10:
        return 0.5, 1.0, 0
    
    # 找出所有信号点（分数>=3）
    signal_indices = np.where(signal_scores[:-lookforward_days] >= 3)[0]
    
    if len(signal_indices) == 0:
        return 0.5, 1.0, 0
    
    returns = []
    
    for idx in signal_indices:
        if idx + lookforward_days < len(close_prices):
            entry_price = close_prices[idx]
            exit_price = close_prices[idx + lookforward_days]
            returns.append((exit_price - entry_price) / entry_price)
    
    if len(returns) == 0:
        return 0.5, 1.0, 0
    
    returns = np.array(returns)
    win_rate = np.mean(returns > 0)
    
    # 计算盈亏比
    winning_returns = returns[returns > 0]
    losing_returns = returns[returns <= 0]
    
    if len(losing_returns) > 0 and len(winning_returns) > 0:
        avg_win = np.mean(winning_returns)
        avg_loss = abs(np.mean(losing_returns))
        profit_factor = avg_win / avg_loss if avg_loss > 0 else 999
    else:
        profit_factor = 1.0 if len(losing_returns) == 0 else 0.0
    
    return win_rate, profit_factor, len(returns)

# ==================== 股票分析主函数 ====================
def analyze_stock(symbol, period_key="1年"):
    """
    分析单只股票的技术指标和信号
    返回: 包含分析结果的字典 或 None（分析失败）
    """
    try:
        # 获取上市日期（从AKShare）
        try:
            info = ak.stock_individual_info_em(symbol)
            listing_info = info[info['item'] == '上市日期']
            if not listing_info.empty:
                listing_date = pd.to_datetime(listing_info['value'].values[0])
                days_listed = (datetime.now() - listing_date).days
                
                # 排除上市时间不足的股票
                if days_listed <= 360:
                    return None
        except:
            # 如果无法获取上市日期，继续分析
            pass
        
        # 获取回测天数
        days_back = BACKTEST_CONFIG.get(period_key, BACKTEST_CONFIG["1年"])["days"]
        
        # 获取股票数据
        close, high, low, volume = fetch_stock_data_with_fallback(symbol, days_back)
        
        if close is None or len(close) < 60:
            return None
        
        # 计算技术指标
        macd_line, signal_line, macd_hist = calculate_macd(close)
        rsi = calculate_rsi(close)
        atr = calculate_atr(high, low, close)
        obv = calculate_obv(close, volume)
        
        # 计算滚动均值
        vol_ma20 = calculate_rolling_mean(volume, 20)
        atr_ma20 = calculate_rolling_mean(atr, 20)
        obv_ma20 = calculate_rolling_mean(obv, 20)
        
        # 生成交易信号
        signals = {
            "MACD金叉": macd_hist[-1] > 0 and macd_line[-1] > signal_line[-1],
            "放量": volume[-1] > vol_ma20[-1] * 1.1 if len(vol_ma20) > 0 and vol_ma20[-1] > 0 else False,
            "RSI强势": 60 <= rsi[-1] <= 80,
            "ATR放大": atr[-1] > atr_ma20[-1] * 1.1 if len(atr_ma20) > 0 and atr_ma20[-1] > 0 else False,
            "OBV上升": obv[-1] > obv_ma20[-1] * 1.05 if len(obv_ma20) > 0 and obv_ma20[-1] > 0 else False,
        }
        
        # 计算信号分数
        score = sum(signals.values())
        
        # 生成历史信号序列用于回测
        signal_hist = np.zeros(len(close))
        for i in range(len(close)):
            sig_macd = macd_hist[i] > 0
            sig_vol = volume[i] > vol_ma20[i] * 1.1 if i < len(vol_ma20) and vol_ma20[i] > 0 else False
            sig_rsi = 60 <= rsi[i] <= 80
            sig_atr = atr[i] > atr_ma20[i] * 1.1 if i < len(atr_ma20) and atr_ma20[i] > 0 else False
            sig_obv = obv[i] > obv_ma20[i] * 1.05 if i < len(obv_ma20) and obv_ma20[i] > 0 else False
            signal_hist[i] = sum([sig_macd, sig_vol, sig_rsi, sig_atr, sig_obv])
        
        # 回测7日表现
        win_rate_7, pf_7, trades_7 = backtest_strategy(close, signal_hist, 7)
        
        # 计算价格变化
        if len(close) >= 2:
            price_change = (close[-1] / close[-2] - 1) * 100
        else:
            price_change = 0
        
        # 评估流动性（30日平均成交额）
        if len(close) >= 30:
            avg_turnover = np.mean(volume[-30:] * close[-30:])
            is_low_liquidity = avg_turnover < 1e8  # 1亿元
        else:
            is_low_liquidity = True
        
        # 准备结果
        result = {
            "symbol": symbol,
            "name": stock_names.get(symbol, "未知"),
            "price": round(float(close[-1]), 2),
            "change": round(float(price_change), 2),
            "score": int(score),
            "signals": ", ".join([k for k, v in signals.items() if v]) or "无信号",
            "win_rate_7": round(float(win_rate_7 * 100), 1),  # 百分比
            "pf_7": round(float(pf_7), 2),
            "trades_7": int(trades_7),
            "is_low_liquidity": bool(is_low_liquidity),
            "analysis_time": datetime.now().strftime("%H:%M:%S"),
            "data_points": len(close)
        }
        
        return result
        
    except Exception as e:
        st.error(f"分析股票 {symbol} 时出错: {str(e)}")
        return None

# ==================== 主界面控制 ====================
st.markdown("---")

# 选择回测周期
col_mode, col_stats = st.columns([1, 2])
with col_mode:
    selected_period = st.selectbox(
        "选择回测周期",
        options=list(BACKTEST_CONFIG.keys()),
        index=2,
        key="period_select"
    )

with col_stats:
    if st.session_state.scan_start_time:
        elapsed = time.time() - st.session_state.scan_start_time
        st.info(f"扫描已运行: {elapsed:.0f}秒 | 优质信号: {sum(1 for x in st.session_state.high_prob if x.get('pf_7', 0) > 4 and x.get('win_rate_7', 0) > 68)}个")

# 进度显示
current_scanned = len(st.session_state.scanned_symbols)
total_stocks = len(tickers_to_scan)

if total_stocks > 0:
    progress_ratio = current_scanned / total_stocks
    progress_bar = st.progress(min(1.0, progress_ratio))
    
    status_text = st.empty()
    status_text.text(f"扫描进度: {current_scanned}/{total_stocks} ({progress_ratio*100:.1f}%) | "
                    f"失败: {st.session_state.failed_count} | "
                    f"优质股: {len([x for x in st.session_state.high_prob if x.get('pf_7', 0) > 4])}")

# ==================== 扫描控制 ====================
st.markdown("---")

if st.button("🚀 开始/继续扫描", type="primary", use_container_width=True):
    if not st.session_state.scan_start_time:
        st.session_state.scan_start_time = time.time()
    
    st.session_state.scanning = True
    st.session_state.paused = False

# 执行扫描
if (st.session_state.scanning and 
    not st.session_state.paused and 
    current_scanned < total_stocks):
    
    # 找出待扫描的股票
    remaining_stocks = [s for s in tickers_to_scan 
                       if s not in st.session_state.scanned_symbols]
    
    batch_size = min(5, len(remaining_stocks))  # 减小批次大小以提高稳定性
    
    with st.spinner(f"正在扫描批次 ({batch_size}只股票)..."):
        batch_results = []
        batch_start_time = time.time()
        
        for i, symbol in enumerate(remaining_stocks[:batch_size]):
            # 更新状态
            status_text.text(f"正在分析: {symbol} ({stock_names.get(symbol, '未知')}) "
                           f"[{current_scanned + i + 1}/{total_stocks}]")
            progress_bar.progress((current_scanned + i + 1) / total_stocks)
            
            # 分析股票
            result = analyze_stock(symbol, selected_period)
            
            if result:
                st.session_state.high_prob.append(result)
                
                # 检查是否优质信号
                if result['pf_7'] > 4 and result['win_rate_7'] > 68:
                    st.success(f"🎯 **优质发现** {symbol} {result['name']} | "
                             f"得分: {result['score']} | "
                             f"7日胜率: {result['win_rate_7']}% | "
                             f"盈亏比: {result['pf_7']:.2f} | "
                             f"信号: {result['signals']}")
                
                batch_results.append(result)
            else:
                st.session_state.failed_count += 1
            
            # 记录已扫描
            st.session_state.scanned_symbols.add(symbol)
            st.session_state.total_scanned += 1
            
            # 随机延迟以避免请求过快
            time.sleep(random.uniform(1.5, 3.0))
        
        batch_time = time.time() - batch_start_time
        
        # 更新进度
        current_scanned = len(st.session_state.scanned_symbols)
        progress_ratio = current_scanned / total_stocks
        progress_bar.progress(min(1.0, progress_ratio))
        
        # 检查是否完成
        if current_scanned >= total_stocks:
            st.session_state.fully_scanned = True
            st.session_state.scanning = False
            st.balloons()
            st.success("🎉 扫描完成！所有股票已分析完毕。")
        
        # 保存进度
        save_progress()
        
        # 显示批次统计
        if batch_results:
            avg_score = sum(r['score'] for r in batch_results) / len(batch_results)
            premium_count = sum(1 for r in batch_results if r['pf_7'] > 4 and r['win_rate_7'] > 68)
            
            st.info(f"批次完成: {len(batch_results)}只 | "
                   f"优质信号: {premium_count}个 | "
                   f"平均得分: {avg_score:.1f} | "
                   f"耗时: {batch_time:.1f}秒")
        
        # 自动刷新继续扫描
        if not st.session_state.fully_scanned and not st.session_state.paused:
            time.sleep(2)
            st.rerun()

# ==================== 结果显示 ====================
st.markdown("---")

if st.session_state.high_prob:
    # 转换为DataFrame
    df_results = pd.DataFrame(st.session_state.high_prob)
    
    # 数据清洗
    required_cols = ['symbol', 'name', 'price', 'change', 'score', 'win_rate_7', 'pf_7', 
                     'signals', 'is_low_liquidity', 'trades_7']
    
    for col in required_cols:
        if col not in df_results.columns:
            df_results[col] = None
    
    # 筛选优质股票
    premium_mask = (df_results['pf_7'] > 4) & (df_results['win_rate_7'] > 68)
    
    if premium_mask.any():
        df_premium = df_results[premium_mask].copy()
        df_premium['group'] = '🔥 优质信号'
        df_premium = df_premium.sort_values(['pf_7', 'win_rate_7'], ascending=[False, False])
        
        st.subheader(f"优质信号发现 ({len(df_premium)}只)")
        
        # 显示优质股票表格
        display_cols = ['symbol', 'name', 'price', 'change', 'score', 'win_rate_7', 'pf_7', 'signals']
        st.dataframe(
            df_premium[display_cols].rename(columns={
                'symbol': '代码',
                'name': '名称',
                'price': '价格',
                'change': '涨幅%',
                'score': '信号分',
                'win_rate_7': '7日胜率%',
                'pf_7': '盈亏比',
                'signals': '触发信号'
            }),
            use_container_width=True,
            hide_index=True
        )
    
    # 显示所有结果
    st.subheader(f"完整扫描结果 ({len(df_results)}只)")
    
    # 添加分组标签
    if premium_mask.any():
        df_results['group'] = np.where(premium_mask, '🔥 优质信号', '📊 一般信号')
        df_display = df_results.sort_values(['group', 'pf_7', 'win_rate_7'], 
                                           ascending=[True, False, False])
    else:
        df_results['group'] = '📊 一般信号'
        df_display = df_results.sort_values(['pf_7', 'win_rate_7'], ascending=[False, False])
    
    # 格式化显示
    display_df = df_display.copy()
    display_df['change'] = display_df['change'].apply(lambda x: f"{x:+.2f}%")
    display_df['win_rate_7'] = display_df['win_rate_7'].apply(lambda x: f"{x:.1f}%")
    display_df['pf_7'] = display_df['pf_7'].apply(lambda x: f"{x:.2f}")
    display_df['liquidity'] = display_df['is_low_liquidity'].apply(lambda x: "低" if x else "正常")
    
    # 创建显示文本
    result_lines = []
    for _, row in df_display.iterrows():
        line = (f"{row['group']} | {row['symbol']} {row['name']:10} | "
                f"价:{row['price']:7.2f} | 涨:{row['change']:+.2f}% | "
                f"分:{row['score']:1d} | 胜:{row['win_rate_7']:.1f}% | "
                f"PF:{row['pf_7']:.2f} | 交:{row['trades_7']:3d}次 | "
                f"流:{'低' if row['is_low_liquidity'] else '常'} | "
                f"信号:{row['signals'][:30]}")
        result_lines.append(line)
    
    # 显示结果
    st.text_area(
        "详细结果 (可全选复制)",
        "\n".join(result_lines),
        height=min(600, len(result_lines) * 25),
        key="results_area"
    )
    
    # 下载功能
    csv_data = df_display.to_csv(index=False, encoding='utf-8-sig')
    
    st.download_button(
        label="📥 下载CSV结果",
        data=csv_data,
        file_name=f"stock_scan_results_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
        use_container_width=True
    )
    
    # 统计信息
    col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
    
    with col_stat1:
        avg_score = df_results['score'].mean()
        st.metric("平均信号分", f"{avg_score:.1f}")
    
    with col_stat2:
        avg_win_rate = df_results['win_rate_7'].mean()
        st.metric("平均7日胜率", f"{avg_win_rate:.1f}%")
    
    with col_stat3:
        avg_pf = df_results['pf_7'].mean()
        st.metric("平均盈亏比", f"{avg_pf:.2f}")
    
    with col_stat4:
        low_liquidity_pct = (df_results['is_low_liquidity'].sum() / len(df_results)) * 100
        st.metric("低流动性占比", f"{low_liquidity_pct:.1f}%")
    
else:
    st.info("暂无扫描结果。点击上方'开始/继续扫描'按钮开始分析。")

# ==================== 页脚 ====================
st.markdown("---")
st.caption(
    f"📊 科创板+创业板短线扫描工具 | "
    f"数据源: yFinance (主) + AKShare (备) | "
    f"最后更新: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
    f"总扫描: {st.session_state.total_scanned}只"
)

# 调试信息（可选）
with st.expander("调试信息"):
    st.write(f"Session State 状态:")
    st.json({
        "high_prob_count": len(st.session_state.high_prob),
        "scanned_symbols_count": len(st.session_state.scanned_symbols),
        "failed_count": st.session_state.failed_count,
        "fully_scanned": st.session_state.fully_scanned,
        "scanning": st.session_state.scanning,
        "paused": st.session_state.paused,
        "total_stocks": total_stocks
    })
