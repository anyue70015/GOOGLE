import streamlit as st
import pandas as pd
import ccxt
from concurrent.futures import ThreadPoolExecutor

# --- 页面配置 ---
st.set_page_config(page_title="全市场深度狙击镜 V3", layout="wide")

class FinalScanner:
    def __init__(self):
        # 移除了代理，专注 OKX 和 Gate
        self.exchanges = {
            'OKX': ccxt.okx({'timeout': 30000, 'enableRateLimit': True}),
            'Gate': ccxt.gateio({'timeout': 30000, 'enableRateLimit': True})
        }
        self.btc_change_1h = 0.0

    def get_btc_status(self):
        try:
            ohlcv = self.exchanges['OKX'].fetch_ohlcv('BTC/USDT', '1h', limit=2)
            self.btc_change_1h = (ohlcv[-1][4] - ohlcv[-2][4]) / ohlcv[-2][4] * 100
            return True
        except: return False

    def analyze_coin(self, exch_name, symbol):
        try:
            exch = self.exchanges[exch_name]
            bars = exch.fetch_ohlcv(symbol, '1h', limit=100)
            if len(bars) < 60: return None
            
            df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
            df['sma20'] = df['c'].rolling(20).mean()
            df['sma50'] = df['c'].rolling(50).mean()
            
            curr = df.iloc[-1]
            prev = df.iloc[-2]
            
            # --- 量化指标 ---
            change_1h = (curr['c'] - prev['c']) / prev['c'] * 100
            vol_avg = df['v'].tail(24).mean()
            vol_ratio = curr['v'] / vol_avg if vol_avg > 0 else 0
            bias = (curr['c'] - curr['sma20']) / curr['sma20'] * 100
            is_uptrend = curr['c'] > curr['sma20'] > curr['sma50']
            
            # --- 评分逻辑 ---
            score = 0
            if is_uptrend: score += 2
            if change_1h > self.btc_change_1h: score += 3 # 强于大盘
            if vol_ratio > 2.0: score += 3                # 资金入场
            if 0 < bias < 2.5: score += 2                 # 安全位置

            # --- 入场建议诊断 ---
            if score >= 7:
                if bias > 6: advice = "⚠️ 高位超买(别追)"
                elif bias < 2.5: advice = "🚀 极品入场点"
                else: advice = "✅ 强势运行"
            elif score >= 5:
                advice = "👀 持续观察"
            else:
                advice = "❄️ 趋势不明"

            # 计算小时成交额 (USDT)
            hourly_volume_usdt = curr['c'] * curr['v']

            return {
                "来源": exch_name,
                "交易对": symbol,
                "评分": score,
                "入场建议": advice,
                "成交额(1h/万)": round(hourly_volume_usdt / 10000, 2),
                "量比": round(vol_ratio, 2),
                "偏离度%": round(bias, 2),
                "24h涨幅%": round((curr['c'] - df['c'].iloc[-24]) / df['c'].iloc[-24] * 100, 2),
            }
        except: return None

def main():
    st.title("🛰️ 全市场深度扫描 & 自动避坑系统")
    
    with st.sidebar:
        st.header("⚙️ 扫描配置")
        # 成交量过滤：默认只看 1h 成交额大于 5 万 USDT 的币
        vol_threshold = st.slider("最小 1h 成交额 (万 USDT)", 0, 100, 5)
        min_score_filter = st.slider("显示最低评分", 0, 10, 4)
        target_ex = st.multiselect("交易所", ["OKX", "Gate"], default=["OKX", "Gate"])
        
        st.divider()
        st.write("**入场秘籍：**")
        st.write("1. 评分 > 7")
        st.write("2. 偏离度 < 2.5%")
        st.write("3. 成交额越多越安全")
        
        run = st.button("开始深度扫描", type="primary", use_container_width=True)

    if run:
        scanner = FinalScanner()
        if not scanner.get_btc_status():
            st.error("无法获取大盘数据，请检查网络")
            return

        st.info(f"📊 大盘基准：BTC 1h 涨跌 {scanner.btc_change_1h:.2f}%")
        
        all_results = []
        for name in target_ex:
            markets = scanner.exchanges[name].load_markets()
            # 只要是 USDT 交易对且在售
            symbols = [s for s, m in markets.items() if '/USDT' in s and m.get('spot') and m.get('active')]
            st.write(f"正在扫描 {name} 的 {len(symbols)} 个币种...")
            
            with ThreadPoolExecutor(max_workers=50) as executor:
                futures = [executor.submit(scanner.analyze_coin, name, s) for s in symbols]
                for f in futures:
                    res = f.result()
                    # 应用侧边栏的成交量和评分过滤
                    if res and res['成交额(1h/万)'] >= vol_threshold and res['评分'] >= min_score_filter:
                        all_results.append(res)

        if all_results:
            df = pd.DataFrame(all_results).sort_values(by='评分', ascending=False)
            
            # 格式化表格颜色
            def color_advice(val):
                if "🚀" in val: color = '#00ff00'
                elif "⚠️" in val: color = '#ff4b4b'
                elif "✅" in val: color = '#1e90ff'
                else: color = '#888888'
                return f'color: {color}'

            st.dataframe(df.style.applymap(color_advice, subset=['入场建议']), use_container_width=True, height=800)
        else:
            st.warning("按当前标准未扫到币，请尝试调低成交量要求或评分要求。")

if __name__ == "__main__":
    main()
