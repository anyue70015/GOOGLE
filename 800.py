import streamlit as st
import ccxt.async_support as ccxt_async  # Use async for faster fetches
import pandas as pd
import numpy as np
import asyncio
import time

st.set_page_config(page_title="多交易所聚合放量扫描器", layout="wide")
st.title("加密货币现货实时放量/吃单扫描器（OKX+Gate+Bitget+Binance+Huobi+Bybit聚合）")

# 上传币种列表
uploaded = st.file_uploader("上传币种列表 (.txt，每行一个，如 BTC/USDT 或 BTC)", type="txt")
if uploaded:
    content = uploaded.read().decode("utf-8")
    symbols = [line.strip().upper() for line in content.splitlines() if line.strip()]
    symbols = list(dict.fromkeys(symbols))  # Remove duplicates
    symbols = [s if '/' in s else f"{s}/USDT" for s in symbols]
    symbols = [s.replace('-', '/') for s in symbols]
    symbols = [s if not s.endswith('/USDT/USDT') else s.replace('/USDT/USDT', '/USDT') for s in symbols]
    st.success(f"已加载 {len(symbols)} 个交易对")
    st.write("监控列表：", ", ".join(symbols[:10]) + " ..." if len(symbols) > 10 else ", ".join(symbols))
else:
    st.info("请先上传包含交易对的txt文件")
    st.stop()

# 参数设置
col1, col2, col3, col4 = st.columns(4)
with col1:
    timeframe = st.selectbox("K线周期", ["1m", "5m", "15m", "1h"], index=1)
with col2:
    refresh_sec = st.slider("刷新间隔（秒）", 30, 120, 60)
with col3:
    vol_multiplier = st.slider("聚合放量倍数阈值", 1.5, 5.0, 2.8, 0.01)
with col4:
    min_change_pct = st.slider("方法2最小涨幅(%)", 0.3, 2.0, 0.6, 0.1)

use_method1 = st.checkbox("方法1：阳线 + 异常放量", value=True)
use_method2 = st.checkbox("方法2：放量上涨 + 尾盘强势（需放量>1x）", value=True)
use_method3 = st.checkbox("方法3：OBV急升（需放量>1x）", value=True)

N_for_avg = {"1m": 60, "5m": 20, "15m": 12, "1h": 8}[timeframe]
vol_multiplier_adjusted = vol_multiplier + (0.5 if timeframe == "1m" else 0)

if 'alerted' not in st.session_state:
    st.session_state.alerted = set()

# Reset alerts button
if st.button("重置警报"):
    st.session_state.alerted = set()

# 创建六个异步交易所实例
exchanges = {
    'okx': ccxt_async.okx({'enableRateLimit': True, 'options': {'defaultType': 'spot'}}),
    'gate': ccxt_async.gate({'enableRateLimit': True, 'options': {'defaultType': 'spot'}}),
    'bitget': ccxt_async.bitget({'enableRateLimit': True, 'options': {'defaultType': 'spot'}}),
    'binance': ccxt_async.binance({
        'enableRateLimit': True,
        'options': {'defaultType': 'spot'},
        'urls': {
            'api': {
                'public': 'https://api.binance.com/api/v3',  # Official URL
                'private': 'https://api.binance.com/api/v3',
            }
        }
    }),
    'huobi': ccxt_async.htx({'enableRateLimit': True, 'options': {'defaultType': 'spot'}}),
    'bybit': ccxt_async.bybit({'enableRateLimit': True, 'options': {'defaultType': 'spot'}})
}

placeholder = st.empty()
alert_container = st.empty()

async def fetch_ohlcv_async(ex, symbol, timeframe, limit):
    try:
        return await ex.fetch_ohlcv(symbol, timeframe, limit=limit)
    except Exception as e:
        return None  # Return None on failure

async def process_symbol(symbol, exchanges, timeframe, N_for_avg):
    agg_df = None
    successful_ex = []
    failed_ex = []
    tasks = [fetch_ohlcv_async(ex, symbol, timeframe, N_for_avg + 10) for ex in exchanges.values()]
    results = await asyncio.gather(*tasks)

    for ex_name, ohlcv in zip(exchanges.keys(), results):
        if ohlcv and len(ohlcv) > 0:
            df_ex = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            successful_ex.append(ex_name)
            if agg_df is None:
                agg_df = df_ex
            else:
                agg_df['volume'] += df_ex['volume']
        else:
            failed_ex.append(ex_name)

    return agg_df, successful_ex, failed_ex

while True:
    data_rows = []
    new_alerts = []
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    for symbol in symbols:
        agg_df, successful_ex, failed_ex = loop.run_until_complete(process_symbol(symbol, exchanges, timeframe, N_for_avg))

        fetch_status = f"成功: {', '.join(successful_ex)} | 失败: {', '.join(failed_ex) if failed_ex else '无'}"

        if not successful_ex or agg_df is None or len(agg_df) < N_for_avg + 5:
            data_rows.append([symbol, "历史不足/空", "", "", "", "", "", fetch_status])
            continue

        current_close = float(agg_df['close'].iloc[-1])
        current_open = float(agg_df['open'].iloc[-1])
        current_high = float(agg_df['high'].iloc[-1])
        current_low = float(agg_df['low'].iloc[-1])
        current_vol = float(agg_df['volume'].iloc[-1])
        prev_close = float(agg_df['close'].iloc[-2])
        if current_vol <= 0:
            data_rows.append([symbol, f"{current_close:.2f}", "Vol=0", "0", "0.00x", "", "", fetch_status])
            continue

        avg_vol = float(agg_df['volume'].iloc[:-1].mean())
        vol_ratio = current_vol / avg_vol if avg_vol > 0 else 0.0
        price_change = (current_close - prev_close) / prev_close * 100 if prev_close != 0 else 0.0

        signal1 = use_method1 and (current_close > current_open) and (vol_ratio > vol_multiplier_adjusted) and (vol_ratio > 1.0)
        signal2 = use_method2 and (vol_ratio > 1.0) and (((price_change > min_change_pct) and (vol_ratio > vol_multiplier_adjusted)) or ((current_high - current_close) / (current_high - current_low + 1e-8) < 0.3))
        signal3 = False
        if use_method3 and len(agg_df) >= 21 and vol_ratio > 1.0:
            obv = (np.sign(agg_df['close'].diff()) * agg_df['volume']).fillna(0).cumsum()
            obv_ma = float(obv.rolling(20).mean().iloc[-1])
            current_obv = float(obv.iloc[-1])
            signal3 = (current_obv > obv_ma * 1.05) and (price_change > 0)

        has_signal = signal1 or signal2 or signal3
        signals_str = []
        if signal1: signals_str.append("1")
        if signal2: signals_str.append("2")
        if signal3: signals_str.append("3")
        signals_display = ", ".join(signals_str) if signals_str else ""

        row = [
            symbol,
            f"{current_close:.2f}",
            f"{price_change:+.2f}%",
            f"{int(current_vol):,}",
            f"{vol_ratio:.2f}x",
            signals_display,
            "⚠️" if has_signal else "",
            fetch_status
        ]
        data_rows.append(row)

        key = f"{symbol}_{timeframe}"
        if has_signal and key not in st.session_state.alerted:
            alert_msg = f"【{symbol} {timeframe}】聚合吃单信号！涨幅{price_change:+.2f}%，放量{vol_ratio:.2f}x → 方法{signals_display}"
            new_alerts.append(alert_msg)
            st.session_state.alerted.add(key)

            # Audio alert (browser may block; fallback to Streamlit error)
            st.components.v1.html(
                """
                <audio autoplay>
                    <source src="https://www.soundjay.com/buttons/beep-07.mp3" type="audio/mpeg">
                </audio>
                <script>
                    var audio = document.querySelector('audio');
                    audio.play().catch(function(error) {
                        console.log("Autoplay blocked: " + error);
                    });
                </script>
                """,
                height=0
            )

    columns = ["交易对", "当前价", "涨幅", "聚合成交量", "放量倍数", "触发方法", "信号", "成功/失败交易所"]
    df_display = pd.DataFrame(data_rows, columns=columns)
    # Sort by vol_ratio descending for better visibility (handle non-numeric safely)
    df_display['放量倍数数'] = pd.to_numeric(df_display['放量倍数'].str.rstrip('x'), errors='coerce').fillna(0)
    df_display = df_display.sort_values(by='放量倍数数', ascending=False).drop(columns='放量倍数数')

    def highlight(row):
        return ['background-color: #ffcccc' if row["信号"] == "⚠️" else ''] * len(row)

    styled = df_display.style.apply(highlight, axis=1)

    with placeholder.container():
        st.subheader(f"当前监控（OKX+Gate+Bitget+Binance+Huobi+Bybit聚合，周期：{timeframe}，刷新间隔：{refresh_sec}秒）")
        st.dataframe(styled, use_container_width=True, height=min(600, len(df_display) * 35 + 50))

    if new_alerts:
        for msg in new_alerts:
            st.error(msg)

    # Clean up async loop
    loop.close()
    time.sleep(refresh_sec)
    st.rerun()
