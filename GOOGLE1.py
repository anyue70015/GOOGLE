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
BMW_API = "https://www.bmwweb.academy/api/v3"
TIMEFRAME = '5m'
LOOKBACK = 20
PRICE_THRESHOLD = 0.5
VOLUME_THRESHOLD = 2.0
TOP_N = 80

# 真实主流币种（与版本A完全一致）
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
    st.session_state.bmw_online = None
    st.session_state.bmw_error = None
    st.session_state.consecutive_failures = 0

# ==================== 数据获取 ====================

@st.cache_data(ttl=3600)
def get_top_pairs():
    """直接返回硬编码的主流币种"""
    return REAL_TOP_COINS[:TOP_N]

def test_bmw_endpoint():
    """测试BMW代理是否可用"""
    try:
        url = f"{BMW_API}/ping"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            st.session_state.bmw_online = True
            st.session_state.bmw_error = None
            st.session_state.consecutive_failures = 0
            return True
        else:
            st.session_state.bmw_online = False
            st.session_state.bmw_error = f"HTTP {response.status_code}"
            st.session_state.consecutive_failures += 1
            return False
    except requests.exceptions.Timeout:
        st.session_state.bmw_online = False
        st.session_state.bmw_error = "连接超时"
        st.session_state.consecutive_failures += 1
        return False
    except requests.exceptions.ConnectionError:
        st.session_state.bmw_online = False
        st.session_state.bmw_error = "连接失败"
        st.session_state.consecutive_failures += 1
        return False
    except Exception as e:
        st.session_state.bmw_online = False
        st.session_state.bmw_error = str(e)[:50]
        st.session_state.consecutive_failures += 1
        return False

def fetch_klines(symbol):
    """通过BMW代理获取K线数据"""
    if not st.session_state.bmw_online:
        return None
    
    try:
        url = f"{BMW_API}/klines"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        params = {
            'symbol': symbol,
            'interval': TIMEFRAME,
            'limit': LOOKBACK + 1
        }
        
        response = requests.get(url, params=params, headers=headers, timeout=15)
        
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
    
    # 连接状态显示
    st.subheader("📡 代理状态")
    if st.session_state.bmw_online is True:
        st.success("✅ 代理在线")
    elif st.session_state.bmw_online is False:
        st.error(f"❌ 代理离线: {st.session_state.bmw_error}")
    else:
        st.info("⏳ 未测试")
    
    if st.session_state.consecutive_failures > 0:
        st.warning(f"连续失败: {st.session_state.consecutive_failures}次")
    
    # 测试连接按钮
    if st.button("🔍 测试BMW代理连接", use_container_width=True):
        with st.spinner("测试中..."):
            if test_bmw_endpoint():
                st.success("✅ BMW代理连接正常")
            else:
                st.error(f"❌ BMW代理无法连接: {st.session_state.bmw_error}")
    
    # 清除缓存
    if st.button("🔄 清除缓存", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    
    # 自动刷新开关
    st.markdown("---")
    auto_refresh = st.toggle("自动刷新", value=st.session_state.auto_refresh)
    st.session_state.auto_refresh = auto_refresh
    
    refresh_rate = st.slider("刷新间隔(秒)", 30, 300, 60, 10)

# 首次运行时自动测试连接
if st.session_state.bmw_online is None:
    test_bmw_endpoint()

# 自动刷新逻辑
current_time = time.time()
time_since_update = current_time - st.session_state.last_update

if st.session_state.auto_refresh and time_since_update > refresh_rate:
    st.session_state.last_update = current_time
    # 定时重新测试连接
    if st.session_state.consecutive_failures > 3:
        test_bmw_endpoint()
    st.rerun()

# 显示倒计时
if st.session_state.auto_refresh:
    st.caption(f"下次自动刷新: {max(0, int(refresh_rate - time_since_update))}秒后")
    progress = min(1.0, time_since_update / refresh_rate)
    st.progress(progress, text="刷新倒计时")

st.markdown("---")

# 获取币种列表
pairs = get_top_pairs()
st.caption(f"监控币种数量: {len(pairs)}个")

# 并发扫描
if st.session_state.bmw_online:
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
    results = []
    st.warning("⏳ BMW代理未连接，请先测试连接")

# 显示结果
st.subheader("🎯 当前5分钟异动币种")

if results:
    df_result = pd.DataFrame(results)
    st.dataframe(
        df_result,
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
    st.success(f"✅ 发现 {len(results)} 个异动币种")
    
    # 更新历史记录
    for signal in results:
        st.session_state.signals_history.insert(0, signal)
        if len(st.session_state.signals_history) > 100:
            st.session_state.signals_history = st.session_state.signals_history[:100]
else:
    if st.session_state.bmw_online:
        st.info("⏳ 当前5分钟周期暂无符合条件的异动币种")
    else:
        st.info("⏳ 等待代理连接...")

# 显示历史记录
st.markdown("---")
st.subheader("📜 历史异动记录")

if st.session_state.signals_history:
    history_df = pd.DataFrame(st.session_state.signals_history[:20])
    st.dataframe(
        history_df,
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
    
    # 下载按钮
    csv = pd.DataFrame(st.session_state.signals_history).to_csv(index=False).encode('utf-8-sig')
    st.download_button(
        label="📥 下载历史记录 (CSV)",
        data=csv,
        file_name=f"bmw_signals_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv"
    )
else:
    st.info("暂无历史记录")

# 状态栏
st.markdown("---")
st.caption(
    f"🟢 监控状态: 运行中 | "
    f"最后扫描: {datetime.now().strftime('%H:%M:%S')} | "
    f"代理状态: {'在线' if st.session_state.bmw_online else '离线'} | "
    f"失败次数: {st.session_state.consecutive_failures}"
)
