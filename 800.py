import streamlit as st
import pandas as pd
import requests
import time
import urllib3

# 禁用 SSL 警告（穿透代理必备）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 基础配置 ---
st.set_page_config(page_title="指挥部 - 物理穿透版", layout="wide")

# 根据你之前的截图，锁定 10811 端口
PROXY_PORT = "10811"
proxies = {
    "http": f"http://127.0.0.1:{PROXY_PORT}",
    "https": f"http://127.0.0.1:{PROXY_PORT}",
}

def fetch_like_a_human(symbol):
    """
    极致伪装：通过模拟浏览器特有的 Header 组合，绕过“物理特征”拦截
    """
    url = f"https://api.binance.me/api/v3/ticker/24hr?symbol={symbol}USDT"
    
    # 模拟最新版 Chrome 的物理请求特征
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
        'Sec-Ch-Ua': '"Not A(Bit:Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"Windows"',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Upgrade-Insecure-Requests': '1'
    }

    try:
        # 使用 Session 保持连接特征，减少握手次数
        with requests.Session() as s:
            s.trust_env = False # 强制不读取系统其他乱七八糟的环境变量
            resp = s.get(url, proxies=proxies, headers=headers, timeout=15, verify=False)
            
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "币种": symbol,
                    "最新价": f"{float(data['lastPrice']):,.2f}",
                    "涨跌": f"{data['priceChangePercent']}%",
                    "诊断": "✅ 物理特征已穿透"
                }
            else:
                return {"币种": symbol, "最新价": "---", "涨跌": "-", "诊断": f"❌ 节点返回 {resp.status_code}"}
    except Exception as e:
        return {"币种": symbol, "最新价": "---", "涨跌": "-", "诊断": "❌ 链路仍被切断"}

# --- UI 渲染 ---
st.title("🛰️ 指挥部 - 物理特征穿透模式")
st.info(f"出口端口：{PROXY_PORT} | 模拟设备：Windows Chrome 121")

placeholder = st.empty()

while True:
    results = []
    # 串行访问，像人一样慢慢点击
    for s in ["BTC", "ETH", "SOL"]:
        results.append(fetch_like_a_human(s))
        time.sleep(1.2)
    
    df = pd.DataFrame(results)
    
    with placeholder.container():
        def color_row(val):
            if "✅" in str(val): return 'color: #00ff00'
            if "❌" in str(val): return 'color: #ff4b4b'
            return ''
            
        st.dataframe(df.style.map(color_row), use_container_width=True, hide_index=True)

    time.sleep(10)
