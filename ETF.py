import streamlit as st
import yfinance as yf
import numpy as np
import time
import pandas as pd

st.set_page_config(page_title="极品短线扫描 (数据精准校准版)", layout="wide")
st.title("极品短线扫描 (数据精准校准版)")

TICKERS = [
    "SLV", "GLD", "GDX", "GDXJ", "SIL", "SLVP",
    "SMH", "SOXX", "SOXL", "TQQQ", "BITO", "MSTR",
    "SPY", "QQQ", "VOO", "ARKK", "XLK", "XLV",
    "WDC", "APH", "MU", "AVGO", "NVDA", "AMD", "HOOD", "PM", "HCA", "ENSG", "ABBV"
]

@st.cache_data(ttl=1800, show_spinner=False)  # 缩短缓存，假期数据变动小
def fetch_data(symbol):
    try:
        df = yf.download(symbol, period="1y", interval="1d", progress=False, threads=False)
        if df.empty or len(df) < 50:
            return None
        df = df[['Close', 'High', 'Low', 'Volume']].dropna()
        if df.empty:
            return None
        df.rename(columns={"Close": "close", "High": "high", "Low": "low", "Volume": "volume"}, inplace=True)
        df.reset_index(drop=True, inplace=True)
        return df
    except Exception as e:
        st.warning(f"{symbol} 数据获取失败: {str(e)}")
        return None

def compute_metrics(symbol):
    df = fetch_data(symbol)
    if df is None or len(df) < 20:
        return None
    
    close = df["close"].values
    volume = df["volume"].values
    
    rets = np.diff(close) / (close[:-1] + 1e-9)
    pos_sum = rets[rets > 0].sum()
    neg_sum = abs(rets[rets <= 0].sum())
    pf7 = round(pos_sum / neg_sum, 2) if neg_sum > 0 else 9.99
    
    prob7 = round((rets > 0).mean() * 100, 1)
    
    if len(df) < 2:
        return None
    vol_ma20 = df["volume"].rolling(20).mean().iloc[-1] if len(df) >= 20 else volume.mean()
    
    s1 = 1 if close[-1] > close[-2] else 0
    s2 = 1 if volume[-1] > vol_ma20 * 1.1 else 0
    s3 = 1 if close[-1] > df["close"].rolling(20).mean().iloc[-1] if len(df) >= 20 else close[-1] > close.mean() else 0
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

if st.button("🚀 开始扫描"):
    results = []
    success_count = 0
    progress = st.progress(0)
    status = st.empty()
    
    for i, sym in enumerate(TICKERS):
        status.text(f"正在扫描 {sym} ... ({i+1}/{len(TICKERS)})")
        m = compute_metrics(sym)
        if m:
            results.append(m)
            success_count += 1
        progress.progress((i + 1) / len(TICKERS))
        time.sleep(1.5)  # 加长延时，防限流
    
    status.text(f"扫描完成！成功 {success_count}/{len(TICKERS)} 只")
    
    if results:
        df_res = pd.DataFrame(results).sort_values("PF7效率", ascending=False)
        
        st.subheader(f"扫描结果 · 共 {len(df_res)} 只")
        
        def highlight_pf7(val):
            if val > 5:
                return 'background-color: #90EE90'
            elif val > 3:
                return 'background-color: #FFFFE0'
            else:
                return 'background-color: #FFB6C1'
        
        styled = df_res.style.map(highlight_pf7, subset=['PF7效率'])
        st.dataframe(styled, use_container_width=True)
        
        txt = f"极品短线扫描 (数据精准校准版) - {time.strftime('%Y-%m-%d')}\n"
        txt += "="*60 + "\n"
        for _, r in df_res.iterrows():
            txt += f"{r['代码']:6} | ${r['现价']:8.2f} | {r['得分']:4} | {r['胜率']:6} | PF7 {r['PF7效率']:>5}\n"
        
        st.download_button("📥 导出 TXT", txt, f"极品短线_{time.strftime('%Y%m%d')}.txt", "text/plain")
    else:
        st.error("所有标的获取失败，请检查网络或稍后重试（假期Yahoo可能限流）")

st.caption("极品短线扫描 (数据精准校准版) · 2025年12月27日")
