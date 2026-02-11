import streamlit as st
import pandas as pd
import numpy as np
import pandas_ta as ta
import ccxt
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

# ==================== 2. 数据获取类（修复版） ====================

class OptimizedDataFetcher:
    def __init__(self):
        self.exchange = ccxt.okx({
            'enableRateLimit': True,
            'timeout': 30000,
            'options': {
                'defaultType': 'swap'  # 统一使用swap
            }
        })
        try:
            self.exchange.load_markets()
        except:
            pass  # 即使markets加载失败，后续再处理
            
        self._cache = {}
        self._cache_time = {}
        self.CACHE_TTL = 30  # 缓存30秒
        
    def _get_cache_key(self, base, timeframe):
        return f"{base}_{timeframe}"
    
    def _is_cache_valid(self, cache_key):
        if cache_key not in self._cache_time:
            return False
        return time.time() - self._cache_time[cache_key] < self.CACHE_TTL
    
    def _get_symbol(self, base):
        """根据币种类型获取正确的交易对符号"""
        if base in CONTRACTS:
            return f"{base}/USDT:USDT"  # 永续合约
        else:
            return f"{base}/USDT"  # 现货
    
    def _fetch_with_retry(self, symbol, timeframe, limit=200, retries=3):
        """带重试的数据获取"""
        for attempt in range(retries):
            try:
                # 尝试不同的调用方式
                try:
                    bars = self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
                except Exception as e1:
                    # 如果失败，尝试不带timeframe参数
                    bars = self.exchange.fetch_ohlcv(symbol, limit=limit)
                
                if bars and len(bars) > 0:
                    return bars
            except ccxt.NetworkError as e:
                if attempt == retries - 1:
                    print(f"网络错误获取 {symbol} {timeframe}: {e}")
                time.sleep(1 * (attempt + 1))
            except ccxt.ExchangeError as e:
                if attempt == retries - 1:
                    print(f"交易所错误获取 {symbol} {timeframe}: {e}")
                time.sleep(1 * (attempt + 1))
            except Exception as e:
                if attempt == retries - 1:
                    print(f"未知错误获取 {symbol} {timeframe}: {e}")
                time.sleep(1 * (attempt + 1))
        
        return None
    
    def fetch_all_data_batch(self, bases, timeframes):
        """批量获取所有数据"""
        all_data = {}
        
        # 构建任务列表
        tasks = []
        task_info = []  # 保存任务信息
        
        for base in bases:
            all_data[base] = {}
            symbol = self._get_symbol(base)
            
            for tf in timeframes:
                cache_key = self._get_cache_key(base, tf)
                
                # 检查缓存
                if self._is_cache_valid(cache_key):
                    all_data[base][tf] = self._cache[cache_key]
                else:
                    tasks.append((symbol, tf))
                    task_info.append((base, tf, symbol))
        
        if not tasks:
            return all_data
        
        # 使用线程池并发获取
        with ThreadPoolExecutor(max_workers=min(10, len(tasks))) as executor:
            # 准备任务
            future_to_task = {}
            for symbol, tf in tasks:
                future = executor.submit(self._fetch_with_retry, symbol, tf, 200)
                future_to_task[future] = (symbol, tf)
            
            # 处理结果
            results = {}
            for future in as_completed(future_to_task):
                symbol, tf = future_to_task[future]
                try:
                    bars = future.result(timeout=15)
                    results[(symbol, tf)] = bars
                except Exception as e:
                    print(f"任务执行失败 {symbol} {tf}: {e}")
                    results[(symbol, tf)] = None
        
        # 处理数据
        for idx, (base, tf, symbol) in enumerate(task_info):
            bars = results.get((symbol, tf))
            
            if bars and len(bars) > 0:
                df = self._process_bars_to_df(bars)
                if not df.empty:
                    cache_key = self._get_cache_key(base, tf)
                    self._cache[cache_key] = df
                    self._cache_time[cache_key] = time.time()
                    all_data[base][tf] = df
                else:
                    all_data[base][tf] = pd.DataFrame()
            else:
                all_data[base][tf] = pd.DataFrame()
        
        return all_data
    
    def _process_bars_to_df(self, bars):
        """处理bars数据为DataFrame"""
        if not bars or len(bars) == 0:
            return pd.DataFrame()
        
        try:
            df = pd.DataFrame(bars, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
            df['ts'] = pd.to_datetime(df['ts'], unit='ms', utc=True)
            df.set_index('ts', inplace=True)
            return df
        except Exception as e:
            print(f"处理数据框时出错: {e}")
            return pd.DataFrame()

# ==================== 3. 逻辑函数 ====================

def send_wx_pusher(title, body):
    """发送微信推送"""
    if not APP_TOKEN or not USER_UID: 
        return
    
    try:
        payload = {
            "appToken": APP_TOKEN,
            "content": f"{title}\n\n{body}",
            "summary": title,
            "contentType": 1,
            "uids": [USER_UID]
        }
        response = requests.post(
            "https://wxpusher.zjiecode.com/api/send/message",
            json=payload,
            timeout=10
        )
        if response.status_code != 200:
            print(f"推送失败: {response.status_code}, {response.text}")
    except Exception as e:
        print(f"推送异常: {e}")

def calculate_indicators(df, sensitivity, atr_period):
    """计算技术指标"""
    if df.empty or len(df) < atr_period * 2:
        return pd.DataFrame()
    
    # 确保列名规范
    df = df.copy()
    if 'volume' in df.columns:
        df.rename(columns={'volume': 'Volume'}, inplace=True)
    
    # 确保有足够的列
    required_cols = ['open', 'high', 'low', 'close', 'Volume']
    for col in required_cols:
        if col not in df.columns:
            print(f"缺少必要列: {col}")
            return pd.DataFrame()
    
    # 重命名列为首字母大写
    df.columns = [str(c).lower() for c in df.columns]
    df.rename(columns={
        'open': 'Open',
        'high': 'High', 
        'low': 'Low',
        'close': 'Close',
        'volume': 'Volume'
    }, inplace=True)
    
    try:
        # 计算ATR
        df['atr'] = ta.atr(df['High'], df['Low'], df['Close'], length=atr_period)
        df = df.dropna(subset=['atr']).copy()
        
        if df.empty:
            return pd.DataFrame()
        
        # 计算动态止损
        n_loss = sensitivity * df['atr']
        src = df['Close']
        trail_stop = np.zeros(len(df))
        
        # 初始化第一个值
        if len(df) > 0:
            trail_stop[0] = src.iloc[0] - n_loss.iloc[0]
        
        # 计算动态止损线
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
        
        # 生成买卖信号
        df['buy_signal'] = (df['Close'] > df['trail_stop']) & (df['Close'].shift(1) <= df['trail_stop'].shift(1))
        df['sell_signal'] = (df['Close'] < df['trail_stop']) & (df['Close'].shift(1) >= df['trail_stop'].shift(1))
        
        # 计算OBV
        df['obv'] = ta.obv(df['Close'], df['Volume'])
        
        # 计算成交量均值
        df['vol_avg'] = df['Volume'].rolling(window=5, min_periods=1).mean().shift(1)
        
        return df
        
    except Exception as e:
        print(f"计算指标时出错: {e}")
        return pd.DataFrame()

def calculate_win_rate(log_df, action_col='动作', profit_col='盈亏'):
    """计算胜率"""
    if log_df.empty:
        return {"win_rate": "0.0%", "total_trades": 0, "wins": 0, "losses": 0}
    
    if action_col not in log_df.columns or profit_col not in log_df.columns:
        return {"win_rate": "N/A", "total_trades": 0, "wins": 0, "losses": 0}
    
    try:
        # 过滤平仓记录
        closed_mask = (
            log_df[action_col].astype(str).str.contains('平', na=False) &
            log_df[profit_col].notna() &
            (log_df[profit_col] != '-') &
            (log_df[profit_col] != '')
        )
        
        closed_trades = log_df[closed_mask].copy()
        
        if closed_trades.empty:
            return {"win_rate": "0.0%", "total_trades": 0, "wins": 0, "losses": 0}
        
        # 转换盈亏为数值
        def parse_profit(x):
            try:
                # 移除百分号和其他字符
                x_str = str(x).replace('%', '').strip()
                return float(x_str)
            except:
                return None
        
        closed_trades['profit_num'] = closed_trades[profit_col].apply(parse_profit)
        closed_trades = closed_trades.dropna(subset=['profit_num'])
        
        if closed_trades.empty:
            return {"win_rate": "0.0%", "total_trades": 0, "wins": 0, "losses": 0}
        
        # 统计胜率
        wins = (closed_trades['profit_num'] > 0).sum()
        losses = (closed_trades['profit_num'] <= 0).sum()
        total = wins + losses
        
        win_rate = (wins / total * 100) if total > 0 else 0.0
        
        return {
            "win_rate": f"{win_rate:.1f}%",
            "total_trades": total,
            "wins": wins,
            "losses": losses
        }
        
    except Exception as e:
        print(f"计算胜率时出错: {e}")
        return {"win_rate": "Error", "total_trades": 0, "wins": 0, "losses": 0}

# ==================== 4. 初始化会话状态 ====================

def initialize_session_state():
    """初始化会话状态"""
    if 'initialized' not in st.session_state:
        st.session_state.initialized = True
        st.session_state.last_update = time.time()
        st.session_state.data_fetcher = OptimizedDataFetcher()
        st.session_state.all_data_cache = {}
        st.session_state.cache_time = 0
        st.session_state.sent_cache = {}
        st.session_state.alert_logs = []
        st.session_state.positions = {}
        st.session_state.last_refresh = None

# ==================== 5. 主程序 ====================

# 设置页面
st.set_page_config(
    page_title="UT Bot Pro 交易系统",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 初始化状态
initialize_session_state()

# 侧边栏配置
st.sidebar.title("⚙️ 系统配置")

# 刷新控制
refresh_sec = st.sidebar.number_input("刷新间隔(秒)", min_value=30, max_value=600, value=300, step=30)
time_passed = time.time() - st.session_state.last_update
time_left = max(0, int(refresh_sec - time_passed))

col1, col2 = st.sidebar.columns(2)
with col1:
    if st.button("🔄 立即刷新", use_container_width=True):
        st.session_state.cache_time = 0
        st.session_state.last_update = time.time()
        st.rerun()

with col2:
    if st.button("🧹 清除缓存", use_container_width=True):
        st.session_state.cache_time = 0
        st.session_state.sent_cache.clear()
        st.session_state.all_data_cache.clear()
        st.session_state.alert_logs.clear()
        st.session_state.positions.clear()
        st.rerun()

st.sidebar.caption(f"⏰ 下次刷新: {time_left}秒后")

# 品种选择
st.sidebar.subheader("交易品种")
selected_cryptos = st.sidebar.multiselect(
    "选择监控品种", 
    CRYPTO_LIST, 
    default=CRYPTO_LIST[:5]
)

# 参数设置
st.sidebar.subheader("策略参数")
sens = st.sidebar.slider("ATR敏感度", 0.1, 5.0, 1.0, 0.1)
atrp = st.sidebar.slider("ATR周期", 1, 30, 10, 1)

# 显示系统状态
st.sidebar.subheader("系统状态")
st.sidebar.caption(f"📊 监控品种: {len(selected_cryptos)}个")
st.sidebar.caption(f"📈 持仓数量: {len(st.session_state.positions)}")
st.sidebar.caption(f"📝 信号记录: {len(st.session_state.alert_logs)}条")
st.sidebar.caption(f"💾 缓存命中: {len(st.session_state.sent_cache)}")

# ==================== 6. 数据获取与处理 ====================

if selected_cryptos:
    # 生成缓存键
    cache_key = f"{'_'.join(sorted(selected_cryptos))}_{sens}_{atrp}"
    
    # 检查是否需要更新数据
    need_refresh = (
        time.time() - st.session_state.cache_time > 60 or 
        cache_key not in st.session_state.all_data_cache or
        st.session_state.last_refresh is None or
        time.time() - st.session_state.last_refresh > refresh_sec
    )
    
    if need_refresh:
        with st.spinner(f"正在获取 {len(selected_cryptos)} 个品种数据..."):
            try:
                fetcher = st.session_state.data_fetcher
                all_data = fetcher.fetch_all_data_batch(selected_cryptos, INTERVALS)
                
                # 计算指标
                processed_data = {}
                for base in selected_cryptos:
                    processed_data[base] = {}
                    for tf in INTERVALS:
                        df = all_data.get(base, {}).get(tf, pd.DataFrame())
                        if not df.empty:
                            processed_data[base][tf] = calculate_indicators(df, sens, atrp)
                        else:
                            processed_data[base][tf] = pd.DataFrame()
                
                st.session_state.all_data_cache[cache_key] = processed_data
                st.session_state.cache_time = time.time()
                st.session_state.last_refresh = time.time()
                st.session_state.last_update = time.time()
                
            except Exception as e:
                st.error(f"数据获取失败: {e}")
                all_data = {}
    else:
        all_data = st.session_state.all_data_cache.get(cache_key, {})
else:
    all_data = {}
    st.warning("请至少选择一个交易品种")

# ==================== 7. 构建展示数据 ====================

st.title("🚀 UT Bot Pro 多重过滤交易系统")

if selected_cryptos and all_data:
    # 创建展示表格
    rows = []
    
    for base in selected_cryptos:
        price_now = "N/A"
        base_data = all_data.get(base, {})
        
        # 获取最新价格
        for t_val in ["1m", "5m", "15m"]:
            df = base_data.get(t_val, pd.DataFrame())
            if not df.empty and len(df) > 0:
                price_now = f"{df.iloc[-1]['Close']:.2f}" if 'Close' in df.columns else "N/A"
                break
        
        row_data = {"资产": base, "实时价格": price_now}
        
        # 各周期状态
        for tf in INTERVALS:
            df = base_data.get(tf, pd.DataFrame())
            if df.empty or len(df) == 0:
                row_data[tf] = "<div style='color:#888;'>-</div>"
                continue
            
            try:
                latest = df.iloc[-1]
                
                if 'Close' not in latest or 'trail_stop' not in latest:
                    row_data[tf] = "<div style='color:#888;'>数据错误</div>"
                    continue
                
                # 判断方向
                is_buy = latest['Close'] > latest['trail_stop']
                color = "#10B981" if is_buy else "#EF4444"  # 绿色和红色
                status_text = "BUY 🟢" if is_buy else "SELL 🔴"
                stop_price = f"{latest['trail_stop']:.2f}" if pd.notna(latest['trail_stop']) else "N/A"
                
                row_data[tf] = f"""
                <div style='color:{color}; font-weight:bold;'>{status_text}</div>
                <div style='font-size:0.8em; color:#888;'>止损: {stop_price}</div>
                """
                
                # 信号检测（只在预警周期）
                if tf in ALERT_INTERVALS and len(df) >= 2:
                    prev = df.iloc[-2]
                    curr = latest
                    
                    # 检查信号
                    buy_cross = (curr['Close'] > curr['trail_stop']) and (prev['Close'] <= prev['trail_stop'])
                    sell_cross = (curr['Close'] < curr['trail_stop']) and (prev['Close'] >= prev['trail_stop'])
                    
                    if buy_cross or sell_cross:
                        signal = "BUY 🟢" if buy_cross else "SELL 🔴"
                        
                        # 生成时间戳
                        sig_time_utc = df.index[-2]
                        sig_time_beijing = sig_time_utc.tz_convert(BEIJING_TZ) if sig_time_utc.tz else sig_time_utc.tz_localize('UTC').tz_convert(BEIJING_TZ)
                        sig_time_str = sig_time_beijing.strftime('%Y-%m-%d %H:%M:%S')
                        cache_key = f"{base}_{tf}_{sig_time_str}"
                        
                        # 检查是否已发送
                        if cache_key not in st.session_state.sent_cache:
                            # 计算成交量比率
                            vol_r = 1.0
                            if 'Volume' in prev and 'vol_avg' in prev and prev['vol_avg'] > 0:
                                vol_r = prev['Volume'] / prev['vol_avg']
                            vol_tag = "⚡放量" if vol_r >= 1.2 else "☁️缩量"
                            
                            # 计算OBV方向
                            obv_tag = "📉流出"
                            if 'obv' in df.columns and len(df) >= 3:
                                obv_up = prev['obv'] > df['obv'].iloc[-3]
                                obv_tag = "📈流入" if obv_up else "📉流出"
                            
                            # 三周期共振检查
                            sync_tags = {}
                            for group_name, group_tfs in RESONANCE_GROUPS.items():
                                if tf in group_tfs:
                                    group_statuses = []
                                    for g_tf in group_tfs:
                                        g_df = all_data.get(base, {}).get(g_tf, pd.DataFrame())
                                        if not g_df.empty and len(g_df) > 0:
                                            g_latest = g_df.iloc[-1]
                                            if 'Close' in g_latest and 'trail_stop' in g_latest:
                                                g_status = "BUY" if g_latest['Close'] > g_latest['trail_stop'] else "SELL"
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
                            
                            # 持仓管理
                            action_descs = {}
                            profit_strs = {}
                            
                            for group_name in RESONANCE_GROUPS:
                                pos_key = f"{base}_{tf}_{group_name}"
                                if pos_key not in st.session_state.positions:
                                    st.session_state.positions[pos_key] = {
                                        "side": "flat", 
                                        "entry_price": None, 
                                        "entry_time": None
                                    }
                                
                                pos = st.session_state.positions[pos_key]
                                action_desc = "观望中"
                                profit_str = "-"
                                
                                if group_name in sync_tags and "共振" in sync_tags[group_name]:
                                    if "做多" in sync_tags[group_name]:
                                        if pos["side"] == "long":
                                            action_desc = "继续持多"
                                        elif pos["side"] == "short":
                                            if pos["entry_price"] is not None:
                                                profit_pct = (pos["entry_price"] - curr['Close']) / pos["entry_price"] * 100
                                                profit_str = f"{profit_pct:+.2f}%"
                                            action_desc = f"平空转多"
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
                                            action_desc = f"平多转空"
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
                                    # 无共振时平仓
                                    if pos["side"] != "flat":
                                        if pos["side"] == "long":
                                            profit_pct = (curr['Close'] - pos["entry_price"]) / pos["entry_price"] * 100
                                        else:
                                            profit_pct = (pos["entry_price"] - curr['Close']) / pos["entry_price"] * 100
                                        profit_str = f"{profit_pct:+.2f}%"
                                        action_desc = f"平仓({pos['side']})"
                                        st.session_state.positions[pos_key] = {
                                            "side": "flat", 
                                            "entry_price": None, 
                                            "entry_time": None
                                        }
                                
                                action_descs[group_name] = action_desc
                                profit_strs[group_name] = profit_str
                            
                            # 创建日志记录
                            log_entry = {
                                "时间": sig_time_str,
                                "资产": base, 
                                "周期": tf, 
                                "信号": signal,
                                "能量": f"{vol_r:.1f}x {vol_tag}",
                                "OBV": obv_tag,
                                "信号价格": curr['Close'],
                                "最新价格": price_now,
                                "止损": curr['trail_stop'],
                                "ATR": curr['atr'] if 'atr' in curr else 0,
                                "成交量": curr['Volume'] if 'Volume' in curr else 0,
                                "OBV值": curr['obv'] if 'obv' in curr else 0
                            }
                            
                            # 添加组信息
                            for group_name in RESONANCE_GROUPS:
                                log_entry[f"{group_name}_共振"] = sync_tags.get(group_name, "N/A")
                                log_entry[f"{group_name}_动作"] = action_descs.get(group_name, "无动作")
                                log_entry[f"{group_name}_盈亏"] = profit_strs.get(group_name, "-")
                            
                            # 添加到日志
                            st.session_state.alert_logs.insert(0, log_entry)
                            
                            # 发送推送
                            push_title = f"{base}({tf}) {signal} | {vol_tag}"
                            push_body = f"价格: {curr['Close']:.2f}\nOBV: {obv_tag}"
                            
                            for group_name in RESONANCE_GROUPS:
                                group_info = f"{group_name}: {sync_tags.get(group_name, 'N/A')}"
                                if action_descs.get(group_name):
                                    group_info += f" | {action_descs[group_name]}"
                                if profit_strs.get(group_name) != "-":
                                    group_info += f" | {profit_strs[group_name]}"
                                push_body += f"\n{group_info}"
                            
                            # 发送推送
                            send_wx_pusher(push_title, push_body)
                            
                            # 标记为已发送
                            st.session_state.sent_cache[cache_key] = True
                            
            except Exception as e:
                print(f"处理 {base} {tf} 时出错: {e}")
                row_data[tf] = "<div style='color:#888;'>错误</div>"
        
        rows.append(row_data)
    
    # 显示主表格
    st.subheader("📊 多周期信号监控")
    
    if rows:
        disp_df = pd.DataFrame(rows)
        
        # 创建HTML表格
        html_table = """
        <style>
        .signal-table {
            width: 100%;
            border-collapse: collapse;
        }
        .signal-table th {
            background-color: #1f2937;
            color: white;
            padding: 10px;
            text-align: center;
            border: 1px solid #374151;
        }
        .signal-table td {
            padding: 8px;
            text-align: center;
            border: 1px solid #e5e7eb;
        }
        .signal-table tr:nth-child(even) {
            background-color: #f9fafb;
        }
        .signal-table tr:hover {
            background-color: #f3f4f6;
        }
        </style>
        <table class="signal-table">
        <thead>
        <tr>
        """
        
        # 表头
        columns = ["资产", "实时价格"] + INTERVALS
        for col in columns:
            html_table += f"<th>{col}</th>"
        html_table += "</tr></thead><tbody>"
        
        # 表格内容
        for _, row in disp_df.iterrows():
            html_table += "<tr>"
            for col in columns:
                value = row.get(col, "-")
                html_table += f"<td>{value}</td>"
            html_table += "</tr>"
        
        html_table += "</tbody></table>"
        
        st.markdown(html_table, unsafe_allow_html=True)
    
    # 显示日志部分
    st.divider()
    st.subheader("📜 交易信号日志")
    
    if st.session_state.alert_logs:
        log_df = pd.DataFrame(st.session_state.alert_logs)
        
        # 准备列
        required_cols = ["时间", "资产", "周期", "信号", "能量", "OBV", "信号价格", "最新价格", "止损", "ATR"]
        for group in RESONANCE_GROUPS:
            required_cols += [f"{group}_共振", f"{group}_动作", f"{group}_盈亏"]
        
        available_cols = [col for col in required_cols if col in log_df.columns]
        log_df = log_df[available_cols].copy()
        
        # 过滤近24小时数据
        try:
            log_df['时间_dt'] = pd.to_datetime(log_df['时间'], errors='coerce')
            now_beijing = datetime.now(BEIJING_TZ)
            threshold = now_beijing - timedelta(hours=24)
            recent_df = log_df[log_df['时间_dt'] >= threshold].copy()
            
            if not recent_df.empty:
                recent_df = recent_df.sort_values("时间_dt", ascending=False)
                
                # 显示统计数据
                st.caption(f"📈 近24小时共 {len(recent_df)} 条信号")
                
                # 按资产显示
                for asset in recent_df["资产"].unique():
                    asset_df = recent_df[recent_df["资产"] == asset]
                    
                    with st.expander(f"{asset} ({len(asset_df)} 条信号)", expanded=True):
                        for period in asset_df["周期"].unique():
                            period_df = asset_df[asset_df["周期"] == period]
                            
                            if not period_df.empty:
                                st.write(f"**{period} 周期** ({len(period_df)} 条)")
                                
                                # 显示表格
                                display_df = period_df.drop(columns=['时间_dt'], errors='ignore').head(20)
                                st.dataframe(
                                    display_df,
                                    use_container_width=True,
                                    hide_index=True
                                )
            else:
                st.info("近24小时内无交易信号")
                
        except Exception as e:
            st.error(f"处理日志时出错: {e}")
    else:
        st.info("暂无交易信号记录")
    
    # 持仓信息
    st.divider()
    st.subheader("💼 当前持仓")
    
    if st.session_state.positions:
        positions_list = []
        for pos_key, pos in st.session_state.positions.items():
            if pos["side"] != "flat":
                parts = pos_key.split("_")
                if len(parts) >= 3:
                    asset = parts[0]
                    timeframe = parts[1]
                    group = parts[2]
                    
                    positions_list.append({
                        "资产": asset,
                        "周期": timeframe,
                        "组别": group,
                        "方向": "多头" if pos["side"] == "long" else "空头",
                        "入场价": pos["entry_price"],
                        "入场时间": pos["entry_time"]
                    })
        
        if positions_list:
            positions_df = pd.DataFrame(positions_list)
            st.dataframe(positions_df, use_container_width=True, hide_index=True)
        else:
            st.info("当前无持仓")
    else:
        st.info("当前无持仓")

else:
    st.info("请从侧边栏选择交易品种开始监控")

# ==================== 8. 自动刷新逻辑 ====================

# 检查是否需要自动刷新
if time.time() - st.session_state.last_update > refresh_sec:
    st.session_state.last_update = time.time()
    st.rerun()

# 显示最后更新时间
st.sidebar.divider()
last_update_str = datetime.fromtimestamp(st.session_state.last_update).strftime('%H:%M:%S')
st.sidebar.caption(f"🕒 最后更新: {last_update_str}")

# 运行信息
st.sidebar.caption("🔧 系统正常运行中")
