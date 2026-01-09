import streamlit as st
import pandas as pd
import ccxt
import time
from concurrent.futures import ThreadPoolExecutor

st.set_page_config(page_title="全量选币狙击镜-修复版", layout="wide")

class RefinedScanner:
    def __init__(self):
        # 针对连接问题增加配置
        self.exchanges = {
            'OKX': ccxt.okx({'timeout': 30000, 'enableRateLimit': True}),
            'Gate': ccxt.gateio({'timeout': 30000, 'enableRateLimit': True})
        }
        self.btc_change_1h = 0.0

    def get_btc_status(self):
        try:
            # 优先从 OKX 获取大盘基准
            ohlcv = self.exchanges['OKX'].fetch_ohlcv('BTC/USDT', '1h', limit=2)
            self.btc_change_1h = (ohlcv[-1][4] - ohlcv[-2][4]) / ohlcv[-2][4] * 100
            return True
        except: return False

    def analyze_coin(self, exch_name, symbol):
        try:
            exch = self.exchanges[exch_name]
            # 获取数据，减少 limit 提升速度
            bars = exch.fetch_ohlcv(symbol, '1h', limit=60)
            if not bars or len(bars) < 50: return None
            
            df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
            df['sma20'] = df['c'].rolling(20).mean()
            df['sma50'] = df['c'].rolling(50).mean()
            
            curr = df.iloc[-1]
            prev = df.iloc[-2]
            
            change_1h = (curr['c'] - prev['c']) / prev['c'] * 100
            vol_avg = df['v'].tail(24).mean()
            vol_ratio = curr['v'] / vol_avg if vol_avg > 0 else 0
            bias = (curr['c'] - curr['sma20']) / curr['sma20'] * 100
            is_uptrend = curr['c'] > curr['sma20'] > curr['sma50']
            
            # --- 核心评分逻辑 ---
            score = 0
            if is_uptrend: score += 2
            if change_1h > self.btc_change_1h: score += 3 # 强于大盘
            if vol_ratio > 1.5: score += 3                # 活跃度
            if 0 < bias < 3: score += 2                   # 位置优

            # 诊断建议
            if score >= 7:
                advice = "🚀 极品入场" if bias < 2.5 else "✅ 强势持仓"
            elif score >= 5:
                advice = "👀 持续观察"
            else:
                advice = "❄️ 观望"

            return {
                "来源": exch_name,
                "交易对": symbol,
                "评分": int(score),
                "入场建议": advice,
                "成交额(1h/万)": round((curr['c'] * curr['v']) / 10000, 2),
                "量比": round(vol_ratio, 2),
                "偏离度%": round(bias, 2),
                "24h涨幅%": round((curr['c'] - df['c'].iloc[-24]) / df['c'].iloc[-24] * 100, 2)
            }
        except: return None

def main():
    st.title("🎯 全球币种全量狙击镜 (OKX + Gate)")
    
    with st.sidebar:
        st.header("🔍 过滤条件")
        # 重点：这里的滑块数值会实时应用到结果
        min_score_val = st.slider("最低评分过滤", 0, 10, 5)
        vol_threshold = st.number_input("最小1h成交额(万USDT)", value=2.0)
        target_ex = st.multiselect("选择交易所", ["OKX", "Gate"], default=["OKX", "Gate"])
        st.divider()
        run_scan = st.button("开始全市场深度扫描", type="primary", use_container_width=True)

    if run_scan:
        scanner = RefinedScanner()
        scanner.get_btc_status()
        st.info(f"大盘基准 (BTC 1h): {scanner.btc_change_1h:.2f}%")
        
        all_results = []
        for name in target_ex:
            st.write(f"正在读取 {name} 的所有币种清单...")
            try:
                # 重新获取市场，强制加载
                m = scanner.exchanges[name].load_markets()
                # 改进筛选逻辑：确保 Gate 的复杂命名也能被识别
                symbols = [s for s, info in m.items() if '/USDT' in s and info.get('active')]
                st.write(f"在 {name} 找到 {len(symbols)} 个交易对，正在分析趋势...")
                
                # 增加并发数到 60 提升速度
                with ThreadPoolExecutor(max_workers=60) as executor:
                    futures = [executor.submit(scanner.analyze_coin, name, s) for s in symbols]
                    for f in futures:
                        res = f.result()
                        # 核心筛选：必须满足成交量且评分大于等于设定的滑块值
                        if res and res['成交额(1h/万)'] >= vol_threshold:
                            if res['评分'] >= min_score_val:
                                all_results.append(res)
            except Exception as e:
                st.error(f"{name} 扫描中断: {e}")

        if all_results:
            df = pd.DataFrame(all_results).sort_values(by=['评分', '成交额(1h/万)'], ascending=False)
            
            # 表格美化
            def style_score(val):
                color = 'green' if val >= 7 else 'orange' if val >= 5 else 'white'
                return f'color: {color}; font-weight: bold'

            st.subheader(f"✅ 扫描完成: 共有 {len(df)} 个符合条件的币种")
            st.dataframe(df.style.applymap(style_score, subset=['评分']), use_container_width=True, height=800)
        else:
            st.warning("没有找到符合条件的币，请尝试调低‘最低评分’或‘成交额’。")

if __name__ == "__main__":
    main()
