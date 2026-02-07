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

# 状态初始化：记录每个币种+周期的最后推送的K线时间
if 'last_alerts' not in st.session_state:
    st.session_state.last_alerts = {}  # key: (base, tf), value: 'YYYY-MM-DD HH:MM'

# 侧边栏
st.sidebar.header("🛡️ 设置")
sensitivity = st.sidebar.slider("UT Bot 敏感度", 0.1, 5.0, 1.0, 0.1)
atr_period = st.sidebar.slider("ATR 周期", 1, 30, 10)

CRYPTO_LIST = ["BTC", "ETH", "SOL", "SUI", "RENDER", "DOGE", "XRP", "HYPE", "AAVE", "TAO", "XAG", "XAU"]
selected_cryptos = st.sidebar.multiselect("币种", CRYPTO_LIST, default=CRYPTO_LIST)

st.sidebar.header("🚨 WxPusher 微信报警（30m & 1h）")
app_token = st.sidebar.text_input("WxPusher appToken", type="password", value="")
user_uid = st.sidebar.text_input("WxPusher UID", type="password", value="")
alert_min = st.sidebar.number_input("新信号阈值（分钟）", 1, 60, 10)

# 调试工具：手动测试 + 强制测试
if st.sidebar.button("立即发送测试微信"):
    if app_token and user_uid:
        test_title = "【手动测试】UT Bot 看板"
        test_body = f"时间: {datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')}\n通道正常！"
        send_wx_pusher(app_token, user_uid, test_title, test_body)
        st.sidebar.success("测试已发送，请查微信")
    else:
        st.sidebar.error("填写 token/UID")

force_test_alert = st.sidebar.checkbox("强制每刷新发测试报警（30m/1h每个币）", value=False)

intervals = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]

# 计算指标（原样）
def calculate_indicators(df):
    if df.empty or len(df) < 50:
        return pd.DataFrame()
    df.columns = [str(c).capitalize() for c in df.columns]
    
    df['atr'] = ta.atr(df['High'], df['Low'], df['Close'], length=atr_period)
    df = df.dropna(subset=['atr']).copy()
    n_loss = sensitivity * df['atr']
    src = df['Close']
    trail_stop = np.zeros(len(df))
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

# 获取信号（原样）
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
    
    buys = df[df['buy']]
    sells = df[df['sell']]
    lb = buys.index[-1] if not buys.empty else None
    ls = sells.index[-1] if not sells.empty else None
    
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
        delta_b = now_u - lb_u
        if delta_b.total_seconds() >= 0:
            dur_b = int(delta_b.total_seconds() / 60)
    
    dur_s = 999
    if ls_u:
        delta_s = now_u - ls_u
        if delta_s.total_seconds() >= 0:
            dur_s = int(delta_s.total_seconds() / 60)
    
    sig = "维持"
    alert_d = None
    if lb_u and (not ls_u or lb_u > ls_u):
        sig = f"🚀 BUY({dur_b}m)" if dur_b <= 30 else "多 🟢"
        if dur_b <= alert_min:
            alert_d = dur_b
    elif ls_u and (not lb_u or ls_u > lb_u):
        sig = f"📉 SELL({dur_s}m)" if dur_s <= 30 else "空 🔴"
        if dur_s <= alert_min:
            alert_d = dur_s
    
    return sig, curr_p, alert_d, rsi_val, f"{ema_cross} | MACD:{macd_cross}", trend

# WxPusher 发送（原样）
def send_wx_pusher(app_token, uid, title, body):
    if not app_token or not uid:
        return
    try:
        payload = {
            "appToken": app_token,
            "content": f"{title}\n{body}",
            "summary": title[:100],
            "uids": [uid]
        }
        response = requests.post("https://wxpusher.zjiecode.com/api/send/message", json=payload, timeout=5)
        if response.status_code == 200:
            res_json = response.json()
            if res_json.get("code") == 1000:
                st.toast("推送成功", icon="✅")
            else:
                st.toast(f"推送失败: {res_json.get('msg')}", icon="⚠️")
    except Exception as e:
        st.toast(f"WxPusher 异常: {str(e)}", icon="❌")

# 多空比（原样）
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

# 渲染表格（原样）
def render_table(df):
    def cell_style_trend(value):
        s = str(value)
        if '多头' in s or '🟢' in s: return 'color:#0f0; font-weight:bold; background:#00440033; text-align:center;'
        if '空头' in s or '🔴' in s: return 'color:#f44; font-weight:bold; background:#44000033; text-align:center;'
        return 'text-align:center;'

    def cell_style_other(value):
        s = str(value)
        if 'BUY' in s or '金叉' in s or '🟢' in s: return 'color:#0f0; font-weight:bold;'
        if 'SELL' in s or '死叉' in s or '🔴' in s: return 'color:#f44; font-weight:bold;'
        if 'RSI' in s:
            try:
                v = float(s.split(':')[1])
                if v > 70: return 'color:#ff0;'
                if v < 30: return 'color:#0ff;'
            except:
                pass
        return ''

    html = '<table style="width:100%; border-collapse:collapse; font-family:monospace; font-size:0.9em;">'
    html += '<tr style="background:#222; color:#fff;">' + ''.join(f'<th style="padding:6px; border:1px solid #444; font-size:0.95em;">{c}</th>' for c in df.columns) + '</tr>'
    
    for _, row in df.iterrows():
        html += '<tr>'
        for c in df.columns:
            val = row[c]
            if c in intervals:
                parts = str(val).split(' | ')
                sig_part = parts[0] if len(parts) > 0 else ""
                rsi_part = parts[1] if len(parts) > 1 else ""
                ema_macd_part = ' | '.join(parts[2:]) if len(parts) > 2 else ""
                
                content = f'''
                <div style="border:1px solid #555; padding:2px; min-height:36px; display:flex; flex-direction:column; justify-content:space-between; font-size:0.85em; line-height:1.2;">
                    <div style="border-bottom:1px solid #444; padding-bottom:1px; {cell_style_other(sig_part)}">{sig_part or "—"}</div>
                    <div style="border-bottom:1px solid #444; padding:1px 0; {cell_style_other(rsi_part)}">{rsi_part or "—"}</div>
                    <div style="padding-top:1px; {cell_style_other(ema_macd_part)}">{ema_macd_part or "—"}</div>
                </div>
                '''
                html += f'<td style="padding:3px; border:1px solid #444; vertical-align:top;">{content}</td>'
            elif c == "多空比(5m)":
                style = cell_style_trend(val)
                html += f'<td style="padding:6px; border:1px solid #444; {style}">{val}</td>'
            elif c == "趋势":
                style = cell_style_trend(val)
                html += f'<td style="padding:6px; border:1px solid #444; {style}">{val}</td>'
            else:
                html += f'<td style="padding:6px; border:1px solid #444;">{val}</td>'
        html += '</tr>'
    html += '</table>'
    st.markdown(html, unsafe_allow_html=True)

# 主界面
st.markdown(
    "<h4 style='text-align:center; margin:0.2em 0 0.1em 0; padding:0; font-size:1.4em; color:#ddd;'>"
    "UT Bot + RSI/EMA/MACD 看板 (5min刷新)"
    "</h4>",
    unsafe_allow_html=True
)

if st.button("刷新", key="refresh_btn"):
    st.rerun()

components.html("""
<div style="font-size:1.1em; color:#888; margin:0.1em 0; text-align:center; line-height:1.1;">
  下次: <span id="cd" style="font-weight:bold;">300</span> s
</div>
<script>
let s=300; const t=document.getElementById('cd');
setInterval(()=>{s--; t.textContent=s; if(s<=0)s=300;},1000);
</script>
""", height=30)

with st.spinner("加载中..."):
    ex = ccxt.okx({'enableRateLimit': True, 'timeout': 10000})
    rows = []
    contracts = {"TAO", "XAG", "XAU"}
    
    for base in selected_cryptos:
        sym = f"{base}/USDT:USDT" if base in contracts else f"{base}/USDT"
        row = {"资产": base, "多空比(5m)": get_ls(base)}
        price = None
        
        for tf in intervals:
            try:
                bars = ex.fetch_ohlcv(sym, timeframe=tf, limit=200)
                if not bars:
                    row[tf] = "无"
                    continue
                df_ohlcv = pd.DataFrame(bars, columns=['timestamp','open','high','low','close','volume'])
                df_ohlcv['timestamp'] = pd.to_datetime(df_ohlcv['timestamp'], unit='ms')
                df_ohlcv.set_index('timestamp', inplace=True)
                processed_df = calculate_indicators(df_ohlcv)
                sig, p, dur, rsi, ema_macd, trend = get_sig(processed_df, tf)
                row[tf] = f"{sig} | RSI:{rsi} | {ema_macd}"
                if p is not None and p > 0:
                    price = p
                
                # 报警 - 30m & 1h + 调试输出
                if tf in ["30m", "1h"] and dur is not None and app_token and user_uid:
                    key = (base, tf)
                    last_kline_time = st.session_state.last_alerts.get(key, None)
                    current_kline_time = processed_df.index[-1].strftime('%Y-%m-%d %H:%M') if not processed_df.empty else "无"
                    
                    # 调试输出
                    debug_str = f"【{base} {tf}】 dur={dur} | last_kline={last_kline_time or 'None'} | curr_kline={current_kline_time} | should={dur <= alert_min + 5 and (last_kline_time is None or last_kline_time != current_kline_time)}"
                    st.write(debug_str)
                    
                    # 强制测试覆盖
                    should_alert = force_test_alert
                    
                    if not should_alert:
                        should_alert = (
                            dur <= alert_min + 5 and
                            (last_kline_time is None or last_kline_time != current_kline_time)
                        )
                    
                    if should_alert:
                        period_label = "30m" if tf == "30m" else "1H"
                        if "BUY" in sig:
                            title = f"[{base} {period_label}] BUY 信号"
                        elif "SELL" in sig:
                            title = f"[{base} {period_label}] SELL 信号"
                        else:
                            title = f"[{base} {period_label}] 信号变动"
                            
                        body = (
                            f"{sig}\n"
                            f"价: {p:.4f if p is not None else 'N/A'}\n"
                            f"RSI: {rsi}\n"
                            f"{ema_macd}\n"
                            f"趋势: {trend}\n"
                            f"距今: {dur}min\n"
                            f"多空: {row['多空比(5m)']}"
                        )
                        send_wx_pusher(app_token, user_uid, title, body)
                        
                        st.session_state.last_alerts[key] = current_kline_time
                        
            except Exception as e:
                row[tf] = f"err: {str(e)[:30]}"
        
        # 现价安全处理（防格式错误）
        row["现价"] = f"{float(price):.4f}" if price is not None and isinstance(price, (int, float)) else "N/A"
        row["趋势"] = trend
        rows.append(row)
    
    result_df = pd.DataFrame(rows)
    render_table(result_df)

st.caption(f"更新: {datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')}")
st.info("· 30m & 1h BUY/SELL 均推送 · 宽松5min防漏 · 防重复 · 5min刷新 · MACD已显示 · 检查网页 dur 值", icon="ℹ️")
