import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import time
import random
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# ==================== 配置 ====================
st.set_page_config(page_title="股票短线扫描", layout="wide")
st.title("科创板和创业板短线扫描工具 - 专业版")

# ==================== 股票池初始化 ====================
@st.cache_resource
def initialize_stock_pool():
    """初始化股票池（科创板300 + 创业板300）"""
    stock_pool = {}
    
    # 科创板样本股票（实际存在的）
    kcb_stocks = {
        "688981": "中芯国际", "688111": "金山办公", "688126": "沪硅产业",
        "688008": "澜起科技", "688099": "晶晨股份", "688036": "传音控股",
        "688185": "康希诺", "688390": "固德威", "688169": "石头科技",
        "688399": "硕世生物", "688019": "安集科技", "688088": "虹软科技",
        "688116": "天奈科技", "688321": "微芯生物", "688363": "华熙生物",
        "688568": "中科星图", "688122": "西部超导", "688005": "容百科技",
        "688777": "中控技术", "688278": "特宝生物", "688298": "东方生物",
        "688310": "迈得医疗", "688366": "昊海生科", "688388": "嘉元科技",
        "688516": "奥特维", "688550": "瑞联新材", "688599": "天合光能",
        "688686": "奥普特", "688696": "极米科技", "688981": "中芯国际",
        "688023": "安恒信息", "688029": "南微医学", "688030": "山石网科",
        "688033": "天宜上佳", "688036": "传音控股", "688039": "当虹科技",
        "688058": "宝兰德", "688066": "航天宏图", "688068": "热景生物",
        "688078": "龙软科技", "688085": "三友医疗", "688086": "紫晶存储",
        "688088": "虹软科技", "688089": "嘉必优", "688090": "瑞松科技",
        "688098": "申联生物", "688099": "晶晨股份", "688100": "威胜信息"
    }
    
    # 创业板样本股票（实际存在的）
    cyb_stocks = {
        "300750": "宁德时代", "300059": "东方财富", "300760": "迈瑞医疗",
        "300498": "温氏股份", "300142": "沃森生物", "300015": "爱尔眼科",
        "300124": "汇川技术", "300274": "阳光电源", "300122": "智飞生物",
        "300014": "亿纬锂能", "300347": "泰格医药", "300595": "欧普康视",
        "300601": "康泰生物", "300628": "亿联网络", "300676": "华大基因",
        "300782": "卓胜微", "300896": "爱美客", "300999": "金龙鱼",
        "300413": "芒果超媒", "300433": "蓝思科技", "300450": "先导智能",
        "300454": "深信服", "300476": "胜宏科技", "300496": "中科创达",
        "300502": "新易盛", "300558": "贝达药业", "300573": "兴齐眼药",
        "300604": "长川科技", "300618": "寒锐钴业", "300750": "宁德时代",
        "300003": "乐普医疗", "300012": "华测检测", "300015": "爱尔眼科",
        "300017": "网宿科技", "300024": "机器人", "300033": "同花顺",
        "300037": "新宙邦", "300039": "上海凯宝", "300054": "鼎龙股份",
        "300059": "东方财富", "300070": "碧水源", "300072": "三聚环保",
        "300075": "数字政通", "300077": "国民技术", "300079": "数码视讯",
        "300083": "劲胜智能", "300085": "银之杰", "300088": "长信科技",
        "300094": "国联水产", "300098": "高新兴", "300101": "振芯科技"
    }
    
    # 添加更多股票以达到各300只
    # 科创板：688100-688399
    for i in range(101, 400):
        code = f"688{i}"
        if code not in stock_pool:
            stock_pool[code] = f"科创板{i}"
    
    # 创业板：300100-300999
    for i in range(100, 1000):
        code = f"300{i:03d}"
        if code not in stock_pool and len(code) == 6:
            stock_pool[code] = f"创业板{i}"
    
    # 添加样本股票（覆盖现有）
    stock_pool.update(kcb_stocks)
    stock_pool.update(cyb_stocks)
    
    return stock_pool

# 初始化股票池
STOCK_POOL = initialize_stock_pool()

# ==================== 回测配置 ====================
BACKTEST_CONFIG = {
    "3个月": {"days": 90},
    "6个月": {"days": 180},
    "1年": {"days": 365},
    "2年": {"days": 730},
}

# ==================== yfinance 数据获取 ====================
def get_yf_symbol(code):
    """将A股代码转换为yfinance格式"""
    if code.startswith('6'):
        return f"{code}.SS"
    elif code.startswith('3'):
        return f"{code}.SZ"
    else:
        return code

@st.cache_data(ttl=600, show_spinner=False)
def fetch_yf_ohlcv(symbol: str, days_back: int):
    """
    使用yfinance获取股票历史数据
    返回: (close, high, low, volume)
    """
    try:
        yf_symbol = get_yf_symbol(symbol)
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back + 60)
        
        ticker = yf.Ticker(yf_symbol)
        df = ticker.history(start=start_date, end=end_date)
        
        if df.empty or len(df) < 30:
            return None, None, None, None
        
        # 转换为numpy数组
        close = df['Close'].values.astype(float)
        high = df['High'].values.astype(float)
        low = df['Low'].values.astype(float)
        volume = df['Volume'].values.astype(float)
        
        return close, high, low, volume
        
    except Exception as e:
        print(f"fetch_yf_ohlcv 失败 {symbol}: {str(e)}")
        return None, None, None, None

# ==================== 专业指标计算函数 ====================
def ema_np(x: np.ndarray, span: int) -> np.ndarray:
    """指数移动平均"""
    if len(x) == 0:
        return np.array([])
    
    alpha = 2 / (span + 1)
    ema = np.empty_like(x)
    ema[0] = x[0]
    for i in range(1, len(x)):
        ema[i] = alpha * x[i] + (1 - alpha) * ema[i-1]
    return ema

def macd_hist_np(close: np.ndarray) -> np.ndarray:
    """MACD柱状线"""
    if len(close) < 26:
        return np.zeros_like(close)
    
    ema12 = ema_np(close, 12)
    ema26 = ema_np(close, 26)
    macd_line = ema12 - ema26
    signal = ema_np(macd_line, 9)
    return macd_line - signal

def rsi_np(close: np.ndarray, period: int = 14) -> np.ndarray:
    """RSI指标"""
    if len(close) < period + 1:
        return np.full_like(close, 50)
    
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
    """ATR指标"""
    if len(close) < 2:
        return np.zeros_like(close)
    
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
    """滚动平均值"""
    if len(x) < window:
        return np.full_like(x, np.nanmean(x) if not np.isnan(x).all() else 0)
    
    cumsum = np.cumsum(np.insert(x, 0, 0.0))
    ma = (cumsum[window:] - cumsum[:-window]) / window
    return np.concatenate([np.full(window-1, ma[0]), ma])

def obv_np(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
    """OBV指标"""
    if len(close) < 2:
        return volume.copy()
    
    direction = np.sign(np.diff(close, prepend=close[0]))
    return np.cumsum(direction * volume)

def backtest_with_stats(close: np.ndarray, score: np.ndarray, steps: int):
    """回测统计"""
    if len(close) <= steps + 1:
        return 0.5, 0.0
    
    idx = np.where(score[:-steps] >= 3)[0]
    if len(idx) == 0:
        return 0.5, 0.0
    
    rets = close[idx + steps] / close[idx] - 1
    win_rate = (rets > 0).mean()
    
    if (rets <= 0).any():
        pf = rets[rets > 0].sum() / abs(rets[rets <= 0].sum())
    else:
        pf = 999
    
    return win_rate, pf

# ==================== 核心计算函数 ====================
@st.cache_data(show_spinner=False)
def compute_stock_metrics(symbol: str, cfg_key: str = "1年"):
    """计算股票技术指标和信号"""
    try:
        # 获取数据
        days_back = BACKTEST_CONFIG[cfg_key]["days"]
        close, high, low, volume = fetch_yf_ohlcv(symbol, days_back)
        
        if close is None or len(close) < 60:
            return None
        
        # 计算技术指标
        macd_hist = macd_hist_np(close)
        rsi = rsi_np(close)
        atr = atr_np(high, low, close)
        obv = obv_np(close, volume)
        vol_ma20 = rolling_mean_np(volume, 20)
        atr_ma20 = rolling_mean_np(atr, 20)
        obv_ma20 = rolling_mean_np(obv, 20)
        
        # 生成当前信号
        sig_macd = macd_hist[-1] > 0
        sig_vol = volume[-1] > vol_ma20[-1] * 1.1 if len(vol_ma20) > 0 and vol_ma20[-1] > 0 else False
        sig_rsi = rsi[-1] >= 60
        sig_atr = atr[-1] > atr_ma20[-1] * 1.1 if len(atr_ma20) > 0 and atr_ma20[-1] > 0 else False
        sig_obv = obv[-1] > obv_ma20[-1] * 1.05 if len(obv_ma20) > 0 and obv_ma20[-1] > 0 else False
        
        # 计算信号分数
        score = sum([sig_macd, sig_vol, sig_rsi, sig_atr, sig_obv])
        
        # 信号详情
        sig_details = {
            "MACD>0": sig_macd,
            "放量": sig_vol,
            "RSI≥60": sig_rsi,
            "ATR放大": sig_atr,
            "OBV上升": sig_obv
        }
        
        # 生成历史信号序列用于回测
        sig_macd_hist = (macd_hist > 0).astype(int)
        sig_vol_hist = (volume > vol_ma20 * 1.1).astype(int) if len(vol_ma20) > 0 else np.zeros_like(close, dtype=int)
        sig_rsi_hist = (rsi >= 60).astype(int)
        sig_atr_hist = (atr > atr_ma20 * 1.1).astype(int) if len(atr_ma20) > 0 else np.zeros_like(close, dtype=int)
        sig_obv_hist = (obv > obv_ma20 * 1.05).astype(int) if len(obv_ma20) > 0 else np.zeros_like(close, dtype=int)
        
        score_arr = sig_macd_hist + sig_vol_hist + sig_rsi_hist + sig_atr_hist + sig_obv_hist
        
        # 回测7日表现
        prob7, pf7 = backtest_with_stats(close[:-1], score_arr[:-1], 7)
        
        # 计算价格变化
        price = close[-1]
        change = (close[-1] / close[-2] - 1) * 100 if len(close) >= 2 else 0
        
        # 计算成交额（最近20天平均）
        if len(volume) >= 20:
            avg_volume = np.mean(volume[-20:])
            turnover = avg_volume * price / 1e8  # 转换为亿元
        else:
            avg_volume = np.mean(volume) if len(volume) > 0 else 0
            turnover = 0
        
        # 计算其他技术指标值
        current_rsi = rsi[-1]
        current_atr = atr[-1]
        current_obv = obv[-1]
        
        # 评估流动性
        is_low_liquidity = (avg_volume * price) < 100000000 if avg_volume > 0 else True
        
        # 准备返回结果
        signals_text = ", ".join([k for k, v in sig_details.items() if v]) or "无信号"
        
        return {
            "symbol": symbol,
            "name": STOCK_POOL.get(symbol, "未知"),
            "price": round(price, 2),
            "change": round(change, 2),
            "score": score,
            "signals": signals_text,
            "prob7": prob7,
            "pf7": pf7,
            "prob7_pct": round(prob7 * 100, 1),
            "rsi": round(current_rsi, 1),
            "atr": round(current_atr, 2),
            "obv": round(current_obv, 0),
            "is_low_liquidity": is_low_liquidity,
            "turnover": round(turnover, 2),
            "data_points": len(close),
            "scan_time": datetime.now().strftime("%H:%M:%S")
        }
        
    except Exception as e:
        print(f"compute_stock_metrics 异常 {symbol}: {str(e)}")
        return None

# ==================== 扫描单只股票 ====================
def scan_stock(stock_code, stock_name, period_key="1年"):
    """扫描单只股票（包装函数）"""
    result = compute_stock_metrics(stock_code, period_key)
    
    if result is None:
        return {
            '代码': stock_code,
            '名称': stock_name,
            '价格': 0,
            '涨幅%': 0,
            '信号分': 0,
            '7日胜率%': 0,
            '盈亏比': 0,
            '触发信号': "数据失败",
            '评级': '❌ 失败',
            'RSI': 0,
            'ATR': 0,
            'OBV': 0,
            '成交额': 0,
            '数据点': 0
        }
    
    # 判断评级
    if result['pf7'] > 4 and result['prob7_pct'] > 68:
        rating = '🔥 优质'
    elif result['score'] >= 3:
        rating = '✅ 良好'
    elif result['score'] >= 1:
        rating = '📊 一般'
    else:
        rating = '⚠️ 弱势'
    
    return {
        '代码': result['symbol'],
        '名称': result['name'],
        '价格': result['price'],
        '涨幅%': result['change'],
        'RSI': result['rsi'],
        'ATR': result['atr'],
        'OBV': result['obv'],
        '信号分': result['score'],
        '7日胜率%': result['prob7_pct'],
        '盈亏比': round(result['pf7'], 2),
        '触发信号': result['signals'],
        '评级': rating,
        '成交额': result['turnover'],
        '数据点': result['data_points'],
        '流动性': '低' if result['is_low_liquidity'] else '正常',
        '扫描时间': result['scan_time']
    }

# ==================== 主界面 ====================
# 初始化session state
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = []
if 'scanning' not in st.session_state:
    st.session_state.scanning = False
if 'premium_count' not in st.session_state:
    st.session_state.premium_count = 0
if 'scanned_count' not in st.session_state:
    st.session_state.scanned_count = 0

# 侧边栏配置
with st.sidebar:
    st.title("⚙️ 专业设置")
    
    # 显示股票池信息
    kcb_count = len([c for c in STOCK_POOL.keys() if c.startswith('688')])
    cyb_count = len([c for c in STOCK_POOL.keys() if c.startswith('300')])
    
    st.info(f"💰 股票总数: {len(STOCK_POOL)}")
    st.info(f"📈 科创板: {kcb_count}只")
    st.info(f"📊 创业板: {cyb_count}只")
    
    st.markdown("---")
    
    # 回测周期选择
    period_key = st.selectbox(
        "回测周期",
        options=list(BACKTEST_CONFIG.keys()),
        index=2,
        help="选择用于回测的历史数据周期"
    )
    
    # 扫描数量设置
    stock_count = st.slider(
        "扫描股票数量",
        min_value=10,
        max_value=min(600, len(STOCK_POOL)),
        value=min(100, len(STOCK_POOL)),
        step=10
    )
    
    # 优质标准
    st.subheader("🎯 优质标准")
    min_pf = st.slider("最小盈亏比(PF7)", 2.0, 10.0, 4.0, 0.5)
    min_win_rate = st.slider("最小7日胜率%", 50, 95, 68, 2)
    
    # 扫描参数
    st.subheader("⚡ 扫描参数")
    batch_size = st.slider("每批数量", 1, 20, 5, 1)
    delay_time = st.slider("延迟时间(秒)", 0.1, 3.0, 0.8, 0.1)
    
    st.markdown("---")
    st.caption("💡 提示: 专业指标包括MACD、RSI、ATR、OBV、成交量分析")

# 控制面板
st.markdown("---")
col1, col2, col3 = st.columns(3)

with col1:
    if st.button("🚀 开始专业扫描", type="primary", use_container_width=True):
        st.session_state.scanning = True
        st.session_state.scan_results = []
        st.session_state.premium_count = 0
        st.session_state.scanned_count = 0

with col2:
    if st.button("⏸️ 暂停扫描", use_container_width=True):
        st.session_state.scanning = False

with col3:
    if st.button("🔄 重置所有", use_container_width=True):
        st.session_state.scan_results = []
        st.session_state.scanning = False
        st.session_state.premium_count = 0
        st.session_state.scanned_count = 0
        st.cache_data.clear()
        st.rerun()

# 扫描进度
if st.session_state.scanning:
    all_stocks = list(STOCK_POOL.items())
    stocks_to_scan = all_stocks[:stock_count]
    total_stocks = len(stocks_to_scan)
    
    scanned_count = st.session_state.scanned_count
    
    if scanned_count < total_stocks:
        batch_end = min(scanned_count + batch_size, total_stocks)
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for i in range(scanned_count, batch_end):
            stock_code, stock_name = stocks_to_scan[i]
            
            progress = (i + 1) / total_stocks
            progress_bar.progress(progress)
            status_text.text(f"🔍 扫描: {stock_code} {stock_name} ({i+1}/{total_stocks})")
            
            # 扫描股票
            result = scan_stock(stock_code, stock_name, period_key)
            st.session_state.scan_results.append(result)
            st.session_state.scanned_count += 1
            
            # 实时显示优质信号
            if result['评级'] == '🔥 优质':
                st.session_state.premium_count += 1
                st.success(f"🎯 优质发现: {stock_code} {stock_name} | "
                          f"价:{result['价格']} | 涨:{result['涨幅%']:+.2f}% | "
                          f"分:{result['信号分']} | 胜:{result['7日胜率%']}% | "
                          f"PF:{result['盈亏比']:.2f} | RSI:{result['RSI']}")
            
            # 延迟
            time.sleep(delay_time)
        
        # 自动继续
        time.sleep(0.5)
        st.rerun()
    else:
        st.session_state.scanning = False
        st.balloons()
        st.success(f"✅ 扫描完成! 共扫描 {total_stocks} 只股票，发现 {st.session_state.premium_count} 只优质股票")

# 显示结果
st.markdown("---")

if st.session_state.scan_results:
    df_results = pd.DataFrame(st.session_state.scan_results)
    
    # 过滤有效结果
    df_valid = df_results[~df_results['评级'].isin(['❌ 失败', '❌ 错误'])].copy()
    
    if not df_valid.empty:
        # 按评级和盈亏比排序
        rating_order = {'🔥 优质': 0, '✅ 良好': 1, '📊 一般': 2, '⚠️ 弱势': 3}
        df_valid['rating_order'] = df_valid['评级'].map(rating_order)
        df_valid = df_valid.sort_values(['rating_order', '盈亏比', '7日胜率%'], ascending=[True, False, False])
        
        # 显示统计信息
        st.subheader("📈 专业分析统计")
        
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            total = len(df_valid)
            st.metric("成功扫描", f"{total}只")
        
        with col2:
            premium = len(df_valid[df_valid['评级'] == '🔥 优质'])
            st.metric("优质股票", f"{premium}只")
        
        with col3:
            avg_score = df_valid['信号分'].mean()
            st.metric("平均信号分", f"{avg_score:.1f}")
        
        with col4:
            avg_win = df_valid['7日胜率%'].mean()
            st.metric("平均胜率", f"{avg_win:.1f}%")
        
        with col5:
            avg_pf = df_valid['盈亏比'].mean()
            st.metric("平均盈亏比", f"{avg_pf:.2f}")
        
        # 显示优质股票
        premium_stocks = df_valid[df_valid['评级'] == '🔥 优质']
        if not premium_stocks.empty:
            st.subheader(f"🔥 优质股票发现 ({len(premium_stocks)}只)")
            
            # 生成TXT格式内容
            txt_content = "=" * 100 + "\n"
            txt_content += "优质股票扫描结果（专业指标分析）\n"
            txt_content += "=" * 100 + "\n"
            txt_content += f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            txt_content += f"回测周期: {period_key} | 筛选标准: PF7>{min_pf} 且 胜率>{min_win_rate}%\n"
            txt_content += f"股票总数: {len(premium_stocks)}只 | 信号指标: MACD, RSI, ATR, OBV, 成交量\n"
            txt_content += "=" * 100 + "\n\n"
            
            for idx, (_, stock) in enumerate(premium_stocks.iterrows(), 1):
                txt_content += f"{idx:3d}. {stock['代码']} {stock['名称']}\n"
                txt_content += f"    价格: {stock['价格']:8.2f}  涨幅: {stock['涨幅%']:+7.2f}%  信号分: {stock['信号分']}/5\n"
                txt_content += f"    胜率: {stock['7日胜率%']:6.1f}%  盈亏比: {stock['盈亏比']:6.2f}  RSI: {stock['RSI']:5.1f}\n"
                txt_content += f"    ATR: {stock['ATR']:6.2f}  OBV: {stock['OBV']:.0f}  成交额: {stock['成交额']:6.2f}亿\n"
                txt_content += f"    触发信号: {stock['触发信号']}\n"
                txt_content += f"    流动性: {stock['流动性']}  数据点: {stock['数据点']}个\n"
                txt_content += "-" * 100 + "\n"
            
            # 显示和下载TXT
            st.text_area("优质股票详情 (专业分析)", txt_content, height=350)
            
            st.download_button(
                label="📥 下载优质股票列表 (TXT)",
                data=txt_content,
                file_name=f"优质股票_专业分析_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                mime="text/plain",
                use_container_width=True
            )
        
        st.markdown("---")
        
        # 显示完整结果
        st.subheader(f"📋 完整扫描结果 ({len(df_valid)}只)")
        
        # 生成完整TXT
        full_txt_content = "=" * 120 + "\n"
        full_txt_content += "完整股票扫描结果 - 专业指标分析\n"
        full_txt_content += "=" * 120 + "\n"
        full_txt_content += f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        full_txt_content += f"回测周期: {period_key} | 扫描数量: {len(df_valid)}只 | 优质股票: {len(premium_stocks)}只\n"
        full_txt_content += f"平均信号分: {avg_score:.2f} | 平均胜率: {avg_win:.2f}% | 平均盈亏比: {avg_pf:.2f}\n"
        full_txt_content += "=" * 120 + "\n\n"
        
        for idx, (_, stock) in enumerate(df_valid.iterrows(), 1):
            full_txt_content += f"{idx:4d}. [{stock['评级']}] {stock['代码']} {stock['名称']}\n"
            full_txt_content += f"      价:{stock['价格']:8.2f} 涨:{stock['涨幅%']:+7.2f}% "
            full_txt_content += f"分:{stock['信号分']:2d}/5 胜:{stock['7日胜率%']:6.1f}% "
            full_txt_content += f"PF:{stock['盈亏比']:5.2f} RSI:{stock['RSI']:5.1f}\n"
            full_txt_content += f"      额:{stock['成交额']:6.2f}亿 流:{stock['流动性']} 信:{stock['触发信号'][:50]}\n"
            
            if idx % 3 == 0:
                full_txt_content += "-" * 120 + "\n"
            else:
                full_txt_content += "\n"
        
        full_txt_content += "=" * 120 + "\n"
        full_txt_content += "专业指标说明:\n"
        full_txt_content += "- MACD>0: MACD柱状线为正，动量向上\n"
        full_txt_content += "- 放量: 成交量超过20日均量1.1倍\n"
        full_txt_content += "- RSI≥60: 相对强弱指数≥60，处于强势区间\n"
        full_txt_content += "- ATR放大: 真实波动幅度超过20日均值1.1倍\n"
        full_txt_content += "- OBV上升: 能量潮指标超过20日均值1.05倍\n"
        full_txt_content += "=" * 120
        
        # 显示和下载
        with st.expander("📄 查看完整专业分析结果"):
            st.text_area("完整专业分析", full_txt_content, height=400)
        
        col_dl1, col_dl2 = st.columns(2)
        
        with col_dl1:
            st.download_button(
                label="📥 下载完整专业分析 (TXT)",
                data=full_txt_content,
                file_name=f"完整扫描_专业分析_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                mime="text/plain",
                use_container_width=True
            )
        
        with col_dl2:
            csv_data = df_valid.to_csv(index=False, encoding='utf-8-sig')
            st.download_button(
                label="📥 下载完整数据 (CSV)",
                data=csv_data,
                file_name=f"股票扫描_专业数据_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True
            )
        
        # 显示数据表格
        with st.expander("📊 查看专业数据表格"):
            display_cols = ['评级', '代码', '名称', '价格', '涨幅%', '信号分', 
                           '7日胜率%', '盈亏比', 'RSI', 'ATR', '成交额', '触发信号']
            
            st.dataframe(
                df_valid[display_cols],
                use_container_width=True,
                height=500
            )
    
    else:
        st.warning("⚠️ 没有获取到有效数据")
else:
    st.info("👈 请设置参数后点击'开始专业扫描'")
    
    # 显示说明
    with st.expander("📖 专业指标说明"):
        st.markdown("""
        ### 专业指标分析系统
        
        **核心指标:**
        1. **MACD (Moving Average Convergence Divergence)**
           - 用于判断股票动量方向
           - MACD>0表示多头动量占优
        
        2. **RSI (Relative Strength Index)**
           - 超买超卖指标，范围0-100
           - RSI≥60表示处于强势区间
        
        3. **ATR (Average True Range)**
           - 波动率指标，衡量价格波动幅度
           - ATR放大表示波动加剧，可能预示趋势变化
        
        4. **OBV (On Balance Volume)**
           - 量价关系指标
           - OBV上升表示资金流入
        
        5. **成交量分析**
           - 对比当前成交量与20日均量
           - 放量表示市场关注度提升
        
        **回测统计:**
        - **7日胜率%**: 基于历史数据的7日后上涨概率
        - **盈亏比(PF7)**: 平均盈利/平均亏损的比例
        
        **优质标准:**
        - 盈亏比 > 4.0
        - 7日胜率 > 68%
        """)

# 页脚
st.markdown("---")
st.caption(
    f"🔬 专业指标分析系统 | "
    f"科创板: {kcb_count}只 | 创业板: {cyb_count}只 | "
    f"更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
    f"指标: MACD, RSI, ATR, OBV, 成交量"
)
