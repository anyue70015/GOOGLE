import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import ccxt
import yfinance as yf
from datetime import datetime

# ==================== 1. 定义四大 AI 的推荐组合 ====================
AI_PORTFOLIOS = {
    "GPT (BTC单押)": ["BTC-USDT"],
    "GROK (算力+避险)": ["VRT", "TSM", "SLV"],
    "GEMINI (共振+存储)": ["SNDK", "STX", "DY", "VRT"],
    "DEEPSEEK (存储全家桶)": ["SNDK", "STX", "WDC"]
}

def get_latest_prices(tickers):
    """同时获取加密货币和美股的最新涨跌幅"""
    results = {}
    for t in tickers:
        try:
            if "-USDT" in t: # 抓取加密货币 (OKX/Binance)
                exchange = ccxt.binance()
                ticker = exchange.fetch_ticker(t)
                results[t] = ticker['percentage'] # 24h 涨跌幅
            else: # 抓取美股 (Yahoo Finance)
                stock = yf.Ticker(t)
                data = stock.history(period="2d")
                if len(data) >= 2:
                    change = (data['Close'].iloc[-1] - data['Close'].iloc[-2]) / data['Close'].iloc[-2] * 100
                    results[t] = change
                else:
                    results[t] = 0.0
        except:
            results[t] = 0.0
    return results

# ==================== 2. 计算实时战斗力 ====================
st.title("⚔️ AI 诸神之战：带单大神实时排行")

with st.spinner('正在同步各路神仙的实战数据...'):
    # 获取所有涉及的标的价格
    all_tickers = list(set([item for sublist in AI_PORTFOLIOS.values() for item in sublist]))
    current_performance = get_latest_prices(all_tickers)

    performance_report = []
    for ai_name, symbols in AI_PORTFOLIOS.items():
        avg_change = sum([current_performance.get(s, 0) for s in symbols]) / len(symbols)
        performance_report.append({"AI 大神": ai_name, "组合平均涨幅 (%)": round(avg_change, 2)})

df_score = pd.DataFrame(performance_report).sort_values(by="组合平均涨幅 (%)", ascending=False)

# ==================== 3. 渲染雷达图/对比图 ====================
fig = go.Figure()

fig.add_trace(go.Bar(
    x=df_score["AI 大神"],
    y=df_score["组合平均涨幅 (%)"],
    marker_color=['#00ff00' if x > 0 else '#ff0000' for x in df_score["组合平均涨幅 (%)"]],
    text=df_score["组合平均涨幅 (%)"],
    textposition='auto',
))

fig.update_layout(
    title="今日 AI 组合收益率对比",
    xaxis_title="AI 派系",
    yaxis_title="涨跌幅 (%)",
    template="plotly_dark"
)

st.plotly_chart(fig, use_container_width=True)

# 展示排行榜
st.subheader("🏆 实时战力排名")
st.dataframe(df_score, hide_index=True)

# 老兵点评逻辑
top_ai = df_score.iloc[0]["AI 大神"]
st.info(f"**老兵点评：** 现在的带单大神是 **{top_ai}**。看来现在的市场风格更偏向它的逻辑。别急着追，看看它的组合里有没有刚回调的票！")
