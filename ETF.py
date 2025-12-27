import streamlit as st
import requests
import numpy as np
import time
import pandas as pd
from io import StringIO

# ==================== 页面配置 ====================
st.set_page_config(page_title="全球核心 ETF 极品短线扫描", layout="wide")
st.title("🎯 全球核心 ETF 短线扫描工具")
st.markdown("筛选标准：**PF7 ≥ 3.6** (历史极稳) 或 **7日胜率 ≥ 68%** (高概率上涨)")

# ==================== 核心常量与配置 ====================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
}

# 核心 ETF 列表：覆盖美股大盘、行业板块、贵金属、债市、中概股
CORE_ETFS = [
    "SPY", "QQQ", "IWM", "DIA",          # 美股四大指数
    "SLV", "GLD", "GDX", "TLT",          # 白银、黄金、金矿、美债
    "SOXX", "SMH", "XLK",                # 半导体与科技
    "XBI", "IBB", "XLV",                # 生物医药与医疗
    "XLE", "XOP", "XLF", "KRE",          # 能源与金融
    "XLU", "XLI", "XLB", "XLP", "XLY",   # 公用事业、工业、材料、必选消费、可选消费
    "KWEB", "FXI", "ASHR",               # 中概股与中国A股
    "BITO", "ARKK", "TSLL"               # 比特币期货、木头姐、特斯拉杠杆
]

BACKTEST_CONFIG = {
    "1年":  {"range": "1y",  "interval": "1d"},
    "2年":  {"range": "2y",  "interval": "1d"},
    "3年":  {"range": "3y",  "interval": "1d"},
    "5年":  {"range": "5y",  "interval": "1d"},
}

# ==================== 工具函数 ====================
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_yahoo_ohlcv(yahoo_symbol: str, range_str: str, interval: str = "1d"):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}?range={range_str}&interval={interval}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json()["chart"]["result"][0]
        quote = data["indicators"]["quote"][0]
        close = np.array(quote["close"], dtype=float)
        high = np.array(quote["high"], dtype=float)
        low = np.array(quote["low"], dtype=float)
        volume = np.array(quote["volume"], dtype=float)
        mask = ~np.isnan(close)
        return close[mask], high[mask], low[mask], volume[mask]
    except Exception as e:
        raise ValueError(f"请求失败: {str(e)}")

def ema_np(x, span):
    alpha = 2 / (span + 1)
    ema = np.empty_like(x)
    ema[0] = x[0]
    for i in range(1, len(x)):
        ema[i] = alpha * x[i] + (1 - alpha) * ema[i-1]
    return ema

def rsi_np(close, period=14):
    delta = np.diff(close, prepend=close[0])
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    alpha = 1 / period
    gain_ema = np.empty_like(gain)
    loss_ema = np.empty_like(loss)
    gain_ema[0], loss_ema[0] = gain[0], loss[0]
    for i in range(1, len(gain)):
        gain_ema[i] = alpha * gain[i] + (1 - alpha) * gain_ema[i-1]
        loss_ema[i] = alpha * loss[i] + (1 - alpha) * loss_ema[i-1]
    rs = gain_ema / (loss_ema + 1e-9)
    return 100 - (100 / (1 + rs))

def backtest_with_stats(close, score, steps):
    if len(close) <= steps + 1: return 0.5, 0.0
    idx = np.where(score[:-steps] >= 3)[0]
    if len(idx) == 0: return 0.5, 0.0
    rets = close[idx + steps] / close[idx] - 1
    win_rate = (rets > 0).mean()
    pf = rets[rets > 0].sum() / abs(rets[rets <= 0].sum()) if (rets <= 0).any() else 9.99
    return win_rate, pf

# ==================== 核心逻辑 ====================
def compute_metrics(symbol, cfg_key):
    close, high, low, volume = fetch_yahoo_ohlcv(symbol, BACKTEST_CONFIG[cfg_key]["range"])
    
    # 指标计算
    macd_h = ema_np(close, 12) - ema_np(close, 26)
    macd_sig = ema_np(macd_h, 9)
    hist = macd_h - macd_sig
    rsi = rsi_np(close)
    
    # 辅助均线
    vol_ma20 = pd.Series(volume).rolling(20).mean().values
    
    # 5项得分逻辑 (当日)
    sig_macd = (hist[-1] > 0)
    sig_vol = (volume[-1] > vol_ma20[-1] * 1.1)
    sig_rsi = (rsi[-1] >= 60)
    sig_price = (close[-1] > close[-2])
    sig_trend = (close[-1] > ema_np(close, 20)[-1])
    score = int(sig_macd) + int(sig_vol) + int(sig_rsi) + int(sig_price) + int(sig_trend)

    # 历史得分数组用于回测
    hist_macd = (hist > 0).astype(int)
    hist_vol = (volume > pd.Series(volume).rolling(20).mean().fillna(method='bfill').values * 1.1).astype(int)
    hist_rsi = (rsi >= 60).astype(int)
    hist_score = hist_macd + hist_vol + hist_rsi + 1 # 简化历史回测得分

    prob7, pf7 = backtest_with_stats(close[:-1], hist_score[:-1], 7)
    
    return {
        "symbol": symbol,
        "price": close[-1],
        "change": (close[-1]/close[-2]-1)*100,
        "score": score,
        "prob7": prob7,
        "pf7": pf7
    }

# ==================== Streamlit UI ====================
mode = st.sidebar.selectbox("回测周期", list(BACKTEST_CONFIG.keys()), index=0)
target_tickers = st.sidebar.multiselect("自定义扫描对象", CORE_ETFS, default=CORE_ETFS)

if st.sidebar.button("开始扫描 ETF"):
    results = []
    progress = st.progress(0)
    for i, sym in enumerate(target_tickers):
        try:
            res = compute_metrics(sym, mode)
            results.append(res)
            st.write(f"✅ {sym} 扫描完成")
        except:
            st.write(f"❌ {sym} 数据获取失败")
        progress.progress((i + 1) / len(target_tickers))
    
    if results:
        df = pd.DataFrame(results)
        # 核心过滤逻辑
        df = df[(df['pf7'] >= 3.6) | (df['prob7'] >= 0.68)]
        df = df.sort_values("pf7", ascending=False)
        
        st.subheader("📊 扫描结果 (PF7 ≥ 3.6 或 7日概率 ≥ 68%)")
        st.dataframe(df.style.format({
            "price": "{:.2f}",
            "change": "{:+.2f}%",
            "prob7": "{:.1%}",
            "pf7": "{:.2f}"
        }))
        
        # 详细列表展示
        for _, row in df.iterrows():
            color = "green" if row['score'] >= 3 else "white"
            st.markdown(f"### :{color}[{row['symbol']}]")
            st.write(f"价格: **${row['price']:.2f}** | 涨跌: **{row['change']:+.2f}%** | 得分: **{row['score']}/5**")
            st.write(f"7日上涨概率: **{row['prob7']:.1%}** | **PF7(盈利因子): {row['pf7']:.2f}**")
            st.divider()
    else:
        st.warning("未发现符合条件的优质 ETF，建议调整回测周期或手动检查关注列表。")

st.info("提示：ETF 的 PF7 通常比个股低，若扫描结果过少，可尝试将回测周期调至'2年'。")