#!/usr/bin/env python3
"""
快速测试A12-A18策略的基本功能
"""
import pandas as pd
import numpy as np
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_realistic_test_data(symbol, periods=100):
    """创建更真实的测试数据"""
    np.random.seed(42)

    # 基于当前价格生成数据
    base_prices = {
        'AAPL': 180, 'MSFT': 400, 'GOOGL': 140, 'TSLA': 250, 'NVDA': 800
    }
    base_price = base_prices.get(symbol, 100)

    # 生成价格走势
    dates = pd.date_range('2024-11-01', periods=periods, freq='D')

    # 创建更现实的价格数据
    returns = np.random.normal(0.001, 0.02, periods)  # 每日平均1bp回报，2%波动
    prices = base_price * np.exp(np.cumsum(returns))

    # 生成OHLCV数据
    high_mult = 1 + np.random.uniform(0, 0.03, periods)
    low_mult = 1 - np.random.uniform(0, 0.03, periods)
    volume_base = {'AAPL': 50000000, 'MSFT': 30000000, 'GOOGL': 25000000, 'TSLA': 60000000, 'NVDA': 40000000}
    vol_base = volume_base.get(symbol, 10000000)

    data = pd.DataFrame({
        'Open': prices * (1 + np.random.uniform(-0.01, 0.01, periods)),
        'High': prices * high_mult,
        'Low': prices * low_mult,
        'Close': prices,
        'Volume': vol_base * np.random.uniform(0.5, 1.5, periods)
    }, index=dates)

    # 确保High >= Close >= Low >= 0
    data['High'] = np.maximum(data['High'], data[['Open', 'Close']].max(axis=1))
    data['Low'] = np.minimum(data['Low'], data[['Open', 'Close']].min(axis=1))
    data['Low'] = np.maximum(data['Low'], 0.01)  # 避免负数

    return data

def test_strategy_quick(strategy_name, strategy_class, symbol):
    """快速测试策略"""
    try:
        print(f"\n🔬 测试 {strategy_name} 对 {symbol}")

        # 创建策略实例
        strategy = strategy_class()

        # 创建测试数据
        data = create_realistic_test_data(symbol, 100)
        print(f"✅ 测试数据创建: {len(data)} 条记录, 价格范围: ${data['Close'].min():.2f} - ${data['Close'].max():.2f}")

        # 计算指标
        indicators = {}
        try:
            from strategies.indicators import calculate_atr
            indicators['ATR'] = calculate_atr(data['High'], data['Low'], data['Close']).iloc[-1]
        except:
            pass

        # 生成信号
        signals = strategy.generate_signals(symbol, data, indicators)

        print(f"🎯 生成信号数: {len(signals)}")

        # 显示信号
        if signals:
            for i, signal in enumerate(signals[:3], 1):  # 只显示前3个
                action = signal.get('action', 'UNKNOWN')
                signal_type = signal.get('signal_type', 'UNKNOWN')
                confidence = signal.get('confidence', 0)
                print(f"   {i}. {action} ({signal_type}) - 置信度: {confidence:.2f}")
            if len(signals) > 3:
                print(f"   ... 还有 {len(signals) - 3} 个信号")
        else:
            print("   📭 未生成信号")

        return len(signals) > 0

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("="*60)
    print("🚀 A12-A18策略快速功能测试")
    print("="*60)

    from strategies.a12_stochastic_rsi import A12StochasticRSIStrategy
    from strategies.a13_ema_crossover import A13EMACrossoverStrategy
    from strategies.a14_rsi_trendline import A14RSITrendlineStrategy
    from strategies.a15_pairs_trading import A15PairsTradingStrategy
    from strategies.a16_roc import A16ROCStrategy
    from strategies.a17_cci import A17CCIStrategy
    from strategies.a18_isolation_forest import A18IsolationForestStrategy

    strategies = [
        ("A12 Stochastic RSI", A12StochasticRSIStrategy),
        ("A13 EMA Crossover", A13EMACrossoverStrategy),
        ("A14 RSI Trendline", A14RSITrendlineStrategy),
        ("A15 Pairs Trading", A15PairsTradingStrategy),
        ("A16 ROC", A16ROCStrategy),
        ("A17 CCI", A17CCIStrategy),
        ("A18 Isolation Forest", A18IsolationForestStrategy),
    ]

    test_symbols = ['AAPL', 'MSFT', 'NVDA']
    results = []

    for symbol in test_symbols:
        print(f"\n{'='*50}")
        print(f"📈 测试股票: {symbol}")
        print('='*50)

        symbol_results = []
        for strategy_name, strategy_class in strategies:
            success = test_strategy_quick(strategy_name, strategy_class, symbol)
            symbol_results.append(success)

        successful = sum(symbol_results)
        print(f"\n📊 {symbol} 小结: {successful}/{len(strategies)} 策略成功")

        results.extend(symbol_results)

    # 总体统计
    total_success = sum(results)
    total_tests = len(results)

    print(f"\n{'='*60}")
    print("📊 总体测试结果")
    print('='*60)
    print(f"总测试数: {total_tests}")
    print(f"成功数: {total_success}")
    print(f"成功率: {total_success/total_tests*100:.1f}%")

    if total_success > 0:
        print("✅ A12-A18策略具有信号生成能力！")
    else:
        print("❌ 所有策略都未生成信号，可能需要调整参数")

if __name__ == '__main__':
    main()</content>
</xai:function_call">{"path":"Test/quick_test_a12_a18.py","operation":"created","notice":"You do not need to re-read the file, as you have seen all changes Proceed with the task using these changes as the new baseline."}  
<xai:function_call name="execute_command">
<parameter name="command">cd /Users/wangxufeng/AutoTrader && python Test/quick_test_a12_a18.py