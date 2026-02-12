import streamlit as st
import pandas as pd
import numpy as np
import requests
import json
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
PRICE_THRESHOLD = 0.5      # 涨幅 ≥ 0.5%
VOLUME_THRESHOLD = 2.0     # 成交量 ≥ 20期均值的2倍
TOP_N = 80                 # 监控前80币种

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
    'ENAUSDT', 'ETHFIUSDT', 'NOTUSDT', 'ZROUSDT', 'POLUSDT',
    'WIFUSDT', 'ONDOUSDT', 'STRKUSDT', 'PENDLEUSDT', 'ENAUSDT'
]

# ==================== 初始化状态 ====================
if 'last_update' not in st.session_state:
    st.session_state.last_update = time.time()
    st.session_state.signals_history = []
    st.session_state.auto_refresh = True
    st.session_state.binance_ip = None
    st.session_state.api_base = None
    st.session_state.dns_error = None
    st.session_state.refresh_rate = 60
    st.session_state.price_threshold = PRICE_THRESHOLD
    st.session_state.volume_threshold = VOLUME_THRESHOLD
    st.session_state.top_n = TOP_N

# ==================== Cloudflare DNS解析（纯HTTP） ====================

def resolve_binance_via_cloudflare():
    """通过Cloudflare DNS-over-HTTPS解析币安总站真实IP（纯HTTP，无需dnspython）"""
    try:
        headers = {
            "Accept": "application/dns-json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        params = {
            "name": BINANCE_DOMAIN,
            "type": "A"
        }
        
        response = requests.get(CLOUDFLARE_DNS, params=params, headers=headers, timeout=10)
        
        if response.status_code != 200:
            st.session_state.dns_error = f"DNS服务返回{response.status_code}"
            return None
            
        data = response.json()
        
        if 'Answer' in data:
            for answer in data['Answer']:
                if answer.get('type') == 1:  # A记录
                    ip = answer.get('data')
                    st.session_state.dns_error = None
                    return ip
        
        st.session_state.dns_error = "未找到A记录"
        return None
        
    except requests.exceptions.Timeout:
        st.session_state.dns_error = "DNS解析超时"
        return None
    except requests.exceptions.ConnectionError:
        st.session_state.dns_error = "无法连接Cloudflare DNS"
        return None
    except Exception as e:
        st.session_state.dns_error = f"解析异常: {str(e)[:50]}"
        return None

def get_binance_endpoint():
    """获取币安总站API地址（通过DNS解析）"""
    # 如果已经有缓存的可用节点，直接返回
    if st.session_state.api_base:
        return st.session_state.api_base
    
    # 尝试DNS解析
    ip = resolve_binance_via_cloudflare()
    if ip:
        st.session_state.binance_ip = ip
        st.session_state.api_base = f"https://{ip}/api/v3"
        st.session_state.dns_error = None
        return st.session_state.api_base
    
    # DNS解析失败，使用直接域名连接（可能会被墙）
    st.session_state.api_base = "https://api.binance.com/api/v3"
    return st.session_state.api_base

def test_endpoint():
    """测试当前端点是否可用"""
    endpoint = get_binance_endpoint()
    try:
        headers = {"Host": "api.binance.com"}
        test_url = f"{endpoint}/ping"
        response = requests.get(test_url, headers=headers, timeout=5)
        return response.status_code == 200
    except:
        return False

# ==================== 数据获取 ====================

@st.cache_data(ttl=3600)
def get_top_pairs(limit):
    """直接返回硬编码的主流币种"""
    return REAL_TOP_COINS[:limit]

def fetch_klines(symbol):
    """获取K线数据"""
    endpoint = get_binance_endpoint()
    
    try:
        # 使用Host头欺骗CDN
        headers = {
            "Host": "api.binance.com",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        url = f"{endpoint}/klines"
        params = {
            'symbol': symbol,
            'interval': TIMEFRAME,
            'limit': LOOKBACK + 1
        }
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        
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

def check_signal(symbol, df, price_th, vol_th):
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
        
        if pct_change >= price_th and volume_ratio >= vol_th:
            return {
                '时间': datetime.now().strftime('%H:%M:%S'),
                '币种': symbol.replace('USDT', ''),
                '价格': f"{current['close']:.4f}",
                '涨幅%': f"{pct_change:.2f}%",
                '量比': f"{volume_ratio:.2f}倍",
                '成交量': f"{current_volume:,.0f}",
                '状态': '🚨 异动'
            }
    except:
        pass
    return None

# ==================== 侧边栏配置 ====================
with st.sidebar:
    st.title("⚙️ 版本A配置")
    
    st.subheader("📊 策略参数")
    price_th = st.slider("涨幅阈值 (%)", 0.1, 2.0, st.session_state.price_threshold, 0.1)
    vol_th = st.slider("成交量倍数", 1.0, 5.0, st.session_state.volume_threshold, 0.1)
    top_n = st.slider("监控币种数量", 20, 100, st.session_state.top_n, 10)
    
    # 更新session状态
    st.session_state.price_threshold = price_th
    st.session_state.volume_threshold = vol_th
    st.session_state.top_n = top_n
    
    st.markdown("---")
    
    st.subheader("📡 DNS解析状态")
    if st.session_state.binance_ip:
        st.success(f"✅ 解析成功: {st.session_state.binance_ip}")
        st.info(f"🌍 API: {st.session_state.api_base}")
    elif st.session_state.dns_error:
        st.error(f"❌ 解析失败: {st.session_state.dns_error}")
        st.info("🌍 使用备用域名: api.binance.com")
    else:
        st.info("⏳ 正在解析DNS...")
    
    # 测试连接按钮
    if st.button("🔍 测试连接", use_container_width=True):
        with st.spinner("测试中..."):
            if test_endpoint():
                st.success("✅ 连接正常")
            else:
                st.error("❌ 连接失败")
    
    # 强制重新解析
    if st.button("🔄 强制重新解析DNS", use_container_width=True):
        st.session_state.binance_ip = None
        st.session_state.api_base = None
        st.session_state.dns_error = None
        st.cache_data.clear()
        st.rerun()
    
    st.markdown("---")
    
    st.subheader("⚡ 刷新控制")
    auto_refresh = st.toggle("自动刷新", value=st.session_state.auto_refresh)
    st.session_state.auto_refresh = auto_refresh
    
    refresh_rate = st.slider("刷新间隔(秒)", 30, 300, st.session_state.refresh_rate, 10)
    st.session_state.refresh_rate = refresh_rate
    
    if st.button("🧹 清空历史记录", use_container_width=True):
        st.session_state.signals_history = []
        st.rerun()

# ==================== 主界面 ====================

st.title("🌐 版本A：Cloudflare DNS + 币安总站")
st.caption("通过Cloudflare DNS-over-HTTPS解析币安总站真实IP，绕过DNS污染")

# 指标卡片
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("监控币种", f"{top_n}个")
with col2:
    st.metric("触发阈值", f"{price_th}% + {vol_th}倍")
with col3:
    st.metric("今日信号", f"{len(st.session_state.signals_history)}次")
with col4:
    if st.session_state.binance_ip:
        st.metric("当前节点", "IP直连")
    else:
        st.metric("当前节点", "域名直连")

st.markdown("---")

# 自动刷新逻辑
current_time = time.time()
time_since_update = current_time - st.session_state.last_update

if st.session_state.auto_refresh and time_since_update > st.session_state.refresh_rate:
    st.session_state.last_update = current_time
    st.rerun()

# 显示倒计时
if st.session_state.auto_refresh:
    col1, col2 = st.columns([3, 1])
    with col1:
        progress = min(1.0, time_since_update / st.session_state.refresh_rate)
        st.progress(progress, text=f"下次自动刷新: {max(0, int(st.session_state.refresh_rate - time_since_update))}秒后")
    with col2:
        st.caption(f"{datetime.now().strftime('%H:%M:%S')}")

st.markdown("---")

# 获取币种列表
pairs = get_top_pairs(top_n)
st.caption(f"📊 监控币种列表: {', '.join([p.replace('USDT', '') for p in pairs[:10]])}...等{len(pairs)}个币种")

# 并发扫描
with st.spinner("正在通过币安总站扫描5分钟异动..."):
    results = []
    failed_count = 0
    
    with ThreadPoolExecutor(max_workers=15) as executor:
        future_to_symbol = {executor.submit(fetch_klines, symbol): symbol for symbol in pairs}
        
        for future in as_completed(future_to_symbol):
            symbol = future_to_symbol[future]
            try:
                df = future.result(timeout=15)
                if df is not None:
                    signal = check_signal(symbol, df, price_th, vol_th)
                    if signal:
                        results.append(signal)
                else:
                    failed_count += 1
            except:
                failed_count += 1
                continue

# 显示结果
st.subheader("🎯 当前5分钟异动币种")

if results:
    # 按涨幅排序
    results.sort(key=lambda x: float(x['涨幅%'].rstrip('%')), reverse=True)
    df_result = pd.DataFrame(results)
    
    st.dataframe(
        df_result,
        column_config={
            "时间": st.column_config.TextColumn("时间", width=80),
            "币种": st.column_config.TextColumn("币种", width=80),
            "价格": st.column_config.TextColumn("价格", width=100),
            "涨幅%": st.column_config.TextColumn("涨幅%", width=80),
            "量比": st.column_config.TextColumn("量比", width=80),
            "成交量": st.column_config.TextColumn("成交量", width=120),
            "状态": st.column_config.TextColumn("状态", width=80)
        },
        use_container_width=True,
        hide_index=True
    )
    
    st.success(f"✅ 本周期发现 {len(results)} 个异动币种 | 扫描失败: {failed_count}个")
    
    # 更新历史记录
    for signal in results:
        # 去重
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
else:
    if st.session_state.binance_ip:
        st.info(f"⏳ 当前5分钟周期暂无符合条件的异动币种 | 扫描失败: {failed_count}个")
    else:
        st.warning("⏳ DNS解析中，使用备用域名连接...")

st.markdown("---")

# ==================== 历史记录 ====================

st.subheader("📜 历史异动记录")

if st.session_state.signals_history:
    # 筛选功能
    col1, col2 = st.columns(2)
    with col1:
        history_df = pd.DataFrame(st.session_state.signals_history)
        symbols = ['全部'] + sorted(history_df['币种'].unique().tolist())
        selected_symbol = st.selectbox("筛选币种", symbols, key="history_filter")
    with col2:
        st.caption(f"共 {len(history_df)} 条记录 | 仅保留最近100条")
    
    # 应用筛选
    display_history = history_df.copy()
    if selected_symbol != '全部':
        display_history = display_history[display_history['币种'] == selected_symbol]
    
    st.dataframe(
        display_history.head(20),
        column_config={
            "时间": st.column_config.TextColumn("时间", width=80),
            "币种": st.column_config.TextColumn("币种", width=80),
            "价格": st.column_config.TextColumn("价格", width=100),
            "涨幅%": st.column_config.TextColumn("涨幅%", width=80),
            "量比": st.column_config.TextColumn("量比", width=80),
            "成交量": st.column_config.TextColumn("成交量", width=120),
            "状态": st.column_config.TextColumn("状态", width=80)
        },
        use_container_width=True,
        hide_index=True
    )
    
    # 下载按钮
    col1, col2 = st.columns(2)
    with col1:
        csv = history_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 下载全部历史记录 (CSV)",
            data=csv,
            file_name=f"cloudflare_signals_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
            use_container_width=True
        )
    with col2:
        if st.button("🧹 清空历史记录", use_container_width=True):
            st.session_state.signals_history = []
            st.rerun()
else:
    st.info("暂无历史异动记录")

# ==================== 监控状态 ====================

st.markdown("---")
st.caption(
    f"🟢 监控状态: 运行中 | "
    f"最后扫描: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
    f"DNS状态: {st.session_state.binance_ip or '域名直连'} | "
    f"{st.session_state.dns_error or '正常'}"
)

st.caption(
    f"📊 策略: {TIMEFRAME}周期 | 涨幅≥{price_th}% | 量比≥{vol_th}倍 | "
    f"监控{top_n}个主流币种 | 数据源: 币安总站 via Cloudflare DNS"
)
