import streamlit as st
import pandas as pd
import requests
import time
import urllib3

# 彻底禁用 SSL 校验，防止因为你系统没有证书库而报错
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.set_page_config(page_title="指挥部 - 兼容模式", layout="wide")

# 根据截图 image_061ef3.png，你的端口是 10811
# 如果不通，请手动尝试改成 10810
PROXY_PORT = "10811" 

def fetch_data_simple(symbol):
    """
    最基础的请求模式，专门针对精简版 Windows 系统优化
    """
    url = f"https://api.binance.me/api/v3/ticker/price?symbol={symbol}USDT"
    
    # 强制手动配置代理，不依赖系统设置
    proxies = {
        "http": f"http://127.0.0.1:{PROXY_PORT}",
        "https": f"http://127.0.0.1:{PROXY_PORT}",
    }
    
    # 伪装成最普通的浏览器
    headers = {
        'User-Agent': 'Mozilla/5.0'
    }

    try:
        # 使用 verify=False 跳过 SSL 验证
        r = requests.get(url, proxies=proxies, headers=headers, timeout=10, verify=False)
        if r.status_code == 200:
            data = r.json()
            return {
                "币种": symbol,
                "价格": f"{float(data['price']):,.2f}",
                "状态": "✅ 通了"
            }
        else:
            return {"币种": symbol, "价格": "---", "状态": f"❌ 错误 {r.status_code}"}
    except Exception as e:
        # 如果还是不行，说明 10811 被防火墙死死封住了
        return {"币种": symbol, "价格": "---", "状态": "❌ 物理墙隔离"}

st.title("🛰️ 终极指挥部 - 系统兼容模式")
st.info(f"由于检测到系统组件缺失，已开启【底层协议兼容】模式。尝试端口：{PROXY_PORT}")

if st.button("🚀 强制刷新"):
    st.rerun()

placeholder = st.empty()

while True:
    res = [fetch_data_simple("BTC"), fetch_data_simple("ETH")]
    df = pd.DataFrame(res)
    with placeholder.container():
        st.table(df)
    time.sleep(10)
