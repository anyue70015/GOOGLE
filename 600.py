import streamlit as st
import pandas as pd
import numpy as np
import pandas_ta as ta
import ccxt
import requests
from datetime import datetime, timedelta
import pytz
import time

# ==================== 1. 核心配置 ====================
APP_TOKEN = "AT_3H9akFZPvOE98cPrDydWmKM4ndgT3bVH"
USER_UID = "UID_wfbEjBobfoHNLmprN3Pi5nwWb4oM"

# TAO, XAG, XAU 是合约，其余是现货（基于您的 Saved Info）
CRYPTO_LIST = ["BTC", "ETH", "SOL", "SUI", "RENDER", "DOGE", "XRP", "HYPE", "AAVE", "TAO", "XAG", "XAU"]
CONTRACTS = {"TAO", "XAG", "XAU"}
INTERVALS = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]
ALERT_INTERVALS = ["15m", "30m", "1h"]

# 定义两个三周期共振组
RESONANCE_GROUPS = {
    "group1": ["4h", "1h", "15m"],  # 组1: 长线/目标15万
    "group2": ["1h", "15m", "5m"]   # 组2: 日内交易
}

BEIJING_TZ = pytz.timezone('Asia/Shanghai')

# ==================== 2. 逻辑函数 ====================

def send_wx_pusher(title, body):
    if not APP_TOKEN or not USER_UID: return
    try:
        payload = {"appToken": APP_TOKEN, "content": f"{title}\n{body}", "uids": [USER_UID]}
        requests.post("https://wxpusher.zjiecode.com/api/send/message", json=payload, timeout=5)
    except: pass

def calculate_indicators(df, sensitivity, atr_period):
    if df.empty or len(df) < 50: return pd.DataFrame()
    df.columns = [str(c).capitalize() for c in df.columns]
    
    df['atr'] = ta.atr(df['High'], df['Low'], df['Close'], length=atr_period)
    df = df.dropna(subset=['atr']).copy()
    n_loss = sensitivity * df['atr']
    src = df['Close']
    trail_stop = np.zeros(len(df))
    trail_stop[0] = src.iloc[0] - n_loss.iloc[0]
    
    for i in range(1, len(df)):
        p = trail_stop[i-1]
        if src.iloc[i] > p and src.iloc[i-1] > p: trail_stop[i] = max(p, src.iloc[i] - n_loss.iloc[i])
        elif src.iloc[i] < p and src.iloc[i-1] < p: trail_stop[i] = min(p, src.iloc[i] + n_loss.iloc[i])
        else: trail_stop[i] = src.iloc[i] - n_loss.iloc[i] if src.iloc[i] > p else src.iloc[i] + n_loss.iloc[i]
    
    df['trail_stop'] = trail_stop
    df['buy_signal'] = (df['Close'] > df['trail_stop']) & (df['Close'].shift(1) <= df['trail_stop'].shift(1))
    df['sell_signal'] = (df['Close'] < df['trail_stop']) & (df['Close'].shift(1) >= df['trail_stop'].shift(1))
    
    df['obv'] = ta.obv(df['Close'], df['Volume'])
    df['vol_avg'] = df['Volume'].shift(1).rolling(window=5).mean()
    return df

def calculate_win_rate(log_df, action_col, profit_col):
    if log_df.empty or action_col not in log_df.columns:
        return {"win_rate": "0.0%", "total_trades": 0, "wins": 0, "losses": 0}
    
    closed_mask = log_df[action_col].astype(str).str.contains('平', na=False)
    closed_trades = log_df[closed_mask].copy()
    
    if closed_trades.empty:
        return {"win_rate": "0.0%", "total_trades": 0, "wins": 0, "losses": 0}
    
    def safe_float(x):
        try: return float(str(x).rstrip('%'))
        except: return 0.0
    
    closed_trades['profit_val'] = closed_trades[profit_col].apply(safe_float)
    wins = len(closed_trades[closed_trades['profit_val'] > 0])
    total = len(closed_trades)
    win_rate = (wins / total * 100) if total > 0 else 0.0
    return {"win_rate": f"{win_rate:.1f}%", "total_trades": total, "wins": wins, "losses": total-wins}

# ==================== 3. 主程序 ====================
st.set_page_config(page_title="UT Bot Pro 最终完整版", layout="wide")

@st.cache_resource
def get_global_state():
    return {"sent_cache": {}, "alert_logs": [], "positions": {}}

state = get_global_state()
ex = ccxt.okx({'enableRateLimit': True})

# 侧边栏
selected_cryptos = st.sidebar.multiselect("品种选择", CRYPTO_LIST, default=CRYPTO_LIST)
sens = st.sidebar.slider("敏感度", 0.1, 5.0, 1.0)
atrp = st.sidebar.slider("ATR周期", 1, 30, 10)
refresh_sec = st.sidebar.selectbox("自动刷新(秒)", [60, 300, 600], index=1)

# 数据获取
all_data = {}
for base in selected_cryptos:
    sym = f"{base}-USDT-SWAP" if base in CONTRACTS else f"{base}/USDT"
    all_data[base] = {}
    for tf in INTERVALS:
        try:
            bars = ex.fetch_ohlcv(sym, timeframe=tf, limit=100)
            df = pd.DataFrame(bars, columns=['ts','open','high','low','close','volume'])
            df['ts'] = pd.to_datetime(df['ts'], unit='ms').dt.tz_localize('UTC')
            df.set_index('ts', inplace=True)
            all_data[base][tf] = calculate_indicators(df, sens, atrp)
            time.sleep(0.1)
        except: all_data[base][tf] = pd.DataFrame()

# 构建看板行数据
rows = []
for base in selected_cryptos:
    # 获取最新价格
    p_df = all_data[base].get("15m", pd.DataFrame())
    price_now = p_df.iloc[-1]['Close'] if not p_df.empty else "N/A"
    row_data = {"资产": base, "实时价格": f"<b>{price_now}</b>"}
    
    for tf in INTERVALS:
        df = all_data[base].get(tf, pd.DataFrame())
        if df.empty: 
            row_data[tf] = "-"
            continue
        latest = df.iloc[-1]
        color = "#00ff00" if latest['Close'] > latest['trail_stop'] else "#ff0000"
        status = "BUY 🟢" if color == "#00ff00" else "SELL 🔴"
        row_data[tf] = f"<div style='color:{color};font-weight:bold;'>{status}</div><div style='font-size:0.7em;color:#888;'>止损:{latest['trail_stop']:.2f}</div>"

        # 推送与共振逻辑
        if tf in ALERT_INTERVALS and len(df) >= 2:
            prev, curr = df.iloc[-2], df.iloc[-1]
            signal = "BUY 🟢" if curr['buy_signal'] else "SELL 🔴" if curr['sell_signal'] else "NONE"
            
            if signal != "NONE":
                sig_time = df.index[-1].astimezone(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')
                cache_key = f"{base}_{tf}_{sig_time}"
                
                if cache_key not in state["sent_cache"]:
                    sync_tags, actions, profits = {}, {}, {}
                    for g_name, g_tfs in RESONANCE_GROUPS.items():
                        if tf in g_tfs:
                            statuses = ["BUY" if all_data[base][gt].iloc[-1]['Close'] > all_data[base][gt].iloc[-1]['trail_stop'] else "SELL" for gt in g_tfs if not all_data[base][gt].empty]
                            is_sync = len(statuses) == 3 and len(set(statuses)) == 1
                            sync_tags[g_name] = f"🔗共振 ({statuses[0]})" if is_sync else "⚠️无共振"
                            
                            # 简易持仓/平仓逻辑记录（省略复杂计算）
                            actions[g_name] = f"{signal}触发"
                            profits[g_name] = "-"
                    
                    log_entry = {"时间": sig_time, "资产": base, "周期": tf, "信号": signal, "价格": curr['Close']}
                    for g in RESONANCE_GROUPS:
                        log_entry[f"{g}_共振"] = sync_tags.get(g, "N/A")
                        log_entry[f"{g}_动作"] = actions.get(g, "观望")
                        log_entry[f"{g}_盈亏"] = profits.get(g, "-")
                    
                    state["alert_logs"].insert(0, log_entry)
                    send_wx_pusher(f"{base} {tf} {signal}", f"价格: {curr['Close']}\n共振: {list(sync_tags.values())}")
                    state["sent_cache"][cache_key] = True
    rows.append(row_data)

# ==================== 4. 渲染界面 ====================
st.markdown("<h3 style='text-align:center;'>🚀 UT Bot 多重过滤系统</h3>", unsafe_allow_html=True)
st.write(pd.DataFrame(rows).to_html(escape=False, index=False), unsafe_allow_html=True)

st.divider()
st.subheader("📜 推送日志（按币种折叠 & 独立下载）")

if state["alert_logs"]:
    log_df = pd.DataFrame(state["alert_logs"])
    log_df['时间_dt'] = pd.to_datetime(log_df['时间']).dt.tz_localize(BEIJING_TZ)
    recent_df = log_df[log_df['时间_dt'] >= (datetime.now(BEIJING_TZ) - timedelta(hours=24))].sort_values("时间_dt", ascending=False)
    
    # 顶部统计
    cols = st.columns(len(RESONANCE_GROUPS) + 1)
    cols[0].metric("24h信号数", len(recent_df))
    for i, g in enumerate(RESONANCE_GROUPS, 1):
        s = calculate_win_rate(recent_df, f"{g}_动作", f"{g}_盈亏")
        cols[i].metric(f"{g} 胜率", s['win_rate'])

    # 按币种折叠展示
    for asset in sorted(recent_df["资产"].unique()):
        asset_df = recent_df[recent_df["资产"] == asset]
        with st.expander(f"📈 {asset} (共 {len(asset_df)} 条)"):
            for period in sorted(asset_df["周期"].unique(), reverse=True):
                p_df = asset_df[asset_df["周期"] == period].copy()
                st.markdown(f"**📍 周期: {period}**")
                st.dataframe(p_df.drop(columns=['时间_dt']), use_container_width=True, hide_index=True)
                
                # 每一个周期一个下载按钮
                csv = p_df.to_csv(index=False).encode('utf-8-sig')
                st.download_button(f"📥 下载 {asset} {period}", csv, f"{asset}_{period}.csv", "text/csv", key=f"dl_{asset}_{period}_{time.time()}")
                st.write("")
else:
    st.info("等待信号中...")

time.sleep(refresh_sec)
st.rerun()
