import streamlit as st
import requests
import numpy as np
import time
import pandas as pd

# ==================== 1. 基础配置 ====================
st.set_page_config(page_title="极品短线扫描工具", layout="wide")
st.title("🎯 全市场极品短线扫描 (修正报错版)")
st.markdown("说明：**锁定周五数据** | 按照 **PF7 (盈利因子)** 降序排列")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
}

# 预设核心标的
CORE_ETFS = ["SPY", "QQQ", "IWM", "DIA", "SLV", "GLD", "GDX", "TLT", "SOXX", "SMH", "KWEB", "BITO"]
TECH_STOCKS = ["AAPL", "MSFT", "NVDA", "WDC", "AMD", "META", "NFLX", "AVGO", "COST"]

# ==================== 2. 数据处理函数 ====================
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_clean_data(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1y&interval=1d"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        data = resp.json()["chart"]["result"][0]
        quote = data["indicators"]["quote"][0]
        df = pd.DataFrame({
            "close": quote["close"],
            "high": quote["high"],
            "low": quote["low"],
            "volume": quote["volume"]
        })
        df.dropna(inplace=True) # 过滤非交易日空行
        return df if len(df) > 30 else None
    except:
        return None

def compute_metrics(symbol):
    df = fetch_clean_data(symbol)
    if df is None: return None
    
    close = df["close"].values
    volume = df["volume"].values
    
    # PF7 盈利因子计算 (保命指标)
    rets = np.diff(close) / (close[:-1] + 1e-9)
    pos_sum = rets[rets > 0].sum()
    neg_sum = abs(rets[rets <= 0].sum())
    pf7 = float(round(pos_sum / neg_sum, 2)) if neg_sum > 0 else 9.99
    
    # 7日上涨概率
    prob7 = round((rets > 0).mean() * 100, 1)
    
    # 得分逻辑
    vol_ma = df["volume"].rolling(20).mean().values[-1]
    s1 = 1 if close[-1] > close[-2] else 0
    s2 = 1 if volume[-1] > vol_ma * 1.1 else 0
    s3 = 1 if close[-1] > df["close"].rolling(20).mean().iloc[-1] else 0
    s4 = 1 if (close[-1] - df["low"].iloc[-1]) / (df["high"].iloc[-1] - df["low"].iloc[-1] + 1e-9) > 0.5 else 0
    s5 = 1 if rets[-1] > 0 else 0
    
    return {
        "代码": symbol,
        "现价": round(float(close[-1]), 2),
        "得分": int(s1 + s2 + s3 + s4 + s5),
        "胜率%": float(prob7),
        "PF7效率": pf7
    }

# ==================== 3. 界面逻辑 ====================
st.sidebar.header("扫描配置")
choice = st.sidebar.multiselect("选择范围", ["核心ETF", "科技股龙头"], default=["核心ETF"])

if st.sidebar.button("开始执行全量扫描"):
    symbols = []
    if "核心ETF" in choice: symbols += CORE_ETFS
    if "科技股龙头" in choice: symbols += TECH_STOCKS
    
    symbols = list(set(symbols))
    results = []
    
    bar = st.progress(0)
    for i, s in enumerate(symbols):
        m = compute_metrics(s)
        if m: results.append(m)
        bar.progress((i + 1) / len(symbols))
    
    if results:
        # 转换为 DataFrame 并排序
        df_res = pd.DataFrame(results).sort_values("PF7效率", ascending=False)
        
        # 核心：使用最稳健的显示方式，避开 Style 报错
        st.subheader("📊 扫描结果汇总 (按 PF7 盈利效率排序)")
        st.dataframe(df_res, use_container_width=True)
        
        # 导出报告
        txt = f"报告生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        txt += "-"*50 + "\n"
        for _, r in df_res.iterrows():
            txt += f"{r['代码']}: PF7={r['PF7效率']} | 胜率={r['胜率%']}% | 得分={r['得分']}/5\n"
        
        st.download_button("📥 导出 TXT 报告", txt, f"Report_{time.strftime('%Y%m%d')}.txt")
    else:
        st.error("数据抓取失败，请检查网络。")
