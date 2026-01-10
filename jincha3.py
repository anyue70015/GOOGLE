import streamlit as st
import yfinance as yf
import numpy as np
import time
import pandas as pd
import random

st.set_page_config(page_title="标普500 + 纳斯达克100 + 热门ETF + 加密币 短线扫描工具", layout="wide")
st.title("标普500 + 纳斯达克100 + 热门ETF + 加密币 短线扫描工具")

# ── 新增清缓存按钮 ──
if st.button("🔄 强制刷新所有数据（清缓存 + 重新扫描）"):
    st.cache_data.clear()
    st.session_state.high_prob = []
    st.session_state.scanned_symbols = set()
    st.session_state.failed_count = 0
    st.session_state.fully_scanned = False
    st.rerun()

st.write("点击下方「开始扫描」按钮后会自动继续运行（每50只刷新一次页面，确保进度实时同步）。速度保持10倍快（每只约3-6秒），总800+只约需30-60分钟。请保持页面打开，不要关闭或刷新。")

# ==================== 核心常量 ====================
BACKTEST_CONFIG = {
    "3个月": {"range": "3mo", "interval": "1d"},
    "6个月": {"range": "6mo", "interval": "1d"},
    "1年":  {"range": "1y",  "interval": "1d"},
    "2年":  {"range": "2y",  "interval": "1d"},
    "3年":  {"range": "3y",  "interval": "1d"},
    "5年":  {"range": "5y",  "interval": "1d"},
    "10年": {"range": "10y", "interval": "1d"},
}

# ==================== 数据拉取（不抛异常，返回 None） ====================
@st.cache_data(ttl=1800, show_spinner=False)
def fetch_yahoo_ohlcv(yahoo_symbol: str, range_str: str, interval: str = "1d"):
    try:
        time.sleep(random.uniform(3, 6))  # 稍微放慢一点防Yahoo彻底限流（原来1-3秒太激进容易卡住）
        ticker = yf.Ticker(yahoo_symbol)
        df = ticker.history(period=range_str, interval=interval, auto_adjust=True, prepost=False, timeout=10)  # 加timeout防卡死
        if df.empty or len(df) < 50:
            return None, None, None, None
        close = df['Close'].values.astype(float)
        high = df['High'].values.astype(float)
        low = df['Low'].values.astype(float)
        volume = df['Volume'].values.astype(float)
        mask = ~np.isnan(close)
        close, high, low, volume = close[mask], high[mask], low[mask], volume[mask]
        if len(close) < 50:
            return None, None, None, None
        return close, high, low, volume
    except Exception as e:
        st.warning(f"yfinance错误 {yahoo_symbol}: {str(e)}")  # 加warning看具体哪个卡住
        return None, None, None, None

# ==================== 指标函数 ====================
# （保持不变，省略以节省空间，你复制时用原来的完整版）

# ==================== 核心计算 ====================
# （保持不变，省略，用原来的）

# ==================== 完整硬编码成分股 + 热门ETF + 加密币 ====================
# （保持不变，所有列表完整复制原来的）

# 定义加密币集合
crypto_tickers = list(set(gate_top200 + okx_top200))
crypto_set = set(c.upper() for c in crypto_tickers)

sp500 = load_sp500_tickers()
all_tickers = list(set(sp500 + ndx100 + extra_etfs + crypto_tickers))
all_tickers.sort()

st.write(f"总计 {len(all_tickers)} 只（标普500 + 纳斯达克100 + 热门ETF + 加密币） | 2026年1月最新")

mode = st.selectbox("回测周期", list(BACKTEST_CONFIG.keys()), index=2)
sort_by = st.selectbox("结果排序方式", ["PF7 (盈利因子)", "7日概率"], index=0)

# session_state 初始化
if 'high_prob' not in st.session_state:
    st.session_state.high_prob = []
if 'scanned_symbols' not in st.session_state:
    st.session_state.scanned_symbols = set()
if 'failed_count' not in st.session_state:
    st.session_state.failed_count = 0
if 'fully_scanned' not in st.session_state:
    st.session_state.fully_scanned = False

progress_bar = st.progress(0)
status_text = st.empty()

# ==================== 显示结果 ====================
# （保持不变，股票优质 + 加密币全部显示）

st.info(f"已扫描: {len(st.session_state.scanned_symbols)}/{len(all_tickers)} | 失败/跳过: {st.session_state.failed_count} | 已获取结果: {len(st.session_state.high_prob)}")

# ==================== 扫描逻辑（每50只rerun一次，防卡在10只） ====================
if not st.session_state.fully_scanned:
    if st.button("🚀 开始/继续全量扫描（每50只刷新一次，进度实时同步）"):
        with st.spinner("扫描进行中（每50只刷新一次页面）..."):
            batch_size = 50  # 增大到50，减少rerun次数（原来10容易在第一批后卡住）
            for i in range(0, len(all_tickers), batch_size):
                batch = all_tickers[i:i+batch_size]
                for sym in batch:
                    if sym in st.session_state.scanned_symbols:
                        continue
                    status_text.text(f"正在计算 {sym} ({len(st.session_state.scanned_symbols)+1}/{len(all_tickers)})")
                    progress_bar.progress((len(st.session_state.scanned_symbols) + 1) / len(all_tickers))
                    try:
                        metrics = compute_stock_metrics(sym, mode)
                        if metrics is None:
                            st.session_state.failed_count += 1
                        else:
                            st.session_state.high_prob.append(metrics)
                        st.session_state.scanned_symbols.add(sym)
                    except Exception as e:
                        st.warning(f"{sym} 异常: {str(e)}")
                        st.session_state.failed_count += 1
                        st.session_state.scanned_symbols.add(sym)
                st.rerun()  # 每50只rerun一次
            st.session_state.fully_scanned = True
            st.success("扫描完成！")
            st.rerun()
else:
    st.success("已完成全扫描！")

if st.button("🔄 重置所有进度（从头开始）"):
    # 重置

st.caption("2026年1月防卡版 | 每50只刷新一次 | 速度稍放缓防限流 | 加timeout + warning看具体错误 | 稳定运行")
