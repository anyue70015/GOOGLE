import streamlit as st
import requests
import numpy as np

# ============ 页面基础设置 ============
st.set_page_config(page_title="回测信号面板", layout="wide")
st.markdown(
    """
    <style>
    body { background:#05060a; }
    .main { background:#05060a; padding-top:10px !important; }

    h1 { font-size:26px !important; font-weight:700 !important; margin-bottom:6px !important; }

    .card {
        background:#14151d;
        border-radius:14px;
        padding:14px 16px 12px;
        border:1px solid #262736;
        box-shadow:0 18px 36px rgba(0,0,0,0.45);
        color:#f5f5f7;
        font-size:13px;
        transition:0.15s;
        margin-bottom:18px;
    }
    .card:hover {
        transform:translateY(-3px);
        box-shadow:0 26px 48px rgba(0,0,0,0.6);
    }

    .card-section {
        display:flex;
        justify-content:space-between;
        align-items:flex-end;
        gap:10px;
    }
    .section-divider {
        border-bottom:1px solid #1f2030;
        margin:10px 0;
    }

    .symbol-line {
        display:flex;
        gap:10px;
        align-items:center;
        font-size:19px;
        margin-bottom:2px;
    }
    .symbol-name { font-weight:800; }
    .symbol-ticker {
        font-size:12px;
        color:#9ca3af;
        padding:2px 6px;
        border:1px solid #262736;
        border-radius:10px;
        background:#0d0e13;
    }
    .symbol-price {
        font-size:19px;
    }
    .change-up { color:#4ade80; font-size:14px; }
    .change-down { color:#fb7185; font-size:14px; }

    .indicator-grid {
        display:flex;
        flex-direction:column;
        gap:8px;
        margin-top:4px;
    }
    .indicator-item {
        display:flex;
        align-items:center;
        justify-content:space-between;
        width:100%;
        background:#191b27;
        border:1px solid #202233;
        border-radius:10px;
        padding:8px 10px;
        font-size:12px;
        color:#d4d4d8;
    }
    .dot { width:6px;height:6px;border-radius:2px;display:inline-block;margin-left:6px; }
    .dot-bull { background:#4ade80; box-shadow:0 0 0 1px rgba(74,222,128,0.25); }
    .dot-neutral { background:#facc15; box-shadow:0 0 0 1px rgba(250,204,21,0.25); }
    .dot-bear { background:#fb7185; box-shadow:0 0 0 1px rgba(251,113,133,0.25); }

    .label { color:#9ca3af; }
    .prob-good { color:#4ade80; font-weight:600; }
    .prob-mid { color:#facc15; font-weight:600; }
    .prob-bad { color:#fb7185; font-weight:600; }

    .score{
        font-size:12px;
        color:#9ca3af;
        margin-top:8px;
        display:flex;
        align-items:center;
        gap:8px;
    }
    .score-label{
        font-size:13px;
        font-weight:700;
        color:#e5e7eb;
        min-width:70px;
    }
    .dot-score{
        width:9px;
        height:9px;
        border-radius:50%;
        display:inline-block;
        margin-right:2px;
    }
    .dot-score-buy{ background:#4ade80; }
    .dot-score-hold{ background:#facc15; }
    .dot-score-sell{ background:#fb7185; }
    .dot-score-off{ background:#4b5563; }
    .advice-text{
        font-size:13px;
        font-weight:600;
    }
    .advice-buy{ color:#4ade80; }
    .advice-hold{ color:#facc15; }
    .advice-sell{ color:#fb7185; }
    .profit-row { font-size:12px; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("回测信号面板")

# ============ 回测配置 ============
BACKTEST_OPTIONS = ["3个月", "6个月", "1年", "2年", "3年", "5年", "10年"]
BACKTEST_CONFIG = {
    "3个月": {"range": "3mo", "interval": "1d", "steps_per_day": 1},
    "6个月": {"range": "6mo", "interval": "1d", "steps_per_day": 1},
    "1年":   {"range": "1y",  "interval": "1d", "steps_per_day": 1},
    "2年":   {"range": "2y",  "interval": "1d", "steps_per_day": 1},
    "3年":   {"range": "3y",  "interval": "1d", "steps_per_day": 1},
    "5年":   {"range": "5y",  "interval": "1d", "steps_per_day": 1},
    "10年":  {"range": "10y", "interval": "1d", "steps_per_day": 1},
}

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={range}&interval={interval}"
YAHOO_QUOTE_URL = "https://query1.finance.yahoo.com/v7/finance/quote?symbols={symbol}"

# ============ 工具函数（略，同之前） ============
# (为了篇幅，这里省略了不变的函数：format_symbol_for_yahoo, contains_chinese, search_eastmoney_symbol,
# search_yahoo_symbol_by_name, resolve_user_input_symbol, fetch_display_name, get_current_price,
# fetch_yahoo_ohlcv, ema_np, macd_hist_np, rsi_np, atr_np, rolling_mean_np, obv_np,
# backtest_with_stats, prob_class, decide_advice)

# 请从上一个版本复制这些函数进来，它们没有变化。

# ============ 计算单只股票 ============
def compute_stock_metrics(symbol: str, cfg_key: str):
    cfg = BACKTEST_CONFIG[cfg_key]
    yahoo_symbol = format_symbol_for_yahoo(symbol)
    display_name = fetch_display_name(symbol, yahoo_symbol)

    current_price, current_change = get_current_price(yahoo_symbol)

    close, high, low, volume = fetch_yahoo_ohlcv(
        yahoo_symbol, cfg["range"], cfg["interval"]
    )

    macd_hist = macd_hist_np(close)
    rsi = rsi_np(close)
    atr = atr_np(high, low, close)
    obv = obv_np(close, volume)

    vol_ma20 = rolling_mean_np(volume, 20)
    atr_ma20 = rolling_mean_np(atr, 20)
    obv_ma20 = rolling_mean_np(obv, 20)

    sig_macd = (macd_hist > 0).astype(int)
    sig_vol = (volume > vol_ma20 * 1.1).astype(int)
    sig_rsi = (rsi >= 60).astype(int)
    sig_atr = (atr > atr_ma20 * 1.1).astype(int)
    sig_obv = (obv > obv_ma20 * 1.05).astype(int)

    score_arr = sig_macd + sig_vol + sig_rsi + sig_atr + sig_obv

    spd = cfg["steps_per_day"]
    steps7 = 7 * spd
    steps30 = 30 * spd

    prob7, avg7, _, _, pf7, _, avg_win7, avg_loss7 = backtest_with_stats(
        close[:-1] if len(close) > 1 else close,
        score_arr[:-1] if len(score_arr) > 1 else score_arr,
        steps7
    )
    prob30, avg30, _, _, pf30, _, avg_win30, avg_loss30 = backtest_with_stats(
        close[:-1] if len(close) > 1 else close,
        score_arr[:-1] if len(score_arr) > 1 else score_arr,
        steps30
    )

    price = current_price if current_price is not None else float(close[-1])
    change = current_change if current_change is not None else (
        float(close[-1] / close[-2] - 1) * 100 if len(close) >= 2 else 0.0
    )

    last_idx = -1
    indicators = []

    macd_status = "bull" if float(macd_hist[last_idx]) > 0 else "bear"
    indicators.append({"name": "MACD 多头/空头", "status": macd_status, "desc": ""})

    vol_ratio = float(volume[last_idx] / (vol_ma20[last_idx] + 1e-9))
    vol_status = "bull" if vol_ratio > 1.10 else "bear" if vol_ratio < 0.90 else "neutral"
    indicators.append({"name": "成交量相对20日均量", "status": vol_status, "desc": f"1.10 / {vol_ratio:.2f}"})

    rsi_val = float(rsi[last_idx])
    rsi_status = "bull" if rsi_val >= 60 else "bear" if rsi_val <= 40 else "neutral"
    indicators.append({"name": "RSI 区间", "status": rsi_status, "desc": f"60.0 / {rsi_val:.1f}"})

    atr_ratio = float(atr[last_idx] / (atr_ma20[last_idx] + 1e-9))
    atr_status = "bull" if atr_ratio > 1.10 else "bear" if atr_ratio < 0.90 else "neutral"
    indicators.append({"name": "ATR 波动率", "status": atr_status, "desc": f"1.10 / {atr_ratio:.2f}"})

    obv_ratio = float(obv[last_idx] / (obv_ma20[last_idx] + 1e-9))
    obv_status = "bull" if obv_ratio > 1.05 else "bear" if obv_ratio < 0.95 else "neutral"
    indicators.append({"name": "OBV 资金趋势", "status": obv_status, "desc": f"1.05 / {obv_ratio:.2f}"})

    return {
        "symbol": yahoo_symbol,
        "display_name": display_name,
        "price": price,
        "change": change,
        "prob7": float(prob7),
        "prob30": float(prob30),
        "pf7": float(pf7),
        "pf30": float(pf30),
        "avg_win7": float(avg_win7),
        "avg_loss7": float(avg_loss7),
        "avg_win30": float(avg_win30),
        "avg_loss30": float(avg_loss30),
        "indicators": indicators,
    }

@st.cache_data(show_spinner=False)
def get_stock_metrics_cached(symbol: str, cfg_key: str, _version: int = 16):
    return compute_stock_metrics(symbol, cfg_key)

# ============ 交互层 ============
# (同之前代码，不变)

# ============ 卡片展示（关键修复部分） ============
if not rows:
    st.info("暂无自选股票，请先在上方输入代码添加。")
else:
    cols_per_row = 4
    for i in range(0, len(rows), cols_per_row):
        cols = st.columns(cols_per_row)
        for col, row in zip(cols, rows[i:i + cols_per_row]):
            with col:
                change_class = "change-up" if row["change"] >= 0 else "change-down"
                change_str = f"{row['change']:+.2f}%"

                prob7_pct = row["prob7"] * 100
                prob30_pct = row["prob30"] * 100

                avg_win7_pct = row["avg_win7"] * 100
                avg_loss7_pct = row["avg_loss7"] * 100
                avg_win30_pct = row["avg_win30"] * 100
                avg_loss30_pct = row["avg_loss30"] * 100

                pf7 = row["pf7"]
                pf30 = row["pf30"]

                prob7_class = prob_class(row["prob7"])
                prob30_class = prob_class(row["prob30"])

                indicators_html = ""
                for ind in row["indicators"]:
                    line = f"{ind['name']} ({ind['desc']})" if ind["desc"] else ind["name"]
                    indicators_html += f"<div class='indicator-item'><span>{line}</span><span class='dot dot-{ind['status']}'></span></div>"

                adv7_label, adv7_intensity, adv7_kind = decide_advice(row["prob7"], pf7)
                adv30_label, adv30_intensity, adv30_kind = decide_advice(row["prob30"], pf30)

                def build_advice_html(label, intensity, kind):
                    if kind == "buy":
                        dot_class = "dot-score dot-score-buy"
                        text_class = "advice-text advice-buy"
                    elif kind == "sell":
                        dot_class = "dot-score dot-score-sell"
                        text_class = "advice-text advice-sell"
                    else:
                        dot_class = "dot-score dot-score-hold"
                        text_class = "advice-text advice-hold"
                    dots = "<span class='{0}'></span>".format(dot_class) * intensity + "<span class='dot-score dot-score-off'></span>" * (5 - intensity)
                    return text_class, label, dots

                adv7_class, adv7_text, adv7_dots = build_advice_html(adv7_label, adv7_intensity, adv7_kind)
                adv30_class, adv30_text, adv30_dots = build_advice_html(adv30_label, adv30_intensity, adv30_kind)

                display_name = row.get("display_name", row["symbol"])
                ticker_label = row["symbol"]

                # 使用单三引号避免嵌套问题
                html = f'''
                <div class="card">
                  <div class="card-section">
                    <div class="symbol-line">
                      <span class="symbol-name">{display_name}</span>
                      <span class="symbol-ticker">{ticker_label}</span>
                    </div>
                    <div style="display:flex; gap:6px; align-items:center;">
                      <span class="symbol-price">${row["price"]:.2f}</span>
                      <span class="{change_class}">{change_str}</span>
                    </div>
                  </div>

                  <div class="section-divider"></div>

                  <div class="indicator-grid">
                    {indicators_html}
                  </div>

                  <div class="section-divider"></div>

                  <div>
                    <div class="profit-row" style="display:flex;justify-content:space-between;gap:8px;margin-bottom:4px;">
                      <div>
                        <span class="label">7日盈利概率</span>
                        <span class="{prob7_class}"> {prob7_pct:.1f}%</span>
                      </div>
                      <div class="label">均盈 {avg_win7_pct:+.1f}% / 均亏 {avg_loss7_pct:+.1f}% / 盈亏 {pf7:.2f}</div>
                    </div>
                    <div class="profit-row" style="display:flex;justify-content:space-between;gap:8px;">
                      <div>
                        <span class="label">30日盈利概率</span>
                        <span class="{prob30_class}"> {prob30_pct:.1f}%</span>
                      </div>
                      <div class="label">均盈 {avg_win30_pct:+.1f}% / 均亏 {avg_loss30_pct:+.1f}% / 盈亏 {pf30:.2f}</div>
                    </div>
                  </div>

                  <div class="section-divider"></div>

                  <div class="score">
                    <span class="score-label">7日信号</span>
                    <span class="{adv7_class}">{adv7_text}</span>
                    {adv7_dots}
                  </div>
                  <div class="score">
                    <span class="score-label">30日信号</span>
                    <span class="{adv30_class}">{adv30_text}</span>
                    {adv30_dots}
                  </div>
                </div>
                '''
                st.markdown(html, unsafe_allow_html=True)

st.caption(
    "价格和涨跌幅基于 Yahoo Finance 最新报价（美股接近实时，非交易时段显示最近收盘价）。"
    "回测信号基于历史完整K线数据，仅供个人研究参考，不构成投资建议。"
)
