import streamlit as st
import pandas as pd
import requests
import time

st.set_page_config(page_title="指挥部 - 云端模式", layout="wide")

def fetch_cloud_data(symbol):
    # 使用官方针对云服务器的 API 节点（有时能避开封锁）
    url = f"https://api1.binance.com/api/v3/ticker/price?symbol={symbol}USDT"
    
    try:
        # 注意：在云端千万不要写 proxies={'http': '127.0.0.1'} ！！
        # 直接直连，让 Streamlit 服务器去撞
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return {"币种": symbol, "价格": r.json()['price'], "状态": "✅ 云端已连通"}
        else:
            return {"币种": symbol, "价格": "---", "状态": f"❌ 被封 IP ({r.status_code})"}
    except Exception as e:
        return {"币种": symbol, "价格": "---", "状态": "❌ 云端无法穿透"}

st.title("🛰️ 指挥部 - Streamlit 云端专用版")
st.warning("提示：当前运行在远程服务器，已禁用本地 127.0.0.1 代理配置。")

placeholder = st.empty()

while True:
    res = [fetch_cloud_data("BTC"), fetch_cloud_data("ETH")]
    df = pd.DataFrame(res)
    with placeholder.container():
        st.table(df)
        if "❌" in str(df):
            st.error("由于币安封锁了云服务器 IP，建议你还是在【本地电脑】安装 Python 运行。")
    time.sleep(10)
