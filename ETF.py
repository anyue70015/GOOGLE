import streamlit as st
import ccxt.async_support as ccxt_async
import pandas as pd
import numpy as np
import asyncio
import time

st.set_page_config(page_title="2026超级周-多交易所聚合放量扫描器", layout="wide")
st.title("加密货币现货实时放量/吃单扫描器（修正币安镜像版）")

# 上传币种列表
uploaded = st.file_uploader("上传币种列表 (.txt，每行一个，如 BTC/USDT)", type="txt")
if uploaded:
    content = uploaded.read().decode("utf-8")
    symbols = [line.strip().upper() for line in content.splitlines() if line.strip()]
    symbols = list(dict.fromkeys(symbols))  # 去重
    symbols = [s if '/' in s else f"{s}/USDT" for s in symbols]
    symbols = [s.replace('-', '/') for s in symbols]
    symbols = [s if not s.endswith('/USDT/USDT') else s.replace('/USDT/USDT', '/USDT') for s in symbols]
    st.success(f"已加载 {len(symbols)} 个交易对")
else:
    st.info("💡 请先上传包含交易对的txt文件，准备应对下周1月27日法案行情")
    st.stop()

# 参数设置
col1, col2, col3, col4 = st.columns(4)
with col1:
    timeframe = st.selectbox("K线周期", ["1m", "5m", "15m", "1h"], index=1)
with col2:
    refresh_sec = st.slider("刷新间隔（秒）", 10, 120, 30) # 缩短最小间隔，应对剧烈波动
with col3:
    vol_multiplier = st.slider("聚合放量倍数阈值", 1.5, 5.0, 2.8, 0.1)
with col4:
    min_change_pct = st.slider("方法2最小涨幅(%)", 0.1, 2.0, 0.6, 0.1)

use_method1 = st.checkbox("方法1：阳线 + 异常放量", value=True)
use_method2 = st.checkbox("方法2：放量上涨 + 尾盘强势", value=True)
use_method3 = st.checkbox("方法3：OBV急升（主力深度建仓标志）", value=True)

N_for_avg = {"1m": 60, "5m": 20, "15m": 12, "1h": 8}[timeframe]
vol_multiplier_adjusted = vol_multiplier + (0.5 if timeframe == "1m" else 0)

if 'alerted' not in st.session_state:
    st.session_state.alerted = set()

if st.button("重置警报"):
    st.session_state.alerted = set()

# 创建异步交易所实例
# 特别针对币安使用了 api1.binance.com 镜像
exchanges = {
    'binance': ccxt_async.binance({
        'enableRateLimit': True,
        'urls': {
            'api': {
                'public': 'https://api1.binance.com',
            }
        },
        'options': {'defaultType': 'spot'},
        'proxies': {'http': 'http://127.0.0.1:10809', 'https': 'http://127.0.0.1:10809'}
    }),
    'okx': ccxt_async.okx({'enableRateLimit': True, 'options': {'defaultType': 'spot'}}),
    'gate': ccxt_async.gate({'enableRateLimit': True, 'options': {'defaultType': 'spot'}}),
    'bitget': ccxt_async.bitget({'enableRateLimit': True, 'options': {'defaultType': 'spot'}}),
    'huobi': ccxt_async.htx({'enableRateLimit': True, 'options': {'defaultType': 'spot'}}),
    'bybit': ccxt_async.bybit({'enableRateLimit': True, 'options': {'defaultType': 'spot'}})
}

placeholder = st.empty()

async def fetch_ohlcv_async(ex, symbol, timeframe, limit, ex_name):
    try:
        # 添加超时保护
        ohlcv = await asyncio.wait_for(ex.fetch_ohlcv(symbol, timeframe, limit=limit), timeout=5)
        return ohlcv, None
    except Exception as e:
        return None, str(e)

async def process_symbol(symbol, exchanges, timeframe, N_for_avg):
    agg_df = None
    successful_ex = []
    failed_ex = []
    
    tasks = [fetch_ohlcv_async(ex, symbol, timeframe, N_for_avg + 10, ex_name) for ex_name, ex in exchanges.items()]
    results = await asyncio.gather(*tasks)

    for ex_name, (ohlcv, error) in zip(exchanges.keys(), results):
        if ohlcv and len(ohlcv) > 0:
            df_ex = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            successful_ex.append(ex_name)
            if agg_df is None:
                agg_df = df_ex.copy()
            else:
                # 聚合各交易所交易量
                agg_df['volume'] += df_ex['volume']
        else:
            failed_ex.append(ex_name)

    return agg_df, successful_ex, failed_ex

async def main_loop():
    while True:
        data_rows = []
        new_alerts = []
        
        # 批量处理 symbol 以提高效率
        for symbol in symbols:
            agg_df, successful_ex, failed_ex = await process_symbol(symbol, exchanges, timeframe, N_for_avg)
            
            fetch_status = f"✅{len(successful_ex)} | ❌{len(failed_ex)}"
            if 'binance' in failed_ex: fetch_status += " (Binance连接失败)"

            if not successful_ex or agg_df is None or len(agg_df) < N_for_avg + 2:
                data_rows.append([symbol, "数据不足", "", "", "", "", "", fetch_status])
                continue

            # 数据提取与转换
            c = agg_df['close'].astype(float).values
            o = agg_df['open'].astype(float).values
            h = agg_df['high'].astype(float).values
            l = agg_df['low'].astype(float).values
            v = agg_df['volume'].astype(float).values
            
            curr_c, curr_o, curr_h, curr_l, curr_v = c[-1], o[-1], h[-1], l[-1], v[-1]
            prev_c = c[-2]
            
            # 计算放量比
            avg_v = v[:-1][-N_for_avg:].mean()
            vol_ratio = curr_v / avg_v if avg_v > 0 else 0
            price_change = (curr_c - prev_c) / prev_c * 100

            # 信号判断
            sig1 = use_method1 and (curr_c > curr_o) and (vol_ratio > vol_multiplier_adjusted)
            sig2 = use_method2 and (vol_ratio > 1.0) and ((price_change > min_change_pct) or ((curr_h - curr_c) / (curr_h - curr_l + 1e-8) < 0.2))
            
            sig3 = False
            if use_method3 and len(agg_df) >= 20:
                # 简易OBV计算
                diff = np.diff(c)
                obv_moves = np.sign(diff) * v[1:]
                obv = np.cumsum(obv_moves)
                if len(obv) >= 20:
                    obv_ma = pd.Series(obv).rolling(20).mean().iloc[-1]
                    sig3 = obv[-1] > obv_ma * 1.05 and price_change > 0

            has_signal = sig1 or sig2 or sig3
            sig_list = [i for i, s in enumerate([sig1, sig2, sig3], 1) if s]
            sig_str = ",".join(map(str, sig_list))

            data_rows.append([
                symbol, f"{curr_c:.4f}", f"{price_change:+.2f}%", 
                f"{curr_v:,.0f}", f"{vol_ratio:.2f}x", sig_str, 
                "⚠️" if has_signal else "", fetch_status
            ])

            # 警报逻辑
            alert_key = f"{symbol}_{timeframe}_{int(time.time() // (60 if timeframe=='1m' else 300))}"
            if has_signal and alert_key not in st.session_state.alerted:
                new_alerts.append(f"🚨 {symbol} {timeframe} 放量{vol_ratio:.1f}x (方法{sig_str})")
                st.session_state.alerted.add(alert_key)

        # 渲染表格
        df_display = pd.DataFrame(data_rows, columns=["交易对", "价格", "涨跌", "成交量", "放量比", "方法", "信号", "状态"])
        df_display['sort_v'] = pd.to_numeric(df_display['放量比'].str.replace('x',''), errors='coerce')
        df_display = df_display.sort_values('sort_v', ascending=False).drop(columns=['sort_v'])

        with placeholder.container():
            st.write(f"上次更新: {time.strftime('%H:%M:%S')}")
            st.dataframe(df_display.style.apply(lambda x: ['background-color: #430000' if x['信号'] == "⚠️" else '' for _ in x], axis=1), use_container_width=True)
            if new_alerts:
                for a in new_alerts: st.toast(a) # 使用 st.toast 更清爽

        await asyncio.sleep(refresh_sec)

# 启动异步
if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except Exception as e:
        st.error(f"系统运行错误: {e}")
