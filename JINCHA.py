import streamlit as st
import numpy as np
import time
import pandas as pd
import random
import baostock as bs
import os
import json
from datetime import datetime, timedelta

st.set_page_config(page_title="科创板 + 创业板短线扫描工具 (Baostock版)", layout="wide")
st.title("科创板 + 创业板短线扫描工具（Baostock稳定版）")

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

st.markdown("扫描科创板(688开头) + 创业板(300开头) 股票（Baostock源，按代码排序取前300各）。上市天数 > 360 天。优质信号（PF7>4 且 概率>68%）实时弹出。")

# ==================== 加载股票列表（Baostock版） ====================
@st.cache_data(ttl=1800)
def load_kcb_cyb_tickers():
    try:
        st.info("Baostock加载科创板 + 创业板股票列表...")
        lg = bs.login()
        if lg.error_code != '0':
            st.error(f"登录失败: {lg.error_msg}")
            return [], {}
        
        rs = bs.query_all_stock(day=datetime.now().strftime("%Y-%m-%d"))
        if rs.error_code != '0':
            st.error(f"查询失败: {rs.error_msg}")
            bs.logout()
            return [], {}
        
        data_list = []
        while rs.error_code == '0' and rs.next():
            data_list.append(rs.get_row_data())
        
        df = pd.DataFrame(data_list, columns=rs.fields)
        df['代码'] = df['code'].str[3:]  # 去sh./sz.前缀
        df_target = df[df['代码'].str.startswith(('688', '300')) & (df['code_name'] != '')].copy()
        
        # 按代码排序，取各前300
        df_target = df_target.sort_values('代码')
        kcb = df_target[df_target['代码'].str.startswith('688')].head(300)
        cyb = df_target[df_target['代码'].str.startswith('300')].head(300)
        df_selected = pd.concat([kcb, cyb])
        
        tickers = df_selected['代码'].tolist()
        names = dict(zip(df_selected['代码'], df_selected['code_name']))
        
        bs.logout()
        st.success(f"加载成功：{len(tickers)} 只")
        return tickers, names
    except Exception as e:
        st.error(f"加载异常: {e}")
        if 'lg' in locals():
            bs.logout()
        return [], {}

tickers_to_scan, stock_names = load_kcb_cyb_tickers()
st.write(f"扫描范围：{len(tickers_to_scan)} 只")

# ==================== 回测周期 ====================
BACKTEST_CONFIG = {
    "3个月": {"days": 90},
    "6个月": {"days": 180},
    "1年":   {"days": 365},
    "2年":   {"days": 730},
}

# ==================== 获取日K - Baostock版 ====================
@st.cache_data(ttl=3600 * 24, show_spinner=False)
def fetch_ohlcv_ak(symbol: str, days_back: int):
    lg = bs.login()
    if lg.error_code != '0':
        return None, None, None, None
    
    try:
        bs_code = "sh." + symbol if symbol.startswith('688') else "sz." + symbol
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days_back + 60)).strftime("%Y-%m-%d")
        
        rs = bs.query_history_k_data_plus(
            code=bs_code,
            fields="date,open,high,low,close,volume",
            start_date=start_date,
            end_date=end_date,
            frequency="d",
            adjustflag="2"  # 前复权
        )
        
        if rs.error_code != '0' or not rs.next():
            bs.logout()
            return None, None, None, None
        
        data_list = []
        while rs.error_code == '0' and rs.next():
            data_list.append(rs.get_row_data())
        
        df = pd.DataFrame(data_list, columns=rs.fields)
        if len(df) < 30:
            bs.logout()
            return None, None, None, None
        
        close = pd.to_numeric(df['close']).values
        high = pd.to_numeric(df['high']).values
        low = pd.to_numeric(df['low']).values
        volume = pd.to_numeric(df['volume']).values * 100
        
        bs.logout()
        return close, high, low, volume
    except:
        bs.logout()
        return None, None, None, None

# ==================== 指标函数（原样保持） ====================
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
    gain_ema = np.empty_like(gain); gain_ema[0] = gain[0]
    loss_ema = np.empty_like(loss); loss_ema[0] = loss[0]
    for i in range(1, len(gain)):
        gain_ema[i] = alpha * gain[i] + (1 - alpha) * gain_ema[i-1]
        loss_ema[i] = alpha * loss[i] + (1 - alpha) * loss_ema[i-1]
    rs = gain_ema / (loss_ema + 1e-9)
    return 100 - (100 / (1 + rs))

def atr_np(high, low, close, period=14):
    prev_close = np.roll(close, 1); prev_close[0] = close[0]
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))
    atr = np.empty_like(tr); atr[0] = tr[0]
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

def obv_np(close, volume):
    direction = np.sign(np.diff(close, prepend=close[0]))
    return np.cumsum(direction * volume)

def backtest_with_stats(close, score, steps):
    if len(close) <= steps + 1:
        return 0.5, 0.0
    idx = np.where(score[:-steps] >= 3)[0]
    if len(idx) == 0:
        return 0.5, 0.0
    rets = close[idx + steps] / close[idx] - 1
    win_rate = (rets > 0).mean()
    pf = rets[rets > 0].sum() / abs(rets[rets <= 0].sum()) if (rets <= 0).any() else 9999
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
        "MACD>0": sig_macd, "放量": sig_vol, "RSI≥60": sig_rsi,
        "ATR放大": sig_atr, "OBV上升": sig_obv
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

    return {
        "symbol": symbol,
        "name": stock_names.get(symbol, "未知"),
        "price": round(price, 2),
        "change": round(change, 2),
        "score": score,
        "prob7": prob7,
        "pf7": pf7,
        "prob7_pct": round(prob7 * 100, 1),
        "signals": ", ".join([k for k, v in sig_details.items() if v]) or "无"
    }

# ==================== 主扫描逻辑 ====================
mode = st.selectbox("回测周期", list(BACKTEST_CONFIG.keys()), index=2)

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
progress_bar.progress(min(1.0, current_completed / total) if total > 0 else 0)

premium_count = sum(1 for x in st.session_state.high_prob if x.get('pf7', 0) > 4 and x.get('prob7_pct', 0) > 68)
st.info(f"已完成: {current_completed}/{total} | 优质实时发现: {premium_count} | 失败/跳过: {st.session_state.failed_count}")

if st.button("🚀 开始/继续扫描"):
    st.session_state.scanning = True

if st.session_state.scanning and current_completed < total and not st.session_state.paused:
    with st.spinner("扫描中（每批10只，Baostock防卡）..."):
        batch_size = 10
        processed = 0
        remaining = [s for s in tickers_to_scan if s not in st.session_state.scanned_symbols]
        batch_start = time.time()

        for sym in remaining:
            if processed >= batch_size or st.session_state.paused:
                break
            status_text.text(f"计算 {sym} ({current_completed + processed + 1}/{total})")
            progress_bar.progress((current_completed + processed + 1) / total)

            try:
                metrics = compute_stock_metrics(sym, mode)
                if metrics:
                    st.session_state.high_prob.append(metrics)
                    if metrics['pf7'] > 4 and metrics['prob7_pct'] > 68:
                        st.success(f"【优质实时发现】 {sym} {metrics['name']}   PF7={metrics['pf7']:.2f}   7日胜率={metrics['prob7_pct']}%   得分={metrics['score']}   信号: {metrics['signals']}")
                else:
                    st.session_state.failed_count += 1
            except:
                st.session_state.failed_count += 1

            st.session_state.scanned_symbols.add(sym)
            processed += 1
            time.sleep(random.uniform(5.0, 10.0))  # Baostock延时防限

        batch_time = time.time() - batch_start
        avg = batch_time / processed if processed > 0 else 0
        st.info(f"本批 {processed} 只完成，耗时 {batch_time:.1f}s，平均 {avg:.1f}s/只")

        if len(st.session_state.scanned_symbols & set(tickers_to_scan)) >= total:
            st.session_state.fully_scanned = True
            st.session_state.scanning = False
            st.success("扫描完成！")

        save_progress()
        st.rerun()

if st.session_state.fully_scanned:
    st.success("已完成全部扫描！")

# ==================== 结果显示 ====================
high_prob_list = [x for x in st.session_state.high_prob if x]

if high_prob_list:
    df_all = pd.DataFrame(high_prob_list)
    df_all['prob7_pct'] = df_all['prob7'].apply(lambda x: round(x * 100, 1))
    df_all['pf7'] = df_all['pf7'].round(2)

    mask_premium = (df_all['pf7'] > 4) & (df_all['prob7_pct'] > 68)
    df_premium = df_all[mask_premium].sort_values(by=['pf7', 'prob7_pct'], ascending=[False, False]).copy()
    df_premium['group'] = '优质（PF7>4 且 概率>68%）'

    df_others = df_all[~mask_premium].sort_values(by=['score', 'pf7'], ascending=[False, False]).copy()
    df_others['group'] = '其他（备选）'

    df_display = pd.concat([df_premium, df_others]) if not df_premium.empty else df_others

    st.subheader(f"扫描结果共 {len(df_display)} 只，其中优质 {len(df_premium)} 只")

    display_lines = []
    for _, row in df_display.iterrows():
        display_line = f"[{row['group']}] {row['symbol']}  {row['name']}  现价 {row['price']:.2f}  涨幅 {row['change']:+.2f}%  得分 {row['score']}  7日胜率 {row['prob7_pct']}%  PF7 {row['pf7']:.2f}  信号: {row['signals']}"
        display_lines.append(display_line)

    st.text_area("结果（优质已排最前）", "\n".join(display_lines), height=600)

else:
    st.info("暂无结果。请点击开始扫描")

st.caption("Baostock完整版 | 2026年 | 防卡稳定 | 支持暂停/下载进度")
