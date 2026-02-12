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
    page_title="8:00 汰弱留强 · 币安总站版",
    page_icon="🎯",
    layout="wide"
)

# ==================== 2. 核心参数 ====================
TIMEFRAME_5M = '5m'
TIMEFRAME_1D = '1d'
LOOKBACK_VOL = 20    # 过去20期5min均量
MA_PERIOD = 200      # 200日均线
TOP_N = 80           # 监控前80币种

# DNS与域名配置
DNS_SERVERS = ["https://dns.pub/dns-query", "https://dns.alidns.com/dns-query"]
BINANCE_DOMAIN = "api.binance.com"

# 你的核心资产清单 (根据记忆：TAO, XAG, XAU 为合约)
CORE_ASSETS = ['TAO/USDT', 'XAG/USDT', 'XAU/USDT', 'BTC/USDT', 'ETH/USDT', 'SOL/USDT']

# ==================== 3. 状态管理与DNS解析 ====================
if 'signals_history' not in st.session_state:
    st.session_state.signals_history = []
if 'api_base' not in st.session_state:
    st.session_state.api_base = None

def resolve_binance_ip():
    """DoH解析获取币安IP"""
    for dns_url in DNS_SERVERS:
        try:
            params = {"name": BINANCE_DOMAIN, "type": "A"}
            r = requests.get(dns_url, params=params, headers={"Accept": "application/dns-json"}, timeout=5)
            if r.status_code == 200:
                data = r.json()
                if 'Answer' in data:
                    return data['Answer'][0]['data']
        except: continue
    return BINANCE_DOMAIN # 失败则回退到域名

def get_base_url():
    if not st.session_state.api_base:
        ip = resolve_binance_ip()
        st.session_state.api_base = f"https://{ip}/api/v3" if ip != BINANCE_DOMAIN else f"https://{BINANCE_DOMAIN}/api/v3"
    return st.session_state.api_base

# ==================== 4. 数据抓取与逻辑计算 ====================

def fetch_data(symbol):
    """同时获取5min线和日线数据"""
    base_url = get_base_url()
    headers = {"Host": BINANCE_DOMAIN, "User-Agent": "Mozilla/5.0"}
    clean_sym = symbol.replace('/', '')
    
    try:
        # 1. 获取5min线 (算量比)
        r_5m = requests.get(f"{base_url}/klines", params={'symbol': clean_sym, 'interval': '5m', 'limit': 21}, headers=headers, timeout=5)
        # 2. 获取日线 (算200MA)
        r_1d = requests.get(f"{base_url}/klines", params={'symbol': clean_sym, 'interval': '1d', 'limit': 201}, headers=headers, timeout=5)
        
        if r_5m.status_code == 200 and r_1d.status_code == 200:
            df_5m = pd.DataFrame(r_5m.json(), columns=['t','o','h','l','c','v','ot','qv','nt','tbv','tqv','i'])
            df_1d = pd.DataFrame(r_1d.json(), columns=['t','o','h','l','c','v','ot','qv','nt','tbv','tqv','i'])
            
            # --- 精准计算 ---
            # 量比: 当前5min成交量 / 过去20根5min均值
            curr_vol = float(df_5m.iloc[-1]['v'])
            avg_vol = df_5m.iloc[:-1]['v'].astype(float).mean()
            vol_ratio = curr_vol / avg_vol if avg_vol > 0 else 0
            
            # 200MA: 
            curr_price = float(df_1d.iloc[-1]['c'])
            ma200 = df_1d['c'].astype(float).mean()
            status = "🔥 趋势之上" if curr_price > ma200 else "❄️ 趋势之下"
            dist = (curr_price - ma200) / ma200 * 100
            
            # 涨跌
            pct = (curr_price - float(df_1d.iloc[-2]['c'])) / float(df_1d.iloc[-2]['c']) * 100
            
            return {
                "币种": symbol,
                "类型": "合约" if any(x in symbol for x in ['TAO', 'XAG', 'XAU']) else "现货",
                "5min量比": round(vol_ratio, 2),
                "200MA状态": status,
                "偏离200MA%": round(dist, 2),
                "今日涨跌%": round(pct, 2),
                "当前价": curr_price
            }
    except: return None

# ==================== 5. 主界面渲染 ====================

st.title("🎯 8:00 汰弱留强精准监控 (Binance DNS版)")
st.caption(f"解析节点: {get_base_url()} | 核心逻辑：5min量比爆发 + 200日趋势过滤")

# 侧边栏
with st.sidebar:
    st.header("⚙️ 监控设置")
    vol_threshold = st.slider("信号触发量比", 1.0, 5.0, 2.0, 0.1)
    auto_refresh = st.toggle("自动刷新", True)
    if st.button("清空历史"): st.session_state.signals_history = []

# 获取名单并并发扫描
# 这里复用你REAL_TOP_COINS的逻辑，但为了格式统一加个/USDT
formatted_coins = [s if '/' in s else f"{s[:-4]}/USDT" for s in REAL_TOP_COINS[:TOP_N]]

placeholder = st.empty()
all_results = []

with st.spinner("正在并发扫描全盘数据..."):
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(fetch_data, sym): sym for sym in formatted_coins}
        for future in as_completed(futures):
            res = future.result()
            if res:
                all_results.append(res)
                # 实时更新展示
                df_tmp = pd.DataFrame(all_results).sort_values(by="5min量比", ascending=False)
                with placeholder.container():
                    # 样式：200MA之上标红
                    st.dataframe(
                        df_tmp.style.applymap(lambda x: 'background-color: #ff4b4b; color: white' if x == "🔥 趋势之上" else '', subset=['200MA状态']),
                        use_container_width=True, height=600
                    )

# 历史异动记录逻辑
current_signals = [r for r in all_results if r['5min量比'] >= vol_threshold and r['200MA状态'] == "🔥 趋势之上"]
for s in current_signals:
    s_log = s.copy()
    s_log['记录时间'] = datetime.now().strftime('%H:%M:%S')
    st.session_state.signals_history.insert(0, s_log)

st.divider()
st.subheader("📜 历史爆发记录 (符合汰弱留强条件)")
if st.session_state.signals_history:
    st.table(pd.DataFrame(st.session_state.signals_history).head(15))

# 自动刷新倒计时
if auto_refresh:
    time.sleep(30)
    st.rerun()
