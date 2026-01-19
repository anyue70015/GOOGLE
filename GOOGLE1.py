import streamlit as st
import numpy as np
import time
import pandas as pd
import random
import akshare as ak
import os
import json
from datetime import datetime, timedelta

st.set_page_config(page_title="科创板 + 创业板短线扫描工具", layout="wide")
st.title("科创板 + 创业板短线扫描工具（前300活跃股版 - 优化版）")

# ── 持久化进度 ──
progress_file = "kcb_cyb_scan_progress.json"

if 'progress_loaded' not in st.session_state:
    st.session_state.progress_loaded = True
    if os.path.exists(progress_file):
        try:
            with open(progress_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            st.session_state.high_prob = data.get("high_prob", [])
            st.session_state.scanned_symbols = set(data.get("scanned_symbols", []))
            st.session_state.failed_count = data.get("failed_count", 0)
            st.session_state.fully_scanned = data.get("fully_scanned", False)
            st.success("已加载历史进度，可继续扫描")
        except Exception as e:
            st.warning(f"进度加载失败: {e}，将从头开始")

def save_progress():
    data = {
        "high_prob": st.session_state.high_prob,
        "scanned_symbols": list(st.session_state.scanned_symbols),
        "failed_count": st.session_state.failed_count,
        "fully_scanned": st.session_state.fully_scanned
    }
    try:
        temp_file = progress_file + ".tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(temp_file, progress_file)
    except:
        pass

# ── 重置按钮 ──
col1, col2 = st.columns(2)
with col1:
    if st.button("🔄 清缓存 & 强制刷新数据"):
        st.cache_data.clear()
        st.session_state.high_prob = []
        st.session_state.scanned_symbols = set()
        st.session_state.failed_count = 0
        st.session_state.fully_scanned = False
        st.session_state.scanning = False
        if os.path.exists(progress_file):
            os.remove(progress_file)
        st.rerun()

with col2:
    if st.button("🔄 重置所有进度"):
        st.session_state.high_prob = []
        st.session_state.scanned_symbols = set()
        st.session_state.failed_count = 0
        st.session_state.fully_scanned = False
        st.session_state.scanning = False
        if os.path.exists(progress_file):
            os.remove(progress_file)
        st.rerun()

# ── 手动暂停 / 继续 ──
if 'paused' not in st.session_state:
    st.session_state.paused = False

col_pause, col_resume = st.columns(2)
with col_pause:
    if not st.session_state.paused:
        if st.button("⏸️ 手动暂停扫描"):
            st.session_state.paused = True
            st.rerun()

with col_resume:
    if st.session_state.paused:
        if st.button("▶️ 手动继续扫描"):
            st.session_state.paused = False
            st.rerun()

st.markdown("扫描**科创板(688开头) + 创业板(300开头)** 最近成交额前300只（总≤600只）。**上市天数 > 360 天**。优质信号（PF7>4 且 概率>68%）排最前面。**优化版：实时显示优质股 + 更稳更快**")

# ==================== 加载股票列表（前300活跃） ====================
@st.cache_data(ttl=1800)
def load_kcb_cyb_tickers():
    try:
        # 优先用同花顺板块接口（稳定、快）
        print("使用 stock_board_industry_name_ths 获取列表...")
        cyb = ak.stock_board_industry_name_ths(symbol="创业板")
        kcb = ak.stock_board_industry_name_ths(symbol="科创板")
        df = pd.concat([cyb, kcb], ignore_index=True)
        df = df.rename(columns={'code': '代码', 'name': '名称'})

        # 补实时成交额（只调用一次 spot）
        spot = ak.stock_zh_a_spot_em()
        spot['代码'] = spot['代码'].astype(str).str.zfill(6)
        spot_dict = dict(zip(spot['代码'], spot['成交额']))

        df['代码'] = df['代码'].astype(str).str.zfill(6)
        df['成交额'] = df['代码'].map(spot_dict).fillna(0)
        df = df.sort_values('成交额', ascending=False)

        # 每个板块取前300
        kcb_top = df[df['代码'].str.startswith('688')].head(300)
        cyb_top = df[df['代码'].str.startswith('300')].head(300)
        df_selected = pd.concat([kcb_top, cyb_top], ignore_index=True)

        tickers = df_selected['代码'].tolist()
        names = dict(zip(df_selected['代码'], df_selected['名称']))

        st.success(f"加载成功：科创前300 + 创业前300 = {len(tickers)} 只（使用同花顺+东财混合源）")
        return tickers, names
    except Exception as e:
        st.error(f"列表加载失败: {e}，使用备用列表")
        return ["688981", "300750"], {"688981": "中芯国际", "300750": "宁德时代"}

tickers_to_scan, stock_names = load_kcb_cyb_tickers()
st.write(f"扫描范围：每个板块最近成交额前300（总计 {len(tickers_to_scan)} 只）")

# ==================== 回测周期 ====================
BACKTEST_CONFIG = {
    "3个月": {"days": 90},
    "6个月": {"days": 180},
    "1年":   {"days": 365},
    "2年":   {"days": 730},
}

# ==================== 获取日K ====================
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_ohlcv_ak(symbol: str, days_back: int):
    try:
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days_back + 60)).strftime("%Y%m%d")
        time.sleep(random.uniform(1.2, 2.5))  # 加大间隔防限流
        df = ak.stock_zh_a_hist(
            symbol=symbol, period="daily", start_date=start_date, end_date=end_date, adjust="qfq"
        )
        if df.empty or len(df) < 30:
            return None, None, None, None
        close = df['收盘'].values.astype(float)
        high = df['最高'].values.astype(float)
        low = df['最低'].values.astype(float)
        volume = df['成交量'].values.astype(float) * 100
        return close, high, low, volume
    except Exception:
        return None, None, None, None

# ==================== 指标函数（保持原样） ====================
# ...（你的 ema_np, macd_hist_np, rsi_np, atr_np, rolling_mean_np, obv_np, backtest_with_stats 函数保持不变）
# 为节省空间，这里省略，但请复制你原代码里的这些函数过来

# ==================== 核心计算 ====================
@st.cache_data(show_spinner=False)
def compute_stock_metrics(symbol: str, cfg_key: str = "1年"):
    # 上市天数检查
    try:
        info = ak.stock_individual_info_em(symbol)
        listing_str = info[info['item'] == '上市日期']['value'].values[0]
        listing_date = pd.to_datetime(listing_str)
        days_listed = (datetime.now() - listing_date).days
        if days_listed <= 360:
            return None
    except:
        pass  # 查不到默认继续

    days = BACKTEST_CONFIG[cfg_key]["days"]
    close, high, low, volume = fetch_ohlcv_ak(symbol, days)
    if close is None:
        return None

    # ...（你的 macd_hist, rsi, atr, obv, vol_ma20 等计算保持不变）

    # score 计算保持不变

    # 历史 score_arr 计算保持不变

    prob7, pf7 = backtest_with_stats(close[:-1], score_arr[:-1], 7)
    pf7 = min(pf7, 9999) if pf7 > 9999 else pf7  # 防 inf

    # ...（其余 price, change, is_low_liquidity, sig_details 保持不变）

    return {
        "symbol": symbol,
        "name": stock_names.get(symbol, "未知"),
        "price": round(price, 2),
        "change": round(change, 2),
        "score": score,
        "prob7": prob7,
        "pf7": pf7,
        "prob7_pct": round(prob7 * 100, 1),
        "is_low_liquidity": is_low_liquidity,
        "signals": ", ".join([k for k, v in sig_details.items() if v]) or "无"
    }

# ==================== 主界面 ====================
mode = st.selectbox("回测周期", list(BACKTEST_CONFIG.keys()), index=2)

for key in ['high_prob', 'scanned_symbols', 'failed_count', 'fully_scanned', 'scanning', 'paused']:
    if key not in st.session_state:
        if key == 'scanned_symbols':
            st.session_state[key] = set()
        elif key == 'high_prob':
            st.session_state[key] = []
        elif key == 'paused':
            st.session_state[key] = False
        else:
            st.session_state[key] = 0 if 'count' in key else False

progress_bar = st.progress(0)
status_text = st.empty()

current_completed = len(st.session_state.scanned_symbols & set(tickers_to_scan))
total = len(tickers_to_scan)
progress_bar.progress(min(1.0, current_completed / total) if total > 0 else 0)

st.info(f"已完成: {current_completed}/{total} | 优质发现: {sum(1 for x in st.session_state.high_prob if x['pf7'] > 4 and x['prob7_pct'] > 68)} | 失败/跳过: {st.session_state.failed_count}")

# 扫描逻辑
if st.button("🚀 开始/继续扫描"):
    st.session_state.scanning = True

if st.session_state.scanning and current_completed < total and not st.session_state.paused:
    with st.spinner("扫描中（每批100只，实时显示优质）..."):
        batch_size = 100
        processed = 0
        remaining = [s for s in tickers_to_scan if s not in st.session_state.scanned_symbols]
        batch_start = time.time()

        for sym in remaining:
            if processed >= batch_size or st.session_state.paused:
                break
            status_text.text(f"正在计算 {sym} ({current_completed + processed + 1}/{total})")
            progress_bar.progress((current_completed + processed + 1) / total)

            try:
                metrics = compute_stock_metrics(sym, mode)
                if metrics:
                    st.session_state.high_prob.append(metrics)

                    # 实时显示优质股
                    if metrics['pf7'] > 4 and metrics['prob7_pct'] > 68:
                        st.success(f"【优质实时发现】 {sym} {metrics['name']}   PF7={metrics['pf7']:.2f}   7日胜率={metrics['prob7_pct']}%   得分={metrics['score']}   信号: {metrics['signals']}")
                else:
                    st.session_state.failed_count += 1
            except Exception as e:
                st.session_state.failed_count += 1

            st.session_state.scanned_symbols.add(sym)
            processed += 1

            time.sleep(random.uniform(1.8, 3.2))  # 防限流

        batch_time = time.time() - batch_start
        st.info(f"本批 {processed} 只完成，耗时 {batch_time:.1f} 秒，平均 {batch_time/processed:.1f} 秒/只")

        if len(st.session_state.scanned_symbols & set(tickers_to_scan)) >= total:
            st.session_state.fully_scanned = True
            st.session_state.scanning = False
            st.success("全部扫描完成！优质股已在上方实时弹出")

        save_progress()
        st.rerun()

if st.session_state.fully_scanned:
    st.success("已完成全部扫描！")

# ==================== 结果显示（优质排前） ====================
# ...（你的 df_all, mask_premium, df_premium, df_others, df_display, display_lines, txt_lines 等保持不变）

# 只需注意：在 st.text_area 前加一句
if high_prob_list:
    premium_now = sum(1 for x in high_prob_list if x['pf7'] > 4 and x['prob7_pct'] > 68)
    st.subheader(f"扫描结果共 {len(df_display)} 只，其中优质 {premium_now} 只（实时已弹出，可全选复制）")

# 其余下载按钮等保持原样
