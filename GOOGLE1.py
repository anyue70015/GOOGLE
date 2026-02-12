import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==================== 1. 页面与接口配置 ====================
st.set_page_config(page_title="8:00 现货汰弱留强", layout="wide")

# 你的专属反代接口
PROXY_URL = "https://www.bmwweb.academy/api/v3"

# 严格筛选的 80 个币安活跃现货币种 (已移除 XAG, XAU)
REAL_TOP_COINS = [
    'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'TAOUSDT', 'XRPUSDT', 'DOGEUSDT', 
    'AVAXUSDT', 'ADAUSDT', 'LINKUSDT', 'DOTUSDT', 'NEARUSDT', 'SUIUSDT', 'APTUSDT', 
    'OPUSDT', 'ARBUSDT', 'TIAUSDT', 'SEIUSDT', 'INJUSDT', 'STXUSDT', 'FTMUSDT', 
    'PEPEUSDT', 'WIFUSDT', 'SHIBUSDT', 'FLOKIUSDT', 'BONKUSDT', 'FETUSDT', 
    'RENDERUSDT', 'ARKMUSDT', 'LDOUSDT', 'AAVEUSDT', 'PENDLEUSDT', 'MKRUSDT', 
    'UNIUSDT', 'JUPUSDT', 'PYTHUSDT', 'ENAUSDT', 'RUNEUSDT', 'NOTUSDT', 'WLDUSDT', 
    'ORDIUSDT', 'SATSUSDT', 'STRKUSDT', 'ZROUSDT', 'EIGENUSDT', 'ZKUSDT', 'ICPUSDT', 
    'FILUSDT', 'ATOMUSDT', 'HBARUSDT', 'VETUSDT', 'LTCUSDT', 'BCHUSDT', 'TRXUSDT', 
    'ETCUSDT', 'THETAUSDT', 'KASUSDT', 'FLOWUSDT', 'AXLUSDT', 'GALAUSDT', 'CHZUSDT', 
    'CRVUSDT', 'ENSUSDT', 'DYDXUSDT', 'MANAUSDT', 'SANDUSDT', 'ASTRUSDT', 'IOUSDT', 
    'SCRUSDT', 'ONTUSDT', 'EGLDUSDT', 'KAVAUSDT', 'ALGOUSDT', 'GRTUSDT', 'PHBUSDT', 
    'AGIXUSDT', 'JTOUSDT', 'TNSRUSDT', 'FLRUSDT', 'GASUSDT'
]

# ==================== 2. 核心抓取逻辑 ====================

def fetch_spot_data(symbol):
    """纯现货 K 线数据获取"""
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        # 5min K线用于量比计算 (取21根)
        r5m = requests.get(f"{PROXY_URL}/klines", 
                           params={'symbol': symbol, 'interval': '5m', 'limit': 21}, 
                           headers=headers, timeout=8)
        # 日线用于 200MA 计算 (取201根)
        r1d = requests.get(f"{PROXY_URL}/klines", 
                           params={'symbol': symbol, 'interval': '1d', 'limit': 201}, 
                           headers=headers, timeout=8)
        
        if r5m.status_code == 200 and r1d.status_code == 200:
            k5, k1 = r5m.json(), r1d.json()
            
            # --- 精准量比计算 ---
            v_curr = float(k5[-1][5])
            v_avg = sum([float(x[5]) for x in k5[:-1]]) / 20
            vr = v_curr / v_avg if v_avg > 0 else 0
            
            # --- 200MA 趋势判定 ---
            closes = [float(x[4]) for x in k1]
            ma200 = sum(closes) / 200
            cp = closes[-1]
            
            # --- 24h 涨跌幅 ---
            pct = (cp - float(k1[-2][4])) / float(k1[-2][4]) * 100
            
            return {
                "币种": symbol.replace('USDT', ''),
                "5min量比": round(vr, 2),
                "200MA状态": "🔥 趋势之上" if cp > ma200 else "❄️ 趋势之下",
                "偏离200MA%": round((cp - ma200) / ma200 * 100, 2),
                "今日涨跌%": round(pct, 2),
                "当前价": cp
            }
    except:
        return None

# ==================== 3. Streamlit 渲染 ====================

st.title("🛡️ 8:00 现货汰弱留强监控")
st.caption(f"已移除 XAG/XAU，专注于币安成交量前 80 的现货资产")

# 侧边栏阈值
vol_th = st.sidebar.slider("量比报警阈值", 0.1, 5.0, 1.5, 0.1)

placeholder = st.empty()
scan_results = []

# 并发扫描执行
with st.spinner("同步全盘现货深度数据..."):
    with ThreadPoolExecutor(max_workers=15) as executor:
        futures = {executor.submit(fetch_spot_data, s): s for s in REAL_TOP_COINS}
        for future in as_completed(futures):
            res = future.result()
            if res:
                scan_results.append(res)
                # 排序并展示
                df = pd.DataFrame(scan_results).sort_values(by="5min量比", ascending=False)
                with placeholder.container():
                    st.dataframe(
                        df.style.applymap(
                            lambda x: 'background-color: #ff4b4b; color: white' if x == "🔥 趋势之上" else 'color: #808080',
                            subset=['200MA状态']
                        ),
                        use_container_width=True, hide_index=True, height=650
                    )

# 符合策略的信号区
signals = [r for r in scan_results if r['5min量比'] >= vol_th and "🔥" in r['200MA状态']]
if signals:
    st.divider()
    st.subheader("🚀 换仓首选信号 (趋势之上 + 量比爆发)")
    st.table(pd.DataFrame(signals))

st.caption(f"数据源: {PROXY_URL} | 更新时间: {datetime.now().strftime('%H:%M:%S')}")

# 自动刷新
time.sleep(45)
st.rerun()
