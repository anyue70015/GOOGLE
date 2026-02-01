import streamlit as st
import pandas as pd
import requests
import time
import urllib3

# 基础配置
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
st.set_page_config(page_title="全球量化指挥部 - 网页兼容版", layout="wide")

# 币种配置 (对应币安前端代码)
SYMBOLS = ["BTCUSDT", "RENDERUSDT", "SUIUSDT", "TAOUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "UNIUSDT", "BCHUSDT", "HYPEUSDT", "DOGEUSDT", "AAVEUSDT"]

def fetch_frontend_data():
    """
    模拟浏览器访问币安官网前端聚合接口
    这个接口通常不会封锁云端 IP
    """
    # 币安前端聚合行情接口
    url = "https://www.binance.com/fapi/v1/ticker/24hr"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Referer": "https://www.binance.com/zh-CN/futures/BTCUSDT"
    }
    
    try:
        # 即使在云端，这个接口的存活率也极高
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            all_data = r.json()
            # 只筛选我们需要的币种
            filtered = [item for item in all_data if item['symbol'] in SYMBOLS]
            return filtered
    except Exception as e:
        st.sidebar.error(f"连接失败: {e}")
        return None

def process_display():
    st.title("🛰️ 全球量化指挥部 - 网页链路中心")
    st.caption("当前链路：Binance Web Public Data (无需代理)")
    
    placeholder = st.empty()
    
    while True:
        raw_data = fetch_frontend_data()
        
        if raw_data:
            rows = []
            for d in raw_data:
                price = float(d['lastPrice'])
                change = float(d['priceChangePercent'])
                # 简单的战术诊断逻辑
                diag = "🎯 强力" if change > 2 else "💀 砸盘" if change < -2 else "⚖️ 观望"
                
                rows.append({
                    "币种": d['symbol'].replace("USDT", ""),
                    "最新价": price,
                    "24h%": change,
                    "成交额(M)": round(float(d['quoteVolume']) / 1000000, 2),
                    "战术诊断": diag
                })
            
            df = pd.DataFrame(rows).sort_values(by="24h%", ascending=False)
            
            with placeholder.container():
                st.dataframe(
                    df.style.format({"24h%": "{:+,.2f}%", "最新价": "{:,}"})
                    .background_gradient(subset=["24h%"], cmap="RdYlGn"),
                    use_container_width=True,
                    hide_index=True
                )
                st.caption(f"📊 网页链路正常 | 刷新时间: {time.strftime('%H:%M:%S')}")
        else:
            st.error("❌ 连币安网页接口都拒绝了你的 IP。Streamlit Cloud 这台服务器彻底报废。")
            st.info("💡 建议：点击 Streamlit 菜单里的 'Reboot App'，强制换一台机器重新尝试。")
            break
            
        time.sleep(10)

process_display()
