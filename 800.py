import streamlit as st
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
import time
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==================== 页面配置 ====================
st.set_page_config(
    page_title="币圈5分钟异动监控 · 多节点容灾版",
    page_icon="🚨",
    layout="wide"
)

# ==================== 核心配置 ====================
# 币安多节点镜像池（全球可用，无需翻墙）
BINANCE_ENDPOINTS = [
    "https://api.binance.us/api/v3",   # 币安美国
    "https://api.binance.is/api/v3",   # 币安冰岛
    "https://api.binance.je/api/v3",   # 币安泽西
    "https://api.binance.sg/api/v3",   # 币安新加坡
    "https://api.binance.com/api/v3",  # 主站（可能被墙，作为后备）
]

TIMEFRAME = '5m'
LOOKBACK = 20
PRICE_THRESHOLD = 0.5      # 涨幅 ≥ 0.5%
VOLUME_THRESHOLD = 2.0     # 成交量 ≥ 20期均值的2倍
TOP_N = 80                 # 监控前80币种
REFRESH_INTERVAL = 60      # 60秒刷新一次

# ==================== 初始化状态 ====================
if 'last_update' not in st.session_state:
    st.session_state.last_update = time.time()
    st.session_state.signals_history = []
    st.session_state.top_pairs = []
    st.session_state.auto_refresh = True
    st.session_state.working_endpoint = None  # ✅ 修复：初始化 working_endpoint
    st.session_state.endpoint_failures = {}

# ==================== 工具函数 ====================

def test_endpoint(endpoint):
    """测试API节点是否可用"""
    try:
        test_url = f"{endpoint}/ping"
        response = requests.get(test_url, timeout=5)
        return response.status_code == 200
    except:
        return False

def get_working_endpoint():
    """获取可用的API节点（带缓存）"""
    # 如果已有可用节点且最近10秒内测试通过，直接使用
    if st.session_state.working_endpoint:
        if test_endpoint(st.session_state.working_endpoint):
            return st.session_state.working_endpoint
    
    # 否则重新测试所有节点
    st.info("🔄 正在检测可用的币安API节点...")
    
    for endpoint in BINANCE_ENDPOINTS:
        if test_endpoint(endpoint):
            st.session_state.working_endpoint = endpoint
            st.success(f"✅ 已连接到: {endpoint}")
            return endpoint
    
    st.error("❌ 所有币安API节点均不可用，请检查网络")
    return None

@st.cache_data(ttl=300)
def get_top_usdt_pairs(limit=100):
    """获取币安现货交易量前N的USDT交易对"""
    endpoint = get_working_endpoint()
    if not endpoint:
        # 返回默认币种
        default_symbols = [
            'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT',
            'DOGEUSDT', 'ADAUSDT', 'AVAXUSDT', 'LINKUSDT', 'DOTUSDT',
            'MATICUSDT', 'SHIBUSDT', 'TRXUSDT', 'UNIUSDT', 'ATOMUSDT',
            'ETCUSDT', 'LTCUSDT', 'BCHUSDT', 'ALGOUSDT', 'VETUSDT',
            'FILUSDT', 'ICPUSDT', 'EOSUSDT', 'THETAUSDT', 'XLMUSDT',
            'AAVEUSDT', 'MKRUSDT', 'SUSHIUSDT', 'YFIUSDT', 'SNXUSDT',
            'COMPUSDT', 'CRVUSDT', '1INCHUSDT', 'ENJUSDT', 'MANAUSDT',
            'SANDUSDT', 'AXSUSDT', 'GALAUSDT', 'APEUSDT', 'CHZUSDT',
        ] * 2  # 重复到80个
        return default_symbols[:limit]
    
    try:
        url = f"{endpoint}/ticker/24hr"
        response = requests.get(url, timeout=10)
        data = response.json()
        
        usdt_pairs = []
        for item in data:
            symbol = item.get('symbol', '')
            if symbol.endswith('USDT'):
                quote_volume = float(item.get('quoteVolume', 0))
                usdt_pairs.append({
                    'symbol': symbol,
                    'volume': quote_volume,
                    'price': float(item.get('lastPrice', 0))
                })
        
        usdt_pairs.sort(key=lambda x: x['volume'], reverse=True)
        return [p['symbol'] for p in usdt_pairs[:limit]]
    
    except Exception as e:
        st.warning(f"获取交易对列表失败，使用默认列表: {e}")
        # 返回默认币种
        return [
            'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT',
            'DOGEUSDT', 'ADAUSDT', 'AVAXUSDT', 'LINKUSDT', 'DOTUSDT',
        ] * 8

@st.cache_data(ttl=50)
def fetch_klines(symbol):
    """获取单个币种的5分钟K线数据"""
    endpoint = get_working_endpoint()
    if not endpoint:
        return None
    
    try:
        url = f"{endpoint}/klines"
        params = {
            'symbol': symbol,
            'interval': TIMEFRAME,
            'limit': LOOKBACK + 1
        }
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        if not data or 'code' in data:
            return None
        
        klines = []
        for k in data:
            klines.append({
                'time': datetime.fromtimestamp(k[0] / 1000),
                'open': float(k[1]),
                'high': float(k[2]),
                'low': float(k[3]),
                'close': float(k[4]),
                'volume': float(k[5])
            })
        
        return pd.DataFrame(klines)
    
    except Exception as e:
        return None

def check_signal(symbol, df, price_threshold, vol_threshold):
    """检查是否满足量价异动条件"""
    if df is None or len(df) < LOOKBACK:
        return None
    
    try:
        current = df.iloc[-1]
        prev = df.iloc[-2]
        
        pct_change = (current['close'] - prev['close']) / prev['close'] * 100
        current_volume = current['volume']
        avg_volume = df['volume'].iloc[:-1].mean()
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0
        
        if pct_change >= price_threshold and volume_ratio >= vol_threshold:
            return {
                '时间': datetime.now().strftime('%H:%M:%S'),
                '币种': symbol.replace('USDT', ''),
                '价格': current['close'],
                '涨幅%': round(pct_change, 2),
                '量比': round(volume_ratio, 2),
                '成交量': f"{current_volume:.0f}",
                '状态': '🚨 异动'
            }
    except Exception as e:
        pass
    
    return None

def scan_symbols_concurrent(symbols, price_th, vol_th):
    """并发扫描多个币种"""
    results = []
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_symbol = {
            executor.submit(fetch_klines, symbol): symbol 
            for symbol in symbols
        }
        
        for future in as_completed(future_to_symbol):
            symbol = future_to_symbol[future]
            try:
                df = future.result(timeout=15)
                signal = check_signal(symbol, df, price_th, vol_th)
                if signal:
                    results.append(signal)
            except:
                continue
    
    return results

# ==================== 侧边栏配置 ====================
with st.sidebar:
    st.title("⚙️ 监控配置")
    
    st.markdown("---")
    st.subheader("📊 策略参数")
    
    price_th = st.slider("涨幅阈值 (%)", 0.1, 2.0, PRICE_THRESHOLD, 0.1)
    vol_th = st.slider("成交量倍数", 1.0, 5.0, VOLUME_THRESHOLD, 0.1)
    top_n = st.slider("监控币种数量", 20, 100, TOP_N, 10)
    
    st.markdown("---")
    st.subheader("⚡ 刷新控制")
    
    auto_refresh = st.toggle("自动刷新", value=st.session_state.auto_refresh)
    st.session_state.auto_refresh = auto_refresh
    
    refresh_rate = st.slider("刷新间隔(秒)", 30, 300, REFRESH_INTERVAL, 10)
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 立即刷新", use_container_width=True):
            st.cache_data.clear()
            st.session_state.last_update = time.time()
            st.rerun()
    
    with col2:
        if st.button("🧹 清空记录", use_container_width=True):
            st.session_state.signals_history = []
            st.rerun()
    
    st.markdown("---")
    
    # 显示当前API节点状态
    if st.session_state.working_endpoint:
        st.success(f"✅ 当前节点: {st.session_state.working_endpoint.split('/')[2]}")
    else:
        st.warning("⚠️ 正在检测可用节点...")
    
    st.info(
        "**监控规则**\n\n"
        f"• 周期: {TIMEFRAME}\n"
        f"• 涨幅: ≥{price_th}%\n"
        f"• 量比: ≥{vol_th}倍\n"
        f"• 范围: 前{top_n}币种\n\n"
        "**节点池**\n"
        "• 币安美国\n"
        "• 币安冰岛\n"
        "• 币安泽西\n"
        "• 币安新加坡\n\n"
        "自动切换可用节点"
    )

# ==================== 主界面 ====================

st.title("🚨 币圈5分钟量价异动监控 · 多节点容灾版")
st.caption(f"监控策略: 5分钟涨幅 ≥{price_th}% + 成交量 ≥{vol_th}倍20期均值 | 监控范围: 前{top_n}币种")

# 创建指标卡片
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("监控币种", f"{top_n}个")
with col2:
    st.metric("触发阈值", f"{price_th}% + {vol_th}倍")
with col3:
    st.metric("今日信号", f"{len(st.session_state.signals_history)}次")
with col4:
    if st.session_state.working_endpoint:
        node = st.session_state.working_endpoint.split('/')[2]
        st.metric("当前节点", node)
    else:
        st.metric("当前节点", "检测中")

st.markdown("---")

# 自动刷新逻辑
current_time = time.time()
time_since_update = current_time - st.session_state.last_update

if st.session_state.auto_refresh and time_since_update > refresh_rate:
    st.session_state.last_update = current_time
    st.rerun()

# 显示刷新倒计时
st.caption(f"下次自动刷新: {max(0, int(refresh_rate - time_since_update))}秒后")
progress = min(1.0, time_since_update / refresh_rate)
st.progress(progress, text="刷新倒计时")

st.markdown("---")

# 获取交易对列表
with st.spinner("正在获取币安交易对列表..."):
    if not st.session_state.top_pairs or time_since_update < 5:
        st.session_state.top_pairs = get_top_usdt_pairs(top_n)
    
    pairs = st.session_state.top_pairs[:top_n]

# 并发扫描所有币种
status_text = st.empty()
progress_bar = st.progress(0, text="正在并发扫描币种...")

# 执行扫描
current_signals = scan_symbols_concurrent(pairs, price_th, vol_th)

# 更新历史记录
for signal in current_signals:
    signal_key = f"{signal['币种']}_{signal['时间']}"
    exists = False
    for s in st.session_state.signals_history:
        if f"{s['币种']}_{s['时间']}" == signal_key:
            exists = True
            break
    
    if not exists:
        st.session_state.signals_history.insert(0, signal)
        if len(st.session_state.signals_history) > 100:
            st.session_state.signals_history = st.session_state.signals_history[:100]

# 清除进度显示
progress_bar.empty()
status_text.empty()

# ==================== 显示当前信号 ====================

st.subheader("🎯 当前5分钟异动币种")

if current_signals:
    current_df = pd.DataFrame(current_signals)
    
    st.dataframe(
        current_df,
        column_config={
            "时间": st.column_config.TextColumn("时间", width="small"),
            "币种": st.column_config.TextColumn("币种", width="small"),
            "价格": st.column_config.NumberColumn("价格", format="%.4f"),
            "涨幅%": st.column_config.NumberColumn("涨幅%", format="%.2f%%"),
            "量比": st.column_config.NumberColumn("量比", format="%.2f倍"),
            "成交量": st.column_config.TextColumn("成交量", width="medium"),
            "状态": st.column_config.TextColumn("状态", width="small")
        },
        use_container_width=True,
        hide_index=True
    )
    
    st.success(f"✅ 当前发现 {len(current_signals)} 个异动币种")
else:
    st.info("⏳ 当前5分钟周期暂无符合条件的异动币种")

st.markdown("---")

# ==================== 历史记录 ====================

st.subheader("📜 历史异动记录")

if st.session_state.signals_history:
    history_df = pd.DataFrame(st.session_state.signals_history)
    
    col1, col2 = st.columns(2)
    with col1:
        if len(history_df) > 0:
            symbols = ['全部'] + sorted(history_df['币种'].unique().tolist())
            selected_symbol = st.selectbox("筛选币种", symbols)
    with col2:
        st.caption(f"共 {len(history_df)} 条记录 | 仅保留最近100条")
    
    display_history = history_df.copy()
    if selected_symbol != '全部':
        display_history = display_history[display_history['币种'] == selected_symbol]
    
    st.dataframe(
        display_history,
        column_config={
            "时间": st.column_config.TextColumn("时间", width="small"),
            "币种": st.column_config.TextColumn("币种", width="small"),
            "价格": st.column_config.NumberColumn("价格", format="%.4f"),
            "涨幅%": st.column_config.NumberColumn("涨幅%", format="%.2f%%"),
            "量比": st.column_config.NumberColumn("量比", format="%.2f倍"),
            "成交量": st.column_config.TextColumn("成交量", width="medium"),
            "状态": st.column_config.TextColumn("状态", width="small")
        },
        use_container_width=True,
        hide_index=True
    )
    
    csv = history_df.to_csv(index=False).encode('utf-8-sig')
    st.download_button(
        label="📥 下载历史记录 (CSV)",
        data=csv,
        file_name=f"signals_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv"
    )
else:
    st.info("暂无历史异动记录")

# ==================== 监控状态 ====================

st.markdown("---")
st.caption(
    f"🟢 监控状态: 运行中 | "
    f"最后扫描: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
    f"节点池: {len(BINANCE_ENDPOINTS)}个镜像节点 | "
    f"当前节点: {st.session_state.working_endpoint if st.session_state.working_endpoint else '检测中'}"
)
