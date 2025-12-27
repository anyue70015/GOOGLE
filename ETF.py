import streamlit as st
import requests
import numpy as np
import time
import pandas as pd
from io import StringIO

# ==================== 页面配置 ====================
st.set_page_config(page_title="极品短线扫描工具", layout="wide")
st.title("🎯 全市场极品短线扫描 (周末修正版)")

# ==================== 核心配置 ====================
# 这里的 HEADERS 已经过清理，确保无不可见字符
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
}

CORE_ETFS = ["SPY", "QQQ", "IWM", "DIA", "SLV", "GLD", "GDX", "TLT", "SOXX", "SMH", "KWEB", "BITO"]

# ==================== 数据抓取与清洗 ====================
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_clean_data(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1y&interval=1d"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()["chart"]["result"][0]
        quote = data["indicators"]["quote"][0]
        
        # 建立DataFrame并彻底清洗周末/节假日产生的空行
        df = pd.DataFrame({
            "close": quote["close"],
            "high": quote["high"],
            "low": quote["low"],
            "volume": quote["volume"]
        })
        df.dropna(inplace=True)
        
        if len(df) < 50:
            return None
        return df
    except Exception:
        return None

# ==================== 核心指标计算 ====================
def compute_stock_metrics(symbol):
    df = fetch_clean_data(symbol)
    if df is None: return None
    
    close = df["close"].values
    volume = df["volume"].values
    
    # 1. 计算 PF7 (盈利因子)
    # 取过去1年的日收益率进行回测
    rets = np.diff(close) / (close[:-1] + 1e-9)
    pos_sum = rets[rets > 0].sum()
    neg_sum = abs(rets[rets <= 0].sum())
    pf7 = round(pos_sum / neg_sum, 2) if neg_sum > 0 else 9.99
    
    # 2. 计算 7日上涨概率
    prob7 = round((rets > 0).mean() * 100, 1)
    
    # 3. 5项技术得分 (基于最新完成的交易日)
    vol_ma20 = df["volume"].rolling(20).mean().values
    
    s1 = 1 if close[-1] > close[-2] else 0
    s2 = 1 if volume[-1] > vol_ma20[-1] * 1.1 else 0
    s3 = 1 if close[-1] > df["close"].rolling(20).mean().iloc[-1] else 0
    s4 = 1 if (close[-1] - df["low"].iloc[-1]) / (df["high"].iloc[-1] - df["low"].iloc[-1] + 1e-9) > 0.5 else 0
    s5 = 1 if rets[-1] > 0 else 0
    score = s1 + s2 + s3 + s4 + s5

    return {
        "代码": symbol,
        "现价": round(close[-1], 2),
        "得分": f"{score}/5",
        "胜率": f"{prob7}%",
        "PF7效率": pf7
    }

# ==================== 界面逻辑 ====================
st.sidebar.header("扫描设置")
targets = st.sidebar.multiselect("选择范围", ["Nasdaq 100", "Core ETFs"], default=["Core ETFs"])

if st.sidebar.button("开始执行全量扫描"):
    symbols = []
    if "Core ETFs" in targets: 
        symbols += CORE_ETFS
    if "Nasdaq 100" in targets: 
        symbols += ["AAPL", "MSFT", "NVDA", "WDC", "AMD", "META", "NFLX", "AVGO", "COST"]
    
    symbols = list(set(symbols)) # 去重
    results = []
    progress = st.progress(0)
    
    for i, s in enumerate(symbols):
        m = compute_stock_metrics(s)
        if m: 
            results.append(m)
        progress.progress((i + 1) / len(symbols))
    
    if results:
        # 按 PF7 降序排列
        df_res = pd.DataFrame(results).sort_values("PF7效率", ascending=False)
        
        st.subheader("📊 扫描结果汇总 (按 PF7 盈利效率排序)")
        st.dataframe(df_res.style.background_gradient(subset=['PF7效率'], cmap='RdYlGn'))
        
        # 导出报告
        txt_content = f"极品短线扫描报告 - {time.strftime('%Y-%m-%d')}\n"
        txt_content += "="*50 + "\n"
        for _, r in df_res.iterrows():
            txt_content += f"{r['代码']}: PF7={r['PF7效率']} | 得分={r['得分']} | 胜率={r['胜率']}\n"
        
        st.download_button("📥 导出 TXT 报告", txt_content, f"Report_{time.strftime('%Y%m%d')}.txt")
    else:
        st.error("数据抓取失败，请检查网络或更换标的重试。")
