import streamlit as st
import pandas as pd
import requests
import time
import urllib3

# 1. 基础配置
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
st.set_page_config(page_title="全球量化指挥部 - 最终战略版", layout="wide")

# 代理配置 - 统一变量名，防止报错
PROXY_10811 = {"http": "http://127.0.0.1:10811", "https": "http://127.0.0.1:10811"}
DIRECT = {"http": None, "https": None} 

BN_MIRROR = "https://www.bmwweb.academy"
BN_FAPI = "https://fapi.binance.com"

SYMBOLS = ["BTC", "RENDER", "SUI", "TAO", "ETH", "SOL", "XRP", "UNI", "BCH", "HYPE", "DOGE", "AAVE", "ZEC", "CHZ"]

# ------------------------------------------------
# 2. 诊断引擎（保持原样）
# ------------------------------------------------
def get_strategy_logic(m1, m5, h1, c24):
    if m1 > 0.15 and m5 > 0.5: return "🎯 战术突击 (强吸筹)"
    if m1 < -0.15 and m5 < -0.5: return "💀 战略撤退 (砸盘)"
    if c24 > 3 and m1 < -0.05: return "🔋 战术回撤 (洗盘)"
    if c24 < -3 and m1 > 0.05: return "🛡️ 战略修复 (抄底)"
    if abs(m1) < 0.05 and abs(m5) < 0.1: return "😴 战略横盘"
    return "⚖️ 中性博弈"

def fetch_accurate_change(symbol, interval, lookback):
    # 修正：将 PROXY_7890 改为 PROXY_10811
    url = f"{BN_FAPI}/fapi/v1/klines?symbol={symbol}USDT&interval={interval}&limit={int(lookback) + 1}"
    try:
        r = requests.get(url, timeout=2.0, verify=False, proxies=PROXY_10811)
        if r.status_code == 200:
            ks = r.json()
            start_price, current_price = float(ks[0][1]), float(ks[-1][4])
            return (current_price - start_price) / start_price * 100
    except: pass
    return 0.0

def fetch_data_row(s):
    try:
        if s == "HYPE":
            try:
                url = "https://www.okx.com/api/v5/market/ticker?instId=HYPE-USDT"
                r = requests.get(url, timeout=1.5, proxies=DIRECT)
                d = r.json()['data'][0]
                price = float(d['last'])
                vol = float(d['vol24h']) * price
                src = "OKX直连"
            except:
                url = f"{BN_MIRROR}/fapi/v1/ticker/24hr?symbol=HYPEUSDT"
                # 修正：将 PROXY_7890 改为 PROXY_10811
                d = requests.get(url, timeout=1.5, verify=False, proxies=PROXY_10811).json()
                price, vol, src = float(d['lastPrice']), float(d['quoteVolume']), "BN合约"
        else:
            url = f"{BN_MIRROR}/api/v3/ticker/24hr?symbol={s}USDT"
            # 修正：将 PROXY_7890 改为 PROXY_10811
            d = requests.get(url, timeout=1.5, verify=False, proxies=PROXY_10811).json()
            price, vol, src = float(d['lastPrice']), float(d['quoteVolume']), "BN现货"

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
# 3. 界面逻辑（核心改动：去掉 while True）
# ------------------------------------------------
st.title("🛰️ 全球量化指挥部 - 实时战略中心")
st.caption(f"分流运行中: HYPE(直连) | 其他(代理10811) | 监控总数: {len(SYMBOLS)}")

# 这里的 placeholder 依然保留
placeholder = st.empty()

rows = []
for s in SYMBOLS:
    res = fetch_data_row(s)
    if res: rows.append(res)

if rows:
    df = pd.DataFrame(rows)
    with placeholder.container():
        st.dataframe(
            df.style.format({
                "1m%": "{:+,.2f}%", "5m%": "{:+,.2f}%", "1h%": "{:+,.2f}%", "24h%": "{:+,.2f}%",
                "最新价": "{:,}"
            }).background_gradient(subset=["1m%", "24h%"], cmap="RdYlGn", vmin=-2.5, vmax=2.5),
            use_container_width=True,
            height=(len(SYMBOLS) + 1) * 38,
            hide_index=True
        )
        st.caption(f"📊 实时链路通畅 | 刷新时间: {time.strftime('%H:%M:%S')}")

# 让网页每 3 秒自动重跑一遍脚本，实现实时刷新且不白屏
time.sleep(3)
st.rerun()
