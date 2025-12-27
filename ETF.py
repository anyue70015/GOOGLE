import streamlit as st
import requests
import numpy as np
import time
import pandas as pd
from io import StringIO

st.set_page_config(page_title="全市场极品扫描-2026回本专用", layout="wide")
st.title("🎯 全市场极品短线扫描 (PF7 排序 + 自动补全列表)")

# ==================== 核心配置 ====================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
}

CORE_ETFS = ["SPY", "QQQ", "IWM", "DIA", "SLV", "GLD", "GDX", "TLT", "SOXX", "SMH", "KWEB", "BITO"]

# ==================== 动态列表获取逻辑 ====================
@st.cache_data(ttl=86400) # 列表每天只更新一次
def get_all_tickers():
    """从网络自动获取各指数成分股"""
    # 标普 500
    try:
        sp500_url = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
        sp500 = pd.read_csv(sp500_url)['Symbol'].tolist()
    except:
        sp500 = ["AAPL", "MSFT", "NVDA", "WDC"] # 备份方案
        
    # 纳指 100
    ndx100 = ["AAPL", "MSFT", "AMZN", "NVDA", "META", "GOOGL", "GOOG", "TSLA", "AVGO", "COST", "ADBE", "AMD", "NFLX", "PEP", "WDC"]
    
    # 罗素 2000 (精选活跃小盘股，因2000只扫描太慢，建议先放核心或ETF)
    r2000 = ["IWM", "VRTX", "KWC", "UPST", "MARA"] 
    
    return sp500, ndx100, r2000

# ==================== 数据抓取与清洗 ====================
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_clean_data(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1y&interval=1d"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        data = resp.json()["chart"]["result"][0]
        quote = data["indicators"]["quote"][0]
        df = pd.DataFrame({"close": quote["close"], "high": quote["high"], "low": quote["low"], "volume": quote["volume"]})
        df.dropna(inplace=True) 
        return df if len(df) > 50 else None
    except:
        return None

def compute_metrics(symbol):
    df = fetch_clean_data(symbol)
    if df is None: return None
    close, volume = df["close"].values, df["volume"].values
    
    # 1. PF7 盈利因子
    rets = np.diff(close) / close[:-1]
    pf7 = round(rets[rets > 0].sum() / (abs(rets[rets <= 0].sum()) + 1e-9), 2)
    
    # 2. 7日胜率
    prob7 = round((rets > 0).mean() * 100, 1)
    
    # 3. 5项得分
    vol_ma20 = df["volume"].rolling(20).mean().values
    s1 = 1 if close[-1] > close[-2] else 0
    s2 = 1 if volume[-1] > vol_ma20[-1] * 1.1 else 0
    s3 = 1 if close[-1] > df["close"].rolling(20).mean().iloc[-1] else 0
    s4 = 1 if (close[-1] - df["low"].iloc[-1]) / (df["high"].iloc[-1] - df["low"].iloc[-1] + 1e-9) > 0.5 else 0
    s5 = 1 if rets[-1] > 0 else 0
    
    return {"symbol": symbol, "price": round(close[-1], 2), "score": s1+s2+s3+s4+s5, "prob7": prob7, "pf7": pf7}

# ==================== 界面控制 ====================
st.sidebar.header("扫描范围设置")
choice = st.sidebar.multiselect("对象", ["S&P 500", "Nasdaq 100", "Russell 2000", "Core ETFs"], default=["Core ETFs"])

# 限制扫描数量防止 API 屏蔽
max_num = st.sidebar.slider("最大扫描标的数量", 10, 500, 50)

if st.sidebar.button("🚀 开始全量扫描"):
    sp, nd, r2 = get_all_tickers()
    symbols = []
    if "S&P 500" in choice: symbols += sp
    if "Nasdaq 100" in choice: symbols += nd
    if "Russell 2000" in choice: symbols += r2
    if "Core ETFs" in choice: symbols += CORE_ETFS
    
    symbols = list(set(symbols))[:max_num] # 去重并限流
    results = []
    bar = st.progress(0)
    msg = st.empty()
    
    for i, s in enumerate(symbols):
        msg.text(f"正在扫描 ({i+1}/{len(symbols)}): {s}")
        m = compute_metrics(s)
        if m: results.append(m)
        bar.progress((i + 1) / len(symbols))
    
    if results:
        df_res = pd.DataFrame(results).sort_values("pf7", ascending=False)
        st.subheader(f"📊 扫描报告 (按 PF7 排序，共 {len(df_res)} 只)")
        st.dataframe(df_res.style.background_gradient(subset=['pf7'], cmap='RdYlGn'))
        
        # 导出 TXT
        txt = f"--- 极品扫描报告 ({time.strftime('%Y-%m-%d')}) ---\n"
        txt += f"{'Symbol':<8} | {'PF7':<6} | {'Prob7':<8} | {'Score':<5}\n"
        txt += "-"*40 + "\n"
        for _, r in df_res.iterrows():
            txt += f"{r['symbol']:<8} | {r['pf7']:<6} | {r['prob7']:<8} | {r['score']}/5\n"
        
        st.download_button("📥 导出 TXT 报告", txt, f"Report_{time.strftime('%Y%m%d')}.txt")
    else:
        st.error("数据抓取失败。")
