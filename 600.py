import streamlit as st
import pandas as pd
import numpy as np
import pandas_ta as ta
import ccxt
import requests
from datetime import datetime
import pytz
from streamlit_autorefresh import st_autorefresh
import streamlit.components.v1 as components

# 配置
st.set_page_config(page_title="UT Bot 看板", layout="wide")
BEIJING_TZ = pytz.timezone('Asia/Shanghai')
st_autorefresh(interval=300 * 1000, key="refresh_5min")  # 5分钟刷新

# 状态初始化
if 'last_alerts' not in st.session_state:
    st.session_state.last_alerts = {}  # key: (base, tf), value: str 'YYYY-MM-DD HH:MM'

# 侧边栏 - 设置
st.sidebar.header("🛡️ 设置")
sensitivity = st.sidebar.slider("UT Bot 敏感度", 0.1, 5.0, 1.8, 0.1)   # 默认调高，更易触发信号
atr_period = st.sidebar.slider("ATR 周期", 1, 30, 7)                   # 默认调小，更敏感

CRYPTO_LIST = ["BTC", "ETH", "SOL", "SUI", "RENDER", "DOGE", "XRP", "HYPE", "AAVE", "TAO", "XAG", "XAU"]
selected_cryptos = st.sidebar.multiselect("币种", CRYPTO_LIST, default=CRYPTO_LIST[:5])  # 默认少选点，减少请求

st.sidebar.header("🚨 WxPusher 微信报警（30m & 1h）")
app_token = st.sidebar.text_input("WxPusher appToken", type="password", value="")
user_uid = st.sidebar.text_input("WxPusher UID", type="password", value="")
alert_min = st.sidebar.number_input("新信号阈值（分钟）", 1, 60, 10)

# 调试开关
force_test = st.sidebar.checkbox("强制每刷新发送测试报警（30m/1h 每个币）", value=False)
if st.sidebar.button("立即发送一次测试微信"):
    if app_token and user_uid:
        test_title = "【手动测试】仪表板报警"
        test_body = f"时间: {datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')}\n这是一条手动测试消息"
        send_wx_pusher(app_token, user_uid, test_title, test_body)
        st.sidebar.success("测试消息已尝试发送，请检查微信")
    else:
        st.sidebar.error("请填写 appToken 和 UID")

intervals = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]

# 计算指标（不变）
def calculate_indicators(df):
    if df.empty or len(df) < 50:
        return pd.DataFrame()
    df.columns = [str(c).capitalize() for c in df.columns]
    
    df['atr'] = ta.atr(df['High'], df['Low'], df['Close'], length=atr_period)
    df = df.dropna(subset=['atr']).copy()
    n_loss = sensitivity * df['atr']
    src = df['Close']
    trail_stop = np.zeros(len(df))
    trail_stop[0] = src.iloc[0]  # 初始值改进
    for i in range(1, len(df)):
        p = trail_stop[i-1]
        if src.iloc[i] > p and src.iloc[i-1] > p:
            trail_stop[i] = max(p, src.iloc[i] - n_loss.iloc[i])
        elif src.iloc[i] < p and src.iloc[i-1] < p:
            trail_stop[i] = min(p, src.iloc[i] + n_loss.iloc[i])
        else:
            trail_stop[i] = src.iloc[i] - n_loss.iloc[i] if src.iloc[i] > p else src.iloc[i] + n_loss.iloc[i]
    df['trail_stop'] = trail_stop
    df['buy'] = (df['Close'] > df['trail_stop']) & (df['Close'].shift(1) <= df['trail_stop'].shift(1))
    df['sell'] = (df['Close'] < df['trail_stop']) & (df['Close'].shift(1) >= df['trail_stop'].shift(1))
    
    df['rsi'] = ta.rsi(df['Close'], length=14)
    df['ema5'] = ta.ema(df['Close'], length=5)
    df['ema13'] = ta.ema(df['Close'], length=13)
    df['ema20'] = ta.ema(df['Close'], length=20)
    df['ema50'] = ta.ema(df['Close'], length=50)
    
    df['ema_cross'] = np.where(
        (df['ema5'] > df['ema13']) & (df['ema5'].shift(1) <= df['ema13'].shift(1)), "金叉 🟢",
        np.where(
            (df['ema5'] < df['ema13']) & (df['ema5'].shift(1) >= df['ema13'].shift(1)), "死叉 🔴",
            "无交叉"
        )
    )
    
    macd = ta.macd(df['Close'], fast=12, slow=26, signal=9)
    df['macd_dif'] = macd['MACD_12_26_9']
    df['macd_dea'] = macd['MACDs_12_26_9']
    df['macd_cross'] = np.where(
        (df['macd_dif'] > df['macd_dea']) & (df['macd_dif'].shift(1) <= df['macd_dea'].shift(1)), "MACD金叉 🟢",
        np.where(
            (df['macd_dif'] < df['macd_dea']) & (df['macd_dif'].shift(1) >= df['macd_dea'].shift(1)), "MACD死叉 🔴",
            "无"
        )
    )
    
    return df

# 获取信号（小改：dur 计算更健壮）
def get_sig(df, tf):
    if df.empty:
        return "N/A", None, None, "N/A", "N/A", "N/A", "N/A"
    
    curr_p = float(df.iloc[-1]['Close'])
    rsi_val = f"{df.iloc[-1]['rsi']:.1f}" if pd.notna(df.iloc[-1]['rsi']) else "N/A"
    
    trend = "N/A"
    if pd.notna(df.iloc[-1]['ema20']) and pd.notna(df.iloc[-1]['ema50']):
        if curr_p > df.iloc[-1]['ema20'] > df.iloc[-1]['ema50']:
            trend = "多头 🟢"
        elif curr_p < df.iloc[-1]['ema20'] < df.iloc[-1]['ema50']:
            trend = "空头 🔴"
        else:
            trend = "震荡 ⚪"
    
    ema_cross = df.iloc[-1]['ema_cross'] if pd.notna(df.iloc[-1]['ema_cross']) else "N/A"
    macd_cross = df.iloc[-1]['macd_cross'] if pd.notna(df.iloc[-1]['macd_cross']) else "无"
    
    buys = df[df['buy']].index
    sells = df[df['sell']].index
    
    lb = buys[-1] if len(buys) > 0 else None
    ls = sells[-1] if len(sells) > 0 else None
    
    now_u = datetime.now(pytz.utc)
    
    def force_utc(ts):
        if ts is None:
            return None
        if isinstance(ts, pd.Timestamp):
            ts = ts.to_pydatetime()
        if ts.tzinfo is None:
            return pytz.utc.localize(ts)
        return ts.astimezone(pytz.utc)
    
    lb_u = force_utc(lb)
    ls_u = force_utc(ls)
    
    dur_b = 999
    if lb_u:
        delta = now_u - lb_u
        if delta.total_seconds() >= 0:
            dur_b = int(delta.total_seconds() / 60)
    
    dur_s = 999
    if ls_u:
        delta = now_u - ls_u
        if delta.total_seconds() >= 0:
            dur_s = int(delta.total_seconds() / 60)
    
    dur = min(dur_b, dur_s) if min(dur_b, dur_s) < 999 else None
    sig = "维持"
    alert_d = dur if dur is not None and dur < 999 else None
    
    if dur_b < dur_s:
        sig = f"🚀 BUY({dur_b}m)" if dur_b <= 60 else "多 🟢"
    elif dur_s < dur_b:
        sig = f"📉 SELL({dur_s}m)" if dur_s <= 60 else "空 🔴"
    
    return sig, curr_p, alert_d, rsi_val, f"{ema_cross} | MACD:{macd_cross}", trend

# WxPusher 发送（加返回成功标志）
def send_wx_pusher(app_token, uid, title, body):
    if not app_token or not uid:
        return False
    try:
        payload = {
            "appToken": app_token,
            "content": f"{title}\n{body}",
            "summary": title[:100],
            "contentType": 1,
            "uids": [uid]
        }
        response = requests.post("https://wxpusher.zjiecode.com/api/send/message", json=payload, timeout=8)
        if response.status_code == 200:
            res_json = response.json()
            if res_json.get("code") == 1000:
                st.toast(f"推送成功: {title}", icon="✅")
                return True
            else:
                st.toast(f"推送失败: {res_json.get('msg')}", icon="⚠️")
        else:
            st.toast(f"网络错误: {response.status_code}", icon="❌")
        return False
    except Exception as e:
        st.toast(f"WxPusher 异常: {str(e)}", icon="❌")
        return False

# 多空比（不变）
def get_ls(base):
    try:
        url = f"https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol={base.upper()}USDT&period=5m&limit=1"
        r = requests.get(url, timeout=5).json()
        if r and isinstance(r, list) and 'longShortRatio' in r[0]:
            ratio = float(r[0]['longShortRatio'])
            emoji = "🟢" if ratio > 1.2 else "🔴" if ratio < 0.8 else "⚪"
            return f"{ratio:.2f} {emoji}"
    except:
        pass
    return "N/A"

# 渲染表格（不变，略过以节省空间，如果你需要我可以再贴）

# 主界面（简化版，重点在报警调试）
st.markdown("<h4 style='text-align:center;'>UT Bot 看板 (调试版 - 重点排查报警)</h4>", unsafe_allow_html=True)

with st.spinner("加载中..."):
    ex = ccxt.okx({'enableRateLimit': True, 'timeout': 10000})
    rows = []
    
    for base in selected_cryptos:
        sym = f"{base}/USDT:USDT" if base in {"TAO", "XAG", "XAU"} else f"{base}/USDT"
        row = {"资产": base, "多空比(5m)": get_ls(base)}
        price = None
        
        for tf in intervals:
            try:
                bars = ex.fetch_ohlcv(sym, timeframe=tf, limit=200)
                if not bars:
                    row[tf] = "无数据"
                    continue
                df_ohlcv = pd.DataFrame(bars, columns=['timestamp','open','high','low','close','volume'])
                df_ohlcv['timestamp'] = pd.to_datetime(df_ohlcv['timestamp'], unit='ms')
                df_ohlcv.set_index('timestamp', inplace=True)
                processed_df = calculate_indicators(df_ohlcv)
                sig, p, dur, rsi, ema_macd, trend = get_sig(processed_df, tf)
                row[tf] = f"{sig} | RSI:{rsi} | {ema_macd}"
                if p is not None and p > 0:
                    price = p
                
                # ──────────────── 报警调试核心 ────────────────
                if tf in ["30m", "1h"] and app_token and user_uid:
                    key = (base, tf)
                    last_kline = st.session_state.last_alerts.get(key, None)
                    current_kline = processed_df.index[-1].strftime('%Y-%m-%d %H:%M') if not processed_df.empty else "无"
                    
                    # 调试输出
                    st.write(f"【{base} {tf}】 dur={dur} | last={last_kline} | curr={current_kline} | alert_min={alert_min}")
                    
                    # 触发条件（放宽版）
                    should_alert = False
                    if force_test:
                        should_alert = True
                    elif dur is not None and dur <= alert_min + 15:  # 放宽到 +15min
                        should_alert = True
                    
                    if should_alert:
                        period_label = "30m" if tf == "30m" else "1h"
                        title = f"[{base} {period_label}] {sig.split('(')[0]} 信号（调试）"
                        body = f"""
{sig}
价格: {p:.4f if p else 'N/A'}
RSI: {rsi}
{ema_macd}
趋势: {trend}
距今: {dur if dur else '未知'} min
多空: {row['多空比(5m)']}
K线: {current_kline}
                        """.strip()
                        
                        st.write(f"→ 触发发送: {title}")
                        success = send_wx_pusher(app_token, user_uid, title, body)
                        if success:
                            st.session_state.last_alerts[key] = current_kline
                        
            except Exception as e:
                row[tf] = f"err: {str(e)[:30]}"
                st.write(f"【错误】{base} {tf}: {str(e)}")
        
        row["现价"] = f"{price:.4f}" if price else "N/A"
        row["趋势"] = trend
        rows.append(row)
    
    # render_table(result_df)  ← 你原来的表格渲染函数放这里

st.caption(f"更新: {datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')}")
st.info("调试提示：看网页上的 dur 值。如果 dur 总是 999/None → 调高 sensitivity 或降低 atr_period", icon="ℹ️")
