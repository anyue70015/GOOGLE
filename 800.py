import streamlit as st
import pandas as pd
import numpy as np
import requests
from datetime import datetime
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==================== 页面配置 ====================
st.set_page_config(
    page_title="BMW代理 · 币安镜像版",
    page_icon="🔄",
    layout="wide"
)

# ==================== 核心配置 ====================
BMW_API = "https://www.bmwweb.academy/api/v3"  # 你指定的域名
TIMEFRAME = '5m'
LOOKBACK = 20
PRICE_THRESHOLD = 0.5
VOLUME_THRESHOLD = 2.0
TOP_N = 80

# 真实主流币种（与版本A完全一致，保证对比公平）
REAL_TOP_COINS = [
    'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT',
    'DOGEUSDT', 'ADAUSDT', 'AVAXUSDT', 'LINKUSDT', 'DOTUSDT',
    'MATICUSDT', 'SHIBUSDT', 'TRXUSDT', 'UNIUSDT', 'ATOMUSDT',
    'ETCUSDT', 'LTCUSDT', 'BCHUSDT', 'ALGOUSDT', 'VETUSDT',
    'FILUSDT', 'ICPUSDT', 'EOSUSDT', 'THETAUSDT', 'XLMUSDT',
    'AAVEUSDT', 'MKRUSDT', 'SUSHIUSDT', 'SNXUSDT', 'COMPUSDT',
    'CRVUSDT', '1INCHUSDT', 'ENJUSDT', 'MANAUSDT', 'SANDUSDT',
    'AXSUSDT', 'GALAUSDT', 'APEUSDT', 'CHZUSDT', 'NEARUSDT',
    'FTMUSDT', 'EGLDUSDT', 'FLOWUSDT', 'KSMUSDT', 'ZECUSDT',
    'DASHUSDT', 'WAVESUSDT', 'OMGUSDT', 'ZILUSDT', 'BATUSDT',
    'ZRXUSDT', 'IOSTUSDT', 'IOTAUSDT', 'ONTUSDT', 'QTUMUSDT',
    'KAVAUSDT', 'RUNEUSDT', 'ALPHAUSDT', 'TLMUSDT', 'C98USDT',
    'KLAYUSDT', 'STXUSDT', 'ARUSDT', 'ENSUSDT', 'PEOPLEUSDT',
    'LDOUSDT', 'OPUSDT', 'ARBUSDT', 'APTUSDT', 'SUIUSDT',
    'SEIUSDT', 'TIAUSDT', 'BLURUSDT', 'JTOUSDT', 'PYTHUSDT',
    'JUPUSDT', 'WIFUSDT', 'ONDOUSDT', 'STRKUSDT', 'PENDLEUSDT',
    'ENAUSDT', 'ETHFIUSDT', 'NOTUSDT', 'ZROUSDT', 'POLUSDT'
]

# ==================== 初始化状态 ====================
if 'last_update' not in st.session_state:
    st.session_state.last_update = time.time()
    st.session_state.signals_history = []
    st.session_state.auto_refresh = True
    st.session_state.bmw_status = "unknown"

# ==================== 数据获取 ====================

@st.cache_data(ttl=3600)
def get_top_pairs():
    """直接返回硬编码的主流币种"""
    return REAL_TOP_COINS[:TOP_N]

def test_bmw_endpoint():
    """测试BMW代理是否可用"""
    try:
        url = f"{BMW_API}/ping"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            st.session_state.bmw_status = "online"
            return True
        else:
            st.session_state.bmw_status = "error"
            return False
    except:
        st.session_state.bmw_status = "offline"
        return False

def fetch_klines(symbol):
    """通过BMW代理获取K线数据"""
    try:
        url = f"{BMW_API}/klines"
        params = {
            'symbol': symbol,
            'interval': TIMEFRAME,
            'limit': LOOKBACK + 1
        }
        
        response = requests.get(url, params=params, timeout=15)
        
        # 检查响应
        if response.status_code != 200:
            return None
            
        data = response.json()
        
        if not data or isinstance(data, dict) and 'code' in data:
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

def check_signal(symbol, df):
    """检查异动信号"""
    if df is None or len(df) < LOOKBACK:
        return None
    
    try:
        current = df.iloc[-1]
        prev = df.iloc[-2]
        
        pct_change = (current['close'] - prev['close']) / prev['close'] * 100
        current_volume = current['volume']
        avg_volume = df['volume'].iloc[:-1].mean()
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0
        
        if pct_change >= PRICE_THRESHOLD and volume_ratio >= VOLUME_THRESHOLD:
            return {
                '时间': datetime.now().strftime('%H:%M:%S'),
                '币种': symbol.replace('USDT', ''),
                '价格': current['close'],
                '涨幅%': round(pct_change, 2),
                '量比': round(volume_ratio, 2),
                '成交量': f"{current_volume:.0f}",
                '状态': '🚨 异动'
            }
    except:
        pass
    return None

# ==================== 主界面 ====================

st.title("🔄 版本B：BMW代理镜像版")
st.caption(f"数据源: {BMW_API}")

# 侧边栏
with st.sidebar:
    st.title("⚙️ 版本B配置")
    
    # 测试连接
    if st.button("🔍 测试BMW代理连接"):
        with st.spinner("测试中..."):
            if test_bmw_endpoint():
                st.success("✅ BMW代理连接正常")
            else:
                st.error("❌ BMW代理无法连接")
    
    # 显示状态
    status_map = {
        "online": "✅ 在线",
        "offline": "❌ 离线",
        "error": "⚠️ 响应异常",
        "unknown": "⏳ 未测试"
    }
    st.info(f"代理状态: {status_map.get(st.session_state.bmw_status, '未知')}")
    
    if st.button("🔄 清除缓存"):
        st.cache_data.clear()
        st.rerun()

# 先测试连接
if st.session_state.bmw_status == "unknown":
    test_bmw_endpoint()

# 获取币种列表
pairs = get_top_pairs()

# 并发扫描
if st.session_state.bmw_status in ["online", "unknown"]:
    with st.spinner("正在通过BMW代理扫描..."):
        results = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_symbol = {executor.submit(fetch_klines, symbol): symbol for symbol in pairs}
            
            for future in as_completed(future_to_symbol):
                symbol = future_to_symbol[future]
                try:
                    df = future.result(timeout=15)
                    signal = check_signal(symbol, df)
                    if signal:
                        results.append(signal)
                except:
                    continue
else:
    st.error("❌ BMW代理无法连接，请测试连接状态")
    results = []

# 显示结果
st.subheader("🎯 当前5分钟异动币种")

if results:
    df_result = pd.DataFrame(results)
    st.dataframe(df_result, use_container_width=True, hide_index=True)
    st.success(f"✅ 发现 {len(results)} 个异动币种")
    
    # 更新历史记录
    for signal in results:
        st.session_state.signals_history.insert(0, signal)
        if len(st.session_state.signals_history) > 100:
            st.session_state.signals_history = st.session_state.signals_history[:100]
else:
    if st.session_state.bmw_status == "online":
        st.info("⏳ 当前周期暂无符合条件的异动币种")
    else:
        st.warning("⏳ 代理连接异常，无法获取数据")

# 显示历史记录
st.markdown("---")
st.subheader("📜 历史记录")

if st.session_state.signals_history:
    history_df = pd.DataFrame(st.session_state.signals_history[:20])
    st.dataframe(history_df, use_container_width=True, hide_index=True)
else:
    st.info("暂无历史记录")

# 状态栏
st.caption(f"最后扫描: {datetime.now().strftime('%H:%M:%S')} | 代理状态: {st.session_state.bmw_status}")
