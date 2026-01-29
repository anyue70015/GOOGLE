import streamlit as st
import pandas as pd
import ccxt
import time
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 1. 基础配置
# ==========================================
st.set_page_config(page_title="2026 全网大单监控", layout="wide")

# 监控币种
SYMBOLS = ["BTC", "ETH", "SOL", "AAVE", "DOGE", "TAO", "SUI", "RENDER", "UNI", "HYPE", "XRP"]
# 交易所映射
EXCHANGE_IDS = {'OKX': 'okx', 'Gate': 'gateio', 'Huobi': 'htx', 'Bitget': 'bitget'}
# 时间周期
TFS = ['1m', '5m', '15m', '1h']

# ==========================================
# 2. 核心抓取逻辑
# ==========================================
def fetch_symbol_data(symbol, big_val_threshold):
    pair = f"{symbol}/USDT"
    # 初始化数据行，默认显示 N/A 防止渲染失败
    res = {"币种": symbol, "最新价": "N/A"}
    for tf in TFS: res[f"{tf}涨跌"] = "0.00%"
    res.update({'OKX': '·', 'Gate': '·', 'Huobi': '·', 'Bitget': '·', '净流入(万)': 0.0, '共振': '', 'raw_sort': 0})
    
    total_net_flow = 0
    active_ex_count = 0
    
    # --- A. 获取价格与多周期涨幅 (OKX优先 -> Gate备份) ---
    found_base_data = False
    for ex_id in ['OKX', 'Gate']:
        if found_base_data: break
        try:
            ex_class = getattr(ccxt, EXCHANGE_IDS[ex_id])
            ex = ex_class({'timeout': 8000, 'enableRateLimit': True})
            
            # 1. 获取最新价
            ticker = ex.fetch_ticker(pair)
            res["最新价"] = f"{ticker['last']}"
            
            # 2. 获取各周期 K 线
            for tf in TFS:
                ohlcv = ex.fetch_ohlcv(pair, tf, limit=2)
                if len(ohlcv) >= 2:
                    ch = ((ohlcv[-1][4] - ohlcv[-1][1]) / ohlcv[-1][1]) * 100
                    res[f"{tf}涨跌"] = f"{ch:+.2f}%"
                    if tf == '1m': res['raw_sort'] = ch
            found_base_data = True
        except:
            continue

    # --- B. 扫描各交易所大单成交额 (显示"xx万") ---
    for name, eid in EXCHANGE_IDS.items():
        try:
            ex_class = getattr(ccxt, eid)
            ex = ex_class({'timeout': 6000, 'enableRateLimit': True})
            trades = ex.fetch_trades(pair, limit=25)
            
            # 统计主动买入的大单总额
            big_buy_sum = sum((t['price'] * t['amount']) for t in trades 
                              if t['side'] == 'buy' and (t['price'] * t['amount']) >= big_val_threshold)
            
            # 计算全量净流入 (买入 - 卖出)
            for t in trades:
                val = (t['price'] or 0) * (t['amount'] or 0)
                total_net_flow += val if t['side'] == 'buy' else -val

            if big_buy_sum > 0:
                active_ex_count += 1
                res[name] = f"{big_buy_sum/10000:.1f}万"
        except:
            res[name] = "⚠️"

    res["净流入(万)"] = round(total_net_flow / 10000, 1)
    res["共振"] = "🚨" if active_ex_count >= 3 else ""
    return res

# ==========================================
# 3. UI 界面与主循环
# ==========================================
st.title("🏹 全网资金流向指挥部 (稳定版)")

with st.sidebar:
    st.header("⚙️ 监控设置")
    big_val = st.number_input("大单定义 (USDT)", value=20000, step=5000)
    # 默认值改为 40 秒，确保直连 IP 不被封锁
    refresh_rate = st.slider("扫描间隔 (秒)", 5, 120, 40)
    st.divider()
    st.write("📈 **绿涨红跌** (国际标准)")
    st.write("🚨 **全网共振**：3家以上所同时有大买单")

placeholder = st.empty()

# 主运行循环
while True:
    data_list = []
    # 限制并发数，保护直连 IP 稳定性
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(fetch_symbol_data, sym, big_val) for sym in SYMBOLS]
        for f in futures:
            try:
                result = f.result()
                if result: data_list.append(result)
            except:
                pass

    if data_list:
        df = pd.DataFrame(data_list)
        if 'raw_sort' in df.columns:
            df = df.sort_values("raw_sort", ascending=False).drop(columns="raw_sort")
        
        with placeholder.container():
            st.write(f"🔄 更新于: {time.strftime('%H:%M:%S')} | 下次更新预计在 {refresh_rate}秒 后")
            
            # 颜色渲染逻辑
            def color_logic(val):
                if not isinstance(val, str): return ''
                if '+' in val: return 'color: #28a745; font-weight: bold' # 绿涨
                if '-' in val: return 'color: #dc3545; font-weight: bold' # 红跌
                return 'color: #212529'

            # 表格样式应用
            st.dataframe(
                df.style.applymap(color_logic, subset=[f"{tf}涨跌" for tf in TFS if f"{tf}涨跌" in df.columns])
                        .set_properties(**{'background-color': '#f8f9fa'}, subset=['OKX', 'Gate', 'Huobi', 'Bitget']),
                use_container_width=True, height=600
            )
    
    # 强制休眠预设的间隔时间
    time.sleep(refresh_rate)
