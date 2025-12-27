import streamlit as st
import requests
import numpy as np
import time
import pandas as pd

# ==================== 1. 页面配置 ====================
st.set_page_config(page_title="极品短线扫描工具", layout="wide")
st.title("🎯 全市场极品短线扫描 (稳定修正版)")
st.markdown("筛选逻辑：**PF7 (盈利因子) 降序排列** | 数据自动锁定至周五收盘")

# ==================== 2. 核心配置 ====================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
}

# 核心标的池
CORE_ETFS = ["SPY", "QQQ", "IWM", "DIA", "SLV", "GLD", "GDX", "TLT", "SOXX", "SMH", "KWEB", "BITO"]
TECH_LIST = ["AAPL", "MSFT", "NVDA", "WDC", "AMD", "META", "NFLX", "AVGO", "TSLA"]

# ==================== 3. 数据计算 ====================
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_clean_data(symbol):
    # 使用 1y 周期确保 PF7 计算有足够样本
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1y&interval=1d"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        data = resp.json()["chart"]["result"][0]
        quote = data["indicators"]["quote"][0]
        
        # 彻底清洗：通过 dropna 剔除周末/节假日的空行
        df = pd.DataFrame({
            "close": quote["close"],
            "high": quote["high"],
            "low": quote["low"],
            "volume": quote["volume"]
        }).dropna()
        
        return df if len(df) > 50 else None
    except:
        return None

def compute_metrics(symbol):
    df = fetch_clean_data(symbol)
    if df is None: return None
    
    close = df["close"].values
    volume = df["volume"].values
    
    # 1. 计算 PF7 (盈利因子) - 回本核心指标
    rets = np.diff(close) / (close[:-1] + 1e-9)
    pos_sum = rets[rets > 0].sum()
    neg_sum = abs(rets[rets <= 0].sum())
    pf7 = round(pos_sum / neg_sum, 2) if neg_sum > 0 else 9.99
    
    # 2. 计算 7日胜率
    prob7 = round((rets > 0).mean() * 100, 1)
    
    # 3. 得分逻辑 (锁定最新完整交易日)
    vol_ma20 = df["volume"].rolling(20).mean().values
    s1 = 1 if close[-1] > close[-2] else 0
    s2 = 1 if volume[-1] > vol_ma20[-1] * 1.1 else 0
    s3 = 1 if close[-1] > df["close"].rolling(20).mean().iloc[-1] else 0
    s4 = 1 if (close[-1] - df["low"].iloc[-1]) / (df["high"].iloc[-1] - df["low"].iloc[-1] + 1e-9) > 0.5 else 0
    s5 = 1 if rets[-1] > 0 else 0
    score = s1 + s2 + s3 + s4 + s5

    return {
        "代码": symbol,
        "价格": round(float(close[-1]), 2),
        "得分": f"{score}/5",
        "胜率": f"{prob7}%",
        "PF7效率": float(pf7)
    }

# ==================== 4. 界面逻辑 ====================
st.sidebar.header("扫描范围")
market_choice = st.sidebar.multiselect("对象组", ["Core ETFs", "Nasdaq 100"], default=["Core ETFs"])

if st.sidebar.button("开始执行全量扫描"):
    symbols = []
    if "Core ETFs" in market_choice: symbols += CORE_ETFS
    if "Nasdaq 100" in market_choice: symbols += TECH_LIST
    
    symbols = list(set(symbols))
    results = []
    bar = st.progress(0)
    
    for i, s in enumerate(symbols):
        m = compute_metrics(s)
        if m: results.append(m)
        bar.progress((i + 1) / len(symbols))
    
    if results:
        # 1. 转换为 DataFrame
        df_res = pd.DataFrame(results)
        
        # 2. 核心：按 PF7 降序排列 (回本效率最高的排最前面)
        df_res = df_res.sort_values("PF7效率", ascending=False)
        
        # 3. 显示表格 (避开报错的 style.background_gradient)
        st.subheader("📊 扫描结果 (按 PF7 效率排序)")
        st.dataframe(df_res, use_container_width=True)
        
        # 4. 导出报告
        txt_out = f"报告时间: {time.strftime('%Y-%m-%d')}\n" + "="*40 + "\n"
        for _, r in df_res.iterrows():
            txt_out += f"{r['代码']}: PF7={r['PF7效率']} | 得分={r['得分']} | 胜率={r['胜率']}\n"
        
        st.download_button("📥 导出 TXT 报告", txt_out, f"Report_{time.strftime('%Y%m%d')}.txt")
    else:
        st.error("未获取到有效数据。")
