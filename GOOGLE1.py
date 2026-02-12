import streamlit as st
import pandas as pd
import requests
from datetime import datetime
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

st.set_page_config(page_title="8:00 汰弱留强 · 稳定版", layout="wide")

# ==================== 1. 配置与名单 ====================
REAL_TOP_COINS = [
    'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT', 'DOGEUSDT', 'ADAUSDT', 'AVAXUSDT',
    'LINKUSDT', 'DOTUSDT', 'MATICUSDT', 'SHIBUSDT', 'TRXUSDT', 'UNIUSDT', 'NEARUSDT', 'FTMUSDT',
    'LDOUSDT', 'OPUSDT', 'ARBUSDT', 'APTUSDT', 'SUIUSDT', 'PEPEUSDT', 'WIFUSDT', 'STXUSDT',
    'ORDIUSDT', 'TIAUSDT', 'FILUSDT', 'AAVEUSDT', 'RENDERUSDT', 'FETUSDT', 'TAOUSDT', 'JUPUSDT',
    'PYTHUSDT', 'ENAUSDT', 'NOTUSDT', 'SATSUSDT', 'FLOKIUSDT', 'GALAUSDT', 'GRTUSDT', 'MKRUSDT',
    'CRVUSDT', 'ETCUSDT', 'DYDXUSDT', 'ENSUSDT', 'PENDLEUSDT', 'GASUSDT', 'ARKMUSDT', 'SEIUSDT',
    'RUNEUSDT', 'OMUSDT', 'BGBUSDT', 'IMXUSDT', 'KASUSDT', 'WLDUSDT', 'BONKUSDT', 'JASMYUSDT',
    'ARUSDT', 'THETAUSDT', 'XAGUSDT', 'XAUUSDT'
]

# ==================== 2. 工具函数 ====================

def resolve_binance_ip():
    """DoH解析"""
    try:
        r = requests.get("https://dns.pub/dns-query", params={"name": "api.binance.com", "type": "A"}, 
                         headers={"Accept": "application/dns-json"}, timeout=5)
        if r.status_code == 200:
            data = r.json()
            if 'Answer' in data: return data['Answer'][0]['data']
    except: pass
    return "api.binance.com" # 失败则回退域名

def fetch_and_calc(symbol, base_url):
    """抓取数据"""
    headers = {"Host": "api.binance.com", "User-Agent": "Mozilla/5.0"}
    # 如果是 IP 直连，需要关闭证书校验的报错（注意：Cloud 环境有时必须走域名）
    verify_cert = True if "binance.com" in base_url else False
    
    try:
        # 5m 线
        r_5m = requests.get(f"{base_url}/klines", 
                            params={'symbol': symbol, 'interval': '5m', 'limit': 21}, 
                            headers=headers, timeout=8, verify=verify_cert)
        # 1d 线
        r_1d = requests.get(f"{base_url}/klines", 
                            params={'symbol': symbol, 'interval': '1d', 'limit': 201}, 
                            headers=headers, timeout=8, verify=verify_cert)
        
        if r_5m.status_code == 200 and r_1d.status_code == 200:
            k_5m, k_1d = r_5m.json(), r_1d.json()
            curr_v = float(k_5m[-1][5])
            avg_v = sum([float(x[5]) for x in k_5m[:-1]]) / 20
            vol_ratio = curr_v / avg_v if avg_v > 0 else 0
            
            closes = [float(x[4]) for x in k_1d]
            ma200 = sum(closes) / len(closes)
            curr_p = closes[-1]
            
            return {
                "币种": symbol.replace('USDT', ''),
                "类型": "合约" if any(x in symbol for x in ['TAO', 'XAG', 'XAU']) else "现货",
                "5min量比": round(vol_ratio, 2),
                "200MA状态": "🔥 趋势之上" if curr_p > ma200 else "❄️ 趋势之下",
                "价格": curr_p
            }
    except Exception as e:
        return {"error": str(e)}
    return None

# ==================== 3. 主界面 ====================

st.title("🛡️ 稳定版 · 8:00 换仓扫描")

# 初始化 URL
if 'final_api_url' not in st.session_state:
    ip = resolve_binance_ip()
    st.session_state.final_api_url = f"https://{ip}/api/v3"

base_url = st.session_state.final_api_url

# 如果直连不通，允许用户切回官方域名
if st.sidebar.button("使用官方域名直连 (如果下方全红)"):
    st.session_state.final_api_url = "https://api.binance.com/api/v3"
    st.rerun()

scan_results = []
errors = []

placeholder = st.empty()

with st.spinner("正在逐个拉取数据..."):
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_and_calc, s, base_url): s for s in REAL_TOP_COINS[:80]}
        for future in as_completed(futures):
            res = future.result()
            if res:
                if "error" in res:
                    errors.append(res["error"])
                else:
                    scan_results.append(res)
                    # 实时渲染
                    df = pd.DataFrame(scan_results).sort_values(by="5min量比", ascending=False)
                    with placeholder.container():
                        st.dataframe(df, use_container_width=True, hide_index=True)

# 调试信息显示
if not scan_results:
    st.error("❌ 依然没有数据获取成功。原因可能是币安屏蔽了当前服务器 IP。")
    if errors:
        st.write("最新报错详情（供调试）：", errors[0])

st.caption(f"当前节点: {base_url} | 报错统计: {len(errors)}")

time.sleep(60)
st.rerun()
