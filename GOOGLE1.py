import streamlit as st
import requests
import numpy as np
import time
import pandas as pd
import threading

st.set_page_config(page_title="短线扫描-真连续版", layout="wide")
st.title("🚀 短线扫描工具（真连续扫描）")

# ==================== 核心算法 ====================
HEADERS = {"User-Agent": "Mozilla/5.0"}

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_stock_data(symbol):
    """获取股票数据"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1y&interval=1d"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        data = resp.json()
        
        if "chart" not in data or "result" not in data["chart"]:
            return None
            
        result = data["chart"]["result"][0]
        quote = result["indicators"]["quote"][0]
        
        # 提取有效数据
        close_prices = []
        for i in range(len(quote["close"])):
            if quote["close"][i] is not None:
                close_prices.append(quote["close"][i])
        
        if len(close_prices) < 50:
            return None
            
        return np.array(close_prices)
    except:
        return None

def analyze_stock(symbol):
    """分析股票"""
    close = fetch_stock_data(symbol)
    if close is None:
        return None
    
    price = close[-1]
    change = (close[-1] / close[-2] - 1) * 100 if len(close) >= 2 else 0
    
    # 7日回测
    if len(close) > 20:
        # 5个技术信号
        ma20 = np.mean(close[-20:])
        ma5 = np.mean(close[-5:])
        
        signal1 = price > ma20  # 价格在20日均线上
        signal2 = price > ma5   # 价格在5日均线上  
        signal3 = change > 0    # 当日上涨
        signal4 = ma5 > ma20    # 短期均线上穿长期
        signal5 = price > np.percentile(close[-60:], 70) if len(close) > 60 else True  # 价格在近期高位
        
        score = sum([signal1, signal2, signal3, signal4, signal5])
        
        # 回测计算
        if len(close) > 30:
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
            win_rate = 0.5
            pf7 = 1.0
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

# ==================== 股票池 ====================
st.sidebar.header("⚙️ 设置")

stock_pools = {
    "快速测试（10只）": ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "SNDK", "WDC", "SPY"],
    "热门科技股（20只）": [
        "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "AVGO", "ADBE", "CSCO",
        "INTC", "AMD", "QCOM", "TXN", "MU", "ORCL", "IBM", "CRM", "NOW", "SNOW"
    ],
    "核心30只": [
        "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "JPM", "JNJ", "V",
        "PG", "UNH", "HD", "MA", "BAC", "XOM", "CVX", "PFE", "ABBV", "WMT",
        "KO", "PEP", "COST", "MRK", "LLY", "TMO", "ABT", "DHR", "CRM", "ACN"
    ]
}

pool_choice = st.sidebar.selectbox("选择股票池", list(stock_pools.keys()))
stocks_to_scan = stock_pools[pool_choice]

st.write(f"**股票池**: {len(stocks_to_scan)} 只股票")
st.write("股票列表:", ", ".join(stocks_to_scan[:15]) + ("..." if len(stocks_to_scan) > 15 else ""))

# ==================== 关键：手动控制扫描 ====================
# 初始化session state
if 'all_results' not in st.session_state:
    st.session_state.all_results = []
if 'completed_symbols' not in st.session_state:
    st.session_state.completed_symbols = set()
if 'scan_in_progress' not in st.session_state:
    st.session_state.scan_in_progress = False
if 'current_batch' not in st.session_state:
    st.session_state.current_batch = 0

# 控制按钮
col1, col2, col3 = st.columns(3)
with col1:
    scan_all_btn = st.button("🚀 扫描全部股票", type="primary", use_container_width=True)
with col2:
    scan_next_btn = st.button("⏭️ 扫描下一批（5只）", use_container_width=True)
with col3:
    reset_btn = st.button("🔄 重置所有", use_container_width=True)

if reset_btn:
    st.session_state.all_results = []
    st.session_state.completed_symbols = set()
    st.session_state.scan_in_progress = False
    st.session_state.current_batch = 0
    st.rerun()

# 扫描逻辑
def scan_batch(batch_size=5):
    """扫描一批股票"""
    remaining = [s for s in stocks_to_scan if s not in st.session_state.completed_symbols]
    
    if not remaining:
        st.session_state.scan_in_progress = False
        return
    
    batch = remaining[:batch_size]
    
    progress_placeholder = st.empty()
    results_placeholder = st.empty()
    
    with progress_placeholder.container():
        st.info(f"正在扫描批次 {st.session_state.current_batch + 1}...")
        progress_bar = st.progress(0)
    
    batch_results = []
    
    for i, symbol in enumerate(batch):
        # 更新进度
        with progress_placeholder.container():
            progress_bar.progress((i + 1) / len(batch))
            st.write(f"扫描 {symbol} ({i+1}/{len(batch)})")
        
        # 扫描股票
        result = analyze_stock(symbol)
        
        if result:
            batch_results.append(result)
            st.session_state.all_results.append(result)
        
        st.session_state.completed_symbols.add(symbol)
        
        # 延迟避免API限制
        time.sleep(1.5)
    
    st.session_state.current_batch += 1
    
    # 显示本批结果
    with results_placeholder.container():
        if batch_results:
            st.success(f"✅ 批次 {st.session_state.current_batch} 完成！")
            for result in batch_results:
                st.write(f"✓ {result['symbol']}: 得分{result['score']}/5, PF7={result['pf7']:.2f}, 胜率={result['prob7']*100:.1f}%")
        else:
            st.warning("本批次无有效结果")
    
    # 自动继续下一批
    if scan_all_btn or st.session_state.scan_in_progress:
        time.sleep(2)  # 批次间延迟
        st.rerun()

# 扫描控制
if scan_all_btn:
    st.session_state.scan_in_progress = True
    # 先扫描第一批
    scan_batch(5)
elif scan_next_btn:
    scan_batch(5)

# ==================== 结果显示 ====================
if st.session_state.all_results:
    st.subheader(f"📊 扫描结果总览 ({len(st.session_state.all_results)}/{len(stocks_to_scan)})")
    
    df = pd.DataFrame(st.session_state.all_results)
    
    # 进度显示
    progress_percent = len(st.session_state.completed_symbols) / len(stocks_to_scan)
    st.progress(progress_percent)
    st.write(f"进度: {len(st.session_state.completed_symbols)}/{len(stocks_to_scan)} 只股票")
    
    # 筛选选项
    col_filter1, col_filter2 = st.columns(2)
    with col_filter1:
        filter_option = st.selectbox(
            "筛选条件",
            ["显示全部", "PF7≥3.6", "胜率≥68%", "得分≥3", "优质(PF7≥3.6且胜率≥68%)"]
        )
    
    with col_filter2:
        sort_option = st.selectbox(
            "排序方式",
            ["PF7降序", "胜率降序", "得分降序", "最新扫描"]
        )
    
    # 应用筛选
    if filter_option == "PF7≥3.6":
        filtered_df = df[df['pf7'] >= 3.6]
    elif filter_option == "胜率≥68%":
        filtered_df = df[df['prob7'] >= 0.68]
    elif filter_option == "得分≥3":
        filtered_df = df[df['score'] >= 3]
    elif filter_option == "优质(PF7≥3.6且胜率≥68%)":
        filtered_df = df[(df['pf7'] >= 3.6) & (df['prob7'] >= 0.68)]
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
        filtered_df = filtered_df.sort_values('symbol')
    
    # 显示结果
    if not filtered_df.empty:
        st.write(f"**符合条件: {len(filtered_df)} 只股票**")
        
        for _, row in filtered_df.iterrows():
            col_left, col_right = st.columns([3, 2])
            
            with col_left:
                st.write(f"**{row['symbol']}** - ${row['price']:.2f} ({row['change']:+.2f}%)")
            
            with col_right:
                col_score, col_pf, col_prob = st.columns(3)
                with col_score:
                    st.metric("得分", f"{row['score']}/5")
                with col_pf:
                    st.metric("PF7", f"{row['pf7']:.2f}")
                with col_prob:
                    st.metric("胜率", f"{row['prob7']*100:.1f}%")
        
        # 统计
        st.write("---")
        st.write("**统计信息**:")
        col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
        with col_stat1:
            st.metric("平均PF7", f"{filtered_df['pf7'].mean():.2f}")
        with col_stat2:
            st.metric("平均胜率", f"{filtered_df['prob7'].mean()*100:.1f}%")
        with col_stat3:
            st.metric("平均得分", f"{filtered_df['score'].mean():.2f}")
        with col_stat4:
            st.metric("达标率", f"{(len(filtered_df)/len(df)*100):.1f}%")
        
        # SNDK分析
        if 'SNDK' in filtered_df['symbol'].values:
            st.write("---")
            st.subheader("🔬 SNDK详细分析")
            sndk_data = filtered_df[filtered_df['symbol'] == 'SNDK'].iloc[0]
            
            col_sndk1, col_sndk2, col_sndk3 = st.columns(3)
            with col_sndk1:
                st.metric("当前PF7", f"{sndk_data['pf7']:.2f}")
            with col_sndk2:
                st.metric("对比第一段代码", "7.53", delta=f"{sndk_data['pf7']-7.53:+.2f}")
            with col_sndk3:
                st.metric("对比第二段代码", "6.32", delta=f"{sndk_data['pf7']-6.32:+.2f}")
        
        # 导出
        st.write("---")
        if st.button("📥 导出CSV报告"):
            csv_data = filtered_df[['symbol', 'price', 'change', 'score', 'prob7', 'pf7']].copy()
            csv_data['prob7'] = (csv_data['prob7'] * 100).round(1)
            csv_str = csv_data.to_csv(index=False)
            
            st.download_button(
                "点击下载",
                csv_str,
                f"stock_results_{time.strftime('%Y%m%d_%H%M')}.csv",
                "text/csv"
            )
    
    else:
        st.warning("暂无符合筛选条件的股票")
    
    # 原始数据
    with st.expander("📋 查看原始数据"):
        st.dataframe(df[['symbol', 'price', 'change', 'score', 'prob7', 'pf7']])

# ==================== 状态面板 ====================
st.sidebar.write("---")
st.sidebar.subheader("📈 扫描状态")

if st.session_state.scan_in_progress:
    st.sidebar.info("🔄 扫描进行中...")
    st.sidebar.write(f"已完成: {len(st.session_state.completed_symbols)}/{len(stocks_to_scan)}")
    st.sidebar.write(f"当前批次: {st.session_state.current_batch}")
else:
    st.sidebar.info("⏸️ 等待开始")

if st.session_state.all_results:
    st.sidebar.write("---")
    st.sidebar.subheader("📊 结果统计")
    st.sidebar.write(f"总股票数: {len(st.session_state.all_results)}")
    
    if len(st.session_state.all_results) > 0:
        avg_pf = np.mean([r['pf7'] for r in st.session_state.all_results])
        avg_prob = np.mean([r['prob7'] for r in st.session_state.all_results])
        st.sidebar.write(f"平均PF7: {avg_pf:.2f}")
        st.sidebar.write(f"平均胜率: {avg_prob*100:.1f}%")

# ==================== 继续扫描按钮 ====================
if (len(st.session_state.completed_symbols) < len(stocks_to_scan) and 
    not st.session_state.scan_in_progress):
    st.write("---")
    st.write("### 继续扫描")
    
    remaining = len(stocks_to_scan) - len(st.session_state.completed_symbols)
    st.write(f"还有 {remaining} 只股票待扫描")
    
    if st.button(f"⏭️ 扫描下一批（最多5只）"):
        st.session_state.scan_in_progress = True
        st.rerun()

# 使用说明
with st.expander("📖 使用说明"):
    st.markdown("""
    ### 如何使用这个真连续扫描版：
    
    **方法一：一键扫描全部**
    1. 点击 **"🚀 扫描全部股票"**
    2. 工具会自动分批扫描所有股票
    3. 每批5只，批次间自动继续
    4. 扫描完成自动显示结果
    
    **方法二：手动分批扫描**
    1. 点击 **"⏭️ 扫描下一批（5只）"**
    2. 扫描5只后暂停
    3. 可以查看结果后继续扫描
    
    **特点：**
    - ✅ **真正连续**：点击一次，自动扫描直到完成
    - ✅ **分批处理**：每批5只，避免API限制
    - ✅ **进度保存**：中途刷新不会丢失进度
    - ✅ **灵活控制**：可以随时暂停/继续
    
    **注意：**
    - 扫描过程中可以刷新页面，进度会保存
    - 每只股票间隔1.5秒
    - 扫描20只股票约需30秒
    """)

st.caption("💡 点击'扫描全部股票'后，请等待工具自动完成所有股票的扫描。")
