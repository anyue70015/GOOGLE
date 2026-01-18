import streamlit as st
import numpy as np
import time
import pandas as pd
import random
import akshare as ak
import os
import json
from datetime import datetime, timedelta

st.set_page_config(page_title="科创板 + 创业板短线扫描工具", layout="wide")
st.title("科创板 + 创业板短线扫描工具")

# ── 持久化进度 ──
progress_file = "kcb_cyb_scan_progress.json"

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
            st.warning(f"进度加载失败: {e}，将从头开始")

def save_progress():
    data = {
        "high_prob": st.session_state.high_prob,
        "scanned_symbols": list(st.session_state.scanned_symbols),
        "failed_count": st.session_state.failed_count,
        "fully_scanned": st.session_state.fully_scanned
    }
    try:
        temp_file = progress_file + ".tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(temp_file, progress_file)
    except:
        pass

# ── 重置按钮 ──
col1, col2 = st.columns(2)
with col1:
    if st.button("🔄 清缓存 & 强制刷新数据"):
        st.cache_data.clear()
        st.session_state.high_prob = []
        st.session_state.scanned_symbols = set()
        st.session_state.failed_count = 0
        st.session_state.fully_scanned = False
        st.session_state.scanning = False
        st.session_state.paused = False
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
        st.session_state.paused = False
        if os.path.exists(progress_file):
            os.remove(progress_file)
        st.rerun()

# ── 手动暂停 / 继续 ──
if 'paused' not in st.session_state:
    st.session_state.paused = False

col_pause, col_resume = st.columns(2)
with col_pause:
    if not st.session_state.paused:
        if st.button("⏸️ 手动暂停扫描"):
            st.session_state.paused = True
            st.rerun()

with col_resume:
    if st.session_state.paused:
        if st.button("▶️ 手动继续扫描"):
            st.session_state.paused = False
            st.rerun()

st.markdown("扫描**科创板(688开头)** + **创业板(300开头)** 所有股票。未手动暂停时，每完成300只自动暂停10分钟（可手动继续）。")

# ==================== 加载科创板 + 创业板股票 ====================
@st.cache_data(ttl=1800)
def load_kcb_cyb_tickers():
    try:
        df = ak.stock_zh_a_spot_em()
        df['代码'] = df['代码'].astype(str).str.zfill(6)
        df_target = df[df['代码'].str.startswith(('688', '300'))]
        tickers = df_target['代码'].tolist()
        st.success(f"加载科创板+创业板成功：{len(tickers)} 只")
        return tickers
    except Exception as e:
        st.error(f"加载失败: {e}")
        return ["688981", "300750", "688111", "300059"]  # 备用

tickers_to_scan = load_kcb_cyb_tickers()
st.write(f"扫描范围：科创板 + 创业板（总计 {len(tickers_to_scan)} 只）")

# ==================== 回测周期 ====================
BACKTEST_CONFIG = {
    "3个月": {"days": 90},
    "6个月": {"days": 180},
    "1年":   {"days": 365},
    "2年":   {"days": 730},
    "3年":   {"days": 1095},
    "5年":   {"days": 1825},
    "10年":  {"days": 3650},
}

# ==================== AKShare 拉历史数据 ====================
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_ohlcv_ak(symbol: str, days_back: int):
    try:
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days_back + 60)).strftime("%Y%m%d")
        time.sleep(random.uniform(0.8, 2.0))
        df = ak.stock_zh_a_hist(
            symbol=symbol,
            period="daily",
            start_date=start_date,
            end_date=end_date,
            adjust="qfq"
        )
        if df.empty or len(df) < 20:
            return None, None, None, None
        close = df['收盘'].values.astype(float)
        high = df['最高'].values.astype(float)
        low = df['最低'].values.astype(float)
        volume = df['成交量'].values.astype(float) * 100  # 手 → 股
        return close, high, low, volume
    except Exception as e:
        st.warning(f"{symbol} AKShare 失败: {str(e)[:80]}...")
        return None, None, None, None

# ==================== 指标函数（你原来的完整版） ====================
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
    days = BACKTEST_CONFIG[cfg_key]["days"]
    close, high, low, volume = fetch_ohlcv_ak(symbol, days)
    
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
    sig_vol = volume[-1] > vol_ma20[-1] * 1.1 if len(vol_ma20) > 0 else False
    sig_rsi = rsi[-1] >= 60
    sig_atr = atr[-1] > atr_ma20[-1] * 1.1 if len(atr_ma20) > 0 else False
    sig_obv = obv[-1] > obv_ma20[-1] * 1.05 if len(obv_ma20) > 0 else False

    score = sum([sig_macd, sig_vol, sig_rsi, sig_atr, sig_obv])

    sig_details = {
        "MACD>0": sig_macd,
        "放量": sig_vol,
        "RSI≥60": sig_rsi,
        "ATR放大": sig_atr,
        "OBV上升": sig_obv
    }

    sig_macd_hist = (macd_hist > 0).astype(int)
    sig_vol_hist = (volume > vol_ma20 * 1.1).astype(int) if len(vol_ma20) > 0 else np.zeros_like(close, dtype=int)
    sig_rsi_hist = (rsi >= 60).astype(int)
    sig_atr_hist = (atr > atr_ma20 * 1.1).astype(int) if len(atr_ma20) > 0 else np.zeros_like(close, dtype=int)
    sig_obv_hist = (obv > obv_ma20 * 1.05).astype(int) if len(obv_ma20) > 0 else np.zeros_like(close, dtype=int)
    score_arr = sig_macd_hist + sig_vol_hist + sig_rsi_hist + sig_atr_hist + sig_obv_hist

    prob7, pf7 = backtest_with_stats(close[:-1], score_arr[:-1], 7)

    price = close[-1]
    change = (close[-1] / close[-2] - 1) * 100 if len(close) >= 2 else 0

    avg_daily_dollar_vol_recent = (volume[-30:] * close[-30:]).mean() if len(close) >= 30 else 0
    is_low_liquidity = avg_daily_dollar_vol_recent < 100000000

    return {
        "symbol": symbol,
        "price": price,
        "change": change,
        "score": score,
        "prob7": prob7,
        "pf7": pf7,
        "sig_details": sig_details,
        "is_low_liquidity": is_low_liquidity
    }

# ==================== 主界面 ====================
mode = st.selectbox("回测周期", list(BACKTEST_CONFIG.keys()), index=2)

# session_state 初始化
for key in ['high_prob', 'scanned_symbols', 'failed_count', 'fully_scanned', 'scanning', 'paused']:
    if key not in st.session_state:
        if key == 'scanned_symbols':
            st.session_state[key] = set()
        elif key == 'high_prob':
            st.session_state[key] = []
        elif key == 'paused':
            st.session_state[key] = False
        else:
            st.session_state[key] = 0 if 'count' in key else False

progress_bar = st.progress(0)
status_text = st.empty()

current_completed = len(st.session_state.scanned_symbols & set(tickers_to_scan))
total = len(tickers_to_scan)
progress_bar.progress(min(1.0, current_completed / total if total > 0 else 0))

# 显示符合条件的股票
if st.session_state.high_prob:
    df_all = pd.DataFrame([x for x in st.session_state.high_prob if x])
    df_all['prob7_pct'] = (df_all['prob7'] * 100).round(1)
    df_all['pf7'] = df_all['pf7'].round(2)

    # 筛选条件
    mask = (df_all['prob7_pct'] > 68) | (df_all['pf7'] > 3.6)
    df_filtered = df_all[mask].copy().sort_values("pf7", ascending=False)

    if not df_filtered.empty:
        st.subheader(f"符合条件股票（7日概率 >68% 或 PF7 >3.6）：共 {len(df_filtered)} 只")
        st.dataframe(df_filtered[['symbol', 'prob7_pct', 'pf7']].rename(columns={
            'symbol': '股票代码',
            'prob7_pct': '7日概率(%)',
            'pf7': 'PF7'
        }), use_container_width=True, hide_index=True)

        # 下载 TXT（纯代码）
        txt_content = "\n".join(df_filtered['symbol'].astype(str).tolist())
        st.download_button(
            "下载符合条件股票代码 TXT",
            txt_content,
            file_name="科创创业板_优质代码.txt",
            mime="text/plain"
        )
    else:
        st.info("暂无满足条件的股票")

st.info(f"已完成: {current_completed}/{total} | 有结果: {len(st.session_state.high_prob)} | 失败/跳过: {st.session_state.failed_count}")

# 扫描逻辑
if st.button("🚀 开始/继续扫描"):
    st.session_state.scanning = True

if st.session_state.scanning and current_completed < total and not st.session_state.paused:
    with st.spinner("扫描中（每50只刷新一次）..."):
        batch_size = 50
        processed = 0
        remaining = [s for s in tickers_to_scan if s not in st.session_state.scanned_symbols]

        for sym in remaining:
            if processed >= batch_size or st.session_state.paused:
                break

            status_text.text(f"正在计算 {sym} ({current_completed + processed + 1}/{total})")
            progress_bar.progress((current_completed + processed + 1) / total)

            metrics = compute_stock_metrics(sym, mode)
            if metrics:
                st.session_state.high_prob.append(metrics)
            else:
                st.session_state.failed_count += 1
            st.session_state.scanned_symbols.add(sym)

            processed += 1

        # 自动暂停检查
        new_completed = len(st.session_state.scanned_symbols & set(tickers_to_scan))
        if new_completed % 300 == 0 and new_completed > 0 and new_completed < total:
            st.session_state.paused = True
            st.warning("自动暂停：已完成 300 只，休息 10 分钟（或手动按继续）")
            time.sleep(600)
            st.session_state.paused = False
            st.rerun()

        if new_completed >= total:
            st.session_state.fully_scanned = True
            st.session_state.scanning = False
            st.success("扫描完成！")

        save_progress()
        st.rerun()

if st.session_state.fully_scanned:
    st.success("已完成全部扫描！")

st.caption("2026年1月版 | 只扫描科创板(688xxx) + 创业板(300xxx) | 每300只自动暂停10分钟 | 可手动暂停/继续 | 只显示概率>68% 或 PF7>3.6 的股票代码 | 支持TXT下载")
