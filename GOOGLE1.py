import streamlit as st
import requests
import numpy as np
import time
import pandas as pd
from io import StringIO

st.set_page_config(page_title="极品短线-三高筛选版（修复版）", layout="wide")
st.title("🎯 极品短线扫描 (科学修复版)")

# ==================== 核心常量 ====================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
}

BACKTEST_CONFIG = {
    "3个月": {"range": "3mo", "interval": "1d"},
    "6个月": {"range": "6mo", "interval": "1d"},
    "1年": {"range": "1y", "interval": "1d"},
    "3年": {"range": "3y", "interval": "1d"},
}

CORE_ETFS = ["SPY", "QQQ", "IWM", "DIA", "SLV", "GLD", "GDX", "TLT", "SOXX", "SMH", 
             "KWEB", "BITO", "WDC", "SNDK", "NVDA", "AAPL", "MSFT", "GOOGL", "META"]

# ==================== 核心算法（修复版本）====================
def ema_np(x, span):
    """指数移动平均 - 与第一段代码保持一致"""
    alpha = 2 / (span + 1)
    ema = np.empty_like(x)
    ema[0] = x[0]
    for i in range(1, len(x)):
        ema[i] = alpha * x[i] + (1 - alpha) * ema[i-1]
    return ema

def macd_hist_np(close):
    """MACD柱状图"""
    ema12 = ema_np(close, 12)
    ema26 = ema_np(close, 26)
    macd_line = ema12 - ema26
    signal = ema_np(macd_line, 9)
    return macd_line - signal

def rsi_np(close, period=14):
    """RSI计算"""
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

def atr_np(high, low, close, period=14):
    """ATR计算 - 新增，提高科学性"""
    prev_close = np.roll(close, 1)
    prev_close[0] = close[0]
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))
    atr = np.empty_like(tr)
    atr[0] = tr[0]
    alpha = 1 / period
    for i in range(1, len(tr)):
        atr[i] = alpha * tr[i] + (1 - alpha) * atr[i-1]
    return atr

def rolling_mean_np(x, window):
    """滚动均值"""
    if len(x) < window:
        return np.full_like(x, np.nanmean(x) if not np.isnan(x).all() else 0)
    return pd.Series(x).rolling(window, min_periods=1).mean().values

def obv_np(close, volume):
    """OBV计算 - 新增，提高科学性"""
    direction = np.sign(np.diff(close, prepend=close[0]))
    return np.cumsum(direction * volume)

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_yahoo_ohlcv(symbol, range_str):
    """获取OHLCV数据"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={range_str}&interval=1d"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        data = resp.json()["chart"]["result"][0]
        quote = data["indicators"]["quote"][0]
        
        # 使用numpy数组处理，与第一段代码保持一致
        close = np.array(quote["close"], dtype=float)
        high = np.array(quote["high"], dtype=float)
        low = np.array(quote["low"], dtype=float)
        volume = np.array(quote["volume"], dtype=float)
        
        # 过滤NaN值
        mask = ~np.isnan(close)
        close, high, low, volume = close[mask], high[mask], low[mask], volume[mask]
        
        if len(close) < 50:
            return None
            
        return close, high, low, volume
    except Exception as e:
        st.warning(f"获取 {symbol} 数据失败: {str(e)}")
        return None

def compute_metrics(symbol, cfg_key):
    """计算股票指标（修复版本）"""
    data = fetch_yahoo_ohlcv(symbol, BACKTEST_CONFIG[cfg_key]["range"])
    if data is None:
        return None
        
    close, high, low, volume = data
    
    # 计算近三天变化
    if len(close) >= 4:
        chg_3d = [(close[-1]/close[-2]-1)*100, 
                  (close[-2]/close[-3]-1)*100, 
                  (close[-3]/close[-4]-1)*100]
    else:
        chg_3d = [0.0, 0.0, 0.0]

    # 计算所有指标
    macd_hist = macd_hist_np(close)
    rsi = rsi_np(close)
    atr = atr_np(high, low, close)
    obv = obv_np(close, volume)
    
    # 计算移动平均
    vol_ma20 = rolling_mean_np(volume, 20)
    atr_ma20 = rolling_mean_np(atr, 20)
    obv_ma20 = rolling_mean_np(obv, 20)
    price_ma20 = rolling_mean_np(close, 20)
    
    # === 修复点1：当前评分信号（5个指标）===
    sig_current = [
        macd_hist[-1] > 0,                           # MACD柱状图为正
        volume[-1] > vol_ma20[-1] * 1.1,             # 成交量放大10%
        rsi[-1] >= 60,                               # RSI >= 60
        atr[-1] > atr_ma20[-1] * 1.1,                # ATR放大10%
        obv[-1] > obv_ma20[-1] * 1.05,               # OBV在均线上方5%
    ]
    current_score = sum(sig_current)  # 0-5分
    
    # === 修复点2：历史评分信号（必须与当前评分使用相同的5个指标）===
    sig_macd_hist = (macd_hist > 0).astype(int)
    sig_vol_hist = (volume > vol_ma20 * 1.1).astype(int)
    sig_rsi_hist = (rsi >= 60).astype(int)
    sig_atr_hist = (atr > atr_ma20 * 1.1).astype(int)
    sig_obv_hist = (obv > obv_ma20 * 1.05).astype(int)
    
    score_hist = sig_macd_hist + sig_vol_hist + sig_rsi_hist + sig_atr_hist + sig_obv_hist
    
    # === 回测计算（使用score≥3作为信号）===
    steps = 7
    if len(close) > steps + 10:  # 确保有足够数据
        idx = np.where(score_hist[:-steps] >= 3)[0]
        if len(idx) > 0:
            rets = close[idx + steps] / close[idx] - 1
            prob7 = (rets > 0).mean()
            
            # PF7计算，与第一段代码保持一致
            if (rets <= 0).any():
                pf7 = rets[rets > 0].sum() / abs(rets[rets <= 0].sum())
            else:
                pf7 = 999.0 if len(rets) > 0 else 1.0
        else:
            prob7, pf7 = 0.5, 1.0
    else:
        prob7, pf7 = 0.5, 1.0
    
    # 当前价格涨跌幅
    change = (close[-1] / close[-2] - 1) * 100 if len(close) >= 2 else 0
    
    return {
        "symbol": symbol,
        "price": close[-1],
        "change": change,
        "score": current_score,
        "prob7": prob7,
        "pf7": pf7,
        "chg_3d": chg_3d,
        "macd": macd_hist[-1],
        "rsi": rsi[-1],
        "volume_ratio": volume[-1] / vol_ma20[-1] if vol_ma20[-1] > 0 else 1.0
    }

# ==================== 界面布局 ====================
st.sidebar.header("🔍 单股深度分析")
single_sym = st.sidebar.text_input("输入股票代码", "AAPL").upper()
if single_sym:
    with st.sidebar.expander(f"查看 {single_sym} 详情", expanded=True):
        for period in ["3个月", "1年", "3年"]:
            metrics = compute_metrics(single_sym, period)
            if metrics:
                st.write(f"**{period}回测结果:**")
                st.write(f"- 当前得分: {metrics['score']}/5")
                st.write(f"- 7日胜率: {metrics['prob7']*100:.1f}%")
                st.write(f"- PF7: {metrics['pf7']:.2f}")
                st.write(f"- MACD柱: {metrics['macd']:.4f}")
                st.write(f"- RSI: {metrics['rsi']:.1f}")
                st.write(f"- 成交量比: {metrics['volume_ratio']:.2f}x")
                st.write("---")

# ==================== 筛选设置 ====================
col1, col2, col3 = st.columns(3)
with col1:
    filter_mode = st.selectbox(
        "筛选模式",
        ["宽松模式 (PF7≥3.6 或 胜率≥68%)", "严格模式 (得分≥3 & 胜率≥70% & PF7≥3.5)"],
        index=0
    )
with col2:
    mode = st.selectbox("回测周期", list(BACKTEST_CONFIG.keys()), index=2)
with col3:
    sort_by = st.selectbox("排序方式", ["PF7", "胜率", "得分"], index=0)

# ==================== 数据获取与扫描 ====================
@st.cache_data(ttl=86400)
def get_all_tickers():
    """获取股票列表"""
    try:
        # 尝试获取标普500成分股
        url = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
        df = pd.read_csv(StringIO(requests.get(url, headers=HEADERS, timeout=10).text))
        sp500 = df['Symbol'].tolist()
        return list(set(sp500 + CORE_ETFS))
    except:
        # 失败时使用核心股票
        return CORE_ETFS

# 初始化session state
if 'high_prob' not in st.session_state:
    st.session_state.high_prob = []
if 'scanned' not in st.session_state:
    st.session_state.scanned = set()
if 'failed_count' not in st.session_state:
    st.session_state.failed_count = 0

# 获取股票列表
all_tickers = get_all_tickers()
all_tickers.sort()

st.write(f"**股票池总计**: {len(all_tickers)} 只股票")
st.info("扫描会自动进行，保持页面打开即可。每只股票间隔5秒以避免API限制。")

# 进度显示
progress_bar = st.progress(0)
status_text = st.empty()

# 扫描逻辑
if len(st.session_state.scanned) < len(all_tickers):
    remaining = [s for s in all_tickers if s not in st.session_state.scanned]
    
    for i, sym in enumerate(remaining):
        status_text.text(f"正在扫描 {sym} ({len(st.session_state.scanned)+1}/{len(all_tickers)})")
        progress_bar.progress((len(st.session_state.scanned) + 1) / len(all_tickers))
        
        try:
            metrics = compute_metrics(sym, mode)
            if metrics:
                st.session_state.high_prob.append(metrics)
            st.session_state.scanned.add(sym)
            
            # 每扫描10只股票更新一次显示
            if (i + 1) % 10 == 0:
                st.rerun()
                
        except Exception as e:
            st.session_state.failed_count += 1
            st.session_state.scanned.add(sym)
        
        time.sleep(5)  # 避免API限制
    
    st.rerun()

# ==================== 结果显示 ====================
if st.session_state.high_prob:
    df = pd.DataFrame(st.session_state.high_prob)
    
    # 应用筛选条件
    if filter_mode == "宽松模式 (PF7≥3.6 或 胜率≥68%)":
        filtered_df = df[(df['pf7'] >= 3.6) | (df['prob7'] >= 0.68)].copy()
        title = f"📈 宽松筛选结果 (共 {len(filtered_df)} 只)"
    else:
        filtered_df = df[(df['score'] >= 3) & (df['prob7'] >= 0.70) & (df['pf7'] >= 3.5)].copy()
        title = f"💎 严格筛选结果 (共 {len(filtered_df)} 只)"
    
    # 排序
    if sort_by == "PF7":
        filtered_df = filtered_df.sort_values("pf7", ascending=False)
    elif sort_by == "胜率":
        filtered_df = filtered_df.sort_values("prob7", ascending=False)
    else:
        filtered_df = filtered_df.sort_values("score", ascending=False)
    
    # 显示结果
    if not filtered_df.empty:
        st.subheader(title)
        
        for _, row in filtered_df.iterrows():
            c3 = row['chg_3d']
            
            # 创建颜色编码的涨跌幅
            chg_str = ", ".join([
                f"<span style='color:{'#ff4b4b' if val>0 else '#00cc66'}'>{val:+.2f}%</span>"
                for val in c3
            ])
            
            # 根据得分设置边框颜色
            border_color = "#00FF00" if row['score'] >= 4 else "#FFA500" if row['score'] >= 3 else "#FF4444"
            
            st.markdown(
                f"""<div style="border-left: 6px solid {border_color}; padding: 12px; margin: 10px 0; background-color: #f8f9fa;">
                    <b style="font-size:18px;">{row['symbol']}</b> | 价格: ${row['price']:.2f} ({row['change']:+.2f}%)<br>
                    得分: <b>{row['score']}/5</b> | 7日胜率: <b>{row['prob7']*100:.1f}%</b> | PF7: <b>{row['pf7']:.2f}</b><br>
                    <small>近三天涨跌: {chg_str} (最新→最早)</small>
                </div>""", 
                unsafe_allow_html=True
            )
        
        # 导出功能
        col_exp1, col_exp2 = st.columns(2)
        
        with col_exp1:
            # CSV导出
            csv_data = filtered_df[['symbol', 'price', 'change', 'score', 'prob7', 'pf7']].to_csv(index=False).encode('utf-8')
            st.download_button(
                "📄 导出CSV",
                csv_data,
                f"stock_scan_{time.strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv"
            )
        
        with col_exp2:
            # TXT报告
            report_lines = [
                "极品短线扫描报告 (修复科学版)",
                f"生成时间: {time.strftime('%Y-%m-%d %H:%M')}",
                f"筛选模式: {filter_mode}",
                f"回测周期: {mode}",
                f"排序方式: {sort_by}",
                f"股票数量: {len(filtered_df)} 只",
                "=" * 50,
                ""
            ]
            
            for _, row in filtered_df.iterrows():
                report_lines.append(
                    f"{row['symbol']:6} | 价格: ${row['price']:8.2f} ({row['change']:+.2f}%) | "
                    f"得分: {row['score']}/5 | 胜率: {row['prob7']*100:5.1f}% | PF7: {row['pf7']:5.2f}"
                )
            
            txt_data = "\n".join(report_lines).encode('utf-8')
            st.download_button(
                "📜 导出TXT报告",
                txt_data,
                f"stock_scan_report_{time.strftime('%Y%m%d_%H%M')}.txt",
                mime="text/plain"
            )
    else:
        st.warning(f"没有找到符合筛选条件的股票。当前扫描了 {len(df)} 只股票。")

# 状态信息
st.write("---")
col_stat1, col_stat2, col_stat3 = st.columns(3)
with col_stat1:
    st.metric("已扫描", f"{len(st.session_state.scanned)}/{len(all_tickers)}")
with col_stat2:
    st.metric("失败数量", st.session_state.failed_count)
with col_stat3:
    st.metric("合格股票", len([x for x in st.session_state.high_prob 
                              if (x['pf7'] >= 3.6 or x['prob7'] >= 0.68)]))

# 重置按钮
if st.button("🔄 重置扫描进度"):
    st.session_state.high_prob = []
    st.session_state.scanned = set()
    st.session_state.failed_count = 0
    st.rerun()

st.caption("💡 提示: 此版本修复了回测与评分不一致的核心bug，使用5个技术指标（MACD、成交量、RSI、ATR、OBV），与第一段代码保持算法一致性。")
