import streamlit as st
import requests
import numpy as np
import time
import pandas as pd
from io import StringIO, BytesIO

st.set_page_config(page_title="标普500 + 纳斯达克100 极品短线扫描工具", layout="wide")
st.title("标普500 + 纳斯达克100 极品短线扫描工具（7日≥68% + PF7≥3.5）")

# ==================== 核心常量 ====================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
}

BACKTEST_CONFIG = {
    "3个月": {"range": "3mo", "interval": "1d"},
    "6个月": {"range": "6mo", "interval": "1d"},
    "1年":  {"range": "1y",  "interval": "1d"},
    "2年":  {"range": "2y",  "interval": "1d"},
    "3年":  {"range": "3y",  "interval": "1d"},
    "5年":  {"range": "5y",  "interval": "1d"},
    "10年": {"range": "10y", "interval": "1d"},
}

# ==================== 数据拉取 ====================
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
        close, high, low, volume = close[mask], high[mask], low[mask], volume[mask]
        if len(close) < 100:
            raise ValueError("数据不足")
        return close, high, low, volume
    except Exception as e:
        raise ValueError(f"请求失败: {str(e)}")

# ==================== 指标函数 ====================
def ema_np(x: np.ndarray, span: int) -> np.ndarray:
    alpha = 2 / (span + 1)
    ema = np.empty_like(x)
    ema[0] = x[0]
    for i in range(1, len(x)):
        ema[i] = alpha * x[i] + (1 - alpha) * ema[i-1]
    return ema

def macd_hist_np(close: np.ndarray) -> np.ndarray:
    ema12 = ema_np(close, 12)
    ema26 = ema_np(close, 26)
    macd_line = ema12 - ema26
    signal = ema_np(macd_line, 9)
    return macd_line - signal

def rsi_np(close: np.ndarray, period: int = 14) -> np.ndarray:
    delta = np.diff(close, prepend=close[0])
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    alpha = 1 / period
    gain_ema = np.empty_like(gain)
    loss_ema = np.empty_like(loss)
    gain_ema[0] = gain[0]
    loss_ema[0] = loss[0]
    for i in range(1, len(gain)):
        gain_ema[i] = alpha * gain[i] + (1 - alpha) * gain_ema[i-1]
        loss_ema[i] = alpha * loss[i] + (1 - alpha) * loss_ema[i-1]
    rs = gain_ema / (loss_ema + 1e-9)
    return 100 - (100 / (1 + rs))

def atr_np(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    prev_close = np.roll(close, 1)
    prev_close[0] = close[0]
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))
    atr = np.empty_like(tr)
    atr[0] = tr[0]
    alpha = 1 / period
    for i in range(1, len(tr)):
        atr[i] = alpha * tr[i] + (1 - alpha) * atr[i-1]
    return atr

def rolling_mean_np(x: np.ndarray, window: int) -> np.ndarray:
    if len(x) < window:
        return np.full_like(x, np.nanmean(x) if not np.isnan(x).all() else 0)
    cumsum = np.cumsum(np.insert(x, 0, 0.0))
    ma = (cumsum[window:] - cumsum[:-window]) / window
    return np.concatenate([np.full(window-1, ma[0]), ma])

def obv_np(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
    direction = np.sign(np.diff(close, prepend=close[0]))
    return np.cumsum(direction * volume)

def backtest_with_stats(close: np.ndarray, score: np.ndarray, steps: int):
    if len(close) <= steps + 1:
        return 0.5, 0.0, 0.0, 0.0
    idx = np.where(score[:-steps] >= 3)[0]
    if len(idx) == 0:
        return 0.5, 0.0, 0.0, 0.0
    rets = close[idx + steps] / close[idx] - 1
    win_rate = (rets > 0).mean()
    pf = rets[rets > 0].sum() / abs(rets[rets <= 0].sum()) if (rets <= 0).any() else 999
    avg_win = rets[rets > 0].mean() if (rets > 0).any() else 0
    avg_loss = rets[rets <= 0].mean() if (rets <= 0).any() else 0
    return win_rate, pf, avg_win, avg_loss

# ==================== 核心计算 ====================
@st.cache_data(show_spinner=False)
def compute_stock_metrics(symbol: str, cfg_key: str = "1年"):
    yahoo_symbol = symbol.upper()
    close, high, low, volume = fetch_yahoo_ohlcv(yahoo_symbol, BACKTEST_CONFIG[cfg_key]["range"])

    macd_hist = macd_hist_np(close)
    rsi = rsi_np(close)
    atr = atr_np(high, low, close)
    obv = obv_np(close, volume)
    vol_ma20 = rolling_mean_np(volume, 20)
    atr_ma20 = rolling_mean_np(atr, 20)
    obv_ma20 = rolling_mean_np(obv, 20)

    sig_macd = (macd_hist > 0).astype(int)[-1]
    sig_vol = (volume[-1] > vol_ma20[-1] * 1.1).astype(int)
    sig_rsi = (rsi[-1] >= 60).astype(int)
    sig_atr = (atr[-1] > atr_ma20[-1] * 1.1).astype(int)
    sig_obv = (obv[-1] > obv_ma20[-1] * 1.05).astype(int)
    score = sig_macd + sig_vol + sig_rsi + sig_atr + sig_obv

    sig_macd_hist = (macd_hist > 0).astype(int)
    sig_vol_hist = (volume > vol_ma20 * 1.1).astype(int)
    sig_rsi_hist = (rsi >= 60).astype(int)
    sig_atr_hist = (atr > atr_ma20 * 1.1).astype(int)
    sig_obv_hist = (obv > obv_ma20 * 1.05).astype(int)
    score_arr = sig_macd_hist + sig_vol_hist + sig_rsi_hist + sig_atr_hist + sig_obv_hist

    prob7, pf7, avg_win7, avg_loss7 = backtest_with_stats(close[:-1], score_arr[:-1], 7)
    prob30, pf30, avg_win30, avg_loss30 = backtest_with_stats(close[:-1], score_arr[:-1], 30)

    price = close[-1]
    change = (close[-1] / close[-2] - 1) * 100 if len(close) >= 2 else 0

    signals_detail = []
    if sig_macd: signals_detail.append("MACD柱>0")
    if sig_vol: signals_detail.append("放量>1.1x MA20")
    if sig_rsi: signals_detail.append("RSI≥60")
    if sig_atr: signals_detail.append("ATR放量>1.1x")
    if sig_obv: signals_detail.append("OBV>1.05x MA20")

    return {
        "symbol": symbol.upper(),
        "price": price,
        "change": change,
        "score": score,
        "signals": " | ".join(signals_detail) if signals_detail else "无",
        "prob7": prob7,
        "pf7": pf7,
        "prob30": prob30,
        "pf30": pf30,
    }

# ==================== 加载成分股（固定顺序） ====================
@st.cache_data(ttl=86400)
def load_sp500_tickers():
    url = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
    resp = requests.get(url, headers=HEADERS)
    resp.raise_for_status()
    df = pd.read_csv(StringIO(resp.text))
    return df['Symbol'].tolist()

# 2025年12月22日重组后最新 Nasdaq-100 列表
ndx100 = [
    "ADBE","AMD","ABNB","ALNY","GOOGL","GOOG","AMZN","AEP","AMGN","ADI",
    "AAPL","AMAT","APP","ARM","ASML","AZN","TEAM","ADSK","ADP","AXON",
    "BKR","BKNG","AVGO","CDNS","CHTR","CTAS","CSCO","CCEP","CTSH","CMCSA",
    "CEG","CPRT","CSGP","COST","CRWD","CSX","DDOG","DXCM","FANG","DASH",
    "EA","EXC","FAST","FER","FTNT","GEHC","GILD","HON","IDXX","INSM",
    "INTC","INTU","ISRG","KDP","KLAC","KHC","LRCX","LIN","MAR","MRVL",
    "MELI","META","MCHP","MU","MSFT","MSTR","MDLZ","MPWR","MNST","NFLX",
    "NVDA","NXPI","ORLY","ODFL","PCAR","PLTR","PANW","PAYX","PYPL","PDD",
    "PEP","QCOM","REGN","ROP","ROST","STX","SHOP","SBUX","SNPS","TMUS",
    "TTWO","TSLA","TXN","TRI","VRSK","VRTX","WBD","WDC","WDAY","XEL","ZS"
]

sp500 = load_sp500_tickers()
all_tickers = list(set(sp500 + ndx100))
all_tickers.sort()  # 固定字母顺序

st.write(f"总计 {len(all_tickers)} 只股票（固定字母顺序） | Nasdaq-100 已更新至2025年12月最新")

mode = st.selectbox("回测周期", list(BACKTEST_CONFIG.keys()), index=2)
sort_by = st.selectbox("结果排序方式", ["PF7 (盈利因子)", "7日概率", "PF30", "30日概率"], index=0)

# ==================== session_state ====================
if 'high_prob' not in st.session_state:
    st.session_state.high_prob = []
if 'scanned_symbols' not in st.session_state:
    st.session_state.scanned_symbols = set()
if 'failed_count' not in st.session_state:
    st.session_state.failed_count = 0

result_container = st.container()
progress_bar = st.progress(len(st.session_state.scanned_symbols) / len(all_tickers))
status_text = st.empty()

# ==================== 结果筛选与显示 + 导出 ====================
if st.session_state.high_prob:
    df_all = pd.DataFrame(st.session_state.high_prob)
    
    # 严格筛选：7日概率 ≥ 68% 且 PF7 ≥ 3.5
    filtered_df = df_all[(df_all['prob7'] >= 0.68) & (df_all['pf7'] >= 3.5)].copy()
    
    if filtered_df.empty:
        st.warning("当前扫描中暂无同时满足 7日概率≥68% 且 PF7≥3.5 的极品短线股票，继续扫描中...")
    else:
        df_display = filtered_df.copy()
        df_display['price'] = df_display['price'].round(2)
        df_display['change'] = df_display['change'].apply(lambda x: f"{x:+.2f}%")
        df_display['prob7'] = (df_display['prob7'] * 100).round(1).map("{:.1f}%".format)
        df_display['pf7'] = df_display['pf7'].round(2)
        df_display['prob30'] = (df_display['prob30'] * 100).round(1).map("{:.1f}%".format)
        df_display['pf30'] = df_display['pf30'].round(2)
        
        # 排序
        if sort_by == "PF7 (盈利因子)":
            df_display = df_display.sort_values("pf7", ascending=False)
        elif sort_by == "PF30":
            df_display = df_display.sort_values("pf30", ascending=False)
        elif sort_by == "30日概率":
            df_display = df_display.sort_values("prob30", ascending=False)
        else:
            df_display = df_display.sort_values("prob7", ascending=False)
        
        # 页面显示
        with result_container:
            st.subheader(f"🎯 极品短线股票（7日概率≥68% 且 PF7≥3.5） 共 {len(df_display)} 只  |  排序：{sort_by}")
            for _, row in df_display.iterrows():
                st.markdown(
                    f"**{row['symbol']}** - 价格: ${row['price']:.2f} ({row['change']}) - "
                    f"得分: {row['score']}/5 ({row['signals']}) - "
                    f"**7日: {row['prob7']} (PF7: {row['pf7']})** - "
                    f"30日: {row['prob30']} (PF30: {row['pf30']})"
                )
        
        # 导出 CSV
        csv_data = df_display.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📄 导出极品股票为 CSV（已美化）",
            data=csv_data,
            file_name=f"极品短线股票_7日≥68%_PF≥3.5_{time.strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
        
        # 导出 TXT
        txt_lines = []
        txt_lines.append(f"极品短线股票扫描结果（严格筛选）")
        txt_lines.append(f"扫描时间：{time.strftime('%Y-%m-%d %H:%M')}")
        txt_lines.append(f"筛选条件：7日上涨概率 ≥ 68%  且  PF7 ≥ 3.5")
        txt_lines.append(f"回测周期：{mode}  |  排序：{sort_by}")
        txt_lines.append(f"符合股票数量：{len(df_display)} 只")
        txt_lines.append("=" * 80)
        txt_lines.append("")
        
        for _, row in df_display.iterrows():
            txt_lines.append(
                f"{row['symbol']:6} | 价格 ${row['price']:8.2f}  {row['change']:>8} | "
                f"得分 {row['score']}/5  {row['signals']:35} | "
                f"7日 {row['prob7']:>6}  PF7 {row['pf7']:>5} | "
                f"30日 {row['prob30']:>6}  PF30 {row['pf30']:>5}"
            )
        
        txt_content = "\n".join(txt_lines)
        
        st.download_button(
            label="📜 导出极品股票为 TXT（超级易读，推荐）",
            data=txt_content.encode('utf-8'),
            file_name=f"极品短线股票_7日≥68%_PF≥3.5_{time.strftime('%Y%m%d')}.txt",
            mime="text/plain"
        )
        
        with st.expander("🔍 TXT 导出内容预览"):
            st.text(txt_content)

st.info(f"已扫描: {len(st.session_state.scanned_symbols)}/{len(all_tickers)} | 失败: {st.session_state.failed_count} | 极品股票: {len([x for x in st.session_state.high_prob if x['prob7']>=0.68 and x['pf7']>=3.5])}")

# ==================== 自动扫描 ====================
with st.spinner("自动扫描中（保持页面打开）..."):
    for sym in all_tickers:
        if sym in st.session_state.scanned_symbols:
            continue
        status_text.text(f"正在计算 {sym} ({len(st.session_state.scanned_symbols)+1}/{len(all_tickers)})")
        progress_bar.progress((len(st.session_state.scanned_symbols) + 1) / len(all_tickers))
        try:
            metrics = compute_stock_metrics(sym, mode)
            st.session_state.scanned_symbols.add(sym)
            st.session_state.high_prob.append(metrics)  # 全部存下来，用于严格筛选
            st.rerun()
        except Exception as e:
            st.session_state.failed_count += 1
            st.warning(f"{sym} 失败: {str(e)}")
            st.session_state.scanned_symbols.add(sym)
        time.sleep(8)

st.success("所有股票扫描完成！极品结果已更新")

if st.button("🔄 重置所有进度（从头开始）"):
    st.session_state.high_prob = []
    st.session_state.scanned_symbols = set()
    st.session_state.failed_count = 0
    st.rerun()

st.caption("2025最新版 | 只看极品短线信号 | 双格式导出 | 实时更新 | 专注3-7日爆发机会")
