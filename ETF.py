import streamlit as st
import yfinance as yf
import numpy as np
import time
import pandas as pd

# ==================== 页面配置 ====================
st.set_page_config(page_title="极品短线扫描工具", layout="wide")
st.title("🎯 全市场极品短线扫描 (2025所有热门ETF扩展版)")

# ==================== 核心配置 - 所有热门ETF列表 ====================
ALL_ETFS = [
    # 核心大盘/指数
    "SPY", "QQQ", "VOO", "IVV", "VTI", "VUG", "SCHG", "IWM", "DIA",
    # 贵金属/矿业 (2025大牛)
    "SLV", "GLD", "GDX", "GDXJ", "SIL", "SLVP", "RING", "SGDJ",
    # 半导体/AI
    "SMH", "SOXX", "SOXL", "NVDA",
    # 杠杆热门
    "TQQQ", "SOXL", "TSLL", "BITX", "TNA", "FAS", "SPXL",
    # 行业/主题
    "XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE",
    "ARKK", "ARKQ", "ARKW", "ARKG", "ARKF",
    # 债券/国际/其他
    "TLT", "BND", "VXUS", "VGK", "VEA", "VWO", "KWEB", "BITO", "MSTR",
    # 你之前关注的
    "WDC", "APH", "HOOD", "PM", "HCA", "ENSG", "ABBV", "MU", "AVGO", "AMD", "META", "NFLX", "COST"
]

# ==================== 数据抓取 ====================
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_clean_data(symbol):
    try:
        df = yf.download(symbol, period="1y", interval="1d", progress=False)
        if len(df) < 50:
            return None
        df = df[['Close', 'High', 'Low', 'Volume']].dropna()
        df.rename(columns={"Close": "close", "High": "high", "Low": "low", "Volume": "volume"}, inplace=True)
        df.reset_index(drop=True, inplace=True)
        return df
    except Exception:
        return None

# ==================== 核心指标计算 ====================
def compute_stock_metrics(symbol):
    df = fetch_clean_data(symbol)
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
    
    # 5项得分
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

# ==================== 界面逻辑 ====================
st.sidebar.header("扫描设置")
if st.sidebar.button("🚀 开始执行全量ETF扫描 (约100+只)"):
    symbols = list(set(ALL_ETFS))  # 去重
    results = []
    progress = st.progress(0)
    
    for i, s in enumerate(symbols):
        m = compute_stock_metrics(s)
        if m:
            results.append(m)
        progress.progress((i + 1) / len(symbols))
        time.sleep(1)  # 防限流
    
    if results:
        df_res = pd.DataFrame(results).sort_values("PF7效率", ascending=False)
        
        st.subheader(f"📊 所有热门ETF扫描结果 (共 {len(df_res)} 只，按 PF7 排序)")
        
        # 安全手动高亮
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
        txt_content = f"极品短线扫描报告 - 所有热门ETF - {time.strftime('%Y-%m-%d')}\n"
        txt_content += "="*70 + "\n"
        for _, r in df_res.iterrows():
            txt_content += f"{r['代码']:6} | 现价 ${r['现价']:8.2f} | 得分 {r['得分']:4} | 胜率 {r['胜率']:6} | PF7 {r['PF7效率']:>6}\n"
        
        st.download_button(
            "📥 导出 TXT 报告",
            txt_content,
            f"所有ETF短线扫描报告_{time.strftime('%Y%m%d')}.txt",
            mime="text/plain"
        )
    else:
        st.error("数据抓取失败，请稍后重试")

st.caption("2025年12月27日所有热门ETF扩展版 | SLV/GDXJ/WDC/SMH等2025牛ETF霸榜 | 回本+吃肉神器！🚀")
