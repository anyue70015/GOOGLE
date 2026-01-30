import streamlit as st
import pandas as pd
import ccxt
import time
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 1. 基础配置
# ==========================================
st.set_page_config(page_title="资金预警-完整容错版", layout="wide")

st.markdown("""
    <style>
    .stDataFrame { opacity: 1.0 !important; }
    .stApp { background-color: white; }
    </style>
    """, unsafe_allow_html=True)

# 你的币种列表
SYMBOLS = ["BTC", "ETH", "SOL", "AAVE", "DOGE", "TAO", "SUI", "RENDER", "UNI", "HYPE", "XRP","ADA", "BCH", "LINK", "LTC", "TRX", "CC", "ASTER", "ZEC"]
EXCHANGE_IDS = {'OKX': 'okx', 'Gate': 'gateio', 'Huobi': 'htx', 'Bitget': 'bitget'}

# 初始化信号记忆（如果不存在）
if 'signal_memory' not in st.session_state:
    st.session_state.signal_memory = {}

# ==========================================
# 2. 强力容错抓取引擎
# ==========================================
def fetch_worker(symbol, big_val_threshold):
    pair = f"{symbol}/USDT"
    # 默认全部初始化为 "NO" 或 0
    res = {
        "币种": symbol, "最新价": "NO", 
        "OKX": "NO", "Gate": "NO", "Huobi": "NO", "Bitget": "NO", 
        "OBV预警": "正常", "预警等级": 0, "net_flow": 0, "active_count": 0
    }
    tf_list = ['1m', '15m', '1h', '4h', '24h', '7d']
    for tf in tf_list: res[f"{tf}涨跌"] = "NO"

    try:
        # 使用 OKX 获取多周期行情
        ex_main = ccxt.okx({'timeout': 3000})
        # 批量获取数据
        for tf in ['1m', '15m', '1h', '4h', '1d', '1w']:
            try:
                ohlcv = ex_main.fetch_ohlcv(pair, tf, limit=2)
                if len(ohlcv) >= 2:
                    ch = ((ohlcv[-1][4] - ohlcv[-1][1]) / ohlcv[-1][1]) * 100
                    key = f"{tf}涨跌" if tf not in ['1d', '1w'] else ("24h涨跌" if tf == '1d' else "7d涨跌")
                    res[key] = ch # 存入浮点数供计算
                else:
                    # 如果只有一根K线，涨幅为0
                    key = f"{tf}涨跌" if tf not in ['1d', '1w'] else ("24h涨跌" if tf == '1d' else "7d涨跌")
                    res[key] = 0.0
            except: continue
        
        tk = ex_main.fetch_ticker(pair)
        res["最新价"] = tk['last']
    except:
        pass # OKX 拿不到就保持 "NO"

    # 扫描各交易所大单
    for name, eid in EXCHANGE_IDS.items():
        try:
            ex_obj = getattr(ccxt, eid)({'timeout': 2000})
            trades = ex_obj.fetch_trades(pair, limit=30)
            exchange_buy = 0
            for t in trades:
                val = t['price'] * t['amount']
                side_sign = 1 if t['side'] == 'buy' else -1
                res['net_flow'] += val * side_sign
                if t['side'] == 'buy' and val >= big_val_threshold:
                    exchange_buy += val
            if exchange_buy > 0:
                res['active_count'] += 1
                res[name] = f"{exchange_buy/10000:.1f}万"
        except:
            res[name] = "NO"

    # 计算 OBV 背离 (仅在数据非 NO 时计算)
    try:
        h1_change = res.get('1h涨跌', 0)
        if isinstance(h1_change, (int, float)):
            if h1_change < -0.5 and res['net_flow'] > 0 and res['active_count'] >= 1:
                res['OBV预警'] = "💎底背离(吸筹)"
            elif h1_change > 0.5 and res['net_flow'] < 0:
                res['OBV预警'] = "⚠️顶背离(派发)"
    except: pass

    return res

# ==========================================
# 3. 界面与主循环
# ==========================================
st.title("🏹 渐进式监控指挥部 - 完整容错版")

with st.sidebar:
    st.header("⚙️ 参数控制")
    big_val = st.number_input("大单阈值 (USDT)", value=20000, step=5000)
    interval = st.slider("扫描间隔 (秒)", 10, 120, 30)
    st.write("---")
    st.markdown("✅ **容错机制已开启**：若交易所无此币或网络超时，对应列显示 `NO`。")

placeholder = st.empty()

while True:
    with ThreadPoolExecutor(max_workers=len(SYMBOLS)) as executor:
        results = list(executor.map(lambda s: fetch_worker(s, big_val), SYMBOLS))
    
    curr_t = time.time()
    for r in results:
        # 自动初始化记忆键值，彻底解决 KeyError
        symbol = r['币种']
        if symbol not in st.session_state.signal_memory:
            st.session_state.signal_memory[symbol] = {"level": 0, "time": 0}
            
        lvl = 0
        raw_1m = r.get('1m涨跌', 0)
        if isinstance(raw_1m, (int, float)) and raw_1m >= 0.5:
            lvl = 1
            if r['active_count'] == 2: lvl = 2
            if r['active_count'] >= 3: lvl = 3
        
        # 底背离提升权重
        if "底背离" in r['OBV预警']: lvl = max(lvl, 2)
        
        if lvl > 0:
            st.session_state.signal_memory[symbol] = {"level": lvl, "time": curr_t}
        
        mem = st.session_state.signal_memory[symbol]
        r['预警等级'] = mem['level'] if curr_t - mem['time'] < 900 else 0

    # 格式化 DataFrame 用于展示
    df = pd.DataFrame(results)
    
    # 将涨幅数字转为带百分比的字符串，如果是 "NO" 则保持原样
    tf_cols = ["1m涨跌", "15m涨跌", "1h涨跌", "4h涨跌", "24h涨跌", "7d涨跌"]
    for col in tf_cols:
        df[col] = df[col].apply(lambda x: f"{x:+.2f}%" if isinstance(x, (int, float)) else x)

    # 排序：1m涨幅高的排前面
    df = df.sort_values("1m涨跌", ascending=False)

    with placeholder.container():
        st.write(f"🔄 更新时间: {time.strftime('%H:%M:%S')} | 状态: 稳定运行中")
        
        def row_style(row):
            if "底背离" in str(row['OBV预警']):
                return ['background-color: #E6F3FF; color: #004085; font-weight: bold'] * len(row)
            lvl = row['预警等级']
            if lvl == 3: return ['background-color: #FF4500; color: white'] * len(row)
            if lvl == 2: return ['background-color: #FFD700; color: black'] * len(row)
            if lvl == 1: return ['background-color: #FFFFE0; color: black'] * len(row)
            return [''] * len(row)

        def color_ch(val):
            if not isinstance(val, str): return ''
            if '+' in val: return 'color: #28a745; font-weight: bold'
            if '-' in val: return 'color: #dc3545; font-weight: bold'
            return ''

        # 最终显示的列顺序
        cols = ["预警等级", "币种", "最新价", "OBV预警"] + tf_cols + ["OKX", "Gate", "Huobi", "Bitget"]
        st.dataframe(
            df[cols].style.apply(row_style, axis=1).applymap(color_ch, subset=tf_cols),
            use_container_width=True, height=650
        )

    time.sleep(interval)
