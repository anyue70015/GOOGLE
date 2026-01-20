# 股票扫描工具 - 最小化稳定版本
# 文件名：stock_scanner_simple.py

import streamlit as st
import pandas as pd
import numpy as np
import time
import random
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# 设置页面
st.set_page_config(page_title="股票扫描工具", layout="wide")
st.title("科创板和创业板股票扫描工具")

# 初始化session state
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = []
if 'scanning' not in st.session_state:
    st.session_state.scanning = False
if 'completed' not in st.session_state:
    st.session_state.completed = False

# 1. 股票池（简化版本，使用固定列表）
def get_stock_pool():
    """返回测试用的股票列表"""
    sample_stocks = [
        ("688981", "中芯国际"),
        ("300750", "宁德时代"),
        ("688111", "金山办公"),
        ("300059", "东方财富"),
        ("688126", "沪硅产业"),
        ("300760", "迈瑞医疗"),
        ("688008", "澜起科技"),
        ("300498", "温氏股份"),
        ("688099", "晶晨股份"),
        ("300142", "沃森生物")
    ]
    return sample_stocks

# 2. 技术指标计算（简化版）
def calculate_indicators():
    """生成模拟的技术指标数据"""
    # 模拟10天的价格数据
    np.random.seed(42)
    n_days = 50
    base_price = 100
    prices = base_price + np.cumsum(np.random.randn(n_days) * 3)
    
    # 模拟指标
    macd_signal = random.choice([True, False])
    volume_signal = random.choice([True, False])
    rsi_signal = random.choice([True, False])
    atr_signal = random.choice([True, False])
    obv_signal = random.choice([True, False])
    
    signals = []
    if macd_signal: signals.append("MACD金叉")
    if volume_signal: signals.append("放量")
    if rsi_signal: signals.append("RSI强势")
    if atr_signal: signals.append("ATR放大")
    if obv_signal: signals.append("OBV上升")
    
    score = len(signals)
    win_rate = random.uniform(40, 90)
    profit_factor = random.uniform(1, 10)
    
    return {
        'score': score,
        'win_rate': round(win_rate, 1),
        'profit_factor': round(profit_factor, 2),
        'signals': "，".join(signals) if signals else "无信号",
        'price': round(base_price + random.uniform(-10, 10), 2),
        'change': round(random.uniform(-5, 5), 2)
    }

# 3. 模拟扫描一只股票
def scan_single_stock(stock_code, stock_name):
    """模拟扫描单只股票"""
    time.sleep(0.5)  # 模拟处理时间
    
    indicators = calculate_indicators()
    
    return {
        '代码': stock_code,
        '名称': stock_name,
        '价格': indicators['price'],
        '涨幅%': indicators['change'],
        '信号分': indicators['score'],
        '7日胜率%': indicators['win_rate'],
        '盈亏比': indicators['profit_factor'],
        '触发信号': indicators['signals'],
        '扫描时间': datetime.now().strftime("%H:%M:%S")
    }

# 4. 主界面
st.markdown("---")

# 控制按钮
col1, col2, col3 = st.columns(3)

with col1:
    if st.button("▶️ 开始扫描", type="primary", use_container_width=True):
        st.session_state.scanning = True
        st.session_state.completed = False
        st.session_state.scan_results = []

with col2:
    if st.button("⏸️ 暂停", use_container_width=True):
        st.session_state.scanning = False

with col3:
    if st.button("🔄 重置", use_container_width=True):
        st.session_state.scan_results = []
        st.session_state.scanning = False
        st.session_state.completed = False
        st.rerun()

st.markdown("---")

# 进度显示
if st.session_state.scanning:
    stock_pool = get_stock_pool()
    total_stocks = len(stock_pool)
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # 执行扫描
    for i, (code, name) in enumerate(stock_pool):
        if not st.session_state.scanning:
            break
            
        # 更新进度
        progress = (i + 1) / total_stocks
        progress_bar.progress(progress)
        status_text.text(f"扫描中: {code} {name} ({i+1}/{total_stocks})")
        
        # 扫描股票
        result = scan_single_stock(code, name)
        st.session_state.scan_results.append(result)
        
        # 显示优质信号
        if result['盈亏比'] > 4 and result['7日胜率%'] > 68:
            st.success(f"🎯 发现优质信号: {code} {name} | "
                      f"胜率: {result['7日胜率%']}% | "
                      f"盈亏比: {result['盈亏比']} | "
                      f"信号: {result['触发信号']}")
        
        # 轻微延迟
        time.sleep(0.1)
        
        # 每扫描3只刷新一次
        if (i + 1) % 3 == 0:
            st.rerun()
    
    # 扫描完成
    st.session_state.scanning = False
    st.session_state.completed = True
    progress_bar.progress(1.0)
    status_text.text("扫描完成！")
    st.balloons()
    st.success("✅ 所有股票扫描完成！")

# 5. 显示结果
st.markdown("---")

if st.session_state.scan_results:
    # 转换为DataFrame
    df_results = pd.DataFrame(st.session_state.scan_results)
    
    # 标记优质股票
    def categorize_stock(row):
        if row['盈亏比'] > 4 and row['7日胜率%'] > 68:
            return '🔥 优质'
        elif row['盈亏比'] > 2 and row['7日胜率%'] > 60:
            return '✅ 良好'
        else:
            return '📊 一般'
    
    df_results['评级'] = df_results.apply(categorize_stock, axis=1)
    
    # 排序
    df_results = df_results.sort_values(['盈亏比', '7日胜率%'], ascending=[False, False])
    
    st.subheader(f"扫描结果 ({len(df_results)}只股票)")
    
    # 分页显示
    tabs = st.tabs(["所有股票", "优质股票", "详细数据"])
    
    with tabs[0]:
        # 显示所有股票
        display_cols = ['评级', '代码', '名称', '价格', '涨幅%', '信号分', '7日胜率%', '盈亏比', '触发信号']
        st.dataframe(
            df_results[display_cols],
            use_container_width=True,
            hide_index=True
        )
    
    with tabs[1]:
        # 只显示优质股票
        premium_stocks = df_results[df_results['评级'] == '🔥 优质']
        if len(premium_stocks) > 0:
            st.write(f"发现 {len(premium_stocks)} 只优质股票：")
            for _, stock in premium_stocks.iterrows():
                st.info(f"**{stock['代码']} {stock['名称']}** | "
                       f"价格: {stock['价格']} | "
                       f"涨跌幅: {stock['涨幅%']}% | "
                       f"胜率: {stock['7日胜率%']}% | "
                       f"盈亏比: {stock['盈亏比']:.2f}")
        else:
            st.info("本次扫描未发现优质股票")
    
    with tabs[2]:
        # 详细数据视图
        st.write("详细数据：")
        st.dataframe(df_results, use_container_width=True)
        
        # 统计信息
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            avg_score = df_results['信号分'].mean()
            st.metric("平均信号分", f"{avg_score:.1f}")
        
        with col2:
            avg_win_rate = df_results['7日胜率%'].mean()
            st.metric("平均胜率", f"{avg_win_rate:.1f}%")
        
        with col3:
            avg_pf = df_results['盈亏比'].mean()
            st.metric("平均盈亏比", f"{avg_pf:.2f}")
        
        with col4:
            premium_count = len(df_results[df_results['评级'] == '🔥 优质'])
            st.metric("优质股票", f"{premium_count}只")
    
    # 下载功能
    st.markdown("---")
    csv_data = df_results.to_csv(index=False, encoding='utf-8-sig')
    
    st.download_button(
        label="📥 下载扫描结果 (CSV)",
        data=csv_data,
        file_name=f"stock_scan_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
        use_container_width=True
    )

else:
    if st.session_state.completed:
        st.info("扫描完成，但未发现符合条件的股票")
    else:
        st.info("点击'开始扫描'按钮开始分析股票")

# 6. 页脚
st.markdown("---")
st.caption(f"🕒 最后更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 这是一个模拟演示版本")

# 7. 侧边栏说明
with st.sidebar:
    st.title("📋 使用说明")
    
    st.markdown("""
    ### 功能说明
    
    这是一个**科创板和创业板股票扫描工具**，主要功能：
    
    1. **模拟扫描**：随机生成股票技术指标
    2. **信号识别**：基于5个技术指标评分
    3. **优质筛选**：自动识别高胜率高盈亏比股票
    4. **结果导出**：支持CSV格式下载
    
    ### 扫描指标
    
    - **MACD金叉**：动量指标
    - **成交量放大**：量价配合
    - **RSI强势**：超买超卖指标
    - **ATR放大**：波动率指标
    - **OBV上升**：资金流向指标
    
    ### 优质标准
    
    - **盈亏比 > 4**
    - **7日胜率 > 68%**
    
    ### 使用步骤
    
    1. 点击"开始扫描"
    2. 等待扫描完成
    3. 查看优质股票
    4. 下载结果CSV文件
    """)
    
    st.markdown("---")
    st.info("💡 提示：这是演示版本，实际使用时需要接入真实数据源")
