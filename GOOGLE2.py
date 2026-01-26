import streamlit as st
import yfinance as yf
import numpy as np
import time
import pandas as pd
import random
import os
import json
from datetime import datetime, timedelta

st.set_page_config(page_title="股票短线深度扫描器", layout="wide")
st.title("📊 股票短线深度扫描工具 (一年测算 + 40日详情)")

# ── 自动计算周期 ──
# 测算 PF7 需要一年数据（约250交易日），显示详情需要最近40交易日
END_DATE_STR = "2026-01-24" 
end_dt = datetime.strptime(END_DATE_STR, "%Y-%m-%d")
start_dt = end_dt - timedelta(days=380) # 考虑到节假日，多取几天确保满一年
START_DATE = start_dt.strftime("%Y-%m-%d")
END_DATE = END_DATE_STR

st.info(f"📅 测算周期：{START_DATE} 至 {END_DATE} | 详情显示：最近 40 个交易日")

# ── 持久化进度文件 ──
progress_file = "scan_progress_full_year.json"
if 'high_prob' not in st.session_state: st.session_state.high_prob = []
if 'scanned_symbols' not in st.session_state: st.session_state.scanned_symbols = set()

# ── 核心工具函数 ──
def ema_np(x, span):
    alpha = 2 / (span + 1)
    ema = np.empty_like(x)
    ema[0] = x[0]
    for i in range(1, len(x)): ema[i] = alpha * x[i] + (1 - alpha) * ema[i-1]
    return ema

def rsi_np(close, period=14):
    delta = np.diff(close, prepend=close[0])
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    alpha = 1 / period
    g_ema, l_ema = np.empty_like(gain), np.empty_like(loss)
    g_ema[0], l_ema[0] = gain[0], loss[0]
    for i in range(1, len(gain)):
        g_ema[i] = alpha * gain[i] + (1 - alpha) * g_ema[i-1]
        l_ema[i] = alpha * loss[i] + (1 - alpha) * l_ema[i-1]
    return 100 - (100 / (1 + (g_ema / (l_ema + 1e-9))))

def backtest_stats(close, score, steps=7):
    # 只要得分 >= 2 就视为短线信号触发点
    idx = np.where(score[:-steps] >= 2)[0]
    if len(idx) == 0: return 0.0, 0.0
    
    rets = close[idx + steps] / close[idx] - 1
    win_rate = (rets > 0).mean()
    
    pos_ret = rets[rets > 0].sum()
    neg_ret = abs(rets[rets <= 0].sum())
    pf = pos_ret / neg_ret if neg_ret > 0 else (9.9 if pos_ret > 0 else 0.0)
    return win_rate, pf

# ==================== 核心计算逻辑 ====================
@st.cache_data(ttl=3600, show_spinner=False)
def compute_comprehensive_metrics(symbol):
    try:
        # 增加重试机制和随机延迟防止被封
        time.sleep(random.uniform(0.3, 0.8))
        df = yf.Ticker(symbol).history(start=START_DATE, end=END_DATE, interval="1d")
        if df.empty or len(df) < 50: return None
        
        close = df['Close'].values.astype(float)
        high = df['High'].values.astype(float)
        low = df['Low'].values.astype(float)
        vol = df['Volume'].values.astype(float)
        dates = df.index.strftime("%Y-%m-%d").values

        # 1. 计算技术指标
        macd_line = ema_np(close, 12) - ema_np(close, 26)
        macd_h = macd_line - ema_np(macd_line, 9)
        rsi = rsi_np(close)
        v_ma20 = pd.Series(vol).rolling(20).mean().values
        
        # 2. 逐日评分 (一年周期)
        scores = []
        for i in range(len(close)):
            s = 0
            if macd_h[i] > 0: s += 1                # 趋势：MACD红柱
            if i > 0 and vol[i] > v_ma20[i] * 1.1: s += 1 # 量能：放量10%
            if 55 <= rsi[i] <= 85: s += 1          # 动能：RSI进入强势区且未极端超买
            if i > 0 and close[i] > close[i-1]: s += 1 # 价格：今日收涨
            if macd_h[i] > (macd_h[i-1] if i>0 else 0): s += 1 # 加速：红柱增长
            scores.append(s)
        
        score_arr = np.array(scores)
        
        # 3. 计算一年周期的统计数据
        prob7, pf7 = backtest_stats(close, score_arr)
        
        # 4. 提取最近 40 个交易日的详情
        detail_count = min(40, len(close))
        recent_details = []
        for i in range(len(close) - detail_count, len(close)):
            change = (close[i] / close[i-1] - 1) * 100 if i > 0 else 0
            recent_details.append({
                "date": dates[i],
                "price": round(close[i], 2),
                "change": f"{change:+.2f}%",
                "score": scores[i]
            })
            
        return {
            "symbol": symbol.upper(),
            "prob7": prob7,
            "pf7": pf7,
            "current_price": close[-1],
            "details": recent_details[::-1], # 倒序排列，最近日期在前
            "signal_count": len(np.where(score_arr[:-7] >= 2)[0])
        }
    except Exception:
        return None

# ==================== 侧边栏与上传 ====================
with st.sidebar:
    st.header("控制面板")
    uploaded_file = st.file_uploader("上传股票代码 TXT", type=["txt"])
    if st.button("🔄 清空所有进度"):
        st.session_state.high_prob = []
        st.session_state.scanned_symbols = set()
        st.rerun()

if not uploaded_file:
    st.warning("请在侧边栏上传 TXT 文件（每行一个代码）")
    st.stop()

tickers = list(dict.fromkeys([t.strip().upper() for t in uploaded_file.read().decode().replace(","," ").split() if t.strip()]))

# ==================== 执行扫描 ====================
if st.button("🚀 开始全量深度扫描"):
    st.session_state.scanning = True

if st.session_state.get('scanning'):
    progress_bar = st.progress(0)
    status = st.empty()
    
    remaining = [s for s in tickers if s not in st.session_state.scanned_symbols]
    for i, sym in enumerate(remaining):
        status.text(f"正在分析 {sym} ({i+1}/{len(remaining)})")
        result = compute_comprehensive_metrics(sym)
        if result:
            st.session_state.high_prob.append(result)
        st.session_state.scanned_symbols.add(sym)
        progress_bar.progress((i + 1) / len(remaining))
    
    st.session_state.scanning = False
    st.success("扫描完成！")

# ==================== 结果呈现 ====================
if st.session_state.high_prob:
    # 转换为 DataFrame 方便排序
    display_data = []
    for item in st.session_state.high_prob:
        display_data.append({
            "代码": item['symbol'],
            "7日胜率(年)": f"{item['prob7']*100:.1f}%",
            "PF7盈利因子(年)": round(item['pf7'], 2),
            "样本信号数": item['signal_count'],
            "当前价格": item['current_price'],
            "raw_pf7": item['pf7']
        })
    
    df_main = pd.DataFrame(display_data).sort_values("raw_pf7", ascending=False)
    
    st.subheader("🏆 测算排行 (按一年期 PF7 排序)")
    st.dataframe(df_main.drop(columns=['raw_pf7']), use_container_width=True)

    st.divider()
    st.subheader("明细查看：最近 40 个交易日评分记录")
    
    # 使用选择框查看具体某只股票的 40 日详情
    selected_stock = st.selectbox("选择股票查看 40 日详情", options=[item['symbol'] for item in st.session_state.high_prob])
    
    if selected_stock:
        stock_data = next(item for item in st.session_state.high_prob if item['symbol'] == selected_stock)
        
        # 显示 40 日详情表格
        df_details = pd.DataFrame(stock_data['details'])
        df_details.columns = ["日期", "收盘价", "涨跌幅", "综合得分(0-5)"]
        
        # 着色：得分越高颜色越深
        st.table(df_details.style.background_gradient(subset=["综合得分(0-5)"], cmap="YlGn"))

st.caption("提示：PF7 > 1.5 且 胜率 > 55% 通常被视为该策略对此股有较好的适配性。数据来自 Yahoo Finance。")
