import streamlit as st
import pandas as pd
import numpy as np
import time
import json
from datetime import datetime, timedelta
import warnings
import sys
import os

warnings.filterwarnings('ignore')

# 设置页面配置为第一行
st.set_page_config(
    page_title="加密货币智能扫描器",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 检查并安装ccxt的备用方案
def ensure_ccxt():
    """确保ccxt可用"""
    try:
        import ccxt
        return ccxt, True
    except ImportError:
        return None, False

# 检查并安装matplotlib的备用方案
def ensure_matplotlib():
    """确保matplotlib可用"""
    try:
        import matplotlib.pyplot as plt
        return plt, True
    except ImportError:
        return None, False

# 获取模块
ccxt_module, ccxt_available = ensure_ccxt()
plt_module, matplotlib_available = ensure_matplotlib()

# 离线演示数据
DEMO_SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT",
    "ADA/USDT", "DOGE/USDT", "DOT/USDT", "MATIC/USDT", "LTC/USDT",
    "AVAX/USDT", "LINK/USDT", "ATOM/USDT", "UNI/USDT", "XLM/USDT",
    "ALGO/USDT", "VET/USDT", "THETA/USDT", "FIL/USDT", "TRX/USDT"
]

DEMO_RESULTS = [
    {"symbol": "BTC/USDT", "total_return": 25.8, "win_rate": 58.2, "volatility": 2.1, "sharpe": 1.8},
    {"symbol": "ETH/USDT", "total_return": 32.5, "win_rate": 55.4, "volatility": 3.2, "sharpe": 1.5},
    {"symbol": "SOL/USDT", "total_return": 180.3, "win_rate": 62.1, "volatility": 8.5, "sharpe": 2.1},
    {"symbol": "BNB/USDT", "total_return": 45.2, "win_rate": 53.7, "volatility": 2.8, "sharpe": 1.6},
    {"symbol": "ADA/USDT", "total_return": -12.3, "win_rate": 48.5, "volatility": 5.4, "sharpe": -0.3},
    {"symbol": "XRP/USDT", "total_return": 18.7, "win_rate": 51.2, "volatility": 4.2, "sharpe": 0.8},
    {"symbol": "DOGE/USDT", "total_return": 65.4, "win_rate": 57.8, "volatility": 12.3, "sharpe": 1.2},
    {"symbol": "DOT/USDT", "total_return": 28.9, "win_rate": 52.4, "volatility": 4.8, "sharpe": 1.1},
    {"symbol": "MATIC/USDT", "total_return": 42.1, "win_rate": 56.3, "volatility": 5.2, "sharpe": 1.4},
    {"symbol": "AVAX/USDT", "total_return": 95.7, "win_rate": 60.2, "volatility": 7.8, "sharpe": 1.9}
]

class CryptoScanner:
    def __init__(self, exchange_id='binance'):
        if not ccxt_available:
            self.mode = "offline"
        else:
            self.mode = "online"
            try:
                self.exchange = getattr(ccxt_module, exchange_id)({
                    'enableRateLimit': True,
                    'options': {'defaultType': 'spot'},
                    'timeout': 30000
                })
            except Exception as e:
                st.error(f"交易所连接失败: {e}")
                self.mode = "offline"
    
    def fetch_symbols(self, quote_currency='USDT', limit=50):
        """获取交易对列表"""
        if self.mode == "offline":
            # 返回演示数据
            symbols = [s for s in DEMO_SYMBOLS if s.endswith(f'/{quote_currency}')]
            return symbols[:limit]
        
        try:
            self.exchange.load_markets()
            symbols = []
            count = 0
            for symbol in self.exchange.symbols:
                if symbol.endswith(f'/{quote_currency}'):
                    symbols.append(symbol)
                    count += 1
                    if count >= limit:
                        break
            return symbols
        except Exception as e:
            st.warning(f"在线获取失败，使用演示数据: {e}")
            symbols = [s for s in DEMO_SYMBOLS if s.endswith(f'/{quote_currency}')]
            return symbols[:limit]
    
    def simple_backtest(self, symbol, days=180):
        """执行回测"""
        if self.mode == "offline":
            # 生成模拟回测结果
            time.sleep(0.05)  # 模拟延迟
            
            # 查找演示数据中的结果
            for result in DEMO_RESULTS:
                if result['symbol'] == symbol:
                    result_copy = result.copy()
                    result_copy.update({
                        'max_price': np.random.uniform(100, 1000),
                        'min_price': np.random.uniform(10, 100),
                        'data_points': np.random.randint(100, 200),
                        'num_trades': np.random.randint(5, 20)
                    })
                    return result_copy
            
            # 如果没找到，生成随机结果
            return {
                'symbol': symbol,
                'total_return': np.random.uniform(-20, 200),
                'win_rate': np.random.uniform(45, 65),
                'volatility': np.random.uniform(2, 15),
                'sharpe': np.random.uniform(-0.5, 2.5),
                'max_price': np.random.uniform(100, 1000),
                'min_price': np.random.uniform(10, 100),
                'data_points': np.random.randint(100, 200),
                'num_trades': np.random.randint(5, 20)
            }
        
        try:
            # 在线回测逻辑
            since = self.exchange.parse8601(
                (datetime.now() - timedelta(days=days)).isoformat()
            )
            
            # 获取OHLCV数据
            ohlcv = self.exchange.fetch_ohlcv(
                symbol, '1d', since=since, limit=min(days, 200)
            )
            
            if len(ohlcv) < 30:
                return None
            
            df = pd.DataFrame(
                ohlcv, 
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
            )
            
            # 计算指标
            df['returns'] = df['close'].pct_change()
            df['sma_20'] = df['close'].rolling(20).mean()
            df['sma_50'] = df['close'].rolling(50).mean()
            
            # 交易信号
            df['signal'] = 0
            df.loc[df['sma_20'] > df['sma_50'], 'signal'] = 1
            df.loc[df['sma_20'] < df['sma_50'], 'signal'] = -1
            
            # 计算收益
            df['strategy_returns'] = df['signal'].shift(1) * df['returns']
            
            # 绩效指标
            total_return = (1 + df['strategy_returns'].fillna(0)).cumprod().iloc[-1] - 1
            
            strategy_returns = df['strategy_returns'].dropna()
            if len(strategy_returns) > 0:
                win_rate = (strategy_returns > 0).mean()
                if strategy_returns.std() > 0:
                    sharpe = (strategy_returns.mean() / strategy_returns.std()) * np.sqrt(252)
                else:
                    sharpe = 0
            else:
                win_rate = 0
                sharpe = 0
            
            return {
                'symbol': symbol,
                'total_return': round(total_return * 100, 2),
                'win_rate': round(win_rate * 100, 2),
                'volatility': round(df['returns'].std() * 100, 2),
                'sharpe': round(sharpe, 2),
                'max_price': round(df['close'].max(), 4),
                'min_price': round(df['close'].min(), 4),
                'data_points': len(df),
                'num_trades': (df['signal'].diff() != 0).sum() - 1
            }
            
        except Exception as e:
            return None

def create_simple_chart(data, chart_type='bar', title='', x='', y=''):
    """创建简单的图表（使用plotly或原生图表）"""
    try:
        import plotly.express as px
        import plotly.graph_objects as go
        
        if chart_type == 'bar':
            fig = px.bar(data, x=x, y=y, title=title)
        elif chart_type == 'scatter':
            fig = px.scatter(data, x=x, y=y, title=title)
        elif chart_type == 'histogram':
            fig = px.histogram(data, x=x, title=title)
        else:
            fig = px.line(data, x=x, y=y, title=title)
        
        fig.update_layout(
            height=400,
            showlegend=True,
            template='plotly_white'
        )
        return fig
    except:
        # 如果plotly也不可用，返回None
        return None

def main():
    # 自定义CSS
    st.markdown("""
    <style>
    .main-title {
        font-size: 2.8rem;
        font-weight: 800;
        background: linear-gradient(90deg, #1E88E5, #4FC3F7);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        margin-bottom: 1rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 10px;
        padding: 20px;
        color: white;
        margin: 5px;
    }
    .stProgress > div > div > div > div {
        background: linear-gradient(90deg, #1E88E5, #4FC3F7);
    }
    .dataframe {
        width: 100%;
        border-collapse: collapse;
    }
    .dataframe th {
        background-color: #f2f2f2;
        padding: 8px;
        text-align: left;
        border: 1px solid #ddd;
    }
    .dataframe td {
        padding: 8px;
        border: 1px solid #ddd;
    }
    .dataframe tr:nth-child(even) {
        background-color: #f9f9f9;
    }
    .positive {
        color: #28a745;
        font-weight: bold;
    }
    .negative {
        color: #dc3545;
        font-weight: bold;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # 标题
    st.markdown('<div class="main-title">🚀 加密货币智能扫描器</div>', unsafe_allow_html=True)
    
    # 模式指示器
    if not ccxt_available:
        st.warning("🔧 当前为演示模式（使用模拟数据）")
        st.info("如需实时数据，请在本地安装依赖：`pip install ccxt pandas numpy plotly`")
    
    # 侧边栏
    with st.sidebar:
        st.header("⚙️ 扫描配置")
        
        if ccxt_available:
            exchange = st.selectbox(
                "选择交易所",
                ['binance', 'okx', 'bybit', 'kucoin', 'gateio'],
                index=0
            )
        else:
            exchange = "demo"
            st.info("演示模式：使用模拟数据")
        
        quote = st.selectbox(
            "计价货币",
            ['USDT', 'BTC', 'ETH', 'BNB'],
            index=0
        )
        
        col1, col2 = st.columns(2)
        with col1:
            days = st.slider("回测天数", 30, 365, 180)
        with col2:
            max_coins = st.slider("扫描数量", 10, 100, 30)
        
        strategy = st.selectbox(
            "交易策略",
            ['双均线策略', 'RSI策略', '布林带策略', 'MACD策略'],
            index=0
        )
        
        # 开始扫描按钮
        if st.button("🚀 开始智能扫描", type="primary", use_container_width=True):
            st.session_state.scan_requested = True
            st.session_state.scan_complete = False
        
        if st.button("🔄 重置", type="secondary", use_container_width=True):
            for key in ['scan_requested', 'scan_complete', 'results']:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()
        
        st.divider()
        
        # 状态面板
        st.subheader("📊 系统状态")
        status_col1, status_col2 = st.columns(2)
        with status_col1:
            st.metric("模式", "演示" if not ccxt_available else "实时")
        with status_col2:
            st.metric("API状态", "离线" if not ccxt_available else "在线")
    
    # 初始化会话状态
    if 'scan_requested' not in st.session_state:
        st.session_state.scan_requested = False
    if 'scan_complete' not in st.session_state:
        st.session_state.scan_complete = False
    if 'results' not in st.session_state:
        st.session_state.results = []
    
    # 主界面
    if st.session_state.scan_requested and not st.session_state.scan_complete:
        # 创建扫描器
        scanner = CryptoScanner(exchange_id=exchange)
        
        # 获取交易对
        with st.spinner("🔄 正在获取交易对列表..."):
            symbols = scanner.fetch_symbols(quote_currency=quote, limit=max_coins)
        
        if not symbols:
            st.error("无法获取交易对列表")
            st.session_state.scan_requested = False
            return
        
        # 显示扫描信息
        st.info(f"""
        🎯 **扫描配置**
        - 交易所: {exchange.upper()}
        - 计价货币: {quote}
        - 回测天数: {days}天
        - 扫描数量: {len(symbols)}个币种
        - 交易策略: {strategy}
        """)
        
        # 创建进度容器
        progress_container = st.container()
        status_container = st.container()
        results_container = st.empty()
        
        with progress_container:
            progress_bar = st.progress(0)
            status_text = st.empty()
        
        # 执行扫描
        results = []
        start_time = time.time()
        
        for i, symbol in enumerate(symbols):
            # 更新进度
            progress = (i + 1) / len(symbols)
            progress_bar.progress(progress)
            
            # 更新状态信息
            elapsed = time.time() - start_time
            speed = (i + 1) / elapsed if elapsed > 0 else 0
            remaining = (len(symbols) - i - 1) / speed if speed > 0 else 0
            
            with status_container:
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("进度", f"{progress:.1%}")
                with col2:
                    st.metric("速度", f"{speed:.1f}/秒")
                with col3:
                    st.metric("已处理", f"{i+1}/{len(symbols)}")
                with col4:
                    st.metric("剩余时间", f"{remaining:.0f}秒" if remaining > 0 else "计算中")
                
                st.caption(f"当前处理: `{symbol}`")
            
            # 执行回测
            result = scanner.simple_backtest(symbol, days=days)
            if result:
                results.append(result)
                
                # 实时显示最佳结果
                if results:
                    best = max(results, key=lambda x: x['total_return'])
                    with results_container:
                        st.success(f"🏆 当前最佳: **{best['symbol']}** - 收益: **{best['total_return']}%**")
            
            # 短暂延迟（避免API限制）
            if ccxt_available:
                time.sleep(0.1)  # 控制请求频率
        
        # 扫描完成
        st.session_state.scan_complete = True
        st.session_state.results = results
        
        st.balloons()
        st.success(f"✅ 扫描完成！成功分析 {len(results)} 个币种")
    
    # 显示结果
    if st.session_state.scan_complete and st.session_state.results:
        results = st.session_state.results
        
        # 结果概览
        st.markdown("### 📊 扫描结果概览")
        
        # 关键指标
        col1, col2, col3, col4 = st.columns(4)
        
        df = pd.DataFrame(results)
        avg_return = df['total_return'].mean()
        max_return = df['total_return'].max()
        positive_rate = (df['total_return'] > 0).sum() / len(df) * 100
        avg_sharpe = df['sharpe'].mean()
        
        with col1:
            st.metric("💰 平均收益", f"{avg_return:.1f}%")
        with col2:
            st.metric("🚀 最高收益", f"{max_return:.1f}%")
        with col3:
            st.metric("✅ 正收益比例", f"{positive_rate:.1f}%")
        with col4:
            st.metric("⚖️ 平均夏普", f"{avg_sharpe:.2f}")
        
        # 结果表格
        st.markdown("### 📋 详细结果")
        
        # 排序选项
        sort_by = st.selectbox(
            "排序方式",
            ['total_return', 'sharpe', 'win_rate', 'volatility'],
            format_func=lambda x: {
                'total_return': '总收益',
                'sharpe': '夏普比率',
                'win_rate': '胜率',
                'volatility': '波动率'
            }[x]
        )
        
        df_sorted = df.sort_values(sort_by, ascending=False)
        
        # 显示表格 - 使用简化版本，避免样式问题
        st.write(f"显示前 {min(20, len(df_sorted))} 个结果（共 {len(df_sorted)} 个）")
        
        # 创建简单的HTML表格
        display_df = df_sorted.head(20).copy()
        
        # 格式化数据
        def format_value(val, col_name):
            if col_name == 'total_return':
                color_class = "positive" if val > 0 else "negative"
                return f'<span class="{color_class}">{val:.1f}%</span>'
            elif col_name == 'sharpe':
                color_class = "positive" if val > 1 else "negative" if val < 0 else ""
                return f'<span class="{color_class}">{val:.2f}</span>'
            elif col_name in ['win_rate', 'volatility']:
                return f'{val:.1f}%'
            elif col_name in ['max_price', 'min_price']:
                return f'{val:.4f}'
            else:
                return str(val)
        
        # 创建HTML表格
        html_table = """
        <div class="dataframe-container">
            <table class="dataframe">
                <thead>
                    <tr>
                        <th>排名</th>
                        <th>交易对</th>
                        <th>总收益率</th>
                        <th>夏普比率</th>
                        <th>胜率</th>
                        <th>波动率</th>
                        <th>最大价格</th>
                        <th>最小价格</th>
                        <th>数据点数</th>
                    </tr>
                </thead>
                <tbody>
        """
        
        for i, (_, row) in enumerate(display_df.iterrows(), 1):
            html_table += f"""
                <tr>
                    <td>{i}</td>
                    <td><strong>{row['symbol']}</strong></td>
                    <td>{format_value(row['total_return'], 'total_return')}</td>
                    <td>{format_value(row['sharpe'], 'sharpe')}</td>
                    <td>{format_value(row['win_rate'], 'win_rate')}</td>
                    <td>{format_value(row['volatility'], 'volatility')}</td>
                    <td>{format_value(row['max_price'], 'max_price')}</td>
                    <td>{format_value(row['min_price'], 'min_price')}</td>
                    <td>{row['data_points']}</td>
                </tr>
            """
        
        html_table += """
                </tbody>
            </table>
        </div>
        """
        
        st.markdown(html_table, unsafe_allow_html=True)
        
        # 可视化 - 使用plotly或简化图表
        st.markdown("### 📈 可视化分析")
        
        try:
            import plotly.express as px
            
            tab1, tab2, tab3 = st.tabs(["收益分布", "风险收益分析", "排行榜"])
            
            with tab1:
                # 收益分布直方图
                fig1 = px.histogram(
                    df, 
                    x='total_return',
                    nbins=20,
                    title='收益率分布',
                    labels={'total_return': '收益率 (%)'},
                    color_discrete_sequence=['#1E88E5']
                )
                fig1.update_layout(
                    height=400,
                    showlegend=False,
                    bargap=0.1
                )
                st.plotly_chart(fig1, use_container_width=True)
            
            with tab2:
                # 风险收益散点图
                fig2 = px.scatter(
                    df,
                    x='volatility',
                    y='total_return',
                    size='sharpe',
                    color='sharpe',
                    hover_name='symbol',
                    title='风险收益分析',
                    labels={
                        'volatility': '波动率 (%)',
                        'total_return': '收益率 (%)',
                        'sharpe': '夏普比率'
                    },
                    color_continuous_scale='RdYlGn'
                )
                fig2.update_layout(height=500)
                st.plotly_chart(fig2, use_container_width=True)
            
            with tab3:
                # 排行榜
                top10 = df.nlargest(10, 'total_return')
                fig3 = px.bar(
                    top10,
                    x='symbol',
                    y='total_return',
                    title='收益率排行榜 (Top 10)',
                    labels={'total_return': '收益率 (%)', 'symbol': '交易对'},
                    color='total_return',
                    color_continuous_scale='RdYlGn'
                )
                fig3.update_layout(
                    height=400,
                    xaxis_tickangle=45
                )
                st.plotly_chart(fig3, use_container_width=True)
        
        except ImportError:
            # 如果plotly不可用，使用简化显示
            st.info("📊 图表功能需要安装plotly库")
            st.code("pip install plotly")
            
            # 显示文本统计
            st.markdown("#### 📊 文本分析")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("**收益分布统计**")
                st.write(f"- 平均收益: {avg_return:.1f}%")
                st.write(f"- 中位数收益: {df['total_return'].median():.1f}%")
                st.write(f"- 标准差: {df['total_return'].std():.1f}%")
                st.write(f"- 最大值: {df['total_return'].max():.1f}%")
                st.write(f"- 最小值: {df['total_return'].min():.1f}%")
            
            with col2:
                st.markdown("**风险指标统计**")
                st.write(f"- 平均夏普比率: {df['sharpe'].mean():.2f}")
                st.write(f"- 平均波动率: {df['volatility'].mean():.1f}%")
                st.write(f"- 平均胜率: {df['win_rate'].mean():.1f}%")
                st.write(f"- 正收益比例: {positive_rate:.1f}%")
        
        # 详细分析
        st.markdown("### 🔍 详细分析")
        
        selected_symbol = st.selectbox(
            "选择币种查看详细分析",
            df['symbol'].tolist()
        )
        
        if selected_symbol:
            coin_data = df[df['symbol'] == selected_symbol].iloc[0]
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("📈 总收益率", f"{coin_data['total_return']}%", 
                         delta="正收益" if coin_data['total_return'] > 0 else "负收益")
                st.metric("🎯 胜率", f"{coin_data['win_rate']}%")
            
            with col2:
                st.metric("⚖️ 夏普比率", f"{coin_data['sharpe']:.2f}",
                         delta="优秀" if coin_data['sharpe'] > 1.5 else "一般" if coin_data['sharpe'] > 0.5 else "较差")
                st.metric("🌀 波动率", f"{coin_data['volatility']}%")
            
            with col3:
                st.metric("💰 价格区间", 
                         f"{coin_data['min_price']:.4f} - {coin_data['max_price']:.4f}")
                st.metric("📊 数据质量", f"{coin_data['data_points']}个数据点")
        
        # 数据导出
        st.markdown("### 💾 数据导出")
        
        col1, col2 = st.columns(2)
        
        with col1:
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 下载CSV格式",
                data=csv,
                file_name=f"crypto_scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True,
                type="primary"
            )
        
        with col2:
            # 提供Excel格式下载选项
            try:
                import io
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False, sheet_name='扫描结果')
                    # 添加汇总表
                    summary_df = pd.DataFrame({
                        '指标': ['平均收益', '最高收益', '正收益比例', '平均夏普', '平均胜率', '平均波动率'],
                        '数值': [f"{avg_return:.1f}%", f"{max_return:.1f}%", 
                               f"{positive_rate:.1f}%", f"{avg_sharpe:.2f}",
                               f"{df['win_rate'].mean():.1f}%", f"{df['volatility'].mean():.1f}%"]
                    })
                    summary_df.to_excel(writer, index=False, sheet_name='汇总统计')
                
                excel_data = output.getvalue()
                st.download_button(
                    label="📊 下载Excel格式",
                    data=excel_data,
                    file_name=f"crypto_scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            except:
                # 如果openpyxl不可用，提供JSON格式
                json_str = df.to_json(orient='records', indent=2)
                st.download_button(
                    label="📄 下载JSON格式",
                    data=json_str,
                    file_name=f"crypto_scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json",
                    use_container_width=True
                )
    
    elif not st.session_state.scan_requested:
        # 欢迎页面
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.markdown("""
            ## 🎯 欢迎使用加密货币智能扫描器
            
            这是一个专业的加密货币市场分析工具，可以帮助您：
            
            ### ✨ 核心功能
            
            🔍 **智能扫描**
            - 全市场币种扫描
            - 多交易所支持
            - 实时数据获取
            
            📊 **深度分析**
            - 多策略回测
            - 风险收益评估
            - 绩效指标计算
            
            📈 **专业工具**
            - 可视化图表
            - 数据导出
            - 实时监控
            """)
        
        with col2:
            st.info("""
            ### 🚀 快速开始
            
            1. 在左侧配置扫描参数
            2. 点击"开始智能扫描"
            3. 查看分析结果
            4. 导出数据进一步分析
            """)
            
            if not ccxt_available:
                st.warning("""
                ⚠️ **当前为演示模式**
                
                如需实时数据，请安装：
                ```bash
                pip install ccxt pandas numpy plotly
                ```
                """)
        
        st.markdown("---")
        
        # 功能展示
        st.markdown("### 📊 功能展示")
        
        cols = st.columns(3)
        
        with cols[0]:
            st.markdown("""
            <div style='padding: 20px; border-radius: 10px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white;'>
                <h3>🎯 精准扫描</h3>
                <p>快速扫描全网币种，发现投资机会</p>
            </div>
            """, unsafe_allow_html=True)
        
        with cols[1]:
            st.markdown("""
            <div style='padding: 20px; border-radius: 10px; background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); color: white;'>
                <h3>📈 专业分析</h3>
                <p>多种技术指标，深度策略回测</p>
            </div>
            """, unsafe_allow_html=True)
        
        with cols[2]:
            st.markdown("""
            <div style='padding: 20px; border-radius: 10px; background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); color: white;'>
                <h3>💾 数据导出</h3>
                <p>支持多种格式，方便进一步分析</p>
            </div>
            """, unsafe_allow_html=True)
        
        # 技术指标说明
        with st.expander("📚 技术指标说明"):
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("""
                **📈 总收益率**
                - 策略在整个回测期间的总收益
                - 计算公式: (最终价值/初始价值 - 1) × 100%
                
                **⚖️ 夏普比率**
                - 衡量风险调整后的收益
                - 越高越好，>1为良好
                - 计算公式: (平均收益 - 无风险利率)/收益标准差
                
                **🎯 胜率**
                - 盈利交易占总交易次数的比例
                - 反映策略的稳定性
                """)
            
            with col2:
                st.markdown("""
                **🌀 波动率**
                - 价格变动的标准差
                - 衡量风险大小
                - 越低越稳定
                
                **💰 最大回撤**
                - 策略从峰值到谷值的最大跌幅
                - 反映最大风险
                - 越低越安全
                
                **📊 数据点数**
                - 使用的历史数据数量
                - 越多越可靠
                """)

if __name__ == "__main__":
    main()
