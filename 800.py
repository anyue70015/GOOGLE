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
st.set_page_config(page_title="OKX Indicator Dashboard", layout="wide")

st.title("OKX EMA + SuperTrend + UT Bot + VWAP + Pivot Dashboard")
st.markdown("資料來源：OKX 公開市場 API（無需 API Key）")

# ────────────────────────────────────────────────
# 使用者輸入（類似 Pine 的 input）
# ────────────────────────────────────────────────
col1, col2, col3 = st.columns(3)

with col1:
    symbol = st.selectbox("交易對 (OKX 格式)", 
                          ["BTC-USDT", "ETH-USDT", "SOL-USDT", "XRP-USDT", "ADA-USDT"], 
                          index=0)
with col2:
    timeframe = st.selectbox("時間框架", 
                             ["1m", "3m", "5m", "15m", "30m", "1H", "2H", "4H", "1D"], 
                             index=3)  # 預設 15m
with col3:
    bars_back = st.slider("載入多少根 K 線（最大約 1440）", 100, 1440, 500)

# ────────────────────────────────────────────────
# 從 OKX 抓資料（使用 ccxt）
# ────────────────────────────────────────────────
@st.cache_data(ttl=60)  # 快取 60 秒，避免頻繁請求
def fetch_okx_ohlcv(symbol, timeframe, limit):
    exchange = ccxt.okx({'enableRateLimit': True})
    since = int((datetime.now() - timedelta(days=30)).timestamp() * 1000)  # 預防抓不夠
    ohlcv = exchange.fetch_ohlcv(symbol + "-SWAP", timeframe, limit=limit)  # 永續合約為例，你可改 SPOT
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    return df

with st.spinner("正在從 OKX 載入資料..."):
    df = fetch_okx_ohlcv(symbol, timeframe, bars_back)

if df.empty:
    st.error("無法載入資料，請稍後再試或換個交易對/時間框架")
    st.stop()

# ────────────────────────────────────────────────
# 計算指標（與 Pine 盡量一致）
# ────────────────────────────────────────────────
# EMA
df['ema10']  = ta.ema(df['close'], length=10)
df['ema20']  = ta.ema(df['close'], length=20)
df['ema50']  = ta.ema(df['close'], length=50)
df['ema200'] = ta.ema(df['close'], length=200)

# EMA cross
df['ema_bull_cross'] = (df['ema10'] > df['ema20']) & (df['ema10'].shift(1) <= df['ema20'].shift(1))
df['ema_bear_cross'] = (df['ema10'] < df['ema20']) & (df['ema10'].shift(1) >= df['ema20'].shift(1))

# SuperTrend
st_res = ta.supertrend(high=df['high'], low=df['low'], close=df['close'], length=10, multiplier=3.0)
df['supertrend'] = st_res[f'SUPERT_10_3.0']
df['st_bull'] = df['close'] > df['supertrend']

# UT Bot（照你原版邏輯）
atr = ta.atr(high=df['high'], low=df['low'], close=df['close'], length=10)
ut_stop = pd.Series(np.nan, index=df.index)
for i in range(1, len(df)):
    prev = ut_stop.iloc[i-1]
    c = df['close'].iloc[i]
    if pd.isna(prev):
        ut_stop.iloc[i] = c - 1.0 * atr.iloc[i]
    else:
        if c > prev:
            ut_stop.iloc[i] = max(prev, c - 1.0 * atr.iloc[i])
        else:
            ut_stop.iloc[i] = min(prev, c + 1.0 * atr.iloc[i])
df['ut_stop'] = ut_stop
df['ut_bull'] = df['close'] > df['ut_stop']

# 訊號
df['buy_signal']  = df['ut_bull'] & ~df['ut_bull'].shift(1) & (df['ema10'] > df['ema20'])
df['sell_signal'] = df['ut_bull'].shift(1) & ~df['ut_bull']   # 翻轉成 bear 時

# VWAP（pandas_ta 預設是累計的，可改成每日重置）
df['vwap'] = ta.vwap(df['high'], df['low'], df['close'], df['volume'])

# Today Pivot（每日）
daily = df.resample('D').agg({'high':'max', 'low':'min', 'close':'last'})
daily['pivot'] = (daily['high'] + daily['low'] + daily['close']) / 3
df = df.join(daily['pivot'], how='left')
df['today_pivot'] = df['pivot'].ffill()

# ────────────────────────────────────────────────
# Checklist 表格（模擬 Pine 的右上 panel）
# ────────────────────────────────────────────────
st.subheader("Checklist（最新一根狀態）")
latest = df.iloc[-1]

data = {
    "指標": ["EMA 10 > EMA 20", "Close > EMA 50", "Close > EMA 200", 
             "SuperTrend Bull", "UT Bot Bull", "Close > VWAP", "Close > Today Pivot"],
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
checklist_df = pd.DataFrame(data)

# 顏色樣式
def color_status(val):
    color = 'lime' if val == 'YES' else 'red'
    return f'background-color: {color}; color: black'

styled = checklist_df.style.applymap(color_status, subset=['狀態'])
st.dataframe(styled, use_container_width=True, hide_index=True)

# ────────────────────────────────────────────────
# Plotly 圖表
# ────────────────────────────────────────────────
fig = make_subplots(rows=1, cols=1)

# K線
fig.add_trace(go.Candlestick(x=df.index,
                             open=df['open'], high=df['high'],
                             low=df['low'], close=df['close'],
                             name='K線'), row=1, col=1)

# EMA & Cloud
fig.add_trace(go.Scatter(x=df.index, y=df['ema10'], name='EMA10', line=dict(color='orange')))
fig.add_trace(go.Scatter(x=df.index, y=df['ema20'], name='EMA20', line=dict(color='blue')))

bull = df[df['ema10'] >= df['ema20']]
bear = df[df['ema10'] < df['ema20']]
fig.add_trace(go.Scatter(x=bull.index, y=bull['ema10'], line=dict(color='rgba(0,0,0,0)'), showlegend=False))
fig.add_trace(go.Scatter(x=bull.index, y=bull['ema20'], fill='tonexty', fillcolor='rgba(0,255,0,0.15)', name='Bull Cloud'))
fig.add_trace(go.Scatter(x=bear.index, y=bear['ema10'], line=dict(color='rgba(0,0,0,0)'), showlegend=False))
fig.add_trace(go.Scatter(x=bear.index, y=bear['ema20'], fill='tonexty', fillcolor='rgba(255,0,0,0.15)', name='Bear Cloud'))

# 其他線（可自行加 SuperTrend, UT, VWAP, Pivot）
fig.add_trace(go.Scatter(x=df.index, y=df['supertrend'], name='SuperTrend', line=dict(color='yellow')))
fig.add_trace(go.Scatter(x=df.index, y=df['ut_stop'], name='UT Bot', line=dict(color=df['ut_bull'].map({True:'lime', False:'red'}))))

# Buy/Sell 標籤
buy_idx = df[df['buy_signal']].index
sell_idx = df[df['sell_signal']].index
fig.add_trace(go.Scatter(x=buy_idx, y=df.loc[buy_idx]['low']*0.995, mode='markers+text',
                         marker=dict(symbol='triangle-up', size=12, color='lime'),
                         text='BUY', textposition='bottom center', name='BUY'))
fig.add_trace(go.Scatter(x=sell_idx, y=df.loc[sell_idx]['high']*1.005, mode='markers+text',
                         marker=dict(symbol='triangle-down', size=12, color='red'),
                         text='SELL', textposition='top center', name='SELL'))

fig.update_layout(title=f"{symbol} {timeframe} 指標圖", xaxis_rangeslider_visible=False,
                  height=700, template='plotly_dark', hovermode='x unified')

st.plotly_chart(fig, use_container_width=True)

st.info("提示：Streamlit Cloud 免費版有流量限制，若圖表卡頓可減少 bars_back 數量。")
