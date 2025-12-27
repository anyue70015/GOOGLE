import streamlit as st
import requests
import numpy as np
import time
import pandas as pd
from io import StringIO

# 设置页面
st.set_page_config(page_title="极品短线扫描工具-修正版", layout="wide")

st.title("🎯 全市场极品短线扫描 (修正版)")
st.markdown("筛选逻辑：**PF7 (盈利因子)** 优先排序 | **周末锁定周五数据**")

# ==================== 核心配置 ====================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
}

# 默认 ETF 列表
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
        
        # 将数据转为 DataFrame 并彻底剔除周末/节假日的空值 (NaN)
        df = pd.DataFrame({
            "close": quote["close"],
            "high": quote["high"],
            "low": quote["low"],
            "volume": quote["volume"]
        })
        df.dropna(inplace=True)
        
        if len(df) < 50: return None
        return df
    except Exception:
        return None

# ==================== 核心指标计算 ====================
def compute_metrics(symbol):
    df = fetch_clean_data(symbol)
    if df is None: return None
    
    close = df["close"].values
    volume = df["volume"].values
    
    # 1. 计算 PF7 (盈利因子)
    rets = np.diff(close) / (close[:-1] + 1e-9)
    pos_sum = rets[rets > 0].sum()
    neg_sum = abs(rets[rets <= 0].sum())
    pf7 = round(pos_sum / neg_sum, 2) if neg_sum > 0 else 9.99
    
    # 2. 计算 7日上涨概率 (胜率)
    prob7 = round((rets > 0).mean() * 100, 1)
    
    # 3. 5项技术得分 (基于最后交易日数据)
    vol_ma20 = df["volume"].rolling(20).mean().values
    
    s1 = 1 if close[-1] > close[-2] else 0 # 价格涨
    s2 = 1 if volume[-1] > vol_ma20[-1] * 1.1 else 0 # 爆量
    s3 = 1 if close[-1] > df["close"].rolling(20).mean().iloc[-1] else 0 # 站上20日线
    s4 = 1 if (close[-1] - df["low"].iloc[-1]) / (df["high"].iloc[-1] - df["low"].iloc[-1] + 1e-9) > 0.5 else 0 # 收盘位
    s5 = 1 if rets[-1] > 0 else 0 # 动能
    
    score = s1 + s2 + s3 + s4 + s5

    return {
        "symbol": symbol,
        "price": round(close[-1], 2),
        "score": score,
        "prob7": f"{prob7}%",
        "pf7": pf7
    }

# ==================== 侧边栏与交互 ====================
st.sidebar.header("扫描配置")
market_choice = st.sidebar.multiselect(
    "选择扫描对象", 
    ["Core ETFs", "S&P 500", "Nasdaq 100"], 
    default=["Core ETFs"]
)

# 加载标普500列表的辅助函数
def get_sp500_tickers():
    try:
        url = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
        df = pd.read_csv(url)
        return df['Symbol'].tolist()
    except:
        return ["AAPL", "MSFT", "AMZN", "NVDA", "WDC"]

if st.sidebar.button("开始执行扫描"):
    symbols = []
    if "Core ETFs" in market_choice: symbols += CORE_ETFS
    if "Nasdaq 100" in market_choice: symbols += ["AAPL", "MSFT", "NVDA", "WDC", "AMD", "META", "NFLX", "AVGO"]
    if "S&P 500" in market_choice: symbols += get_sp500_tickers()
    
    symbols = list(set(symbols)) # 去重
    results = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, s in enumerate(symbols):
        status_text.text(f"正在分析: {s}")
        res = compute_metrics(s)
        if res: results.append(res)
        progress_bar.progress((i + 1) / len(symbols))
    
    status_text.text("扫描完成！")
    
    if results:
        # 按 PF7 降序排列
        df_res = pd.DataFrame(results).sort_values("pf7", ascending=False)
        
        st.subheader("📊 扫描结果分析 (按回本效率 PF7 排序)")
        st.table(df_res)
        
        # --- 导出 TXT 功能 ---
        txt_content = f"极品短线扫描报告 - 生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        txt_content += "="*60 + "\n"
        txt_content += f"{'代码':<8} | {'价格':<8} | {'得分':<5} | {'胜率':<8} | {'PF7':<5}\n"
        txt_content += "-"*60 + "\n"
        for _, r in df_res.iterrows():
            txt_content += f"{r['symbol']:<8} | {r['price']:<8} | {r['score']:<5} | {r['prob7']:<8} | {r['pf7']:<5}\n"
        
        st.download_button(
            label="📄 导出 TXT 格式报告",
            data=txt_content,
            file_name=f"Report_{time.strftime('%Y%m%d')}.txt",
            mime="text/plain"
        )
    else:
        st.warning("未扫描到有效数据，请检查网络或更换对象。")
