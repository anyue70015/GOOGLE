import streamlit as st
import yfinance as yf
import numpy as np
import time
import re
import pandas as pd
import shutil
import platformdirs

# ==================== 頁面設置 ====================
st.set_page_config(page_title="回測信號面板 - yfinance 版", layout="wide")

st.markdown(
    """
    <style>
    body { background:#05060a; }
    .main { background:#05060a; padding-top:10px !important; }
    h1 { font-size:26px !important; font-weight:700 !important; margin-bottom:6px !important; }
    .stCode { background:#14151d; border:1px solid #262736; border-radius:10px; padding:12px; color:#e5e7eb; font-family:Consolas, monospace; white-space:pre; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("回測信號面板 - 自助掃描（yfinance 版，按 PF7 排序）")

# ==================== 配置 ====================
BACKTEST_OPTIONS = ["3個月", "6個月", "1年", "2年", "3年", "5年", "10年"]
BACKTEST_CONFIG = {
    "3個月": {"period": "3mo", "interval": "1d"},
    "6個月": {"period": "6mo", "interval": "1d"},
    "1年":  {"period": "1y",  "interval": "1d"},
    "2年":  {"period": "2y",  "interval": "1d"},
    "3年":  {"period": "3y",  "interval": "1d"},
    "5年":  {"period": "5y",  "interval": "1d"},
    "10年": {"period": "10y", "interval": "1d"},
}

# ==================== 清除快取按鈕（解決 cookie 舊資料問題） ====================
if st.button("清除 yfinance 快取（價格或資料持續失敗時按）", type="secondary"):
    cache_dir = platformdirs.user_cache_dir("py-yfinance")
    shutil.rmtree(cache_dir, ignore_errors=True)
    st.success("快取已清除！請重新執行掃描。")
    st.rerun()

# ==================== 工具函數 ====================
def format_symbol_for_yahoo(symbol: str) -> str:
    sym = symbol.strip().upper()
    if sym.isdigit() and len(sym) == 6:
        if sym.startswith(("600", "601", "603", "605", "688")):
            return f"{sym}.SS"
        if sym.startswith(("000", "001", "002", "003", "300", "301")):
            return f"{sym}.SZ"
    return sym

@st.cache_data(ttl=300)
def get_current_prices_batch(symbols: list):
    if not symbols:
        return {}
    
    yahoo_syms = [format_symbol_for_yahoo(s) for s in symbols]
    result = {}
    
    try:
        # 批量下載最近 5 天資料，取最新 Close 與前一天比較漲跌幅
        df = yf.download(
            yahoo_syms,
            period="5d",
            interval="1d",
            group_by="ticker",
            threads=True,
            progress=False,
            auto_adjust=False,
            prepost=False
        )
        
        for orig_sym, y_sym in zip(symbols, yahoo_syms):
            try:
                if len(yahoo_syms) > 1:
                    sub_df = df[y_sym]
                else:
                    sub_df = df
                
                if sub_df.empty or len(sub_df) < 2:
                    result[orig_sym.upper()] = (None, 0.0)
                    continue
                
                latest = sub_df.iloc[-1]
                prev = sub_df.iloc[-2]
                
                price = latest.get("Close") or latest.get("Adj Close")
                prev_close = prev.get("Close") or prev.get("Adj Close")
                
                if pd.isna(price) or pd.isna(prev_close):
                    result[orig_sym.upper()] = (None, 0.0)
                    continue
                
                change_pct = ((price / prev_close) - 1) * 100
                result[orig_sym.upper()] = (float(price), float(change_pct))
            except Exception as e:
                st.warning(f"價格處理失敗 {orig_sym}: {e}")
                result[orig_sym.upper()] = (None, 0.0)
    
    except Exception as e:
        st.warning(f"批量價格下載失敗: {e}")
        result = {s.upper(): (None, 0.0) for s in symbols}
    
    return result

@st.cache_data(ttl=3600)
def fetch_yahoo_ohlcv(symbol: str, period: str, interval: str):
    try:
        ticker = yf.Ticker(format_symbol_for_yahoo(symbol))
        df = ticker.history(period=period, interval=interval, auto_adjust=False, prepost=False)
        if df.empty or len(df) < 80:
            st.warning(f"資料不足 {symbol}")
            return None, None, None, None
        close = df["Close"].values
        high = df["High"].values
        low = df["Low"].values
        volume = df["Volume"].values
        return close, high, low, volume
    except Exception as e:
        st.warning(f"OHLCV 載入失敗 {symbol}: {str(e)}")
        return None, None, None, None

# ==================== 指標計算函數（原樣保留） ====================
# ... (你的 ema_np, macd_hist_np, rsi_np, atr_np, rolling_mean_np, obv_np, backtest_with_stats 保持不變)

# ==================== 計算單股票 ====================
def compute_stock_metrics(symbol: str, cfg_key: str):
    try:
        close, high, low, volume = fetch_yahoo_ohlcv(symbol, BACKTEST_CONFIG[cfg_key]["period"], "1d")
        if close is None:
            return {"symbol": symbol.upper(), "error": "資料載入失敗"}

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

        steps7 = 7
        prob7, pf7 = backtest_with_stats(close[:-1], score_arr[:-1], steps7)

        return {
            "symbol": symbol.upper(),
            "price": None,
            "change": 0.0,
            "prob7": prob7,
            "pf7": pf7,
            "score": score_arr[-1],
            "macd_yes": macd_hist[-1] > 0,
            "vol_yes": volume[-1] > vol_ma20[-1]*1.1,
            "rsi_yes": rsi[-1] >= 60,
            "atr_yes": atr[-1] > atr_ma20[-1]*1.1,
            "obv_yes": obv[-1] > obv_ma20[-1]*1.05,
        }
    except Exception as e:
        return {"symbol": symbol.upper(), "error": str(e)}

# ==================== 互動 ====================
col1, col2 = st.columns([3, 1])
with col1:
    default_tickers = """LLY GEV MIRM ABBV HWM GE MU HII SCCO SNDK WDC SLV STX JNJ WBD FOXA BK RTX WELL PH GVA AHR ATRO GLW CMI APH PM COR CAH HCA NEM"""
    tickers_input = st.text_area(
        "輸入股票代碼（空格/逗號/換行分隔）",
        value=default_tickers,
        height=180,
        key="tickers_input"
    )

with col2:
    mode = st.selectbox("回測週期", BACKTEST_OPTIONS, index=3, key="mode")  # 預設 2年
    if st.button("開始掃描", type="primary", use_container_width=True):
        raw = tickers_input.strip()
        symbols = re.findall(r'[A-Za-z0-9.\-]+', raw.upper())
        symbols = list(dict.fromkeys(symbols))  # 去重

        if not symbols:
            st.warning("請輸入至少一個股票代碼")
        else:
            with st.spinner(f"使用 yfinance 掃描 {len(symbols)} 個股票..."):
                batch_prices = get_current_prices_batch(symbols)

                results = []
                for sym in symbols:
                    metrics = compute_stock_metrics(sym, mode)
                    if sym.upper() in batch_prices:
                        metrics["price"], metrics["change"] = batch_prices[sym.upper()]
                    results.append(metrics)
                    time.sleep(0.5)  # 加大延遲，避免 rate-limit

                st.session_state["scan_results"] = results

# ==================== 顯示結果（純文字，按 PF7 降序） ====================
if "scan_results" in st.session_state:
    results = st.session_state["scan_results"]
    valid_results = [r for r in results if "error" not in r and isinstance(r.get("pf7"), (int, float))]

    if valid_results:
        valid_results.sort(key=lambda x: x["pf7"], reverse=True)

        lines = []
        for row in valid_results:
            price_str = f"{row['price']:.2f}" if row['price'] is not None else "N/A"
            change_str = f"{row['change']:+.2f}%" if row['change'] is not None else "N/A"
            score_str = f"{int(row['score'])}/5"
            macd_str = "是" if row["macd_yes"] else "否"
            vol_str  = "是" if row["vol_yes"] else "否"
            rsi_str  = "是" if row["rsi_yes"] else "否"
            atr_str  = "是" if row["atr_yes"] else "否"
            obv_str  = "是" if row["obv_yes"] else "否"

            line = (
                f"{row['symbol']} - "
                f"價格: ${price_str} ({change_str}) - "
                f"得分: {score_str} - "
                f"MACD>0: {macd_str} | 放量: {vol_str} | RSI≥60: {rsi_str} | ATR放大: {atr_str} | OBV上升: {obv_str} - "
                f"7日概率: {row['prob7']*100:.1f}% | PF7: {row['pf7']:.2f}"
            )
            lines.append(line)

        st.subheader("掃描結果（按 PF7 降序）")
        st.code("\n".join(lines), language="text")

        st.info("資料來自 yfinance (Yahoo Finance 非官方介面)，即時性取決於市場開盤狀態。建議先升級 yfinance 到 1.0+ 版。")
    else:
        st.warning("無有效結果（可能載入失敗或資料不足）。請檢查代碼、網路，或按清除快取後重試。")

st.caption("Powered by yfinance 1.0+ | 僅供研究參考，不構成投資建議 | 目前時間: 2026年1月")
