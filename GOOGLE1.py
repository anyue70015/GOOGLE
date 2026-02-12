import streamlit as st
import pandas as pd
import numpy as np
import requests
import json
import dns.resolver
from datetime import datetime
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==================== 页面配置 ====================
st.set_page_config(
    page_title="币安总站 · Cloudflare DNS解析版",
    page_icon="🌐",
    layout="wide"
)

# ==================== 核心配置 ====================
TIMEFRAME = '5m'
LOOKBACK = 20
PRICE_THRESHOLD = 0.5
VOLUME_THRESHOLD = 2.0
TOP_N = 80

# Cloudflare DNS-over-HTTPS
CLOUDFLARE_DNS = "https://cloudflare-dns.com/dns-query"
BINANCE_DOMAIN = "api.binance.com"

# 真实主流币种（硬编码，保证有行情）
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
    st.session_state.binance_ip = None
    st.session_state.api_base = None

# ==================== Cloudflare DNS解析 ====================

def resolve_binance_via_cloudflare():
    """通过Cloudflare DNS解析币安总站真实IP"""
    try:
        headers = {"Accept": "application/dns-json"}
        params = {"name": BINANCE_DOMAIN, "type": "A"}
        
        response = requests.get(CLOUDFLARE_DNS, params=params, headers=headers, timeout=10)
        data = response.json()
        
        if 'Answer' in data:
            for answer in data['Answer']:
                if answer['type'] == 1:  # A记录
                    ip = answer['data']
                    return ip
        return None
    except Exception as e:
        st.sidebar.error(f"DNS解析失败: {e}")
        return None

def get_binance_endpoint():
    """获取币安总站API地址（通过DNS解析）"""
    if st.session_state.binance_ip and st.session_state.api_base:
        return st.session_state.api_base
    
    ip = resolve_binance_via_cloudflare()
    if ip:
        st.session_state.binance_ip = ip
        st.session_state.api_base = f"https://{ip}/api/v3"
        return st.session_state.api_base
    
    # 降级方案：直接使用域名
    st.session_state.api_base = "https://api.binance.com/api/v3"
    return st.session_state.api_base

# ==================== 数据获取 ====================

@st.cache_data(ttl=3600)
def get_top_pairs():
    """直接返回硬编码的主流币种"""
    return REAL_TOP_COINS[:TOP_N]

def fetch_klines(symbol):
    """获取K线数据"""
    endpoint = get_binance_endpoint()
    
    try:
        # 使用Host头欺骗CDN
        headers = {"Host": "api.binance.com"}
        url = f"{endpoint}/klines"
        params = {
            'symbol': symbol,
            'interval': TIMEFRAME,
            'limit': LOOKBACK + 1
        }
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
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

st.title("🌐 版本A：Cloudflare DNS + 币安总站")
st.caption("通过Cloudflare DNS解析币安总站真实IP，绕过DNS污染")

# 侧边栏
with st.sidebar:
    st.title("⚙️ 版本A配置")
    st.info(f"当前解析IP: {st.session_state.binance_ip or '解析中...'}")
    st.info(f"API地址: {st.session_state.api_base or '初始化中...'}")
    
    if st.button("🔄 强制重新解析DNS"):
        st.session_state.binance_ip = None
        st.session_state.api_base = None
        st.cache_data.clear()
        st.rerun()

# 获取币种列表
pairs = get_top_pairs()

# 并发扫描
with st.spinner("正在通过币安总站扫描..."):
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

# 显示结果
st.subheader("🎯 当前5分钟异动币种")

if results:
    df_result = pd.DataFrame(results)
    st.dataframe(df_result, use_container_width=True, hide_index=True)
    st.success(f"✅ 发现 {len(results)} 个异动币种")
else:
    st.info("⏳ 当前周期暂无符合条件的异动币种")

# 显示状态
st.caption(f"最后扫描: {datetime.now().strftime('%H:%M:%S')} | 解析IP: {st.session_state.binance_ip or '无'}")
