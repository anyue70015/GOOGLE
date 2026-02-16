import streamlit as st
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import ccxt
import numpy as np
from datetime import datetime, timedelta

# ────────────────────────────────────────────────
# Streamlit 頁面設定
# ────────────────────────────────────────────────
st.set_page_config(
    page_title="OKX Multi-Indicator Dashboard",
    layout="wide",
    page_icon="📊"
)

st.title("OKX EMA + SuperTrend + UT Bot + VWAP + Pivot + EMA Cloud")
st.markdown("資料來自 OKX 公開 API（無需 API Key） | 指標邏輯盡量還原 Pine Script v5")

# ────────────────────────────────────────────────
# 使用者輸入區
# ────────────────────────────────────────────────
col1, col2, col3, col4 = st.columns([2, 2, 2, 1])

with col1:
    symbol = st.selectbox("交易對", 
                          ["BTC-USDT", "ETH-USDT", "SOL-USDT", "XRP-USDT", "ADA-USDT", "DOGE-USDT", "BNB-USDT"],
                          index=0)

with col2:
    timeframe = st.selectbox("時間框架", 
                             ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"],
                             index=3)  # 預設 15m

with col3:
    bars_back = st.slider("載入 K 線數量", 200, 1500, 800, step=100)

with col4:
    if st.button("重新載入最新資料", type="primary"):
        st.cache_data.clear()
        st.rerun()

# ────────────────────────────────────────────────
# 從 OKX 抓取 OHLCV 資料
# ────────────────────────────────────────────────
@st.cache_data(ttl=45)  # 快取 45 秒，適合即時圖表
def fetch_okx_ohlcv(symbol_str, tf, limit):
    try:
        exchange = ccxt.okx({'enableRateLimit': True, 'options': {'defaultType': 'swap'}})  # 永續合約流動性較好
        ohlcv = exchange.fetch_ohlcv(symbol_str + '-SWAP', timeframe=tf, limit=limit)
        if not ohlcv:
            return pd.DataFrame()
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        return df
    except Exception as e:
        st.error(f"抓取資料失敗：{str(e)}")
        return pd.DataFrame()

with st.spinner("正在從 OKX 載入最新資料..."):
    df = fetch_okx_ohlcv(symbol, timeframe, bars_back)

if df.empty:
    st.error("無法取得資料，請稍後重試或更換交易對/時間框架。")
    st.stop()

# 基本清理
df = df.dropna(subset=['open', 'high', 'low', 'close'])

# ────────────────────────────────────────────────
# 計算所有指標（與 Pine Script 盡量一致）
# ────────────────────────────────────────────────
# EMA
df['ema10']  = ta.ema(df['close'], length=10)
df['ema20']  = ta.ema(df['close'], length=20)
df['ema50']  = ta.ema(df['close'], length=50)
df['ema200'] = ta.ema(df['close'], length=200)

# EMA cross 用於雲顏色變化
df['ema_bull_cross'] = (df['ema10'] > df['ema20']) & (df['ema10'].shift(1) <= df['ema20'].shift(1))
df['ema_bear_cross'] = (df['ema10'] < df['ema20']) & (df['ema10'].shift(1) >= df['ema20'].shift(1))

# SuperTrend
st_res = ta.supertrend(high=df['high'], low=df['low'], close=df['close'], length=10, multiplier=3.0)
df['supertrend']     = st_res['SUPERT_10_3.0']
df['st_bull']        = df['close'] > df['supertrend']

# UT Bot（你的原版邏輯：uptrend 時 stop 在下方）
atr = ta.atr(high=df['high'], low=df['low'], close=df['close'], length=10)
ut_stop = pd.Series(np.nan, index=df.index, dtype=float)

for i in range(1, len(df)):
    prev = ut_stop.iloc[i-1]
    c = df['close'].iloc[i]
    a = atr.iloc[i]
    if pd.isna(prev):
        ut_stop.iloc[i] = c - 1.0 * a
    else:
        if c > prev:
            ut_stop.iloc[i] = max(prev, c - 1.0 * a)
        else:
            ut_stop.iloc[i] = min(prev, c + 1.0 * a)

df['ut_stop'] = ut_stop
df['ut_bull'] = df['close'] > df['ut_stop']
df['ut_bear'] = df['close'] < df['ut_stop']  # 明確定義 bear

# 訊號（關鍵修正：處理 shift 後的 NaN）
df['buy_signal'] = (
    df['ut_bull'] &
    (~df['ut_bull'].shift(1).fillna(False)) &
    (df['ema10'] > df['ema20'])
)

df['sell_signal'] = (
    df['ut_bear'] &
    (~df['ut_bear'].shift(1).fillna(False))
    # 可選：& (df['ema10'] < df['ema20'])  若想對 sell 也加 EMA 過濾
)

# VWAP
df['vwap'] = ta.vwap(high=df['high'], low=df['low'], close=df['close'], volume=df['volume'])

# 今日 Pivot Point
daily = df.resample('D').agg({'high': 'max', 'low': 'min', 'close': 'last'})
daily['pivot'] = (daily['high'] + daily['low'] + daily['close']) / 3
df = df.join(daily['pivot'], how='left')
df['today_pivot'] = df['pivot'].ffill()

# 清理 NaN（避免畫圖出問題）
df = df.dropna(subset=['ema10', 'ema20', 'ema50', 'ema200', 'supertrend', 'ut_stop', 'vwap', 'today_pivot'])

# ────────────────────────────────────────────────
# Checklist 表格（模擬 Pine Script 右上角 panel）
# ────────────────────────────────────────────────
st.subheader("最新狀態 Checklist")

latest = df.iloc[-1]

checklist_data = {
    "指標": [
        "EMA 10 > EMA 20",
        "Close > EMA 50",
        "Close > EMA 200",
        "SuperTrend Bull",
        "UT Bot Bull",
        "Close > VWAP",
        "Close > Today Pivot"
    ],
    "狀態": [
        "YES" if latest['ema10'] > latest['ema20'] else "NO",
        "YES" if latest['close'] > latest['ema50'] else "NO",
        "YES" if latest['close'] > latest['ema200'] else "NO",
        "YES" if latest['st_bull'] else "NO",
        "YES" if latest['ut_bull'] else "NO",
        "YES" if latest['close'] > latest['vwap'] else "NO",
        "YES" if latest['close'] > latest['today_pivot'] else "NO"
    ]
}

checklist_df = pd.DataFrame(checklist_data)

def style_status(val):
    if val == "YES":
        return 'background-color: #004d00; color: lime; font-weight: bold;'
    else:
        return 'background-color: #4d0000; color: red; font-weight: bold;'

styled_checklist = checklist_df.style.applymap(style_status, subset=['狀態'])
st.dataframe(styled_checklist, use_container_width=True, hide_index=True)

# ────────────────────────────────────────────────
# Plotly 主圖表
# ────────────────────────────────────────────────
fig = make_subplots(rows=1, cols=1, shared_xaxes=True)

# K線
fig.add_trace(
    go.Candlestick(
        x=df.index,
        open=df['open'], high=df['high'], low=df['low'], close=df['close'],
        name='K線', increasing_line_color='#00ff9d', decreasing_line_color='#ff3366'
    ),
    row=1, col=1
)

# EMA 線
fig.add_trace(go.Scatter(x=df.index, y=df['ema10'],  name='EMA 10',  line=dict(color='orange', width=2)))
fig.add_trace(go.Scatter(x=df.index, y=df['ema20'],  name='EMA 20',  line=dict(color='blue',   width=2)))
fig.add_trace(go.Scatter(x=df.index, y=df['ema50'],  name='EMA 50',  line=dict(color='green',  width=2)))
fig.add_trace(go.Scatter(x=df.index, y=df['ema200'], name='EMA 200', line=dict(color='red',    width=2)))

# EMA Cloud
bull = df[df['ema10'] >= df['ema20']]
bear = df[df['ema10'] < df['ema20']]
fig.add_trace(go.Scatter(x=bull.index, y=bull['ema10'], line=dict(color='rgba(0,0,0,0)'), showlegend=False))
fig.add_trace(go.Scatter(x=bull.index, y=bull['ema20'], fill='tonexty', fillcolor='rgba(0,255,0,0.18)', name='Bull Cloud'))
fig.add_trace(go.Scatter(x=bear.index, y=bear['ema10'], line=dict(color='rgba(0,0,0,0)'), showlegend=False))
fig.add_trace(go.Scatter(x=bear.index, y=bear['ema20'], fill='tonexty', fillcolor='rgba(255,0,0,0.18)', name='Bear Cloud'))

# SuperTrend
fig.add_trace(go.Scatter(x=df.index, y=df['supertrend'], name='SuperTrend', line=dict(color='yellow', width=2)))

# UT Bot
fig.add_trace(go.Scatter(
    x=df.index, y=df['ut_stop'], name='UT Bot',
    line=dict(color=np.where(df['ut_bull'], 'lime', 'red'), width=2)
))

# VWAP & Pivot
fig.add_trace(go.Scatter(x=df.index, y=df['vwap'],       name='VWAP',       line=dict(color='purple',  width=2, dash='dot')))
fig.add_trace(go.Scatter(x=df.index, y=df['today_pivot'], name='Today Pivot', line=dict(color='yellow', width=2, dash='dot')))

# Buy / Sell 標籤
buy_idx  = df[df['buy_signal']].index
sell_idx = df[df['sell_signal']].index

fig.add_trace(go.Scatter(
    x=buy_idx, y=df.loc[buy_idx, 'low'] * 0.992,
    mode='markers+text',
    name='BUY',
    marker=dict(symbol='triangle-up', size=14, color='lime'),
    text=['BUY'] * len(buy_idx),
    textposition='bottom center',
    textfont=dict(color='black', size=12)
))

fig.add_trace(go.Scatter(
    x=sell_idx, y=df.loc[sell_idx, 'high'] * 1.008,
    mode='markers+text',
    name='SELL',
    marker=dict(symbol='triangle-down', size=14, color='red'),
    text=['SELL'] * len(sell_idx),
    textposition='top center',
    textfont=dict(color='white', size=12)
))

fig.update_layout(
    title=f"{symbol} {timeframe} – 多指標綜合看板",
    xaxis_rangeslider_visible=False,
    height=850,
    template='plotly_dark',
    hovermode='x unified',
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
)

st.plotly_chart(fig, use_container_width=True)

st.caption("提示：圖表可能因資料量大而稍慢，若卡頓可減少「載入 K 線數量」或切換較大時間框架。")
st.caption("UT Bot 使用原版邏輯（uptrend 時 trailing stop 在價格下方）。如需經典 QuantNomad 版 UT Bot 可再告知。")
