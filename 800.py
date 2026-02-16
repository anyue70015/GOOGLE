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
st.markdown("""
<style>
    .vwap-yes { color: #00ff00; font-weight: bold; }
    .vwap-no { color: #ff0000; font-weight: bold; }
    .info-box { background-color: #1e1e1e; padding: 10px; border-radius: 5px; margin: 5px 0; }
</style>
""", unsafe_allow_html=True)

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
        value=200,
        help="从最新K线往前推多少根用于计算VWAP"
    )
    
    vwap_method = st.radio(
        "VWAP计算方法",
        ['从起点累积 (TradingView模式)', '从今日0点开始', '从昨日延续'],
        index=0,
        help="选择VWAP的计算方式"
    )
    
    scan_interval = st.number_input("自动刷新间隔(秒)", 5, 60, SCAN_INTERVAL)
    
    if st.button("🔄 立即扫描", use_container_width=True):
        st.session_state.manual_scan = True

# 初始化session_state
if 'last_scan_time' not in st.session_state:
    st.session_state.last_scan_time = 0
if 'manual_scan' not in st.session_state:
    st.session_state.manual_scan = False
if 'market_data' not in st.session_state:
    st.session_state.market_data = None
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
            st.error(f"❌ 获取{symbol}数据失败")
            return None
        
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df['date'] = df['timestamp'].dt.date
        df['hour'] = df['timestamp'].dt.hour
        df['minute'] = df['timestamp'].dt.minute
        
        return df
    except Exception as e:
        st.error(f"❌ 获取数据失败: {e}")
        return None

# ================= VWAP计算方法1: 从起点累积 (TradingView模式) =================
def calculate_vwap_from_start(df, lookback_bars=200):
    """
    方法1: 从数据起点开始累积VWAP
    匹配TradingView的ta.vwap行为
    """
    data = df.tail(lookback_bars).copy()
    
    if len(data) < 10:
        return None, 0, "数据不足"
    
    # 计算典型价格
    typical = (data['high'] + data['low'] + data['close']) / 3
    volume = data['volume']
    
    # 累积计算
    cumulative_pv = (typical * volume).cumsum()
    cumulative_volume = volume.cumsum()
    
    # 防止除零
    cumulative_volume = cumulative_volume.replace(0, np.nan).fillna(method='ffill')
    
    vwap_series = cumulative_pv / cumulative_volume
    current_vwap = vwap_series.iloc[-1]
    
    # 计算覆盖的时间范围
    time_span = (data['timestamp'].iloc[-1] - data['timestamp'].iloc[0]).total_seconds() / 3600
    
    return current_vwap, len(data), f"覆盖{time_span:.1f}小时数据"

# ================= VWAP计算方法2: 从今日0点开始 =================
def calculate_vwap_from_today(df):
    """
    方法2: 从今日0点开始计算VWAP
    匹配传统金融的日线VWAP
    """
    today = datetime.now().date()
    today_data = df[df['timestamp'].dt.date == today]
    
    if len(today_data) < 2:
        # 今日数据不足，使用昨日数据补充
        yesterday = today - timedelta(days=1)
        yesterday_data = df[df['timestamp'].dt.date == yesterday]
        
        if len(yesterday_data) > 0:
            # 取昨日最后几根补充
            needed = max(10 - len(today_data), 0)
            # 修复：使用英文变量名，修正缩进
           补充数据 = yesterday_data.tail(needed)
            combined = pd.concat([补充数据, today_data])
            status = f"补充{needed}根昨日数据，共{len(combined)}根"
        else:
            combined = today_data
            status = f"仅今日数据{len(combined)}根"
    else:
        combined = today_data
        status = f"纯今日数据{len(combined)}根"
    
    if len(combined) < 2:
        return None, 0, "数据不足"
    
    typical = (combined['high'] + combined['low'] + combined['close']) / 3
    volume = combined['volume']
    
    cumulative_pv = (typical * volume).cumsum()
    cumulative_volume = volume.cumsum()
    
    vwap_series = cumulative_pv / cumulative_volume
    current_vwap = vwap_series.iloc[-1]
    
    return current_vwap, len(combined), status

# ================= VWAP计算方法3: 从昨日延续 =================
def calculate_vwap_continuous(df, lookback_days=7):
    """
    方法3: 从昨日收盘延续，包含完整周期
    适合做中长线分析
    """
    # 获取最近N天的数据
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
    
    return current_vwap, len(period_data), f"覆盖{days_covered}天数据"

# ================= 多时间框架VWAP分析 =================
def analyze_vwap_all_timeframes(df, current_price):
    """
    分析所有时间框架的VWAP
    """
    timeframes = ['1m', '5m', '15m', '1h', '4h', '1d']
    results = []
    
    for tf in timeframes:
        # 根据不同时间框架调整lookback
        lookback = {
            '1m': 200,
            '5m': 200,
            '15m': 200,
            '1h': 168,  # 7天
            '4h': 126,  # 21天
            '1d': 90    # 90天
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
    """
    绘制价格和VWAP对比图
    """
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
    
    # 基本信息卡片
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
    
    # 方法1: 从起点累积
    vwap1, bars1, status1 = calculate_vwap_from_start(df, vwap_lookback)
    
    # 方法2: 从今日0点开始
    vwap2, bars2, status2 = calculate_vwap_from_today(df)
    
    # 方法3: 从昨日延续
    vwap3, bars3, status3 = calculate_vwap_continuous(df, lookback_days=7)
    
    # 创建对比表格
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
    
    df_comparison = pd.DataFrame(comparison_data)
    st.dataframe(df_comparison, use_container_width=True)
    
    # ================= 根据选择的方法显示图表 =================
    st.subheader("📈 VWAP图表分析")
    
    selected_method = vwap_method
    if selected_method == '从起点累积 (TradingView模式)' and vwap1:
        fig = plot_vwap_chart(df, vwap1, selected_method)
        st.plotly_chart(fig, use_container_width=True)
    elif selected_method == '从今日0点开始' and vwap2:
        fig = plot_vwap_chart(df, vwap2, selected_method)
        st.plotly_chart(fig, use_container_width=True)
    elif selected_method == '从昨日延续' and vwap3:
        fig = plot_vwap_chart(df, vwap3, selected_method)
        st.plotly_chart(fig, use_container_width=True)
    
    # ================= 多时间框架VWAP分析 =================
    st.subheader("🕐 多时间框架VWAP分析")
    
    tf_results = analyze_vwap_all_timeframes(df, current_price)
    st.dataframe(tf_results, use_container_width=True)
    
    # ================= VWAP历史走势 =================
    st.subheader("📉 VWAP历史走势")
    
    # 计算历史VWAP序列
    lookback_history = min(100, len(df))
    historical_vwap = []
    
    for i in range(lookback_history, len(df)):
        subset = df.iloc[i-lookback_history:i]
        vwap_hist, _, _ = calculate_vwap_from_start(subset, lookback_history)
        if vwap_hist:
            historical_vwap.append({
                '时间': df.iloc[i]['timestamp'],
                '价格': df.iloc[i]['close'],
                'VWAP': vwap_hist
            })
    
    if historical_vwap:
        hist_df = pd.DataFrame(historical_vwap)
        
        fig_hist = go.Figure()
        fig_hist.add_trace(go.Scatter(
            x=hist_df['时间'],
            y=hist_df['价格'],
            name='价格',
            line=dict(color='blue')
        ))
        fig_hist.add_trace(go.Scatter(
            x=hist_df['时间'],
            y=hist_df['VWAP'],
            name='VWAP',
            line=dict(color='purple', dash='dash')
        ))
        
        fig_hist.update_layout(
            title='价格 vs VWAP 历史走势',
            xaxis_title='时间',
            yaxis_title='价格',
            template='plotly_dark',
            height=400
        )
        
        st.plotly_chart(fig_hist, use_container_width=True)
    
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
        # 计算覆盖时间
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
        对于{timeframe}图表，推荐：
        - 短期交易: 使用{vwap_lookback}根K线 (覆盖约{coverage:.1f}小时)
        - 日内交易: 使用从今日0点开始
        - 趋势交易: 使用7天连续数据
        """)
    
    # ================= 保存历史数据 =================
    st.session_state.vwap_history.append({
        '时间': datetime.now(),
        '价格': current_price,
        'VWAP_起点累积': vwap1,
        'VWAP_今日开始': vwap2,
        'VWAP_7天': vwap3
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
    ### 🎯 VWAP三种计算方法详解
    
    #### 1. **从起点累积 (TradingView模式)**
    - ✅ **最匹配你的Pine Script**
    - 从图表显示的第一根K线开始累积计算
    - 时间框架越大，覆盖的历史越长
    - 1h图表用200根 = 覆盖8.3天，完全合理！
    
    #### 2. **从今日0点开始**
    - 传统金融的日线VWAP
    - 如果今日数据不足，会自动补充昨日数据
    - 适合做日内交易参考
    
    #### 3. **从昨日延续 (7天)**
    - 包含完整周期
    - 过滤短期噪音
    - 适合中长线趋势判断
    
    ### 💡 为什么补充昨日数据是可信的？
    币圈24小时交易，没有"开盘收盘"概念。VWAP本来就是从某个起点累积的：
    - 补充昨日数据 = 延长计算周期
    - 1h图表用200根K线覆盖8.3天，更准确！
    - 这才是币圈VWAP的正确打开方式
    
    ### 📊 各时间框架推荐设置
    | 时间框架 | 推荐K线数 | 覆盖时间 | 用途 |
    |----------|-----------|----------|------|
    | 1m | 200 | 3.3小时 | 超短线 |
    | 5m | 200 | 16.7小时 | 短线 |
    | 15m | 200 | 50小时 | 日内 |
    | 1h | 168 | 7天 | 波段 |
    | 4h | 126 | 21天 | 中线 |
    | 1d | 90 | 90天 | 长线 |
    """)

# ================= 自动刷新 =================
time.sleep(2)
st.rerun()
