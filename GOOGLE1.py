import streamlit as st
import requests
import numpy as np
import time
import pandas as pd

st.set_page_config(page_title="短线扫描-连续扫描版", layout="wide")
st.title("🚀 短线扫描工具（连续扫描）")

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
            if quote["close"][i] is not None and quote["volume"][i] is not None:
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
        # 简化的5指标系统
        # 1. 价格在20日均线上方
        ma20 = np.mean(close[-20:])
        signal1 = price > ma20
        
        # 2. 最近5日上涨
        signal2 = price > np.mean(close[-5:])
        
        # 3. 当日上涨
        signal3 = change > 0
        
        # 4. 波动率（简单判断）
        volatility = np.std(close[-20:]) / np.mean(close[-20:])
        signal4 = volatility > 0.02
        
        # 5. 成交量趋势（简化）
        if len(close) > 10:
            recent_trend = np.mean(close[-5:]) > np.mean(close[-10:-5])
            signal5 = recent_trend
        else:
            signal5 = True
        
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
            
            if len(negative) > 0 and negative.sum() != 0:
                pf7 = abs(positive.sum() / negative.sum())
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

# ==================== 连续扫描逻辑 ====================
st.sidebar.header("⚙️ 设置")

# 股票池
stock_pools = {
    "快速测试（10只）": ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "SNDK", "WDC", "SPY"],
    "热门科技股（20只）": [
        "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "AVGO", "ADBE", "CSCO",
        "INTC", "AMD", "QCOM", "TXN", "MU", "ORCL", "IBM", "CRM", "NOW", "SNOW"
    ],
    "标普500龙头（25只）": [
        "AAPL", "MSFT", "AMZN", "GOOGL", "META", "NVDA", "TSLA", "JPM", "JNJ", "V",
        "PG", "UNH", "HD", "MA", "BAC", "XOM", "CVX", "PFE", "ABBV", "WMT",
        "KO", "PEP", "COST", "MRK", "LLY"
    ]
}

pool_choice = st.sidebar.selectbox("选择股票池", list(stock_pools.keys()))
stocks_to_scan = stock_pools[pool_choice]

st.write(f"**股票池**: {len(stocks_to_scan)} 只股票")
st.write("股票列表:", ", ".join(stocks_to_scan[:15]) + ("..." if len(stocks_to_scan) > 15 else ""))

# 初始化session state
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = []
if 'scan_complete' not in st.session_state:
    st.session_state.scan_complete = False
if 'scanning' not in st.session_state:
    st.session_state.scanning = False
if 'current_stock_index' not in st.session_state:
    st.session_state.current_stock_index = 0

# 控制按钮
col1, col2, col3 = st.columns(3)
with col1:
    start_btn = st.button("🚀 开始连续扫描", type="primary", use_container_width=True)
with col2:
    pause_btn = st.button("⏸️ 暂停扫描", use_container_width=True)
with col3:
    reset_btn = st.button("🔄 重置", use_container_width=True)

if start_btn:
    st.session_state.scanning = True
    st.session_state.scan_complete = False
    st.session_state.current_stock_index = 0
    st.session_state.scan_results = []

if pause_btn:
    st.session_state.scanning = False

if reset_btn:
    st.session_state.scan_results = []
    st.session_state.scan_complete = False
    st.session_state.scanning = False
    st.session_state.current_stock_index = 0
    st.rerun()

# 连续扫描逻辑
if st.session_state.scanning and not st.session_state.scan_complete:
    # 创建进度区域
    progress_container = st.container()
    
    with progress_container:
        # 显示进度
        progress = st.session_state.current_stock_index / len(stocks_to_scan)
        st.progress(progress)
        
        # 扫描当前股票
        if st.session_state.current_stock_index < len(stocks_to_scan):
            current_symbol = stocks_to_scan[st.session_state.current_stock_index]
            
            with st.spinner(f"扫描 {current_symbol} ({st.session_state.current_stock_index+1}/{len(stocks_to_scan)})..."):
                result = analyze_stock(current_symbol)
                
                if result:
                    st.session_state.scan_results.append(result)
                    st.success(f"✓ {current_symbol}: 得分{result['score']}/5, PF7={result['pf7']:.2f}")
                else:
                    st.warning(f"✗ {current_symbol}: 数据获取失败")
                
                # 移动到下一只股票
                st.session_state.current_stock_index += 1
                
                # 避免API限制，稍微延迟
                time.sleep(1.5)
                
                # 自动刷新继续扫描
                st.rerun()
        else:
            # 扫描完成
            st.session_state.scan_complete = True
            st.session_state.scanning = False
            st.balloons()
            st.success("🎉 扫描完成！")

# ==================== 结果显示 ====================
if st.session_state.scan_results:
    st.subheader(f"📊 扫描结果 ({len(st.session_state.scan_results)}/{len(stocks_to_scan)})")
    
    df = pd.DataFrame(st.session_state.scan_results)
    
    # 筛选选项
    filter_option = st.radio(
        "筛选条件",
        ["显示全部", "PF7≥3.6 或 胜率≥68%", "得分≥3", "PF7≥5.0"],
        horizontal=True
    )
    
    if filter_option == "PF7≥3.6 或 胜率≥68%":
        filtered_df = df[(df['pf7'] >= 3.6) | (df['prob7'] >= 0.68)]
    elif filter_option == "得分≥3":
        filtered_df = df[df['score'] >= 3]
    elif filter_option == "PF7≥5.0":
        filtered_df = df[df['pf7'] >= 5.0]
    else:
        filtered_df = df
    
    # 排序
    sort_by = st.selectbox("排序方式", ["PF7降序", "胜率降序", "得分降序", "价格变化"])
    
    if sort_by == "PF7降序":
        filtered_df = filtered_df.sort_values('pf7', ascending=False)
    elif sort_by == "胜率降序":
        filtered_df = filtered_df.sort_values('prob7', ascending=False)
    elif sort_by == "得分降序":
        filtered_df = filtered_df.sort_values('score', ascending=False)
    else:
        filtered_df = filtered_df.sort_values('change', ascending=False)
    
    # 显示结果
    if not filtered_df.empty:
        for _, row in filtered_df.iterrows():
            # 颜色编码
            score_color = "#00cc00" if row['score'] >= 4 else "#ff9900" if row['score'] >= 3 else "#ff4444"
            pf_color = "#00cc00" if row['pf7'] >= 5 else "#ff9900" if row['pf7'] >= 3 else "#ff4444"
            
            st.markdown(f"""
            <div style="border-left: 5px solid {score_color}; padding: 12px; margin: 8px 0; background: #f8f9fa;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <strong style="font-size: 18px;">{row['symbol']}</strong>
                        <span style="margin-left: 15px;">${row['price']:.2f} ({row['change']:+.2f}%)</span>
                    </div>
                    <div style="text-align: right;">
                        <span style="background-color: {score_color}; color: white; padding: 3px 10px; border-radius: 12px; margin-right: 10px;">
                            得分: {row['score']}/5
                        </span>
                        <span style="background-color: {pf_color}; color: white; padding: 3px 10px; border-radius: 12px;">
                            PF7: {row['pf7']:.2f}
                        </span>
                    </div>
                </div>
                <div style="margin-top: 6px; font-size: 14px; color: #666;">
                    胜率: <strong>{row['prob7']*100:.1f}%</strong> | 
                    数据点: {row['data_points']}
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
            st.subheader("🔬 SNDK详细分析")
            sndk_row = filtered_df[filtered_df['symbol'] == 'SNDK'].iloc[0]
            
            col_sndk1, col_sndk2, col_sndk3 = st.columns(3)
            with col_sndk1:
                st.metric("当前PF7", f"{sndk_row['pf7']:.2f}")
            with col_sndk2:
                st.metric("对比原始第一段", "7.53", delta=f"{sndk_row['pf7']-7.53:+.2f}")
            with col_sndk3:
                st.metric("对比原始第二段", "6.32", delta=f"{sndk_row['pf7']-6.32:+.2f}")
        
        # 导出功能
        st.write("---")
        st.subheader("📥 导出结果")
        
        if st.button("生成CSV报告"):
            csv_data = filtered_df[['symbol', 'price', 'change', 'score', 'prob7', 'pf7']].copy()
            csv_data['prob7'] = (csv_data['prob7'] * 100).round(1)
            csv_str = csv_data.to_csv(index=False)
            
            st.download_button(
                "下载CSV文件",
                csv_str,
                f"stock_scan_{time.strftime('%Y%m%d_%H%M')}.csv",
                "text/csv"
            )
        
        # 数据表格
        with st.expander("📋 查看数据表格"):
            st.dataframe(
                filtered_df[['symbol', 'price', 'change', 'score', 'prob7', 'pf7']],
                use_container_width=True
            )
    else:
        st.warning("没有找到符合筛选条件的股票")

# 状态显示
st.sidebar.write("---")
st.sidebar.subheader("📈 扫描状态")

if st.session_state.scanning:
    st.sidebar.info("🔄 扫描中...")
elif st.session_state.scan_complete:
    st.sidebar.success("✅ 扫描完成")
else:
    st.sidebar.info("⏸️ 等待开始")

if st.session_state.scan_results:
    success_rate = len(st.session_state.scan_results) / st.session_state.current_stock_index * 100
    st.sidebar.metric("成功率", f"{success_rate:.1f}%")
    st.sidebar.metric("已扫描", f"{st.session_state.current_stock_index}/{len(stocks_to_scan)}")

# 使用说明
with st.expander("📖 使用说明"):
    st.markdown("""
    ### 如何使用：
    1. **选择股票池**：从侧边栏选择要扫描的股票组
    2. **点击"开始连续扫描"**：工具会自动连续扫描所有股票
    3. **可以随时暂停或重置**
    4. **查看结果**：扫描完成后会自动显示结果
    
    ### 特点：
    - ✅ **连续扫描**：一次点击自动扫描所有股票
    - ✅ **实时进度**：显示扫描进度和状态
    - ✅ **筛选排序**：多种筛选和排序方式
    - ✅ **SNDK对比**：特别显示与原始代码的对比
    
    ### 注意：
    - 扫描过程中请保持页面打开
    - 每只股票间隔1.5秒，避免API限制
    - 扫描速度约40只/分钟
    """)

st.caption("💡 点击'开始连续扫描'后，工具会自动扫描所有股票，无需手动继续。")
