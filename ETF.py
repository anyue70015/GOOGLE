import streamlit as st
import yfinance as yf
import numpy as np
import time
import pandas as pd

st.set_page_config(page_title="极品短线扫描 (数据精准校准版)", layout="wide")

st.title("极品短线扫描 (数据精准校准版)")

# ==================== 热门标的列表 ====================
TICKERS = [
    # 2025强势ETF
    "SLV", "GLD", "GDX", "GDXJ", "SIL", "SLVP",
    "SMH", "SOXX", "SOXL", "TQQQ", "BITO", "MSTR",
    "SPY", "QQQ", "VOO", "ARKK", "XLK", "XLV",
    # 2025强势个股
    "WDC", "APH", "MU", "AVGO", "NVDA", "AMD", "HOOD", "PM", "HCA", "ENSG", "ABBV"
]

# ==================== 数据抓取 ====================
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_data(symbol):
    try:
        df = yf.download(symbol, period="1y", interval="1d", progress=False)
        if len(df) < 50:
            return None
        df = df[['Close', 'High', 'Low', 'Volume']].dropna()
        df.rename(columns={"Close": "close", "High": "high", "Low": "low", "Volume": "volume"}, inplace=True)
        df.reset_index(drop=True, inplace=True)
        return df
    except:
        return None

# ==================== 计算指标 ====================
def compute_metrics(symbol):
    df = fetch_data(symbol)
    if df is None:
        return None
    
    close = df["close"].values
    volume = df["volume"].values
    
    # PF7
    rets = np.diff(close) / (close[:-1] + 1e-9)
    pos_sum = rets[rets > 0].sum()
    neg_sum = abs(rets[rets <= 0].sum())
    pf7 = round(pos_sum / neg_sum, 2) if neg_sum > 0 else 9.99
    
    # 日胜率
    prob7 = round((rets > 0).mean() * 100, 1)
    
    # 当前得分 (5项)
    if len(df) < 2:
        return None
    vol_ma20 = df["volume"].rolling(20).mean().iloc[-1]
    
    s1 = 1 if close[-1] > close[-2] else 0
    s2 = 1 if volume[-1] > vol_ma20 * 1.1 else 0
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

# ==================== 执行扫描 ====================
if st.button("🚀 开始扫描"):
    results = []
    progress = st.progress(0)
    
    for i, sym in enumerate(TICKERS):
        m = compute_metrics(sym)
        if m:
            results.append(m)
        progress.progress((i + 1) / len(TICKERS))
        time.sleep(0.5)  # 防限流
    
    if results:
        df_res = pd.DataFrame(results).sort_values("PF7效率", ascending=False)
        
        st.subheader(f"扫描完成 · 共 {len(df_res)} 只")
        
        # 高亮PF7
        def highlight_pf7(val):
            if val > 5:
                return 'background-color: #90EE90'
            elif val > 3:
                return 'background-color: #FFFFE0'
            else:
                return 'background-color: #FFB6C1'
        
        styled = df_res.style.map(highlight_pf7, subset=['PF7效率'])
        st.dataframe(styled, use_container_width=True)
        
        # TXT导出
        txt = f"极品短线扫描 (数据精准校准版) - {time.strftime('%Y-%m-%d')}\n"
        txt += "="*60 + "\n"
        for _, r in df_res.iterrows():
            txt += f"{r['代码']:6} | ${r['现价']:8.2f} | {r['得分']:4} | {r['胜率']:6} | PF7 {r['PF7效率']:>5}\n"
        
        st.download_button("📥 导出 TXT", txt, f"极品短线_{time.strftime('%Y%m%d')}.txt", "text/plain")
    else:
        st.error("数据获取失败，请重试")

st.caption("极品短线扫描 (数据精准校准版) · 2025年12月27日 · 仅显示扫描结果")
