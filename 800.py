import streamlit as st
import pandas as pd
import requests
import time
import urllib3
import os

# 1. 基础配置
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
st.set_page_config(page_title="全球量化指挥部 - 云端兼容版", layout="wide")

# --- 代理自动识别逻辑 ---
# 判断是否在 Streamlit Cloud 运行 (云端通常有 HOSTNAME 环境变量)
IS_CLOUD = os.environ.get("HOSTNAME") == "streamlit" or os.environ.get("STREAMLIT_RUNTIME_ENV") == "cloud"

if IS_CLOUD:
    # 云端环境：直接连接（海外服务器直连币安/OKX更稳）
    MY_PROXY = None
    st.sidebar.success("🚀 运行环境：Streamlit Cloud (直连模式)")
else:
    # 本地环境：使用你的 10811 代理
    MY_PROXY = {"http": "http://127.0.0.1:10811", "https": "http://127.0.0.1:10811"}
    st.sidebar.info("🏠 运行环境：本地 (代理 10811)")

DIRECT = {"http": None, "https": None} 

BN_MIRROR = "https://www.bmwweb.academy"
BN_FAPI = "https://fapi.binance.com"

# 币种名单
SYMBOLS = ["BTC", "RENDER", "SUI", "TAO", "ETH", "SOL", "XRP", "UNI", "BCH", "HYPE", "DOGE", "AAVE", "ZEC", "CHZ"]

# ------------------------------------------------
# 2. 诊断引擎 (完全保留你的逻辑)
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
    """回溯 K 线精准计算涨幅"""
    url = f"{BN_FAPI}/fapi/v1/klines?symbol={symbol}USDT&interval={interval}&limit={int(lookback) + 1}"
    try:
        # 使用自动识别的代理变量 MY_PROXY
        r = requests.get(url, timeout=2.5, verify=False, proxies=MY_PROXY)
        if r.status_code == 200:
            ks = r.json()
            if len(ks) >= lookback:
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
                r = requests.get(url, timeout=2.0, proxies=DIRECT)
                d = r.json()['data'][0]
                price = float(d['last'])
                vol = float(d['vol24h']) * price
                src = "OKX直连"
            except:
                # OKX 失败则尝试币安合约镜像
                url = f"{BN_MIRROR}/fapi/v1/ticker/24hr?symbol=HYPEUSDT"
                d = requests.get(url, timeout=2.0, verify=False, proxies=MY_PROXY).json()
                price, vol, src = float(d['lastPrice']), float(d['quoteVolume']), "BN合约"
        
        # 其他币种：走币安现货镜像
        else:
            url = f"{BN_MIRROR}/api/v3/ticker/24hr?symbol={s}USDT"
            d = requests.get(url, timeout=2.0, verify=False, proxies=MY_PROXY).json()
            price, vol, src = float(d['lastPrice']), float(d['quoteVolume']), "BN现货"

        # 执行各周期高精度回溯计算
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
st.caption(f"当前模式: {'云端直连' if IS_CLOUD else '本地代理'} | 监控总数: {len(SYMBOLS)}")

# 创建数据占位符
placeholder = st.empty()

# 获取数据并渲染
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
            }).background_gradient(subset=["1m%", "24h%"], cmap="RdYlGn", vmin=-1.0, vmax=1.0),
            use_container_width=True,
            height=(len(SYMBOLS) + 1) * 38,
            hide_index=True
        )
        st.caption(f"📊 链路通畅 | 数据刷新时间: {time.strftime('%H:%M:%S')}")

# 自动刷新逻辑：每隔 5 秒重新运行脚本
time.sleep(5)
st.rerun()
