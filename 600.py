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

# 定义两个三周期组
RESONANCE_GROUPS = {
    "group1": ["4h", "1h", "15m"],  # 组1: 4h, 1h, 15m
    "group2": ["1h", "15m", "5m"]   # 组2: 1h, 15m, 5m
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

# 计算胜率统计（基于日志）
def calculate_win_rate(log_df):
    if log_df.empty: return {"win_rate": 0, "total_trades": 0, "wins": 0, "losses": 0}
    
    closed_trades = log_df[(log_df['动作'].str.contains('平')) & (log_df['盈亏'] != '-')]
    closed_trades['profit'] = closed_trades['盈亏'].str.rstrip('%').astype(float)
    
    wins = len(closed_trades[closed_trades['profit'] > 0])
    losses = len(closed_trades[closed_trades['profit'] <= 0])
    total = wins + losses
    win_rate = (wins / total * 100) if total > 0 else 0
    
    return {"win_rate": f"{win_rate:.1f}%", "total_trades": total, "wins": wins, "losses": losses}

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
ex.load_markets()  # 预加载markets，提高稳定性

selected_cryptos = st.sidebar.multiselect("品种选择", CRYPTO_LIST, default=CRYPTO_LIST)
sens = st.sidebar.slider("敏感度", 0.1, 5.0, 1.0)
atrp = st.sidebar.slider("ATR周期", 1, 30, 10)

# 抓取数据（优化符号）
all_data = {}
for base in selected_cryptos:
    # 统一符号处理
    sym = f"{base}-USDT-SWAP" if base in CONTRACTS else f"{base}/USDT"
    all_data[base] = {}
    for tf in INTERVALS:
        try:
            bars = ex.fetch_ohlcv(sym, timeframe=tf, limit=200)  # 增加limit
            df = pd.DataFrame(bars, columns=['ts','open','high','low','close','volume'])
            df['ts'] = pd.to_datetime(df['ts'], unit='ms').dt.tz_localize('UTC')
            df.set_index('ts', inplace=True)
            all_data[base][tf] = calculate_indicators(df, sens, atrp)
            time.sleep(0.5)  # 防rate limit
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
        
        # 信号判断 + 持仓管理（只在ALERT_INTERVALS，且三周期共振时触发）
        if tf in ALERT_INTERVALS and len(df) >= 2:
            prev = df.iloc[-2]
            curr = df.iloc[-1]
            
            buy_cross = (curr['Close'] > curr['trail_stop']) and (prev['Close'] <= prev['trail_stop'])
            sell_cross = (curr['Close'] < curr['trail_stop']) and (prev['Close'] >= prev['trail_stop'])
            
            signal = "NONE"
            if buy_cross: signal = "BUY 🟢"
            elif sell_cross: signal = "SELL 🔴"
            
            if signal != "NONE":
                sig_time_utc = df.index[-2]  # UTC时间
                sig_time_beijing = sig_time_utc.astimezone(BEIJING_TZ)
                sig_time_str = sig_time_beijing.strftime('%Y-%m-%d %H:%M:%S')  # 带日期，防跨天重复
                cache_key = f"{base}_{tf}_{sig_time_str}"
                
                if cache_key not in state["sent_cache"]:
                    vol_r = prev['Volume'] / prev['vol_avg'] if prev['vol_avg'] > 0 else 1.0
                    vol_tag = "⚡放量" if vol_r >= 1.2 else "☁️缩量"
                    obv_up = prev['obv'] > df['obv'].iloc[-3] if len(df) >= 3 else False
                    obv_tag = "📈流入" if obv_up else "📉流出"
                    
                    # 三周期共振检查（为每个组独立检查）
                    sync_tags = {}
                    for group_name, group_tfs in RESONANCE_GROUPS.items():
                        if tf in group_tfs:
                            group_statuses = []
                            for g_tf in group_tfs:
                                g_df = all_data[base].get(g_tf, pd.DataFrame())
                                if not g_df.empty:
                                    g_status = "BUY" if g_df.iloc[-1]['Close'] > g_df.iloc[-1]['trail_stop'] else "SELL"
                                    group_statuses.append(g_status)
                            
                            # 只在全组同向时视为共振
                            if all(s == "BUY" for s in group_statuses) and signal == "BUY 🟢":
                                sync_tags[group_name] = "🔗共振 (做多)"
                            elif all(s == "SELL" for s in group_statuses) and signal == "SELL 🔴":
                                sync_tags[group_name] = "🔗共振 (做空)"
                            else:
                                sync_tags[group_name] = "⚠️无共振"
                    
                    # 持仓逻辑 - 每个组独立持仓（多/空双向）
                    action_descs = {}
                    profit_strs = {}
                    for group_name in RESONANCE_GROUPS:
                        pos_key = f"{base}_{tf}_{group_name}"
                        if pos_key not in state["positions"]:
                            state["positions"][pos_key] = {"side": "flat", "entry_price": None, "entry_time": None}
                        
                        pos = state["positions"][pos_key]
                        action_desc = ""
                        profit_str = ""
                        
                        if group_name in sync_tags and "共振" in sync_tags[group_name]:
                            if "做多" in sync_tags[group_name]:
                                if pos["side"] == "long":
                                    action_desc = "继续持多"
                                elif pos["side"] == "short":
                                    if pos["entry_price"] is not None:
                                        profit_pct = (pos["entry_price"] - curr['Close']) / pos["entry_price"] * 100  # 空头盈亏
                                        profit_str = f"{profit_pct:+.2f}%"
                                    action_desc = f"平空转多（盈亏 {profit_str or '未知'}）"
                                    state["positions"][pos_key] = {
                                        "side": "long",
                                        "entry_price": curr['Close'],
                                        "entry_time": sig_time_str
                                    }
                                else:
                                    action_desc = "开多"
                                    state["positions"][pos_key] = {
                                        "side": "long",
                                        "entry_price": curr['Close'],
                                        "entry_time": sig_time_str
                                    }
                            
                            elif "做空" in sync_tags[group_name]:
                                if pos["side"] == "short":
                                    action_desc = "继续持空"
                                elif pos["side"] == "long":
                                    if pos["entry_price"] is not None:
                                        profit_pct = (curr['Close'] - pos["entry_price"]) / pos["entry_price"] * 100  # 多头盈亏
                                        profit_str = f"{profit_pct:+.2f}%"
                                    action_desc = f"平多转空（盈亏 {profit_str or '未知'}）"
                                    state["positions"][pos_key] = {
                                        "side": "short",
                                        "entry_price": curr['Close'],
                                        "entry_time": sig_time_str
                                    }
                                else:
                                    action_desc = "开空"
                                    state["positions"][pos_key] = {
                                        "side": "short",
                                        "entry_price": curr['Close'],
                                        "entry_time": sig_time_str
                                    }
                        else:
                            # 无共振时，如果有仓位，考虑平仓？
                            if pos["side"] != "flat":
                                if pos["side"] == "long":
                                    profit_pct = (curr['Close'] - pos["entry_price"]) / pos["entry_price"] * 100
                                else:
                                    profit_pct = (pos["entry_price"] - curr['Close']) / pos["entry_price"] * 100
                                profit_str = f"{profit_pct:+.2f}%"
                                action_desc = f"无共振平仓（{pos['side']} 盈亏 {profit_str}）"
                                state["positions"][pos_key] = {"side": "flat", "entry_price": None, "entry_time": None}
                            else:
                                action_desc = "观望中（无持仓）"
                        
                        action_descs[group_name] = action_desc
                        profit_strs[group_name] = profit_str
                    
                    # 日志记录更多东西：每个组的共振、动作、盈亏 + 其他指标
                    log_entry = {
                        "时间": sig_time_str,  # 带日期
                        "资产": base, 
                        "周期": tf, 
                        "信号": signal,
                        "能量": f"{vol_r:.1f}x {vol_tag}",
                        "OBV": obv_tag,
                        "信号价格": curr['Close'],
                        "最新价格": price_now,
                        "止损": latest['trail_stop'],
                        "ATR": latest['atr'],
                        "成交量": latest['Volume'],
                        "OBV值": latest['obv']
                    }
                    
                    for group_name in RESONANCE_GROUPS:
                        log_entry[f"{group_name}_共振"] = sync_tags.get(group_name, "N/A")
                        log_entry[f"{group_name}_动作"] = action_descs.get(group_name, "")
                        log_entry[f"{group_name}_盈亏"] = profit_strs.get(group_name, "-")
                    
                    state["alert_logs"].insert(0, log_entry)
                    
                    # 推送（包含组信息）
                    push_title = f"{base}({tf}){signal}|{vol_tag}"
                    push_body = f"价格:{curr['Close']}\n{obv_tag}"
                    for group_name in RESONANCE_GROUPS:
                        push_body += f"\n{group_name}: {sync_tags.get(group_name, 'N/A')} | {action_descs.get(group_name, '')} | 盈亏 {profit_strs.get(group_name, '-')}"
                    
                    send_wx_pusher(push_title, push_body)
                    state["sent_cache"][cache_key] = True

# ==================== 4. 渲染 ====================
st.markdown("<h3 style='text-align:center;'>🚀 UT Bot 多重过滤系统</h3>", unsafe_allow_html=True)
if rows:
    disp_df = pd.DataFrame(rows)
    st.write(disp_df[["资产", "实时价格"] + INTERVALS].to_html(escape=False, index=False), unsafe_allow_html=True)

st.divider()
st.subheader("📜 推送日志 - 近24小时（按时间降序，按币种 → 周期独立归类 & 下载）")

if state["alert_logs"]:
    log_df = pd.DataFrame(state["alert_logs"])
    
    required_cols = ["时间", "资产", "周期", "信号", "能量", "OBV", "信号价格", "最新价格", "止损", "ATR", "成交量", "OBV值"]
    for group in RESONANCE_GROUPS:
        required_cols += [f"{group}_共振", f"{group}_动作", f"{group}_盈亏"]
    
    available_cols = [col for col in required_cols if col in log_df.columns]
    log_df = log_df[available_cols].copy()
    
    # 时间解析（现在带年月日，防0点错）
    log_df['时间_dt'] = pd.to_datetime(log_df['时间'], format='%Y-%m-%d %H:%M:%S', errors='coerce')
    log_df['时间_dt'] = log_df['时间_dt'].dt.tz_localize(BEIJING_TZ, ambiguous='NaT', nonexistent='NaT')
    
    now_beijing = datetime.now(BEIJING_TZ)
    threshold = now_beijing - timedelta(hours=24)
    recent_df = log_df[log_df['时间_dt'] >= threshold].copy()
    
    if recent_df.empty:
        st.info("近24小时内暂无推送记录")
    else:
        recent_df = recent_df.sort_values("时间_dt", ascending=False).reset_index(drop=True)  # 时间降序
        st.caption(f"共 {len(recent_df)} 条信号 | 时间范围：{threshold.strftime('%Y-%m-%d %H:%M')} → {now_beijing.strftime('%Y-%m-%d %H:%M')}")
        
        # 胜率统计（全局 + 每个组）
        global_stats = calculate_win_rate(recent_df)
        st.markdown(f"**全局胜率统计**：胜率 {global_stats['win_rate']} | 总交易 {global_stats['total_trades']} | 胜 {global_stats['wins']} | 负 {global_stats['losses']}")
        
        for group in RESONANCE_GROUPS:
            group_df = recent_df[recent_df[f"{group}_盈亏"] != '-']
            group_stats = calculate_win_rate(group_df.rename(columns={f"{group}_盈亏": "盈亏", f"{group}_动作": "动作"}))
            st.markdown(f"**{group} 胜率统计**：胜率 {group_stats['win_rate']} | 总交易 {group_stats['total_trades']} | 胜 {group_stats['wins']} | 负 {group_stats['losses']}")
        
        # 外层：按币种
        assets = sorted(recent_df["资产"].unique())
        
        for asset in assets:
            asset_df = recent_df[recent_df["资产"] == asset]
            
            with st.expander(f"📈 {asset} （{len(asset_df)} 条信号）", expanded=(len(assets) <= 5)):
                # 内层：按周期（每个周期独立表格 + 下载按钮）
                periods = sorted(asset_df["周期"].unique(), reverse=True)  # 1h > 30m > 15m
                
                for period in periods:
                    period_df = asset_df[asset_df["周期"] == period].copy()
                    
                    # 小标题 + 条数
                    st.markdown(f"**{period}** （{len(period_df)} 条）")
                    
                    # 显示表格
                    display_cols = [c for c in required_cols[3:] if c in period_df.columns]  # 从信号开始，排除时间/资产/周期
                    display_cols = ["时间", "信号"] + display_cols
                    
                    st.dataframe(
                        period_df[display_cols],
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "盈亏": st.column_config.TextColumn("盈亏", width="small"),
                            "动作": st.column_config.TextColumn("动作", width="medium"),
                            "信号价格": st.column_config.NumberColumn("信号价格", format="%.4f"),
                            "最新价格": st.column_config.NumberColumn("最新价格", format="%.4f"),
                            "止损": st.column_config.NumberColumn("止损", format="%.4f"),
                            "ATR": st.column_config.NumberColumn("ATR", format="%.4f")
                        }
                    )
                    
                    # 每个周期单独的下载按钮
                    if not period_df.empty:
                        csv_period = period_df.drop(columns=['时间_dt', '资产', '周期'], errors='ignore').to_csv(index=False).encode('utf-8-sig')
                        file_name = f"{asset}_{period}_24h_{now_beijing.strftime('%Y%m%d_%H%M')}.csv"
                        
                        st.download_button(
                            label=f"下载 {asset} {period} （CSV）",
                            data=csv_period,
                            file_name=file_name,
                            mime="text/csv",
                            key=f"dl_{asset}_{period}"  # 避免key冲突
                        )
                    
                    st.markdown("---")  # 分隔线
        
        # 全局下载（可选，全部近24小时）
        st.markdown("### 全部近24小时下载")
        csv_all = recent_df.drop(columns=['时间_dt'], errors='ignore').to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="下载全部（CSV）",
            data=csv_all,
            file_name=f"utbot_all_24h_{now_beijing.strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
            key="dl_all_csv"
        )
        
        # Excel 全局下载（可选）
        try:
            from io import BytesIO
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                recent_df.drop(columns=['时间_dt'], errors='ignore').to_excel(writer, index=False, sheet_name="全部")
            output.seek(0)
            st.download_button(
                label="下载全部（Excel）",
                data=output,
                file_name=f"utbot_all_24h_{now_beijing.strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_all_excel"
            )
        except:
            pass
else:
    st.info("暂无推送日志")
