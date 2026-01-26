import streamlit as st
import yfinance as yf
import numpy as np
import time
import pandas as pd
import random
import os
import json
from datetime import datetime

st.set_page_config(page_title="量化实战版-30只精选扫描", layout="wide")
st.title("🛡️ 我的30只股票-滚动回测终极版")

# ── 进度持久化 ──
progress_file = "scan_progress_final.json"

if 'high_prob' not in st.session_state:
    st.session_state.high_prob = []
    if os.path.exists(progress_file):
        try:
            with open(progress_file, "r") as f:
                data = json.load(f)
                st.session_state.high_prob = data.get("high_prob", [])
                st.session_state.scanned_symbols = set(data.get("scanned_symbols", []))
        except: pass

# ==================== 科学计算引擎 (核心改进) ====================
def ema_np(x, span):
    alpha = 2 / (span + 1)
    ema = np.empty_like(x); ema[0] = x[0]
    for i in range(1, len(x)): ema[i] = alpha * x[i] + (1 - alpha) * ema[i-1]
    return ema

def backtest_with_stats(close, score, steps=7):
    """最核心改进：严格计算盈亏比，排除虚高"""
    if len(close) <= steps + 1: return 0.5, 0.0
    idx = np.where(score[:-steps] >= 3)[0] # 只有3分以上才算有效信号
    if len(idx) == 0: return 0.5, 0.0
    
    rets = close[idx + steps] / close[idx] - 1
    win_rate = (rets > 0).mean()
    pos_sum = rets[rets > 0].sum()
    neg_sum = abs(rets[rets <= 0].sum())
    
    # PF计算：盈利总额/亏损总额，若无亏损则封顶9.9
    pf = pos_sum / neg_sum if neg_sum > 0 else (9.9 if pos_sum > 0 else 0.0)
    return win_rate, pf

@st.cache_data(ttl=1800)
def compute_premium_metrics(symbol, period_str="1y"):
    try:
        df = yf.Ticker(symbol).history(period=period_str, interval="1d", auto_adjust=True)
        if len(df) < 50: return None
        
        close, high, low, vol = df['Close'].values, df['High'].values, df['Low'].values, df['Volume'].values
        
        # 指标计算
        macd = (ema_np(close, 12) - ema_np(close, 26)) - ema_np((ema_np(close, 12) - ema_np(close, 26)), 9)
        # 这里的Score判定更严格
        s_macd = (macd > 0).astype(int)
        s_vol = (vol > pd.Series(vol).rolling(20).mean().values * 1.1).astype(int)
        s_rsi = (pd.Series(close).rolling(14).apply(lambda x: 100 - (100/(1+(x.diff().where(x.diff()>0,0).mean()/x.diff().where(x.diff()<0,0).abs().mean()))), raw=False) >= 60).astype(int)
        
        score_arr = s_macd + s_vol + (s_rsi.fillna(0).values)
        
        # --- 学习过来的好东西：滚动切片计算 ---
        # 只拿截至昨天的历史数据算PF，避免今天涨了拉高历史分数的舞弊
        prob7, pf7 = backtest_with_stats(close[:-1], score_arr[:-1], 7)
        
        # 增加流动性检查 (134万资金安全线)
        dollar_vol = (vol[-10:] * close[-10:]).mean()
        is_safe = dollar_vol > 50_000_000 # 日均5000万美金才安全
        
        return {
            "symbol": symbol,
            "price": close[-1],
            "score": int(score_arr[-1]),
            "prob7": prob7,
            "pf7": pf7,
            "is_safe": is_safe,
            "change": (close[-1]/close[-2]-1)*100
        }
    except: return None

# ==================== UI & 自动扫描 ====================
my_30 = ["LLY", "GEV", "MIRM", "ABBV", "HWM", "GE", "MU", "HII", "SCCO", "SNDK", "WDC", "SLV", "STX", "JNJ", "FOXA", "BK", "RTX", "WELL", "PH", "GVA", "AHR", "ATRO", "GLW", "CMI", "APH", "SMH", "TPR", "SOXX", "COR", "TSM", "NVDA", "GOOG", "ASTS"]

if 'scanned_symbols' not in st.session_state: st.session_state.scanned_symbols = set()

col_ctrl1, col_ctrl2 = st.columns(2)
with col_ctrl1:
    if st.button("🚀 开始全量科学扫描"):
        st.session_state.scanning = True
with col_ctrl2:
    if st.button("🔄 重置"):
        st.session_state.high_prob = []; st.session_state.scanned_symbols = set()
        if os.path.exists(progress_file): os.remove(progress_file)
        st.rerun()

# 自动循环执行
if st.session_state.get('scanning', False):
    remaining = [s for s in my_30 if s not in st.session_state.scanned_symbols]
    if remaining:
        target = remaining[0]
        res = compute_premium_metrics(target)
        if res: st.session_state.high_prob.append(res)
        st.session_state.scanned_symbols.add(target)
        # 保存进度
        with open(progress_file, "w") as f:
            json.dump({"high_prob": st.session_state.high_prob, "scanned_symbols": list(st.session_state.scanned_symbols)}, f)
        st.rerun()
    else:
        st.session_state.scanning = False
        st.success("全部扫描完成！")

# 结果展示
if st.session_state.high_prob:
    df = pd.DataFrame(st.session_state.high_prob).sort_values("pf7", ascending=False)
    
    for _, r in df.iterrows():
        safe_tag = "✅ 安全" if r['is_safe'] else "⚠️ 低流动性"
        color = "green" if r['score'] >= 3 else "black"
        # 紧凑显示：单行展示核心数据
        st.markdown(f":{color}[**{r['symbol']}**] | PF7: **{r['pf7']:.2f}** | 胜率: {r['prob7']*100:.1f}% | 得分: **{r['score']}** | 价格: ${r['price']:.2f} ({r['change']:+.2f}%) | {safe_tag}")
