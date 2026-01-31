import streamlit as st
import requests
import pandas as pd
import time

# --- 基础配置 ---
st.set_page_config(page_title="指挥部 - 底层穿透版", layout="wide")

# 你的 v2rayN 混合端口
PROXY_PORT = "10811"
proxies = {
    "http": f"http://127.0.0.1:{PROXY_PORT}",
    "https": f"http://127.0.0.1:{PROXY_PORT}",
}

def fetch_by_raw_request(symbol):
    """
    跳过所有框架，直接用底层 requests 访问
    """
    url = f"https://api.binance.me/api/v3/ticker/24hr?symbol={symbol}USDT"
    
    try:
        # 增加 headers 伪装
        headers = {'User-Agent': 'Mozilla/5.0'}
        # 强制不检查 SSL 证书
        response = requests.get(url, proxies=proxies, timeout=10, verify=False, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            return {
                "币种": symbol,
                "最新价": f"{float(data['lastPrice']):,.2f}",
                "涨跌": f"{data['priceChangePercent']}%",
                "状态": "✅ 底层打通"
            }
        else:
            return {"币种": symbol, "最新价": "---", "涨跌": "-", "状态": f"❌ 错误代码 {response.status_code}"}
    except Exception as e:
        return {"币种": symbol, "最新价": "---", "涨跌": "-", "状态": "❌ 物理墙拦截"}

# --- UI 渲染 ---
st.title("🛰️ 终极指挥部 - 底层 Socket 穿透测试")
st.info(f"正在尝试跳过交易所框架，直接从 {PROXY_PORT} 端口发射请求...")

if st.button("🚀 暴力重试"):
    st.rerun()

# 这里的循环非常关键
placeholder = st.empty()

while True:
    res_list = []
    for s in ["BTC", "ETH"]:
        res_list.append(fetch_by_raw_request(s))
    
    df = pd.DataFrame(res_list)
    
    with placeholder.container():
        st.table(df)
        
        if "❌ 物理墙拦截" in df.values:
            st.error("🚨 警告：底层请求也被拦截！")
            st.write("请检查以下三项：")
            st.write("1. **管理员权限**：请关闭 VS Code/PyCharm，重新以【管理员身份】打开它们再运行。")
            st.write("2. **防火墙**：检查 Windows 防火墙，是否禁止了 `python.exe` 访问网络。")
            st.write("3. **v2rayN 设置**：点击参数设置 -> Core设置 -> 勾选【允许来自局域网的连接】。")

    time.sleep(5)
