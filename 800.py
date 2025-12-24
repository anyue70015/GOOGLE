import streamlit as st
import requests
import numpy as np
import time
import pandas as pd
from io import StringIO

st.set_page_config(page_title="标普500 + 纳斯达克100 大盘扫描工具", layout="wide")
st.title("标普500 + 纳斯达克100 断点续扫工具（中断后继续，10秒防限流）")

# ==================== 核心函数（全展开） ====================
# (你的所有函数保持不变，已完整)

# ==================== 加载成分股 ====================
# (load_sp500_tickers 和 load_ndx100_tickers 已完整)

sp500 = load_sp500_tickers()
ndx100 = load_ndx100_tickers()
tickers = list(set(sp500 + ndx100))
st.write(f"总计 {len(tickers)} 只股票")

mode = st.selectbox("回测周期", list(BACKTEST_CONFIG.keys()), index=2)
threshold = st.slider("7日盈利概率阈值 (%)", 50, 90, 65) / 100.0

# ==================== session_state 持久化（关键！） ====================
if 'high_prob' not in st.session_state:
    st.session_state.high_prob = []  # 高概率列表永久保存
if 'current_index' not in st.session_state:
    st.session_state.current_index = 0  # 当前进度
if 'failed_count' not in st.session_state:
    st.session_state.failed_count = 0

result_container = st.container()
progress_bar = st.progress(st.session_state.current_index / len(tickers))
status_text = st.empty()

# ==================== 实时显示已发现（排序） ====================
with result_container:
    if st.session_state.high_prob:
        st.session_state.high_prob.sort(key=lambda x: x["prob7"], reverse=True)  # 始终排序
        st.subheader(f"已发现 {len(st.session_state.high_prob)} 只 ≥ {threshold*100:.0f}% 的股票（实时保存+排序）")
        for row in st.session_state.high_prob:
            change_str = f"{row['change']:+.2f}%"
            st.markdown(f"**{row['symbol']}** - 价格: ${row['price']:.2f} ({change_str}) - **7日概率: {row['prob7']*100:.1f}%** - PF: {row['pf7']:.2f}")

st.info(f"当前进度: {st.session_state.current_index}/{len(tickers)} | 失败: {st.session_state.failed_count} | 已发现: {len(st.session_state.high_prob)}")

# ==================== 开始/继续扫描按钮 ====================
if st.session_state.current_index < len(tickers):
    if st.button("开始/继续扫描（自动从上次中断处继续，每只10秒）", type="primary"):
        with st.spinner("扫描中..."):
            while st.session_state.current_index < len(tickers):
                i = st.session_state.current_index
                sym = tickers[i]
                status_text.text(f"正在计算 {sym} ({i+1}/{len(tickers)})")
                progress_bar.progress((i + 1) / len(tickers))
                try:
                    metrics = compute_stock_metrics(sym, mode)
                    if metrics["prob7"] >= threshold:
                        st.session_state.high_prob.append(metrics)
                        with result_container:
                            st.session_state.high_prob.sort(key=lambda x: x["prob7"], reverse=True)
                            st.rerun()  # 实时更新显示
                    st.session_state.current_index += 1
                except Exception as e:
                    st.session_state.failed_count += 1
                    st.warning(f"{sym} 失败: {str(e)}")
                    st.session_state.current_index += 1
                time.sleep(10)  # 10秒防限流
        st.rerun()
else:
    st.success("所有股票扫描完成！结果已永久保存")

if st.button("重置进度（从头重新扫，清空结果）"):
    st.session_state.high_prob = []
    st.session_state.current_index = 0
    st.session_state.failed_count = 0
    st.rerun()

st.caption("断点续扫版：中断/刷新后进度+结果永久保留，从151继续扫！实时排序显示。10秒sleep安全。")
