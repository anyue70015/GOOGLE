import streamlit as st
import requests
import numpy as np
import time
import pandas as pd

st.set_page_config(page_title="回本利器-数据校准版", layout="wide")
st.title("🎯 极品短线扫描 (数据精准校准版)")

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"}

CORE_ETFS = ["SLV", "GLD", "GDX", "SOXX", "SMH", "SPY", "QQQ", "IWM", "BITO", "WDC", "NVDA", "AAPL"]

@st.cache_data(ttl=3600)
def fetch_clean_data(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1y&interval=1d"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        data = resp.json()["chart"]["result"][0]
        quote = data["indicators"]["quote"][0]
        df = pd.DataFrame({"close": quote["close"], "vol": quote["volume"]}).dropna()
        # 确保只取有价格波动的行，过滤掉成交量为0的僵尸交易日（周末残留）
        df = df[df['vol'] > 0]
        return df
    except:
        return None

def compute_metrics(symbol):
    df = fetch_clean_data(symbol)
    if df is None or len(df) < 50: return None
    
    close = df["close"].values
    
    # --- 修正逻辑开始 ---
    # 计算每日百分比收益率
    rets = np.diff(close) / close[:-1]
    
    # 只统计显著波动的日子，避免微小震荡摊薄 PF
    # 如果某天涨跌幅几乎为 0 (小于 0.01%)，不计入 PF 分母，防止数值被恶意摊薄
    pos_rets = rets[rets > 0.0001]
    neg_rets = rets[rets < -0.0001]
    
    pf7 = round(pos_rets.sum() / (abs(neg_rets.sum()) + 1e-9), 2)
    prob7 = round((len(pos_rets) / len(rets)) * 100, 1)
    # --- 修正逻辑结束 ---
    
    # 得分逻辑保持不变
    s1 = 1 if close[-1] > close[-2] else 0
    s2 = 1 if df['vol'].values[-1] > df['vol'].rolling(20).mean().values[-1] * 1.1 else 0
    s3 = 1 if close[-1] > df['close'].rolling(20).mean().values[-1] else 0
    score = s1 + s2 + s3 + 2
    
    return {"代码": symbol, "现价": round(close[-1], 2), "得分": f"{score}/5", "胜率": f"{prob7}%", "PF7效率": pf7}

if st.sidebar.button("👉 重新校准扫描"):
    results = []
    for s in CORE_ETFS:
        m = compute_metrics(s)
        if m: results.append(m)
    
    if results:
        df_res = pd.DataFrame(results).sort_values("PF7效率", ascending=False)
        st.table(df_res) # 使用 Table 最稳
        
        # TXT 报告
        txt = "--- 校准后报告 ---\n"
        for _, r in df_res.iterrows():
            txt += f"{r['代码']}: PF7={r['PF7效率']} | 胜率={r['胜率']}\n"
        st.download_button("下载报告", txt, "fix_report.txt")
