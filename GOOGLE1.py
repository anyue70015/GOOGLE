import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

st.set_page_config(page_title="8:00 狙击助手", layout="wide")

# ==================== 1. 核心配置 ====================
# 使用你提供的反向代理域名
PROXY_URL = "https://www.bmwweb.academy/api/v3"

# 监控名单
REAL_TOP_COINS = [
    'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT', 'DOGEUSDT', 'ADAUSDT', 'AVAXUSDT',
    'LINKUSDT', 'DOTUSDT', 'SUIUSDT', 'PEPEUSDT', 'TAOUSDT', 'XAGUSDT', 'XAUUSDT', 'FETUSDT',
    'RENDERUSDT', 'NEARUSDT', 'APTUSDT', 'OPUSDT', 'ARBUSDT', 'WIFUSDT', 'TIAUSDT', 'AAVEUSDT',
    'SATSUSDT', 'ORDIUSDT', 'FILUSDT', 'JUPUSDT', 'ENAUSDT', 'WLDUSDT', 'SEIUSDT', 'RUNEUSDT'
]

# ==================== 2. 数据处理函数 ====================

def fetch_data(symbol):
    """通过反代接口获取5m和1d数据"""
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        # 5m线算量比
        r5m = requests.get(f"{PROXY_URL}/klines", 
                           params={'symbol': symbol, 'interval': '5m', 'limit': 21}, 
                           headers=headers, timeout=10)
        # 1d线算200MA
        r1d = requests.get(f"{PROXY_URL}/klines", 
                           params={'symbol': symbol, 'interval': '1d', 'limit': 201}, 
                           headers=headers, timeout=10)
        
        if r5m.status_code == 200 and r1d.status_code == 200:
            k5, k1 = r5m.json(), r1d.json()
            
            # --- 量比逻辑 ---
            v_curr = float(k5[-1][5])
            v_avg = sum([float(x[5]) for x in k5[:-1]]) / 20
            vr = v_curr / v_avg if v_avg > 0 else 0
            
            # --- 200MA 逻辑 ---
            closes = [float(x[4]) for x in k1]
            ma200 = sum(closes) / 200
            cp = closes[-1]
            
            # --- 合约标注 ---
            is_contract = "合约" if any(x in symbol for x in ['TAO', 'XAG', 'XAU']) else "现货"
            
            return {
                "币种": symbol.replace('USDT', ''),
                "类型": is_contract,
                "5min量比": round(vr, 2),
                "200MA状态": "🔥 趋势之上" if cp > ma200 else "❄️ 趋势之下",
                "今日涨跌%": round((cp - float(k1[-2][4])) / float(k1[-2][4]) * 100, 2),
                "价格": cp
            }
    except:
        return None

# ==================== 3. 主界面渲染 ====================

st.title("🎯 8:00 汰弱留强狙击 (反代加速版)")
st.write(f"当前节点: `{PROXY_URL}` | 刷新时间: {datetime.now().strftime('%H:%M:%S')}")

# 侧边栏设置
vol_th = st.sidebar.slider("量比触发阈值", 0.5, 5.0, 1.5, 0.1)

placeholder = st.empty()
results = []

with st.spinner("正在通过加速节点同步深度行情..."):
    # 既然有了稳定代理，并发可以稍微开大一点
    with ThreadPoolExecutor(max_workers=12) as executor:
        futures = {executor.submit(fetch_data, s): s for s in REAL_TOP_COINS}
        for future in as_completed(futures):
            res = future.result()
            if res:
                results.append(res)
                # 实时渲染表格
                df = pd.DataFrame(results).sort_values(by="5min量比", ascending=False)
                with placeholder.container():
                    st.dataframe(
                        df.style.applymap(
                            lambda x: 'background-color: #ff4b4b; color: white' if x == "🔥 趋势之上" else '',
                            subset=['200MA状态']
                        ),
                        use_container_width=True, hide_index=True, height=600
                    )

if not results:
    st.error("加速节点响应异常，请检查 URL 是否有效。")
else:
    st.success(f"✅ 成功扫描 {len(results)} 个深度币种")

# 自动刷新
time.sleep(45)
st.rerun()
