import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import akshare as ak
import time
import random
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# ==================== 配置 ====================
st.set_page_config(page_title="股票实时扫描", layout="wide")
st.title("科创板和创业板实时扫描工具 - 成交额前300专业版")

# ==================== 回测配置 ====================
BACKTEST_CONFIG = {
    "3个月": {"days": 90},
    "6个月": {"days": 180},
    "1年": {"days": 365},
    "2年": {"days": 730},
}

# ==================== 获取成交额前300股票（实时） ====================
@st.cache_resource
def initialize_stock_pool():
    """初始化股票池：获取实时成交额前300股票"""
    try:
        # 使用AKShare获取全市场实时行情
        df = ak.stock_zh_a_spot_em()
        
        if df.empty or len(df) < 100:
            return get_backup_stocks()
        
        # 数据清洗
        df['代码'] = df['代码'].astype(str).str.zfill(6)
        df['名称'] = df['名称'].astype(str)
        
        # 处理成交额
        if '成交额' not in df.columns:
            df['成交额'] = 0
        
        df['成交额'] = pd.to_numeric(df['成交额'], errors='coerce').fillna(0)
        df['最新价'] = pd.to_numeric(df['最新价'], errors='coerce').fillna(0)
        df['涨跌幅'] = pd.to_numeric(df['涨跌幅'], errors='coerce').fillna(0)
        df['涨跌额'] = pd.to_numeric(df['涨跌额'], errors='coerce').fillna(0)
        
        # 筛选科创板和创业板
        kcb_df = df[df['代码'].str.startswith('688')].copy()
        cyb_df = df[df['代码'].str.startswith('300')].copy()
        
        # 按成交额排序取前300
        if not kcb_df.empty:
            kcb_top = kcb_df.sort_values('成交额', ascending=False).head(300)
        else:
            kcb_top = pd.DataFrame()
        
        if not cyb_df.empty:
            cyb_top = cyb_df.sort_values('成交额', ascending=False).head(300)
        else:
            cyb_top = pd.DataFrame()
        
        # 合并结果
        combined_df = pd.concat([kcb_top, cyb_top], ignore_index=True)
        
        if combined_df.empty:
            return get_backup_stocks()
        
        # 转换为字典
        stock_dict = {}
        realtime_data_dict = {}  # 存储实时数据
        
        for _, row in combined_df.iterrows():
            code = row['代码']
            stock_dict[code] = row['名称']
            
            # 存储实时数据
            realtime_data_dict[code] = {
                'price': float(row['最新价']),
                'change_percent': float(row['涨跌幅']),
                'change_amount': float(row['涨跌额']),
                'turnover': float(row['成交额']),
                'volume': float(row.get('成交量', 0)),
                'high': float(row.get('最高', 0)),
                'low': float(row.get('最低', 0)),
                'open': float(row.get('今开', 0)),
                'pre_close': float(row.get('昨收', 0)),
                'update_time': datetime.now().strftime("%H:%M:%S")
            }
        
        print(f"股票池初始化: 科创板{len(kcb_top)}只, 创业板{len(cyb_top)}只")
        return stock_dict, realtime_data_dict
        
    except Exception as e:
        print(f"初始化股票池失败: {str(e)}")
        return get_backup_stocks()

def get_backup_stocks():
    """备用股票池"""
    print("使用备用股票池")
    
    backup_stocks = {
        # 科创板
        "688981": "中芯国际", "688111": "金山办公", "688126": "沪硅产业",
        "688008": "澜起科技", "688099": "晶晨股份", "688036": "传音控股",
        # 创业板
        "300750": "宁德时代", "300059": "东方财富", "300760": "迈瑞医疗",
        "300498": "温氏股份", "300142": "沃森生物", "300015": "爱尔眼科",
    }
    
    # 添加模拟实时数据
    realtime_data_dict = {}
    for code in backup_stocks.keys():
        base_price = random.uniform(30, 200)
        change_pct = random.uniform(-5, 5)
        realtime_data_dict[code] = {
            'price': round(base_price * (1 + change_pct/100), 2),
            'change_percent': round(change_pct, 2),
            'change_amount': round(base_price * change_pct/100, 2),
            'turnover': random.uniform(1e8, 1e9),
            'volume': random.uniform(1e6, 1e7),
            'high': round(base_price * 1.05, 2),
            'low': round(base_price * 0.95, 2),
            'open': round(base_price * 0.99, 2),
            'pre_close': round(base_price, 2),
            'update_time': datetime.now().strftime("%H:%M:%S"),
            'is_simulated': True
        }
    
    return backup_stocks, realtime_data_dict

# 初始化股票池
STOCK_POOL, REALTIME_DATA = initialize_stock_pool()

# ==================== 获取历史数据（用于技术指标计算） ====================
@st.cache_data(ttl=3600, show_spinner=False)  # 缓存1小时
def get_historical_data(symbol: str, days_back: int):
    """获取历史数据用于技术指标计算"""
    try:
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days_back + 20)).strftime("%Y%m%d")
        
        df = ak.stock_zh_a_hist(symbol=symbol, period="daily", 
                               start_date=start_date, end_date=end_date, adjust="qfq")
        
        if df.empty or len(df) < 30:
            print(f"{symbol}: 历史数据不足 ({len(df)}天)")
            return None, None, None, None
        
        close = df['收盘'].values.astype(float)
        high = df['最高'].values.astype(float)
        low = df['最低'].values.astype(float)
        volume = df['成交量'].values.astype(float)
        
        print(f"{symbol}: 历史数据获取成功 ({len(df)}天)")
        return close, high, low, volume
        
    except Exception as e:
        print(f"{symbol}: 历史数据获取失败 - {str(e)}")
        
        # 备用方案：使用yfinance
        try:
            if symbol.startswith('6'):
                yf_symbol = f"{symbol}.SS"
            else:
                yf_symbol = f"{symbol}.SZ"
            
            ticker = yf.Ticker(yf_symbol)
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days_back + 60)
            
            df = ticker.history(start=start_date, end=end_date)
            
            if not df.empty and len(df) >= 30:
                close = df['Close'].values.astype(float)
                high = df['High'].values.astype(float)
                low = df['Low'].values.astype(float)
                volume = df['Volume'].values.astype(float)
                print(f"{symbol}: 使用yfinance历史数据 ({len(df)}天)")
                return close, high, low, volume
        except:
            pass
        
        return None, None, None, None

# ==================== 专业指标计算（保持不变） ====================
def ema_np(x: np.ndarray, span: int) -> np.ndarray:
    alpha = 2 / (span + 1)
    ema = np.empty_like(x)
    ema[0] = x[0]
    for i in range(1, len(x)):
        ema[i] = alpha * x[i] + (1 - alpha) * ema[i-1]
    return ema

def macd_hist_np(close: np.ndarray) -> np.ndarray:
    ema12 = ema_np(close, 12)
    ema26 = ema_np(close, 26)
    macd_line = ema12 - ema26
    signal = ema_np(macd_line, 9)
    return macd_line - signal

def rsi_np(close: np.ndarray, period: int = 14) -> np.ndarray:
    delta = np.diff(close, prepend=close[0])
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    alpha = 1 / period
    gain_ema = np.empty_like(gain)
    loss_ema = np.empty_like(loss)
    gain_ema[0] = gain[0]
    loss_ema[0] = loss[0]
    for i in range(1, len(gain)):
        gain_ema[i] = alpha * gain[i] + (1 - alpha) * gain_ema[i-1]
        loss_ema[i] = alpha * loss[i] + (1 - alpha) * loss_ema[i-1]
    rs = gain_ema / (loss_ema + 1e-9)
    return 100 - (100 / (1 + rs))

def atr_np(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    prev_close = np.roll(close, 1)
    prev_close[0] = close[0]
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))
    atr = np.empty_like(tr)
    atr[0] = tr[0]
    alpha = 1 / period
    for i in range(1, len(tr)):
        atr[i] = alpha * tr[i] + (1 - alpha) * atr[i-1]
    return atr

def rolling_mean_np(x: np.ndarray, window: int) -> np.ndarray:
    if len(x) < window:
        return np.full_like(x, np.nanmean(x) if not np.isnan(x).all() else 0)
    cumsum = np.cumsum(np.insert(x, 0, 0.0))
    ma = (cumsum[window:] - cumsum[:-window]) / window
    return np.concatenate([np.full(window-1, ma[0]), ma])

def obv_np(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
    direction = np.sign(np.diff(close, prepend=close[0]))
    return np.cumsum(direction * volume)

def backtest_with_stats(close: np.ndarray, score: np.ndarray, steps: int):
    if len(close) <= steps + 1:
        return 0.5, 0.0
    idx = np.where(score[:-steps] >= 3)[0]
    if len(idx) == 0:
        return 0.5, 0.0
    rets = close[idx + steps] / close[idx] - 1
    win_rate = (rets > 0).mean()
    pf = rets[rets > 0].sum() / abs(rets[rets <= 0].sum()) if (rets <= 0).any() else 999
    return win_rate, pf

# ==================== 核心计算（使用实时数据） ====================
def compute_stock_metrics(symbol: str, cfg_key: str = "1年"):
    """计算股票技术指标（使用实时数据）"""
    try:
        # 获取实时数据
        realtime_data = REALTIME_DATA.get(symbol)
        if not realtime_data:
            print(f"{symbol}: 无实时数据")
            return None
        
        # 获取历史数据用于技术指标计算
        days_back = BACKTEST_CONFIG[cfg_key]["days"]
        close_hist, high_hist, low_hist, volume_hist = get_historical_data(symbol, days_back)
        
        if close_hist is None or len(close_hist) < 60:
            print(f"{symbol}: 历史数据不足")
            return None
        
        # 计算技术指标（使用历史数据）
        macd_hist = macd_hist_np(close_hist)
        rsi = rsi_np(close_hist)
        atr = atr_np(high_hist, low_hist, close_hist)
        obv = obv_np(close_hist, volume_hist)
        vol_ma20 = rolling_mean_np(volume_hist, 20)
        atr_ma20 = rolling_mean_np(atr, 20)
        obv_ma20 = rolling_mean_np(obv, 20)
        
        # 生成信号（基于历史数据）
        sig_macd = macd_hist[-1] > 0
        sig_vol = volume_hist[-1] > vol_ma20[-1] * 1.1 if len(vol_ma20) > 0 and vol_ma20[-1] > 0 else False
        sig_rsi = rsi[-1] >= 60
        sig_atr = atr[-1] > atr_ma20[-1] * 1.1 if len(atr_ma20) > 0 and atr_ma20[-1] > 0 else False
        sig_obv = obv[-1] > obv_ma20[-1] * 1.05 if len(obv_ma20) > 0 and obv_ma20[-1] > 0 else False
        
        score = sum([sig_macd, sig_vol, sig_rsi, sig_atr, sig_obv])
        
        # 历史信号回测
        sig_macd_hist_arr = (macd_hist > 0).astype(int)
        sig_vol_hist_arr = (volume_hist > vol_ma20 * 1.1).astype(int) if len(vol_ma20) > 0 else np.zeros_like(close_hist, dtype=int)
        sig_rsi_hist_arr = (rsi >= 60).astype(int)
        sig_atr_hist_arr = (atr > atr_ma20 * 1.1).astype(int) if len(atr_ma20) > 0 else np.zeros_like(close_hist, dtype=int)
        sig_obv_hist_arr = (obv > obv_ma20 * 1.05).astype(int) if len(obv_ma20) > 0 else np.zeros_like(close_hist, dtype=int)
        
        score_arr = sig_macd_hist_arr + sig_vol_hist_arr + sig_rsi_hist_arr + sig_atr_hist_arr + sig_obv_hist_arr
        prob7, pf7 = backtest_with_stats(close_hist[:-1], score_arr[:-1], 7)
        
        # 使用实时数据
        price = realtime_data['price']
        change_percent = realtime_data['change_percent']
        change_amount = realtime_data['change_amount']
        turnover = realtime_data['turnover']
        current_rsi = rsi[-1]
        
        # 信号文本
        signals_list = []
        if sig_macd: signals_list.append("MACD>0")
        if sig_vol: signals_list.append("放量")
        if sig_rsi: signals_list.append("RSI≥60")
        if sig_atr: signals_list.append("ATR放大")
        if sig_obv: signals_list.append("OBV上升")
        signals_text = ", ".join(signals_list) if signals_list else "无信号"
        
        return {
            "symbol": symbol,
            "name": STOCK_POOL.get(symbol, "未知"),
            "price": price,
            "change_percent": change_percent,
            "change_amount": change_amount,
            "score": score,
            "signals": signals_text,
            "prob7": prob7,
            "pf7": pf7,
            "prob7_pct": round(prob7 * 100, 1),
            "rsi": round(current_rsi, 1),
            "turnover": round(turnover / 1e8, 2),  # 转换为亿元
            "data_points": len(close_hist),
            "scan_time": datetime.now().strftime("%H:%M:%S"),
            "update_time": realtime_data.get('update_time', ''),
            "is_realtime": not realtime_data.get('is_simulated', False)
        }
        
    except Exception as e:
        print(f"{symbol}: 计算失败 - {str(e)}")
        return None

# ==================== 主界面 ====================
# 初始化session state
for key in ['scan_results', 'scanning', 'premium_count', 'scanned_count']:
    if key not in st.session_state:
        if 'count' in key:
            st.session_state[key] = 0
        elif 'scanning' in key:
            st.session_state[key] = False
        else:
            st.session_state[key] = []

# 计算股票池统计
kcb_count = len([c for c in STOCK_POOL.keys() if c.startswith('688')])
cyb_count = len([c for c in STOCK_POOL.keys() if c.startswith('300')])
total_count = len(STOCK_POOL)

# 侧边栏
with st.sidebar:
    st.title("⚙️ 专业设置")
    
    # 显示数据状态
    realtime_sample = list(REALTIME_DATA.values())[0] if REALTIME_DATA else {}
    data_source = "实时数据" if realtime_sample.get('is_realtime', True) else "模拟数据"
    
    st.success(f"📊 {data_source}")
    st.info(f"科创板: {kcb_count}只")
    st.info(f"创业板: {cyb_count}只")
    st.info(f"总计: {total_count}只")
    
    # 显示当前时间
    current_time = datetime.now().strftime("%H:%M:%S")
    st.caption(f"🕒 当前时间: {current_time}")
    
    # 显示实时数据示例
    if REALTIME_DATA:
        st.markdown("---")
        st.caption("💰 实时数据示例")
        sample_code = list(STOCK_POOL.keys())[0]
        sample_data = REALTIME_DATA.get(sample_code, {})
        if sample_data:
            st.text(f"{sample_code}: {sample_data.get('price', 0):.2f}")
            st.text(f"涨跌: {sample_data.get('change_percent', 0):+.2f}%")
            st.text(f"更新: {sample_data.get('update_time', '')}")
    
    st.markdown("---")
    
    # 回测周期
    period_key = st.selectbox(
        "回测周期",
        options=list(BACKTEST_CONFIG.keys()),
        index=2
    )
    
    # 扫描设置
    stock_count = st.slider(
        "扫描数量",
        min_value=10,
        max_value=min(600, total_count),
        value=min(50, total_count),
        step=10
    )
    
    # 优质标准
    min_pf = st.slider("最小盈亏比", 2.0, 10.0, 4.0, 0.5)
    min_win_rate = st.slider("最小胜率%", 50, 95, 68, 2)
    
    # 延迟设置
    delay_time = st.slider("请求延迟(秒)", 0.1, 3.0, 0.5, 0.1)
    
    # 刷新按钮
    if st.button("🔄 刷新实时数据", use_container_width=True):
        st.cache_data.clear()
        st.cache_resource.clear()
        st.rerun()

# 控制面板
st.markdown("---")
col1, col2, col3 = st.columns(3)

with col1:
    if st.button("🚀 开始实时扫描", type="primary", use_container_width=True):
        st.session_state.scanning = True
        st.session_state.scan_results = []
        st.session_state.premium_count = 0
        st.session_state.scanned_count = 0

with col2:
    if st.button("⏸️ 暂停扫描", use_container_width=True):
        st.session_state.scanning = False

with col3:
    if st.button("🔄 重置结果", use_container_width=True):
        st.session_state.scan_results = []
        st.session_state.scanning = False
        st.session_state.premium_count = 0
        st.session_state.scanned_count = 0
        st.rerun()

# 扫描进度显示
progress_container = st.empty()
status_container = st.empty()

# 扫描逻辑
if st.session_state.scanning:
    all_stocks = list(STOCK_POOL.items())[:stock_count]
    total_stocks = len(all_stocks)
    
    scanned = st.session_state.scanned_count
    
    if scanned < total_stocks:
        batch_size = 3
        batch_end = min(scanned + batch_size, total_stocks)
        
        # 创建进度条
        progress_bar = progress_container.progress(scanned / total_stocks)
        status_text = status_container.text(f"准备扫描...")
        
        for i in range(scanned, batch_end):
            code, name = all_stocks[i]
            
            progress = (i + 1) / total_stocks
            progress_bar.progress(progress)
            status_text = status_container.text(f"扫描: {code} {name} ({i+1}/{total_stocks})")
            
            # 扫描股票
            result = compute_stock_metrics(code, period_key)
            
            if result:
                # 判断评级
                if result['pf7'] > min_pf and result['prob7_pct'] > min_win_rate:
                    rating = '🔥 优质'
                    st.session_state.premium_count += 1
                elif result['score'] >= 3:
                    rating = '✅ 良好'
                elif result['score'] >= 1:
                    rating = '📊 一般'
                else:
                    rating = '⚠️ 弱势'
                
                stock_result = {
                    '代码': result['symbol'],
                    '名称': result['name'],
                    '价格': result['price'],
                    '涨幅%': result['change_percent'],
                    '涨跌额': result['change_amount'],
                    '信号分': result['score'],
                    '7日胜率%': result['prob7_pct'],
                    '盈亏比': round(result['pf7'], 2),
                    'RSI': result['rsi'],
                    '成交额': result['turnover'],
                    '触发信号': result['signals'],
                    '评级': rating,
                    '数据点': result['data_points'],
                    '扫描时间': result['scan_time'],
                    '更新时间': result.get('update_time', ''),
                    '实时性': '实时' if result.get('is_realtime', False) else '延迟'
                }
                
                st.session_state.scan_results.append(stock_result)
                
                # 实时显示优质股票
                if rating == '🔥 优质':
                    st.success(f"🎯 {code} {name} | "
                              f"价:{result['price']:.2f} | 涨:{result['change_percent']:+.2f}% | "
                              f"额:{result['change_amount']:+.2f} | 分:{result['score']} | "
                              f"胜:{result['prob7_pct']}% | PF:{result['pf7']:.2f}")
            
            st.session_state.scanned_count += 1
            time.sleep(delay_time)
        
        # 检查是否完成
        if st.session_state.scanned_count >= total_stocks:
            st.session_state.scanning = False
            progress_bar.progress(1.0)
            status_text = status_container.text(f"✅ 扫描完成! 共{total_stocks}只，优质{st.session_state.premium_count}只")
            st.balloons()
        
        # 自动继续下一批（如果还没完成）
        if st.session_state.scanning:
            time.sleep(0.5)
            st.rerun()

# 显示结果
st.markdown("---")

if st.session_state.scan_results:
    df_results = pd.DataFrame(st.session_state.scan_results)
    
    # 过滤有效结果
    df_valid = df_results[~df_results['评级'].isin(['❌ 失败', '❌ 错误'])].copy()
    
    if not df_valid.empty:
        # 按评级排序
        rating_order = {'🔥 优质': 0, '✅ 良好': 1, '📊 一般': 2, '⚠️ 弱势': 3}
        df_valid['rating_order'] = df_valid['评级'].map(rating_order)
        df_sorted = df_valid.sort_values(['rating_order', '盈亏比', '7日胜率%'], 
                                        ascending=[True, False, False])
        
        # 统计信息
        premium_count = len(df_sorted[df_sorted['评级'] == '🔥 优质'])
        total_scanned = len(df_sorted)
        
        st.subheader(f"📊 实时扫描结果 ({total_scanned}只)")
        
        # 显示数据时间信息
        if '更新时间' in df_sorted.columns:
            latest_update = df_sorted['更新时间'].max()
            st.caption(f"🕒 最新数据时间: {latest_update} | 当前时间: {datetime.now().strftime('%H:%M:%S')}")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("总扫描", f"{total_scanned}只")
        with col2:
            st.metric("优质股票", f"{premium_count}只")
        with col3:
            avg_score = df_sorted['信号分'].mean()
            st.metric("平均信号分", f"{avg_score:.1f}")
        with col4:
            avg_pf = df_sorted['盈亏比'].mean()
            st.metric("平均盈亏比", f"{avg_pf:.2f}")
        
        # 优质股票TXT
        premium_df = df_sorted[df_sorted['评级'] == '🔥 优质']
        if not premium_df.empty:
            st.subheader(f"🔥 优质股票 ({len(premium_df)}只)")
            
            # 生成TXT内容
            txt_content = "=" * 100 + "\n"
            txt_content += "优质股票实时扫描结果\n"
            txt_content += "=" * 100 + "\n"
            txt_content += f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            txt_content += f"数据时间: {latest_update if 'latest_update' in locals() else '未知'}\n"
            txt_content += f"筛选标准: 盈亏比>{min_pf} 且 胜率>{min_win_rate}%\n"
            txt_content += f"股票数量: {len(premium_df)}只\n"
            txt_content += "=" * 100 + "\n\n"
            
            for idx, (_, stock) in enumerate(premium_df.iterrows(), 1):
                txt_content += f"{idx:3d}. {stock['代码']} {stock['名称']}\n"
                txt_content += f"     价格: {stock['价格']:8.2f}   涨幅: {stock['涨幅%']:+7.2f}%   涨跌额: {stock.get('涨跌额', 0):+7.2f}\n"
                txt_content += f"     成交额: {stock['成交额']:6.2f}亿   实时性: {stock.get('实时性', '未知')}\n"
                txt_content += f"     信号分: {stock['信号分']}/5   胜率: {stock['7日胜率%']:6.1f}%   盈亏比: {stock['盈亏比']:6.2f}\n"
                txt_content += f"     RSI: {stock['RSI']:5.1f}   信号: {stock['触发信号']}\n"
                txt_content += f"     更新时间: {stock.get('更新时间', '未知')}\n"
                txt_content += "-" * 100 + "\n"
            
            # 显示和下载TXT
            st.text_area("优质股票详情", txt_content, height=300)
            
            st.download_button(
                label="📥 下载优质股票列表 (TXT)",
                data=txt_content,
                file_name=f"优质股票_实时_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                mime="text/plain",
                use_container_width=True
            )

else:
    st.info("👈 请设置参数后点击'开始实时扫描'按钮")

# 页脚
st.markdown("---")
current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
st.caption(
    f"📊 实时扫描系统 | "
    f"科创板: {kcb_count}只 | 创业板: {cyb_count}只 | "
    f"更新时间: {current_time} | "
    f"数据源: AKShare实时行情"
)
