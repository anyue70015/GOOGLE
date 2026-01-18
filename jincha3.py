import streamlit as st
import yfinance as yf
import numpy as np
import time
import pandas as pd
import random
import akshare as ak
import os
import json

st.set_page_config(page_title="A股成交额前500短线扫描工具", layout="wide")
st.title("A股成交额前500短线扫描工具 (2026优化版)")

# ── 持久化进度文件 ──
progress_file = "a_share_scan_progress.json"

if 'progress_loaded' not in st.session_state:
    st.session_state.progress_loaded = True
    if os.path.exists(progress_file):
        try:
            with open(progress_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            st.session_state.high_prob = data.get("high_prob", [])
            st.session_state.scanned_symbols = set(data.get("scanned_symbols", []))
            st.session_state.failed_count = data.get("failed_count", 0)
            st.session_state.fully_scanned = data.get("fully_scanned", False)
            st.success("已加载历史进度，可继续扫描")
        except Exception as e:
            st.warning(f"进度加载失败: {e}，从头开始")

def save_progress():
    data = {
        "high_prob": st.session_state.high_prob,
        "scanned_symbols": list(st.session_state.scanned_symbols),
        "failed_count": st.session_state.failed_count,
        "fully_scanned": st.session_state.fully_scanned
    }
    try:
        with open(progress_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except:
        pass

# ── 重置按钮 ──
col1, col2 = st.columns(2)
with col1:
    if st.button("🔄 强制刷新数据 & 清缓存"):
        st.cache_data.clear()
        st.session_state.high_prob = []
        st.session_state.scanned_symbols = set()
        st.session_state.failed_count = 0
        st.session_state.fully_scanned = False
        st.session_state.scanning = False
        if os.path.exists(progress_file):
            os.remove(progress_file)
        st.rerun()

with col2:
    if st.button("🔄 重置所有进度"):
        st.session_state.high_prob = []
        st.session_state.scanned_symbols = set()
        st.session_state.failed_count = 0
        st.session_state.fully_scanned = False
        st.session_state.scanning = False
        if os.path.exists(progress_file):
            os.remove(progress_file)
        st.rerun()

st.markdown("扫描**最近交易日成交额前500**A股（AKShare实时获取）。扫描后自动显示高潜力股（技术信号+简单回测）。低流动性标⚠️。")

# ==================== 加载成交额前500 ====================
@st.cache_data(ttl=1800)  # 缓存30分钟
def load_a_share_top500_by_amount():
    try:
        df = ak.stock_zh_a_spot_em()
        df['代码'] = df['代码'].astype(str).str.zfill(6)
        df_valid = df[df['成交额'].notna() & (df['成交额'] > 0)]
        top500_df = df_valid.sort_values(by='成交额', ascending=False).head(500)
        tickers = top500_df['代码'].tolist()
        if len(tickers) >= 400:
            st.success(f"加载成交额前500成功：{len(tickers)} 只（AKShare实时）")
            return tickers
        else:
            raise ValueError(f"数量不足，仅{len(tickers)}只")
    except Exception as e:
        st.error(f"AKShare失败: {e}")
        # 备用大盘股列表（可手动更新）
        backup = ["600519", "601012", "000001", "002594", "300750", "601318", "600036", "000333", "601166", "002475"]
        st.warning("使用备用列表（仅示例，请检查网络/AKShare版本）")
        return backup

# ==================== 回测周期配置 ====================
BACKTEST_CONFIG = {
    "3个月": {"range": "3mo", "interval": "1d"},
    "6个月": {"range": "6mo", "interval": "1d"},
    "1年":   {"range": "1y",  "interval": "1d"},
    "2年":   {"range": "2y",  "interval": "1d"},
    "3年":   {"range": "3y",  "interval": "1d"},
    "5年":   {"range": "5y",  "interval": "1d"},
    "10年":  {"range": "10y", "interval": "1d"},
}

# ==================== yfinance 数据拉取（优化版） ====================
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_yahoo_ohlcv(symbol: str, range_str: str, interval: str = "1d"):
    suffix = ".SS" if symbol.startswith(('6', '9')) else ".SZ"
    yahoo_symbol = f"{symbol}{suffix}"

    for attempt in range(3):
        try:
            time.sleep(random.uniform(0.8, 2.0))
            df = yf.download(yahoo_symbol, period=range_str, interval=interval,
                             auto_adjust=True, prepost=False, timeout=45, progress=False)
            if df.empty or len(df) < 60:
                return None, None, None, None

            close = df['Close'].dropna().values.astype(float)
            if len(close) < 60:
                return None, None, None, None

            high = df['High'].values.astype(float)[-len(close):]
            low = df['Low'].values.astype(float)[-len(close):]
            volume = df['Volume'].values.astype(float)[-len(close):]

            return close, high, low, volume
        except Exception:
            if attempt == 2:
                pass  # 静默失败，交给上层计数
            time.sleep(3)
    return None, None, None, None

# ==================== 指标计算函数（不变） ====================
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

# ==================== 核心指标计算 ====================
@st.cache_data(show_spinner=False)
def compute_stock_metrics(symbol: str, cfg_key: str = "1年"):
    close, high, low, volume = fetch_yahoo_ohlcv(symbol, BACKTEST_CONFIG[cfg_key]["range"])
    
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

    avg_daily_dollar_vol_recent = (volume[-30:] * close[-30:]).mean() if len(close) >= 30 else 0
    is_low_liquidity = avg_daily_dollar_vol_recent < 80000000  # 8000万阈值

    liquidity_note = " (低流动性⚠️)" if is_low_liquidity else ""

    return {
        "symbol": symbol,
        "display_symbol": symbol + liquidity_note,
        "price": price,
        "change": change,
        "score": score,
        "prob7": prob7,
        "pf7": pf7,
        "sig_details": sig_details,
        "is_low_liquidity": is_low_liquidity
    }

# ==================== 主逻辑 ====================
tickers_to_scan = load_a_share_top500_by_amount()
st.write(f"扫描范围：成交额前500（当前 {len(tickers_to_scan)} 只）")

mode = st.selectbox("回测周期", list(BACKTEST_CONFIG.keys()), index=2)
sort_by = st.selectbox("排序方式", ["PF7 (盈利因子)", "7日概率"], index=0)

tickers_set = set(tickers_to_scan)
total = len(tickers_to_scan)

if 'prev_mode' not in st.session_state:
    st.session_state.prev_mode = mode

if st.session_state.prev_mode != mode:
    st.session_state.high_prob = []
    st.session_state.scanned_symbols = set()
    st.session_state.fully_scanned = False
    st.info("回测周期变更，已重置进度")
    st.session_state.prev_mode = mode
    st.rerun()

for key in ['high_prob', 'scanned_symbols', 'failed_count', 'fully_scanned', 'scanning']:
    if key not in st.session_state:
        if key == 'scanned_symbols':
            st.session_state[key] = set()
        elif key == 'high_prob':
            st.session_state[key] = []
        else:
            st.session_state[key] = False if key == 'fully_scanned' or key == 'scanning' else 0

progress_bar = st.progress(0)
status_text = st.empty()

current_completed = len(st.session_state.scanned_symbols & tickers_set)
progress_val = min(1.0, current_completed / total) if total > 0 else 0
progress_bar.progress(progress_val)

# 显示结果（用DataFrame）
if st.session_state.high_prob:
    df_all = pd.DataFrame([x for x in st.session_state.high_prob if x and x["symbol"] in tickers_set])
    if not df_all.empty:
        df_all['price'] = df_all['price'].round(2)
        df_all['change'] = df_all['change'].apply(lambda x: f"{x:+.2f}%")
        df_all['prob7_fmt'] = (df_all['prob7'] * 100).round(1).map("{:.1f}%".format)
        df_all['pf7'] = df_all['pf7'].round(2)

        sort_key = "pf7" if sort_by == "PF7 (盈利因子)" else "prob7"
        df_sorted = df_all.sort_values(sort_key, ascending=False)

        df_display = df_sorted[['symbol', 'price', 'change', 'score', 'prob7_fmt', 'pf7']].copy()
        df_display['sig_details'] = df_sorted['sig_details'].apply(lambda d: " | ".join(f"{k}:{'是' if v else '否'}" for k,v in d.items()))
        df_display['symbol'] = df_display['symbol'].where(~df_sorted['is_low_liquidity'], df_display['symbol'] + " ⚠️")

        st.subheader(f"优质A股（{len(df_display)} 只，按 {sort_by} 排序）")
        st.dataframe(df_display.rename(columns={
            "symbol": "代码", "price": "价格", "change": "涨跌幅", "score": "得分/5",
            "prob7_fmt": "7日胜率", "pf7": "PF7", "sig_details": "信号详情"
        }), use_container_width=True, hide_index=True)

if not st.session_state.high_prob:
    st.info("点击下方按钮开始/继续扫描")

st.info(f"总标的: {total} | 已完成: {current_completed} | 有结果: {len(st.session_state.high_prob)} | 失败/跳过: {st.session_state.failed_count}")

if st.session_state.failed_count > 0:
    failed_syms = [sym for sym in st.session_state.scanned_symbols if sym not in {m['symbol'] for m in st.session_state.high_prob}]
    st.warning(f"失败股票示例（前20）：{', '.join(failed_syms[:20])} ...")

# 扫描按钮 & 逻辑
if st.button("🚀 开始/继续扫描（每批100只自动刷新）"):
    st.session_state.scanning = True

if st.session_state.scanning and current_completed < total:
    with st.spinner("扫描中..."):
        batch_size = 100
        processed = 0
        remaining = [s for s in tickers_to_scan if s not in st.session_state.scanned_symbols]

        for sym in remaining:
            if processed >= batch_size:
                break

            status_text.text(f"处理 {sym} ({current_completed + processed + 1}/{total})")
            progress_bar.progress(min(1.0, (current_completed + processed + 1) / total))

            try:
                metrics = compute_stock_metrics(sym, mode)
                if metrics:
                    st.session_state.high_prob.append(metrics)
                else:
                    st.session_state.failed_count += 1
                st.session_state.scanned_symbols.add(sym)
            except Exception as e:
                st.session_state.failed_count += 1
                st.session_state.scanned_symbols.add(sym)

            processed += 1
            time.sleep(0.1)  # 轻微延时防卡

        save_progress()

        new_completed = len(st.session_state.scanned_symbols & tickers_set)
        progress_bar.progress(min(1.0, new_completed / total))

        if new_completed >= total:
            st.session_state.fully_scanned = True
            st.session_state.scanning = False
            st.success("前500扫描完成！")

        st.rerun()

if current_completed >= total:
    st.success("已完成全部扫描！")

st.caption("2026年1月版 | AKShare + yfinance | 直接复制运行 | 如yfinance失败多，可考虑代理或换源")
