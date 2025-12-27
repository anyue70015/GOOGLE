import streamlit as st
import requests
import numpy as np
import time
import pandas as pd
from io import StringIO

# ==================== 页面配置 ====================
st.set_page_config(page_title="全市场短线极品扫描 - 2026回本专用", layout="wide")
st.title("🎯 全市场短线极品扫描 (PF7 优先排序)")

# ==================== 核心常量 ====================
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"}

CORE_ETFS = ["SPY", "QQQ", "IWM", "DIA", "SLV", "GLD", "GDX", "TLT", "SOXX", "SMH", "KWEB", "BITO"]

BACKTEST_CONFIG = {"1年": {"range": "1y"}, "2年": {"range": "2y"}, "5年": {"range": "5y"}}

# ==================== 数据源加载 ====================
@st.cache_data(ttl=86400)
def load_tickers(market_type):
    if market_type == "S&P 500":
        url = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
        return pd.read_csv(StringIO(requests.get(url, headers=HEADERS).text))['Symbol'].tolist()
    elif market_type == "Nasdaq 100":
        return ["AAPL","MSFT","AMZN","NVDA","META","GOOGL","GOOG","TSLA","AVGO","COST","ADBE","AMD","NFLX","PEP","AZN","LIN","WDC"] # 简缩版示例
    elif market_type == "Russell 2000":
        return ["IWM", "VRTX", "KWC"] # 罗素2000通常扫描指数ETF或代表性成分
    return []

# ==================== 核心计算函数 ====================
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_data(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1y&interval=1d"
    resp = requests.get(url, headers=HEADERS, timeout=10)
    data = resp.json()["chart"]["result"][0]
    quote = data["indicators"]["quote"][0]
    close = np.array(quote["close"], dtype=float)
    volume = np.array(quote["volume"], dtype=float)
    mask = ~np.isnan(close)
    return close[mask], volume[mask]

def compute_metrics(symbol):
    close, volume = fetch_data(symbol)
    # 简易得分逻辑
    vol_ma = pd.Series(volume).rolling(20).mean().values
    sig_vol = 1 if volume[-1] > vol_ma[-1] * 1.1 else 0
    sig_price = 1 if close[-1] > close[-2] else 0
    # 盈利因子模拟 (核心逻辑)
    rets = np.diff(close) / close[:-1]
    pos_rets = rets[rets > 0].sum()
    neg_rets = abs(rets[rets <= 0].sum())
    pf7 = round(pos_rets / neg_rets, 2) if neg_rets != 0 else 9.99
    prob7 = round((rets > 0).mean() * 100, 1)
    
    return {"symbol": symbol, "price": round(close[-1], 2), "score": sig_vol + sig_price + 2, "prob7": prob7, "pf7": pf7}

# ==================== 界面控制 ====================
st.sidebar.header("扫描范围设置")
scan_mode = st.sidebar.multiselect("选择扫描对象", ["S&P 500", "Nasdaq 100", "Russell 2000", "Core ETFs"], default=["Core ETFs"])

if st.sidebar.button("开始扫描"):
    all_targets = []
    if "S&P 500" in scan_mode: all_targets += load_tickers("S&P 500")
    if "Nasdaq 100" in scan_mode: all_targets += load_tickers("Nasdaq 100")
    if "Core ETFs" in scan_mode: all_targets += CORE_ETFS
    
    all_targets = list(set(all_targets))
    results = []
    bar = st.progress(0)
    
    for i, sym in enumerate(all_targets[:50]): # 示例限流前50只
        try:
            results.append(compute_metrics(sym))
        except: pass
        bar.progress((i+1)/50)
    
    if results:
        df = pd.DataFrame(results).sort_values("pf7", ascending=False)
        st.dataframe(df)
        
        # === 导出 TXT 功能 ===
        txt_output = "--- 极品短线扫描报告 (按 PF7 排序) ---\n"
        txt_output += f"生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        for _, row in df.iterrows():
            txt_output += f"代码: {row['symbol']:<6} | PF7: {row['pf7']:<5} | 胜率: {row['prob7']}% | 得分: {row['score']}/5\n"
        
        st.download_button(
            label="📄 导出 TXT 报告",
            data=txt_output,
            file_name=f"Market_Scan_{time.strftime('%Y%m%d')}.txt",
            mime="text/plain"
        )
