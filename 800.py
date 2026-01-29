import streamlit as st
import ccxt.async_support as ccxt_async
import pandas as pd
import numpy as np
import asyncio
import time
import nest_asyncio

# 关键：允许 Streamlit 环境下嵌套 asyncio 运行
nest_asyncio.apply()

# --- 页面配置 ---
st.set_page_config(page_title="2026量化神兵-直连优化版", layout="wide")

st.title("🚀 加密货币聚合扫描器 (直连优化版 - 优先Binance)")
st.markdown("优先使用 Binance 数据做放量判断（最可靠）。节点超时可侧边栏切换。")

# --- 侧边栏：直连节点切换 ---
st.sidebar.title("🌐 节点设置")
binance_node = st.sidebar.selectbox("币安节点（优先性能集群）", 
    ["api1.binance.com", "api2.binance.com", "api3.binance.com", "api4.binance.com", 
     "api.binance.com", "api-gcp.binance.com"],
    index=0)

# --- 币种列表处理 ---
uploaded = st.file_uploader("上传币种列表 (.txt)", type="txt")
if uploaded:
    content = uploaded.read().decode("utf-8")
    symbols = [line.strip().upper() for line in content.splitlines() if line.strip()]
    symbols = list(dict.fromkeys(symbols))  # 去重
    symbols = [s if '/' in s else f"{s}/USDT" for s in symbols]
    st.success(f"已加载 {len(symbols)} 个交易对")
else:
    st.stop()

# --- 主参数 ---
timeframe = st.selectbox("周期", ["1m", "5m", "15m", "1h"], index=1)
refresh_sec = st.slider("刷新间隔(秒)", 5, 60, 20)
vol_multiplier = st.slider("放量阈值 (x)", 1.0, 5.0, 2.5)

# --- 交易所实例化 ---
exchanges = {}
ex_list = ['binance', 'okx', 'gate', 'bitget', 'bybit']  # 去 huobi，用 bybit 更活跃

for name in ex_list:
    cfg = {
        'enableRateLimit': True,
        'options': {'defaultType': 'spot', 'adjustForTimeDifference': True},
        'timeout': 20000,  # 20秒宽限
    }
    if name == 'binance':
        cfg['urls'] = {'api': {'public': f'https://{binance_node}'}}
    
    ex_class = getattr(ccxt_async, name)
    exchanges[name] = ex_class(cfg)

# Binance 单独提出来优先用
binance_ex = exchanges['binance']

# --- 数据抓取 ---
async def fetch_ohlcv(ex, symbol, timeframe, limit):
    try:
        data = await asyncio.wait_for(ex.fetch_ohlcv(symbol, timeframe, limit=limit), timeout=30.0)
        return data, None
    except Exception as e:
        return None, str(e)

async def process_symbol(symbol, timeframe):
    N = {"1m": 40, "5m": 20, "15m": 12, "1h": 8}[timeframe]
    limit = N + 10  # 多取几根更安全

    # 优先尝试 Binance
    binance_ohlcv, binance_err = await fetch_ohlcv(binance_ex, symbol, timeframe, limit)
    
    if binance_ohlcv and len(binance_ohlcv) >= N:
        df = pd.DataFrame(binance_ohlcv, columns=['t','o','h','l','c','v'])
        source = "Binance"
        success = ["binance"]
        fails = []
    else:
        # fallback 到其他交易所
        fallback_names = [name for name in exchanges if name != 'binance']
        other_tasks = [fetch_ohlcv(exchanges[name], symbol, timeframe, limit) for name in fallback_names]
        other_results = await asyncio.gather(*other_tasks, return_exceptions=True)
        
        df = None
        source = "无数据"
        success = []
        fails = ["binance (优先失败)"]
        
        for name, result in zip(fallback_names, other_results):
            if isinstance(result, Exception):
                fails.append(f"{name} (异常: {str(result)})")
                continue
            ohlcv, err = result
            if ohlcv and len(ohlcv) >= N:
                df = pd.DataFrame(ohlcv, columns=['t','o','h','l','c','v'])
                source = name.capitalize()
                success = [name]
                fails = ["binance"] + [n for n in fallback_names if n != name]
                break
            else:
                fails.append(name)

    if df is None:
        return None, success, fails, source
    
    return df, success, fails, source

placeholder = st.empty()

async def main_loop():
    while True:
        data_rows = []
        for symbol in symbols:
            df, success, fails, source = await process_symbol(symbol, timeframe)
            status = f"源:{source} | ✅{len(success)} ❌{len(fails)}"
            if 'binance' in fails or 'binance (优先失败)' in fails:
                status += " (Binance超时/失败)"
            
            if df is None or len(df) < 5:
                data_rows.append([symbol, "-", "-", "-", "-", "", "", status])
                continue
                
            df[['c','o','v']] = df[['c','o','v']].apply(pd.to_numeric, errors='coerce')
            curr_c = df['c'].iloc[-1]
            prev_c = df['c'].iloc[-2] if len(df) > 1 else curr_c
            curr_v = df['v'].iloc[-1]
            # 用最近20根（不含当前）做平均
            avg_v_slice = df['v'].iloc[-21:-1]
            avg_v = avg_v_slice.mean() if not avg_v_slice.empty else 1.0
            vol_ratio = curr_v / avg_v if avg_v > 0 else 0
            change = (curr_c - prev_c) / prev_c * 100 if prev_c != 0 else 0

            sig1 = (curr_c > df['o'].iloc[-1]) and (vol_ratio > vol_multiplier)
            sig2 = (vol_ratio > 1.2) and (change > 0.5)
            
            sig_list = [str(i) for i, s in enumerate([sig1, sig2], 1) if s]
            signal_str = ",".join(sig_list)
            alert = "⚠️" if sig_list else ""
            
            data_rows.append([
                symbol, f"{curr_c:.4f}", f"{change:+.2f}%", f"{curr_v:,.0f}", 
                f"{vol_ratio:.2f}x", signal_str, alert, status
            ])

        if data_rows:
            df_final = pd.DataFrame(data_rows, columns=["交易对","现价","涨幅(1根)","成交量","放量比","信号","警报","状态"])
            
            # 安全排序
            df_final['放量比_num'] = pd.to_numeric(df_final['放量比'].str.replace('x', ''), errors='coerce').fillna(0)
            df_final = df_final.sort_values('放量比_num', ascending=False).drop(columns=['放量比_num'])

            # 样式
            def style_rows(row):
                if row["警报"] == "⚠️":
                    return ['background-color: rgba(255, 75, 75, 0.12); color: #FF4B4B; font-weight: bold;'] * len(row)
                return [''] * len(row)

            with placeholder.container():
                st.write(f"⏱️ 更新: {time.strftime('%Y-%m-%d %H:%M:%S')} | 节点: {binance_node} | 间隔: {refresh_sec}s")
                st.dataframe(
                    df_final.style.apply(style_rows, axis=1),
                    use_container_width=True,
                    height=800
                )
        
        await asyncio.sleep(refresh_sec)

# --- 运行入口 ---
if __name__ == "__main__":
    asyncio.run(main_loop())
