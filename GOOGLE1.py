import streamlit as st
import requests
import numpy as np
import time
import pandas as pd

st.set_page_config(page_title="短线扫描-简化调试版", layout="wide")
st.title("🔍 短线扫描调试版")

# ==================== 简化算法 ====================
HEADERS = {"User-Agent": "Mozilla/5.0"}

def fetch_simple(symbol):
    """简化数据获取"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1y&interval=1d"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        data = resp.json()
        
        if "chart" not in data or "result" not in data["chart"]:
            st.error(f"{symbol}: 数据格式错误")
            return None
            
        result = data["chart"]["result"][0]
        quote = result["indicators"]["quote"][0]
        
        # 简化为只取收盘价
        close_prices = [c for c in quote["close"] if c is not None]
        
        if len(close_prices) < 50:
            st.warning(f"{symbol}: 数据不足 ({len(close_prices)})")
            return None
            
        return np.array(close_prices)
    except Exception as e:
        st.error(f"{symbol}: 获取失败 - {str(e)}")
        return None

def simple_analysis(symbol):
    """简化分析"""
    close = fetch_simple(symbol)
    if close is None:
        return None
    
    # 简单计算：价格变化和基本统计
    price = close[-1]
    change = (close[-1] / close[-2] - 1) * 100 if len(close) >= 2 else 0
    
    # 简化的7日回报模拟
    if len(close) > 7:
        # 模拟过去所有7日窗口的回报
        returns = []
        for i in range(len(close) - 7):
            ret = (close[i + 7] / close[i] - 1) * 100
            returns.append(ret)
        
        returns = np.array(returns)
        positive_returns = returns[returns > 0]
        negative_returns = returns[returns <= 0]
        
        # 计算胜率和PF7
        win_rate = len(positive_returns) / len(returns) if len(returns) > 0 else 0
        
        if len(negative_returns) > 0:
            pf7 = abs(positive_returns.sum() / negative_returns.sum()) if negative_returns.sum() != 0 else 999
        else:
            pf7 = 999 if len(positive_returns) > 0 else 1
    else:
        win_rate = 0.5
        pf7 = 1.0
    
    # 简单得分（基于价格趋势）
    if len(close) > 20:
        ma20 = np.mean(close[-20:])
        above_ma = price > ma20
        trend_up = price > np.mean(close[-5:])
        recent_gain = change > 0
        score = sum([above_ma, trend_up, recent_gain])
    else:
        score = 1
    
    return {
        'symbol': symbol,
        'price': price,
        'change': change,
        'score': score,
        'prob7': win_rate,
        'pf7': pf7,
        'data_points': len(close)
    }

# ==================== 界面 ====================
st.sidebar.header("⚙️ 设置")

# 股票选择
stock_options = [
    "INSM", "WDC", "GOOGL", "AMZN", "META",
    "NVDA", "TSLA", "SNDK", "WDC", "SPY",
    "QQQ", "IWM", "GLD", "SLV", "BTC-USD"
]

selected_stocks = st.sidebar.multiselect(
    "选择要扫描的股票",
    stock_options,
    default=["AAPL", "MSFT", "SNDK"]
)

# 扫描按钮
if st.sidebar.button("🚀 开始扫描", type="primary"):
    st.session_state.scan_results = []
    st.session_state.current_index = 0

# 初始化
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = []
if 'current_index' not in st.session_state:
    st.session_state.current_index = 0

# 扫描逻辑
if selected_stocks and st.session_state.current_index < len(selected_stocks):
    symbol = selected_stocks[st.session_state.current_index]
    
    with st.spinner(f"扫描 {symbol} ({st.session_state.current_index+1}/{len(selected_stocks)})..."):
        result = simple_analysis(symbol)
        
        if result:
            st.session_state.scan_results.append(result)
            st.success(f"✓ {symbol} 扫描完成")
        
        st.session_state.current_index += 1
        
        # 短暂延迟
        time.sleep(1)
        
        # 自动刷新继续扫描
        st.rerun()

# 显示结果
if st.session_state.scan_results:
    st.subheader(f"📊 扫描结果 ({len(st.session_state.scan_results)}/{len(selected_stocks)})")
    
    df = pd.DataFrame(st.session_state.scan_results)
    
    # 筛选条件
    col1, col2 = st.columns(2)
    with col1:
        show_all = st.checkbox("显示全部", value=True)
    
    if show_all:
        filtered_df = df
    else:
        filtered_df = df[(df['pf7'] >= 3.6) | (df['prob7'] >= 0.68)]
    
    # 排序
    sort_by = st.selectbox("排序方式", ["PF7", "胜率", "价格变化", "得分"])
    if sort_by == "PF7":
        filtered_df = filtered_df.sort_values('pf7', ascending=False)
    elif sort_by == "胜率":
        filtered_df = filtered_df.sort_values('prob7', ascending=False)
    elif sort_by == "价格变化":
        filtered_df = filtered_df.sort_values('change', ascending=False)
    else:
        filtered_df = filtered_df.sort_values('score', ascending=False)
    
    # 显示
    for _, row in filtered_df.iterrows():
        col_a, col_b, col_c, col_d = st.columns(4)
        with col_a:
            st.metric(f"{row['symbol']}", f"${row['price']:.2f}", f"{row['change']:+.2f}%")
        with col_b:
            st.metric("得分", f"{row['score']}/3")
        with col_c:
            st.metric("胜率", f"{row['prob7']*100:.1f}%")
        with col_d:
            st.metric("PF7", f"{row['pf7']:.2f}")
    
    # 统计
    st.write("---")
    st.write("**统计摘要**:")
    col_stat1, col_stat2, col_stat3 = st.columns(3)
    with col_stat1:
        st.write(f"平均PF7: {df['pf7'].mean():.2f}")
    with col_stat2:
        st.write(f"平均胜率: {df['prob7'].mean()*100:.1f}%")
    with col_stat3:
        st.write(f"平均得分: {df['score'].mean():.1f}/3")
    
    # SNDK特别对比
    sndk_data = df[df['symbol'] == 'SNDK']
    if not sndk_data.empty:
        st.write("---")
        st.write("**🔬 SNDK对比分析**:")
        row = sndk_data.iloc[0]
        st.write(f"当前PF7: {row['pf7']:.2f}")
        st.write(f"对比原始第一段代码: 7.53 (差异: {row['pf7']-7.53:+.2f})")
        st.write(f"对比原始第二段代码: 6.32 (差异: {row['pf7']-6.32:+.2f})")

# 重置按钮
if st.sidebar.button("🔄 重置扫描"):
    st.session_state.scan_results = []
    st.session_state.current_index = 0
    st.rerun()

# 进度显示
if selected_stocks:
    progress = st.session_state.current_index / len(selected_stocks)
    st.sidebar.progress(progress)
    st.sidebar.write(f"进度: {st.session_state.current_index}/{len(selected_stocks)}")

# 调试信息
with st.expander("🐛 调试信息"):
    st.write("当前session state:")
    st.write(st.session_state)
    
    if st.button("测试单个股票"):
        test_symbol = st.text_input("测试股票", "AAPL")
        if test_symbol:
            result = simple_analysis(test_symbol)
            if result:
                st.write("结果:", result)

st.info("💡 这是一个简化版本，用于调试和验证核心逻辑。")
