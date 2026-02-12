import streamlit as st
import pandas as pd
import numpy as np
import requests
import json
from datetime import datetime
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==================== 1. 页面配置 ====================
st.set_page_config(
    page_title="8:00 汰弱留强 · 终极监控",
    page_icon="🎯",
    layout="wide"
)

# ==================== 2. 核心参数与币种名单 ====================
LOOKBACK_VOL = 20    # 过去20期5min均量
MA_PERIOD = 200      # 200日均线判定
TOP_N = 80           # 监控总数

REAL_TOP_COINS = [
    'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT', 'DOGEUSDT', 'ADAUSDT', 'AVAXUSDT',
    'LINKUSDT', 'DOTUSDT', 'MATICUSDT', 'SHIBUSDT', 'TRXUSDT', 'UNIUSDT', 'NEARUSDT', 'FTMUSDT',
    'LDOUSDT', 'OPUSDT', 'ARBUSDT', 'APTUSDT', 'SUIUSDT', 'PEPEUSDT', 'WIFUSDT', 'STXUSDT',
    'ORDIUSDT', 'TIAUSDT', 'FILUSDT', 'AAVEUSDT', 'RENDERUSDT', 'FETUSDT', 'TAOUSDT', 'JUPUSDT',
    'PYTHUSDT', 'ENAUSDT', 'NOTUSDT', 'SATSUSDT', 'FLOKIUSDT', 'GALAUSDT', 'GRTUSDT', 'MKRUSDT',
    'CRVUSDT', 'ETCUSDT', 'DYDXUSDT', 'ENSUSDT', 'PENDLEUSDT', 'GASUSDT', 'ARKMUSDT', 'SEIUSDT',
    'RUNEUSDT', 'OMUSDT', 'BGBUSDT', 'IMXUSDT', 'KASUSDT', 'WLDUSDT', 'BONKUSDT', 'JASMYUSDT',
    'ARUSDT', 'THETAUSDT', 'XAGUSDT', 'XAUUSDT', 'LUNAUSDT', 'USTCUSDT', 'FLOWUSDT', 'AXSUSDT',
    'SANDUSDT', 'MANAUSDT', 'CHZUSDT', 'APEUSDT', 'ICPUSDT', 'ZILUSDT', 'EGLDUSDT', 'IOTAUSDT',
    'KAVAUSDT', 'ANKRUSDT', 'WAVESUSDT', 'ROSEUSDT', 'SNXUSDT', 'DYMUSDT', 'STRKUSDT', 'AXLUSDT'
]

DNS_SERVERS = ["https://dns.pub/dns-query", "https://dns.alidns.com/dns-query"]
BINANCE_DOMAIN = "api.binance.com"

# ==================== 3. 核心功能函数 ====================

# 初始化全局变量
if 'signals_history' not in st.session_state:
    st.session_state.signals_history = []

def resolve_binance_ip():
    """通过DNS解析获取IP"""
    headers = {"Accept": "application/dns-json"}
    for dns_url in DNS_SERVERS:
        try:
            params = {"name": BINANCE_DOMAIN, "type": "A"}
            r = requests.get(dns_url, params=params, headers=headers, timeout=5)
            if r.status_code == 200:
                data = r.json()
                if 'Answer' in data:
                    return data['Answer'][0]['data']
        except: continue
    return BINANCE_DOMAIN

def fetch_and_calc(symbol, base_url):
    """注意：base_url 现在是作为参数传入，不读取 session_state"""
    headers = {"Host": BINANCE_DOMAIN, "User-Agent": "Mozilla/5.0"}
    try:
        # 5m线算量比
        r_5m = requests.get(f"{base_url}/klines", params={'symbol': symbol, 'interval': '5m', 'limit': 21}, headers=headers, timeout=5)
        # 1d线算200MA
        r_1d = requests.get(f"{base_url}/klines", params={'symbol': symbol, 'interval': '1d', 'limit': 201}, headers=headers, timeout=5)
        
        if r_5m.status_code == 200 and r_1d.status_code == 200:
            k_5m = r_5m.json()
            k_1d = r_1d.json()
            
            curr_v = float(k_5m[-1][5])
            avg_v = sum([float(x[5]) for x in k_5m[:-1]]) / (len(k_5m)-1)
            vol_ratio = curr_v / avg_v if avg_v > 0 else 0
            
            closes = [float(x[4]) for x in k_1d]
            ma200 = sum(closes) / len(closes)
            curr_p = closes[-1]
            
            status = "🔥 趋势之上" if curr_p > ma200 else "❄️ 趋势之下"
            dist = (curr_p - ma200) / ma200 * 100
            pct = (curr_p - float(k_1d[-2][4])) / float(k_1d[-2][4]) * 100
            
            is_contract = "合约" if any(x in symbol for x in ['TAO', 'XAG', 'XAU']) else "现货"
            
            return {
                "币种": symbol.replace('USDT', ''),
                "类型": is_contract,
                "5min量比": round(vol_ratio, 2),
                "200MA状态": status,
                "偏离200MA%": round(dist, 2),
                "今日涨跌%": round(pct, 2),
                "价格": curr_p
            }
    except: return None

# ==================== 4. 主流程 ====================

st.title("🌐 8:00 汰弱留强看板")

# 1. 在主线程提前解析好 IP (避开多线程 session_state 限制)
if 'static_base_url' not in st.session_state or st.sidebar.button("🔄 刷新域名解析"):
    ip = resolve_binance_ip()
    st.session_state.static_base_url = f"https://{ip}/api/v3"

current_base_url = st.session_state.static_base_url

with st.sidebar:
    st.header("⚙️ 监控配置")
    vol_th = st.slider("信号触发量比", 1.0, 5.0, 2.5, 0.1)
    if st.button("🧹 清除历史"):
        st.session_state.signals_history = []

placeholder = st.empty()
scan_results = []

# 并发扫描
with st.spinner(f"正在扫描前 {TOP_N} 个币种..."):
    # 将 current_base_url 作为参数传递给子线程
    with ThreadPoolExecutor(max_workers=15) as executor:
        futures = {executor.submit(fetch_and_calc, s, current_base_url): s for s in REAL_TOP_COINS[:TOP_N]}
        for future in as_completed(futures):
            res = future.result()
            if res:
                scan_results.append(res)
                df_show = pd.DataFrame(scan_results).sort_values(by="5min量比", ascending=False)
                with placeholder.container():
                    st.dataframe(
                        df_show.style.applymap(
                            lambda x: 'background-color: #ff4b4b; color: white' if x == "🔥 趋势之上" else 'color: #888888',
                            subset=['200MA状态']
                        ),
                        use_container_width=True, height=600, hide_index=True
                    )

# 历史记录逻辑
current_signals = [r for r in scan_results if r['5min量比'] >= vol_th and r['200MA状态'] == "🔥 趋势之上"]
for s in current_signals:
    if s['币种'] not in [h['币种'] for h in st.session_state.signals_history[:5]]:
        s_log = s.copy()
        s_log['捕获时间'] = datetime.now().strftime('%H:%M:%S')
        st.session_state.signals_history.insert(0, s_log)

st.divider()
st.subheader("📜 历史爆发记录")
if st.session_state.signals_history:
    st.dataframe(pd.DataFrame(st.session_state.signals_history).head(20), use_container_width=True, hide_index=True)

st.caption(f"🟢 正常运行 | 节点: {current_base_url} | 刷新: {datetime.now().strftime('%H:%M:%S')}")

# 自动刷新
time.sleep(45)
st.rerun()
