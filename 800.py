import streamlit as st
import pandas as pd
import ccxt
import time
import pandas_ta as ta
from concurrent.futures import ThreadPoolExecutor
import streamlit as st
import pandas as pd
import requests
import time
import urllib3

# 1. 基础配置
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
st.set_page_config(page_title="全球量化指挥部 - 最终战略版", layout="wide")

# 代理配置
PROXY_10811 = {"http": "http://127.0.0.1:10811", "https": "http://127.0.0.1:10811"}
DIRECT = {"http": None, "https": None} 

BN_MIRROR = "https://www.bmwweb.academy"
BN_FAPI = "https://fapi.binance.com"

# 币种名单：BTC + 您的原始名单（含 HYPE）
SYMBOLS = ["BTC", "RENDER", "SUI", "TAO", "ETH", "SOL", "XRP", "UNI", "BCH", "HYPE", "DOGE", "AAVE", "ZEC", "CHZ"]

# ------------------------------------------------
# 2. 诊断引擎
# ------------------------------------------------
def get_strategy_logic(m1, m5, h1, c24):
    """根据 1m/5m/1h/24h 涨幅进行战术诊断"""
    if m1 > 0.15 and m5 > 0.5: return "🎯 战术突击 (强吸筹)"
    if m1 < -0.15 and m5 < -0.5: return "💀 战略撤退 (砸盘)"
    if c24 > 3 and m1 < -0.05: return "🔋 战术回撤 (洗盘)"
    if c24 < -3 and m1 > 0.05: return "🛡️ 战略修复 (抄底)"
    if abs(m1) < 0.05 and abs(m5) < 0.1: return "😴 战略横盘"
    return "⚖️ 中性博弈"

def fetch_accurate_change(symbol, interval, lookback):
    """回溯 K 线精准计算涨幅（走币安代理）"""
    url = f"{BN_FAPI}/fapi/v1/klines?symbol={symbol}USDT&interval={interval}&limit={lookback + 1}"
    try:
        r = requests.get(url, timeout=1.5, verify=False, proxies=PROXY_7890)
        if r.status_code == 200:
            ks = r.json()
            start_price, current_price = float(ks[0][1]), float(ks[-1][4])
            return (current_price - start_price) / start_price * 100
    except: pass
    return 0.0

def fetch_data_row(s):
    try:
        # HYPE 逻辑：强制直连 OKX
        if s == "HYPE":
            try:
                url = "https://www.okx.com/api/v5/market/ticker?instId=HYPE-USDT"
                r = requests.get(url, timeout=1.2, proxies=DIRECT)
                d = r.json()['data'][0]
                price = float(d['last'])
                vol = float(d['vol24h']) * price
                src = "OKX直连"
            except:
                # OKX 失败则尝试币安合约镜像（走代理）
                url = f"{BN_MIRROR}/fapi/v1/ticker/24hr?symbol=HYPEUSDT"
                d = requests.get(url, timeout=1.2, verify=False, proxies=PROXY_7890).json()
                price, vol, src = float(d['lastPrice']), float(d['quoteVolume']), "BN合约"
        
        # 其他币种：走币安现货镜像（走代理）
        else:
            url = f"{BN_MIRROR}/api/v3/ticker/24hr?symbol={s}USDT"
            d = requests.get(url, timeout=1.2, verify=False, proxies=PROXY_7890).json()
            price, vol, src = float(d['lastPrice']), float(d['quoteVolume']), "BN现货"

        # 执行各周期高精度回溯计算 (1m, 5m, 1h, 24h)
        m1 = fetch_accurate_change(s, "1m", 1)
        m5 = fetch_accurate_change(s, "1m", 5)
        h1 = fetch_accurate_change(s, "1m", 60)
        c24 = fetch_accurate_change(s, "1h", 24)

        return {
            "币种": s,
            "最新价": round(price, 4) if price < 10 else round(price, 2),
            "1m%": m1, 
            "5m%": m5, 
            "1h%": h1, 
            "24h%": c24,
            "净流入(万)": round((c24 * vol / 1000000), 1),
            "战术/战略诊断": get_strategy_logic(m1, m5, h1, c24),
            "来源": src
        }
    except: return None

# ------------------------------------------------
# 3. 界面逻辑
# ------------------------------------------------
st.title("🛰️ 全球量化指挥部 - 实时战略中心")
st.caption(f"分流运行中: HYPE(直连) | 其他(代理10811) | 监控总数: {len(SYMBOLS)}")

placeholder = st.empty()

while True:
    rows = []
    for s in SYMBOLS:
        res = fetch_data_row(s)
        if res: rows.append(res)
    
    if rows:
        df = pd.DataFrame(rows)
        with placeholder.container():
            # 动态调整高度以适配 20 个以内的币种展示
            st.dataframe(
                df.style.format({
                    "1m%": "{:+,.2f}%", "5m%": "{:+,.2f}%", "1h%": "{:+,.2f}%", "24h%": "{:+,.2f}%",
                    "最新价": "{:,}"
                }).background_gradient(subset=["1m%", "24h%"], cmap="RdYlGn", vmin=-2.5, vmax=2.5),
                use_container_width=True,
                height=(len(SYMBOLS) + 1) * 36,
                hide_index=True
            )
            st.caption(f"📊 实时链路通畅 | 刷新时间: {time.strftime('%H:%M:%S')}")
    
    time.sleep(3)
