import streamlit as st
import pandas as pd
import numpy as np
import pandas_ta as ta
import ccxt
import requests
from datetime import datetime, timedelta
import pytz
from streamlit_autorefresh import st_autorefresh
import streamlit.components.v1 as components

# ============================================
# 配置
# ============================================
st.set_page_config(page_title="UT Bot 专业看板", layout="wide", page_icon="📈")
BEIJING_TZ = pytz.timezone('Asia/Shanghai')

# 5分钟自动刷新
st_autorefresh(interval=300 * 1000, key="refresh_5min")

# ============================================
# 初始化会话状态
# ============================================
if 'signal_history' not in st.session_state:
    st.session_state.signal_history = {}

if 'last_refresh' not in st.session_state:
    st.session_state.last_refresh = datetime.now(BEIJING_TZ)

# ============================================
# 侧边栏配置
# ============================================
st.sidebar.header("⚙️ 交易参数设置")
sensitivity = st.sidebar.slider("超级趋势敏感度 (ATR倍数)", 0.5, 3.0, 1.0, 0.1, 
                               help="值越小信号越敏感，值越大信号越稳定")
atr_period = st.sidebar.slider("ATR计算周期", 5, 30, 10, 1)
atr_multiplier = st.sidebar.slider("止损ATR倍数", 1.0, 3.0, 2.0, 0.1,
                                  help="用于计算动态止损位，值越大止损越宽")

st.sidebar.header("📊 监控资产")
CRYPTO_LIST = ["BTC", "ETH", "SOL", "SUI", "RENDER", "DOGE", "XRP", 
               "HYPE", "AAVE", "TAO", "XAG", "XAU", "ADA", "AVAX", "DOT"]
selected_cryptos = st.sidebar.multiselect(
    "选择要监控的资产", 
    CRYPTO_LIST, 
    default=["BTC", "ETH", "SOL", "XAG", "XAU"]
)

st.sidebar.header("📱 微信推送设置")
app_token = st.sidebar.text_input(
    "WxPusher AppToken", 
    type="password",
    value="AT_3H9akFZPvOE98cPrDydWmKM4ndgT3bVH" if 'app_token' not in st.session_state else st.session_state.app_token
)
user_uid = st.sidebar.text_input(
    "WxPusher UID", 
    type="password",
    value="UID_wfbEjBobfoHNLmprN3Pi5nwWb4oM" if 'user_uid' not in st.session_state else st.session_state.user_uid
)

st.session_state.app_token = app_token
st.session_state.user_uid = user_uid

alert_min = st.sidebar.number_input("新信号推送阈值(分钟)", 5, 60, 10,
                                   help="只推送此时间范围内新出现的信号")

st.sidebar.header("⚡ 其他设置")
show_stop_loss = st.sidebar.checkbox("显示动态止损位", value=True, help="在表格中显示ATR动态止损位")
show_resonance = st.sidebar.checkbox("显示多周期共振", value=True, help="显示多个时间周期的信号一致性")

# ============================================
# 技术指标计算函数
# ============================================
def calculate_indicators(df):
    """计算所有技术指标"""
    if df.empty or len(df) < 50:
        return pd.DataFrame()
    
    # 标准化列名
    df.columns = [str(c).capitalize() for c in df.columns]
    
    # 核心指标：超级趋势 (基于ATR)
    df['atr'] = ta.atr(df['High'], df['Low'], df['Close'], length=atr_period)
    df = df.dropna(subset=['atr']).copy()
    
    # 计算超级趋势止损线
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
    df['buy_signal'] = (df['Close'] > df['trail_stop']) & (df['Close'].shift(1) <= df['trail_stop'].shift(1))
    df['sell_signal'] = (df['Close'] < df['trail_stop']) & (df['Close'].shift(1) >= df['trail_stop'].shift(1))
    
    # 动态止损位计算
    df['atr_stop_long'] = df['Close'] - (atr_multiplier * df['atr'])
    df['atr_stop_short'] = df['Close'] + (atr_multiplier * df['atr'])
    
    # RSI指标
    df['rsi'] = ta.rsi(df['Close'], length=14)
    
    # EMA均线系统
    df['ema5'] = ta.ema(df['Close'], length=5)
    df['ema13'] = ta.ema(df['Close'], length=13)
    df['ema20'] = ta.ema(df['Close'], length=20)
    df['ema50'] = ta.ema(df['Close'], length=50)
    
    # EMA交叉信号
    df['ema_cross'] = np.where(
        (df['ema5'] > df['ema13']) & (df['ema5'].shift(1) <= df['ema13'].shift(1)), 
        "金叉 🟢",
        np.where(
            (df['ema5'] < df['ema13']) & (df['ema5'].shift(1) >= df['ema13'].shift(1)), 
            "死叉 🔴",
            "无"
        )
    )
    
    # MACD指标
    macd = ta.macd(df['Close'], fast=12, slow=26, signal=9)
    df['macd_dif'] = macd['MACD_12_26_9']
    df['macd_dea'] = macd['MACDs_12_26_9']
    df['macd_hist'] = macd['MACDh_12_26_9']
    
    df['macd_cross'] = np.where(
        (df['macd_dif'] > df['macd_dea']) & (df['macd_dif'].shift(1) <= df['macd_dea'].shift(1)), 
        "MACD金叉 🟢",
        np.where(
            (df['macd_dif'] < df['macd_dea']) & (df['macd_dif'].shift(1) >= df['macd_dea'].shift(1)), 
            "MACD死叉 🔴",
            "无"
        )
    )
    
    # 成交量指标
    df['volume_ma5'] = df['Volume'].rolling(5).mean()
    df['volume_ratio'] = df['Volume'] / df['volume_ma5']
    
    return df

# ============================================
# 信号分析函数（已修复时间判断逻辑）
# ============================================
def get_signal_analysis(df, timeframe, asset_symbol):
    """分析当前K线的交易信号"""
    if df.empty or len(df) < 20:
        return {
            'signal': 'N/A',
            'price': 0,
            'rsi': 'N/A',
            'trend': 'N/A',
            'ema_macd': 'N/A',
            'stop_loss': 'N/A',
            'minutes_since': 999,
            'signal_type': None,
            'should_alert': False
        }
    
    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else latest
    
    current_price = float(latest['Close'])
    
    # RSI值
    rsi_val = f"{latest['rsi']:.1f}" if pd.notna(latest['rsi']) else 'N/A'
    
    # 趋势判断
    if pd.notna(latest['ema20']) and pd.notna(latest['ema50']):
        if current_price > latest['ema20'] > latest['ema50']:
            trend = "多头 🟢"
        elif current_price < latest['ema20'] < latest['ema50']:
            trend = "空头 🔴"
        else:
            trend = "震荡 ⚪"
    else:
        trend = "N/A"
    
    # EMA和MACD交叉状态
    ema_status = latest['ema_cross'] if pd.notna(latest['ema_cross']) else '无'
    macd_status = latest['macd_cross'] if pd.notna(latest['macd_cross']) else '无'
    ema_macd_info = f"{ema_status} | {macd_status}"
    
    # 止损位
    stop_loss = f"{latest['atr_stop_long']:.4f}" if pd.notna(latest['atr_stop_long']) else 'N/A'
    
    # 信号判断（修复的核心部分）
    now_utc = datetime.now(pytz.utc)
    signal_type = None
    signal_text = "维持"
    minutes_since = 999
    
    # 查找最近的买卖信号
    buy_signals = df[df['buy_signal']]
    sell_signals = df[df['sell_signal']]
    
    if not buy_signals.empty:
        last_buy_time = buy_signals.index[-1]
        if isinstance(last_buy_time, pd.Timestamp):
            last_buy_time = last_buy_time.to_pydatetime()
        if last_buy_time.tzinfo is None:
            last_buy_time = pytz.utc.localize(last_buy_time)
        
        buy_minutes = int((now_utc - last_buy_time).total_seconds() / 60)
        
        # 检查是否为最新信号
        if sell_signals.empty or last_buy_time > sell_signals.index[-1]:
            minutes_since = buy_minutes
            if buy_minutes <= 30:
                signal_text = f"🚀 BUY({buy_minutes}m)"
                signal_type = "BUY"
            else:
                signal_text = "多 🟢"
    
    if not sell_signals.empty:
        last_sell_time = sell_signals.index[-1]
        if isinstance(last_sell_time, pd.Timestamp):
            last_sell_time = last_sell_time.to_pydatetime()
        if last_sell_time.tzinfo is None:
            last_sell_time = pytz.utc.localize(last_sell_time)
        
        sell_minutes = int((now_utc - last_sell_time).total_seconds() / 60)
        
        # 检查是否为最新信号
        if buy_signals.empty or last_sell_time > buy_signals.index[-1]:
            if sell_minutes < minutes_since:  # 取最近的信号
                minutes_since = sell_minutes
                if sell_minutes <= 30:
                    signal_text = f"📉 SELL({sell_minutes}m)"
                    signal_type = "SELL"
                else:
                    signal_text = "空 🔴"
    
    # 推送判断（修复逻辑）
    should_alert = False
    signal_key = f"{asset_symbol}_{timeframe}"
    
    if signal_type and minutes_since <= alert_min:
        last_alert = st.session_state.signal_history.get(signal_key)
        
        if last_alert is None:
            # 第一次收到信号
            should_alert = True
        else:
            last_time = last_alert.get('time')
            last_type = last_alert.get('type')
            
            # 检查是否需要推送
            time_diff = (now_utc - last_time).total_seconds() if last_time else 9999
            
            if time_diff > 1800:  # 30分钟冷却期
                should_alert = True
            elif last_type != signal_type:
                should_alert = True  # 信号方向变化
    
    # 如果需要推送，更新历史记录
    if should_alert and signal_type:
        st.session_state.signal_history[signal_key] = {
            'time': now_utc,
            'type': signal_type,
            'price': current_price
        }
    
    return {
        'signal': signal_text,
        'price': current_price,
        'rsi': rsi_val,
        'trend': trend,
        'ema_macd': ema_macd_info,
        'stop_loss': stop_loss,
        'minutes_since': minutes_since,
        'signal_type': signal_type,
        'should_alert': should_alert
    }

# ============================================
# 微信推送函数
# ============================================
def send_wx_pusher(app_token, uid, title, content):
    """发送微信推送"""
    if not app_token or not uid or app_token == "your_app_token" or uid == "your_uid":
        return False
    
    try:
        url = "https://wxpusher.zjiecode.com/api/send/message"
        payload = {
            "appToken": app_token,
            "content": content,
            "summary": title[:100],
            "contentType": 1,
            "uids": [uid]
        }
        
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            result = response.json()
            if result.get("code") == 1000:
                return True
            else:
                st.error(f"推送失败: {result.get('msg')}")
                return False
        else:
            st.error(f"HTTP错误: {response.status_code}")
            return False
            
    except Exception as e:
        st.error(f"推送异常: {str(e)}")
        return False

# ============================================
# 多空比获取
# ============================================
def get_long_short_ratio(symbol):
    """获取币安合约多空比"""
    try:
        url = f"https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol={symbol}USDT&period=5m&limit=1"
        response = requests.get(url, timeout=5)
        data = response.json()
        
        if data and isinstance(data, list) and len(data) > 0:
            ratio = float(data[0]['longShortRatio'])
            
            if ratio > 1.5:
                return f"{ratio:.2f} 🟢(极度乐观)"
            elif ratio > 1.2:
                return f"{ratio:.2f} 🟡(乐观)"
            elif ratio > 0.8:
                return f"{ratio:.2f} ⚪(中性)"
            elif ratio > 0.5:
                return f"{ratio:.2f} 🟠(悲观)"
            else:
                return f"{ratio:.2f} 🔴(极度悲观)"
    
    except Exception as e:
        pass
    
    return "N/A"

# ============================================
# 表格渲染函数（支持止损位显示）
# ============================================
def render_data_table(data_rows):
    """渲染数据表格"""
    if not data_rows:
        st.warning("没有数据可显示")
        return
    
    # 创建DataFrame
    columns = ["资产", "现价", "趋势", "多空比(5m)"]
    
    if show_resonance:
        columns.append("周期共振")
    
    if show_stop_loss:
        columns.append("动态止损")
    
    # 添加时间周期列
    intervals = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]
    columns.extend(intervals)
    
    df_display = pd.DataFrame(data_rows, columns=columns)
    
    # 自定义CSS样式
    st.markdown("""
    <style>
    .dataframe {
        width: 100%;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        font-size: 0.85em;
    }
    
    .buy-signal {
        background-color: rgba(0, 255, 0, 0.1) !important;
        color: #00ff00 !important;
        font-weight: bold !important;
    }
    
    .sell-signal {
        background-color: rgba(255, 0, 0, 0.1) !important;
        color: #ff4444 !important;
        font-weight: bold !important;
    }
    
    .bullish {
        color: #00ff00;
        font-weight: bold;
    }
    
    .bearish {
        color: #ff4444;
        font-weight: bold;
    }
    
    .neutral {
        color: #888888;
    }
    
    .stop-loss {
        color: #ff9900;
        font-weight: bold;
    }
    
    .resonance-strong {
        background-color: rgba(0, 100, 0, 0.2) !important;
        color: #00ff00 !important;
        font-weight: bold !important;
    }
    
    .resonance-weak {
        background-color: rgba(100, 0, 0, 0.2) !important;
        color: #ff4444 !important;
        font-weight: bold !important;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # 转换DataFrame为HTML并应用样式
    html = df_display.to_html(escape=False, index=False)
    
    # 应用样式类
    html = html.replace('<td>🚀 BUY', '<td class="buy-signal">🚀 BUY')
    html = html.replace('<td>📉 SELL', '<td class="sell-signal">📉 SELL')
    html = html.replace('<td>多 🟢', '<td class="bullish">多 🟢')
    html = html.replace('<td>空 🔴', '<td class="bearish">空 🔴')
    html = html.replace('<td>维持', '<td class="neutral">维持')
    
    if show_stop_loss:
        html = html.replace('<td>动态止损', '<td class="stop-loss">动态止损')
    
    # 显示表格
    st.markdown(html, unsafe_allow_html=True)

# ============================================
# 主界面
# ============================================
st.title("🚀 UT Bot 专业交易看板")
st.markdown("**超级趋势策略 + 多指标共振 + 实时风控**")

# 顶部控制栏
col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
with col1:
    if st.button("🔄 手动刷新数据", use_container_width=True):
        st.session_state.last_refresh = datetime.now(BEIJING_TZ)
        st.rerun()

with col2:
    refresh_status = st.empty()
    refresh_status.markdown(f"**最后刷新:** {st.session_state.last_refresh.strftime('%H:%M:%S')}")

with col3:
    st.metric("监控资产数", len(selected_cryptos))

with col4:
    # 倒计时
    next_refresh = st.session_state.last_refresh + timedelta(seconds=300)
    remaining = (next_refresh - datetime.now(BEIJING_TZ)).seconds
    st.metric("下次刷新", f"{remaining}秒")

# 主数据加载区域
st.markdown("---")
st.subheader("📊 实时市场信号")

try:
    # 初始化交易所连接
    exchange = ccxt.okx({
        'enableRateLimit': True,
        'timeout': 15000,
        'rateLimit': 100
    })
    
    all_data = []
    
    # 进度条
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for idx, symbol in enumerate(selected_cryptos):
        status_text.text(f"正在获取 {symbol} 数据... ({idx+1}/{len(selected_cryptos)})")
        
        # 确定交易对格式
        if symbol in ["TAO", "XAG", "XAU"]:
            trading_pair = f"{symbol}/USDT:USDT"
        else:
            trading_pair = f"{symbol}/USDT"
        
        row_data = {
            "资产": symbol,
            "现价": "N/A",
            "趋势": "N/A",
            "多空比(5m)": get_long_short_ratio(symbol),
            "周期共振": "N/A",
            "动态止损": "N/A"
        }
        
        # 存储各周期信号
        timeframe_signals = {}
        current_price = None
        
        # 获取各时间周期数据
        timeframes = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]
        
        for tf in timeframes:
            try:
                # 获取K线数据
                ohlcv = exchange.fetch_ohlcv(trading_pair, timeframe=tf, limit=100)
                
                if ohlcv and len(ohlcv) > 50:
                    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                    df.set_index('timestamp', inplace=True)
                    
                    # 计算指标
                    df_indicators = calculate_indicators(df)
                    
                    # 分析信号
                    signal_info = get_signal_analysis(df_indicators, tf, symbol)
                    
                    # 记录信号
                    timeframe_signals[tf] = signal_info
                    
                    # 更新当前价格（使用1小时周期的价格）
                    if tf == "1h" and signal_info['price'] > 0:
                        current_price = signal_info['price']
                        row_data["现价"] = f"{current_price:.4f}"
                        row_data["趋势"] = signal_info['trend']
                    
                    # 构建显示文本
                    display_text = signal_info['signal']
                    
                    if signal_info['rsi'] != 'N/A':
                        rsi_num = float(signal_info['rsi'])
                        rsi_color = "🟢" if rsi_num < 30 else "🔴" if rsi_num > 70 else "⚪"
                        display_text += f" | RSI:{signal_info['rsi']}{rsi_color}"
                    
                    display_text += f" | {signal_info['ema_macd']}"
                    
                    # 添加止损位（仅在1h和4h周期显示）
                    if tf in ["1h", "4h"] and signal_info['stop_loss'] != 'N/A' and show_stop_loss:
                        display_text += f" | 止损:{signal_info['stop_loss']}"
                    
                    row_data[tf] = display_text
                    
                    # 微信推送（仅在30m和1h周期，且信号新鲜时）
                    if tf in ["30m", "1h"] and signal_info['should_alert']:
                        if app_token and user_uid:
                            signal_type = "买入" if signal_info['signal_type'] == "BUY" else "卖出"
                            
                            # 构建推送内容
                            title = f"🚨 {symbol} {tf} {signal_type}信号"
                            content = f"""
                            🎯 资产：{symbol}
                            ⏰ 周期：{tf}
                            📈 信号：{signal_info['signal']}
                            💰 价格：{signal_info['price']:.4f}
                            📊 RSI：{signal_info['rsi']}
                            🎯 趋势：{signal_info['trend']}
                            🛡️ 止损：{signal_info['stop_loss']}
                            🔄 状态：{signal_info['ema_macd']}
                            ⚖️ 多空比：{row_data['多空比(5m)']}
                            """
                            
                            # 发送推送
                            if send_wx_pusher(app_token, user_uid, title, content):
                                st.toast(f"{symbol} {tf} 信号已推送", icon="✅")
                
                else:
                    row_data[tf] = "数据不足"
                    
            except Exception as tf_error:
                row_data[tf] = f"错误: {str(tf_error)[:20]}"
        
        # 计算多周期共振
        if show_resonance and timeframe_signals:
            buy_count = sum(1 for tf in ["30m", "1h", "4h"] 
                          if tf in timeframe_signals and timeframe_signals[tf]['signal_type'] == "BUY")
            sell_count = sum(1 for tf in ["30m", "1h", "4h"] 
                           if tf in timeframe_signals and timeframe_signals[tf]['signal_type'] == "SELL")
            
            if buy_count >= 2:
                row_data["周期共振"] = f"多头共振({buy_count}/3) 🟢"
            elif sell_count >= 2:
                row_data["周期共振"] = f"空头共振({sell_count}/3) 🔴"
            else:
                row_data["周期共振"] = "无共振 ⚪"
        
        # 设置动态止损显示
        if show_stop_loss and "1h" in timeframe_signals:
            row_data["动态止损"] = timeframe_signals["1h"]['stop_loss']
        
        all_data.append(row_data)
        progress_bar.progress((idx + 1) / len(selected_cryptos))
    
    # 清空进度状态
    progress_bar.empty()
    status_text.empty()
    
    # 渲染数据表格
    if all_data:
        render_data_table(all_data)
        
        # 显示统计信息
        st.markdown("---")
        
        col_stat1, col_stat2, col_stat3 = st.columns(3)
        
        buy_signals = sum(1 for row in all_data 
                         if any("BUY" in str(row.get(tf, "")) for tf in ["30m", "1h"]))
        sell_signals = sum(1 for row in all_data 
                          if any("SELL" in str(row.get(tf, "")) for tf in ["30m", "1h"]))
        
        with col_stat1:
            st.metric("30m/1h买入信号", buy_signals)
        with col_stat2:
            st.metric("30m/1h卖出信号", sell_signals)
        with col_stat3:
            st.metric("信号推送", len(st.session_state.signal_history))
        
        # 显示信号历史
        with st.expander("📋 最近信号推送记录"):
            if st.session_state.signal_history:
                history_data = []
                for key, record in list(st.session_state.signal_history.items())[-10:]:
                    symbol, tf = key.split("_")
                    history_data.append({
                        "时间": record['time'].astimezone(BEIJING_TZ).strftime("%H:%M:%S"),
                        "资产": symbol,
                        "周期": tf,
                        "类型": record['type'],
                        "价格": f"{record.get('price', 0):.4f}"
                    })
                
                if history_data:
                    st.dataframe(pd.DataFrame(history_data), use_container_width=True)
            else:
                st.info("暂无推送记录")
        
        # 风险提示
        st.info("""
        ⚠️ **风险提示**：
        1. 本系统为技术分析工具，不构成投资建议
        2. 止损位仅供参考，请根据个人风险承受能力调整
        3. 市场有风险，投资需谨慎
        4. 建议结合基本面分析和风险管理策略使用
        """)
    
    else:
        st.warning("未能获取任何数据，请检查网络连接或资产选择")
        
except Exception as e:
    st.error(f"系统错误: {str(e)}")
    st.exception(e)

# ============================================
# 页脚
# ============================================
st.markdown("---")
st.caption(f"""
🔄 系统最后更新: {datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')} | 
📊 数据源: OKX + Binance | 
⚡ 刷新间隔: 5分钟 | 
🛡️ 版本: 2.0 (增强稳定版)
""")
