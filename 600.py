import streamlit as st
import pandas as pd
import numpy as np
import pandas_ta as ta
import ccxt
import asyncio
import aiohttp
import requests
from datetime import datetime, timedelta
import pytz
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
import warnings
warnings.filterwarnings('ignore')

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

# ==================== 2. 异步数据获取 ====================

class AsyncDataFetcher:
    def __init__(self):
        self.exchange = ccxt.okx({
            'enableRateLimit': True,
            'timeout': 30000,
            'session': aiohttp.ClientSession()
        })
        self.exchange.load_markets()
        self._cache = {}
        self._cache_time = {}
        self.CACHE_TTL = 30  # 缓存30秒
        
    def _get_cache_key(self, base, timeframe):
        return f"{base}_{timeframe}"
    
    def _is_cache_valid(self, cache_key):
        if cache_key not in self._cache_time:
            return False
        return time.time() - self._cache_time[cache_key] < self.CACHE_TTL
    
    async def fetch_ohlcv_async(self, symbol, timeframe, limit=200):
        try:
            ohlcv = await self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            return ohlcv
        except Exception as e:
            print(f"Error fetching {symbol} {timeframe}: {e}")
            return None
    
    async def fetch_multiple_async(self, symbols_timeframes):
        """批量获取多个symbol和时间周期的数据"""
        tasks = []
        for symbol, timeframe in symbols_timeframes:
            tasks.append(self.fetch_ohlcv_async(symbol, timeframe))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return results
    
    def fetch_all_data_batch(self, bases, timeframes):
        """批量同步获取所有数据"""
        all_data = {}
        
        # 构建要获取的所有symbol和timeframe组合
        symbols_timeframes = []
        symbol_map = {}  # 映射索引到base和timeframe
        
        for base in bases:
            all_data[base] = {}
            sym = f"{base}-USDT-SWAP" if base in CONTRACTS else f"{base}/USDT"
            
            for tf in timeframes:
                cache_key = self._get_cache_key(base, tf)
                
                # 检查缓存
                if self._is_cache_valid(cache_key):
                    all_data[base][tf] = self._cache[cache_key]
                else:
                    symbols_timeframes.append((sym, tf))
                    idx = len(symbols_timeframes) - 1
                    symbol_map[idx] = (base, tf, sym)
        
        if not symbols_timeframes:
            return all_data
        
        # 使用线程池并发获取
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            for sym, tf in symbols_timeframes:
                future = executor.submit(self._fetch_sync, sym, tf)
                futures.append(future)
            
            for idx, future in enumerate(futures):
                if idx not in symbol_map:
                    continue
                    
                base, tf, sym = symbol_map[idx]
                try:
                    bars = future.result(timeout=10)
                    if bars and len(bars) > 0:
                        df = self._process_bars_to_df(bars)
                        cache_key = self._get_cache_key(base, tf)
                        self._cache[cache_key] = df
                        self._cache_time[cache_key] = time.time()
                        all_data[base][tf] = df
                    else:
                        all_data[base][tf] = pd.DataFrame()
                except Exception as e:
                    print(f"Error processing {base} {tf}: {e}")
                    all_data[base][tf] = pd.DataFrame()
        
        return all_data
    
    def _fetch_sync(self, symbol, timeframe, retries=3):
        """同步获取数据，带重试"""
        for attempt in range(retries):
            try:
                bars = self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=200)
                return bars
            except Exception as e:
                if attempt == retries - 1:
                    print(f"Failed to fetch {symbol} {timeframe} after {retries} attempts: {e}")
                time.sleep(1 * (attempt + 1))  # 指数退避
        return None
    
    def _process_bars_to_df(self, bars):
        """处理bars数据为DataFrame"""
        if not bars or len(bars) == 0:
            return pd.DataFrame()
        
        df = pd.DataFrame(bars, columns=['ts','open','high','low','close','volume'])
        df['ts'] = pd.to_datetime(df['ts'], unit='ms').dt.tz_localize('UTC')
        df.set_index('ts', inplace=True)
        return df

# ==================== 3. 逻辑函数 ====================

def send_wx_pusher(title, body):
    if not APP_TOKEN or not USER_UID: return
    try:
        payload = {"appToken": APP_TOKEN, "content": f"{title}\n{body}", "uids": [USER_UID]}
        requests.post("https://wxpusher.zjiecode.com/api/send/message", json=payload, timeout=5)
    except Exception as e:
        print(f"推送失败: {e}")

@lru_cache(maxsize=100)
def calculate_indicators_cached(df_hash, sensitivity, atr_period):
    """缓存指标计算"""
    return calculate_indicators(df_hash, sensitivity, atr_period)

def calculate_indicators(df, sensitivity, atr_period):
    if df.empty or len(df) < 50: 
        return pd.DataFrame()
    
    df.columns = [str(c).capitalize() for c in df.columns]
    
    # 计算ATR
    df['atr'] = ta.atr(df['High'], df['Low'], df['Close'], length=atr_period)
    df = df.dropna(subset=['atr']).copy()
    
    if df.empty:
        return pd.DataFrame()
    
    n_loss = sensitivity * df['atr']
    src = df['Close']
    trail_stop = np.zeros(len(df))
    
    # 初始化第一个值
    if len(df) > 0:
        trail_stop[0] = src.iloc[0] - n_loss.iloc[0]
    
    # 向量化计算（比循环快）
    for i in range(1, len(df)):
        p = trail_stop[i-1]
        src_i = src.iloc[i]
        src_i_1 = src.iloc[i-1]
        n_loss_i = n_loss.iloc[i]
        
        if src_i > p and src_i_1 > p:
            trail_stop[i] = max(p, src_i - n_loss_i)
        elif src_i < p and src_i_1 < p:
            trail_stop[i] = min(p, src_i + n_loss_i)
        elif src_i > p:
            trail_stop[i] = src_i - n_loss_i
        else:
            trail_stop[i] = src_i + n_loss_i
    
    df['trail_stop'] = trail_stop
    df['buy_signal'] = (df['Close'] > df['trail_stop']) & (df['Close'].shift(1) <= df['trail_stop'].shift(1))
    df['sell_signal'] = (df['Close'] < df['trail_stop']) & (df['Close'].shift(1) >= df['trail_stop'].shift(1))
    
    # 计算OBV和成交量均值
    df['obv'] = ta.obv(df['Close'], df['Volume'])
    df['vol_avg'] = df['Volume'].shift(1).rolling(window=5, min_periods=1).mean()
    
    return df

def calculate_win_rate(log_df, action_col='动作', profit_col='盈亏'):
    if log_df.empty:
        return {"win_rate": "0.0%", "total_trades": 0, "wins": 0, "losses": 0}
    
    if action_col not in log_df.columns or profit_col not in log_df.columns:
        return {"win_rate": "N/A (无交易记录)", "total_trades": 0, "wins": 0, "losses": 0}
    
    # 向量化过滤
    closed_mask = (
        log_df[action_col].astype(str).str.contains('平', na=False) &
        (log_df[profit_col] != '-') &
        (log_df[profit_col] != '') &
        log_df[profit_col].notna()
    )
    
    closed_trades = log_df[closed_mask].copy()
    
    if closed_trades.empty:
        return {"win_rate": "0.0% (无平仓记录)", "total_trades": 0, "wins": 0, "losses": 0}
    
    # 使用向量化转换
    def safe_float_series(x):
        try:
            return pd.to_numeric(x.astype(str).str.rstrip('%'), errors='coerce')
        except:
            return pd.Series([np.nan] * len(x))
    
    closed_trades['profit'] = safe_float_series(closed_trades[profit_col])
    closed_trades = closed_trades.dropna(subset=['profit'])
    
    if closed_trades.empty:
        return {"win_rate": "0.0%", "total_trades": 0, "wins": 0, "losses": 0}
    
    wins = (closed_trades['profit'] > 0).sum()
    losses = (closed_trades['profit'] <= 0).sum()
    total = wins + losses
    win_rate = (wins / total * 100) if total > 0 else 0.0
    
    return {
        "win_rate": f"{win_rate:.1f}%",
        "total_trades": total,
        "wins": wins,
        "losses": losses
    }

# ==================== 4. 主程序 ====================

st.set_page_config(page_title="UT Bot Pro 性能优化版", layout="wide")

# 初始化状态
if "last_update" not in st.session_state:
    st.session_state.last_update = time.time()
    st.session_state.data_fetcher = AsyncDataFetcher()
    st.session_state.all_data_cache = {}
    st.session_state.cache_time = 0
    st.session_state.sent_cache = {}
    st.session_state.alert_logs = []
    st.session_state.positions = {}

refresh_sec = 300 
time_passed = time.time() - st.session_state.last_update

# 侧边栏
st.sidebar.title("⚙️ 设置")
st.sidebar.caption(f"🔄 刷新倒计时: {max(0, int(refresh_sec - time_passed))}s")

selected_cryptos = st.sidebar.multiselect(
    "品种选择", 
    CRYPTO_LIST, 
    default=CRYPTO_LIST[:5]  # 默认选前5个加快加载
)

sens = st.sidebar.slider("敏感度", 0.1, 5.0, 1.0, 0.1)
atrp = st.sidebar.slider("ATR周期", 1, 30, 10, 1)

# 自动刷新按钮
if st.sidebar.button("🔄 手动刷新数据"):
    st.session_state.cache_time = 0  # 清除缓存
    st.rerun()

# 批量获取数据（带缓存）
cache_key = f"{'_'.join(selected_cryptos)}_{sens}_{atrp}"
if (time.time() - st.session_state.cache_time > 60 or 
    cache_key not in st.session_state.all_data_cache):
    
    with st.spinner(f"正在获取{len(selected_cryptos)}个品种数据..."):
        fetcher = st.session_state.data_fetcher
        all_data = fetcher.fetch_all_data_batch(selected_cryptos, INTERVALS)
        
        # 计算指标
        for base in selected_cryptos:
            for tf in INTERVALS:
                if tf in all_data[base] and not all_data[base][tf].empty:
                    all_data[base][tf] = calculate_indicators(all_data[base][tf], sens, atrp)
        
        st.session_state.all_data_cache[cache_key] = all_data
        st.session_state.cache_time = time.time()
        st.session_state.last_update = time.time()

all_data = st.session_state.all_data_cache.get(cache_key, {})

# 构建展示数据
rows = []
for base in selected_cryptos:
    price_now = "N/A"
    base_data = all_data.get(base, {})
    
    # 获取最新价格
    for t_val in ["1m", "5m", "15m"]:
        df = base_data.get(t_val, pd.DataFrame())
        if not df.empty:
            price_now = df.iloc[-1]['Close']
            break
    
    row_data = {"资产": base, "实时价格": f"<b>{price_now}</b>"}
    
    for tf in INTERVALS:
        df = base_data.get(tf, pd.DataFrame())
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
            if buy_cross: 
                signal = "BUY 🟢"
            elif sell_cross: 
                signal = "SELL 🔴"
            
            if signal != "NONE":
                sig_time_utc = df.index[-2]
                sig_time_beijing = sig_time_utc.astimezone(BEIJING_TZ)
                sig_time_str = sig_time_beijing.strftime('%Y-%m-%d %H:%M:%S')
                cache_key = f"{base}_{tf}_{sig_time_str}"
                
                if cache_key not in st.session_state.sent_cache:
                    # 计算成交量比率
                    vol_r = prev['Volume'] / prev['vol_avg'] if prev['vol_avg'] > 0 else 1.0
                    vol_tag = "⚡放量" if vol_r >= 1.2 else "☁️缩量"
                    
                    # 计算OBV方向
                    obv_up = prev['obv'] > df['obv'].iloc[-3] if len(df) >= 3 else False
                    obv_tag = "📈流入" if obv_up else "📉流出"
                    
                    # 三周期共振检查
                    sync_tags = {}
                    for group_name, group_tfs in RESONANCE_GROUPS.items():
                        if tf in group_tfs:
                            group_statuses = []
                            for g_tf in group_tfs:
                                g_df = all_data.get(base, {}).get(g_tf, pd.DataFrame())
                                if not g_df.empty:
                                    g_status = "BUY" if g_df.iloc[-1]['Close'] > g_df.iloc[-1]['trail_stop'] else "SELL"
                                    group_statuses.append(g_status)
                            
                            if len(group_statuses) == len(group_tfs):
                                if all(s == "BUY" for s in group_statuses) and signal == "BUY 🟢":
                                    sync_tags[group_name] = "🔗共振 (做多)"
                                elif all(s == "SELL" for s in group_statuses) and signal == "SELL 🔴":
                                    sync_tags[group_name] = "🔗共振 (做空)"
                                else:
                                    sync_tags[group_name] = "⚠️无共振"
                            else:
                                sync_tags[group_name] = "⚠️数据不足"
                    
                    # 持仓逻辑
                    action_descs = {}
                    profit_strs = {}
                    
                    for group_name in RESONANCE_GROUPS:
                        pos_key = f"{base}_{tf}_{group_name}"
                        if pos_key not in st.session_state.positions:
                            st.session_state.positions[pos_key] = {"side": "flat", "entry_price": None, "entry_time": None}
                        
                        pos = st.session_state.positions[pos_key]
                        action_desc = ""
                        profit_str = ""
                        
                        if group_name in sync_tags and "共振" in sync_tags[group_name]:
                            if "做多" in sync_tags[group_name]:
                                if pos["side"] == "long":
                                    action_desc = "继续持多"
                                elif pos["side"] == "short":
                                    if pos["entry_price"] is not None:
                                        profit_pct = (pos["entry_price"] - curr['Close']) / pos["entry_price"] * 100
                                        profit_str = f"{profit_pct:+.2f}%"
                                    action_desc = f"平空转多（盈亏 {profit_str or '未知'}）"
                                    st.session_state.positions[pos_key] = {
                                        "side": "long",
                                        "entry_price": curr['Close'],
                                        "entry_time": sig_time_str
                                    }
                                else:
                                    action_desc = "开多"
                                    st.session_state.positions[pos_key] = {
                                        "side": "long",
                                        "entry_price": curr['Close'],
                                        "entry_time": sig_time_str
                                    }
                            
                            elif "做空" in sync_tags[group_name]:
                                if pos["side"] == "short":
                                    action_desc = "继续持空"
                                elif pos["side"] == "long":
                                    if pos["entry_price"] is not None:
                                        profit_pct = (curr['Close'] - pos["entry_price"]) / pos["entry_price"] * 100
                                        profit_str = f"{profit_pct:+.2f}%"
                                    action_desc = f"平多转空（盈亏 {profit_str or '未知'}）"
                                    st.session_state.positions[pos_key] = {
                                        "side": "short",
                                        "entry_price": curr['Close'],
                                        "entry_time": sig_time_str
                                    }
                                else:
                                    action_desc = "开空"
                                    st.session_state.positions[pos_key] = {
                                        "side": "short",
                                        "entry_price": curr['Close'],
                                        "entry_time": sig_time_str
                                    }
                        else:
                            if pos["side"] != "flat":
                                if pos["side"] == "long":
                                    profit_pct = (curr['Close'] - pos["entry_price"]) / pos["entry_price"] * 100
                                else:
                                    profit_pct = (pos["entry_price"] - curr['Close']) / pos["entry_price"] * 100
                                profit_str = f"{profit_pct:+.2f}%"
                                action_desc = f"无共振平仓（{pos['side']} 盈亏 {profit_str}）"
                                st.session_state.positions[pos_key] = {"side": "flat", "entry_price": None, "entry_time": None}
                            else:
                                action_desc = "观望中（无持仓）"
                        
                        action_descs[group_name] = action_desc
                        profit_strs[group_name] = profit_str
                    
                    # 日志记录
                    log_entry = {
                        "时间": sig_time_str,
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
                        log_entry[f"{group_name}_动作"] = action_descs.get(group_name, "无动作")
                        log_entry[f"{group_name}_盈亏"] = profit_strs.get(group_name, "-")
                    
                    st.session_state.alert_logs.insert(0, log_entry)
                    
                    # 推送
                    push_title = f"{base}({tf}){signal}|{vol_tag}"
                    push_body = f"价格:{curr['Close']:.2f}\n{obv_tag}"
                    for group_name in RESONANCE_GROUPS:
                        push_body += f"\n{group_name}: {sync_tags.get(group_name, 'N/A')} | {action_descs.get(group_name, '')} | 盈亏 {profit_strs.get(group_name, '-')}"
                    
                    send_wx_pusher(push_title, push_body)
                    st.session_state.sent_cache[cache_key] = True
    
    rows.append(row_data)

# ==================== 5. 渲染界面 ====================

st.markdown("<h3 style='text-align:center;'>🚀 UT Bot 多重过滤系统 (性能优化版)</h3>", unsafe_allow_html=True)

if rows:
    disp_df = pd.DataFrame(rows)
    st.write(disp_df[["资产", "实时价格"] + INTERVALS].to_html(escape=False, index=False), unsafe_allow_html=True)

st.divider()
st.subheader("📜 推送日志 - 近24小时")

if st.session_state.alert_logs:
    log_df = pd.DataFrame(st.session_state.alert_logs)
    
    required_cols = ["时间", "资产", "周期", "信号", "能量", "OBV", "信号价格", "最新价格", "止损", "ATR", "成交量", "OBV值"]
    for group in RESONANCE_GROUPS:
        required_cols += [f"{group}_共振", f"{group}_动作", f"{group}_盈亏"]
    
    available_cols = [col for col in required_cols if col in log_df.columns]
    log_df = log_df[available_cols].copy()
    
    # 时间解析
    log_df['时间_dt'] = pd.to_datetime(log_df['时间'], format='%Y-%m-%d %H:%M:%S', errors='coerce')
    if log_df['时间_dt'].dt.tz is None:
        log_df['时间_dt'] = log_df['时间_dt'].dt.tz_localize(BEIJING_TZ, ambiguous='NaT', nonexistent='NaT')
    
    now_beijing = datetime.now(BEIJING_TZ)
    threshold = now_beijing - timedelta(hours=24)
    recent_df = log_df[log_df['时间_dt'] >= threshold].copy()
    
    if recent_df.empty:
        st.info("近24小时内暂无推送记录")
    else:
        recent_df = recent_df.sort_values("时间_dt", ascending=False).reset_index(drop=True)
        st.caption(f"共 {len(recent_df)} 条信号 | 时间范围：{threshold.strftime('%Y-%m-%d %H:%M')} → {now_beijing.strftime('%Y-%m-%d %H:%M')}")
        
        # 胜率统计
        if '动作' in recent_df.columns and '盈亏' in recent_df.columns:
            global_stats = calculate_win_rate(recent_df, action_col='动作', profit_col='盈亏')
            st.markdown(f"**全局胜率统计**：胜率 {global_stats['win_rate']} | 总交易 {global_stats['total_trades']} | 胜 {global_stats['wins']} | 负 {global_stats['losses']}")
        
        for group in RESONANCE_GROUPS:
            group_action_col = f"{group}_动作"
            group_profit_col = f"{group}_盈亏"
            if group_action_col in recent_df.columns and group_profit_col in recent_df.columns:
                group_stats = calculate_win_rate(recent_df, action_col=group_action_col, profit_col=group_profit_col)
                st.markdown(f"**{group} 胜率统计**：胜率 {group_stats['win_rate']} | 总交易 {group_stats['total_trades']} | 胜 {group_stats['wins']} | 负 {group_stats['losses']}")
        
        # 按币种显示
        assets = sorted(recent_df["资产"].unique())
        
        for asset in assets:
            asset_df = recent_df[recent_df["资产"] == asset]
            
            with st.expander(f"📈 {asset} （{len(asset_df)} 条信号）", expanded=(len(assets) <= 5)):
                periods = sorted(asset_df["周期"].unique(), key=lambda x: INTERVALS.index(x) if x in INTERVALS else len(INTERVALS))
                
                for period in periods:
                    period_df = asset_df[asset_df["周期"] == period].copy()
                    
                    st.markdown(f"**{period}** （{len(period_df)} 条）")
                    
                    display_cols = [c for c in required_cols[3:] if c in period_df.columns]
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
                    
                    # 下载按钮
                    if not period_df.empty:
                        csv_period = period_df.drop(columns=['时间_dt', '资产', '周期'], errors='ignore').to_csv(index=False).encode('utf-8-sig')
                        file_name = f"{asset}_{period}_24h_{now_beijing.strftime('%Y%m%d_%H%M')}.csv"
                        
                        st.download_button(
                            label=f"下载 {asset} {period} （CSV）",
                            data=csv_period,
                            file_name=file_name,
                            mime="text/csv",
                            key=f"dl_{asset}_{period}_{time.time()}"
                        )
                    
                    st.markdown("---")
        
        # 全局下载
        st.markdown("### 全部近24小时下载")
        csv_all = recent_df.drop(columns=['时间_dt'], errors='ignore').to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="下载全部（CSV）",
            data=csv_all,
            file_name=f"utbot_all_24h_{now_beijing.strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
            key="dl_all_csv"
        )
else:
    st.info("暂无推送日志")

# 性能信息
st.sidebar.divider()
st.sidebar.caption("📊 性能信息")
st.sidebar.caption(f"数据获取耗时: {time.time() - st.session_state.cache_time:.1f}s")
st.sidebar.caption(f"缓存命中率: {len(st.session_state.sent_cache)} 条已推送")
st.sidebar.caption(f"持仓数量: {len(st.session_state.positions)}")

# 清除缓存按钮
if st.sidebar.button("🧹 清除缓存"):
    st.session_state.cache_time = 0
    st.session_state.sent_cache.clear()
    st.session_state.all_data_cache.clear()
    st.rerun()
