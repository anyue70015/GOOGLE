import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import time
import random
from datetime import datetime, timedelta
import warnings
import akshare as ak
warnings.filterwarnings('ignore')

# ==================== 配置 ====================
st.set_page_config(page_title="股票短线扫描", layout="wide")
st.title("科创板和创业板短线扫描工具 - 成交额前300专业版")

# ==================== 回测配置 ====================
BACKTEST_CONFIG = {
    "3个月": {"days": 90},
    "6个月": {"days": 180},
    "1年": {"days": 365},
    "2年": {"days": 730},
}

# ==================== 获取成交额前300股票 ====================
@st.cache_data(ttl=1800)
def get_top_volume_stocks():
    """获取科创板和创业板成交额前300的股票"""
    try:
        # 显示获取状态
        status = st.empty()
        status.info("📡 正在获取实时行情数据...")
        
        # 获取全市场数据
        df = ak.stock_zh_a_spot_em()
        
        if df.empty:
            status.warning("无法获取实时数据，使用备用股票池")
            return get_backup_stocks()
        
        # 数据清洗
        df['代码'] = df['代码'].astype(str).str.zfill(6)
        df['名称'] = df['名称'].astype(str)
        
        # 处理成交额
        if '成交额' not in df.columns:
            df['成交额'] = 0
        
        df['成交额'] = pd.to_numeric(df['成交额'], errors='coerce').fillna(0)
        
        # 筛选科创板和创业板
        kcb_mask = df['代码'].str.startswith('688')
        cyb_mask = df['代码'].str.startswith('300')
        
        kcb_df = df[kcb_mask].copy()
        cyb_df = df[cyb_mask].copy()
        
        # 按成交额排序取前300
        kcb_sorted = kcb_df.sort_values('成交额', ascending=False).head(300)
        cyb_sorted = cyb_df.sort_values('成交额', ascending=False).head(300)
        
        # 合并
        combined_df = pd.concat([kcb_sorted, cyb_sorted], ignore_index=True)
        
        if combined_df.empty:
            status.warning("未找到股票，使用备用股票池")
            return get_backup_stocks()
        
        # 转换为字典
        stock_dict = {}
        turnover_dict = {}  # 保存成交额信息
        
        for _, row in combined_df.iterrows():
            stock_dict[row['代码']] = row['名称']
            turnover_dict[row['代码']] = row['成交额']
        
        # 显示统计
        kcb_count = len(kcb_sorted)
        cyb_count = len(cyb_sorted)
        
        status.success(f"✅ 获取成功: 科创板{kcb_count}只, 创业板{cyb_count}只")
        status.empty()
        
        return stock_dict, turnover_dict
        
    except Exception as e:
        st.error(f"获取失败: {str(e)[:100]}")
        return get_backup_stocks()

def get_backup_stocks():
    """备用股票池"""
    backup_stocks = {
        # 科创板
        "688981": "中芯国际", "688111": "金山办公", "688126": "沪硅产业",
        "688008": "澜起科技", "688099": "晶晨股份", "688036": "传音控股",
        "688185": "康希诺", "688390": "固德威", "688169": "石头科技",
        "688399": "硕世生物", "688019": "安集科技", "688088": "虹软科技",
        # 创业板
        "300750": "宁德时代", "300059": "东方财富", "300760": "迈瑞医疗",
        "300498": "温氏股份", "300142": "沃森生物", "300015": "爱尔眼科",
        "300124": "汇川技术", "300274": "阳光电源", "300122": "智飞生物",
        "300014": "亿纬锂能", "300347": "泰格医药", "300595": "欧普康视",
    }
    
    # 添加模拟数据
    turnover_dict = {}
    for code in backup_stocks.keys():
        turnover_dict[code] = random.uniform(1e7, 1e9)  # 随机成交额
    
    return backup_stocks, turnover_dict

# 获取股票池
STOCK_POOL, TURNOVER_DATA = get_top_volume_stocks()

# ==================== yfinance数据获取 ====================
def get_yf_symbol(code):
    """转换为yfinance格式"""
    if code.startswith('6'):
        return f"{code}.SS"
    elif code.startswith('3'):
        return f"{code}.SZ"
    return code

@st.cache_data(ttl=600, show_spinner=False)
def fetch_yf_ohlcv(symbol: str, days_back: int):
    """获取股票历史数据"""
    try:
        yf_symbol = get_yf_symbol(symbol)
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back + 60)
        
        ticker = yf.Ticker(yf_symbol)
        df = ticker.history(start=start_date, end=end_date)
        
        if df.empty or len(df) < 30:
            return None, None, None, None
        
        close = df['Close'].values.astype(float)
        high = df['High'].values.astype(float)
        low = df['Low'].values.astype(float)
        volume = df['Volume'].values.astype(float)
        
        return close, high, low, volume
        
    except Exception as e:
        print(f"数据获取失败 {symbol}: {str(e)}")
        return None, None, None, None

# ==================== 专业指标计算（使用您的算法）====================
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

# ==================== 核心计算 ====================
@st.cache_data(show_spinner=False)
def compute_stock_metrics(symbol: str, cfg_key: str = "1年"):
    """计算股票技术指标"""
    try:
        days_back = BACKTEST_CONFIG[cfg_key]["days"]
        close, high, low, volume = fetch_yf_ohlcv(symbol, days_back)
        
        if close is None or len(close) < 60:
            return None
        
        # 计算指标
        macd_hist = macd_hist_np(close)
        rsi = rsi_np(close)
        atr = atr_np(high, low, close)
        obv = obv_np(close, volume)
        vol_ma20 = rolling_mean_np(volume, 20)
        atr_ma20 = rolling_mean_np(atr, 20)
        obv_ma20 = rolling_mean_np(obv, 20)
        
        # 生成信号
        sig_macd = macd_hist[-1] > 0
        sig_vol = volume[-1] > vol_ma20[-1] * 1.1 if len(vol_ma20) > 0 else False
        sig_rsi = rsi[-1] >= 60
        sig_atr = atr[-1] > atr_ma20[-1] * 1.1 if len(atr_ma20) > 0 else False
        sig_obv = obv[-1] > obv_ma20[-1] * 1.05 if len(obv_ma20) > 0 else False
        
        score = sum([sig_macd, sig_vol, sig_rsi, sig_atr, sig_obv])
        
        # 历史信号回测
        sig_macd_hist = (macd_hist > 0).astype(int)
        sig_vol_hist = (volume > vol_ma20 * 1.1).astype(int) if len(vol_ma20) > 0 else np.zeros_like(close, dtype=int)
        sig_rsi_hist = (rsi >= 60).astype(int)
        sig_atr_hist = (atr > atr_ma20 * 1.1).astype(int) if len(atr_ma20) > 0 else np.zeros_like(close, dtype=int)
        sig_obv_hist = (obv > obv_ma20 * 1.05).astype(int) if len(obv_ma20) > 0 else np.zeros_like(close, dtype=int)
        
        score_arr = sig_macd_hist + sig_vol_hist + sig_rsi_hist + sig_atr_hist + sig_obv_hist
        prob7, pf7 = backtest_with_stats(close[:-1], score_arr[:-1], 7)
        
        # 价格变化
        price = close[-1]
        change = (close[-1] / close[-2] - 1) * 100 if len(close) >= 2 else 0
        
        # 获取成交额
        turnover = TURNOVER_DATA.get(symbol, 0)
        
        return {
            "symbol": symbol,
            "name": STOCK_POOL.get(symbol, "未知"),
            "price": round(price, 2),
            "change": round(change, 2),
            "score": score,
            "signals": ", ".join([k for k, v in {
                "MACD>0": sig_macd, "放量": sig_vol, "RSI≥60": sig_rsi,
                "ATR放大": sig_atr, "OBV上升": sig_obv
            }.items() if v]) or "无信号",
            "prob7": prob7,
            "pf7": pf7,
            "prob7_pct": round(prob7 * 100, 1),
            "rsi": round(rsi[-1], 1),
            "turnover": round(turnover / 1e8, 2),  # 转换为亿元
            "data_points": len(close),
            "scan_time": datetime.now().strftime("%H:%M:%S")
        }
        
    except Exception as e:
        print(f"计算失败 {symbol}: {str(e)}")
        return None

# ==================== 主界面 ====================
# 侧边栏
with st.sidebar:
    st.title("⚙️ 专业设置")
    
    # 显示股票池信息
    kcb_count = len([c for c in STOCK_POOL.keys() if c.startswith('688')])
    cyb_count = len([c for c in STOCK_POOL.keys() if c.startswith('300')])
    
    st.success(f"📊 实时股票池")
    st.info(f"科创板: {kcb_count}只 (成交额前{kcb_count})")
    st.info(f"创业板: {cyb_count}只 (成交额前{cyb_count})")
    
    # 显示成交额TOP5
    st.markdown("---")
    st.caption("💰 成交额TOP5")
    
    # 获取成交额前5
    turnover_items = [(k, v, TURNOVER_DATA.get(k, 0)) for k, v in STOCK_POOL.items()]
    turnover_sorted = sorted(turnover_items, key=lambda x: x[2], reverse=True)[:5]
    
    for code, name, turnover in turnover_sorted:
        st.text(f"{code} {name[:8]}: {turnover/1e8:.1f}亿")
    
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
        max_value=min(600, len(STOCK_POOL)),
        value=min(100, len(STOCK_POOL)),
        step=10
    )
    
    # 优质标准
    min_pf = st.slider("最小盈亏比", 2.0, 10.0, 4.0, 0.5)
    min_win_rate = st.slider("最小胜率%", 50, 95, 68, 2)
    
    # 刷新按钮
    if st.button("🔄 刷新实时数据", use_container_width=True):
        st.cache_data.clear()
        global STOCK_POOL, TURNOVER_DATA
        STOCK_POOL, TURNOVER_DATA = get_top_volume_stocks()
        st.rerun()

# 控制面板
st.markdown("---")
col1, col2, col3 = st.columns(3)

with col1:
    if st.button("🚀 开始扫描", type="primary", use_container_width=True):
        st.session_state.scanning = True
        st.session_state.scan_results = []
        st.session_state.premium_count = 0
        st.session_state.scanned_count = 0

with col2:
    if st.button("⏸️ 暂停扫描", use_container_width=True):
        st.session_state.scanning = False

with col3:
    if st.button("🔄 重置", use_container_width=True):
        st.session_state.scan_results = []
        st.session_state.scanning = False
        st.session_state.premium_count = 0
        st.session_state.scanned_count = 0
        st.rerun()

# 初始化session state
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = []
if 'scanning' not in st.session_state:
    st.session_state.scanning = False
if 'premium_count' not in st.session_state:
    st.session_state.premium_count = 0
if 'scanned_count' not in st.session_state:
    st.session_state.scanned_count = 0

# 扫描逻辑
if st.session_state.scanning:
    all_stocks = list(STOCK_POOL.items())[:stock_count]
    total_stocks = len(all_stocks)
    
    scanned = st.session_state.scanned_count
    
    if scanned < total_stocks:
        batch_size = 5
        batch_end = min(scanned + batch_size, total_stocks)
        
        progress_bar = st.progress(scanned / total_stocks)
        
        for i in range(scanned, batch_end):
            code, name = all_stocks[i]
            
            progress = (i + 1) / total_stocks
            progress_bar.progress(progress)
            
            # 计算指标
            result = compute_stock_metrics(code, period_key)
            
            if result:
                # 判断评级
                if result['pf7'] > min_pf and result['prob7_pct'] > min_win_rate:
                    rating = '🔥 优质'
                    st.session_state.premium_count += 1
                elif result['score'] >= 3:
                    rating = '✅ 良好'
                else:
                    rating = '📊 一般'
                
                stock_result = {
                    '代码': code,
                    '名称': name,
                    '价格': result['price'],
                    '涨幅%': result['change'],
                    '信号分': result['score'],
                    '7日胜率%': result['prob7_pct'],
                    '盈亏比': round(result['pf7'], 2),
                    'RSI': result['rsi'],
                    '成交额': result['turnover'],
                    '触发信号': result['signals'],
                    '评级': rating,
                    '扫描时间': result['scan_time']
                }
                
                st.session_state.scan_results.append(stock_result)
                
                # 实时显示优质股票
                if rating == '🔥 优质':
                    st.success(f"🎯 {code} {name} | 价:{result['price']} | "
                              f"涨:{result['change']:+.2f}% | 分:{result['score']} | "
                              f"胜:{result['prob7_pct']}% | PF:{result['pf7']:.2f}")
            
            st.session_state.scanned_count += 1
            time.sleep(0.8)
        
        st.rerun()
    else:
        st.session_state.scanning = False
        st.balloons()
        st.success(f"✅ 扫描完成! 共{total_stocks}只，优质{st.session_state.premium_count}只")

# 显示结果
st.markdown("---")

if st.session_state.scan_results:
    df_results = pd.DataFrame(st.session_state.scan_results)
    
    if not df_results.empty:
        # 排序
        rating_order = {'🔥 优质': 0, '✅ 良好': 1, '📊 一般': 2}
        df_results['rating_order'] = df_results['评级'].map(rating_order)
        df_sorted = df_results.sort_values(['rating_order', '盈亏比'], ascending=[True, False])
        
        # 统计
        premium_count = len(df_sorted[df_sorted['评级'] == '🔥 优质'])
        
        st.subheader(f"📊 扫描结果 ({len(df_sorted)}只)")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("总扫描", f"{len(df_sorted)}只")
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
            
            txt_content = "=" * 100 + "\n"
            txt_content += f"优质股票列表 (成交额前300筛选)\n"
            txt_content += "=" * 100 + "\n"
            txt_content += f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            txt_content += f"筛选标准: 盈亏比>{min_pf} 且 胜率>{min_win_rate}%\n"
            txt_content += f"数据来源: 实时成交额排名\n"
            txt_content += "=" * 100 + "\n\n"
            
            for idx, (_, stock) in enumerate(premium_df.iterrows(), 1):
                txt_content += f"{idx:3d}. {stock['代码']} {stock['名称']}\n"
                txt_content += f"     价格:{stock['价格']:8.2f} 涨幅:{stock['涨幅%']:+7.2f}% 成交额:{stock['成交额']:6.2f}亿\n"
                txt_content += f"     信号分:{stock['信号分']}/5 胜率:{stock['7日胜率%']:6.1f}% 盈亏比:{stock['盈亏比']:6.2f}\n"
                txt_content += f"     RSI:{stock['RSI']:5.1f} 信号:{stock['触发信号']}\n"
                txt_content += "-" * 100 + "\n"
            
            st.text_area("优质股票详情", txt_content, height=300)
            
            st.download_button(
                label="📥 下载优质股票列表 (TXT)",
                data=txt_content,
                file_name=f"优质股票_成交额筛选_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                mime="text/plain",
                use_container_width=True
            )

# 页脚
st.markdown("---")
st.caption(
    f"📊 专业扫描系统 | 数据源: AKShare(成交额) + yfinance(技术指标) | "
    f"科创板: {kcb_count}只 | 创业板: {cyb_count}只 | "
    f"更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
)
