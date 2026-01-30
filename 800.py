import streamlit as st
import pandas as pd
import ccxt
import time
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 1. 基础配置
# ==========================================
st.set_page_config(page_title="指挥部-Bitget全量加速版", layout="wide")

SYMBOLS = ["BTC", "ETH", "SOL", "AAVE", "DOGE", "TAO", "SUI", "RENDER", "UNI", "HYPE", "XRP","ADA", "BCH", "LINK", "LTC", "TRX", "ZEC", "ASTER"]

# ==========================================
# 2. 核心抓取：Bitget 优先 + 并发模式
# ==========================================
def get_data_from_exchange(symbol):
    pair = f"{symbol}/USDT"
    # 定义优先级：Bitget 第一（为了 TAO/HYPE/ZEC），OKX 第二，Gate 第三
    e_ids = ['bitget', 'okx', 'gateio']
    
    for eid in e_ids:
        try:
            ex = getattr(ccxt, eid)({'timeout': 3000})
            tk = ex.fetch_ticker(pair)
            return {
                "币种": symbol,
                "最新价": tk['last'],
                "24h涨跌": tk['percentage'],
                "24h成交额": f"{tk['quoteVolume']/10000:.1f}万",
                "来源": eid.upper()
            }
        except:
            continue # 如果这个交易所没有该币种，自动跳下一个
    return {"币种": symbol, "最新价": "未找到", "24h涨跌": 0, "来源": "None"}

# ==========================================
# 3. UI 调度
# ==========================================
st.title("🚨 Bitget 强化指挥部 (2026.01.30 暴跌监控)")

if 'last_df' not in st.session_state:
    st.session_state.last_df = pd.DataFrame()

placeholder = st.empty()

while True:
    # 使用线程池全量并发抓取（不再分批，18个币同时抓）
    with ThreadPoolExecutor(max_workers=len(SYMBOLS)) as executor:
        results = list(executor.map(get_data_from_exchange, SYMBOLS))
    
    df = pd.DataFrame(results)
    
    # 排序逻辑：按跌幅最狠的排在最前面
    df = df.sort_values(by="24h涨跌", ascending=True)
    
    # 格式化显示
    display_df = df.copy()
    display_df['24h涨跌'] = display_df['24h涨跌'].apply(lambda x: f"{x:+.2f}%" if x != 0 else "0.00%")
    
    with placeholder.container():
        t_now = time.strftime('%H:%M:%S')
        st.subheader(f"🔄 全量同步完成 | 刷新时间: {t_now}")
        
        # 重点监控 TAO (Bitget)
        tao_data = df[df['币种'] == 'TAO'].iloc[0] if not df[df['币种'] == 'TAO'].empty else None
        if tao_data and float(str(tao_data['24h涨跌']).replace('%','')) < -5:
            st.warning(f"⚠️ Bitget 信号：TAO 正在剧烈波动，当前价: {tao_data['最新价']}")

        st.dataframe(display_df, use_container_width=True, height=700)

    time.sleep(15) # 暴跌期间建议 15 秒同步一次全量数据
