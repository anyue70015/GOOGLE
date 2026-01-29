import streamlit as st
import ccxt
import pandas as pd
import numpy as np
import time

st.set_page_config(page_title="多交易所聚合放量扫描器", layout="wide")
st.title("加密货币现货实时放量/吃单扫描器（OKX + Gate + Bitget + Binance镜像聚合）")

# 上传币种列表
uploaded = st.file_uploader("上传币种列表 (.txt，每行一个，如 BTC/USDT 或 BTC)", type="txt")
if uploaded:
    content = uploaded.read().decode("utf-8")
    symbols = [line.strip().upper() for line in content.splitlines() if line.strip()]
    symbols = list(dict.fromkeys(symbols))
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

# 创建四个交易所实例
exchanges = {
    'okx': ccxt.okx({'enableRateLimit': True, 'options': {'defaultType': 'spot'}}),
    'gate': ccxt.gate({'enableRateLimit': True, 'options': {'defaultType': 'spot'}}),
    'bitget': ccxt.bitget({'enableRateLimit': True, 'options': {'defaultType': 'spot'}}),
    'binance': ccxt.binance({
        'enableRateLimit': True,
        'options': {'defaultType': 'spot'},
        'urls': {
            'api': {
                'public': 'https://www.bmwweb.academy/api/v3',
                'private': 'https://www.bmwweb.academy/api/v3',
            }
        }
    })
}

placeholder = st.empty()
alert_container = st.empty()

while True:
    data_rows = []
    new_alerts = []

    for symbol in symbols:
        agg_df = None
        agg_volumes = []
        successful_ex = []  # 记录成功获取的交易所

        for ex_name, ex in exchanges.items():
            try:
                ohlcv = ex.fetch_ohlcv(symbol, timeframe, limit=N_for_avg + 10)
                if not ohlcv:
                    continue

                df_ex = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                agg_volumes.append(df_ex['volume'].iloc[-1])
                successful_ex.append(ex_name)  # 成功记录

                if agg_df is None:
                    agg_df = df_ex
                else:
                    agg_df['volume'] += df_ex['volume']  # 累加 volume

            except Exception:
                pass  # 失败不记录

        if not successful_ex or agg_df is None or len(agg_df) < N_for_avg + 5:
            data_rows.append([symbol, "历史不足/空", "", "", "", "", "成功所: 无"])
            continue

        current_close = float(agg_df['close'].iloc[-1])
        current_open = float(agg_df['open'].iloc[-1])
        current_high = float(agg_df['high'].iloc[-1])
        current_low = float(agg_df['low'].iloc[-1])
        current_vol = float(agg_df['volume'].iloc[-1])

        prev_close = float(agg_df['close'].iloc[-2])

        if current_vol <= 0:
            data_rows.append([symbol, f"{current_close:.2f}", "Vol=0", "0", "0.00x", "", f"成功所: {', '.join(successful_ex)}"])
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
            "⚠️" if has_signal else ""
        ]
        data_rows.append(row)

        key = f"{symbol}_{timeframe}"
        if has_signal and key not in st.session_state.alerted:
            alert_msg = f"【{symbol} {timeframe}】聚合吃单信号！涨幅{price_change:+.2f}%，放量{vol_ratio:.2f}x → 方法{signals_display}"
            new_alerts.append(alert_msg)
            st.session_state.alerted.add(key)

            st.components.v1.html(
                """
                <audio autoplay>
                    <source src="https://www.soundjay.com/buttons/beep-07.mp3" type="audio/mpeg">
                </audio>
                <script>
                    var audio = document.querySelector('audio');
                    audio.play().catch(function(error) {
                        console.log("Autoplay blocked: " + error);
                        alert("浏览器阻止自动播放声音，请点击页面允许音频");
                    });
                </script>
                """,
                height=0
            )

    columns = ["交易对", "当前价", "涨幅", "聚合成交量", "放量倍数", "触发方法", "信号"]
    df_display = pd.DataFrame(data_rows, columns=columns)

    def highlight(row):
        return ['background-color: #ffcccc' if row["信号"] == "⚠️" else ''] * len(row)

    styled = df_display.style.apply(highlight, axis=1)

    with placeholder.container():
        st.subheader(f"当前监控（OKX+Gate+Bitget+Binance镜像聚合，周期：{timeframe}，刷新间隔：{refresh_sec}秒）")
        st.dataframe(styled, use_container_width=True, height=600)

        if new_alerts:
            for msg in new_alerts:
                st.error(msg)

    time.sleep(refresh_sec)
    st.rerun()
