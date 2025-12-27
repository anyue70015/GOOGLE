import streamlit as st
import requests
import numpy as np
import time
import pandas as pd
from io import StringIO

# 设置页面
st.set_page_config(page_title="极品短线扫描-周末修正版", layout="wide")

# 检查依赖并提示（针对新手的友好提醒）
try:
    import requests
    import pandas as pd
except ImportError:
    st.error("缺少必要组件！请运行: pip install requests pandas")

st.title("🎯 全市场极品短线扫描 (周末修正版)")

# ==================== 核心配置 ====================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
}

CORE_ETFS = ["SPY", "QQQ", "IWM", "DIA", "SLV", "GLD", "GDX", "TLT", "SOXX", "SMH", "KWEB", "BITO"]

# ==================== 数据清洗逻辑 ====================
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_clean_data(symbol):
    # 使用 1y 周期获取日线数据
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1y&interval=1d"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()["chart"]["result"][0]
        quote = data["indicators"]["quote"][0]
        
        # 核心：将数据转为 DataFrame 并剔除空值（解决周末漂移）
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
    except Exception as e:
        return None

def compute_metrics(symbol):
    df = fetch_clean_data(symbol)
    if df is None: return None
    
    close = df["close"].values
    volume = df["volume"].values
    
    # 1. 计算 PF7 (盈利因子)
    rets = np.diff(close) / close[:-1]
    pos_sum = rets[rets > 0].sum()
    neg_sum = abs(rets[rets <= 0].sum())
    pf7 = round(pos_sum / neg_sum, 2) if neg_sum > 0 else 9.99
    
    # 2. 计算 7日胜率
    prob7 = round((rets > 0).mean() * 100, 1)
    
    # 3. 得分逻辑 (锁定周五收盘数据)
    vol_ma20 = df["volume"].rolling(20).mean().values
    
    s1 = 1 if close[-1] > close[-2] else 0
    s2 = 1 if volume[-1] > vol_ma20[-1] * 1.1 else 0
    s3 = 1 if close[-1] > df["close"].rolling(20).mean().iloc[-1] else 0
    s4 = 1 if (close[-1] - df["low"].iloc[-1]) / (df["high"].iloc[-1] - df["low"].iloc[-1] + 1e-9) > 0.5 else 0
    s5 = 1 if rets[-1] > 0 else 0
    
    score = s1 + s2 + s3 + s4 + s5

    return {
        "symbol": symbol,
        "price": round(close[-1], 2),
        "score": score,
        "prob7": f"{prob7}%",
        "pf7": pf7
    }

# ==================== 侧边栏与执行 ====================
st.sidebar.header("扫描配置")
market_choice = st.sidebar.multiselect("扫描范围", ["Core ETFs", "Nasdaq 100"], default=["Core ETFs"])

if st.sidebar.button("开始执行"):
    symbols = []
    if "Core ETFs" in market_choice: symbols += CORE_ETFS
    if "Nasdaq 100" in market_choice: symbols += ["AAPL", "MSFT", "NVDA", "WDC", "AMD", "META"]
    
    symbols = list(set(symbols))
    results = []
    
    with st.spinner("正在抓取并清洗周五收盘数据..."):
        for s in symbols:
            res = compute_metrics(s)
            if res: results.append(res)
    
    if results:
        df_res = pd.DataFrame(results).sort_values("pf7", ascending=False)
        st.subheader("📊 扫描结果 (按回本效率 PF7 排序)")
        st.table(df_res) # 使用 table 显示更简洁
        
        # 导出 TXT
        output = "--- 扫描报告 ---\n"
        for _, r in df_res.iterrows():
            output += f"{r['symbol']}: PF7={r['pf7']}, Score={r['score']}\n"
        st.download_button("下载 TXT 报告", output, "report.txt")
    else:
        st.warning("暂无数据，请检查网络连接。")
