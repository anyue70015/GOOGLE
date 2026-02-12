import streamlit as st
import pandas as pd
import requests
import time
import random
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

st.set_page_config(page_title="8:00 币安深度版", layout="wide")

# ==================== 1. 币安全球备用域名池 ====================
# api1, api2, api3 是币安分布在不同地区的负载均衡，能有效绕过单点封锁
BINANCE_ENDPOINTS = [
    "https://api.binance.com/api/v3",
    "https://api1.binance.com/api/v3",
    "https://api2.binance.com/api/v3",
    "https://api3.binance.com/api/v3"
]

REAL_TOP_COINS = [
    'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT', 'DOGEUSDT', 'ADAUSDT', 'AVAXUSDT',
    'LINKUSDT', 'DOTUSDT', 'SUIUSDT', 'PEPEUSDT', 'TAOUSDT', 'XAGUSDT', 'XAUUSDT', 'FETUSDT',
    'RENDERUSDT', 'NEARUSDT', 'APTUSDT', 'OPUSDT', 'ARBUSDT', 'WIFUSDT', 'TIAUSDT', 'AAVEUSDT'
]

# ==================== 2. 核心抓取逻辑 ====================

def fetch_with_retry(symbol):
    """带随机伪装和域名轮询的抓取"""
    # 随机选择一个域名，分散请求压力
    base_url = random.choice(BINANCE_ENDPOINTS)
    
    # 随机 User-Agent 伪装成浏览器
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
    ]
    headers = {"User-Agent": random.choice(user_agents)}
    
    try:
        # 5m线和1d线
        r5m = requests.get(f"{base_url}/klines", params={'symbol': symbol, 'interval': '5m', 'limit': 21}, headers=headers, timeout=5)
        r1d = requests.get(f"{base_url}/klines", params={'symbol': symbol, 'interval': '1d', 'limit': 201}, headers=headers, timeout=5)
        
        if r5m.status_code == 200 and r1d.status_code == 200:
            k5, k1 = r5m.json(), r1d.json()
            # 量比计算
            v_curr = float(k5[-1][5])
            v_avg = sum([float(x[5]) for x in k5[:-1]]) / 20
            vr = v_curr / v_avg if v_avg > 0 else 0
            
            # 200MA
            closes = [float(x[4]) for x in k1]
            ma200 = sum(closes) / 200
            cp = closes[-1]
            
            return {
                "币种": symbol,
                "5min量比": round(vr, 2),
                "200MA状态": "🔥 趋势之上" if cp > ma200 else "❄️ 趋势之下",
                "今日涨跌%": round((cp - float(k1[-2][4])) / float(k1[-2][4]) * 100, 2),
                "价格": cp
            }
        elif r5m.status_code == 451:
            return {"error": "地区限制(451)"}
    except Exception as e:
        return {"error": str(e)}
    return None

# ==================== 3. 主界面 ====================

st.title("🎯 币安深度 · 汰弱留强")
st.write(f"当前时间: {datetime.now().strftime('%H:%M:%S')} | 数据源: Binance Global")

placeholder = st.empty()
results = []
blocked_count = 0

with st.spinner("正在穿透币安防火墙..."):
    # 降低并发数到 5，减小被封风险
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(fetch_with_retry, s): s for s in REAL_TOP_COINS}
        for future in as_completed(futures):
            res = future.result()
            if res:
                if "error" in res:
                    if "451" in res["error"]: blocked_count += 1
                else:
                    results.append(res)
                    df = pd.DataFrame(results).sort_values(by="5min量比", ascending=False)
                    with placeholder.container():
                        st.dataframe(df, use_container_width=True, hide_index=True)

if blocked_count > 0:
    st.warning(f"⚠️ 检测到 {blocked_count} 次地区限制(451)，Streamlit Cloud 已被币安屏蔽。")

# 自动刷新
time.sleep(60)
st.rerun()
