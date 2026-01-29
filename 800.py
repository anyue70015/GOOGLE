import streamlit as st
import pandas as pd
import ccxt
import time
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 1. 基础配置
# ==========================================
st.set_page_config(page_title="2026 稳定版资金监控", layout="wide")

SYMBOLS = ["BTC", "ETH", "SOL", "AAVE", "DOGE", "TAO", "SUI", "RENDER", "UNI", "HYPE", "XRP"]
EXCHANGE_IDS = {'OKX': 'okx', 'Gate': 'gateio', 'Huobi': 'htx', 'Bitget': 'bitget'}
TFS = ['1m', '5m', '15m', '1h']

# ==========================================
# 2. 核心抓取逻辑 (增加稳定性)
# ==========================================
def fetch_symbol_data(symbol, big_val):
    pair = f"{symbol}/USDT"
    res = {"币种": symbol}
    total_net_flow = 0
    active_ex_count = 0
    
    # --- 1. 抓取涨跌幅 (OKX优先，Gate备选) ---
    changes = {f"{tf}涨跌": "0.00%" for tf in TFS}
    changes['raw_sort'] = 0
    
    found_data = False
    for ex_id in ['OKX', 'Gate']:
        if found_data: break
        try:
            ex_class = getattr(ccxt, EXCHANGE_IDS[ex_id])
            ex = ex_class({'timeout': 7000, 'enableRateLimit': True})
            for tf in TFS:
                ohlcv = ex.fetch_ohlcv(pair, tf, limit=2)
                if len(ohlcv) >= 2:
                    ch = ((ohlcv[-1][4] - ohlcv[-1][1]) / ohlcv[-1][1]) * 100
                    changes[f"{tf}涨跌"] = f"{ch:+.2f}%"
                    if tf == '1m': changes['raw_sort'] = ch
                    found_data = True
        except:
            continue
    res.update(changes)

    # --- 2. 扫描大单 (循环抓取防止瞬间并发过高) ---
    for name, eid in EXCHANGE_IDS.items():
        try:
            ex_class = getattr(ccxt, eid)
            ex = ex_class({'timeout': 5000, 'enableRateLimit': True})
            trades = ex.fetch_trades(pair, limit=20) # 进一步缩小深度提速
            
            icons = []
            for t in trades:
                val = (t['price'] or 0) * (t['amount'] or 0)
                side = 1 if t['side'] == 'buy' else -1
                total_net_flow += val * side
                if t['side'] == 'buy':
                    if val >= 500000: icons.append("💣")
                    elif val >= 100000: icons.append("🧨")
                    elif val >= big_val: icons.append("🔥")
            
            if icons: active_ex_count += 1
            res[name] = "".join(dict.fromkeys(icons)) if icons else "·" # 去重显示
        except:
            res[name] = "⚠️"

    res["净流入(万)"] = round(total_net_flow / 10000, 1)
    res["共振"] = "🚨" if active_ex_count >= 3 else ""
    return res

# ==========================================
# 3. UI 界面与主循环
# ==========================================
st.title("🏹 全网资金流向监控 (稳定版)")

with st.sidebar:
    st.header("⚙️ 监控配置")
    big_val = st.number_input("大单阈值 (USDT)", value=20000, step=5000)
    refresh_rate = st.slider("扫描间隔 (秒)", 5, 60, 10)
    st.divider()
    st.write("💡 **绿涨红跌** (国际标准)")
    st.write("🚨 3家及以上所同时买入")

placeholder = st.empty()

# 为了防止 Streamlit 脚本卡死，使用 try-except 包裹主循环
try:
    while True:
        data_list = []
        # 使用 ThreadPoolExecutor，但 worker 数量不宜过大，防止 IP 被封
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_sym = {executor.submit(fetch_symbol_data, sym, big_val): sym for sym in SYMBOLS}
            for future in future_to_sym:
                try:
                    result = future.result()
                    if result: data_list.append(result)
                except Exception as e:
                    pass

        if data_list:
            df = pd.DataFrame(data_list).sort_values("raw_sort", ascending=False).drop(columns="raw_sort")
            
            with placeholder.container():
                st.write(f"🔄 上次更新: {time.strftime('%H:%M:%S')} | 币种数量: {len(df)}")
                
                # 样式定制
                def style_df(row):
                    if row['共振'] == '🚨':
                        return ['background-color: #f0f7ff; border: 1px solid #007bff'] * len(row)
                    return [''] * len(row)

                def color_logic(val):
                    if not isinstance(val, str): return ''
                    if '+' in val: return 'color: #28a745; font-weight: bold' # 绿涨
                    if '-' in val: return 'color: #dc3545; font-weight: bold' # 红跌
                    return 'color: #212529'

                st.dataframe(
                    df.style.apply(style_df, axis=1)
                            .applymap(color_logic, subset=[f"{tf}涨跌" for tf in TFS]),
                    use_container_width=True, height=600
                )
        
        # 强制休眠，给 API 喘息时间
        time.sleep(refresh_rate)

except Exception as global_e:
    st.error(f"程序发生意外中断，请刷新页面重试。错误信息: {global_e}")
