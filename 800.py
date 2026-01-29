import streamlit as st
import pandas as pd
import ccxt
import time
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 1. 样式与配置 (强制黑金模式)
# ==========================================
st.set_page_config(page_title="2026 全网资金共振系统", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #0E1117; color: #FFFFFF; }
    [data-testid="stSidebar"] { background-color: #1A1C24; }
    h1, h2, h3, p { color: #FFFFFF !important; }
    .stDataFrame { border: 1px solid #31333F; }
    </style>
    """, unsafe_allow_html=True)

SYMBOLS = ["BTC", "ETH", "SOL", "AAVE", "DOGE", "TAO", "SUI", "RENDER", "UNI", "HYPE", "XRP"]
EXCHANGE_IDS = {'OKX': 'okx', 'Gate': 'gateio', 'Huobi': 'htx', 'Bitget': 'bitget'}
TIMEFRAMES = ['1m', '5m', '15m', '1h'] # 60m 对应 CCXT 的 1h

# ==========================================
# 2. 核心抓取引擎
# ==========================================
def get_ex(name):
    ex_class = getattr(ccxt, EXCHANGE_IDS[name])
    return ex_class({'enableRateLimit': True, 'timeout': 15000})

def fetch_symbol_data(symbol, big_val):
    pair = f"{symbol}/USDT"
    res = {"币种": symbol}
    total_net_flow = 0
    active_ex_count = 0

    # --- A. 获取多周期涨幅 (OKX 优先 -> Gate 备份) ---
    def get_change_data():
        for ex_name in ['OKX', 'Gate']:
            try:
                ex = get_ex(ex_name)
                changes = {}
                for tf in TIMEFRAMES:
                    ohlcv = ex.fetch_ohlcv(pair, tf, limit=2)
                    if len(ohlcv) >= 2:
                        ch = ((ohlcv[-1][4] - ohlcv[-1][1]) / ohlcv[-1][1]) * 100
                        changes[f"{tf}涨幅"] = f"{ch:+.2f}%"
                        if tf == '1m': changes['raw_sort'] = ch # 用1分钟涨幅排序
                    else:
                        changes[f"{tf}涨幅"] = "0.00%"
                return changes, ex_name
            except:
                continue
        return {f"{tf}涨幅": "N/A" for tf in TIMEFRAMES}, "None"

    change_data, source_name = get_change_data()
    res.update(change_data)
    res["来源"] = source_name

    # --- B. 扫描四个交易所的大单与能量 ---
    def scan_ex(name):
        nonlocal total_net_flow, active_ex_count
        try:
            ex = get_ex(name)
            trades = ex.fetch_trades(pair, limit=50)
            icons = []
            ex_net = 0
            for t in trades:
                val = t['price'] * t['amount']
                side = 1 if t['side'] == 'buy' else -1
                ex_net += val * side
                if t['side'] == 'buy':
                    if val >= 500000: icons.append("💣")
                    elif val >= 100000: icons.append("🧨")
                    elif val >= big_val: icons.append("🔥")
            
            total_net_flow += ex_net
            if icons: active_ex_count += 1
            return "".join(icons[:3]) if icons else "·"
        except:
            return "⚠️"

    for name in EXCHANGE_IDS.keys():
        res[name] = scan_ex(name)

    res["净流入(万)"] = round(total_net_flow / 10000, 2)
    res["共振"] = "🚨" if active_ex_count >= 3 else ""
    return res

# ==========================================
# 3. 主界面刷新
# ==========================================
st.title("🏹 2026 全网资金流向指挥部 (多周期版)")

with st.sidebar:
    st.header("⚡ 扫描配置")
    big_val = st.number_input("大单阈值 (USDT)", value=20000)
    refresh_rate = st.slider("扫描频率 (秒)", 5, 60, 10)
    st.markdown("---")
    st.markdown("数据逻辑：\n1. 优先取 OKX 涨幅\n2. OKX 掉线自动取 Gate\n3. 🚨 3家所共振高亮")

placeholder = st.empty()

while True:
    final_data = []
    with ThreadPoolExecutor(max_workers=len(SYMBOLS)) as executor:
        futures = [executor.submit(fetch_symbol_data, sym, big_val) for sym in SYMBOLS]
        for f in futures:
            final_data.append(f.result())

    # 按 1分钟涨幅 排序
    df = pd.DataFrame(final_data).sort_values("raw_sort", ascending=False).drop(columns="raw_sort")

    with placeholder.container():
        st.write(f"⏱️ 刷新: {time.strftime('%H:%M:%S')} | 策略: OKX/Gate 容灾切换")
        
        # 样式渲染
        def style_logic(row):
            if row['共振'] == '🚨':
                return ['background-color: #3e2723; color: #ffcc00; font-weight: bold'] * len(row)
            return ['color: #e0e0e0'] * len(row)

        def color_change(val):
            if isinstance(val, str) and '+' in val: return 'color: #00ff00'
            if isinstance(val, str) and '-' in val: return 'color: #ff4b4b'
            return ''

        st.dataframe(
            df.style.apply(style_logic, axis=1)
                    .applymap(color_change, subset=["1m涨幅", "5m涨幅", "15m涨幅", "1h涨幅"]),
            use_container_width=True, height=650
        )
    
    time.sleep(refresh_rate)
