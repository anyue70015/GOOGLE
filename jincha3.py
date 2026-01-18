import streamlit as st
import yfinance as yf
import numpy as np
import time
import pandas as pd
import random
import requests
import json
import os

st.set_page_config(page_title="A股成交额前500短线扫描工具", layout="wide")
st.title("A股成交额前500短线扫描工具")

# ── 持久化进度文件 ──
progress_file = "a_share_scan_progress.json"

# 只加载一次进度
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
        with open(progress_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
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

st.write("扫描A股最近交易日**成交额前500**股票（动态从东方财富接口获取）。点击「开始扫描」后会自动持续运行（每100只自动刷新页面）。低流动性标的会标注⚠️。")

# ==================== 动态加载A股成交额前500 ====================
@st.cache_data(ttl=3600)  # 缓存1小时
def load_a_share_top500_by_amount():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
    }
    
    # 东方财富成交额排行接口（实时前500）
    api_url = "https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=500&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f6&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23&fields=f12,f14,f2,f3,f6,f8&cb=&_="
    
    try:
        resp = requests.get(api_url, headers=headers, timeout=15)
        resp.raise_for_status()
        text = resp.text.strip()
        
        # 去掉可能的回调函数包裹
        if text.startswith("jQuery") or text.startswith("("):
            start = text.find("(") + 1
            end = text.rfind(")")
            text = text[start:end]
        
        data = json.loads(text)
        
        if 'data' in data and 'diff' in data['data']:
            items = data['data']['diff']
            tickers = []
            for item in items:
                code = str(item.get('f12', ''))
                if code and len(code) == 6 and code.isdigit():
                    tickers.append(code)
            tickers = list(set(tickers))[:500]
            if len(tickers) >= 300:
                st.success(f"成功加载A股成交额前500股票（{len(tickers)} 只）")
                return tickers
            else:
                raise ValueError("返回数量不足")
        else:
            raise ValueError("API无有效数据")
            
    except Exception as e:
        st.error(f"动态加载失败: {str(e)}")
        # 备用列表（2025-2026年常见高成交额前200示例，实际请替换最新列表）
        backup = [ "600519","601012","000001","002594","300750","601318","600036","000333","601166","002475",
        "601899","600900","601398","600030","300059","000858","002230","600276","601288","603259",
        "002241","600887","000568","002714","300760","601857","601988","000002","601668","600519",
        "000063","002415","002352","300122","601688","600048","601601","601766","601390","601628",
        "600999","600016","601229","600837","600000","601211","601881","000776","002736","601995",
        "600061","600155","000166","002945","601198","002797","000728","002500","601236","601377",
        "600909","601878","601162","002797","600958","600621","601456","601696","002945","600155",
        "601236","601377","600909","601878","601162","002945","600958","600621","601456","601696",
        "000002","601668","600519","000063","002415","002352","300122","601688","600048","601601",
        "601766","601390","601628","600999","600016","601229","600837","600000","601211","601881",
        "000776","002736","601995","600061","600155","000166","002945","601198","002797","000728",
        "002500","601236","601377","600909","601878","601162","002797","600958","600621","601456",
        "601696","002945","600155","601236","601377","600909","601878","601162","002945","600958",
        "600621","601456","601696","000002","601668","600519","000063","002415","002352","300122",
        "601688","600048","601601","601766","601390","601628","600999","600016","601229","600837",
        "600000","601211","601881","000776","002736","601995","600061","600155","000166","002945",
        "601198","002797","000728","002500","601236","601377","600909","601878","601162","002797",
        "600958","600621","601456","601696","002945","600155","601236","601377","600909","601878",
        "601162","002945","600958","600621","601456","601696"
    ]
        st.warning("使用备用列表（仅200只示例，请手动更新完整500只）")
        return backup

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

# ==================== 数据拉取（支持A股后缀） ====================
@st.cache_data(ttl=1800, show_spinner=False)
def fetch_yahoo_ohlcv(symbol: str, range_str: str, interval: str = "1d"):
    # A股自动加后缀
    if len(symbol) == 6 and symbol.isdigit():
        if symbol.startswith(('6', '9')):
            yahoo_symbol = f"{symbol}.SS"
        else:
            yahoo_symbol = f"{symbol}.SZ"
    else:
        yahoo_symbol = symbol.upper()

    try:
        time.sleep(random.uniform(0.15, 0.45))
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
    is_low_liquidity = avg_daily_dollar_vol_recent < 20000000  # A股阈值调低到2000万人民币
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

# ==================== 扫描范围 ====================
tickers_to_scan = load_a_share_top500_by_amount()
st.write(f"扫描范围：A股最近交易日成交额前500（当前加载 {len(tickers_to_scan)} 只，动态更新）")

mode = st.selectbox("回测周期", list(BACKTEST_CONFIG.keys()), index=2)
sort_by = st.selectbox("结果排序方式", ["PF7 (盈利因子)", "7日概率"], index=0)

# ==================== 参数变更处理 ====================
tickers_set = set(tickers_to_scan)
total = len(tickers_to_scan)

if 'prev_mode' not in st.session_state:
    st.session_state.prev_mode = mode

if st.session_state.prev_mode != mode:
    st.session_state.high_prob = []
    st.session_state.scanned_symbols = set()
    st.session_state.fully_scanned = False
    st.info("🔄 回测周期已变更，已重置进度，请重新扫描")
    st.session_state.prev_mode = mode
    st.rerun()

# session_state 初始化
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

# ==================== 进度条 ====================
progress_bar = st.progress(0)
status_text = st.empty()

current_completed = len(st.session_state.scanned_symbols.intersection(tickers_set))
progress_val = min(1.0, max(0.0, current_completed / total)) if total > 0 else 0.0
progress_bar.progress(progress_val)

# ==================== 显示结果 ====================
if st.session_state.high_prob:
    df_all = pd.DataFrame([x for x in st.session_state.high_prob if x is not None and x["symbol"] in tickers_set])
    
    if not df_all.empty:
        df_all['price'] = df_all['price'].round(2)
        df_all['change'] = df_all['change'].apply(lambda x: f"{x:+.2f}%")
        df_all['prob7_fmt'] = (df_all['prob7'] * 100).round(1).map("{:.1f}%".format)
        df_all['pf7'] = df_all['pf7'].round(2)
        
        if sort_by == "PF7 (盈利因子)":
            df_all = df_all.sort_values("pf7", ascending=False)
        else:
            df_all = df_all.sort_values("prob7", ascending=False)
        
        st.subheader(f"优质A股（共 {len(df_all)} 只）")
        for _, row in df_all.iterrows():
            details = row['sig_details']
            detail_str = " | ".join([f"{k}: {'是' if v else '否'}" for k,v in details.items()])
            liquidity_warning = " **⚠️ 低流动性 - 滑点风险高**" if row['is_low_liquidity'] else ""
            st.markdown(f"**{row['display_symbol']}** - 价格: ¥{row['price']:.2f} ({row['change']}) - 得分: {row['score']}/5 - {detail_str} - **7日概率: {row['prob7_fmt']} | PF7: {row['pf7']}**{liquidity_warning}")

if not st.session_state.high_prob:
    st.info("尚未扫描出结果，请点击「开始扫描」")

st.info(f"当前范围总标的: {total} | 已完成: {current_completed} | 累计有结果: {len(st.session_state.high_prob)} | 失败/跳过: {st.session_state.failed_count}")

# ==================== 扫描逻辑 ====================
if st.button("🚀 开始/继续全量扫描（自动持续运行）"):
    st.session_state.scanning = True

if st.session_state.scanning and current_completed < total:
    with st.spinner("扫描进行中（每100只自动刷新页面）..."):
        batch_size = 100
        processed_in_this_run = 0
        
        remaining_tickers = [sym for sym in tickers_to_scan if sym not in st.session_state.scanned_symbols]
        
        for sym in remaining_tickers:
            if processed_in_this_run >= batch_size:
                break
            
            current_progress = current_completed + processed_in_this_run
            progress_val = min(1.0, current_progress / total)
            status_text.text(f"正在计算 {sym} ({current_progress + 1}/{total})")
            progress_bar.progress(progress_val)
            
            try:
                metrics = compute_stock_metrics(sym, mode)
                if metrics is not None:
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
        
        # 刷新后重新计算进度
        new_completed = len(st.session_state.scanned_symbols.intersection(tickers_set))
        progress_bar.progress(min(1.0, new_completed / total))
        
        if new_completed >= total:
            st.session_state.fully_scanned = True
            st.session_state.scanning = False
            st.success("A股前500扫描完成！")
        
        st.rerun()

if current_completed >= total:
    st.success("已完成A股前500全扫描！结果已全部更新")

st.caption("2026年1月A股专用版 | 成交额前500动态加载 | 直接复制运行")


