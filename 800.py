import streamlit as st
import ccxt
import pandas as pd
import pandas_ta as pta
import time
from datetime import datetime, timedelta
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ================= 配置 =================
EXCHANGE_NAME = 'okx'
SCAN_INTERVAL = 10

SYMBOLS = ['HYPE/USDT', 'BTC/USDT', 'ETH/USDT', 'SOL/USDT']

# 指标参数
UT_FACTOR = 1.0
UT_ATR_LEN = 10
ST_ATR_LEN = 10
ST_MULTIPLIER = 3.0

# ================= UI =================
st.set_page_config(
    page_title="币圈多时间框架VWAP计算器", 
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("📊 币圈24/7 VWAP计算器")

# 侧边栏
with st.sidebar:
    st.header("⚙️ 参数设置")
    
    # 交易对选择
    symbol = st.selectbox(
        "交易对",
        SYMBOLS,
        index=0
    )
    
    # 时间框架选择
    timeframe = st.selectbox(
        "时间框架",
        ['1m', '5m', '15m', '1h', '4h', '1d'],
        index=0
    )
    
    # VWAP计算参数
    st.subheader("📈 VWAP计算参数")
    vwap_lookback = st.number_input(
        "VWAP使用K线数量",
        min_value=10,
        max_value=500,
        value=200
    )
    
    vwap_method = st.radio(
        "VWAP计算方法",
        ['从起点累积 (TradingView模式)', '从今日0点开始', '从昨日延续'],
        index=0
    )
    
    scan_interval = st.number_input("自动刷新间隔(秒)", 5, 60, SCAN_INTERVAL)
    
    if st.button("🔄 立即扫描", use_container_width=True):
        st.session_state.manual_scan = True

# 初始化session_state
if 'last_scan_time' not in st.session_state:
    st.session_state.last_scan_time = 0
if 'manual_scan' not in st.session_state:
    st.session_state.manual_scan = False
if 'vwap_history' not in st.session_state:
    st.session_state.vwap_history = []

# ================= 数据获取 =================
@st.cache_data(ttl=5, show_spinner=False)
def fetch_market_data(symbol, timeframe, limit=500):
    """获取市场数据"""
    try:
        exchange = ccxt.okx({
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'}
        })
        
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        
        if not ohlcv or len(ohlcv) < 10:
            return None
        
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df['date'] = df['timestamp'].dt.date
        
        return df
    except Exception as e:
        st.error(f"获取数据失败: {e}")
        return None

# ================= VWAP计算方法1: 从起点累积 =================
def calculate_vwap_from_start(df, lookback_bars=200):
    """从数据起点开始累积VWAP"""
    data = df.tail(lookback_bars).copy()
    
    if len(data) < 10:
        return None, 0, "数据不足"
    
    typical = (data['high'] + data['low'] + data['close']) / 3
    volume = data['volume']
    
    cumulative_pv = (typical * volume).cumsum()
    cumulative_volume = volume.cumsum()
    cumulative_volume = cumulative_volume.replace(0, np.nan).fillna(method='ffill')
    
    vwap_series = cumulative_pv / cumulative_volume
    current_vwap = vwap_series.iloc[-1]
    
    time_span = (data['timestamp'].iloc[-1] - data['timestamp'].iloc[0]).total_seconds() / 3600
    
    return current_vwap, len(data), f"覆盖{time_span:.1f}小时"

# ================= VWAP计算方法2: 从今日0点开始 (完全修复版) =================
def calculate_vwap_from_today(df):
    """从今日0点开始计算VWAP"""
    today = datetime.now().date()
    today_data = df[df['timestamp'].dt.date == today]
    
    if len(today_data) < 2:
        # 今日数据不足，使用昨日数据补充
        yesterday = today - timedelta(days=1)
        yesterday_data = df[df['timestamp'].dt.date == yesterday]
        
        if len(yesterday_data) > 0:
            # 需要补充的K线数量
            needed = max(10 - len(today_data), 0)
            
            # 修复：使用英文变量名，修正缩进
            yesterday_tail = yesterday_data.tail(needed)
            combined_data = pd.concat([yesterday_tail, today_data])
            status = f"补充{needed}根昨日数据，共{len(combined_data)}根"
        else:
            combined_data = today_data
            status = f"仅今日数据{len(combined_data)}根"
    else:
        combined_data = today_data
        status = f"纯今日数据{len(combined_data)}根"
    
    if len(combined_data) < 2:
        return None, 0, "数据不足"
    
    typical = (combined_data['high'] + combined_data['low'] + combined_data['close']) / 3
    volume = combined_data['volume']
    
    cumulative_pv = (typical * volume).cumsum()
    cumulative_volume = volume.cumsum()
    
    vwap_series = cumulative_pv / cumulative_volume
    current_vwap = vwap_series.iloc[-1]
    
    return current_vwap, len(combined_data), status

# ================= VWAP计算方法3: 从昨日延续 =================
def calculate_vwap_continuous(df, lookback_days=7):
    """从昨日延续，包含完整周期"""
    end_date = df['timestamp'].max()
    start_date = end_date - timedelta(days=lookback_days)
    
    period_data = df[df['timestamp'] >= start_date].copy()
    
    if len(period_data) < 10:
        return None, 0, "数据不足"
    
    typical = (period_data['high'] + period_data['low'] + period_data['close']) / 3
    volume = period_data['volume']
    
    cumulative_pv = (typical * volume).cumsum()
    cumulative_volume = volume.cumsum()
    
    vwap_series = cumulative_pv / cumulative_volume
    current_vwap = vwap_series.iloc[-1]
    
    days_covered = (period_data['timestamp'].iloc[-1] - period_data['timestamp'].iloc[0]).days
    
    return current_vwap, len(period_data), f"覆盖{days_covered}天"

# ================= 多时间框架VWAP分析 =================
def analyze_vwap_all_timeframes(df, current_price):
    """分析所有时间框架的VWAP"""
    timeframes = ['1m', '5m', '15m', '1h', '4h', '1d']
    results = []
    
    for tf in timeframes:
        lookback = {
            '1m': 200,
            '5m': 200,
            '15m': 200,
            '1h': 168,
            '4h': 126,
            '1d': 90
        }.get(tf, 200)
        
        vwap, bars, status = calculate_vwap_from_start(df, lookback)
        
        if vwap:
            results.append({
                '时间框架': tf,
                'VWAP值': f"${vwap:.4f}",
                '价格>VWAP': '✅ YES' if current_price > vwap else '❌ NO',
                '使用K线': bars,
                '说明': status
            })
    
    return pd.DataFrame(results)

# ================= 绘制VWAP图表 =================
def plot_vwap_chart(df, vwap_value, method_name):
    """绘制价格和VWAP对比图"""
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        row_heights=[0.7, 0.3],
        subplot_titles=(f'价格与VWAP ({method_name})', '成交量')
    )
    
    # 蜡烛图
    fig.add_trace(
        go.Candlestick(
            x=df['timestamp'].tail(100),
            open=df['open'].tail(100),
            high=df['high'].tail(100),
            low=df['low'].tail(100),
            close=df['close'].tail(100),
            name='价格'
        ),
        row=1, col=1
    )
    
    # VWAP线
    fig.add_hline(
        y=vwap_value,
        line_dash="dash",
        line_color="purple",
        annotation_text=f"VWAP: ${vwap_value:.4f}",
        annotation_position="top right",
        row=1, col=1
    )
    
    # 成交量
    colors = ['red' if df['close'].iloc[i] < df['open'].iloc[i] else 'green' 
              for i in range(len(df.tail(100)))]
    
    fig.add_trace(
        go.Bar(
            x=df['timestamp'].tail(100),
            y=df['volume'].tail(100),
            name='成交量',
            marker_color=colors
        ),
        row=2, col=1
    )
    
    fig.update_layout(
        title=f'{symbol} {timeframe} 价格与VWAP',
        yaxis_title='价格',
        xaxis_rangeslider_visible=False,
        height=600,
        template='plotly_dark'
    )
    
    return fig

# ================= 主分析函数 =================
def analyze_market():
    """主分析函数"""
    df = fetch_market_data(symbol, timeframe, limit=500)
    
    if df is None:
        st.error("无法获取市场数据")
        return
    
    current_price = df['close'].iloc[-1]
    current_time = df['timestamp'].iloc[-1]
    
    # 显示基本信息
    st.subheader(f"📊 {symbol} - {timeframe} - {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("当前价格", f"${current_price:.4f}")
    with col2:
        st.metric("24h最高", f"${df['high'].tail(1440).max():.4f}" if timeframe == '1m' else "计算中")
    with col3:
        st.metric("24h最低", f"${df['low'].tail(1440).min():.4f}" if timeframe == '1m' else "计算中")
    with col4:
        st.metric("24h成交量", f"{df['volume'].tail(1440).sum():.0f}" if timeframe == '1m' else "计算中")
    
    # ================= VWAP三种方法对比 =================
    st.subheader("🔄 VWAP三种计算方法对比")
    
    vwap1, bars1, status1 = calculate_vwap_from_start(df, vwap_lookback)
    vwap2, bars2, status2 = calculate_vwap_from_today(df)
    vwap3, bars3, status3 = calculate_vwap_continuous(df, lookback_days=7)
    
    comparison_data = []
    
    if vwap1:
        comparison_data.append({
            '计算方法': '📈 从起点累积 (TradingView模式)',
            'VWAP值': f"${vwap1:.4f}",
            '价格>VWAP': '✅ YES' if current_price > vwap1 else '❌ NO',
            '使用K线': f"{bars1}根",
            '说明': status1
        })
    
    if vwap2:
        comparison_data.append({
            '计算方法': '📅 从今日0点开始',
            'VWAP值': f"${vwap2:.4f}",
            '价格>VWAP': '✅ YES' if current_price > vwap2 else '❌ NO',
            '使用K线': f"{bars2}根",
            '说明': status2
        })
    
    if vwap3:
        comparison_data.append({
            '计算方法': '📊 从昨日延续 (7天)',
            'VWAP值': f"${vwap3:.4f}",
            '价格>VWAP': '✅ YES' if current_price > vwap3 else '❌ NO',
            '使用K线': f"{bars3}根",
            '说明': status3
        })
    
    if comparison_data:
        df_comparison = pd.DataFrame(comparison_data)
        st.dataframe(df_comparison, use_container_width=True)
    
    # ================= 根据选择的方法显示图表 =================
    st.subheader("📈 VWAP图表分析")
    
    if vwap_method == '从起点累积 (TradingView模式)' and vwap1:
        fig = plot_vwap_chart(df, vwap1, vwap_method)
        st.plotly_chart(fig, use_container_width=True)
    elif vwap_method == '从今日0点开始' and vwap2:
        fig = plot_vwap_chart(df, vwap2, vwap_method)
        st.plotly_chart(fig, use_container_width=True)
    elif vwap_method == '从昨日延续' and vwap3:
        fig = plot_vwap_chart(df, vwap3, vwap_method)
        st.plotly_chart(fig, use_container_width=True)
    
    # ================= 多时间框架VWAP分析 =================
    st.subheader("🕐 多时间框架VWAP分析")
    
    tf_results = analyze_vwap_all_timeframes(df, current_price)
    st.dataframe(tf_results, use_container_width=True)
    
    # ================= 统计摘要 =================
    st.subheader("📊 统计摘要")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**📌 当前市场状态**")
        if vwap1 and vwap2 and vwap3:
            all_yes = all([current_price > v for v in [vwap1, vwap2, vwap3] if v])
            if all_yes:
                st.success("✅ 所有VWAP方法都显示多头信号")
            else:
                st.warning("⚠️ VWAP信号不一致，建议谨慎")
    
    with col2:
        st.markdown("**📌 最佳VWAP参数建议**")
        if timeframe == '1m':
            coverage = vwap_lookback / 60
        elif timeframe == '5m':
            coverage = vwap_lookback * 5 / 60
        elif timeframe == '15m':
            coverage = vwap_lookback * 15 / 60
        elif timeframe == '1h':
            coverage = vwap_lookback
        else:
            coverage = vwap_lookback * 4 if timeframe == '4h' else vwap_lookback * 24
            
        st.info(f"""
        对于{timeframe}图表：
        - 当前使用: {vwap_lookback}根K线 (覆盖约{coverage:.1f}小时)
        - 日内交易: 用今日0点开始
        - 趋势交易: 用7天连续数据
        """)
    
    # ================= 保存历史数据 =================
    st.session_state.vwap_history.append({
        '时间': datetime.now().strftime('%H:%M:%S'),
        '价格': current_price,
        'VWAP_起点': vwap1 if vwap1 else 0,
        'VWAP_今日': vwap2 if vwap2 else 0,
        'VWAP_7天': vwap3 if vwap3 else 0
    })
    
    if len(st.session_state.vwap_history) > 20:
        st.session_state.vwap_history = st.session_state.vwap_history[-20:]

# ================= 主循环 =================
current_time = time.time()
if st.session_state.manual_scan or (current_time - st.session_state.last_scan_time > scan_interval):
    analyze_market()
    st.session_state.last_scan_time = current_time
    st.session_state.manual_scan = False

# ================= 显示历史记录 =================
if st.session_state.vwap_history:
    with st.expander("📜 历史扫描记录"):
        hist_df = pd.DataFrame(st.session_state.vwap_history)
        st.dataframe(hist_df, use_container_width=True)

# ================= 使用说明 =================
with st.expander("ℹ️ 使用说明"):
    st.markdown("""
    ### VWAP三种计算方法
    
    1. **从起点累积 (TradingView模式)**
       - 从图表起点开始累积，匹配Pine Script的ta.vwap
       
    2. **从今日0点开始**  
       - 传统日线VWAP，数据不足时自动补充昨日数据
       
    3. **从昨日延续 (7天)**
       - 包含完整周期，适合趋势分析
    """)

# ================= 自动刷新 =================
time.sleep(2)
st.rerun()
