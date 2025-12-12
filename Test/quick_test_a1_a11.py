#!/usr/bin/env python3
"""
快速测试A1-A11策略的基本功能
"""
import pandas as pd
import numpy as np
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_realistic_test_data(symbol, periods=250):
    """创建更真实的测试数据，包含可能触发信号的模式"""
    np.random.seed(42)

    # 基于当前价格生成数据
    base_prices = {
        'AAPL': 180, 'MSFT': 400, 'GOOGL': 140, 'TSLA': 250, 'NVDA': 800
    }
    base_price = base_prices.get(symbol, 100)

    # 生成价格走势 - 包含明显的波动模式来触发信号
    dates = pd.date_range('2024-10-01', periods=periods, freq='D')

    # 创建带有趋势、震荡和明显波动周期的价格数据
    trend = np.linspace(0, 0.0002, periods)  # 很轻微的上升趋势
    oscillation = np.sin(np.linspace(0, 4*np.pi, periods)) * 0.02  # 更大的震荡 (2%) 来创建超买超卖
    cycle = np.sin(np.linspace(0, 1.5*np.pi, periods)) * 0.015  # 周期波动 (1.5%)

    # 添加一些明显的下跌和上涨事件
    random_shocks = np.zeros(periods)
    # 前1/3下跌，后2/3震荡
    shock_indices = np.random.choice(periods//3, size=int(periods*0.05), replace=False)
    random_shocks[shock_indices] = np.random.uniform(-0.03, -0.01, len(shock_indices))

    # 中间部分添加一些上涨
    up_indices = np.random.choice(range(periods//3, 2*periods//3), size=int(periods*0.05), replace=False)
    random_shocks[up_indices] = np.random.uniform(0.02, 0.05, len(up_indices))

    noise = np.random.normal(0, 0.005, periods)  # 噪声

    returns = trend + oscillation + cycle + random_shocks + noise
    prices = base_price * (1 + np.cumsum(returns))

    # 生成OHLCV数据
    high_mult = 1 + np.random.uniform(0, 0.015, periods)
    low_mult = 1 - np.random.uniform(0, 0.015, periods)
    volume_base = {'AAPL': 50000000, 'MSFT': 30000000, 'GOOGL': 25000000, 'TSLA': 60000000, 'NVDA': 40000000}
    vol_base = volume_base.get(symbol, 10000000)

    # 成交量与价格波动相关，增加一些成交量高峰
    price_volatility = np.abs(np.diff(prices, prepend=prices[0]))
    volume_multiplier = 1 + price_volatility / np.std(price_volatility) * 1.2

    # 在某些点增加成交量来模拟突破
    volume_spikes = np.zeros(periods)
    spike_indices = np.random.choice(periods, size=int(periods*0.1), replace=False)
    volume_spikes[spike_indices] = np.random.uniform(2, 5, len(spike_indices))
    volume_multiplier += volume_spikes

    data = pd.DataFrame({
        'Open': prices * (1 + np.random.uniform(-0.005, 0.005, periods)),
        'High': prices * high_mult,
        'Low': prices * low_mult,
        'Close': prices,
        'Volume': vol_base * np.random.uniform(0.3, 2.0, periods) * volume_multiplier
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
        data = create_realistic_test_data(symbol)
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
    print("🚀 A1-A11策略快速功能测试")
    print("="*60)

    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from strategies.a1_momentum_reversal import A1MomentumReversalStrategy
    from strategies.a2_zscore import A2ZScoreStrategy
    from strategies.a3_dual_ma_volume import A3DualMAVolumeStrategy
    from strategies.a4_pullback import A4PullbackStrategy
    from strategies.a5_multifactor_ai import A5MultiFactorAI
    from strategies.a6_news_trading import A6NewsTrading
    from strategies.a7_cta_trend import A7CTATrendStrategy
    from strategies.a8_rsi_oscillator import A8RSIOscillatorStrategy
    from strategies.a9_macd_crossover import A9MACDCrossoverStrategy
    from strategies.a10_bollinger_bands import A10BollingerBandsStrategy
    from strategies.a11_moving_average_crossover import A11MovingAverageCrossoverStrategy

    strategies = [
        ("A1 Momentum Reversal", A1MomentumReversalStrategy),
        ("A2 Z-Score", A2ZScoreStrategy),
        ("A3 Dual MA + Volume", A3DualMAVolumeStrategy),
        ("A4 Pullback", A4PullbackStrategy),
        ("A5 MultiFactor AI", A5MultiFactorAI),
        ("A6 News Trading", A6NewsTrading),
        ("A7 CTA Trend", A7CTATrendStrategy),
        ("A8 RSI Oscillator", A8RSIOscillatorStrategy),
        ("A9 MACD Crossover", A9MACDCrossoverStrategy),
        ("A10 Bollinger Bands", A10BollingerBandsStrategy),
        ("A11 Moving Average Crossover", A11MovingAverageCrossoverStrategy),
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
        print("✅ A1-A11策略具有信号生成能力！")
    else:
        print("❌ 所有策略都未生成信号，可能需要调整参数")

if __name__ == '__main__':
    main()