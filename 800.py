import streamlit as st
import pandas as pd
import ccxt
import time
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 1. 样式配置 (回归白色主题)
# ==========================================
st.set_page_config(page_title="2026 全网资金扫描", layout="wide")

# 设定币种列表
SYMBOLS = ["BTC", "ETH", "SOL", "AAVE", "DOGE", "TAO", "SUI", "RENDER", "UNI", "HYPE", "XRP"]
EXCHANGE_IDS = {'OKX': 'okx', 'Gate': 'gateio', 'Huobi': 'htx', 'Bitget': 'bitget'}
TFS = ['1m', '5m', '15m', '1h']

# ==========================================
# 2. 核心抓取函数 (极简 & 快速)
# ==========================================
def get_ex(name):
    ex_class = getattr(ccxt, EXCHANGE_IDS[name])
    # 缩短超时时间到 5 秒，一旦卡住立刻放弃，不拖累全局速度
    return ex_class({'enableRateLimit': True, 'timeout': 5000})

def fetch_symbol_data(symbol, big_val):
    pair = f"{symbol}/USDT"
    res = {"币种": symbol}
    total_net_flow = 0
    active_ex_count = 0

    # A. 涨跌幅抓取 (OKX优先，Gate备选)
    changes = {f"{tf}涨跌": "N/A" for tf in TFS}
    changes['raw_sort'] = 0
    for ex_name in ['OKX', 'Gate']:
        try:
            ex = get_ex(ex_name)
            for tf in TFS:
                ohlcv = ex.fetch_ohlcv(pair, tf, limit=2)
                if len(ohlcv) >= 2:
                    ch = ((ohlcv[-1][4] - ohlcv[-1][1]) / ohlcv[-1][1]) * 100
                    changes[f"{tf}涨跌"] = f"{ch:+.2f}%"
                    if tf == '1m': changes['raw_sort'] = ch
            break # 只要拿到一家的数据就退出循环
        except:
            continue
    res.update(changes)

    # B. 大单扫描 (4所并发)
    def scan_single_ex(name):
        nonlocal total_net_flow, active_ex_count
        try:
            ex = get_ex(name)
            trades = ex.fetch_trades(pair, limit=30) # 减少深度到30，提速
            icons = []
            for t in trades:
                val = t['price'] * t['amount']
                side = 1 if t['side'] == 'buy' else -1
                total_net_flow += val * side
                if t['side'] == 'buy':
                    if val >= 500000: icons.append("💣")
                    elif val >= 100000: icons.append("🧨")
                    elif val >= big_val: icons.append("🔥")
            if icons: active_ex_count += 1
            return "".join(icons[:3]) if icons else "·"
        except:
            return "⚠️"

    for name in EXCHANGE_IDS.keys():
        res[name] = scan_single_ex(name)

    res["净流入(万)"] = round(total_net_flow / 10000, 2)
    res["共振"] = "🚨" if active_ex_count >= 3 else ""
    return res

# ==========================================
# 3. UI 渲染与极速刷新
# ==========================================
st.title("🏹 全网资金共振扫描器 (极速直连版)")

with st.sidebar:
    st.header("⚙️ 参数")
    big_val = st.number_input("大单阈值 (USDT)", value=20000)
    refresh_rate = st.slider("扫描间隔 (秒)", 3, 30, 5)
    st.info("白色模式：红色代表跌，绿色代表涨。")

placeholder = st.empty()

while True:
    final_data = []
    # 增加线程池到 30，确保所有币种几乎同时完成抓取
    with ThreadPoolExecutor(max_workers=30) as executor:
        futures = [executor.submit(fetch_symbol_data, sym, big_val) for sym in SYMBOLS]
        for f in futures:
            final_data.append(f.result())

    df = pd.DataFrame(final_data).sort_values("raw_sort", ascending=False).drop(columns="raw_sort")

    with placeholder.container():
        st.write(f"⏱️ 更新时间: {time.strftime('%H:%M:%S')} | 状态: 极速模式已开启")
        
        # 针对白色主题的样式
        def style_df(row):
            if row['共振'] == '🚨':
                return ['background-color: #FFF3E0; font-weight: bold'] * len(row) # 淡淡的橙色背景提示共振
            return [''] * len(row)

        def color_val(val):
            if not isinstance(val, str): return ''
            if '+' in val: return 'color: #D32F2F; font-weight: bold' # 涨：在中国习惯用红色（如果习惯绿涨请改颜色码）
            if '-' in val: return 'color: #388E3C; font-weight: bold' # 跌：用绿色
            return 'color: #000000'

        # 注意：这里涨跌幅颜色我按中国习惯设为红涨绿跌，如需国际标准请调换颜色码
        st.dataframe(
            df.style.apply(style_df, axis=1)
                    .applymap(color_val, subset=[f"{tf}涨跌" for tf in TFS]),
            use_container_width=True, height=600
        )
    
    time.sleep(refresh_rate)
