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

# ── 重置按钮 ──
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
        raw = content.replace("\n", " ").replace(",", " ").strip()
        tickers_to_scan = [t.strip().upper() for t in raw.split() if t.strip()]
        tickers_to_scan = list(dict.fromkeys(tickers_to_scan))
        st.success(f"成功读取 {len(tickers_to_scan)} 只股票")
        st.write("股票列表预览：", ", ".join(tickers_to_scan[:15]) + " ..." if len(tickers_to_scan)>15 else ", ".join(tickers_to_scan))
    except:
        st.error("文件读取失败，请确保是纯文本txt格式")
        tickers_to_scan = []
else:
    st.info("请先上传股票列表txt文件")
    tickers_to_scan = []

if not tickers_to_scan:
    st.stop()

st.write("点击「开始/继续扫描」后会自动持续运行。所有股票都会强制显示（即使数据拉取失败或无信号，也会显示 N/A / 0 分）。")

# ==================== 核心常量 ====================
START_DATE = "2025-12-26"
END_DATE = "2026-01-24"
INTERVAL = "1d"

# ==================== 数据拉取 ====================
@st.cache_data(ttl=300, show_spinner=False)
def fetch_yahoo_ohlcv(yahoo_symbol: str):
    try:
        time.sleep(random.uniform(1.2, 2.8))
        ticker = yf.Ticker(yahoo_symbol)
        df = ticker.history(start=START_DATE, end=END_DATE, interval=INTERVAL, auto_adjust=True, prepost=False, timeout=30)
        if df.empty or len(df) < 20:
            return None, None, None, None, None
        dates = df.index.strftime("%Y-%m-%d").values
        close = df['Close'].values.astype(float)
        high = df['High'].values.astype(float)
        low = df['Low'].values.astype(float)
        volume = df['Volume'].values.astype(float)
        mask = ~np.isnan(close)
        dates, close, high, low, volume = dates[mask], close[mask], high[mask], low[mask], volume[mask]
        if len(close) < 20:
            return None, None, None, None, None
        return dates, close, high, low, volume
    except Exception:
        return None, None, None, None, None

# ==================== 指标函数（保持原样） ====================
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
def compute_stock_metrics(symbol: str):
    yahoo_symbol = symbol.upper()
    
    dates, close, high, low, volume = fetch_yahoo_ohlcv(yahoo_symbol)
    
    if dates is None:
        return None

    n_days = min(20, len(close))
    dates = dates[-n_days:]
    close = close[-n_days:]
    high = high[-n_days:]
    low = low[-n_days:]
    volume = volume[-n_days:]

    macd_hist = macd_hist_np(close)
    rsi = rsi_np(close)
    atr = atr_np(high, low, close)
    obv = obv_np(close, volume)
    vol_ma20 = rolling_mean_np(volume, min(20, len(volume)))
    atr_ma20 = rolling_mean_np(atr, min(20, len(atr)))
    obv_ma20 = rolling_mean_np(obv, min(20, len(obv)))

    daily_metrics = []
    for i in range(len(close)):
        sig_macd = macd_hist[i] > 0
        sig_vol = volume[i] > vol_ma20[i] * 1.1 if i >= 19 else False
        sig_rsi = rsi[i] >= 60
        sig_atr = atr[i] > atr_ma20[i] * 1.1 if i >= 19 else False
        sig_obv = obv[i] > obv_ma20[i] * 1.05 if i >= 19 else False

        score = sum([sig_macd, sig_vol, sig_rsi, sig_atr, sig_obv])

        sig_details = {
            "MACD>0": sig_macd,
            "放量": sig_vol,
            "RSI≥60": sig_rsi,
            "ATR放大": sig_atr,
            "OBV上升": sig_obv
        }

        price = close[i]
        change = (close[i] / close[i-1] - 1) * 100 if i >= 1 else 0

        daily_metrics.append({
            "date": dates[i],
            "price": price,
            "change": change,
            "score": score,
            "sig_details": sig_details
        })

    sig_macd_hist = (macd_hist > 0).astype(int)
    sig_vol_hist = (volume > vol_ma20 * 1.1).astype(int)
    sig_rsi_hist = (rsi >= 60).astype(int)
    sig_atr_hist = (atr > atr_ma20 * 1.1).astype(int)
    sig_obv_hist = (obv > obv_ma20 * 1.05).astype(int)
    score_arr = sig_macd_hist + sig_vol_hist + sig_rsi_hist + sig_atr_hist + sig_obv_hist

    prob7, pf7 = backtest_with_stats(close, score_arr, 7)

    recent_rising = False
    if len(score_arr) >= 3:
        s3, s2, s1 = score_arr[-3], score_arr[-2], score_arr[-1]
        if s1 > s2 > s3 and sig_vol_hist[-1] and sig_atr_hist[-1]:
            recent_rising = True

    return {
        "symbol": symbol.upper(),
        "display_symbol": symbol.upper(),
        "prob7": prob7,
        "pf7": pf7,
        "daily_metrics": daily_metrics,
        "is_crypto": False,
        "recent_rising放量ATR": recent_rising
    }

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

# ==================== 强制显示所有股票（优化：避免重复追加占位） ====================
forced_symbols = set([s.upper() for s in tickers_to_scan])

# 移除旧的占位符行（防止污染）
st.session_state.high_prob = [x for x in st.session_state.high_prob if x["symbol"] not in forced_symbols or "待计算或数据不可用" not in x.get("display_symbol", "")]

# 添加缺失的占位符
existing_symbols = {x["symbol"] for x in st.session_state.high_prob if x is not None and "symbol" in x}
missing = forced_symbols - existing_symbols

for sym in missing:
    st.session_state.high_prob.append({
        "symbol": sym,
        "display_symbol": sym + " (待计算或数据不可用)",
        "prob7": 0.0,
        "pf7": 0.0,
        "daily_metrics": [{"date": "N/A", "price": 0.0, "change": "N/A", "score": 0, 
                           "sig_details": {"MACD>0": False, "放量": False, "RSI≥60": False, "ATR放大": False, "OBV上升": False}}] * 20,
        "is_crypto": False,
        "recent_rising放量ATR": False
    })

# ==================== 进度 ====================
progress_bar = st.progress(0)
status_text = st.empty()

total = len(tickers_to_scan)
current_completed = len(st.session_state.scanned_symbols.intersection(set(tickers_to_scan)))
progress_val = min(1.0, max(0.0, current_completed / total)) if total > 0 else 0.0
progress_bar.progress(progress_val)

# ==================== 显示结果（优化：折叠 + 无数据提示） ====================
if st.session_state.high_prob:
    all_metrics = [x for x in st.session_state.high_prob if x is not None and x["symbol"] in set(tickers_to_scan)]
    
    if all_metrics:
        df_all = pd.DataFrame(all_metrics)
        df_all['prob7'] = pd.to_numeric(df_all['prob7'], errors='coerce').fillna(0.0)
        df_all['pf7']   = pd.to_numeric(df_all['pf7'],   errors='coerce').fillna(0.0)
        
        if sort_by == "PF7 (盈利因子)":
            df_all = df_all.sort_values("pf7", ascending=False)
        else:
            df_all = df_all.sort_values("prob7", ascending=False)
        
        st.subheader(f"全部结果（按 {sort_by} 排序） 共 {len(df_all)} 只")
        
        for _, row in df_all.iterrows():
            prefix = "↑↑↑放量ATR连升 " if row.get("recent_rising放量ATR", False) else ""
            prob7_fmt = f"{(row['prob7'] * 100):.1f}%"
            pf7_str = f"{row['pf7']:.2f}" if row['pf7'] > 0 else "N/A"
            
            is_placeholder = all(dm['date'] == "N/A" for dm in row['daily_metrics'])
            
            expander_title = f"{prefix}{row['display_symbol']} — 7日概率: {prob7_fmt} | PF7: {pf7_str}"
            with st.expander(expander_title):
                if is_placeholder:
                    st.info("暂无有效K线数据（可能ticker无效或日期范围无交易）")
                else:
                    for dm in row['daily_metrics']:
                        details = dm['sig_details']
                        detail_str = " | ".join([f"{k}: {'是' if v else '否'}" for k,v in details.items()])
                        change = f"{dm['change']:+.2f}%" if isinstance(dm['change'], (int, float)) else dm['change']
                        price_str = f"${dm['price']:.2f}" if dm['price'] > 0 else "N/A"
                        st.markdown(f"{dm['date']} | 价格: {price_str} ({change}) | 得分: {dm['score']}/5 | {detail_str}")

st.info(f"总标的: {total} | 已完成: {current_completed} | 累计有结果: {len(st.session_state.high_prob)} | 失败/跳过: {st.session_state.failed_count}")

# ==================== 下载结果 ====================
if st.session_state.high_prob and tickers_to_scan:
    all_metrics = [x for x in st.session_state.high_prob if x is not None]
    if all_metrics:
        df_download = pd.DataFrame(all_metrics).sort_values("pf7", ascending=False)
        df_download['prob7'] = pd.to_numeric(df_download['prob7'], errors='coerce').fillna(0.0)
        df_download['pf7']   = pd.to_numeric(df_download['pf7'],   errors='coerce').fillna(0.0)
        
        lines = []
        for _, row in df_download.iterrows():
            prefix = "↑↑↑放量ATR连升 " if row.get("recent_rising放量ATR", False) else ""
            prob7_fmt = f"{(row['prob7'] * 100):.1f}%"
            pf7_str = f"{row['pf7']:.2f}" if row['pf7'] > 0 else "N/A"
            lines.append(f"{prefix}{row['symbol']} - 整体7日概率: {prob7_fmt} | PF7: {pf7_str}")
            
            is_placeholder = all(dm['date'] == "N/A" for dm in row['daily_metrics'])
            if is_placeholder:
                lines.append("  暂无有效数据")
            else:
                for dm in row['daily_metrics']:
                    details = dm['sig_details']
                    detail_str = " | ".join([f"{k}: {'是' if v else '否'}" for k,v in details.items()])
                    change = f"{dm['change']:+.2f}%" if isinstance(dm['change'], (int, float)) else dm['change']
                    price_str = f"${dm['price']:.2f}" if dm['price'] > 0 else "N/A"
                    line = f"  {dm['date']} - 价格: {price_str} ({change}) - 得分: {dm['score']}/5 - {detail_str}"
                    lines.append(line)
        
        txt_content = "\n".join(lines)
        
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
        batch_size = 8
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
                metrics = compute_stock_metrics(sym)
                if metrics is not None:
                    # 替换任何旧行（包括占位）
                    st.session_state.high_prob = [m for m in st.session_state.high_prob if m["symbol"] != sym]
                    st.session_state.high_prob.append(metrics)
                else:
                    st.session_state.failed_count += 1
                st.session_state.scanned_symbols.add(sym)
            except Exception as e:
                st.warning(f"{sym} 计算异常: {str(e)}")
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

st.caption("2026年1月版 | 支持txt上传 | 强制全部显示 | 已优化占位符和显示布局 | 直接复制运行")
