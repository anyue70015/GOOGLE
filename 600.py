import streamlit as st
import requests
import numpy as np
import time
import pandas as pd
from io import StringIO

st.set_page_config(page_title="标普500 + 纳斯达克100 大盘扫描工具", layout="wide")
st.title("标普500 + 纳斯达克100 实时扫描工具（超65%立即显示）")

# ==================== 所有计算函数（同上一个版本，完全复制） ====================
# HEADERS, BACKTEST_CONFIG, fetch_yahoo_ohlcv, ema_np, macd_hist_np, rsi_np, atr_np, 
# rolling_mean_np, obv_np, backtest_with_stats, compute_stock_metrics
# （把上一个消息里从 HEADERS 到 compute_stock_metrics 的所有代码复制进来，不要漏！）

# ==================== 加载成分股（同上） ====================
# load_sp500_tickers, load_ndx100_tickers, tickers

sp500 = load_sp500_tickers()
ndx100 = load_ndx100_tickers()
tickers = list(set(sp500 + ndx100))
st.write(f"总计 {len(tickers)} 只股票（2025年12月最新去重）")

mode = st.selectbox("回测周期", list(BACKTEST_CONFIG.keys()), index=2)  # 默认1年
threshold = st.slider("7日盈利概率阈值 (%)", 50, 90, 65) / 100.0

# ==================== 实时显示容器 ====================
placeholder = st.empty()  # 用于实时更新列表
result_container = st.container()  # 显示实时结果

high_prob = []  # 存储所有符合的
failed_count = 0

progress_bar = st.progress(0)
status_text = st.empty()
count_text = st.empty()

with placeholder.container():
    st.info("扫描开始，每只股票等待60秒。超过阈值的会**立即显示**在下面！")

with st.spinner("超慢实时扫描启动..."):
    for i, sym in enumerate(tickers):
        status_text.text(f"正在计算 {sym} ({i+1}/{len(tickers)})")
        progress_bar.progress((i + 1) / len(tickers))
        try:
            metrics = compute_stock_metrics(sym, mode)
            if metrics["prob7"] >= threshold:
                high_prob.append(metrics)
                # 实时更新显示
                high_prob.sort(key=lambda x: x["prob7"], reverse=True)  # 保持排序
                with result_container:
                    st.subheader(f"已发现 {len(high_prob)} 只 ≥ {threshold*100:.0f}% 的股票（实时更新）")
                    for row in high_prob:
                        change_str = f"{row['change']:+.2f}%"
                        st.markdown(f"**{row['symbol']}** - 价格: ${row['price']:.2f} ({change_str}) - **7日概率: {row['prob7']*100:.1f}%** - PF: {row['pf7']:.2f}")
        except Exception as e:
            failed_count += 1
            st.warning(f"{sym} 失败: {str(e)}")
        count_text.text(f"已完成: {i+1} | 已发现高概率: {len(high_prob)} | 失败: {failed_count}")
        time.sleep(60)  # 60秒超安全

# 扫描结束最终总结
st.success(f"全扫描完成！共发现 {len(high_prob)} 只7日概率 ≥ {threshold*100:.0f}% 的股票")
if high_prob:
    with result_container:
        st.subheader("最终榜单（按概率降序）")
        for row in high_prob:
            change_str = f"{row['change']:+.2f}%"
            st.markdown(f"**{row['symbol']}** - 价格: ${row['price']:.2f} ({change_str}) - **7日概率: {row['prob7']*100:.1f}%** - PF: {row['pf7']:.2f}")

st.caption("实时显示版：每扫到一只超阈值的，就立刻显示！假期市场概率偏低，耐心等～")
