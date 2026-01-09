import streamlit as st
import numpy as np
import pandas as pd
import time
import datetime
import threading
from queue import Queue, Empty
import warnings
warnings.filterwarnings('ignore')

st.set_page_config(page_title="罗素2000 模拟回测扫描", layout="wide")
st.title("🚀 罗素2000 模拟回测极速扫描器")

# ==================== 初始化会话状态 ====================
def init_session_state():
    """初始化所有会话状态"""
    if 'initialized' not in st.session_state:
        st.session_state.initialized = True
        st.session_state.scan_results = []
        st.session_state.scanning = False
        st.session_state.progress = 0
        st.session_state.total_symbols = 2000
        st.session_state.current_symbol = ""
        st.session_state.last_update = time.time()
        st.session_state.result_queue = Queue()
        st.session_state.failed_count = 0
        st.session_state.start_time = None
        st.session_state.period = "1年"
        st.session_state.all_tickers = []
        st.session_state.completed_count = 0

init_session_state()

# ==================== 生成模拟股票数据 ====================
def generate_simulated_tickers():
    """生成模拟的罗素2000股票列表"""
    if st.session_state.all_tickers:
        return st.session_state.all_tickers
    
    # 基础股票列表
    base_tickers = [
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'JPM', 'V', 'JNJ',
        'WMT', 'PG', 'HD', 'BAC', 'MA', 'DIS', 'NFLX', 'ADBE', 'CRM', 'PYPL',
        'ABT', 'PEP', 'CMCSA', 'TMO', 'AVGO', 'COST', 'DHR', 'MCD', 'NKE', 'LIN',
        'INTC', 'CSCO', 'PFE', 'T', 'VZ', 'MRK', 'ABBV', 'BMY', 'UNH', 'LLY',
        'AMD', 'QCOM', 'TXN', 'AMGN', 'GILD', 'CVX', 'XOM', 'COP', 'SLB', 'EOG'
    ]
    
    # 生成2000只股票
    all_tickers = []
    for i in range(2000):
        if i < len(base_tickers):
            all_tickers.append(base_tickers[i])
        else:
            # 生成模拟股票代码
            import random
            import string
            prefix = random.choice(['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M'])
            suffix = random.choice(['', 'A', 'B', 'C', 'D', 'E'])
            num = random.randint(10, 999)
            ticker = f"{prefix}{num:03d}{suffix}"
            all_tickers.append(ticker)
    
    st.session_state.all_tickers = all_tickers[:2000]
    return st.session_state.all_tickers

# ==================== 模拟回测计算（完全本地） ====================
def simulate_stock_analysis(symbol):
    """模拟股票分析 - 完全本地计算，不依赖网络"""
    try:
        # 随机生成模拟价格（$10-$500）
        base_price = np.random.uniform(10, 500)
        
        # 生成价格变化（-5% 到 +5%）
        daily_change = np.random.uniform(-0.05, 0.05)
        price = base_price * (1 + daily_change)
        
        # 模拟价格变化
        change = daily_change * 100
        
        # ========== 模拟技术指标 ==========
        # 1. 随机生成得分（0-5），但倾向于3-4
        score = min(5, max(0, np.random.normal(3.5, 1.0)))
        score = int(round(score))
        
        # 2. 模拟PF7（盈利因子）基于得分
        if score >= 4:
            pf7 = np.random.uniform(4.0, 8.0)  # 高分股有高PF7
        elif score >= 3:
            pf7 = np.random.uniform(2.5, 5.0)
        else:
            pf7 = np.random.uniform(1.0, 3.0)
        
        # 3. 模拟7日胜率（基于PF7和得分）
        base_prob = 0.5 + (score / 10) + (pf7 / 20)
        prob7 = min(0.95, max(0.3, base_prob))
        
        # 4. 模拟RSI
        if score >= 4:
            rsi = np.random.uniform(60, 80)
        elif score >= 3:
            rsi = np.random.uniform(50, 70)
        else:
            rsi = np.random.uniform(30, 60)
        
        # 5. 模拟波动率
        if score >= 4:
            volatility = np.random.uniform(20, 40)  # 高分股通常波动较大
        else:
            volatility = np.random.uniform(10, 30)
        
        # 6. 模拟动量
        if score >= 4:
            momentum = np.random.uniform(5, 20)
        elif score >= 3:
            momentum = np.random.uniform(-5, 10)
        else:
            momentum = np.random.uniform(-10, 5)
        
        # 7. 模拟最大回撤
        if score >= 4:
            max_drawdown = np.random.uniform(5, 15)
        elif score >= 3:
            max_drawdown = np.random.uniform(10, 25)
        else:
            max_drawdown = np.random.uniform(15, 35)
        
        # 8. 模拟是否在20日均线上
        above_ma20 = "是" if np.random.random() > 0.3 else "否"
        
        # 9. 模拟数据点数（一年约252个交易日）
        data_points = np.random.randint(200, 252)
        
        return {
            'symbol': symbol,
            'price': round(price, 2),
            'change': round(change, 2),
            'score': score,
            'prob7': round(prob7, 3),
            'pf7': round(pf7, 2),
            'rsi': round(rsi, 1),
            'volatility': round(volatility, 1),
            'max_drawdown': round(max_drawdown, 1),
            'above_ma20': above_ma20,
            'momentum_20d': round(momentum, 1),
            'data_points': data_points,
            'scan_time': datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        }
        
    except Exception as e:
        print(f"模拟{symbol}时出错: {e}")
        return None

# ==================== 极速批量扫描 ====================
def ultra_fast_scan():
    """极速扫描 - 完全本地，无需网络"""
    tickers = generate_simulated_tickers()
    total = len(tickers)
    
    # 分批处理以显示进度
    batch_size = 100
    for batch_start in range(0, total, batch_size):
        if not st.session_state.scanning:
            break
            
        batch_end = min(batch_start + batch_size, total)
        batch_tickers = tickers[batch_start:batch_end]
        
        # 处理当前批次
        for i, symbol in enumerate(batch_tickers):
            if not st.session_state.scanning:
                break
                
            # 模拟分析（极快，约1毫秒）
            result = simulate_stock_analysis(symbol)
            if result:
                st.session_state.result_queue.put(('result', result))
            
            # 更新进度
            completed = batch_start + i + 1
            st.session_state.progress = (completed / total) * 100
            st.session_state.current_symbol = symbol
            st.session_state.completed_count = completed
            
            # 每50个结果强制更新一次显示
            if completed % 50 == 0:
                st.session_state.last_update = time.time()
                time.sleep(0.001)  # 短暂让出控制权
        
        # 批次间短暂休息
        if st.session_state.scanning:
            time.sleep(0.01)

# ==================== 启动扫描线程 ====================
def start_scan_thread():
    """启动扫描线程"""
    if st.session_state.scanning:
        return
    
    # 重置状态
    st.session_state.scanning = True
    st.session_state.scan_results = []
    st.session_state.progress = 0
    st.session_state.completed_count = 0
    st.session_state.start_time = time.time()
    st.session_state.failed_count = 0
    
    # 启动扫描线程
    def scan_thread():
        try:
            ultra_fast_scan()
        finally:
            st.session_state.scanning = False
            st.session_state.progress = 100
            st.session_state.result_queue.put(('complete', None))
            
            # 计算总耗时
            total_time = time.time() - st.session_state.start_time
            st.session_state.result_queue.put(('stats', f"总耗时: {total_time:.2f}秒"))
    
    thread = threading.Thread(target=scan_thread, daemon=True)
    thread.start()
    st.toast("🚀 开始极速扫描2000只股票！", icon="🚀")

# ==================== 处理结果队列 ====================
def process_results():
    """处理结果队列"""
    processed = 0
    while True:
        try:
            item_type, data = st.session_state.result_queue.get_nowait()
            
            if item_type == 'result':
                st.session_state.scan_results.append(data)
                processed += 1
            elif item_type == 'complete':
                st.toast("✅ 扫描完成！", icon="✅")
            elif item_type == 'stats':
                st.toast(f"📊 {data}", icon="📊")
                
        except Empty:
            break
    
    return processed

# ==================== 主界面布局 ====================
# 控制面板
st.sidebar.header("⚡ 控制面板")

# 扫描控制按钮
st.sidebar.subheader("🚀 扫描控制")

if st.sidebar.button("🚀 开始极速扫描", type="primary", use_container_width=True):
    start_scan_thread()
    st.rerun()

col1, col2 = st.sidebar.columns(2)
with col1:
    if st.button("⏸️ 暂停", use_container_width=True):
        st.session_state.scanning = False
        st.rerun()
with col2:
    if st.button("🔄 重置", use_container_width=True):
        st.session_state.scan_results = []
        st.session_state.scanning = False
        st.session_state.progress = 0
        st.rerun()

st.sidebar.divider()

# 筛选条件
st.sidebar.subheader("🎯 筛选条件")
min_score = st.sidebar.slider("最低得分", 0, 5, 3, 1)
min_pf7 = st.sidebar.slider("最低PF7", 0.0, 10.0, 3.0, 0.1)
min_prob = st.sidebar.slider("最低胜率%", 0, 100, 60, 1)

st.sidebar.divider()

# 排序方式
st.sidebar.subheader("📈 排序方式")
sort_options = ["最新", "PF7", "胜率", "得分", "价格变化"]
sort_by = st.sidebar.radio("排序", sort_options, index=1, horizontal=True)

# ==================== 进度显示 ====================
st.header("📊 扫描进度 - 2000只股票")

# 进度统计
col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    status = "🟢 扫描中" if st.session_state.scanning else "✅ 完成" if st.session_state.progress == 100 else "⏸️ 待命"
    st.metric("状态", status)

with col2:
    st.metric("进度", f"{st.session_state.progress:.1f}%")
    st.progress(st.session_state.progress / 100)

with col3:
    current = st.session_state.current_symbol or "等待开始"
    st.metric("当前股票", current[:10])

with col4:
    scanned = st.session_state.completed_count
    total = st.session_state.total_symbols
    st.metric("已扫描", f"{scanned}/{total}")

with col5:
    st.metric("速度", f"{scanned/max(1, time.time()-st.session_state.start_time):.0f}/秒" 
             if st.session_state.start_time and st.session_state.scanning else "-")

# 耗时统计
if st.session_state.start_time and st.session_state.scanning:
    elapsed = time.time() - st.session_state.start_time
    if st.session_state.progress > 0:
        remaining = (elapsed / st.session_state.progress) * (100 - st.session_state.progress)
    else:
        remaining = 0
    
    st.caption(f"⏱️ 已运行: {elapsed:.1f}秒 | 预计剩余: {remaining:.1f}秒 | 已找到: {len(st.session_state.scan_results)}只")

st.divider()

# ==================== 实时结果区域 ====================
# 处理新结果
new_results = process_results()
if new_results > 0 and st.session_state.scanning:
    st.toast(f"🔄 更新了 {new_results} 个新结果", icon="🔄")

# 显示结果
if st.session_state.scan_results:
    df = pd.DataFrame(st.session_state.scan_results)
    
    if len(df) > 0:
        # 筛选
        mask = (df['score'] >= min_score) & (df['pf7'] >= min_pf7) & (df['prob7'] >= min_prob/100)
        filtered = df[mask].copy()
        
        if len(filtered) > 0:
            # 排序
            if sort_by == "PF7":
                filtered = filtered.sort_values("pf7", ascending=False)
            elif sort_by == "胜率":
                filtered = filtered.sort_values("prob7", ascending=False)
            elif sort_by == "得分":
                filtered = filtered.sort_values("score", ascending=False)
            elif sort_by == "价格变化":
                filtered = filtered.sort_values("change", ascending=False)
            else:  # 最新
                filtered = filtered.sort_values("scan_time", ascending=False)
            
            # 显示统计
            st.subheader(f"🎯 发现 {len(filtered)} 只优质股票（共{len(df)}只）")
            
            # 分页显示
            page_size = 20
            total_pages = max(1, (len(filtered) + page_size - 1) // page_size)
            
            page = st.number_input("页码", min_value=1, max_value=total_pages, value=1)
            start_idx = (page - 1) * page_size
            end_idx = min(start_idx + page_size, len(filtered))
            
            # 显示当前页
            for idx in range(start_idx, end_idx):
                row = filtered.iloc[idx]
                
                # 颜色编码
                if row['score'] >= 4:
                    color = "#22c55e"
                    icon = "🔥"
                    badge = "优质"
                elif row['score'] >= 3:
                    color = "#f59e0b"
                    icon = "⚡"
                    badge = "良好"
                else:
                    color = "#ef4444"
                    icon = "📊"
                    badge = "一般"
                
                # 显示卡片
                with st.container():
                    # 使用columns布局
                    cols = st.columns([1, 3, 1])
                    
                    with cols[0]:
                        st.markdown(f"""
                        <div style="text-align: center; padding: 15px; border-radius: 10px; background: {color}15; border: 2px solid {color};">
                            <div style="font-size: 28px; font-weight: bold; color: {color};">
                                {icon} {row['score']}/5
                            </div>
                            <div style="font-size: 12px; color: #666; margin-top: 5px;">{badge}</div>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    with cols[1]:
                        st.markdown(f"""
                        <div style="padding: 10px;">
                            <div style="display: flex; align-items: center; gap: 15px; margin-bottom: 10px;">
                                <span style="font-size: 24px; font-weight: bold; color: #333;">{row['symbol']}</span>
                                <span style="font-size: 22px; font-weight: bold; color: #222;">${row['price']:,.2f}</span>
                                <span style="color: {'#22c55e' if row['change'] >= 0 else '#ef4444'}; 
                                      font-weight: bold; font-size: 20px; padding: 2px 8px; 
                                      border-radius: 5px; background: {'#22c55e' if row['change'] >= 0 else '#ef4444'}15;">
                                    {row['change']:+.2f}%
                                </span>
                            </div>
                            <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px;">
                                <div>
                                    <div style="font-size: 12px; color: #666;">PF7指数</div>
                                    <div style="font-size: 20px; font-weight: bold; color: {color}">{row['pf7']:.2f}</div>
                                </div>
                                <div>
                                    <div style="font-size: 12px; color: #666;">7日胜率</div>
                                    <div style="font-size: 20px; font-weight: bold;">{row['prob7']*100:.1f}%</div>
                                </div>
                                <div>
                                    <div style="font-size: 12px; color: #666;">RSI指标</div>
                                    <div style="font-size: 20px;">{row['rsi']:.1f}</div>
                                </div>
                                <div>
                                    <div style="font-size: 12px; color: #666;">波动率</div>
                                    <div style="font-size: 20px;">{row['volatility']:.1f}%</div>
                                </div>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    with cols[2]:
                        st.markdown(f"""
                        <div style="text-align: right; padding: 10px;">
                            <div style="font-size: 12px; color: #666; margin-bottom: 5px;">
                                ⏰ {row['scan_time']}
                            </div>
                            <div style="font-size: 11px; color: #888; margin-bottom: 3px;">
                                📈 动量: {row['momentum_20d']:.1f}%
                            </div>
                            <div style="font-size: 11px; color: #888; margin-bottom: 3px;">
                                📊 均线上: {row['above_ma20']}
                            </div>
                            <div style="font-size: 11px; color: #888;">
                                📋 数据点: {row['data_points']}
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    st.divider()
            
            # 分页信息
            st.caption(f"📄 第 {page}/{total_pages} 页 | 📊 显示 {start_idx+1}-{end_idx} 条 | 🎯 共 {len(filtered)} 只优质股票")
            
            # 导出功能
            st.subheader("📤 导出结果")
            
            col_exp1, col_exp2 = st.columns(2)
            
            with col_exp1:
                if st.button("📄 生成TXT报告", type="primary", use_container_width=True):
                    txt_content = f"罗素2000模拟扫描报告\n"
                    txt_content += "=" * 70 + "\n"
                    txt_content += f"扫描时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    txt_content += f"扫描总数: {len(df)} 只股票\n"
                    txt_content += f"优质股票: {len(filtered)} 只\n"
                    txt_content += f"筛选条件: 得分≥{min_score}, PF7≥{min_pf7}, 胜率≥{min_prob}%\n"
                    txt_content += "=" * 70 + "\n\n"
                    
                    # 添加详细数据
                    for idx in range(min(200, len(filtered))):  # 限制前200只
                        row = filtered.iloc[idx]
                        txt_content += f"{idx+1:4d}. {row['symbol']:8s} | 价格: ${row['price']:8.2f} ({row['change']:+7.2f}%)\n"
                        txt_content += f"      得分: {row['score']}/5 | PF7: {row['pf7']:6.2f} | 胜率: {row['prob7']*100:6.1f}%\n"
                        txt_content += f"      RSI: {row['rsi']:6.1f} | 波动: {row['volatility']:6.1f}% | 动量: {row['momentum_20d']:+6.1f}%\n"
                        txt_content += f"      回撤: {row['max_drawdown']:6.1f}% | 均线上: {row['above_ma20']:3s} | 数据: {row['data_points']}\n"
                        txt_content += "-" * 60 + "\n"
                    
                    # 提供下载
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    st.download_button(
                        label="⬇️ 下载TXT文件",
                        data=txt_content,
                        file_name=f"russell2000_simulation_{timestamp}.txt",
                        mime="text/plain",
                        use_container_width=True
                    )
            
            with col_exp2:
                if st.button("📊 生成CSV文件", use_container_width=True):
                    csv_data = filtered.to_csv(index=False)
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    st.download_button(
                        label="⬇️ 下载CSV文件",
                        data=csv_data,
                        file_name=f"russell2000_simulation_{timestamp}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
            
            # 统计信息
            with st.expander("📊 详细统计"):
                col_stat1, col_stat2, col_stat3 = st.columns(3)
                with col_stat1:
                    st.metric("平均得分", f"{filtered['score'].mean():.2f}/5")
                    st.metric("最高得分", f"{filtered['score'].max()}/5")
                with col_stat2:
                    st.metric("平均PF7", f"{filtered['pf7'].mean():.2f}")
                    st.metric("最高PF7", f"{filtered['pf7'].max():.2f}")
                with col_stat3:
                    st.metric("平均胜率", f"{filtered['prob7'].mean()*100:.1f}%")
                    st.metric("最高胜率", f"{filtered['prob7'].max()*100:.1f}%")
        
        else:
            st.warning(f"🔍 暂无符合筛选条件的股票（得分≥{min_score}, PF7≥{min_pf7}, 胜率≥{min_prob}%）")
    else:
        st.info("📭 暂无扫描结果")
else:
    if st.session_state.scanning:
        st.info("⏳ 正在极速扫描中，请稍候...")
        # 添加加载动画
        st.markdown("""
        <div style="text-align: center; padding: 40px;">
            <div style="font-size: 48px; margin-bottom: 20px;">⚡</div>
            <p style="font-size: 18px; color: #666; margin-bottom: 10px;">
                <strong>极速扫描中...</strong>
            </p>
            <p style="font-size: 14px; color: #888;">
                模拟2000只罗素2000股票分析<br>
                基于年度回测数据模型<br>
                结果将实时显示...
            </p>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.info("👈 点击'开始极速扫描'按钮开始模拟分析")

# ==================== 自动刷新机制 ====================
if st.session_state.scanning:
    # 检查是否需要刷新
    current_time = time.time()
    if current_time - st.session_state.last_update > 0.3:  # 0.3秒刷新一次
        st.session_state.last_update = current_time
        st.rerun()
    
    # JavaScript自动刷新作为备用
    st.markdown("""
    <script>
    setTimeout(function() {
        window.location.reload(1);
    }, 500);
    </script>
    """, unsafe_allow_html=True)

# ==================== 系统信息 ====================
with st.sidebar.expander("ℹ️ 系统信息"):
    st.write("**版本:** 模拟回测扫描器 v1.0")
    st.write("**数据源:** 本地模拟数据")
    st.write("**股票数量:** 2000只")
    st.write("**扫描速度:** 极速（约2-3秒完成）")
    st.write("**回测周期:** 模拟一年数据")
    st.write("**算法:** 基于统计学模型的模拟分析")

# ==================== 页脚 ====================
st.divider()
st.caption(f"""
**模拟回测扫描引擎 v1.0** | 🚀 极速本地计算 | 📊 实时结果 | ⏱️ 最后更新: {datetime.datetime.now().strftime('%H:%M:%S')}
**注意:** 此版本使用模拟数据进行演示，无需网络连接，极速完成2000只股票分析
""")
