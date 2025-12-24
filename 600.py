import streamlit as st
import requests
import numpy as np
import time
import pandas as pd
from io import StringIO

# ==================== 页面设置 ====================
st.set_page_config(page_title="大盘扫描面板", layout="wide")
st.title("标普500 + 纳斯达克100 扫描工具（7日概率 ≥75%）")

# 这里必须粘贴你原代码的所有函数！！！
# HEADERS, BACKTEST_CONFIG, format_symbol_for_yahoo, get_current_price, fetch_yahoo_ohlcv,
# ema_np, macd_hist_np, rsi_np, atr_np, rolling_mean_np, obv_np,
# backtest_with_stats, prob_class, decide_advice, compute_stock_metrics
# （从你第一个消息复制全部过来）

# ==================== 加载成分股（加User-Agent防403） ====================
HEADERS_CSV = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"
}

@st.cache_data(ttl=86400)
def load_sp500_tickers():
    url = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
    resp = requests.get(url, headers=HEADERS_CSV)
    resp.raise_for_status()
    df = pd.read_csv(StringIO(resp.text))
    return df['Symbol'].tolist()

@st.cache_data(ttl=86400)
def load_ndx100_tickers():
    # 优先用Wikipedia解析（2025最新，最准）
    wiki_url = "https://en.wikipedia.org/wiki/NASDAQ-100"
    tables = pd.read_html(wiki_url)
    # Nasdaq-100表格通常是第4或第5个（有"Ticker"列）
    for table in tables:
        if 'Ticker' in table.columns:
            return table['Ticker'].tolist()
    # 备用raw CSV（如果wiki变了）
    backup_url = "https://raw.githubusercontent.com/Gary-Strauss/NASDAQ100_Constituents/main/data/nasdaq100_constituents.csv"
    resp = requests.get(backup_url, headers=HEADERS_CSV)
    resp.raise_for_status()
    df = pd.read_csv(StringIO(resp.text))
    return df['Ticker'].tolist()  # 或 'Symbol'，根据实际调整

st.info("加载标普500和纳斯达克100成分股（约580只去重）...")

try:
    sp500 = load_sp500_tickers()
except Exception as e:
    st.error(f"S&P500加载失败: {e}")
    sp500 = []

try:
    ndx100 = load_ndx100_tickers()
except Exception as e:
    st.error(f"Nasdaq100加载失败: {e}")
    ndx100 = []

tickers = list(set(sp500 + ndx100))
st.write(f"总计 {len(tickers)} 只股票（已去重）")

if len(tickers) == 0:
    st.stop()

mode = "1年"  # 可加 st.selectbox("回测周期", BACKTEST_OPTIONS, ...) 改

high_prob = []

progress_bar = st.progress(0)
status_text = st.empty()

with st.spinner("正在一个个扫描（每只sleep 4秒防Yahoo限流，总约40-60分钟）..."):
    for i, sym in enumerate(tickers):
        status_text.text(f"进度: {i+1}/{len(tickers)} - 计算 {sym}")
        progress_bar.progress((i + 1) / len(tickers))
        try:
            metrics = compute_stock_metrics(sym, mode)
            if metrics["prob7"] >= 0.75:
                high_prob.append(metrics)
        except Exception as e:
            st.warning(f"{sym} 计算失败: {str(e)}")
        time.sleep(4)  # 安全防Yahoo封IP

progress_bar.empty()
status_text.empty()

if not high_prob:
    st.info("扫描完成！当前没有7日概率 ≥75% 的股票（阈值高，年末市场正常）。可以把代码里 0.75 改成 0.70 重跑看Top。")
else:
    high_prob.sort(key=lambda x: x["prob7"], reverse=True)
    st.success(f"扫描完成！找到 {len(high_prob)} 只 ≥75% 的股票：")
    for row in high_prob:
        change_class = "change-up" if row["change"] >= 0 else "change-down"
        change_str = f"{row['change']:+.2f}%"
        st.markdown(f"**{row['symbol']}** - 价格: ${row['price']:.2f} ({change_str}) - **7日概率: {row['prob7']*100:.1f}%** - PF: {row['pf7']:.2f}")

st.caption("数据来源 Yahoo Finance。回测基于历史，仅供研究参考。运行慢但精确！")
