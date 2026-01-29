import streamlit as st
import requests
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta

st.set_page_config(page_title="加密货币全网聚合放量扫描器", layout="wide")
st.title("加密货币实时放量/吃单扫描器（CoinGecko 全网聚合）")

# ==============================================
# 上传币种列表（CoinGecko ID 格式）
# ==============================================
st.info("CoinGecko 使用币种 ID（如 bitcoin、ethereum、solana）。请在 TXT 中填写 CoinGecko ID（小写），如 bitcoin")
uploaded = st.file_uploader("上传币种列表 (.txt，每行一个 CoinGecko ID，如 bitcoin)", type="txt")
if uploaded:
    content = uploaded.read().decode("utf-8")
    ids = [line.strip().lower() for line in content.splitlines() if line.strip()]
    ids = list(dict.fromkeys(ids))
    st.success(f"已加载 {len(ids)} 个币种")
    st.write("监控列表：", ", ".join(ids[:10]) + " ..." if len(ids) > 10 else ", ".join(ids))
else:
    st.info("请先上传包含 CoinGecko ID 的txt文件")
    st.stop()

# ==============================================
# 参数设置
# ==============================================
col1, col2, col3, col4 = st.columns(4)
with col1:
    interval_minutes = st.selectbox("聚合间隔（分钟）", [5, 15, 60], index=0)  # CoinGecko 最小5m
    timeframe = f"{interval_minutes}m"
with col2:
    refresh_sec = st.slider("刷新间隔（秒）", 60, 300, 120, help="CoinGecko 免费限频，建议120s+")
with col3:
    vol_multiplier = st.slider("全网放量倍数阈值", 1.5, 5.0, 2.8, 0.01)
with col4:
    min_change_pct = st.slider("方法2最小涨幅(%)", 0.3, 2.0, 0.6, 0.1)

use_method1 = st.checkbox("方法1：阳线 + 异常放量", value=True)
use_method2 = st.checkbox("方法2：放量上涨 + 尾盘强势（需放量>1x）", value=True)
use_method3 = st.checkbox("方法3：OBV急升（需放量>1x）", value=True)

# CoinGecko 参数
N_for_avg = {5: 20, 15: 12, 60: 8}[interval_minutes]  # 根据间隔调整平均窗口

# 状态管理
if 'alerted' not in st.session_state:
    st.session_state.alerted = set()

placeholder = st.empty()
alert_container = st.empty()

while True:
    data_rows = []
    new_alerts = []

    for coin_id in ids:
        try:
            # CoinGecko /coins/{id}/market_chart/range 接口
            now = int(time.time())
            days_ago = now - 86400 * 7  # 最近7天
            url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart/range?vs_currency=usd&from={days_ago}&to={now}&precision=2"
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()

            if 'prices' not in data or 'total_volumes' not in data:
                data_rows.append([coin_id, "数据缺失", "", "", "", "", ""])
                continue

            # 构建 DataFrame
            df = pd.DataFrame({
                'timestamp': [item[0] for item in data['prices']],
                'close': [item[1] for item in data['prices']],
                'volume': [item[1] for item in data['total_volumes']]
            })

            # 过滤到指定间隔（CoinGecko 返回的是原始数据，我们手动聚合到 5m/15m/1h）
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df = df.set_index('timestamp').resample(f'{interval_minutes}T').agg({
                'close': 'last',
                'volume': 'sum'
            }).dropna()

            if len(df) < N_for_avg + 5:
                data_rows.append([coin_id, "历史不足", "", "", "", "", f"根数={len(df)}"])
                continue

            df = df.tail(N_for_avg + 10)

            current_close = float(df['close'].iloc[-1])
            current_vol = float(df['volume'].iloc[-1])

            prev_close = float(df['close'].iloc[-2])

            if current_vol <= 0:
                data_rows.append([coin_id, f"{current_close:.2f}", "Vol=0", "0", "0.00x", "", ""])
                continue

            avg_vol = float(df['volume'].iloc[:-1].mean())
            vol_ratio = current_vol / avg_vol if avg_vol > 0 else 0.0

            price_change = (current_close - prev_close) / prev_close * 100 if prev_close != 0 else 0.0

            # 方法1
            signal1 = False
            if use_method1:
                # CoinGecko 没有 open/high/low，只能用 close 变化判断“阳线”
                is_bull = price_change > 0
                vol_spike = vol_ratio > vol_multiplier
                signal1 = is_bull and vol_spike and vol_ratio > 1.0

            # 方法2
            signal2 = False
            if use_method2 and vol_ratio > 1.0:
                vol_spike = vol_ratio > vol_multiplier
                signal2 = (price_change > min_change_pct) and vol_spike

            # 方法3
            signal3 = False
            if use_method3 and len(df) >= 21 and vol_ratio > 1.0:
                obv = (np.sign(df['close'].diff()) * df['volume']).fillna(0).cumsum()
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
                coin_id.upper(),
                f"{current_close:.2f}",
                f"{price_change:+.2f}%",
                f"{int(current_vol):,}",
                f"{vol_ratio:.2f}x",
                signals_display,
                "⚠️" if has_signal else ""
            ]
            data_rows.append(row)

            key = f"{coin_id}_{timeframe}"
            if has_signal and key not in st.session_state.alerted:
                alert_msg = f"【{coin_id.upper()}】全网吃单信号！涨幅{price_change:+.2f}%，放量{vol_ratio:.2f}x → 方法{signals_display}"
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

        except Exception as e:
            data_rows.append([coin_id, "错误", str(e)[:50], "", "", "", ""])

    columns = ["币种", "当前价 (USD)", "涨幅", "全网成交量", "放量倍数", "触发方法", "信号"]
    df_display = pd.DataFrame(data_rows, columns=columns)

    def highlight(row):
        return ['background-color: #ffcccc' if row["信号"] == "⚠️" else ''] * len(row)

    styled = df_display.style.apply(highlight, axis=1)

    with placeholder.container():
        st.subheader(f"当前监控（CoinGecko 全网聚合，周期：{timeframe}，刷新间隔：{refresh_sec}秒）")
        st.dataframe(styled, use_container_width=True, height=600)

        if new_alerts:
            for msg in new_alerts:
                st.error(msg)

    time.sleep(refresh_sec)
    st.rerun()
