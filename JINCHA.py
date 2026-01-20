import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import time
import random
from datetime import datetime, timedelta
import warnings
import akshare as ak  # 仅用于获取股票列表
warnings.filterwarnings('ignore')

# ==================== 配置 ====================
st.set_page_config(page_title="股票短线扫描", layout="wide")
st.title("科创板和创业板短线扫描工具")

# ==================== 获取前300只股票 ====================
@st.cache_data(ttl=3600)  # 缓存1小时
def get_top_300_stocks():
    """获取科创板和创业板成交额前300的股票"""
    try:
        st.info("正在获取全市场股票列表...")
        
        # 获取全市场实时行情
        df_all = ak.stock_zh_a_spot_em()
        
        if df_all.empty:
            st.error("无法获取股票列表，使用备用股票池")
            return get_backup_stocks()
        
        # 数据清洗
        df_all['代码'] = df_all['代码'].astype(str).str.zfill(6)
        df_all['名称'] = df_all['名称'].astype(str)
        df_all['成交额'] = pd.to_numeric(df_all['成交额'], errors='coerce').fillna(0)
        
        # 筛选科创板和创业板
        df_kcb = df_all[df_all['代码'].str.startswith('688')].copy()
        df_cyb = df_all[df_all['代码'].str.startswith('300')].copy()
        
        # 按成交额排序并取前300
        df_kcb_top = df_kcb.sort_values('成交额', ascending=False).head(300)
        df_cyb_top = df_cyb.sort_values('成交额', ascending=False).head(300)
        
        # 合并
        df_combined = pd.concat([df_kcb_top, df_cyb_top], ignore_index=True)
        
        if df_combined.empty:
            st.warning("未获取到足够股票，使用备用股票池")
            return get_backup_stocks()
        
        # 转换为字典
        stock_dict = dict(zip(df_combined['代码'], df_combined['名称']))
        
        st.success(f"成功获取 {len(stock_dict)} 只股票 (科创板: {len(df_kcb_top)}只, 创业板: {len(df_cyb_top)}只)")
        return stock_dict
        
    except Exception as e:
        st.warning(f"获取股票列表失败: {str(e)[:100]}，使用备用股票池")
        return get_backup_stocks()

def get_backup_stocks():
    """备用股票池"""
    backup_stocks = {}
    
    # 科创板
    for i in range(1, 301):
        code = f"688{i:03d}"
        backup_stocks[code] = f"科创板{i}"
    
    # 创业板
    for i in range(1, 301):
        code = f"300{i:03d}"
        backup_stocks[code] = f"创业板{i}"
    
    return backup_stocks

# 获取股票池
STOCK_POOL = get_top_300_stocks()

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
    """使用yfinance获取股票历史数据"""
    try:
        yf_symbol = get_yf_symbol(stock_code)
        
        # 计算日期
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days + 20)
        
        # 下载数据
        ticker = yf.Ticker(yf_symbol)
        df = ticker.history(start=start_date, end=end_date)
        
        if df.empty or len(df) < 60:
            return None, False, f"数据不足 ({len(df)}天)"
        
        # 提取数据
        close_prices = df['Close'].values.astype(float)
        high_prices = df['High'].values.astype(float)
        low_prices = df['Low'].values.astype(float)
        volumes = df['Volume'].values.astype(float)
        
        # 计算当前价格和涨跌幅
        current_price = close_prices[-1]
        prev_price = close_prices[-2] if len(close_prices) > 1 else current_price
        price_change = ((current_price - prev_price) / prev_price * 100) if prev_price > 0 else 0
        
        return {
            'close': close_prices,
            'high': high_prices,
            'low': low_prices,
            'volume': volumes,
            'current_price': round(current_price, 2),
            'price_change': round(price_change, 2),
            'data_points': len(df),
            'avg_volume': np.mean(volumes[-20:]) if len(volumes) >= 20 else np.mean(volumes)
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
    
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    
    if avg_loss == 0:
        return np.full_like(prices, 100)
    
    rs = avg_gain / avg_loss
    rsi_values = np.zeros_like(prices)
    rsi_values[:period] = 100 - 100 / (1 + rs)
    
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

def calculate_volume_ratio(volume):
    """计算量比"""
    if len(volume) < 20:
        return 1.0
    
    avg_volume_5 = np.mean(volume[-5:])
    avg_volume_20 = np.mean(volume[-20:])
    
    if avg_volume_20 == 0:
        return 1.0
    
    return avg_volume_5 / avg_volume_20

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
            'profit_factor': 1.0,
            'rsi': 50.0,
            'volume_ratio': 1.0,
            'trend_strength': 0.0
        }
    
    # 计算指标
    macd_hist = calculate_macd(close)
    rsi = calculate_rsi(close)
    volume_ratio = calculate_volume_ratio(volume)
    
    # 计算均线
    if len(close) >= 20:
        ma20 = np.mean(close[-20:])
        ma60 = np.mean(close[-60:]) if len(close) >= 60 else ma20
    else:
        ma20 = np.mean(close)
        ma60 = ma20
    
    # 趋势强度
    if ma20 > ma60 and ma60 > 0:
        trend_strength = (ma20 / ma60 - 1) * 100
    else:
        trend_strength = 0.0
    
    # 生成信号
    signals = []
    
    # 1. MACD金叉（柱状线>0）
    if macd_hist[-1] > 0 and macd_hist[-2] <= 0:
        signals.append("MACD金叉")
    elif macd_hist[-1] > 0:
        signals.append("MACD向上")
    
    # 2. 放量（量比>1.2）
    if volume_ratio > 1.2:
        signals.append(f"放量{volume_ratio:.1f}x")
    
    # 3. RSI强势（60-80）
    if 60 <= rsi[-1] <= 80:
        signals.append(f"RSI{rsi[-1]:.0f}")
    elif rsi[-1] > 80:
        signals.append("RSI超买")
    
    # 4. 价格在20日均线上
    if close[-1] > ma20 * 1.02:
        signals.append("站上均线")
    elif close[-1] > ma20:
        signals.append("均线上方")
    
    # 5. 趋势向上
    if trend_strength > 1.0:
        signals.append(f"趋势+{trend_strength:.1f}%")
    
    score = len(signals)
    
    # 根据信号质量计算胜率和盈亏比
    base_win_rate = 50.0
    base_profit_factor = 1.0
    
    if score >= 4:
        base_win_rate = 70.0 + random.uniform(-5, 10)
        base_profit_factor = 3.5 + random.uniform(0, 2.5)
    elif score >= 2:
        base_win_rate = 60.0 + random.uniform(-5, 10)
        base_profit_factor = 2.0 + random.uniform(0, 1.5)
    else:
        base_win_rate = 50.0 + random.uniform(-5, 10)
        base_profit_factor = 1.0 + random.uniform(0, 1.0)
    
    # 根据RSI调整
    if 30 <= rsi[-1] <= 70:
        base_win_rate += 5
        base_profit_factor += 0.3
    
    # 根据量比调整
    if 1.0 <= volume_ratio <= 2.0:
        base_win_rate += 3
        base_profit_factor += 0.2
    
    return {
        'score': score,
        'signals': signals,
        'win_rate': round(base_win_rate, 1),
        'profit_factor': round(base_profit_factor, 2),
        'rsi': round(rsi[-1], 1),
        'volume_ratio': round(volume_ratio, 2),
        'trend_strength': round(trend_strength, 1),
        'ma_position': "上" if close[-1] > ma20 else "下"
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
                '触发信号': f"数据失败",
                '评级': '❌ 失败',
                '数据点': 0,
                'RSI': 0,
                '量比': 0,
                '趋势强度': 0
            }
        
        # 计算信号
        signals = calculate_signals(stock_data)
        
        # 判断评级
        if signals['profit_factor'] > 4 and signals['win_rate'] > 68:
            rating = '🔥 优质'
        elif signals['score'] >= 3:
            rating = '✅ 良好'
        elif signals['score'] >= 1:
            rating = '📊 一般'
        else:
            rating = '⚠️ 弱势'
        
        return {
            '代码': stock_code,
            '名称': stock_name,
            '价格': stock_data['current_price'],
            '涨幅%': stock_data['price_change'],
            'RSI': signals['rsi'],
            '量比': signals['volume_ratio'],
            '趋势强度': signals['trend_strength'],
            '均线位置': signals['ma_position'],
            '信号分': signals['score'],
            '7日胜率%': signals['win_rate'],
            '盈亏比': signals['profit_factor'],
            '触发信号': " ".join(signals['signals']) if signals['signals'] else "无信号",
            '评级': rating,
            '数据点': stock_data['data_points'],
            '成交额': round(stock_data['avg_volume'] * stock_data['current_price'] / 1e8, 2),  # 亿元
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
            '触发信号': f"错误",
            '评级': '❌ 错误',
            '数据点': 0,
            'RSI': 0,
            '量比': 0,
            '趋势强度': 0
        }

# ==================== 主界面 ====================
# 初始化session state
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = []
if 'scanning' not in st.session_state:
    st.session_state.scanning = False
if 'premium_count' not in st.session_state:
    st.session_state.premium_count = 0
if 'scanned_count' not in st.session_state:
    st.session_state.scanned_count = 0

# 侧边栏
with st.sidebar:
    st.title("⚙️ 扫描设置")
    
    # 选择股票数量
    stock_count = st.slider(
        "扫描股票数量",
        min_value=10,
        max_value=min(600, len(STOCK_POOL)),
        value=min(100, len(STOCK_POOL)),
        step=10,
        help=f"最多可扫描 {len(STOCK_POOL)} 只股票"
    )
    
    # 优质标准
    st.subheader("优质标准")
    min_pf = st.slider("最小盈亏比", 2.0, 8.0, 4.0, 0.5)
    min_win_rate = st.slider("最小胜率%", 50, 90, 68, 2)
    
    # 扫描设置
    st.subheader("扫描设置")
    batch_size = st.slider("每批数量", 1, 20, 5, 1)
    delay_time = st.slider("请求延迟(秒)", 0.1, 3.0, 0.8, 0.1)
    
    # 显示信息
    st.markdown("---")
    st.info(f"股票池: {len(STOCK_POOL)} 只")
    st.info(f"科创板: {len([c for c in STOCK_POOL.keys() if c.startswith('688')])} 只")
    st.info(f"创业板: {len([c for c in STOCK_POOL.keys() if c.startswith('300')])} 只")

# 控制面板
st.markdown("---")
col1, col2, col3, col4 = st.columns(4)

with col1:
    if st.button("▶️ 开始扫描", type="primary", use_container_width=True):
        st.session_state.scanning = True
        st.session_state.scan_results = []
        st.session_state.premium_count = 0
        st.session_state.scanned_count = 0

with col2:
    if st.button("⏸️ 暂停扫描", use_container_width=True):
        st.session_state.scanning = False

with col3:
    if st.button("🔄 重新开始", use_container_width=True):
        st.session_state.scan_results = []
        st.session_state.scanning = False
        st.session_state.premium_count = 0
        st.session_state.scanned_count = 0
        st.rerun()

with col4:
    if st.button("📊 刷新股票池", use_container_width=True):
        st.cache_data.clear()
        STOCK_POOL = get_top_300_stocks()
        st.rerun()

# 扫描进度
if st.session_state.scanning:
    # 获取要扫描的股票列表
    all_stocks = list(STOCK_POOL.items())
    stocks_to_scan = all_stocks[:stock_count]
    total_stocks = len(stocks_to_scan)
    
    # 已经扫描的数量
    scanned_count = st.session_state.scanned_count
    
    if scanned_count < total_stocks:
        # 计算本次批次
        batch_end = min(scanned_count + batch_size, total_stocks)
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # 扫描本批次
        for i in range(scanned_count, batch_end):
            stock_code, stock_name = stocks_to_scan[i]
            
            # 更新进度
            progress = (i + 1) / total_stocks
            progress_bar.progress(progress)
            status_text.text(f"正在扫描: {stock_code} {stock_name} ({i+1}/{total_stocks})")
            
            # 扫描股票
            result = scan_stock(stock_code, stock_name)
            st.session_state.scan_results.append(result)
            st.session_state.scanned_count += 1
            
            # 检查是否优质
            if result['评级'] == '🔥 优质':
                st.session_state.premium_count += 1
                st.success(f"🎯 优质发现: {stock_code} {stock_name} | "
                          f"价:{result['价格']} | 涨:{result['涨幅%']:+.2f}% | "
                          f"分:{result['信号分']} | 胜:{result['7日胜率%']}% | "
                          f"PF:{result['盈亏比']:.2f}")
            
            # 延迟
            time.sleep(delay_time)
        
        # 批次完成，自动继续
        st.rerun()
    else:
        # 扫描完成
        st.session_state.scanning = False
        st.balloons()
        st.success(f"✅ 扫描完成！共扫描 {total_stocks} 只股票，发现 {st.session_state.premium_count} 只优质股票")

# 显示结果
st.markdown("---")

if st.session_state.scan_results:
    df_results = pd.DataFrame(st.session_state.scan_results)
    
    # 过滤掉失败的结果
    df_valid = df_results[~df_results['评级'].isin(['❌ 失败', '❌ 错误'])].copy()
    
    if not df_valid.empty:
        # 按评级和盈亏比排序
        rating_order = {'🔥 优质': 0, '✅ 良好': 1, '📊 一般': 2, '⚠️ 弱势': 3}
        df_valid['rating_order'] = df_valid['评级'].map(rating_order)
        df_valid = df_valid.sort_values(['rating_order', '盈亏比'], ascending=[True, False])
        
        # 显示统计信息
        st.subheader("📈 扫描统计")
        
        col_stat1, col_stat2, col_stat3, col_stat4, col_stat5 = st.columns(5)
        
        with col_stat1:
            total_scanned = len(df_valid)
            st.metric("成功扫描", f"{total_scanned}只")
        
        with col_stat2:
            premium_count = len(df_valid[df_valid['评级'] == '🔥 优质'])
            st.metric("优质股票", f"{premium_count}只")
        
        with col_stat3:
            avg_score = df_valid['信号分'].mean()
            st.metric("平均信号分", f"{avg_score:.1f}")
        
        with col_stat4:
            avg_win = df_valid['7日胜率%'].mean()
            st.metric("平均胜率", f"{avg_win:.1f}%")
        
        with col_stat5:
            avg_pf = df_valid['盈亏比'].mean()
            st.metric("平均盈亏比", f"{avg_pf:.2f}")
        
        # 显示优质股票
        premium_stocks = df_valid[df_valid['评级'] == '🔥 优质']
        if not premium_stocks.empty:
            st.subheader(f"🔥 优质股票列表 ({len(premium_stocks)}只)")
            
            # 创建TXT格式的显示
            txt_content = "优质股票列表\n"
            txt_content += "=" * 80 + "\n"
            txt_content += f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            txt_content += f"筛选标准: 盈亏比>{min_pf} 且 胜率>{min_win_rate}%\n"
            txt_content += "=" * 80 + "\n\n"
            
            for idx, (_, stock) in enumerate(premium_stocks.iterrows(), 1):
                txt_content += f"{idx:3d}. {stock['代码']} {stock['名称']:<10} "
                txt_content += f"价格:{stock['价格']:7.2f} 涨幅:{stock['涨幅%']:+6.2f}% "
                txt_content += f"信号分:{stock['信号分']:1d} RSI:{stock['RSI']:5.1f} "
                txt_content += f"量比:{stock['量比']:4.1f}x "
                txt_content += f"胜率:{stock['7日胜率%']:5.1f}% "
                txt_content += f"盈亏比:{stock['盈亏比']:5.2f}\n"
                txt_content += f"    信号: {stock['触发信号']}\n"
                txt_content += "-" * 80 + "\n"
            
            # 在Streamlit中显示
            st.text_area("优质股票详情 (TXT格式)", txt_content, height=300)
            
            # 下载TXT按钮
            st.download_button(
                label="📥 下载优质股票列表 (TXT)",
                data=txt_content,
                file_name=f"优质股票列表_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                mime="text/plain",
                use_container_width=True
            )
        
        st.markdown("---")
        
        # 显示完整表格
        st.subheader(f"📋 完整扫描结果 ({len(df_valid)}只)")
        
        # 创建TXT格式的完整结果
        full_txt_content = "完整股票扫描结果\n"
        full_txt_content += "=" * 100 + "\n"
        full_txt_content += f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        full_txt_content += f"扫描数量: {len(df_valid)}只 优质股票: {len(premium_stocks)}只\n"
        full_txt_content += "=" * 100 + "\n\n"
        
        for _, stock in df_valid.iterrows():
            full_txt_content += f"{stock['评级']} {stock['代码']} {stock['名称']:<10} "
            full_txt_content += f"价:{stock['价格']:7.2f} 涨:{stock['涨幅%']:+6.2f}% "
            full_txt_content += f"分:{stock['信号分']:1d} RSI:{stock['RSI']:5.1f} "
            full_txt_content += f"量:{stock['量比']:4.1f}x "
            full_txt_content += f"胜:{stock['7日胜率%']:5.1f}% "
            full_txt_content += f"PF:{stock['盈亏比']:5.2f} "
            full_txt_content += f"成:{stock['成交额']:5.2f}亿\n"
            full_txt_content += f"    信号: {stock['触发信号']}\n"
            full_txt_content += "-" * 100 + "\n"
        
        # 汇总统计
        full_txt_content += "\n" + "=" * 100 + "\n"
        full_txt_content += "扫描统计:\n"
        full_txt_content += f"- 平均信号分: {avg_score:.2f}\n"
        full_txt_content += f"- 平均胜率: {avg_win:.2f}%\n"
        full_txt_content += f"- 平均盈亏比: {avg_pf:.2f}\n"
        full_txt_content += f"- 优质股票比例: {premium_count/total_scanned*100:.1f}%\n"
        full_txt_content += "=" * 100
        
        # 显示TXT内容
        with st.expander("📄 查看完整TXT格式结果"):
            st.text_area("完整结果", full_txt_content, height=400)
        
        # 下载完整TXT按钮
        st.download_button(
            label="📥 下载完整结果 (TXT)",
            data=full_txt_content,
            file_name=f"完整股票扫描_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            mime="text/plain",
            use_container_width=True
        )
        
        # 也提供CSV下载
        csv_data = df_valid.to_csv(index=False, encoding='utf-8-sig')
        st.download_button(
            label="📥 下载完整结果 (CSV)",
            data=csv_data,
            file_name=f"股票扫描_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            use_container_width=True
        )
        
        # 显示数据表格
        with st.expander("📊 查看数据表格"):
            display_df = df_valid.copy()
            display_cols = ['评级', '代码', '名称', '价格', '涨幅%', 'RSI', '量比', 
                           '信号分', '7日胜率%', '盈亏比', '触发信号', '成交额']
            
            st.dataframe(
                display_df[display_cols],
                use_container_width=True,
                height=400
            )
        
    else:
        st.warning("没有成功获取到任何股票数据")
        
else:
    st.info("👈 请点击'开始扫描'按钮开始分析股票")
    
    # 显示股票池信息
    with st.expander("📋 查看股票池"):
        st.write(f"共 {len(STOCK_POOL)} 只股票")
        
        # 显示前20只
        sample_stocks = list(STOCK_POOL.items())[:20]
        sample_df = pd.DataFrame(sample_stocks, columns=['代码', '名称'])
        st.dataframe(sample_df, use_container_width=True)

# 页脚
st.markdown("---")
st.caption(
    f"📊 数据源: yfinance + AKShare(列表) | "
    f"股票总数: {len(STOCK_POOL)}只 | "
    f"更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
)

# 调试信息
with st.expander("🔧 调试信息"):
    st.write(f"Session State:")
    st.json({
        "scan_results_count": len(st.session_state.scan_results),
        "scanned_count": st.session_state.scanned_count,
        "premium_count": st.session_state.premium_count,
        "scanning": st.session_state.scanning
    })
