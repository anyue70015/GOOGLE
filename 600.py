import streamlit as st
import requests
import numpy as np
import time
import pandas as pd
from io import StringIO

st.set_page_config(page_title="标普500 + 纳斯达克100 手动续扫工具", layout="wide")
st.title("标普500 + 纳斯达克100 手动续扫工具（点按钮扫下一只）")

# ==================== 所有核心函数（全展开，同之前） ====================
# (把之前完整版的 HEADERS 到 compute_stock_metrics 全部复制进来)

# ==================== 加载成分股 ====================
# (load_sp500_tickers, load_ndx100_tickers 同之前)

sp500 = load_sp500_tickers()
ndx100 = load_ndx100_tickers()
tickers = list(set(sp500 + ndx100))
st.write(f"总计 {len(tickers)} 只股票")

mode = st.selectbox("回测周期", list(BACKTEST_CONFIG.keys()), index=2)
threshold = st.slider("7日盈利概率阈值 (%)", 50, 90, 65) / 100.0

# ==================== 初始化 session_state ====================
if 'current_index' not in st.session_state:
    st.session_state.current_index = 0
if 'high_prob' not in st.session_state:
    st.session_state.high_prob = []
if 'failed_count' not in st.session_state:
    st.session_state.failed_count = 0
if 'scanned_symbols' not in st.session_state:
    st.session_state.scanned_symbols = []  # 已扫股票，避免重复

# ==================== 显示当前进度 ====================
st.info(f"当前进度: 已扫描 {st.session_state.current_index} / {len(tickers)} 只 | 已发现高概率: {len(st.session_state.high_prob)} 只 | 失败: {st.session_state.failed_count} 只")

progress_bar = st.progress(st.session_state.current_index / len(tickers) if len(tickers) > 0 else 0)

result_container = st.container()

# ==================== 实时显示已发现股票 ====================
if st.session_state.high_prob:
    with result_container:
        st.subheader(f"已发现 {len(st.session_state.high_prob)} 只 ≥ {threshold*100:.0f}% 的股票（实时保存）")
        st.session_state.high_prob.sort(key=lambda x: x["prob7"], reverse=True)
        for row in st.session_state.high_prob:
            change_str = f"{row['change']:+.2f}%"
            st.markdown(f"**{row['symbol']}** - 价格: ${row['price']:.2f} ({change_str}) - **7日概率: {row['prob7']*100:.1f}%** - PF: {row['pf7']:.2f}")

# ==================== 扫描按钮 ====================
if st.session_state.current_index < len(tickers):
    if st.button("扫描下一只股票（等待60秒）", type="primary"):
        sym = tickers[st.session_state.current_index]
        with st.spinner(f"正在计算 {sym} ..."):
            try:
                metrics = compute_stock_metrics(sym, mode)
                st.session_state.scanned_symbols.append(sym)
                if metrics["prob7"] >= threshold:
                    st.session_state.high_prob.append(metrics)
                st.success(f"{sym} 计算完成！7日概率: {metrics['prob7']*100:.1f}%")
            except Exception as e:
                st.session_state.failed_count += 1
                st.error(f"{sym} 失败: {str(e)}")
            time.sleep(10)  # 60秒防限流
        st.session_state.current_index += 1
        st.rerun()  # 刷新页面更新进度
else:
    st.success("所有股票扫描完成！")

# ==================== 重置按钮 ====================
if st.button("重置所有进度（从头开始）"):
    st.session_state.current_index = 0
    st.session_state.high_prob = []
    st.session_state.failed_count = 0
    st.session_state.scanned_symbols = []
    st.rerun()

st.caption("手动点按钮版：每次点一次扫1只，网络中断也没事，进度永久保存。高概率实时显示！假期市场概率偏低，慢慢扫～")
