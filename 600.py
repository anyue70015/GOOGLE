import streamlit as st
import pandas as pd
import numpy as np
import ccxt
import requests
import os
from datetime import datetime, timedelta
import pytz
import time

# ==================== 1. 核心配置 ====================
APP_TOKEN = "AT_3H9akFZPvOE98cPrDydWmKM4ndgT3bVH0"
USER_UID = "UID_wfbEjBobfoHNLmprN3Pi5nwWb4oM0"
LOG_FILE = "trade_resonance_master.csv"  # 永久保存文件名

# 品种列表
CRYPTO_LIST = ["BTC", "ETH", "SOL", "SUI", "RENDER", "DOGE", "XRP", "HYPE", "AAVE", "TAO", "XAG", "XAU"]
CONTRACTS = {"TAO", "XAG", "XAU"} 

# 界面显示的全部周期
DISPLAY_INTERVALS = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]

# 触发微信推送的共振组
RESONANCE_GROUPS = {
    "Group1_短线(5-15-60)": ["5m", "15m", "1h"],
    "Group2_趋势(15-60-240)": ["15m", "1h", "4h"]
}
# 大周期单独推送列表（1h及以上出信号就发）
MAJOR_LEVELS = ["1h", "4h", "1d"]

BEIJING_TZ = pytz.timezone('Asia/Shanghai')

# ==================== 2. 功能函数 ====================

def load_logs():
    if os.path.exists(LOG_FILE):
        try: return pd.read_csv(LOG_FILE).to_dict('records')
        except: return []
    return []

def save_log_to_disk(entry):
    df = pd.DataFrame([entry])
    header = not os.path.exists(LOG_FILE)
    df.to_csv(LOG_FILE, mode='a', index=False, header=header, encoding='utf-8-sig')

def send_wx(title, body):
    try:
        payload = {"appToken": APP_TOKEN, "content": f"{title}\n{body}", "uids": [USER_UID]}
        requests.post("https://wxpusher.zjiecode.com/api/send/message", json=payload, timeout=5)
    except: pass

def rma(series, length):
    """Wilder 平滑 (RMA)"""
    alpha = 1.0 / length
    rma_series = series.copy()
    rma_series.iloc[:length] = np.nan
    rma_series.iloc[length-1] = series.iloc[:length].mean()
    for i in range(length, len(series)):
        rma_series.iloc[i] = alpha * series.iloc[i] + (1 - alpha) * rma_series.iloc[i-1]
    return rma_series

def calculate_ut_bot(df, sensitivity, atr_period):
    if df.empty or len(df) < 50: return pd.DataFrame()
    df.columns = [str(c).lower() for c in df.columns]  # 改为小写统一
    # 手写 TR 和 ATR (使用 RMA 平滑)
    tr = np.maximum(df['high'] - df['low'],
                    np.maximum(abs(df['high'] - df['close'].shift()),
                               abs(df['low'] - df['close'].shift())))
    df['atr'] = rma(tr, atr_period)
    df = df.dropna(subset=['atr']).copy()
    n_loss = sensitivity * df['atr']
    src = df['close']
    trail_stop = np.full(len(df), np.nan)
    trail_stop[0] = src[0] - n_loss[0]  # 初始化第一个 trail_stop 为 close - n_loss (假设初始 BUY 方向)
    for i in range(1, len(df)):
        p = trail_stop[i-1]
        if src[i] > p and src[i-1] > p: 
            trail_stop[i] = max(p, src[i] - n_loss[i])
        elif src[i] < p and src[i-1] < p: 
            trail_stop[i] = min(p, src[i] + n_loss[i])
        else: 
            trail_stop[i] = src[i] - n_loss[i] if src[i] > src[i-1] else src[i] + n_loss[i]  # 调整翻转逻辑
    df['ts'] = trail_stop
    df['pos'] = np.where(df['close'] > df['ts'], "BUY", "SELL")
    # 改进 sig_change 计算
    if len(df) >= 2:
        df['sig_change'] = False
        df['sig_change'].iloc[1:] = df['pos'].iloc[1:] != df['pos'].iloc[:-1]
    else:
        df['sig_change'] = False
    return df

def rsi_manual(close, period=14):
    delta = close.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def macd_manual(close, fast=12, slow=26, signal=9):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist

def obv_manual(close, volume):
    direction = np.sign(close.diff())
    obv = (direction * volume).fillna(0).cumsum()
    return obv

# ==================== 3. 主程序 ====================
st.set_page_config(page_title="UT Bot 多重看板+分列日志版", layout="wide")

# 初始化日志与缓存
if "alert_logs" not in st.session_state:
    st.session_state.alert_logs = load_logs()
if "sent_cache" not in st.session_state:
    st.session_state.sent_cache = {f"{l['资产']}_{l['类型']}_{l['时间'][:16]}" for l in st.session_state.alert_logs if '类型' in l}

ex = ccxt.okx({'enableRateLimit': True, 'defaultType': 'swap'})  # 指定 swap
sens = st.sidebar.slider("敏感度", 0.1, 5.0, 1.0)  # 默认调低到1.0，更容易触发
atrp = st.sidebar.slider("ATR周期", 1, 30, 10)

# 新增侧边栏配置止盈止损比率
tp_ratio = st.sidebar.slider("止盈比率 (%)", 0.1, 10.0, 2.0) / 100
sl_ratio = st.sidebar.slider("止损比率 (%)", 0.1, 10.0, 1.0) / 100

# 新增指标参数
rsi_period = st.sidebar.slider("RSI周期", 5, 30, 14)
rsi_buy_thresh = st.sidebar.slider("RSI BUY阈值 (>)", 30, 70, 50)
rsi_sell_thresh = st.sidebar.slider("RSI SELL阈值 (<)", 30, 70, 50)
macd_fast = st.sidebar.slider("MACD快线", 5, 20, 12)
macd_slow = st.sidebar.slider("MACD慢线", 20, 40, 26)
macd_signal = st.sidebar.slider("MACD信号线", 5, 15, 9)
atr_mult_thresh = st.sidebar.slider("ATR波动阈值倍数 (> sma(ATR))", 0.5, 2.0, 0.8)  # 默认放宽到0.8
obv_sma_period = st.sidebar.slider("OBV SMA周期", 5, 50, 20)

# 抓取数据
all_data = {}
for base in CRYPTO_LIST:
    sym = f"{base}/USDT" if base not in CONTRACTS else f"{base}-USDT-SWAP"  # 修正
    all_data[base] = {}
    for tf in DISPLAY_INTERVALS:
        try:
            bars = ex.fetch_ohlcv(sym, timeframe=tf, limit=200)  # 增加到200
            df = pd.DataFrame(bars, columns=['ts','open','high','low','close','volume'])
            df.set_index(pd.to_datetime(df['ts'], unit='ms').dt.tz_localize('UTC'), inplace=True)
            df = calculate_ut_bot(df, sens, atrp)
            if not df.empty:
                # 计算额外指标
                df['rsi'] = rsi_manual(df['close'], rsi_period)
                macd_line, macd_sig, macd_hist = macd_manual(df['close'], macd_fast, macd_slow, macd_signal)
                df['macd'] = macd_line
                df['macd_signal'] = macd_sig
                df['macd_hist'] = macd_hist
                df['obv'] = obv_manual(df['close'], df['volume'])
                df['obv_sma'] = df['obv'].rolling(obv_sma_period).mean()
                df['atr_sma'] = df['atr'].rolling(atrp).mean()
            all_data[base][tf] = df
            # DEBUG: 最后时间
            if not df.empty:
                st.sidebar.write(f"{base} {tf} 最后时间: {df.index[-1]}")
        except Exception as e:
            st.sidebar.error(f"{base} {tf} 抓取失败: {e}")
            all_data[base][tf] = pd.DataFrame()

# 核心：生成看板行 + 信号逻辑
rows = []
now_str = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')

# 初始化开仓位置字典
if "positions" not in st.session_state:
    st.session_state.positions = {}

for base in CRYPTO_LIST:
    p_15m = all_data[base].get("15m", pd.DataFrame())
    price_now = p_15m.iloc[-1]['close'] if not p_15m.empty else "N/A"
    
    # 构造顶部的看板行
    row = {"资产": base, "实时价格": f"<b>{price_now}</b>"}
    for tf in DISPLAY_INTERVALS:
        df = all_data[base].get(tf, pd.DataFrame())
        if df.empty: row[tf] = "-"; continue
        curr = df.iloc[-1]
        color = "#00ff00" if curr['pos'] == "BUY" else "#ff0000"
        row[tf] = f"<div style='color:{color};font-weight:bold;'>{curr['pos']}</div><div style='font-size:0.75em;color:#888;'>Stop:{curr['ts']:.2f}</div>"

    # 信号触发逻辑 A. 共振组
    for g_name, g_tfs in RESONANCE_GROUPS.items():
        states = [all_data[base][tf].iloc[-1]['pos'] for tf in g_tfs if not all_data[base][tf].empty]
        is_res = len(states) == 3 and len(set(states)) == 1
        if is_res:
            filter_pass = True
            for tf in g_tfs:
                df = all_data[base][tf]
                if df.empty: filter_pass = False; break
                curr = df.iloc[-1]
                direction = states[0]
                
                rsi_ok = (curr['rsi'] > rsi_buy_thresh if direction == "BUY" else curr['rsi'] < rsi_sell_thresh)
                macd_ok = (curr['macd'] > curr['macd_signal'] if direction == "BUY" else curr['macd'] < curr['macd_signal'])
                obv_ok = (curr['obv'] > curr['obv_sma'] if direction == "BUY" else curr['obv'] < curr['obv_sma'])
                atr_ok = curr['atr'] > curr['atr_sma'] * atr_mult_thresh
                
                # DEBUG: 输出过滤
                st.sidebar.write(f"DEBUG {base} {tf} {direction}: RSI={rsi_ok}, MACD={macd_ok}, OBV={obv_ok}, ATR={atr_ok}")
                
                if not (rsi_ok and macd_ok and obv_ok and atr_ok):
                    filter_pass = False
                    break
            
            if filter_pass and any([all_data[base][tf].iloc[-1]['sig_change'] for tf in g_tfs if not all_data[base][tf].empty]):
                cache_key = f"{base}_{g_name}_{now_str[:16]}"
                if cache_key not in st.session_state.sent_cache:
                    log_entry = {"时间": now_str, "资产": base, "类型": g_name, "方向": states[0], "价格": price_now}
                    st.session_state.alert_logs.insert(0, log_entry)
                    save_log_to_disk(log_entry)
                    send_wx(f"🔗共振({g_name})", f"{base} {states[0]} @{price_now}")
                    st.session_state.sent_cache.add(cache_key)
                    st.session_state.positions[base] = {'方向': states[0], '入场价': price_now, '入场时间': now_str, '类型': g_name}

    # B. 大周期
    for tf in MAJOR_LEVELS:
        df = all_data[base].get(tf, pd.DataFrame())
        if not df.empty:
            total_changes = df['sig_change'].sum()
            st.sidebar.write(f"DEBUG: {base} {tf} total_changes={total_changes}")
            curr = df.iloc[-1]
            # DEBUG sig_change
            if len(df) >= 2:
                prev = df.iloc[-2]
                prev_pos = prev['pos']
                curr_pos = curr['pos']
                sig_change = curr['sig_change']
                diff = curr['close'] - curr['ts']
                st.sidebar.write(f"DEBUG: {base} {tf} sig_change={sig_change} (当前:{curr_pos} ← 前:{prev_pos}), Diff={diff:.2f}")
                st.sidebar.write(f"DEBUG {base} {tf} | 前一根 pos: {prev_pos}, ts:{prev['ts']:.2f}, close:{prev['close']:.2f} | 最新 pos: {curr_pos}, ts:{curr['ts']:.2f}, close:{curr['close']:.2f}")
            else:
                st.sidebar.write(f"DEBUG: {base} {tf} 数据不足2根")
            
            if sig_change:
                direction = curr['pos']
                rsi_ok = (curr['rsi'] > rsi_buy_thresh if direction == "BUY" else curr['rsi'] < rsi_sell_thresh)
                macd_ok = (curr['macd'] > curr['macd_signal'] if direction == "BUY" else curr['macd'] < curr['macd_signal'])
                obv_ok = (curr['obv'] > curr['obv_sma'] if direction == "BUY" else curr['obv'] < curr['obv_sma'])
                atr_ok = curr['atr'] > curr['atr_sma'] * atr_mult_thresh
                
                # DEBUG 过滤
                st.sidebar.write(f"DEBUG {base} {tf} {direction}: RSI={rsi_ok}, MACD={macd_ok}, OBV={obv_ok}, ATR={atr_ok}")
                
                if rsi_ok and macd_ok and obv_ok and atr_ok:
                    cache_key = f"{base}_{tf}_{now_str[:16]}"
                    if cache_key not in st.session_state.sent_cache:
                        log_entry = {"时间": now_str, "资产": base, "类型": f"大周期_{tf}", "方向": direction, "价格": price_now}
                        st.session_state.alert_logs.insert(0, log_entry)
                        save_log_to_disk(log_entry)
                        send_wx(f"📢大周期报警({tf})", f"{base} {direction} @{price_now}")
                        st.session_state.sent_cache.add(cache_key)
                        st.session_state.positions[base] = {'方向': direction, '入场价': price_now, '入场时间': now_str, '类型': f"大周期_{tf}"}
    
    rows.append(row)

    # 止盈止损监控
    if isinstance(price_now, (int, float)):
        if base in st.session_state.positions:
            pos = st.session_state.positions[base]
            entry_price = pos['入场价']
            direction = pos['方向']
            if direction == "BUY":
                tp_price = entry_price * (1 + tp_ratio)
                sl_price = entry_price * (1 - sl_ratio)
                if price_now >= tp_price or price_now <= sl_price:
                    exit_type = "止盈" if price_now >= tp_price else "止损"
                    pnl = (price_now - entry_price) / entry_price * 100
                    log_entry = {"时间": now_str, "资产": base, "类型": f"{pos['类型']}_平仓_{exit_type}", "方向": direction, "价格": price_now, "盈亏(%)": f"{pnl:.2f}"}
                    st.session_state.alert_logs.insert(0, log_entry)
                    save_log_to_disk(log_entry)
                    send_wx(f"🚨{exit_type}平仓({pos['类型']})", f"{base} {direction} 平仓 @{price_now} 盈亏: {pnl:.2f}%")
                    del st.session_state.positions[base]
            elif direction == "SELL":
                tp_price = entry_price * (1 - tp_ratio)
                sl_price = entry_price * (1 + sl_ratio)
                if price_now <= tp_price or price_now >= sl_price:
                    exit_type = "止盈" if price_now <= tp_price else "止损"
                    pnl = (entry_price - price_now) / entry_price * 100
                    log_entry = {"时间": now_str, "资产": base, "类型": f"{pos['类型']}_平仓_{exit_type}", "方向": direction, "价格": price_now, "盈亏(%)": f"{pnl:.2f}"}
                    st.session_state.alert_logs.insert(0, log_entry)
                    save_log_to_disk(log_entry)
                    send_wx(f"🚨{exit_type}平仓({pos['类型']})", f"{base} {direction} 平仓 @{price_now} 盈亏: {pnl:.2f}%")
                    del st.session_state.positions[base]

# ==================== 4. 渲染界面 ====================
st.markdown("<h3 style='text-align:center;'>🚀 UT Bot 多重过滤共振监控</h3>", unsafe_allow_html=True)

st.write(pd.DataFrame(rows).to_html(escape=False, index=False), unsafe_allow_html=True)

st.divider()
st.subheader("📜 分列历史日志 (左:Group1 | 中:Group2 | 右:大周期单发)")

if st.session_state.alert_logs:
    df_logs = pd.DataFrame(st.session_state.alert_logs)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("##### 🟢 Group1 (5-15-60)")
        g1_df = df_logs[df_logs["类型"].str.contains("Group1")]
        g1_open = g1_df[~g1_df["类型"].str.contains("平仓")]
        g1_close = g1_df[g1_df["类型"].str.contains("平仓")]
        
        if not g1_open.empty:
            st.markdown("**开仓记录**")
            st.dataframe(g1_open[["时间", "资产", "方向", "价格"]], use_container_width=True, hide_index=True)
        
        if not g1_close.empty:
            st.markdown("**平仓记录**")
            st.dataframe(g1_close[["时间", "资产", "方向", "价格", "盈亏(%)"]], use_container_width=True, hide_index=True)
        
        if not g1_df.empty:
            st.download_button("下载 G1 全记录 CSV", g1_df.to_csv(index=False).encode('utf-8-sig'), "G1_full.csv", key="dl_g1")

    with col2:
        st.markdown("##### 🔵 Group2 (15-60-240)")
        g2_df = df_logs[df_logs["类型"].str.contains("Group2")]
        g2_open = g2_df[~g2_df["类型"].str.contains("平仓")]
        g2_close = g2_df[g2_df["类型"].str.contains("平仓")]
        
        if not g2_open.empty:
            st.markdown("**开仓记录**")
            st.dataframe(g2_open[["时间", "资产", "方向", "价格"]], use_container_width=True, hide_index=True)
        
        if not g2_close.empty:
            st.markdown("**平仓记录**")
            st.dataframe(g2_close[["时间", "资产", "方向", "价格", "盈亏(%)"]], use_container_width=True, hide_index=True)
        
        if not g2_df.empty:
            st.download_button("下载 G2 全记录 CSV", g2_df.to_csv(index=False).encode('utf-8-sig'), "G2_full.csv", key="dl_g2")

    with col3:
        st.markdown("##### 🟠 大周期单周期 (1h+)")
        major_df = df_logs[df_logs["类型"].str.contains("大周期")]
        major_open = major_df[~major_df["类型"].str.contains("平仓")]
        major_close = major_df[major_df["类型"].str.contains("平仓")]
        
        if not major_open.empty:
            st.markdown("**开仓记录**")
            st.dataframe(major_open[["时间", "资产", "类型", "方向", "价格"]], use_container_width=True, hide_index=True)
        
        if not major_close.empty:
            st.markdown("**平仓记录**")
            st.dataframe(major_close[["时间", "资产", "类型", "方向", "价格", "盈亏(%)"]], use_container_width=True, hide_index=True)
        
        if not major_df.empty:
            st.download_button("下载大周期 全记录 CSV", major_df.to_csv(index=False).encode('utf-8-sig'), "Major_full.csv", key="dl_major")
else:
    st.info("监控运行中，暂无触发信号...")

st.sidebar.caption(f"最后刷新: {now_str}")
time.sleep(120)  # 缩短到120秒
st.rerun()
