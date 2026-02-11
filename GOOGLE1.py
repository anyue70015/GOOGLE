import streamlit as st
import pandas as pd
import ccxt
import time
from datetime import datetime

# --- 基础配置 ---
st.set_page_config(page_title="8:00 全量监控", layout="wide")

# 排除不需要的稳定币
STABLECOINS = ['USDT', 'USDC', 'DAI', 'FDUSD', 'TUSD', 'USDE', 'USDG', 'PYUSD', 'EUR', 'USDS']

# 初始化交易所
ex = ccxt.okx({'enableRateLimit': True})

def get_ma200_info(sym):
    """获取200MA信息"""
    try:
        # 增加 limit 确保数据够算 MA
        daily = ex.fetch_ohlcv(sym, timeframe='1d', limit=210)
        if not daily or len(daily) < 200: return 0, "数据不足"
        df = pd.DataFrame(daily, columns=['ts','o','h','l','c','v'])
        ma200 = df['c'].rolling(200).mean().iloc[-1]
        price = df['c'].iloc[-1]
        status = "🔥 趋势之上" if price > ma200 else "❄️ 趋势之下"
        dist = (price - ma200) / ma200 * 100
        return dist, status
    except:
        return 0, "计算失败"

st.title("🚀 Top 80 币种实时全量监控")
st.write(f"当前时间: {datetime.now().strftime('%H:%M:%S')} | 刷新率: 30s")

# 自动刷新插件
from streamlit_autorefresh import st_autorefresh
st_autorefresh(interval=30000, key="full_refresh")

# --- 1. 强制初始化一个空的展示框 ---
placeholder = st.empty()
results = []

# --- 2. 获取初始名单 (核心修正点) ---
try:
    # 如果 fetch_tickers 不给力，我们手动定义你关注的核心资产，确保页面不白
    with st.spinner('正在同步 OKX 行情数据...'):
        all_tickers = ex.fetch_tickers()
        
    # 筛选 USDT 对，并排除稳定币
    valid_tickers = {k: v for k, v in all_tickers.items() if '/USDT' in k and not any(sc in k for sc in STABLECOINS)}
    
    # 按照成交量排序取前 80
    top_80_list = sorted(valid_tickers.items(), key=lambda x: x[1].get('quoteVolume', 0), reverse=True)[:80]
    
    if not top_80_list:
        st.error("无法获取 Top 80 名单，请检查 API 连通性。")
        st.stop()
        
except Exception as e:
    st.error(f"初始化行情失败: {e}")
    st.stop()

# --- 3. 开始逐个扫描并即时渲染 ---
for i, (sym, data) in enumerate(top_80_list):
    try:
        # 识别资产类型 (根据你之前的要求)
        asset_type = "合约" if any(x in sym for x in ['TAO', 'XAG', 'XAU']) else "现货"
        
        price = data.get('last', 0)
        change = data.get('percentage', 0)
        vol_24h = data.get('quoteVolume', 0)
        
        # 5min 量能
        bars_5m = ex.fetch_ohlcv(sym, timeframe='5m', limit=2)
        v_now = bars_5m[-1][5] if bars_5m else 0
        # 量比：当前 5 分钟成交量 / 全天 5 分钟平均量
        v_ratio = v_now / (vol_24h / 288) if vol_24h > 0 else 0
        
        # 200MA 状态
        dist, status = get_ma200_info(sym)
        
        results.append({
            "币种": sym,
            "类型": asset_type,
            "5min量比": round(v_ratio, 2),
            "24h涨跌%": round(change, 2),
            "200MA状态": status,
            "偏离200MA%": round(dist, 2),
            "价格": price
        })
        
        # 每抓一个就更新一次表格，让列表“活”起来
        df_display = pd.DataFrame(results).sort_values(by="5min量比", ascending=False)
        with placeholder.container():
            # 表格样式处理
            def highlight_trend(val):
                color = '#ff4b4b' if val == "🔥 趋势之上" else '#31333F'
                return f'background-color: {color}'

            st.dataframe(
                df_display.style.applymap(highlight_trend, subset=['200MA状态']),
                use_container_width=True,
                height=600
            )
            st.caption(f"已加载: {len(results)} / 80")
            
        # 频率控制，防止被封
        time.sleep(0.1)
        
    except Exception as e:
        continue

st.success("✅ 全盘扫描完成。请根据【200MA状态】和【量比】执行汰弱留强。")
