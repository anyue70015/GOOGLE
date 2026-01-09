import streamlit as st
import ccxt
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import warnings
warnings.filterwarnings('ignore')

# 设置页面配置
st.set_page_config(
    page_title="加密货币全量回测扫描器",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 自定义CSS样式
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1E88E5;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.5rem;
        font-weight: bold;
        color: #424242;
        margin-top: 1rem;
        margin-bottom: 0.5rem;
    }
    .metric-card {
        background-color: #f8f9fa;
        border-radius: 10px;
        padding: 15px;
        border-left: 4px solid #1E88E5;
        margin-bottom: 10px;
    }
    .stProgress > div > div > div > div {
        background-color: #1E88E5;
    }
    .scanning-status {
        padding: 10px;
        border-radius: 5px;
        margin: 10px 0;
    }
</style>
""", unsafe_allow_html=True)

class CryptoBacktestScanner:
    def __init__(self, exchange_id='binance', timeframe='1d'):
        """初始化扫描器"""
        try:
            self.exchange = getattr(ccxt, exchange_id)({
                'enableRateLimit': True,
                'options': {'defaultType': 'spot'}
            })
            self.timeframe = timeframe
            self.scan_results = []
        except Exception as e:
            st.error(f"交易所连接失败: {str(e)}")
            st.stop()
    
    def fetch_all_symbols(self, quote_currency='USDT'):
        """获取所有交易对"""
        try:
            self.exchange.load_markets()
            symbols = [symbol for symbol in self.exchange.symbols 
                      if symbol.endswith(f'/{quote_currency}')]
            return symbols
        except Exception as e:
            st.error(f"获取交易对失败: {str(e)}")
            return []
    
    def calculate_technical_indicators(self, df):
        """计算技术指标"""
        # 移动平均线
        df['sma_10'] = df['close'].rolling(10).mean()
        df['sma_20'] = df['close'].rolling(20).mean()
        df['sma_50'] = df['close'].rolling(50).mean()
        
        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # 布林带
        df['bb_middle'] = df['close'].rolling(20).mean()
        df['bb_std'] = df['close'].rolling(20).std()
        df['bb_upper'] = df['bb_middle'] + 2 * df['bb_std']
        df['bb_lower'] = df['bb_middle'] - 2 * df['bb_std']
        
        # MACD
        exp1 = df['close'].ewm(span=12, adjust=False).mean()
        exp2 = df['close'].ewm(span=26, adjust=False).mean()
        df['macd'] = exp1 - exp2
        df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        
        return df
    
    def backtest_strategy(self, symbol, days=365, initial_balance=10000):
        """回测策略"""
        try:
            # 获取历史数据
            since = self.exchange.parse8601(
                (datetime.now() - timedelta(days=days)).isoformat()
            )
            ohlcv = self.exchange.fetch_ohlcv(
                symbol, self.timeframe, since=since, limit=1000
            )
            
            if len(ohlcv) < 100:  # 数据太少
                return None, None
            
            # 创建DataFrame
            df = pd.DataFrame(
                ohlcv, 
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
            )
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            # 计算技术指标
            df = self.calculate_technical_indicators(df)
            
            # 双均线策略
            df['signal'] = 0
            df.loc[df['sma_10'] > df['sma_20'], 'signal'] = 1  # 买入信号
            df.loc[df['sma_10'] < df['sma_20'], 'signal'] = -1  # 卖出信号
            
            # RSI策略
            df['rsi_signal'] = 0
            df.loc[df['rsi'] < 30, 'rsi_signal'] = 1  # 超卖买入
            df.loc[df['rsi'] > 70, 'rsi_signal'] = -1  # 超卖卖出
            
            # 组合信号
            df['combined_signal'] = df['signal'] + df['rsi_signal']
            df['combined_signal'] = np.where(
                df['combined_signal'] > 0, 1,
                np.where(df['combined_signal'] < 0, -1, 0)
            )
            
            # 计算收益
            df['returns'] = df['close'].pct_change()
            df['strategy_returns'] = df['combined_signal'].shift(1) * df['returns']
            df['cumulative_returns'] = (1 + df['strategy_returns'].fillna(0)).cumprod()
            df['cumulative_benchmark'] = (1 + df['returns'].fillna(0)).cumprod()
            
            # 模拟交易
            balance = initial_balance
            position = 0
            trades = []
            
            for i in range(1, len(df)):
                signal = df['combined_signal'].iloc[i-1]
                price = df['close'].iloc[i]
                
                if signal == 1 and position == 0:  # 买入
                    position = balance / price
                    balance = 0
                    trades.append({
                        'timestamp': df['timestamp'].iloc[i],
                        'type': 'BUY',
                        'price': price,
                        'position': position
                    })
                elif signal == -1 and position > 0:  # 卖出
                    balance = position * price
                    trades.append({
                        'timestamp': df['timestamp'].iloc[i],
                        'type': 'SELL',
                        'price': price,
                        'position': position
                    })
                    position = 0
            
            # 最终结算
            if position > 0:
                final_price = df['close'].iloc[-1]
                balance = position * final_price
            
            # 计算绩效指标
            total_return = (balance / initial_balance - 1) * 100
            annual_return = (1 + total_return/100) ** (365/days) - 1
            
            strategy_returns = df['strategy_returns'].dropna()
            if len(strategy_returns) > 0:
                win_rate = (strategy_returns > 0).mean() * 100
                profit_factor = abs(strategy_returns[strategy_returns > 0].sum() / 
                                   strategy_returns[strategy_returns < 0].sum()) if strategy_returns[strategy_returns < 0].sum() != 0 else 99
            else:
                win_rate = 0
                profit_factor = 0
            
            # 最大回撤
            cumulative = df['cumulative_returns']
            peak = cumulative.expanding().max()
            drawdown = (cumulative - peak) / peak
            max_drawdown = drawdown.min() * 100
            
            # 夏普比率
            if strategy_returns.std() > 0:
                sharpe_ratio = (strategy_returns.mean() / strategy_returns.std()) * np.sqrt(252)
            else:
                sharpe_ratio = 0
            
            # 索提诺比率
            downside_returns = strategy_returns[strategy_returns < 0]
            if len(downside_returns) > 0 and downside_returns.std() > 0:
                sortino_ratio = (strategy_returns.mean() / downside_returns.std()) * np.sqrt(252)
            else:
                sortino_ratio = 0
            
            result = {
                'symbol': symbol,
                'total_return': round(total_return, 2),
                'annual_return': round(annual_return * 100, 2),
                'win_rate': round(win_rate, 2),
                'profit_factor': round(profit_factor, 2),
                'max_drawdown': round(max_drawdown, 2),
                'sharpe_ratio': round(sharpe_ratio, 2),
                'sortino_ratio': round(sortino_ratio, 2),
                'num_trades': len(trades),
                'data_points': len(df),
                'final_balance': round(balance, 2)
            }
            
            return result, df
            
        except Exception as e:
            st.error(f"处理 {symbol} 时出错: {str(e)[:100]}")
            return None, None

def create_performance_chart(df, symbol):
    """创建绩效图表"""
    fig = make_subplots(
        rows=3, cols=1,
        subplot_titles=('价格走势与交易信号', '累计收益对比', 'RSI指标'),
        vertical_spacing=0.1,
        row_heights=[0.5, 0.25, 0.25]
    )
    
    # 价格和信号
    fig.add_trace(
        go.Scatter(x=df['timestamp'], y=df['close'], 
                  name='价格', line=dict(color='blue')),
        row=1, col=1
    )
    
    # 买入信号
    buy_signals = df[df['combined_signal'].shift(1) == 1]
    fig.add_trace(
        go.Scatter(x=buy_signals['timestamp'], y=buy_signals['close'],
                  mode='markers', name='买入',
                  marker=dict(color='green', size=10, symbol='triangle-up')),
        row=1, col=1
    )
    
    # 卖出信号
    sell_signals = df[df['combined_signal'].shift(1) == -1]
    fig.add_trace(
        go.Scatter(x=sell_signals['timestamp'], y=sell_signals['close'],
                  mode='markers', name='卖出',
                  marker=dict(color='red', size=10, symbol='triangle-down')),
        row=1, col=1
    )
    
    # 累计收益
    fig.add_trace(
        go.Scatter(x=df['timestamp'], y=df['cumulative_returns'],
                  name='策略收益', line=dict(color='green')),
        row=2, col=1
    )
    fig.add_trace(
        go.Scatter(x=df['timestamp'], y=df['cumulative_benchmark'],
                  name='基准收益', line=dict(color='gray', dash='dash')),
        row=2, col=1
    )
    
    # RSI指标
    fig.add_trace(
        go.Scatter(x=df['timestamp'], y=df['rsi'],
                  name='RSI', line=dict(color='purple')),
        row=3, col=1
    )
    fig.add_hline(y=70, line_dash="dash", line_color="red", row=3, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", row=3, col=1)
    
    fig.update_layout(
        height=800,
        showlegend=True,
        title_text=f"{symbol} 回测分析"
    )
    
    return fig

def main():
    # 标题
    st.markdown('<div class="main-header">📊 加密货币全量回测扫描器</div>', 
                unsafe_allow_html=True)
    
    # 侧边栏配置
    with st.sidebar:
        st.header("⚙️ 扫描配置")
        
        # 交易所选择
        exchange_options = ['binance', 'okx', 'bybit', 'kucoin', 'gateio']
        selected_exchange = st.selectbox("选择交易所", exchange_options, index=0)
        
        # 计价货币
        quote_currency = st.selectbox("计价货币", 
                                      ['USDT', 'USD', 'BTC', 'ETH'], index=0)
        
        # 回测周期
        days = st.slider("回测周期（天）", 30, 730, 365, 30)
        
        # K线周期
        timeframe = st.selectbox("K线周期", 
                                 ['1d', '4h', '1h', '15m', '5m'], index=0)
        
        # 初始资金
        initial_balance = st.number_input("初始资金（USDT）", 
                                         min_value=1000, 
                                         max_value=1000000, 
                                         value=10000, 
                                         step=1000)
        
        # 扫描数量限制
        max_symbols = st.slider("最大扫描数量", 10, 500, 100, 10)
        
        # 开始扫描按钮
        start_scan = st.button("🚀 开始全量扫描", type="primary", use_container_width=True)
        
        st.divider()
        
        # 策略说明
        st.info("""
        **策略说明：**
        - 双均线策略 (SMA10/SMA20)
        - RSI超买超卖策略
        - 组合信号交易
        """)
    
    # 初始化会话状态
    if 'scan_results' not in st.session_state:
        st.session_state.scan_results = []
    if 'scanning' not in st.session_state:
        st.session_state.scanning = False
    if 'progress' not in st.session_state:
        st.session_state.progress = 0
    if 'scanner' not in st.session_state:
        st.session_state.scanner = None
    
    # 主界面
    col1, col2 = st.columns([3, 1])
    
    with col2:
        st.markdown('<div class="sub-header">📈 实时状态</div>', 
                    unsafe_allow_html=True)
        
        status_placeholder = st.empty()
        progress_placeholder = st.empty()
        metrics_placeholder = st.empty()
        
        if st.button("🛑 停止扫描", disabled=not st.session_state.scanning):
            st.session_state.scanning = False
            st.rerun()
    
    with col1:
        # 扫描进度显示区域
        scan_placeholder = st.empty()
        
        if start_scan and not st.session_state.scanning:
            st.session_state.scanning = True
            st.session_state.scan_results = []
            st.session_state.progress = 0
            
            # 创建扫描器实例
            st.session_state.scanner = CryptoBacktestScanner(
                exchange_id=selected_exchange,
                timeframe=timeframe
            )
            
            # 获取交易对
            all_symbols = st.session_state.scanner.fetch_all_symbols(quote_currency)
            if len(all_symbols) > max_symbols:
                scan_symbols = all_symbols[:max_symbols]
            else:
                scan_symbols = all_symbols
            
            # 显示扫描信息
            with scan_placeholder.container():
                st.info(f"🎯 开始扫描 {len(scan_symbols)} 个交易对...")
                
                # 进度条
                progress_bar = st.progress(0)
                
                # 实时信息
                info_col1, info_col2, info_col3 = st.columns(3)
                
                start_time = time.time()
                
                for i, symbol in enumerate(scan_symbols):
                    if not st.session_state.scanning:
                        break
                    
                    # 更新进度
                    progress = (i + 1) / len(scan_symbols)
                    progress_bar.progress(progress)
                    
                    with info_col1:
                        st.metric("当前币种", symbol)
                    with info_col2:
                        elapsed = time.time() - start_time
                        speed = (i + 1) / elapsed if elapsed > 0 else 0
                        st.metric("扫描速度", f"{speed:.1f} 币种/秒")
                    with info_col3:
                        remaining = (len(scan_symbols) - i - 1) / speed if speed > 0 else 0
                        st.metric("预计剩余", f"{remaining:.0f} 秒")
                    
                    # 执行回测
                    result, _ = st.session_state.scanner.backtest_strategy(
                        symbol, days=days, initial_balance=initial_balance
                    )
                    
                    if result:
                        st.session_state.scan_results.append(result)
                    
                    # 更新状态
                    with status_placeholder:
                        if st.session_state.scan_results:
                            best = max(st.session_state.scan_results, 
                                      key=lambda x: x['total_return'])
                            st.metric("🏆 最佳表现", 
                                     f"{best['symbol']}: {best['total_return']}%")
                    
                    # 强制刷新界面
                    time.sleep(0.01)  # 避免API限制
                
                # 扫描完成
                st.session_state.scanning = False
                st.success(f"✅ 扫描完成！共处理 {len(st.session_state.scan_results)} 个币种")
                st.rerun()
        
        # 显示扫描结果
        if st.session_state.scan_results and not st.session_state.scanning:
            st.markdown('<div class="sub-header">📋 扫描结果汇总</div>', 
                        unsafe_allow_html=True)
            
            # 创建结果DataFrame
            results_df = pd.DataFrame(st.session_state.scan_results)
            
            # 排序选项
            sort_by = st.selectbox("排序方式", [
                'total_return', 'annual_return', 'sharpe_ratio', 
                'win_rate', 'max_drawdown'
            ])
            
            # 排序和过滤
            results_df = results_df.sort_values(sort_by, ascending=False)
            
            # 显示表格
            st.dataframe(
                results_df.style
                .background_gradient(subset=['total_return'], cmap='RdYlGn')
                .background_gradient(subset=['sharpe_ratio'], cmap='RdYlGn')
                .format({
                    'total_return': '{:.2f}%',
                    'annual_return': '{:.2f}%',
                    'win_rate': '{:.2f}%',
                    'max_drawdown': '{:.2f}%'
                }),
                use_container_width=True,
                height=400
            )
            
            # 性能统计
            st.markdown('<div class="sub-header">📊 性能统计</div>', 
                        unsafe_allow_html=True)
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                avg_return = results_df['total_return'].mean()
                st.metric("平均收益率", f"{avg_return:.2f}%")
            
            with col2:
                avg_sharpe = results_df['sharpe_ratio'].mean()
                st.metric("平均夏普比率", f"{avg_sharpe:.2f}")
            
            with col3:
                positive_count = (results_df['total_return'] > 0).sum()
                positive_rate = positive_count / len(results_df) * 100
                st.metric("正收益比例", f"{positive_rate:.1f}%")
            
            with col4:
                avg_trades = results_df['num_trades'].mean()
                st.metric("平均交易次数", f"{avg_trades:.0f}")
            
            # 可视化图表
            st.markdown('<div class="sub-header">📈 可视化分析</div>', 
                        unsafe_allow_html=True)
            
            tab1, tab2, tab3 = st.tabs(["收益分布", "相关性分析", "详细分析"])
            
            with tab1:
                # 收益分布直方图
                fig = px.histogram(results_df, x='total_return', 
                                  nbins=30, 
                                  title="收益率分布",
                                  labels={'total_return': '收益率 (%)'})
                fig.update_layout(bargap=0.1)
                st.plotly_chart(fig, use_container_width=True)
            
            with tab2:
                # 相关性热力图
                numeric_cols = ['total_return', 'sharpe_ratio', 'win_rate', 
                               'max_drawdown', 'num_trades']
                corr_matrix = results_df[numeric_cols].corr()
                
                fig = px.imshow(corr_matrix,
                               labels=dict(color="相关系数"),
                               x=numeric_cols,
                               y=numeric_cols,
                               color_continuous_scale="RdBu_r",
                               text_auto=True)
                fig.update_layout(title="指标相关性热力图")
                st.plotly_chart(fig, use_container_width=True)
            
            with tab3:
                # 选择币种进行详细分析
                selected_symbol = st.selectbox(
                    "选择币种查看详细分析",
                    results_df['symbol'].tolist()
                )
                
                if selected_symbol and st.session_state.scanner:
                    # 获取详细数据
                    result, detailed_df = st.session_state.scanner.backtest_strategy(
                        selected_symbol, days=days, initial_balance=initial_balance
                    )
                    
                    if detailed_df is not None:
                        # 显示详细图表
                        fig = create_performance_chart(detailed_df, selected_symbol)
                        st.plotly_chart(fig, use_container_width=True)
                        
                        # 显示详细指标
                        st.markdown("#### 详细绩效指标")
                        detail_cols = st.columns(4)
                        
                        metrics = [
                            ("总收益率", f"{result['total_return']}%"),
                            ("年化收益率", f"{result['annual_return']}%"),
                            ("胜率", f"{result['win_rate']}%"),
                            ("盈利因子", f"{result['profit_factor']}"),
                            ("最大回撤", f"{result['max_drawdown']}%"),
                            ("夏普比率", f"{result['sharpe_ratio']}"),
                            ("索提诺比率", f"{result['sortino_ratio']}"),
                            ("交易次数", f"{result['num_trades']}")
                        ]
                        
                        for i, (label, value) in enumerate(metrics):
                            with detail_cols[i % 4]:
                                st.metric(label, value)
            
            # 下载结果
            st.markdown('<div class="sub-header">💾 数据导出</div>', 
                        unsafe_allow_html=True)
            
            csv = results_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 下载CSV结果",
                data=csv,
                file_name=f"crypto_scan_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True
            )
    
    # 底部信息
    st.divider()
    st.caption(f"📅 最后更新: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    main()
