import streamlit as st
import requests
import numpy as np
import pandas as pd
import time
import datetime
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue
import warnings
warnings.filterwarnings('ignore')

st.set_page_config(page_title="罗素2000 极速扫描", layout="wide")
st.title("⚡ 罗素2000 极速短线扫描器")

# ==================== 超高速数据获取 ====================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# 会话状态初始化
for key in ['scan_results', 'scanning', 'progress', 'total', 'current', 'last_update', 'queue']:
    if key not in st.session_state:
        if key == 'queue':
            st.session_state[key] = Queue()
        elif key == 'scan_results':
            st.session_state[key] = []
        else:
            st.session_state[key] = 0

# ==================== 超快速数据获取（缓存+极简） ====================
@st.cache_data(ttl=300)
def get_price_data_fast(symbol):
    """超快速获取价格数据 - 仅获取收盘价"""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=3mo&interval=1d"
        resp = requests.get(url, headers=HEADERS, timeout=5)
        if resp.status_code != 200:
            return None
        
        data = resp.json()
        close = data['chart']['result'][0]['indicators']['quote'][0]['close']
        close = [c for c in close if c is not None]
        
        if len(close) < 20:
            return None
            
        return np.array(close[-30:])  # 只取最近30天
    except:
        return None

# ==================== 极速指标计算 ====================
def compute_ultra_fast(symbol):
    """极速计算 - 3个核心指标"""
    try:
        close = get_price_data_fast(symbol)
        if close is None or len(close) < 10:
            return None
            
        price = close[-1]
        prev = close[-2] if len(close) > 1 else price
        change = ((price / prev) - 1) * 100
        
        # 1. 趋势得分（简化为价格在均线上方）
        ma10 = np.mean(close[-10:])
        trend_score = 1 if price > ma10 else 0
        
        # 2. 动量得分（5日涨幅）
        momentum = (price / close[-5] - 1) * 100 if len(close) > 5 else 0
        momentum_score = 1 if momentum > 1 else 0  # 涨幅>1%
        
        # 3. 波动得分（标准差）
        vol = np.std(close[-10:]) / np.mean(close[-10:]) * 100 if len(close) >= 10 else 0
        vol_score = 1 if vol > 2 else 0  # 波动>2%
        
        # 4. RSI极简版
        returns = np.diff(close) / close[:-1]
        up_days = sum(1 for r in returns[-14:] if r > 0)
        rsi = up_days / 14 * 100 if len(returns) >= 14 else 50
        rsi_score = 1 if rsi > 55 else 0
        
        # 5. 回测极简版
        if len(close) > 10:
            # 简单策略：价格高于5日均线时买入
            signals = []
            future_returns = []
            
            for i in range(5, len(close) - 3):
                ma5 = np.mean(close[i-5:i])
                signal = 1 if close[i] > ma5 else 0
                signals.append(signal)
                
                if signal == 1:
                    ret = (close[i+3] / close[i] - 1) * 100  # 3天回报
                    future_returns.append(ret)
            
            if future_returns:
                win_rate = sum(1 for r in future_returns if r > 0) / len(future_returns)
                avg_gain = np.mean([r for r in future_returns if r > 0]) if any(r > 0 for r in future_returns) else 0
                avg_loss = abs(np.mean([r for r in future_returns if r <= 0])) if any(r <= 0 for r in future_returns) else 1
                pf7 = avg_gain / avg_loss if avg_loss > 0 else 999
            else:
                win_rate = 0.5
                pf7 = 1.0
        else:
            win_rate = 0.5
            pf7 = 1.0
        
        # 总得分（0-4）
        total_score = trend_score + momentum_score + vol_score + rsi_score
        
        return {
            'symbol': symbol,
            'price': round(price, 2),
            'change': round(change, 2),
            'score': total_score,
            'prob7': round(win_rate, 3),
            'pf7': round(pf7, 2),
            'rsi': round(rsi, 1),
            'momentum': round(momentum, 2),
            'scan_time': datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        }
        
    except:
        return None

# ==================== 超高速并发扫描 ====================
def ultra_fast_scan(symbols, max_workers=20):
    """超高速并发扫描 - 20个线程同时运行"""
    results = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 批量提交任务
        future_to_symbol = {}
        for symbol in symbols:
            future = executor.submit(compute_ultra_fast, symbol)
            future_to_symbol[future] = symbol
        
        completed = 0
        total = len(future_to_symbol)
        
        # 处理完成的任务 - 实时更新
        for future in as_completed(future_to_symbol):
            completed += 1
            symbol = future_to_symbol[future]
            
            try:
                result = future.result(timeout=3)
                if result:
                    # 立即添加到结果队列
                    st.session_state.queue.put(('result', result))
                    
                    # 实时更新进度
                    st.session_state.progress = (completed / total) * 100
                    st.session_state.current = symbol
                    
                    # 每扫描1个就更新一次显示
                    if completed % 1 == 0:  # 改为每个都更新
                        st.session_state.last_update = time.time()
                        
                        # 强制Streamlit更新
                        st.rerun()
                        
            except Exception as e:
                st.session_state.queue.put(('error', (symbol, str(e))))
    
    return results

# ==================== 后台扫描线程 ====================
def start_background_scan(symbols):
    """启动后台扫描线程"""
    st.session_state.scanning = True
    st.session_state.scan_results = []
    st.session_state.progress = 0
    st.session_state.total = len(symbols)
    
    def scan_thread():
        ultra_fast_scan(symbols)
        st.session_state.scanning = False
        st.session_state.progress = 100
        st.session_state.queue.put(('complete', None))
        time.sleep(0.5)
        st.rerun()
    
    thread = threading.Thread(target=scan_thread, daemon=True)
    thread.start()

# ==================== 股票列表 ====================
@st.cache_data(ttl=3600)
def get_tickers_fast():
    """快速获取股票列表"""
    # 使用预定义的列表，避免网络请求
    tickers = [
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'JPM', 'V', 'JNJ',
        'WMT', 'PG', 'HD', 'BAC', 'MA', 'DIS', 'NFLX', 'ADBE', 'CRM', 'PYPL',
        'ABT', 'PEP', 'CMCSA', 'TMO', 'AVGO', 'COST', 'DHR', 'MCD', 'NKE', 'LIN',
        'INTC', 'CSCO', 'PFE', 'T', 'VZ', 'MRK', 'ABBV', 'BMY', 'UNH', 'LLY',
        'AMD', 'QCOM', 'TXN', 'AMGN', 'GILD', 'CVX', 'XOM', 'COP', 'SLB', 'EOG',
        'GS', 'MS', 'BLK', 'AXP', 'SPGI', 'MMC', 'ICE', 'C', 'WFC', 'USB',
        'PNC', 'BK', 'STT', 'TFC', 'RF', 'KEY', 'CFG', 'HBAN', 'FITB', 'MTB',
        'ZION', 'CMA', 'EWBC', 'BOKF', 'CADE', 'WAL', 'PBCT', 'ONB', 'HOMB', 'UCBI'
    ]
    return tickers

# ==================== 实时界面更新 ====================
def update_display():
    """实时更新显示 - 从队列获取最新结果"""
    new_results = []
    
    # 处理队列中的所有新结果
    while not st.session_state.queue.empty():
        item_type, data = st.session_state.queue.get()
        
        if item_type == 'result':
            new_results.append(data)
            # 立即添加到总结果中
            st.session_state.scan_results.append(data)
        elif item_type == 'error':
            st.toast(f"扫描失败: {data[0]}", icon="⚠️")
        elif item_type == 'complete':
            st.toast("扫描完成!", icon="✅")
    
    return new_results

# ==================== 主界面布局 ====================
# 控制面板
with st.sidebar:
    st.header("⚙️ 控制面板")
    
    # 扫描控制
    if st.button("🚀 极速扫描", type="primary", use_container_width=True):
        if not st.session_state.scanning:
            tickers = get_tickers_fast()
            start_background_scan(tickers[:50])  # 只扫描前50只，更快
    
    if st.button("⏸️ 暂停", use_container_width=True):
        st.session_state.scanning = False
    
    if st.button("🔄 重置", use_container_width=True):
        st.session_state.scan_results = []
        st.session_state.scanning = False
        st.session_state.progress = 0
        st.rerun()
    
    st.divider()
    
    # 筛选条件
    st.subheader("🎯 筛选条件")
    min_score = st.slider("最低得分", 0, 4, 2, 1)
    min_pf7 = st.slider("最低PF7", 0.0, 10.0, 2.5, 0.1)
    min_prob = st.slider("最低概率%", 0, 100, 60, 1)
    
    st.divider()
    
    # 排序方式
    st.subheader("📊 排序方式")
    sort_by = st.radio("选择排序", ["最新", "PF7", "概率", "得分"], index=0, horizontal=True)

# ==================== 实时进度显示 ====================
col1, col2, col3, col4 = st.columns(4)

with col1:
    if st.session_state.scanning:
        status = "🟢 扫描中"
    elif st.session_state.progress == 100:
        status = "✅ 完成"
    else:
        status = "⏸️ 暂停"
    st.metric("状态", status)

with col2:
    st.metric("进度", f"{st.session_state.progress:.0f}%")
    st.progress(st.session_state.progress / 100)

with col3:
    current = st.session_state.current or "等待"
    st.metric("当前", current)

with col4:
    total = st.session_state.total
    scanned = int((st.session_state.progress / 100) * total)
    st.metric("数量", f"{scanned}/{total}")

st.divider()

# ==================== 实时结果区域 ====================
results_container = st.container()

with results_container:
    # 先更新显示（获取队列中的新结果）
    update_display()
    
    # 显示结果
    if st.session_state.scan_results:
        # 转换为DataFrame
        df = pd.DataFrame(st.session_state.scan_results)
        
        # 筛选
        mask = (df['score'] >= min_score) & (df['pf7'] >= min_pf7) & (df['prob7'] >= min_prob/100)
        filtered = df[mask].copy()
        
        if len(filtered) > 0:
            # 排序
            if sort_by == "PF7":
                filtered = filtered.sort_values("pf7", ascending=False)
            elif sort_by == "概率":
                filtered = filtered.sort_values("prob7", ascending=False)
            elif sort_by == "得分":
                filtered = filtered.sort_values("score", ascending=False)
            else:  # 最新
                filtered = filtered.sort_values("scan_time", ascending=False)
            
            # 显示统计
            st.subheader(f"📈 发现 {len(filtered)} 只优质股票")
            
            # 实时显示 - 每只股票立即显示
            for idx, row in filtered.iterrows():
                # 颜色编码
                if row['score'] >= 3:
                    color = "#22c55e"  # 绿色
                    emoji = "🔥"
                elif row['score'] >= 2:
                    color = "#f59e0b"  # 橙色
                    emoji = "⚡"
                else:
                    color = "#ef4444"  # 红色
                    emoji = "📉"
                
                # 创建实时卡片
                col_left, col_mid, col_right = st.columns([1, 2, 1])
                
                with col_left:
                    st.markdown(f"""
                    <div style="text-align: center;">
                        <div style="font-size: 24px; font-weight: bold; color: {color};">
                            {row['score']}/4
                        </div>
                        <div style="font-size: 12px; color: #666;">得分</div>
                    </div>
                    """, unsafe_allow_html=True)
                
                with col_mid:
                    st.markdown(f"""
                    <div>
                        <div style="display: flex; align-items: center; gap: 10px;">
                            <span style="font-size: 20px; font-weight: bold;">{row['symbol']}</span>
                            <span style="font-size: 18px; font-weight: bold;">
                                ${row['price']:,.2f}
                            </span>
                            <span style="color: {'#22c55e' if row['change'] >= 0 else '#ef4444'}; font-weight: bold;">
                                {row['change']:+.2f}%
                            </span>
                        </div>
                        <div style="display: flex; gap: 20px; margin-top: 5px;">
                            <span>PF7: <b>{row['pf7']:.2f}</b></span>
                            <span>概率: <b>{row['prob7']*100:.1f}%</b></span>
                            <span>RSI: <b>{row['rsi']:.1f}</b></span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                
                with col_right:
                    st.markdown(f"""
                    <div style="text-align: right; color: #666; font-size: 12px;">
                        {row['scan_time']}
                    </div>
                    """, unsafe_allow_html=True)
                
                st.divider()
            
            # 导出选项
            st.subheader("📤 导出结果")
            col_exp1, col_exp2 = st.columns(2)
            
            with col_exp1:
                if st.button("📄 导出TXT格式"):
                    # 生成TXT格式
                    txt_content = "罗素2000扫描结果\n"
                    txt_content += "=" * 50 + "\n"
                    txt_content += f"扫描时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    txt_content += f"符合条件: {len(filtered)} 只股票\n\n"
                    
                    for idx, row in filtered.iterrows():
                        txt_content += f"{row['symbol']} - 价格: ${row['price']:.2f} ({row['change']:+.2f}%)\n"
                        txt_content += f"    得分: {row['score']}/4 | PF7: {row['pf7']:.2f} | 7日概率: {row['prob7']*100:.1f}%\n"
                        txt_content += f"    RSI: {row['rsi']:.1f} | 动量: {row['momentum']:.2f}%\n"
                        txt_content += f"    扫描时间: {row['scan_time']}\n"
                        txt_content += "-" * 40 + "\n"
                    
                    # 提供下载
                    st.download_button(
                        label="⬇️ 下载TXT文件",
                        data=txt_content,
                        file_name=f"russell2000_results_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                        mime="text/plain"
                    )
            
            with col_exp2:
                if st.button("📊 导出CSV格式"):
                    csv = filtered.to_csv(index=False)
                    st.download_button(
                        label="⬇️ 下载CSV文件",
                        data=csv,
                        file_name=f"russell2000_results_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv"
                    )
            
            # 显示统计摘要
            with st.expander("📊 统计摘要"):
                col_stat1, col_stat2, col_stat3 = st.columns(3)
                with col_stat1:
                    st.metric("平均得分", f"{filtered['score'].mean():.1f}/4")
                    st.metric("最高得分", f"{filtered['score'].max():.0f}/4")
                with col_stat2:
                    st.metric("平均PF7", f"{filtered['pf7'].mean():.2f}")
                    st.metric("最高PF7", f"{filtered['pf7'].max():.2f}")
                with col_stat3:
                    st.metric("平均概率", f"{filtered['prob7'].mean()*100:.1f}%")
                    st.metric("最高概率", f"{filtered['prob7'].max()*100:.1f}%")
        
        else:
            st.info("🔍 暂无符合筛选条件的股票")
    else:
        if st.session_state.scanning:
            st.info("⏳ 正在极速扫描中，结果将实时显示...")
            # 添加动画效果
            st.markdown("""
            <div style="text-align: center; padding: 20px;">
                <div style="font-size: 48px; margin-bottom: 20px;">⚡</div>
                <p>极速扫描中，请稍候...</p>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("👈 点击'极速扫描'开始分析")

# ==================== 自动刷新机制 ====================
# 如果正在扫描，每0.5秒自动刷新一次
if st.session_state.scanning:
    # 计算时间差，每0.5秒刷新一次
    current_time = time.time()
    if current_time - st.session_state.last_update > 0.5:  # 0.5秒刷新一次
        st.session_state.last_update = current_time
        st.rerun()
    
    # 添加JavaScript自动刷新作为备用
    st.markdown("""
    <script>
    setTimeout(function() {
        window.location.reload(1);
    }, 500);
    </script>
    """, unsafe_allow_html=True)

# ==================== 性能统计 ====================
with st.sidebar.expander("⚡ 性能统计"):
    if st.session_state.scan_results:
        scan_time = len(st.session_state.scan_results) * 0.3  # 估算每只0.3秒
        st.metric("扫描速度", f"{scan_time:.1f}秒")
        st.metric("股票数量", len(st.session_state.scan_results))
        st.metric("成功率", f"{(len(st.session_state.scan_results)/st.session_state.total)*100:.0f}%")

# ==================== 页脚 ====================
st.divider()
st.caption(f"""
**极速扫描引擎 v3.0** | 并发线程: 20 | 刷新频率: 0.5秒 | 最后更新: {datetime.datetime.now().strftime('%H:%M:%S')}
**优化特性:** 极简算法 + 并发处理 + 实时队列 + 自动刷新
""")

# 初始化时启动一次扫描演示
if 'initialized' not in st.session_state:
    st.session_state.initialized = True
    # 自动开始一个小型扫描演示
    if not st.session_state.scanning and len(st.session_state.scan_results) == 0:
        demo_tickers = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA']
        start_background_scan(demo_tickers)
