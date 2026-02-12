import streamlit as st
import pandas as pd
import numpy as np
import pandas_ta as ta
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

def calculate_ut_bot(df, sensitivity, atr_period):
    if df.empty or len(df) < 50: return pd.DataFrame()
    df.columns = [str(c).capitalize() for c in df.columns]
    df['atr'] = ta.atr(df['High'], df['Low'], df['Close'], length=atr_period)
    df = df.dropna(subset=['atr']).copy()
    n_loss = sensitivity * df['atr']
    src, trail_stop = df['Close'], np.zeros(len(df))
    for i in range(1, len(df)):
        p = trail_stop[i-1]
        if src.iloc[i] > p and src.iloc[i-1] > p: trail_stop[i] = max(p, src.iloc[i] - n_loss.iloc[i])
        elif src.iloc[i] < p and src.iloc[i-1] < p: trail_stop[i] = min(p, src.iloc[i] + n_loss.iloc[i])
        else: trail_stop[i] = src.iloc[i] - n_loss.iloc[i] if src.iloc[i] > p else src.iloc[i] + n_loss.iloc[i]
    df['ts'] = trail_stop
    df['pos'] = np.where(df['Close'] > df['ts'], "BUY", "SELL")
    df['sig_change'] = (df['pos'] != df['pos'].shift(1))
    return df

# ==================== 3. 主程序 ====================
st.set_page_config(page_title="UT Bot 多重看板+分列日志版", layout="wide")

# 初始化日志与缓存
if "alert_logs" not in st.session_state:
    st.session_state.alert_logs = load_logs()
if "sent_cache" not in st.session_state:
    st.session_state.sent_cache = {f"{l['资产']}_{l['类型']}_{l['时间'][:16]}" for l in st.session_state.alert_logs if '类型' in l}

ex = ccxt.okx({'enableRateLimit': True})
sens = st.sidebar.slider("敏感度", 0.1, 5.0, 1.2)
atrp = st.sidebar.slider("ATR周期", 1, 30, 10)

# 新增侧边栏配置止盈止损比率
tp_ratio = st.sidebar.slider("止盈比率 (%)", 0.1, 10.0, 2.0) / 100  # e.g., 2% = 0.02
sl_ratio = st.sidebar.slider("止损比率 (%)", 0.1, 10.0, 1.0) / 100  # e.g., 1% = 0.01

# 新增指标参数
rsi_period = st.sidebar.slider("RSI周期", 5, 30, 14)
rsi_buy_thresh = st.sidebar.slider("RSI BUY阈值 (>)", 30, 70, 50)
rsi_sell_thresh = st.sidebar.slider("RSI SELL阈值 (<)", 30, 70, 50)
macd_fast = st.sidebar.slider("MACD快线", 5, 20, 12)
macd_slow = st.sidebar.slider("MACD慢线", 20, 40, 26)
macd_signal = st.sidebar.slider("MACD信号线", 5, 15, 9)
atr_mult_thresh = st.sidebar.slider("ATR波动阈值倍数 (> sma(ATR))", 0.5, 2.0, 1.0)  # ATR > sma(ATR, atrp) * mult
obv_sma_period = st.sidebar.slider("OBV SMA周期", 5, 50, 20)

# 抓取数据
all_data = {}
for base in CRYPTO_LIST:
    sym = f"{base}-USDT-SWAP" if base in CONTRACTS else f"{base}/USDT"
    all_data[base] = {}
    for tf in DISPLAY_INTERVALS:
        try:
            bars = ex.fetch_ohlcv(sym, timeframe=tf, limit=100)
            df = pd.DataFrame(bars, columns=['ts','open','high','low','close','volume'])
            df.set_index(pd.to_datetime(df['ts'], unit='ms').dt.tz_localize('UTC'), inplace=True)
            df = calculate_ut_bot(df, sens, atrp)
            if not df.empty:
                # 计算额外指标
                df['rsi'] = ta.rsi(df['Close'], length=rsi_period)
                macd = ta.macd(df['Close'], fast=macd_fast, slow=macd_slow, signal=macd_signal)
                df['macd'] = macd['MACD_12_26_9']  # 假设默认列名
                df['macd_signal'] = macd['MACDs_12_26_9']
                df['macd_hist'] = macd['MACDh_12_26_9']
                df['obv'] = ta.obv(df['Close'], df['Volume'])
                df['obv_sma'] = ta.sma(df['obv'], length=obv_sma_period)
                df['atr_sma'] = ta.sma(df['atr'], length=atrp)
            all_data[base][tf] = df
        except: all_data[base][tf] = pd.DataFrame()

# 核心：生成看板行 + 信号逻辑
rows = []
now_str = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')

# 初始化开仓位置字典（session_state持久化模拟持仓）
if "positions" not in st.session_state:
    st.session_state.positions = {}  # {base: {'方向': 'BUY/SELL', '入场价': price, '入场时间': now_str, '类型': 'Group1/大周期_1h 等'}}

for base in CRYPTO_LIST:
    p_15m = all_data[base].get("15m", pd.DataFrame())
    price_now = p_15m.iloc[-1]['Close'] if not p_15m.empty else "N/A"
    
    # --- 1. 构造顶部的看板行 (格局不变) ---
    row = {"资产": base, "实时价格": f"<b>{price_now}</b>"}
    for tf in DISPLAY_INTERVALS:
        df = all_data[base].get(tf, pd.DataFrame())
        if df.empty: row[tf] = "-"; continue
        curr = df.iloc[-1]
        color = "#00ff00" if curr['pos'] == "BUY" else "#ff0000"
        row[tf] = f"<div style='color:{color};font-weight:bold;'>{curr['pos']}</div><div style='font-size:0.75em;color:#888;'>Stop:{curr['ts']:.2f}</div>"

    # --- 2. 信号触发逻辑 ---
    # A. 检查两组共振 (共振才发)
    for g_name, g_tfs in RESONANCE_GROUPS.items():
        states = [all_data[base][tf].iloc[-1]['pos'] for tf in g_tfs if not all_data[base][tf].empty]
        is_res = len(states) == 3 and len(set(states)) == 1
        if is_res:
            # 加强过滤: 检查三个周期的指标一致
            filter_pass = True
            for tf in g_tfs:
                df = all_data[base][tf]
                if df.empty: filter_pass = False; break
                curr = df.iloc[-1]
                direction = states[0]
                
                # RSI 过滤
                rsi_ok = (curr['rsi'] > rsi_buy_thresh if direction == "BUY" else curr['rsi'] < rsi_sell_thresh)
                
                # MACD 过滤: MACD > signal 为 BUY, < 为 SELL
                macd_ok = (curr['macd'] > curr['macd_signal'] if direction == "BUY" else curr['macd'] < curr['macd_signal'])
                
                # OBV 过滤: OBV > SMA 为 BUY, < 为 SELL
                obv_ok = (curr['obv'] > curr['obv_sma'] if direction == "BUY" else curr['obv'] < curr['obv_sma'])
                
                # ATR 过滤: 当前 ATR > SMA(ATR) * mult (高波动确认)
                atr_ok = curr['atr'] > curr['atr_sma'] * atr_mult_thresh
                
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
                    # 记录开仓
                    st.session_state.positions[base] = {'方向': states[0], '入场价': price_now, '入场时间': now_str, '类型': g_name}

    # B. 检查大周期 (1h+出信号即发)
    for tf in MAJOR_LEVELS:
        df = all_data[base].get(tf, pd.DataFrame())
        if not df.empty and df.iloc[-1]['sig_change']:
            curr = df.iloc[-1]
            direction = curr['pos']
            
            # 加强过滤: 单周期指标检查
            rsi_ok = (curr['rsi'] > rsi_buy_thresh if direction == "BUY" else curr['rsi'] < rsi_sell_thresh)
            macd_ok = (curr['macd'] > curr['macd_signal'] if direction == "BUY" else curr['macd'] < curr['macd_signal'])
            obv_ok = (curr['obv'] > curr['obv_sma'] if direction == "BUY" else curr['obv'] < curr['obv_sma'])
            atr_ok = curr['atr'] > curr['atr_sma'] * atr_mult_thresh
            
            if rsi_ok and macd_ok and obv_ok and atr_ok:
                cache_key = f"{base}_{tf}_{now_str[:16]}"
                if cache_key not in st.session_state.sent_cache:
                    log_entry = {"时间": now_str, "资产": base, "类型": f"大周期_{tf}", "方向": direction, "价格": price_now}
                    st.session_state.alert_logs.insert(0, log_entry)
                    save_log_to_disk(log_entry)
                    send_wx(f"📢大周期报警({tf})", f"{base} {direction} @{price_now}")
                    st.session_state.sent_cache.add(cache_key)
                    # 记录开仓
                    st.session_state.positions[base] = {'方向': direction, '入场价': price_now, '入场时间': now_str, '类型': f"大周期_{tf}"}
    
    rows.append(row)

    # --- 新增: 止盈止损监控（只在日志系统内操作） ---
    if isinstance(price_now, (int, float)):  # 确保有有效价格
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
                    del st.session_state.positions[base]  # 关闭位置
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
                    del st.session_state.positions[base]  # 关闭位置

# ==================== 4. 渲染界面 ====================
st.markdown("<h3 style='text-align:center;'>🚀 UT Bot 多重过滤共振监控</h3>", unsafe_allow_html=True)

# 渲染顶部看板 (格局保持)
st.write(pd.DataFrame(rows).to_html(escape=False, index=False), unsafe_allow_html=True)

st.divider()
st.subheader("📜 分列历史日志 (左:Group1 | 中:Group2 | 右:大周期单发)")

if st.session_state.alert_logs:
    df_logs = pd.DataFrame(st.session_state.alert_logs)
    
    # --- 重点：三列日志展示 ---
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
time.sleep(300)
st.rerun()
