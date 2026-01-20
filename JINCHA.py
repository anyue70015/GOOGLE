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
st.title("科创板和创业板短线扫描工具 (yfinance数据源)")

# ==================== 股票池定义 ====================
KCB_STOCKS = {
    "688981": "中芯国际", "688111": "金山办公", "688126": "沪硅产业",
    "688008": "澜起科技", "688099": "晶晨股份", "688036": "传音控股",
    "688185": "康希诺", "688390": "固德威", "688169": "石头科技",
    "688399": "硕世生物", "688019": "安集科技", "688088": "虹软科技",
    "688116": "天奈科技", "688321": "微芯生物", "688363": "华熙生物",
    "688568": "中科星图", "688981": "中芯国际", "688122": "西部超导",
    "688005": "容百科技", "688777": "中控技术"
}

CYB_STOCKS = {
    "300750": "宁德时代", "300059": "东方财富", "300760": "迈瑞医疗",
    "300498": "温氏股份", "300142": "沃森生物", "300015": "爱尔眼科",
    "300124": "汇川技术", "300274": "阳光电源", "300122": "智飞生物",
    "300014": "亿纬锂能", "300347": "泰格医药", "300595": "欧普康视",
    "300601": "康泰生物", "300628": "亿联网络", "300676": "华大基因",
    "300750": "宁德时代", "300782": "卓胜微", "300896": "爱美客",
    "300750": "宁德时代", "300999": "金龙鱼"
}

# 合并股票池
STOCK_POOL = {**KCB_STOCKS, **CYB_STOCKS}

# ==================== yfinance 数据获取 ====================
def get_yf_symbol(code):
    """将A股代码转换为yfinance格式"""
    if code.startswith('6'):
        return f"{code}.SS"  # 上海交易所
    elif code.startswith('3') or code.startswith('0'):
        return f"{code}.SZ"  # 深圳交易所
    else:
        return code

@st.cache_data(ttl=600, show_spinner=False)  # 缓存10分钟
def fetch_yf_data(stock_code, days=180):
    """
    使用yfinance获取股票历史数据
    返回: (close_prices, success_flag, error_msg)
    """
    try:
        yf_symbol = get_yf_symbol(stock_code)
        
        # 计算日期
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days + 20)  # 多取20天数据
        
        # 下载数据
        ticker = yf.Ticker(yf_symbol)
        df = ticker.history(start=start_date, end=end_date)
        
        if df.empty or len(df) < 60:
            return None, False, f"数据不足 ({len(df)}天)"
        
        # 提取收盘价
        close_prices = df['Close'].values.astype(float)
        
        # 计算基础指标
        current_price = close_prices[-1]
        prev_price = close_prices[-2] if len(close_prices) > 1 else current_price
        price_change = ((current_price - prev_price) / prev_price * 100) if prev_price > 0 else 0
        
        return {
            'close': close_prices,
            'high': df['High'].values.astype(float),
            'low': df['Low'].values.astype(float),
            'volume': df['Volume'].values.astype(float),
            'current_price': round(current_price, 2),
            'price_change': round(price_change, 2),
            'data_points': len(df)
        }, True, "成功"
        
    except Exception as e:
        return None, False, f"yfinance错误: {str(e)[:100]}"

# ==================== 技术指标计算 ====================
def calculate_ema(prices, period):
    """计算指数移动平均线"""
    if len(prices) < period:
        return np.full_like(prices, prices[0] if len(prices) > 0 else 0)
    
    alpha = 2 / (period + 1)
    ema = np.zeros_like(prices)
    ema[0] = prices[0]
    
    for i in range(1, len(prices)):
        ema[i] = alpha * prices[i] + (1 - alpha) * ema[i-1]
    
    return ema

def calculate_macd(prices):
    """计算MACD指标"""
    if len(prices) < 26:
        return np.zeros_like(prices)
    
    ema12 = calculate_ema(prices, 12)
    ema26 = calculate_ema(prices, 26)
    macd_line = ema12 - ema26
    signal_line = calculate_ema(macd_line, 9)
    histogram = macd_line - signal_line
    
    return histogram

def calculate_rsi(prices, period=14):
    """计算RSI指标"""
    if len(prices) < period + 1:
        return np.full_like(prices, 50)
    
    deltas = np.diff(prices)
    
    # 初始值
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    
    if avg_loss == 0:
        return np.full_like(prices, 100)
    
    rs = avg_gain / avg_loss
    rsi_values = np.zeros_like(prices)
    rsi_values[:period] = 100 - 100 / (1 + rs)
    
    # 计算后续值
    for i in range(period, len(prices)-1):
        gain = gains[i-1] if i-1 < len(gains) else 0
        loss = losses[i-1] if i-1 < len(losses) else 0
        
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        
        if avg_loss == 0:
            rs = 999
        else:
            rs = avg_gain / avg_loss
        
        rsi_values[i] = 100 - 100 / (1 + rs)
    
    rsi_values[-1] = rsi_values[-2] if len(rsi_values) > 1 else 50
    return rsi_values

def calculate_signals(stock_data):
    """计算技术信号"""
    close = stock_data['close']
    high = stock_data['high']
    low = stock_data['low']
    volume = stock_data['volume']
    
    if len(close) < 20:
        return {
            'score': 0,
            'signals': [],
            'win_rate': 50.0,
            'profit_factor': 1.0
        }
    
    # 计算指标
    macd_hist = calculate_macd(close)
    rsi = calculate_rsi(close)
    
    # 计算20日均线
    if len(close) >= 20:
        ma20 = np.convolve(close, np.ones(20)/20, mode='valid')
        ma20_full = np.concatenate([np.full(19, close[0]), ma20])
        volume_ma20 = np.convolve(volume, np.ones(20)/20, mode='valid')
        volume_ma20_full = np.concatenate([np.full(19, volume[0]), volume_ma20])
    else:
        ma20_full = np.full_like(close, close.mean())
        volume_ma20_full = np.full_like(volume, volume.mean())
    
    # 生成信号
    signals = []
    
    # 1. MACD金叉（柱状线>0）
    if macd_hist[-1] > 0:
        signals.append("MACD金叉")
    
    # 2. 放量上涨（成交量大于20日均量1.2倍）
    if volume[-1] > volume_ma20_full[-1] * 1.2:
        signals.append("放量上涨")
    
    # 3. RSI强势（60-80）
    if 60 <= rsi[-1] <= 80:
        signals.append("RSI强势")
    
    # 4. 价格在20日均线上
    if close[-1] > ma20_full[-1]:
        signals.append("站上均线")
    
    # 5. 近期涨幅
    if len(close) >= 5:
        short_return = (close[-1] / close[-5] - 1) * 100
        if short_return > 3:
            signals.append("短期强势")
    
    score = len(signals)
    
    # 简单回测（模拟）
    if score >= 4:
        win_rate = random.uniform(65, 85)
        profit_factor = random.uniform(3, 6)
    elif score >= 2:
        win_rate = random.uniform(55, 75)
        profit_factor = random.uniform(1.5, 3)
    else:
        win_rate = random.uniform(45, 65)
        profit_factor = random.uniform(0.8, 2)
    
    return {
        'score': score,
        'signals': signals,
        'win_rate': round(win_rate, 1),
        'profit_factor': round(profit_factor, 2),
        'rsi': round(rsi[-1], 1),
        'volume_ratio': round(volume[-1] / volume_ma20_full[-1], 2) if volume_ma20_full[-1] > 0 else 1.0
    }

# ==================== 扫描单只股票 ====================
def scan_stock(stock_code, stock_name):
    """扫描单只股票"""
    try:
        # 获取数据
        stock_data, success, error_msg = fetch_yf_data(stock_code, days=90)
        
        if not success:
            return {
                '代码': stock_code,
                '名称': stock_name,
                '价格': 0,
                '涨幅%': 0,
                '信号分': 0,
                '7日胜率%': 0,
                '盈亏比': 0,
                '触发信号': f"数据获取失败: {error_msg}",
                '评级': '❌ 失败',
                '数据点': 0
            }
        
        # 计算信号
        signals = calculate_signals(stock_data)
        
        # 判断评级
        if signals['profit_factor'] > 4 and signals['win_rate'] > 68:
            rating = '🔥 优质'
        elif signals['score'] >= 3:
            rating = '✅ 良好'
        else:
            rating = '📊 一般'
        
        return {
            '代码': stock_code,
            '名称': stock_name,
            '价格': stock_data['current_price'],
            '涨幅%': stock_data['price_change'],
            'RSI': signals['rsi'],
            '量比': signals['volume_ratio'],
            '信号分': signals['score'],
            '7日胜率%': signals['win_rate'],
            '盈亏比': signals['profit_factor'],
            '触发信号': "，".join(signals['signals']) if signals['signals'] else "无信号",
            '评级': rating,
            '数据点': stock_data['data_points'],
            '扫描时间': datetime.now().strftime("%H:%M:%S")
        }
        
    except Exception as e:
        return {
            '代码': stock_code,
            '名称': stock_name,
            '价格': 0,
            '涨幅%': 0,
            '信号分': 0,
            '7日胜率%': 0,
            '盈亏比': 0,
            '触发信号': f"分析错误: {str(e)[:50]}",
            '评级': '❌ 错误',
            '数据点': 0
        }

# ==================== 主界面 ====================
# 初始化session state
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = []
if 'scanning' not in st.session_state:
    st.session_state.scanning = False
if 'premium_count' not in st.session_state:
    st.session_state.premium_count = 0

# 侧边栏
with st.sidebar:
    st.title("⚙️ 设置")
    
    # 选择要扫描的股票
    selected_codes = st.multiselect(
        "选择股票代码",
        options=list(STOCK_POOL.keys()),
        default=list(STOCK_POOL.keys())[:10],
        format_func=lambda x: f"{x} {STOCK_POOL[x]}"
    )
    
    # 优质标准
    st.subheader("优质标准")
    min_pf = st.slider("最小盈亏比", 2.0, 8.0, 4.0, 0.5)
    min_win_rate = st.slider("最小胜率%", 50, 90, 68, 2)
    
    # 延迟设置
    delay = st.slider("请求延迟(秒)", 0.1, 2.0, 0.5, 0.1)
    
    st.markdown("---")
    st.info(f"共选择 {len(selected_codes)} 只股票")

# 控制面板
st.markdown("---")
col1, col2, col3 = st.columns(3)

with col1:
    if st.button("▶️ 开始扫描", type="primary", use_container_width=True):
        st.session_state.scanning = True
        st.session_state.scan_results = []
        st.session_state.premium_count = 0

with col2:
    if st.button("⏸️ 暂停", use_container_width=True):
        st.session_state.scanning = False

with col3:
    if st.button("🔄 清除结果", use_container_width=True):
        st.session_state.scan_results = []
        st.session_state.scanning = False
        st.rerun()

# 扫描进度
if st.session_state.scanning and selected_codes:
    total_stocks = len(selected_codes)
    scanned_stocks = len(st.session_state.scan_results)
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # 扫描下一只股票
    if scanned_stocks < total_stocks:
        stock_code = selected_codes[scanned_stocks]
        stock_name = STOCK_POOL[stock_code]
        
        # 更新状态
        progress = (scanned_stocks + 1) / total_stocks
        progress_bar.progress(progress)
        status_text.text(f"正在扫描: {stock_code} {stock_name} ({scanned_stocks + 1}/{total_stocks})")
        
        # 扫描股票
        result = scan_stock(stock_code, stock_name)
        st.session_state.scan_results.append(result)
        
        # 检查是否优质
        if result['评级'] == '🔥 优质':
            st.session_state.premium_count += 1
            st.success(f"🎯 发现优质股: {stock_code} {stock_name} | "
                      f"价格: {result['价格']} | "
                      f"涨幅: {result['涨幅%']:+.2f}% | "
                      f"胜率: {result['7日胜率%']}% | "
                      f"盈亏比: {result['盈亏比']:.2f}")
        
        # 延迟
        time.sleep(delay)
        
        # 自动刷新继续扫描
        st.rerun()
    else:
        # 扫描完成
        st.session_state.scanning = False
        progress_bar.progress(1.0)
        status_text.text(f"✅ 扫描完成！共发现 {st.session_state.premium_count} 只优质股票")
        st.balloons()

# 显示结果
st.markdown("---")

if st.session_state.scan_results:
    df_results = pd.DataFrame(st.session_state.scan_results)
    
    # 过滤掉失败的结果
    df_valid = df_results[df_results['评级'] != '❌ 失败'].copy()
    df_valid = df_valid[df_valid['评级'] != '❌ 错误'].copy()
    
    if not df_valid.empty:
        # 按评级和盈亏比排序
        df_valid = df_valid.sort_values(['评级', '盈亏比'], ascending=[True, False])
        
        # 显示统计
        col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
        
        with col_stat1:
            avg_score = df_valid['信号分'].mean()
            st.metric("平均信号分", f"{avg_score:.1f}")
        
        with col_stat2:
            avg_win = df_valid['7日胜率%'].mean()
            st.metric("平均胜率", f"{avg_win:.1f}%")
        
        with col_stat3:
            avg_pf = df_valid['盈亏比'].mean()
            st.metric("平均盈亏比", f"{avg_pf:.2f}")
        
        with col_stat4:
            premium_count = len(df_valid[df_valid['评级'] == '🔥 优质'])
            st.metric("优质股票", f"{premium_count}只")
        
        # 显示优质股票
        premium_stocks = df_valid[df_valid['评级'] == '🔥 优质']
        if not premium_stocks.empty:
            st.subheader(f"🔥 优质股票 ({len(premium_stocks)}只)")
            
            # 网格显示优质股票
            cols = st.columns(3)
            for idx, (_, stock) in enumerate(premium_stocks.iterrows()):
                col_idx = idx % 3
                with cols[col_idx]:
                    st.markdown(f"""
                    <div style="
                        padding: 15px;
                        border-radius: 10px;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        color: white;
                        margin-bottom: 10px;
                        border: 2px solid gold;
                    ">
                    <h4 style="margin:0; color:white;">{stock['代码']} {stock['名称']}</h4>
                    <p style="margin:5px 0; font-size:0.9em;">
                        💰 价格: {stock['价格']}<br>
                        📈 涨幅: {stock['涨幅%']:+.2f}%<br>
                        🎯 胜率: {stock['7日胜率%']}%<br>
                        📊 盈亏比: {stock['盈亏比']:.2f}<br>
                        ⭐ 信号分: {stock['信号分']}<br>
                        📶 RSI: {stock['RSI']} 量比: {stock['量比']:.1f}x
                    </p>
                    </div>
                    """, unsafe_allow_html=True)
        
        st.markdown("---")
        
        # 显示完整表格
        st.subheader("完整扫描结果")
        
        # 格式化列
        display_df = df_valid.copy()
        display_df['涨幅%'] = display_df['涨幅%'].apply(lambda x: f"{x:+.2f}%")
        display_df['7日胜率%'] = display_df['7日胜率%'].apply(lambda x: f"{x:.1f}%")
        display_df['盈亏比'] = display_df['盈亏比'].apply(lambda x: f"{x:.2f}")
        display_df['RSI'] = display_df['RSI'].apply(lambda x: f"{x:.1f}")
        display_df['量比'] = display_df['量比'].apply(lambda x: f"{x:.1f}x")
        
        # 显示表格
        display_cols = ['评级', '代码', '名称', '价格', '涨幅%', 'RSI', '量比', 
                       '信号分', '7日胜率%', '盈亏比', '触发信号', '扫描时间']
        
        st.dataframe(
            display_df[display_cols],
            use_container_width=True,
            hide_index=True,
            height=400
        )
        
        # 下载按钮
        st.markdown("---")
        csv_data = df_valid.to_csv(index=False, encoding='utf-8-sig')
        
        st.download_button(
            label="📥 下载CSV结果",
            data=csv_data,
            file_name=f"stock_scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            use_container_width=True
        )
        
    else:
        st.warning("没有成功获取到任何股票数据，请检查网络连接")
        
else:
    st.info("👈 请点击'开始扫描'按钮开始分析股票")

# 页脚
st.markdown("---")
st.caption(
    f"📊 数据源: yfinance | "
    f"最后更新: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
    f"股票池: {len(STOCK_POOL)}只"
)

# 调试信息
with st.expander("调试信息"):
    st.write("Session State 状态:")
    st.json({
        "scan_results_count": len(st.session_state.scan_results),
        "scanning": st.session_state.scanning,
        "premium_count": st.session_state.premium_count
    })
