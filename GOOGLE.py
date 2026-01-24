import streamlit as st
import yfinance as yf
import numpy as np
import time
import pandas as pd
import random
import os
import json

st.set_page_config(page_title="我的股票 短线扫描工具", layout="wide")
st.title("我的股票 短线扫描工具")

# ── 持久化进度文件 ──
progress_file = "scan_progress_my_stocks.json"

# 只加载一次进度
if 'progress_loaded' not in st.session_state:
    st.session_state.progress_loaded = True
    if os.path.exists(progress_file):
        try:
            with open(progress_file, "r") as f:
                data = json.load(f)
            st.session_state.high_prob = data.get("high_prob", [])
            st.session_state.scanned_symbols = set(data.get("scanned_symbols", []))
            st.session_state.failed_count = data.get("failed_count", 0)
            st.session_state.fully_scanned = data.get("fully_scanned", False)
            st.success("检测到历史进度，已自动加载（可继续扫描）")
        except Exception as e:
            st.warning(f"加载进度失败: {e}，将从头开始")

def save_progress():
    data = {
        "high_prob": st.session_state.high_prob,
        "scanned_symbols": list(st.session_state.scanned_symbols),
        "failed_count": st.session_state.failed_count,
        "fully_scanned": st.session_state.fully_scanned
    }
    try:
        with open(progress_file, "w") as f:
            json.dump(data, f)
    except:
        pass

# ── 清缓存 + 重置按钮 ──
if st.button("🔄 强制刷新所有数据（清缓存 + 重新扫描）"):
    st.cache_data.clear()
    st.session_state.high_prob = []
    st.session_state.scanned_symbols = set()
    st.session_state.failed_count = 0
    st.session_state.fully_scanned = False
    st.session_state.scanning = False
    if os.path.exists(progress_file):
        os.remove(progress_file)
    st.rerun()

if st.button("🔄 重置所有进度（从头开始）"):
    st.session_state.high_prob = []
    st.session_state.scanned_symbols = set()
    st.session_state.failed_count = 0
    st.session_state.fully_scanned = False
    st.session_state.scanning = False
    if os.path.exists(progress_file):
        os.remove(progress_file)
    st.rerun()

st.write("上传包含股票代码的txt文件（代码之间用空格或换行分隔）")

uploaded_file = st.file_uploader("选择股票列表文件 (.txt)", type=["txt"])

if uploaded_file is not None:
    try:
        content = uploaded_file.read().decode("utf-8")
        # 支持空格、换行、逗号等多种分隔
        raw = content.replace("\n", " ").replace(",", " ").strip()
        tickers_to_scan = [t.strip().upper() for t in raw.split() if t.strip()]
        tickers_to_scan = list(dict.fromkeys(tickers_to_scan))  # 去重
        st.success(f"成功读取 {len(tickers_to_scan)} 只股票")
        st.write("股票列表预览：", ", ".join(tickers_to_scan[:15]) + " ..." if len(tickers_to_scan)>15 else ", ".join(tickers_to_scan))
    except:
        st.error("文件读取失败，请确保是纯文本txt格式")
        tickers_to_scan = []
else:
    st.info("请先上传股票列表txt文件")
    tickers_to_scan = []
    # 可选：保留一个默认小列表用于测试
    # tickers_to_scan = ["NVDA", "TSM", "LLY"]

# 如果没有上传，则不执行后续扫描逻辑
if not tickers_to_scan:
    st.stop()

st.write("点击「开始/继续扫描」后会自动持续运行。所有股票都会强制显示（即使数据拉取失败或无信号，也会显示 N/A / 0 分）。")

# ==================== 核心常量 ====================
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
@st.cache_data(ttl=300, show_spinner=False)  # 缩短TTL以避免数据滞后
def fetch_yahoo_ohlcv(yahoo_symbol: str, range_str: str, interval: str = "1d"):
    try:
        time.sleep(random.uniform(1.2, 2.8))  # 防限流
        ticker = yf.Ticker(yahoo_symbol)
        df = ticker.history(period=range_str, interval=interval, auto_adjust=True, prepost=False, timeout=30)
        if df.empty or len(df) < 50:
            return None, None, None, None
        close = df['Close'].values.astype(float)
        high = df['High'].values.astype(float)
        low = df['Low'].values.astype(float)
        volume = df['Volume'].values.astype(float)
        mask = ~np.isnan(close)
        close, high, low, volume = close[mask], high[mask], low[mask], volume[mask]
        if len(close) < 50:
            return None, None, None, None
        return close, high, low, volume
    except Exception:
        return None, None, None, None

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
        return 0.5, 0.0
    idx = np.where(score[:-steps] >= 3)[0]
    if len(idx) == 0:
        return 0.5, 0.0
    rets = close[idx + steps] / close[idx] - 1
    win_rate = (rets > 0).mean()
    pf = rets[rets > 0].sum() / abs(rets[rets <= 0].sum()) if (rets <= 0).any() else 999
    return win_rate, pf

# ==================== 核心计算 ====================
@st.cache_data(show_spinner=False)
def compute_stock_metrics(symbol: str, cfg_key: str = "1年"):
    yahoo_symbol = symbol.upper()
    
    close, high, low, volume = fetch_yahoo_ohlcv(yahoo_symbol, BACKTEST_CONFIG[cfg_key]["range"])
    
    if close is None:
        return None

    macd_hist = macd_hist_np(close)
    rsi = rsi_np(close)
    atr = atr_np(high, low, close)
    obv = obv_np(close, volume)
    vol_ma20 = rolling_mean_np(volume, 20)
    atr_ma20 = rolling_mean_np(atr, 20)
    obv_ma20 = rolling_mean_np(obv, 20)

    sig_macd = macd_hist[-1] > 0
    sig_vol = volume[-1] > vol_ma20[-1] * 1.1
    sig_rsi = rsi[-1] >= 60
    sig_atr = atr[-1] > atr_ma20[-1] * 1.1
    sig_obv = obv[-1] > obv_ma20[-1] * 1.05

    score = sum([sig_macd, sig_vol, sig_rsi, sig_atr, sig_obv])

    sig_details = {
        "MACD>0": sig_macd,
        "放量": sig_vol,
        "RSI≥60": sig_rsi,
        "ATR放大": sig_atr,
        "OBV上升": sig_obv
    }

    sig_macd_hist = (macd_hist > 0).astype(int)
    sig_vol_hist = (volume > vol_ma20 * 1.1).astype(int)
    sig_rsi_hist = (rsi >= 60).astype(int)
    sig_atr_hist = (atr > atr_ma20 * 1.1).astype(int)
    sig_obv_hist = (obv > obv_ma20 * 1.05).astype(int)
    score_arr = sig_macd_hist + sig_vol_hist + sig_rsi_hist + sig_atr_hist + sig_obv_hist

    prob7, pf7 = backtest_with_stats(close[:-1], score_arr[:-1], 7)

    price = close[-1]
    change = (close[-1] / close[-2] - 1) * 100 if len(close) >= 2 else 0

    # 新增：近3日得分是否严格递增 + 今天放量+ATR放大
    recent_rising = False
    if len(score_arr) >= 3:
        s3, s2, s1 = score_arr[-3], score_arr[-2], score_arr[-1]
        if s1 > s2 > s3 and sig_vol and sig_atr:
            recent_rising = True

    return {
        "symbol": symbol.upper(),
        "display_symbol": symbol.upper(),
        "price": price,
        "change": change,
        "score": score,
        "prob7": prob7,
        "pf7": pf7,
        "sig_details": sig_details,
        "is_crypto": False,
        "recent_rising放量ATR": recent_rising
    }

mode = st.selectbox("回测周期", list(BACKTEST_CONFIG.keys()), index=2)
sort_by = st.selectbox("结果排序方式", ["PF7 (盈利因子)", "7日概率"], index=0)

# ==================== session_state 初始化 ====================
if 'high_prob' not in st.session_state:
    st.session_state.high_prob = []
if 'scanned_symbols' not in st.session_state:
    st.session_state.scanned_symbols = set()
if 'failed_count' not in st.session_state:
    st.session_state.failed_count = 0
if 'fully_scanned' not in st.session_state:
    st.session_state.fully_scanned = False
if 'scanning' not in st.session_state:
    st.session_state.scanning = False

# ==================== 强制全部股票显示（每次渲染页面都重新检查并补齐） ====================
forced_symbols = set([s.upper() for s in tickers_to_scan])
computed_symbols = {x["symbol"] for x in st.session_state.high_prob if x is not None and "symbol" in x}
missing = forced_symbols - computed_symbols

for sym in missing:
    st.session_state.high_prob.append({
        "symbol": sym,
        "display_symbol": sym + " (待计算或数据不可用)",
        "price": 0.0,
        "change": "N/A",
        "score": 0,
        "prob7": 0.0,
        "pf7": 0.0,
        "sig_details": {"MACD>0": False, "放量": False, "RSI≥60": False, "ATR放大": False, "OBV上升": False},
        "is_crypto": False,
        "recent_rising放量ATR": False
    })

# ==================== 参数变更处理 ====================
total = len(tickers_to_scan)

if st.session_state.get("prev_mode") != mode:
    st.session_state.high_prob = []
    st.session_state.fully_scanned = False
    st.info("🔄 回测周期已变更，已清除旧结果（需重新计算）")

st.session_state.prev_mode = mode

# ==================== 进度条 ====================
progress_bar = st.progress(0)
status_text = st.empty()

current_completed = len(st.session_state.scanned_symbols.intersection(set(tickers_to_scan)))
progress_val = min(1.0, max(0.0, current_completed / total)) if total > 0 else 0.0
progress_bar.progress(progress_val)

# ==================== 显示结果 ====================
if st.session_state.high_prob:
    df_all = pd.DataFrame([x for x in st.session_state.high_prob if x is not None and x["symbol"] in set(tickers_to_scan)])
    
    if not df_all.empty:
        def format_and_sort(df):
            df = df.copy()
            df['price'] = df['price'].round(2)
            df['change'] = df['change'].apply(lambda x: f"{x:+.2f}%" if isinstance(x, (int, float)) else x)
            df['prob7_fmt'] = (df['prob7'] * 100).round(1).map("{:.1f}%".format)
            df['pf7'] = df['pf7'].round(2)
            if sort_by == "PF7 (盈利因子)":
                df = df.sort_values("pf7", ascending=False)
            else:
                df = df.sort_values("prob7", ascending=False)
            return df
        
        df_display = format_and_sort(df_all)
        
        st.subheader(f"全部结果（按 {sort_by} 排序） 共 {len(df_display)} 只")
        
        # 紧凑连续显示：行与行之间零间隙
        for _, row in df_display.iterrows():
            details = row['sig_details']
            detail_str = " | ".join([f"{k}: {'是' if v else '否'}" for k,v in details.items()])
            
            prefix = ""
            if row.get("recent_rising放量ATR", False):
                prefix = "↑↑↑放量ATR连升 "
            
            if row['pf7'] == 0.0 and row['prob7'] == 0.0:
                prefix = "**待计算/无数据** " + prefix
                score_str = "得分: 0/5 - 无信号"
                prob_pf_str = "**7日概率: 0.0% | PF7: 0.0**"
            elif row['pf7'] > 4.0 and row['prob7'] > 0.70:
                prefix = prefix
                score_str = f"**超级优质** 得分: {row['score']}/5 - {detail_str}"
                prob_pf_str = f"**7日概率: {row['prob7_fmt']} | PF7: {row['pf7']}**"
            else:
                prefix = prefix
                score_str = f"得分: {row['score']}/5 - {detail_str}"
                prob_pf_str = f"**7日概率: {row['prob7_fmt']} | PF7: {row['pf7']}**"
            
            line = f"{prefix}{row['display_symbol']} - 价格: ${row['price']:.2f} ({row['change']}) - {score_str} - {prob_pf_str}"
            
            # 每行直接输出，不加任何额外换行或分隔
            st.markdown(line)

st.info(f"总标的: {total} | 已完成: {current_completed} | 累计有结果: {len(st.session_state.high_prob)} | 失败/跳过: {st.session_state.failed_count}")

# ==================== 下载结果 ====================
if st.session_state.high_prob and tickers_to_scan:
    # 准备下载内容 - 按 PF7 降序
    df_download = pd.DataFrame([x for x in st.session_state.high_prob if x is not None])
    if not df_download.empty:
        df_download = df_download.sort_values("pf7", ascending=False)
        
        lines = []
        for _, row in df_download.iterrows():
            details = row['sig_details']
            detail_str = " | ".join([f"{k}: {'是' if v else '否'}" for k,v in details.items()])
            prefix = ""
            if row.get("recent_rising放量ATR", False):
                prefix = "↑↑↑放量ATR连升 "
            prob7_fmt = f"{(row['prob7'] * 100):.1f}%"
            change = f"{row['change']:+.2f}%" if isinstance(row['change'], (int, float)) else row['change']
            line = f"{prefix}{row['symbol']} - 价格: ${row['price']:.2f} ({change}) - 得分: {row['score']}/5 - {detail_str} - 7日概率: {prob7_fmt} | PF7: {row['pf7']:.2f}"
            lines.append(line)
        
        txt_content = "\r\n".join(lines)  # 使用 \r\n 以兼容 Windows 记事本
        
        st.download_button(
            label="📥 下载结果 (按PF7排序 txt)",
            data=txt_content,
            file_name="scan_result_my_stocks.txt",
            mime="text/plain"
        )

# ==================== 扫描逻辑 ====================
if st.button("🚀 开始/继续全量扫描（点击后自动持续运行，不会停）"):
    st.session_state.scanning = True

if st.session_state.scanning and current_completed < total:
    with st.spinner("扫描进行中（每批次刷新一次页面）..."):
        batch_size = 8  # 降低以防限流
        processed_in_this_run = 0
        
        remaining_tickers = [sym for sym in tickers_to_scan if sym not in st.session_state.scanned_symbols]
        
        for sym in remaining_tickers:
            if processed_in_this_run >= batch_size:
                break
            
            anticipated_completed = current_completed + processed_in_this_run + 1
            progress_val = min(1.0, max(0.0, anticipated_completed / total)) if total > 0 else 0.0
            
            status_text.text(f"正在计算 {sym} ({anticipated_completed}/{total})")
            progress_bar.progress(progress_val)
            
            try:
                metrics = compute_stock_metrics(sym, mode)
                if metrics is not None:
                    # 如果已存在占位符，替换它
                    st.session_state.high_prob = [m for m in st.session_state.high_prob if m["symbol"] != sym]
                    st.session_state.high_prob.append(metrics)
                else:
                    st.session_state.failed_count += 1
                st.session_state.scanned_symbols.add(sym)
            except Exception as e:
                st.warning(f"{sym} 异常: {str(e)}")
                st.session_state.failed_count += 1
                st.session_state.scanned_symbols.add(sym)
            
            processed_in_this_run += 1
        
        save_progress()
        
        new_completed = len(st.session_state.scanned_symbols.intersection(set(tickers_to_scan)))
        accurate_progress = min(1.0, max(0.0, new_completed / total)) if total > 0 else 0.0
        progress_bar.progress(accurate_progress)
        
        if new_completed >= total:
            st.session_state.fully_scanned = True
            st.session_state.scanning = False
            st.success("扫描完成！")
        
        st.rerun()

if current_completed >= total:
    st.success("已完成全部扫描！结果已全部更新")

st.caption("2026年1月版 | 支持txt上传 | 强制全部显示 | 结果行间亲密无间无空行无横线 | 直接复制运行")
