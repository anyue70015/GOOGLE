import streamlit as st
import requests
import numpy as np
import time
import pandas as pd

# ==================== 页面设置 ====================
st.set_page_config(page_title="大盘扫描面板", layout="wide")
st.title("标普500 + 纳斯达克100 扫描工具（7日概率 ≥75%）")

# 原代码的所有函数（format_symbol_for_yahoo, ema_np, macd_hist_np, rsi_np, atr_np, rolling_mean_np, obv_np, backtest_with_stats, decide_advice, compute_stock_metrics 等）
# 这里省略粘贴，复制你原来的所有函数和HEADERS、BACKTEST_CONFIG

# 新增：加载成分股列表
@st.cache_data(ttl=86400)
def load_sp500_tickers():
    url = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
    df = pd.read_csv(url)
    return df['Symbol'].tolist()

@st.cache_data(ttl=86400)
def load_ndx100_tickers():
    url = "https://raw.githubusercontent.com/fja05680/sp500/master/nasdaq100.csv"  # 或用slickcharts等可靠源
    # 如果上面不行，用这个备用：https://www.slickcharts.com/nasdaq100 (手动复制或找csv)
    # 这里用一个公开GitHub源，或你手动上传csv
    df = pd.read_csv("https://raw.githubusercontent.com/grmarcil/nasdaq100/main/nasdaq100.csv")  # 找个有效源
    return df['Ticker'].tolist()  # 调整列名

st.info("加载标普500和纳斯达克100成分股（约580只去重）...")

try:
    sp500 = load_sp500_tickers()
except:
    st.error("SP500列表加载失败，使用备用")
    sp500 = []  # 你可以手动贴部分

try:
    ndx100 = load_ndx100_tickers()
except:
    ndx100 = []

tickers = list(set(sp500 + ndx100))
st.write(f"总计 {len(tickers)} 只股票")

mode = "1年"  # 默认1年，你可以加selectbox改

high_prob = []

with st.spinner("正在一个个扫描（慢扫，防限流，每只sleep 2秒，总约20-30分钟）..."):
    for i, sym in enumerate(tickers):
        st.write(f"进度: {i+1}/{len(tickers)} - 正在计算 {sym}")
        try:
            metrics = compute_stock_metrics(sym, mode)
            if metrics["prob7"] >= 0.75:
                high_prob.append(metrics)
            time.sleep(2)  # 防Yahoo限流
        except Exception as e:
            st.warning(f"{sym} 失败: {e}")
            time.sleep(2)

if not high_prob:
    st.info("当前没有7日概率 ≥75% 的股票（阈值高，正常市场少见）。试试降低到70%改代码阈值。")
else:
    high_prob.sort(key=lambda x: x["prob7"], reverse=True)
    st.success(f"找到 {len(high_prob)} 只符合7日概率 ≥75% 的股票！")
    for row in high_prob:
        # 用你原卡片HTML显示
        # ... 粘贴原展示代码

st.caption("扫描完成。数据实时，Yahoo来源。运行慢但精确。")