import streamlit as st
import ccxt.async_support as ccxt_async
import pandas as pd
import numpy as np
import asyncio
import time

# --- 页面配置 ---
st.set_page_config(page_title="2026多交易所聚合扫描器", layout="wide")
st.title("加密货币实时放量扫描器 (Binance镜像/数据加固版)")

# --- 币种列表处理 ---
uploaded = st.file_uploader("上传币种列表 (.txt)", type="txt")
if uploaded:
    content = uploaded.read().decode("utf-8")
    symbols = [line.strip().upper() for line in content.splitlines() if line.strip()]
    symbols = list(dict.fromkeys(symbols))
    symbols = [s if '/' in s else f"{s}/USDT" for s in symbols]
    st.success(f"已加载 {len(symbols)} 个交易对")
else:
    st.info("💡 请先上传交易对文件以启动监控")
    st.stop()

# --- 参数设置区 ---
col1, col2, col3, col4 = st.columns(4)
with col1:
    timeframe = st.selectbox("K线周期", ["1m", "5m", "15m", "1h"], index=1)
with col2:
    refresh_sec = st.slider("刷新间隔", 10, 120, 30)
with col3:
    vol_multiplier = st.slider("成交量放大倍数", 1.5, 5.0, 2.8)
with col4:
    min_change_pct = st.slider("方法2最小涨幅(%)", 0.1, 2.0, 0.6)

# --- 状态管理 ---
if 'alerted' not in st.session_state:
    st.session_state.alerted = set()
if st.button("重置警报记录"):
    st.session_state.alerted = set()

# --- 交易所配置 (解决币安连接) ---
ex_config = {
    'binance': {
        'urls': {'api': {'public': 'https://api1.binance.com'}},
        'proxies': {'http': 'http://127.0.0.1:10809', 'https': 'http://127.0.0.1:10809'} # 若不通请检查端口
    },
    'okx': {}, 'gate': {}, 'bitget': {}, 'huobi': {}, 'bybit': {}
}

# 实例化
exchanges = {}
for name, cfg in ex_config.items():
    ex_class = getattr(ccxt_async, name if name != 'huobi' else 'htx')
    exchanges[name] = ex_class({
        'enableRateLimit': True,
        'options': {'defaultType': 'spot'},
        **cfg
    })

# --- 核心抓取函数 ---
async def fetch_ohlcv(ex, symbol, timeframe, limit):
    try:
        # 增加 5 秒超时，防止某个交易所挂起导致整体阻塞
        data = await asyncio.wait_for(ex.fetch_ohlcv(symbol, timeframe, limit=limit), timeout=5.0)
        return data, None
    except Exception as e:
        return None, str(e)

async def process_symbol(symbol, timeframe):
    N = {"1m": 60, "5m": 20, "15m": 12, "1h": 8}[timeframe]
    tasks = [fetch_ohlcv(ex, symbol, timeframe, N + 10) for ex in exchanges.values()]
    results = await asyncio.gather(*tasks)
    
    agg_df = None
    success_list = []
    fail_list = []
    
    for (name, ex), (ohlcv, err) in zip(exchanges.items(), results):
        if ohlcv and len(ohlcv) > 5:
            df = pd.DataFrame(ohlcv, columns=['t','o','h','l','c','v'])
            success_list.append(name)
            if agg_df is None:
                agg_df = df.copy()
            else:
                agg_df['v'] += df['v'] # 累加聚合成交量
        else:
            fail_list.append(name)
            
    return agg_df, success_list, fail_list

# --- 主循环渲染 ---
placeholder = st.empty()

async def main():
    while True:
        data_rows = []
        for symbol in symbols:
            df, success, fails = await process_symbol(symbol, timeframe)
            
            status = f"✅{len(success)} ❌{len(fails)}"
            if 'binance' in fails: status += " (Binance仍离线)"
            
            # --- 数据加固保护：防止 ValueError ---
            if df is None or len(df) < 5:
                data_rows.append([symbol, "无数据", "", "", "", "", "", status])
                continue
                
            # 确保数值类型正确且无空值
            for col in ['c','o','h','l','v']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            df = df.dropna(subset=['c','v'])

            if len(df) < 2: continue
            
            curr_c, prev_c = df['c'].iloc[-1], df['c'].iloc[-2]
            curr_v, avg_v = df['v'].iloc[-1], df['v'].iloc[:-1].tail(20).mean()
            vol_ratio = curr_v / avg_v if avg_v > 0 else 0
            price_change = (curr_c - prev_c) / prev_c * 100

            # --- 信号算法 ---
            sig1 = (curr_c > df['o'].iloc[-1]) and (vol_ratio > vol_multiplier)
            sig2 = (vol_ratio > 1.0) and (price_change > min_change_pct)
            
            # 修复 np.diff 的 sig3 逻辑
            sig3 = False
            if len(df) >= 20:
                c_vals = df['c'].values
                v_vals = df['v'].values
                # 关键修复点：diff 之前确保长度足够
                if len(c_vals) > 1:
                    price_diff = np.diff(c_vals)
                    # np.sign(diff) 得到 1, -1, 0，乘以 v 得到方向成交量
                    obv_series = np.cumsum(np.sign(price_diff) * v_vals[1:])
                    if len(obv_series) >= 10:
                        obv_ma = pd.Series(obv_series).rolling(10).mean().iloc[-1]
                        sig3 = (obv_series[-1] > obv_ma * 1.05) and (price_change > 0)

            # --- 统计展示 ---
            sig_list = [str(i) for i, s in enumerate([sig1, sig2, sig3], 1) if s]
            has_sig = len(sig_list) > 0
            
            data_rows.append([
                symbol, f"{curr_c:.4f}", f"{price_change:+.2f}%",
                f"{curr_v:,.0f}", f"{vol_ratio:.2f}x", 
                ",".join(sig_list), "⚠️" if has_sig else "", status
            ])
            
            # 警报 Key：币种+周期+分钟级时间戳，防止同根K线重复报警
            alert_key = f"{symbol}_{timeframe}_{int(time.time()//60)}"
            if has_sig and alert_key not in st.session_state.alerted:
                st.toast(f"🚨 {symbol} 信号！放量{vol_ratio:.1f}x")
                st.session_state.alerted.add(alert_key)

        # 渲染表格
        df_final = pd.DataFrame(data_rows, columns=["交易对","现价","涨幅","聚合成交量","放量比","方法","信号","状态"])
        # 按放量比排序
        df_final['v_val'] = pd.to_numeric(df_final['放量比'].str.replace('x',''), errors='coerce').fillna(0)
        df_final = df_final.sort_values('v_val', ascending=False).drop(columns=['v_val'])

        with placeholder.container():
            st.write(f"⏱️ 更新于: {time.strftime('%H:%M:%S')} (已修正 OBV 溢出错误)")
            st.dataframe(df_final.style.apply(lambda x: ['background-color: #3e0000' if x['信号'] == "⚠️" else '' for _ in x], axis=1), 
                         use_container_width=True, height=600)

        await asyncio.sleep(refresh_sec)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        st.error(f"⚠️ 致命错误: {e}")
        time.sleep(5)
        st.rerun()
