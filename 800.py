import streamlit as st
import requests
import numpy as np
import time
import pandas as pd
from io import StringIO

st.set_page_config(page_title="标普500 + 纳斯达克100 大盘扫描工具", layout="wide")
st.title("标普500 + 纳斯达克100 扫描工具（实时显示 + 防限流）")

# ==================== 核心函数保持不变（你的代码已完整） ====================
# HEADERS, BACKTEST_CONFIG, fetch_yahoo_ohlcv, ema_np, macd_hist_np, rsi_np, atr_np, rolling_mean_np, obv_np, backtest_with_stats, compute_stock_metrics
# 你的这些函数已经很好，无需改

# ==================== 加载成分股 ====================
# 你的 load_sp500_tickers 和 load_ndx100_tickers 很好

sp500 = load_sp500_tickers()
ndx100 = load_ndx100_tickers()
tickers = list(set(sp500 + ndx100))
st.write(f"总计 {len(tickers)} 只股票")

mode = st.selectbox("回测周期", list(BACKTEST_CONFIG.keys()), index=2)
threshold = st.slider("7日盈利概率阈值 (%)", 50, 90, 65) / 100.0

# ==================== 关键修复：用 session_state 实现“点击运行”自动扫描 ====================
if 'high_prob' not in st.session_state:
    st.session_state.high_prob = []
if 'scanned_count' not in st.session_state:
    st.session_state.scanned_count = 0
if 'failed_count' not in st.session_state:
    st.session_state.failed_count = 0

result_container = st.container()
progress_bar = st.progress(st.session_state.scanned_count / len(tickers))
status_text = st.empty()

with result_container:
    if st.session_state.high_prob:
        st.subheader(f"已发现 {len(st.session_state.high_prob)} 只 ≥ {threshold*100:.0f}% 的股票")
        st.session_state.high_prob.sort(key=lambda x: x["prob7"], reverse=True)
        for row in st.session_state.high_prob:
            change_str = f"{row['change']:+.2f}%"
            st.markdown(f"**{row['symbol']}** - 价格: ${row['price']:.2f} ({change_str}) - **7日概率: {row['prob7']*100:.1f}%** - PF: {row['pf7']:.2f}")

st.info(f"当前进度: {st.session_state.scanned_count}/{len(tickers)} | 失败: {st.session_state.failed_count}")

if st.button("开始/继续扫描（每只sleep 10秒，安全防限流）", type="primary"):
    with st.spinner("扫描中..."):
        start_idx = st.session_state.scanned_count
        for i in range(start_idx, len(tickers)):
            sym = tickers[i]
            status_text.text(f"正在计算 {sym} ({i+1}/{len(tickers)})")
            try:
                metrics = compute_stock_metrics(sym, mode)
                st.session_state.scanned_count += 1
                if metrics["prob7"] >= threshold:
                    st.session_state.high_prob.append(metrics)
                    with result_container:
                        st.session_state.high_prob.sort(key=lambda x: x["prob7"], reverse=True)
                        st.rerun()  # 实时更新列表
            except Exception as e:
                st.session_state.failed_count += 1
                st.warning(f"{sym} 失败: {str(e)}")
            progress_bar.progress(st.session_state.scanned_count / len(tickers))
            time.sleep(10)  # 10秒足够安全
        st.success("全扫描完成！")
    st.rerun()

if st.button("重置所有进度"):
    st.session_state.high_prob = []
    st.session_state.scanned_count = 0
    st.session_state.failed_count = 0
    st.rerun()

st.caption("点击按钮开始扫描，每只10秒安全防限流。高概率股票实时显示。假期市场概率偏低。")