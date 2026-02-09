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

CRYPTO_LIST = ["BTC", "ETH", "SOL", "SUI", "RENDER", "DOGE", "XRP", "HYPE", "AAVE", "TAO", "XAG", "XAU"]
CONTRACTS = {"TAO", "XAG", "XAU"}
INTERVALS = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]
ALERT_INTERVALS = ["15m", "30m", "1h"]

RESONANCE_MAP = {"15m": "1h", "30m": "4h", "1h": "4h"}
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
    trail_stop[0] = src.iloc[0] - n_loss.iloc[0]  # 初始化第一根，避免0值干扰
    
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

# ==================== 3. 主程序 ====================
st.set_page_config(page_title="UT Bot Pro 最终修正版", layout="wide")

if "last_update" not in st.session_state:
    st.session_state.last_update = time.time()

refresh_sec = 300 
time_passed = time.time() - st.session_state.last_update
if time_passed > refresh_sec:
    st.session_state.last_update = time.time()
    st.rerun()

st.sidebar.caption(f"🔄 刷新倒计时: {max(0, int(refresh_sec - time_passed))}s")

@st.cache_resource
def get_global_state():
    return {"sent_cache": {}, "alert_logs": [], "positions": {}}

state = get_global_state()
ex = ccxt.okx({'enableRateLimit': True})

selected_cryptos = st.sidebar.multiselect("品种选择", CRYPTO_LIST, default=CRYPTO_LIST)
sens = st.sidebar.slider("敏感度", 0.1, 5.0, 1.0)
atrp = st.sidebar.slider("ATR周期", 1, 30, 10)

# 抓取数据（保持你原来的符号写法）
all_data = {}
for base in selected_cryptos:
    sym = f"{base}/USDT:USDT" if base in CONTRACTS else f"{base}/USDT"
    all_data[base] = {}
    for tf in INTERVALS:
        try:
            bars = ex.fetch_ohlcv(sym, timeframe=tf, limit=100)
            df = pd.DataFrame(bars, columns=['ts','open','high','low','close','volume'])
            df['ts'] = pd.to_datetime(df['ts'], unit='ms').dt.tz_localize('UTC')
            df.set_index('ts', inplace=True)
            all_data[base][tf] = calculate_indicators(df, sens, atrp)
        except: 
            all_data[base][tf] = pd.DataFrame()

# 构建展示与推送逻辑
rows = []
for base in selected_cryptos:
    price_now = "N/A"
    for t_val in ["1m", "5m", "15m"]:
        if not all_data[base].get(t_val, pd.DataFrame()).empty:
            price_now = all_data[base][t_val].iloc[-1]['Close']
            break
            
    row_data = {"资产": base, "实时价格": f"<b>{price_now}</b>"}
    
    for tf in INTERVALS:
        df = all_data[base].get(tf, pd.DataFrame())
        if df.empty:
            row_data[tf] = "-"
            continue
        
        latest = df.iloc[-1]
        color = "#00ff00" if latest['Close'] > latest['trail_stop'] else "#ff0000"
        status_text = "BUY 🟢" if color == "#00ff00" else "SELL 🔴"
        row_data[tf] = f"<div style='color:{color}; font-weight:bold;'>{status_text}</div><div style='font-size:0.8em; color:#888;'>止损:{latest['trail_stop']:.2f}</div>"
        
        # 信号判断 + 持仓管理
        if tf in ALERT_INTERVALS and len(df) >= 2:
            prev = df.iloc[-2]
            curr = df.iloc[-1]
            
            buy_cross = (curr['Close'] > curr['trail_stop']) and (prev['Close'] <= prev['trail_stop'])
            sell_cross = (curr['Close'] < curr['trail_stop']) and (prev['Close'] >= prev['trail_stop'])
            
            signal = "NONE"
            if buy_cross: signal = "BUY 🟢"
            elif sell_cross: signal = "SELL 🔴"
            
            if signal != "NONE":
                sig_time = df.index[-2].astimezone(BEIJING_TZ).strftime('%m-%d %H:%M')
                cache_key = f"{base}_{tf}_{sig_time}"
                
                if cache_key not in state["sent_cache"]:
                    vol_r = prev['Volume'] / prev['vol_avg'] if prev['vol_avg'] > 0 else 1.0
                    vol_tag = "⚡放量" if vol_r >= 1.2 else "☁️缩量"
                    obv_up = prev['obv'] > df['obv'].iloc[-3] if len(df) >= 3 else False
                    obv_tag = "📈流入" if obv_up else "📉流出"
                    
                    p_tf = RESONANCE_MAP.get(tf)
                    p_df = all_data[base].get(p_tf, pd.DataFrame())
                    p_status = "BUY" if (not p_df.empty and p_df.iloc[-1]['Close'] > p_df.iloc[-1]['trail_stop']) else "SELL"
                    sync_tag = "🔗共振" if signal.startswith(p_status) else "⚠️逆势"
                    
                    # 持仓逻辑 - 只做多 + 观望
                    pos_key = f"{base}_{tf}"
                    if pos_key not in state["positions"]:
                        state["positions"][pos_key] = {"side": "flat", "entry_price": None, "entry_time": None}
                    
                    pos = state["positions"][pos_key]
                    action_desc = ""
                    profit_str = ""
                    
                    if signal == "BUY 🟢":
                        if pos["side"] == "long":
                            action_desc = "继续持多"
                        else:
                            action_desc = "开多"
                            state["positions"][pos_key] = {
                                "side": "long",
                                "entry_price": curr['Close'],
                                "entry_time": sig_time
                            }
                    
                    elif signal == "SELL 🔴":
                        if pos["side"] == "long":
                            if pos["entry_price"] is not None:
                                profit_pct = (curr['Close'] - pos["entry_price"]) / pos["entry_price"] * 100
                                profit_str = f"{profit_pct:+.2f}%"
                            action_desc = f"平多（盈亏 {profit_str or '未知'}）"
                            state["positions"][pos_key] = {"side": "flat", "entry_price": None, "entry_time": None}
                        else:
                            action_desc = "观望中（无持仓）"
                    
                    state["alert_logs"].insert(0, {
                        "时间": datetime.now(BEIJING_TZ).strftime('%H:%M:%S'),
                        "资产": base, "周期": tf, "信号": signal,
                        "动作": action_desc,
                        "盈亏": profit_str if profit_str else "-",
                        "能量": f"{vol_r:.1f}x {vol_tag}",
                        "OBV": obv_tag, "共振": sync_tag,
                        "信号价格": curr['Close'],
                        "信号时间": sig_time,
                        "最新价格": price_now
                    })
                    
                    push_title = f"{base}({tf}){signal}|{vol_tag}"
                    push_body = f"价格:{curr['Close']}\n{sync_tag}|{obv_tag}"
                    if action_desc: push_body += f"\n动作: {action_desc}"
                    if profit_str: push_body += f"\n盈亏: {profit_str}"
                    
                    send_wx_pusher(push_title, push_body)
                    state["sent_cache"][cache_key] = True

    rows.append(row_data)

# ==================== 4. 渲染 ====================
st.markdown("<h3 style='text-align:center;'>🚀 UT Bot 多重过滤系统</h3>", unsafe_allow_html=True)
if rows:
    disp_df = pd.DataFrame(rows)
    st.write(disp_df[["资产", "实时价格"] + INTERVALS].to_html(escape=False, index=False), unsafe_allow_html=True)

st.divider()
st.subheader("📜 推送日志 - 近24小时（按币种 → 周期归类）")

if state["alert_logs"]:
    log_df = pd.DataFrame(state["alert_logs"])
    
    required_cols = ["时间", "资产", "周期", "信号", "动作", "盈亏", "能量", "OBV", "共振", "信号价格", "信号时间", "最新价格"]
    available_cols = [col for col in required_cols if col in log_df.columns]
    log_df = log_df[available_cols].copy()
    
    # 时间解析（兼容 HH:MM:SS 或完整日期）
    try:
        log_df['时间_dt'] = pd.to_datetime(log_df['时间'], format='%Y-%m-%d %H:%M:%S', errors='raise')
    except:
        today = datetime.now(BEIJING_TZ).date()
        log_df['时间_dt'] = pd.to_datetime(
            log_df['时间'].apply(lambda x: f"{today} {x}"),
            format='%Y-%m-%d %H:%M:%S', errors='coerce'
        )
    
    log_df['时间_dt'] = log_df['时间_dt'].dt.tz_localize(BEIJING_TZ, ambiguous='NaT', nonexistent='NaT')
    
    now_beijing = datetime.now(BEIJING_TZ)
    threshold = now_beijing - timedelta(hours=24)
    recent_df = log_df[log_df['时间_dt'] >= threshold].copy()
    
    if recent_df.empty:
        st.info("近24小时内暂无推送记录")
    else:
        recent_df = recent_df.sort_values("时间_dt", ascending=False).reset_index(drop=True)
        st.caption(f"共 {len(recent_df)} 条 | 时间范围：{threshold.strftime('%m-%d %H:%M')} → {now_beijing.strftime('%m-%d %H:%M')}")
        
        assets = sorted(recent_df["资产"].unique())
        
        for asset in assets:
            asset_df = recent_df[recent_df["资产"] == asset]
            with st.expander(f"📈 {asset} （{len(asset_df)} 条）", expanded=(len(assets) <= 5)):
                periods = sorted(asset_df["周期"].unique(), reverse=True)  # 大周期优先
                for period in periods:
                    period_df = asset_df[asset_df["周期"] == period]
                    st.markdown(f"**{period}** （{len(period_df)} 条）")
                    display_cols = [c for c in ["时间", "信号", "动作", "盈亏", "能量", "OBV", "共振", "信号价格", "信号时间", "最新价格"] if c in period_df.columns]
                    st.dataframe(
                        period_df[display_cols],
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "盈亏": st.column_config.TextColumn("盈亏", width="small"),
                            "动作": st.column_config.TextColumn("动作", width="medium"),
                            "信号价格": st.column_config.NumberColumn("信号价格", format="%.4f"),
                            "最新价格": st.column_config.NumberColumn("最新价格", format="%.4f")
                        }
                    )
                    st.markdown("---")
        
        st.markdown("### 下载近24小时日志")
        csv_data = recent_df.drop(columns=['时间_dt'], errors='ignore').to_csv(index=False).encode('utf-8-sig')
        st.download_button("下载 CSV", csv_data, f"utbot_24h_{now_beijing.strftime('%Y%m%d_%H%M')}.csv", "text/csv")
        
        try:
            from io import BytesIO
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                recent_df.drop(columns=['时间_dt'], errors='ignore').to_excel(writer, index=False, sheet_name="近24小时")
            output.seek(0)
            st.download_button("下载 Excel", output, f"utbot_24h_{now_beijing.strftime('%Y%m%d_%H%M')}.xlsx",
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        except:
            st.caption("Excel 下载需 openpyxl 支持，若不可用请用 CSV")
else:
    st.info("暂无推送日志")
