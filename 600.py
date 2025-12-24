import streamlit as st
import requests
import numpy as np
import time
import pandas as pd

# ==================== 页面设置 ====================
st.set_page_config(page_title="大盘扫描面板", layout="wide")
st.title("标普500 + 纳斯达克100 扫描工具（7日概率 ≥75%）")

# 这里粘贴你原代码的所有工具函数：HEADERS, BACKTEST_CONFIG, format_symbol_for_yahoo, 
# get_current_price, fetch_yahoo_ohlcv, ema_np, macd_hist_np, rsi_np, atr_np, 
# rolling_mean_np, obv_np, backtest_with_stats, prob_class, decide_advice, compute_stock_metrics
# （直接复制你第一个消息里的所有函数，不要漏）

# ==================== 加载成分股 ====================
@st.cache_data(ttl=86400)
def load_sp500_tickers():
    url = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
    df = pd.read_csv(url)
    return df['Symbol'].tolist()

@st.cache_data(ttl=86400)
def load_ndx100_tickers():
    url = "https://raw.githubusercontent.com/Gary-Strauss/NASDAQ100_Constituents/main/data/nasdaq100_constituents.csv"
    # 如果上面URL列名不对，改成实际的（如 'Ticker' 或 'Company'）
    df = pd.read_csv(url)
    return df['Ticker'].tolist()  # 根据实际CSV调整列名

st.info("加载标普500和纳斯达克100成分股（约580只去重）...")

sp500 = load_sp500_tickers()
ndx100 = load_ndx100_tickers()

tickers = list(set(sp500 + ndx100))
st.write(f"总计 {len(tickers)} 只股票（已去重）")

mode = "1年"  # 可加 st.selectbox 改周期

high_prob = []

progress_bar = st.progress(0)
status_text = st.empty()

with st.spinner("正在一个个扫描（每只sleep 3秒防限流，总约30-40分钟）..."):
    for i, sym in enumerate(tickers):
        status_text.text(f"进度: {i+1}/{len(tickers)} - 正在计算 {sym}")
        progress_bar.progress((i + 1) / len(tickers))
        try:
            metrics = compute_stock_metrics(sym, mode)
            if metrics["prob7"] >= 0.75:
                high_prob.append(metrics)
            time.sleep(3)  # 增加到3秒更安全防限流
        except Exception as e:
            st.warning(f"{sym} 加载失败: {str(e)}")
            time.sleep(3)

if not high_prob:
    st.info("扫描完成！当前没有7日概率 ≥75% 的股票（阈值较高，正常市场少见）。可以把阈值改成0.70试试。")
else:
    high_prob.sort(key=lambda x: x["prob7"], reverse=True)
    st.success(f"扫描完成！找到 {len(high_prob)} 只7日概率 ≥75% 的股票：")
    # 这里可以用你原卡片HTML展示
    for row in high_prob:
        # 粘贴你原来的卡片HTML生成代码
        # 示例简版：
        st.markdown(f"**{row['symbol']}** - 7日概率: {row['prob7']*100:.1f}%")

st.caption("数据来源 Yahoo Finance。回测基于历史信号统计，仅供研究参考，不构成投资建议。")
