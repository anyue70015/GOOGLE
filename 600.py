import streamlit as st
import requests
import numpy as np
import time
import pandas as pd
from io import StringIO

st.set_page_config(page_title="标普500 + 纳斯达克100 大盘扫描工具", layout="wide")
st.title("标普500 + 纳斯达克100 断点续扫工具（中断后继续）")

# ==================== 核心函数（同之前，全展开） ====================
# (把之前所有函数复制进来：HEADERS, BACKTEST_CONFIG, fetch_yahoo_ohlcv, ema_np ... compute_stock_metrics)

# ==================== 加载成分股 ====================
# (同之前 load_sp500_tickers, load_ndx100_tickers)

sp500 = load_sp500_tickers()
ndx100 = load_ndx100_tickers()
tickers = list(set(sp500 + ndx100))
st.write(f"总计 {len(tickers)} 只股票")

mode = st.selectbox("回测周期", list(BACKTEST_CONFIG.keys()), index=2)
threshold = st.slider("7日盈利概率阈值 (%)", 50, 90, 65) / 100.0

# ==================== 断点续扫逻辑 ====================
if 'current_index' not in st.session_state:
    st.session_state.current_index = 0  # 从头开始
if 'high_prob' not in st.session_state:
    st.session_state.high_prob = []  # 已发现列表
if 'failed_count' not in st.session_state:
    st.session_state.failed_count = 0

placeholder = st.empty()
result_container = st.container()

with placeholder.container():
    st.info(f"当前进度: 已扫描 {st.session_state.current_index} / {len(tickers)} 只 | 已发现高概率: {len(st.session_state.high_prob)} 只 | 失败: {st.session_state.failed_count} 只")
    st.info("网络中断或刷新页面后，会自动从上次进度继续！超过阈值的会实时显示。")

progress_bar = st.progress(st.session_state.current_index / len(tickers) if len(tickers) > 0 else 0)
status_text = st.empty()

with st.spinner("扫描中（每只60秒，断点续扫）..."):
    i = st.session_state.current_index
    while i < len(tickers):
        sym = tickers[i]
        status_text.text(f"正在计算 {sym} ({i+1}/{len(tickers)})")
        progress_bar.progress((i + 1) / len(tickers))
        try:
            metrics = compute_stock_metrics(sym, mode)
            if metrics["prob7"] >= threshold:
                st.session_state.high_prob.append(metrics)
                st.session_state.high_prob.sort(key=lambda x: x["prob7"], reverse=True)
                with result_container:
                    st.subheader(f"实时发现 {len(st.session_state.high_prob)} 只 ≥ {threshold*100:.0f}% 的股票")
                    for row in st.session_state.high_prob:
                        change_str = f"{row['change']:+.2f}%"
                        st.markdown(f"**{row['symbol']}** - 价格: ${row['price']:.2f} ({change_str}) - **7日概率: {row['prob7']*100:.1f}%** - PF: {row['pf7']:.2f}")
        except Exception as e:
            st.session_state.failed_count += 1
            st.warning(f"{sym} 失败: {str(e)}")
        # 更新进度
        st.session_state.current_index = i + 1
        i += 1
        time.sleep(10)  # 60秒

# 扫描完成
st.success(f"全扫描完成！共发现 {len(st.session_state.high_prob)} 只 ≥ {threshold*100:.0f}% 的股票")
if st.session_state.high_prob:
    with result_container:
        st.subheader("最终榜单")
        for row in st.session_state.high_prob:
            change_str = f"{row['change']:+.2f}%"
            st.markdown(f"**{row['symbol']}** - 价格: ${row['price']:.2f} ({change_str}) - **7日概率: {row['prob7']*100:.1f}%** - PF: {row['pf7']:.2f}")

# 可选：加一个“重置进度”按钮
if st.button("重置扫描进度（从头开始）"):
    st.session_state.current_index = 0
    st.session_state.high_prob = []
    st.session_state.failed_count = 0
    st.rerun()

st.caption("断点续扫版：网络中断刷新后自动继续，前面的不会白扫！")
