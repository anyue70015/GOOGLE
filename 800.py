import streamlit as st
import pandas as pd
import pandas_ta as ta
import cloudscraper
import time

# --- 基础配置 ---
st.set_page_config(page_title="指挥部 - 深度穿透版", layout="wide")

# 根据你的图片 [image_054cd8.png] 确认端口为 10811
# 如果不通，请依次尝试 10812 或 10813
PROXY_PORT = "10811"
proxies = {
    "http": f"http://127.0.0.1:{PROXY_PORT}",
    "https": f"http://127.0.0.1:{PROXY_PORT}",
}

def fetch_via_scraper(symbol):
    """
    使用 cloudscraper 模拟浏览器 TLS 指纹，绕过节点对 API 的物理阻断
    """
    # 锁定币安备用 API 域名
    url = f"https://api.binance.me/api/v3/ticker/24hr?symbol={symbol}USDT"
    kline_url = f"https://api.binance.me/api/v3/klines?symbol={symbol}USDT&interval=1h&limit=35"
    
    # 创建模拟浏览器的 scraper 实例
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False})
    
    try:
        # 1. 抓取价格数据
        resp = scraper.get(url, proxies=proxies, timeout=15, verify=False)
        # 2. 抓取 K 线数据
        k_resp = scraper.get(kline_url, proxies=proxies, timeout=15, verify=False)
        
        if resp.status_code == 200 and k_resp.status_code == 200:
            data = resp.json()
            klines = k_resp.json()
            
            # 计算 RSI
            df = pd.DataFrame(klines, columns=['t','o','h','l','c','v','T','q','n','V','L','M'])
            df['c'] = df['c'].astype(float)
            rsi = ta.rsi(df['c'], length=14).iloc[-1]
            
            return {
                "币种": symbol,
                "最新价": f"{float(data['lastPrice']):,.2f}",
                "24H涨跌": f"{data['priceChangePercent']}%",
                "RSI": round(rsi, 1),
                "状态": "✅ 链路已穿透"
            }
        else:
            return {"币种": symbol, "最新价": "---", "24H涨跌": "-", "RSI": "-", "状态": f"❌ 节点返回 {resp.status_code}"}
    except Exception as e:
        return {"币种": symbol, "最新价": "---", "24H涨跌": "-", "RSI": "-", "状态": "❌ 物理特征拦截"}

# --- UI 渲染 ---
st.title("🛰️ 指挥部 - 深度指纹穿透")
st.caption(f"当前监控出口：127.0.0.1:{PROXY_PORT} | 模式：TLS 指纹模拟")

if st.button("🚀 暴力刷新链路"):
    st.rerun()

placeholder = st.empty()

while True:
    results = []
    # 串行请求，防止瞬间并发导致指纹失效
    for s in ["BTC", "ETH", "SOL"]:
        results.append(fetch_via_scraper(s))
        time.sleep(1) # 增加物理间隔
    
    df = pd.DataFrame(results)
    
    with placeholder.container():
        def color_map(val):
            if "✅" in str(val): return 'color: #00ff00; font-weight: bold'
            if "❌" in str(val): return 'color: #ff4b4b; font-weight: bold'
            return ''
            
        st.dataframe(df.style.map(color_map), use_container_width=True, hide_index=True)
        
        if "❌ 物理特征拦截" in df.values:
            st.warning("⚠️ 依然被拦截？请右键点击 v2rayN 图标，确认：\n1. 路由模式是否为【全局模式】。\n2. 系统代理是否为【自动配置系统代理】。")

    time.sleep(15)
