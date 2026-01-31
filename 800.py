import streamlit as st
import pandas as pd
import requests
import time
import urllib3

# 1. 彻底切断所有验证
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.set_page_config(page_title="指挥部 - 强制打通版", layout="wide")

# 根据你的截图，我们尝试 10811 和 10810 两个端口
def try_ports():
    target_ports = ["10811", "10810"]
    url = "https://api.binance.me/api/v3/ping"
    
    for port in target_ports:
        proxies = {"http": f"http://127.0.0.1:{port}", "https": f"http://127.0.0.1:{port}"}
        try:
            # 模拟最底层的单次请求
            r = requests.get(url, proxies=proxies, timeout=5, verify=False)
            if r.status_code == 200:
                return port
        except:
            continue
    return None

def fetch_data_emergency(symbol, port):
    url = f"https://api.binance.me/api/v3/ticker/price?symbol={symbol}USDT"
    proxies = {"http": f"http://127.0.0.1:{port}", "https": f"http://127.0.0.1:{port}"}
    
    # 强制模拟浏览器的最细微特征
    headers = {
        'Connection': 'close', # 请求完立刻断开，防止占用被防火墙杀掉
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'
    }

    try:
        # 强制不使用 Session，每次都是独立硬闯
        r = requests.get(url, proxies=proxies, headers=headers, timeout=8, verify=False)
        if r.status_code == 200:
            return {"币种": symbol, "价格": r.json()['price'], "状态": "✅ 物理墙已穿透"}
    except Exception:
        return {"币种": symbol, "价格": "---", "状态": "❌ 仍被系统拦截"}

# --- UI 逻辑 ---
st.title("🛰️ 终极自愈监控台")

# 自动探测可用端口
active_port = try_ports()

if active_port:
    st.success(f"📡 自动发现可用通道：{active_port}")
    
    # 串行采集
    btc_data = fetch_data_emergency("BTC", active_port)
    eth_data = fetch_data_emergency("ETH", active_port)
    
    df = pd.DataFrame([btc_data, eth_data])
    st.table(df)
    
    if "✅" in str(df.values):
        st.balloons() # 庆祝一下
else:
    st.error("🚨 所有本地端口 (10810/10811) 均被系统拒绝访问。")
    st.info("请尝试：右键点击右下角 360 或安全中心图标，选择【退出】，然后重启本脚本。")

if st.button("🔄 暴力重试"):
    st.rerun()

time.sleep(10)
