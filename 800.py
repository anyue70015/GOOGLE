import streamlit as st
import pandas as pd
import ccxt
import time
import pandas_ta as ta
from concurrent.futures import ThreadPoolExecutor

st.set_page_config(page_title="指挥部-优化版", layout="wide")

# 币种列表（已去TRX）
SYMBOLS = ["BTC", "ETH", "SOL", "AAVE", "DOGE", "TAO", "SUI", "RENDER", "UNI", "HYPE", "XRP", "ADA", "BCH", "LINK", "LTC", "ZEC", "ASTER"]
EXCHANGES = {'OKX': 'okx', 'Bitget': 'bitget', 'Gate': 'gateio', 'Huobi': 'htx', 'Binance': 'binance'}

# 大币列表（用于ATR分层）
LARGE_COINS = ["BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "BCH", "LINK", "LTC"]

def get_tactical_logic(df, curr_p, flow, rsi, symbol, change_1m):
    atr_series = ta.atr(df['h'], df['l'], df['c'], length=14)
    atr_val = atr_series.iloc[-1] if atr_series is not None else 0
    atr_pct = (atr_val / curr_p) * 100 if curr_p != 0 else 0
    
    obv_series = ta.obv(df['c'], df['v'])
    obv_trend = "UP" if obv_series.iloc[-1] > obv_series.iloc[-2] else "DOWN"
    
    macd = ta.macd(df['c'])
    macd_status = "金叉" if macd['MACDh_12_26_9'].iloc[-1] > 0 else "死叉"
    
    diag = "🔎 观望"
    
    # ATR阈值分层
    atr_threshold = 3.0 if symbol in LARGE_COINS else 5.0
    
    # 1. 抄底（RSI放宽到<30）
    if rsi < 30 and obv_trend == "UP":
        diag = "🛒 底部吸筹"
    
    # 2. 破位（净流入阈值降到-20，ATR分层）
    elif atr_pct > atr_threshold and macd_status == "死叉" and flow < -20:
        diag = "💀 确认破位"
    
    # 3. 诱多（RSI放宽到>65）
    elif obv_trend == "DOWN" and rsi > 65:
        diag = "⚠️ 诱多虚涨"
    
    # 4. 新增短线脉冲（轻微偏强/偏弱）
    elif change_1m > 1.2 and flow > 20 and rsi > 55 and obv_trend == "UP":
        diag = "🚀 轻微偏强"
    elif change_1m < -1.2 and flow < -20:
        diag = "🩸 短线急跌"
        
    return diag, round(atr_pct, 2), "💎流入" if obv_trend == "UP" else "💀流出"

def fetch_commander_data(symbol):
    pair = f"{symbol}/USDT"
    res = {"币种": symbol}
    
    # 所有币种默认使用币安镜像，唯独 HYPE 使用原来的 OKX
    if symbol == "HYPE":
        main_ex_id = 'okx'
        main_ex = ccxt.okx({'enableRateLimit': True, 'timeout': 8000})
        print(f"{symbol} 使用原 OKX")
    else:
        mirror_base = "https://www.bmwweb.academy"
        main_ex_id = 'binance'
        main_ex = ccxt.binance({
            'enableRateLimit': True,
            'timeout': 12000,
            'rateLimit': 400,
            'urls': {
                'api': {
                    'public': mirror_base + '/api',
                    'private': mirror_base + '/api',
                    'v3': mirror_base + '/api/v3',
                    'sapi': mirror_base + '/sapi/v1',
                },
                'www': mirror_base,
                'api': mirror_base + '/api',
            },
            'options': {
                'defaultType': 'spot',
                'adjustForTimeDifference': True,
            }
        })
        print(f"{symbol} 使用镜像: {mirror_base}")
    
    try:
        tk = main_ex.fetch_ticker(pair)
        curr_p = tk['last']
        res["最新价"] = f"{curr_p:,.4f}" if curr_p < 10 else f"{curr_p:,.2f}"
        res["24h"] = tk.get('percentage', 0)

        # 短期涨幅（用limit=2更稳）
        timeframes = {"1m": '1m', "5m": '5m', "15m": '15m', "1h": '1h'}
        for label, tf in timeframes.items():
            k = main_ex.fetch_ohlcv(pair, tf, limit=2)
            if len(k) >= 2:
                base_p = k[-2][4]
                res[label] = ((curr_p - base_p) / base_p) * 100
            else:
                res[label] = 0.0

        # 净流入 + 交易量来源（新增）
        total_flow = 0.0
        volume_sources = []
        for eid in EXCHANGES.values():
            try:
                ex = getattr(ccxt, eid)({'enableRateLimit': True, 'timeout': 5000})
                tk_ex = ex.fetch_ticker(pair)
                qvol = tk_ex.get('quoteVolume', 0)  # 24h USDT volume
                if qvol > 100000:  # 最小阈值，避免噪音
                    volume_sources.append(eid.capitalize())
                trades = ex.fetch_trades(pair, limit=50)
                total_flow += sum((t['price'] * t['amount']) if t['side'] == 'buy' else -(t['price'] * t['amount']) for t in trades)
            except:
                continue
        res["净流入(万)"] = round(total_flow / 10000, 1)
        res["交易量来源"] = ", ".join(volume_sources) if volume_sources else "-"

        # 指标
        ohlcv_raw = main_ex.fetch_ohlcv(pair, '1h', limit=40)
        df = pd.DataFrame(ohlcv_raw, columns=['t','o','h','l','c','v'])
        rsi_val = ta.rsi(df['c'], length=14).iloc[-1] if len(df) >= 14 else 50
        res["RSI"] = round(rsi_val, 1)
        
        diag, atr_p, obv_s = get_tactical_logic(df, curr_p, res["净流入(万)"], rsi_val, symbol, res.get("1m", 0))
        res["战术诊断"] = diag
        res["ATR%"] = atr_p
        res["OBV"] = obv_s
        
    except Exception as e:
        res["最新价"] = "Err"
        res["战术诊断"] = "异常"
        res["交易量来源"] = str(e)[:20]
        # 防止后续样式崩溃，给默认值
        res["RSI"] = 50.0
        res["ATR%"] = 0.0
        res["OBV"] = "未知"
        res["1m"] = 0.0  # 防止无 "1m" 导致排序崩溃
    
    return res

# 界面
st.title("🛰️ 全球资产指挥部 (优化诊断 + 交易量来源)")
placeholder = st.empty()

while True:
    with ThreadPoolExecutor(max_workers=6) as executor:  # 降到6，减少并发压力
        results = list(executor.map(fetch_commander_data, SYMBOLS))
    
    df = pd.DataFrame([r for r in results if r])
    
    # 安全排序：先检查列是否存在
    if not df.empty:
        if "1m" in df.columns:
            df = df.sort_values(by="1m", ascending=False)
        else:
            st.warning("缺少 '1m' 列，跳过排序")
    
    display_df = df.copy()
    order = ["币种", "最新价", "战术诊断", "1m", "5m", "15m", "1h", "24h", "净流入(万)", "RSI", "ATR%", "OBV", "交易量来源"]
    
    # 只处理存在的列
    available_order = [col for col in order if col in display_df.columns]
    
    for col in ["1m", "5m", "15m", "1h", "24h"]:
        if col in display_df.columns:
            display_df[col] = display_df[col].apply(lambda x: f"{x:+.2f}%" if isinstance(x, (int, float)) else x)

    with placeholder.container():
        st.write(f"📊 监控中 | 频率: 90s | 时间: {time.strftime('%H:%M:%S')} | 诊断优化：RSI放宽/ATR分层/短脉冲/净流入-20")
        
        def style_logic(val):
            # 强制转字符串，防止 NaN/None/数字导致崩溃
            val_str = str(val) if val is not None else ""
            
            if "底部吸筹" in val_str:
                return 'background-color: #006400; color: white'
            if "确认破位" in val_str:
                return 'background-color: #8B0000; color: white'
            if "轻微偏强" in val_str or "脉冲" in val_str:
                return 'background-color: #228B22; color: white'
            if "短线急跌" in val_str:
                return 'background-color: #B22222; color: white'
            if val_str == "💎流入":
                return 'color: #00ff00'
            return ''
        
        # 安全渲染
        if "战术诊断" not in display_df.columns and "OBV" not in display_df.columns:
            st.warning("缺少样式列，显示原始表格")
            st.dataframe(display_df[available_order], use_container_width=True, height=700)
        else:
            try:
                subset_cols = [col for col in ["战术诊断", "OBV"] if col in display_df.columns]
                if subset_cols:
                    styled_df = display_df[available_order].style.applymap(style_logic, subset=subset_cols)
                else:
                    styled_df = display_df[available_order].style
                
                st.dataframe(
                    styled_df,
                    use_container_width=True,
                    height=700
                )
            except Exception as e:
                st.error(f"样式渲染异常（数据类型问题）：{str(e)}")
                st.dataframe(display_df[available_order], use_container_width=True, height=700)

    time.sleep(90)  # 建议90s，减少负载
