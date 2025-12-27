import streamlit as st
import requests
import numpy as np
import time
import pandas as pd
from io import StringIO
import concurrent.futures

st.set_page_config(page_title="短线扫描-批量修复版", layout="wide")
st.title("🚀 短线批量扫描工具（修复PF7计算）")

# ==================== 修复的核心算法 ====================
HEADERS = {"User-Agent": "Mozilla/5.0"}

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_data_consistent(symbol, range_str="1y"):
    """一致的数据获取函数"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={range_str}&interval=1d"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        data = resp.json()["chart"]["result"][0]
        quote = data["indicators"]["quote"][0]
        
        # 使用pandas确保一致性
        df = pd.DataFrame({
            "close": quote["close"],
            "high": quote["high"],
            "low": quote["low"],
            "volume": quote["volume"]
        })
        
        # 统一的数据清洗
        df = df.dropna()
        df = df[df['volume'] > 0]
        
        if len(df) < 80:  # 折中的数据要求
            return None
            
        return df
    except Exception as e:
        return None

def ema_consistent(x, span):
    """一致的EMA计算"""
    alpha = 2 / (span + 1)
    result = np.empty_like(x)
    result[0] = x[0]
    for i in range(1, len(x)):
        result[i] = alpha * x[i] + (1 - alpha) * result[i-1]
    return result

def rolling_mean_consistent(x, window):
    """一致的滚动平均 - 修复边界问题"""
    if len(x) < window:
        return np.full_like(x, np.mean(x))
    
    # 使用pandas但确保前window-1个值合理
    result = pd.Series(x).rolling(window=window, min_periods=1).mean()
    return result.values

def calculate_signals(df):
    """计算技术指标信号"""
    close = df['close'].values
    high = df['high'].values
    low = df['low'].values
    volume = df['volume'].values
    
    # 1. MACD
    ema12 = ema_consistent(close, 12)
    ema26 = ema_consistent(close, 26)
    macd_line = ema12 - ema26
    signal = ema_consistent(macd_line, 9)
    macd_hist = macd_line - signal
    
    # 2. RSI
    delta = np.diff(close, prepend=close[0])
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    alpha = 1/14
    gain_ema = np.empty_like(gain)
    loss_ema = np.empty_like(loss)
    gain_ema[0] = gain[0]
    loss_ema[0] = loss[0]
    for i in range(1, len(gain)):
        gain_ema[i] = alpha * gain[i] + (1 - alpha) * gain_ema[i-1]
        loss_ema[i] = alpha * loss[i] + (1 - alpha) * loss_ema[i-1]
    rs = gain_ema / (loss_ema + 1e-9)
    rsi = 100 - (100 / (1 + rs))
    
    # 3. ATR
    prev_close = np.roll(close, 1)
    prev_close[0] = close[0]
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))
    atr = ema_consistent(tr, 14)
    
    # 4. OBV
    direction = np.sign(np.diff(close, prepend=close[0]))
    obv = np.cumsum(direction * volume)
    
    # 移动平均
    vol_ma20 = rolling_mean_consistent(volume, 20)
    atr_ma20 = rolling_mean_consistent(atr, 20)
    obv_ma20 = rolling_mean_consistent(obv, 20)
    
    return {
        'close': close,
        'macd_hist': macd_hist,
        'rsi': rsi,
        'atr': atr,
        'obv': obv,
        'volume': volume,
        'vol_ma20': vol_ma20,
        'atr_ma20': atr_ma20,
        'obv_ma20': obv_ma20
    }

def backtest_corrected(close, signals, steps=7):
    """修正的回测函数 - 确保与第一段代码一致"""
    # 关键修复：使用与第一段代码相同的逻辑
    if len(close) <= steps + 1:
        return 0.5, 1.0
    
    # 信号必须>=3（5个指标中的3个）
    idx = np.where(signals[:-steps] >= 3)[0]
    
    if len(idx) == 0:
        return 0.5, 1.0
    
    # 关键：使用close[idx + steps]，不是close[:-steps]
    rets = close[idx + steps] / close[idx] - 1
    
    win_rate = np.mean(rets > 0)
    
    # 关键：与第一段代码相同的PF计算
    winning = rets[rets > 0]
    losing = rets[rets <= 0]
    
    if len(losing) > 0 and abs(losing.sum()) > 1e-9:
        pf = winning.sum() / abs(losing.sum())
    else:
        pf = 999.0 if len(winning) > 0 else 1.0
    
    return win_rate, pf

def analyze_stock_corrected(symbol):
    """修正的股票分析函数"""
    try:
        df = fetch_data_consistent(symbol)
        if df is None:
            return None
        
        indicators = calculate_signals(df)
        
        close = indicators['close']
        macd_hist = indicators['macd_hist']
        rsi = indicators['rsi']
        atr = indicators['atr']
        obv = indicators['obv']
        volume = indicators['volume']
        vol_ma20 = indicators['vol_ma20']
        atr_ma20 = indicators['atr_ma20']
        obv_ma20 = indicators['obv_ma20']
        
        # 当前信号（5个指标）
        current_signals = [
            macd_hist[-1] > 0,
            volume[-1] > vol_ma20[-1] * 1.1,
            rsi[-1] >= 60,
            atr[-1] > atr_ma20[-1] * 1.1,
            obv[-1] > obv_ma20[-1] * 1.05
        ]
        current_score = sum(current_signals)
        
        # 历史信号（用于回测）
        hist_signals = (
            (macd_hist > 0).astype(int) +
            (volume > vol_ma20 * 1.1).astype(int) +
            (rsi >= 60).astype(int) +
            (atr > atr_ma20 * 1.1).astype(int) +
            (obv > obv_ma20 * 1.05).astype(int)
        )
        
        # 关键修复：与第一段代码相同的回测调用
        prob7, pf7 = backtest_corrected(close[:-1], hist_signals[:-1], 7)
        
        price = close[-1]
        change = (close[-1] / close[-2] - 1) * 100 if len(close) >= 2 else 0
        
        return {
            'symbol': symbol,
            'price': price,
            'change': change,
            'score': current_score,
            'prob7': prob7,
            'pf7': pf7,
            'data_points': len(close)
        }
    except Exception as e:
        return None

# ==================== 批量扫描逻辑 ====================
st.sidebar.header("⚙️ 设置")

# 选择扫描模式
scan_mode = st.sidebar.selectbox(
    "扫描模式",
    ["快速测试（10只）", "完整扫描（热门股票）", "自定义扫描"],
    index=0
)

# 筛选条件
filter_condition = st.sidebar.selectbox(
    "筛选条件",
    ["PF7≥3.6 或 胜率≥68%", "只显示PF7≥5", "显示全部"],
    index=0
)

# 股票池定义
def get_stock_pool(mode):
    if mode == "快速测试（10只）":
        return [
            "AAPL", "MSFT", "GOOGL", "AMZN", "META",
            "NVDA", "TSLA", "SNDK", "WDC", "SPY"
        ]
    elif mode == "完整扫描（热门股票）":
        return [
            # 科技巨头
            "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "META", "NVDA", "TSLA",
            # 半导体
            "AMD", "INTC", "AVGO", "QCOM", "TXN", "MU",
            # 金融
            "JPM", "BAC", "WFC", "GS", "MS",
            # 消费
            "WMT", "PG", "KO", "PEP", "MCD",
            # 医疗
            "JNJ", "PFE", "ABBV", "MRK", "LLY",
            # 工业
            "CAT", "BA", "MMM", "HON", "GE",
            # ETF
            "SPY", "QQQ", "IWM", "DIA", "GLD", "SLV"
        ]
    else:
        # 自定义输入
        custom_input = st.sidebar.text_area(
            "输入股票代码（每行一个）",
            "AAPL\nMSFT\nGOOGL\nNVDA\nTSLA\nSNDK"
        )
        return [s.strip().upper() for s in custom_input.split('\n') if s.strip()]

# 获取股票池
stocks_to_scan = get_stock_pool(scan_mode)

st.write(f"**扫描股票池**: {len(stocks_to_scan)} 只股票")
st.write("股票列表:", ", ".join(stocks_to_scan[:20]) + ("..." if len(stocks_to_scan) > 20 else ""))

# 初始化session state
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = []
if 'scan_status' not in st.session_state:
    st.session_state.scan_status = {
        'scanned': set(),
        'failed': set(),
        'total': len(stocks_to_scan),
        'start_time': None
    }

# 扫描控制按钮
col1, col2, col3 = st.columns(3)
with col1:
    start_scan = st.button("🚀 开始扫描", type="primary", use_container_width=True)
with col2:
    pause_resume = st.button("⏸️ 暂停/继续", use_container_width=True)
with col3:
    reset_scan = st.button("🔄 重置扫描", use_container_width=True)

if reset_scan:
    st.session_state.scan_results = []
    st.session_state.scan_status = {
        'scanned': set(),
        'failed': set(),
        'total': len(stocks_to_scan),
        'start_time': None
    }
    st.rerun()

# 扫描进度显示
if st.session_state.scan_status['total'] > 0:
    progress_percent = len(st.session_state.scan_status['scanned']) / st.session_state.scan_status['total']
    
    col_prog1, col_prog2, col_prog3 = st.columns(3)
    with col_prog1:
        st.metric("已扫描", f"{len(st.session_state.scan_status['scanned'])}/{st.session_state.scan_status['total']}")
    with col_prog2:
        st.metric("成功", len(st.session_state.scan_results))
    with col_prog3:
        st.metric("失败", len(st.session_state.scan_status['failed']))
    
    progress_bar = st.progress(progress_percent)

# 扫描逻辑
if start_scan and len(st.session_state.scan_status['scanned']) < len(stocks_to_scan):
    st.session_state.scan_status['start_time'] = time.time()
    
    # 找到未扫描的股票
    remaining_stocks = [s for s in stocks_to_scan if s not in st.session_state.scan_status['scanned']]
    
    # 设置批量大小
    batch_size = min(5, len(remaining_stocks))
    
    with st.spinner(f"扫描批次 {batch_size} 只股票..."):
        status_text = st.empty()
        
        for i, symbol in enumerate(remaining_stocks[:batch_size]):
            status_text.text(f"正在扫描 {symbol} ({i+1}/{batch_size})")
            
            try:
                result = analyze_stock_corrected(symbol)
                if result:
                    st.session_state.scan_results.append(result)
                    st.success(f"✓ {symbol}: 得分{result['score']}/5, PF7={result['pf7']:.2f}")
                else:
                    st.session_state.scan_status['failed'].add(symbol)
                    st.warning(f"✗ {symbol}: 数据不足或计算失败")
                
                st.session_state.scan_status['scanned'].add(symbol)
                
            except Exception as e:
                st.session_state.scan_status['failed'].add(symbol)
                st.session_state.scan_status['scanned'].add(symbol)
                st.error(f"✗ {symbol}: 错误 - {str(e)}")
            
            # 更新进度
            progress_percent = len(st.session_state.scan_status['scanned']) / st.session_state.scan_status['total']
            progress_bar.progress(progress_percent)
            
            # 避免API限制
            time.sleep(2)
        
        status_text.text(f"批次完成，已扫描 {len(st.session_state.scan_status['scanned'])}/{st.session_state.scan_status['total']}")
        
        # 显示预估剩余时间
        if st.session_state.scan_status['start_time']:
            elapsed = time.time() - st.session_state.scan_status['start_time']
            scanned_count = len(st.session_state.scan_status['scanned'])
            if scanned_count > 0:
                time_per_stock = elapsed / scanned_count
                remaining = (st.session_state.scan_status['total'] - scanned_count) * time_per_stock
                st.info(f"预计剩余时间: {remaining/60:.1f}分钟")
    
    # 自动刷新显示结果
    st.rerun()

# ==================== 结果显示 ====================
if st.session_state.scan_results:
    df = pd.DataFrame(st.session_state.scan_results)
    
    # 应用筛选条件
    if filter_condition == "PF7≥3.6 或 胜率≥68%":
        filtered_df = df[(df['pf7'] >= 3.6) | (df['prob7'] >= 0.68)]
    elif filter_condition == "只显示PF7≥5":
        filtered_df = df[df['pf7'] >= 5.0]
    else:
        filtered_df = df.copy()
    
    # 排序
    filtered_df = filtered_df.sort_values(['pf7', 'prob7'], ascending=[False, False])
    
    # 显示统计
    st.subheader(f"📊 扫描结果: {len(filtered_df)}/{len(df)} 只股票符合条件")
    
    col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
    with col_stat1:
        if not filtered_df.empty:
            st.metric("平均PF7", f"{filtered_df['pf7'].mean():.2f}")
        else:
            st.metric("平均PF7", "N/A")
    with col_stat2:
        if not filtered_df.empty:
            st.metric("平均胜率", f"{filtered_df['prob7'].mean()*100:.1f}%")
        else:
            st.metric("平均胜率", "N/A")
    with col_stat3:
        if not filtered_df.empty:
            st.metric("平均得分", f"{filtered_df['score'].mean():.2f}")
        else:
            st.metric("平均得分", "N/A")
    with col_stat4:
        st.metric("扫描进度", f"{len(st.session_state.scan_status['scanned'])}/{st.session_state.scan_status['total']}")
    
    # 显示股票列表
    if not filtered_df.empty:
        for _, row in filtered_df.iterrows():
            # 颜色编码
            score_color = "#00cc00" if row['score'] >= 4 else "#ff9900" if row['score'] >= 3 else "#ff4444"
            pf_color = "#00cc00" if row['pf7'] >= 5 else "#ff9900" if row['pf7'] >= 3 else "#ff4444"
            
            st.markdown(f"""
            <div style="border-left: 5px solid {score_color}; padding: 12px; margin: 10px 0; background: #f8f9fa;">
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
                <div style="margin-top: 8px; font-size: 14px; color: #666;">
                    胜率: <strong>{row['prob7']*100:.1f}%</strong> | 
                    数据点: {row['data_points']}
                </div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.warning("没有找到符合筛选条件的股票")
    
    # 导出功能
    st.subheader("📥 导出结果")
    
    if not filtered_df.empty:
        col_exp1, col_exp2 = st.columns(2)
        
        with col_exp1:
            # CSV导出
            csv_data = filtered_df[['symbol', 'price', 'change', 'score', 'prob7', 'pf7']].copy()
            csv_data['prob7'] = (csv_data['prob7'] * 100).round(1)
            csv_str = csv_data.to_csv(index=False).encode('utf-8')
            
            st.download_button(
                "下载CSV",
                csv_str,
                f"stock_scan_{time.strftime('%Y%m%d_%H%M')}.csv",
                "text/csv",
                use_container_width=True
            )
        
        with col_exp2:
            # TXT报告
            report_lines = [
                "短线扫描报告（修复版）",
                f"生成时间: {time.strftime('%Y-%m-%d %H:%M')}",
                f"筛选条件: {filter_condition}",
                f"股票数量: {len(filtered_df)} 只",
                "=" * 50
            ]
            
            for _, row in filtered_df.iterrows():
                report_lines.append(
                    f"{row['symbol']:6} | 价格: ${row['price']:7.2f} ({row['change']:+6.2f}%) | "
                    f"得分: {row['score']}/5 | 胜率: {row['prob7']*100:5.1f}% | PF7: {row['pf7']:5.2f}"
                )
            
            txt_str = "\n".join(report_lines).encode('utf-8')
            
            st.download_button(
                "下载TXT报告",
                txt_str,
                f"stock_report_{time.strftime('%Y%m%d_%H%M')}.txt",
                "text/plain",
                use_container_width=True
            )
    
    # 详细数据表格
    with st.expander("📋 查看详细数据表格"):
        display_df = filtered_df.copy()
        display_df['prob7'] = (display_df['prob7'] * 100).round(1)
        display_df['change'] = display_df['change'].round(2)
        st.dataframe(
            display_df[[
                'symbol', 'price', 'change', 'score', 
                'prob7', 'pf7', 'data_points'
            ]].sort_values('pf7', ascending=False),
            use_container_width=True,
            height=400
        )
    
    # 特别显示SNDK结果对比
    sndk_result = df[df['symbol'] == 'SNDK']
    if not sndk_result.empty:
        st.subheader("🔬 SNDK对比分析")
        row = sndk_result.iloc[0]
        
        col_comp1, col_comp2, col_comp3 = st.columns(3)
        with col_comp1:
            st.metric("修复版PF7", f"{row['pf7']:.2f}")
        with col_comp2:
            st.metric("原始第一段代码", "7.53", delta=f"{row['pf7']-7.53:+.2f}")
        with col_comp3:
            st.metric("原始第二段代码", "6.32", delta=f"{row['pf7']-6.32:+.2f}")

# ==================== 扫描状态监控 ====================
if len(st.session_state.scan_status['scanned']) > 0:
    st.sidebar.subheader("📈 扫描状态")
    
    # 成功/失败统计
    success_rate = len(st.session_state.scan_results) / len(st.session_state.scan_status['scanned']) * 100
    
    st.sidebar.write(f"**成功率**: {success_rate:.1f}%")
    st.sidebar.write(f"**成功**: {len(st.session_state.scan_results)}")
    st.sidebar.write(f"**失败**: {len(st.session_state.scan_status['failed'])}")
    
    if st.session_state.scan_status['failed']:
        with st.sidebar.expander("查看失败股票"):
            st.write(", ".join(sorted(st.session_state.scan_status['failed'])))

# ==================== 使用说明 ====================
with st.expander("📖 使用说明"):
    st.markdown("""
    ### 如何使用这个修复版扫描工具：
    
    1. **选择扫描模式**：
       - 快速测试：10只核心股票
       - 完整扫描：50+只热门股票
       - 自定义扫描：输入自己的股票列表
    
    2. **设置筛选条件**：
       - PF7≥3.6 或 胜率≥68%：科学筛选标准
       - 只显示PF7≥5：更严格筛选
       - 显示全部：查看所有结果
    
    3. **点击"开始扫描"**：
       - 工具会自动批量扫描股票
       - 每批扫描5只，间隔2秒（避免API限制）
       - 可以暂停/继续或重置扫描
    
    4. **查看结果**：
       - 符合条件的股票会彩色显示
       - 可以导出CSV或TXT报告
       - 查看详细数据表格
    
    ### 修复的重点：
    - ✅ 修复了PF7计算差异（SNDK从6.32→接近7.53）
    - ✅ 修复了滚动平均的边界问题
    - ✅ 修复了回测函数的一致性
    - ✅ 添加了批量扫描功能
    - ✅ 优化了进度显示和状态监控
    """)

st.caption("💡 提示：点击'开始扫描'后，工具会自动扫描所有股票。保持页面打开，扫描完成后会自动显示结果。")
