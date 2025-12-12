#!/usr/bin/env python3
"""
全面信号触发测试：确保A1-A11策略在适当条件下能生成信号
"""
import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_signal_triggering_data(symbol, strategy_name, periods=250):
    """为特定策略创建能触发信号的测试数据"""
    np.random.seed(42)

    base_prices = {
        'AAPL': 180, 'MSFT': 400, 'GOOGL': 140, 'TSLA': 250, 'NVDA': 800
    }
    base_price = base_prices.get(symbol, 100)

    dates = pd.date_range('2024-10-01', periods=periods, freq='D')

    if strategy_name == 'A1 Momentum Reversal':
        # 创建适合A1策略的条件：RSI适中，价格偏离MA20
        trend = np.linspace(0, 0.002, periods)  # 适中的上升趋势
        oscillation = 0.03 * np.sin(np.linspace(0, 6*np.pi, periods))  # 中等震荡
        cycle = 0.02 * np.sin(np.linspace(0, 3*np.pi, periods))

        # 添加价格偏离事件（模拟早盘动量）
        shocks = np.zeros(periods)
        momentum_indices = np.random.choice(range(periods//4, 3*periods//4), size=6, replace=False)
        shocks[momentum_indices] = np.random.uniform(0.05, 0.08, len(momentum_indices))  # 上涨动量

    elif strategy_name == 'A2 Z-Score':
        # 创建均值回归条件 - 更强的偏离
        trend = np.zeros(periods)
        oscillation = 0.15 * np.sin(np.linspace(0, 6*np.pi, periods))  # 更大幅度震荡
        cycle = 0.08 * np.sin(np.linspace(0, 3*np.pi, periods))

        # 添加更极端的偏离事件
        shocks = np.zeros(periods)
        extreme_indices = np.random.choice(range(periods//4, periods), size=6, replace=False)
        shocks[extreme_indices] = np.random.choice([-0.25, 0.25], len(extreme_indices))  # 更大的偏离

    elif strategy_name == 'A3 Dual MA + Volume':
        # 创建均线交叉条件 - 确保快线(9)和慢线(21)的金叉
        # 使用确定性的模式：前半部分下降，后半部分上升
        trend = np.zeros(periods)
        mid_point = periods // 2

        # 前半部分：轻微下降，让快线在慢线下方
        trend[:mid_point] = np.linspace(0, -0.01, mid_point)

        # 后半部分：温和上升，形成金叉
        trend[mid_point:] = np.linspace(-0.01, 0.03, periods - mid_point)

        oscillation = 0.015 * np.sin(np.linspace(0, 6*np.pi, periods))
        cycle = 0.01 * np.sin(np.linspace(0, 2.5*np.pi, periods))

        # 在后半部分添加成交量放大
        shocks = np.zeros(periods)
        shocks[mid_point:] = np.linspace(0.02, 0.06, periods - mid_point)  # 逐渐放大

    elif strategy_name == 'A4 Pullback':
        # 创建更强的回撤条件
        trend = np.linspace(0, 0.015, periods)  # 更强的上升趋势
        oscillation = 0.06 * np.sin(np.linspace(0, 3*np.pi, periods))  # 更大的震荡
        cycle = 0.04 * np.sin(np.linspace(0, 1.5*np.pi, periods))

        # 添加更明显的回撤事件
        shocks = np.zeros(periods)
        pullback_indices = np.random.choice(range(periods//3, 2*periods//3), size=3, replace=False)
        shocks[pullback_indices] = np.random.uniform(-0.12, -0.08, len(pullback_indices))  # 更大的回撤

    elif strategy_name == 'A5 MultiFactor AI':
        # 创建更好的多因子条件
        trend = np.linspace(0, 0.003, periods)  # 更强的上升趋势
        oscillation = 0.045 * np.sin(np.linspace(0, 5*np.pi, periods))  # 更大的震荡
        cycle = 0.035 * np.sin(np.linspace(0, 2.5*np.pi, periods))

        # 添加更多积极的因子事件
        shocks = np.zeros(periods)
        factor_indices = np.random.choice(range(periods//2, periods), size=8, replace=False)
        shocks[factor_indices] = np.random.uniform(0.02, 0.06, len(factor_indices))  # 更多的上涨事件

    elif strategy_name == 'A7 CTA Trend':
        # 创建更明显的趋势突破条件
        trend = np.linspace(0, 0.008, periods)  # 更强的上升趋势
        oscillation = 0.03 * np.sin(np.linspace(0, 3*np.pi, periods))
        cycle = 0.025 * np.sin(np.linspace(0, 1.8*np.pi, periods))

        # 添加更强的突破事件
        shocks = np.zeros(periods)
        trend_breakout_indices = np.random.choice(range(3*periods//4, periods), size=3, replace=False)
        shocks[trend_breakout_indices] = np.random.uniform(0.12, 0.18, len(trend_breakout_indices))  # 更大的突破

    elif strategy_name == 'A8 RSI Oscillator':
        # 创建RSI超买超卖条件
        trend = np.linspace(0, 0.001, periods)
        oscillation = 0.06 * np.sin(np.linspace(0, 10*np.pi, periods))  # 非常强的震荡
        cycle = 0.03 * np.sin(np.linspace(0, 4*np.pi, periods))

        # 添加极端RSI事件
        shocks = np.zeros(periods)
        extreme_rsi_indices = np.random.choice(periods, size=10, replace=False)
        shocks[extreme_rsi_indices] = np.random.choice([-0.12, 0.12], len(extreme_rsi_indices))

    elif strategy_name == 'A9 MACD Crossover':
        # 创建MACD交叉条件 - 产生金叉信号
        # 前半部分震荡，后半部分上涨形成金叉
        trend = np.zeros(periods)
        mid_point = periods // 2

        # 前半部分：震荡
        trend[:mid_point] = np.random.normal(0, 0.001, mid_point)

        # 后半部分：上涨趋势，制造MACD金叉
        trend[mid_point:] = np.linspace(0, 0.01, periods - mid_point)

        oscillation = 0.04 * np.sin(np.linspace(0, 8*np.pi, periods))
        cycle = 0.03 * np.sin(np.linspace(0, 4*np.pi, periods))

        # 添加动量事件
        shocks = np.zeros(periods)
        momentum_indices = np.random.choice(range(mid_point, periods), size=8, replace=False)
        shocks[momentum_indices] = np.random.uniform(0.02, 0.06, len(momentum_indices))

    elif strategy_name == 'A10 Bollinger Bands':
        # 创建布林带条件 - 产生上轨突破
        # 稳定的趋势 + 强震荡 + 明确的突破事件
        trend = np.linspace(0, 0.002, periods)  # 稳定上涨趋势
        oscillation = 0.08 * np.sin(np.linspace(0, 12*np.pi, periods))  # 更强震荡
        cycle = 0.05 * np.sin(np.linspace(0, 6*np.pi, periods))

        # 添加突破布林带上轨的事件 - 在最后几根K线，确保突破发生
        shocks = np.zeros(periods)
        # 在最后8根K线中添加逐渐增大的突破事件，确保突破上轨
        shocks[periods-8] = 0.08  # 第243根K线
        shocks[periods-7] = 0.12  # 第244根K线
        shocks[periods-6] = 0.16  # 第245根K线
        shocks[periods-5] = 0.20  # 第246根K线
        shocks[periods-4] = 0.25  # 第247根K线
        shocks[periods-3] = 0.30  # 第248根K线
        shocks[periods-2] = 0.35  # 第249根K线
        shocks[periods-1] = 0.40  # 第250根K线（最后1根）

    elif strategy_name == 'A11 Moving Average Crossover':
        # 创建均线交叉条件 - 产生金叉信号
        # 前半部分震荡，后半部分快速上涨形成均线金叉
        trend = np.zeros(periods)
        mid_point = periods // 2

        # 前半部分：轻微震荡，让快线在慢线下方
        trend[:mid_point] = np.random.normal(0, 0.0005, mid_point)

        # 后半部分：快速上涨，形成均线金叉
        trend[mid_point:] = np.linspace(0, 0.012, periods - mid_point)

        oscillation = 0.03 * np.sin(np.linspace(0, 8*np.pi, periods))
        cycle = 0.025 * np.sin(np.linspace(0, 4*np.pi, periods))

        # 添加更强的交叉事件，确保最后几根K线产生金叉
        shocks = np.zeros(periods)
        # 在最后几根K线添加更强的上涨事件，确保快线上穿慢线
        shocks[periods-5] = 0.10  # 第246根K线
        shocks[periods-4] = 0.15  # 第247根K线
        shocks[periods-3] = 0.20  # 第248根K线
        shocks[periods-2] = 0.25  # 第249根K线
        shocks[periods-1] = 0.30  # 第250根K线（最后1根）

    else:
        # 默认数据生成
        trend = np.linspace(0, 0.0002, periods)
        oscillation = np.sin(np.linspace(0, 4*np.pi, periods)) * 0.02
        cycle = np.sin(np.linspace(0, 1.5*np.pi, periods)) * 0.015
        shocks = np.random.normal(0, 0.005, periods)

    noise = np.random.normal(0, 0.003, periods)
    returns = trend + oscillation + cycle + shocks + noise
    prices = base_price * (1 + np.cumsum(returns))

    # 生成OHLCV数据
    high_mult = 1 + np.random.uniform(0, 0.01, periods)
    low_mult = 1 - np.random.uniform(0, 0.01, periods)
    volume_base = {'AAPL': 50000000, 'MSFT': 30000000, 'GOOGL': 25000000, 'TSLA': 60000000, 'NVDA': 40000000}
    vol_base = volume_base.get(symbol, 10000000)

    # 成交量与波动相关
    price_volatility = np.abs(np.diff(prices, prepend=prices[0]))
    volume_multiplier = 1 + price_volatility / np.std(price_volatility) * 1.5

    # 添加成交量高峰 - 特别在金叉点放大成交量
    volume_spikes = np.zeros(periods)
    spike_indices = np.random.choice(periods, size=int(periods*0.08), replace=False)
    volume_spikes[spike_indices] = np.random.uniform(3, 6, len(spike_indices))

    # 为A3策略特别添加金叉点成交量突破
    if strategy_name == 'A3 Dual MA + Volume':
        cross_point = periods - 5
        volume_spikes[cross_point:] = np.random.uniform(8, 12, 5)  # 金叉点大幅放大成交量

    volume_multiplier += volume_spikes

    data = pd.DataFrame({
        'Open': prices * (1 + np.random.uniform(-0.003, 0.003, periods)),
        'High': prices * high_mult,
        'Low': prices * low_mult,
        'Close': prices,
        'Volume': vol_base * np.random.uniform(0.5, 2.5, periods) * volume_multiplier
    }, index=dates)

    # 确保数据有效性
    data['High'] = np.maximum(data['High'], data[['Open', 'Close']].max(axis=1))
    data['Low'] = np.minimum(data['Low'], data[['Open', 'Close']].min(axis=1))
    data['Low'] = np.maximum(data['Low'], 0.01)

    return data

def test_strategy_comprehensive(strategy_name, strategy_class, symbol):
    """全面测试策略信号生成"""
    try:
        print(f"\n🔬 全面测试 {strategy_name} 对 {symbol}")

        # 创建策略实例
        try:
            strategy = strategy_class()
        except Exception as e:
            print(f"❌ 策略实例化失败: {e}")
            return False

        # 为特定策略创建触发信号的数据
        data = create_signal_triggering_data(symbol, strategy_name)
        print(f"✅ 信号触发数据创建: {len(data)} 条记录, 价格范围: ${data['Close'].min():.2f} - ${data['Close'].max():.2f}")

        # 计算指标
        indicators = {}
        try:
            from strategies.indicators import calculate_atr, calculate_rsi, calculate_moving_average

            # ATR
            indicators['ATR'] = calculate_atr(data['High'], data['Low'], data['Close']).iloc[-1]

            # RSI (A1, A8等策略需要)
            indicators['RSI'] = calculate_rsi(data['Close'], period=14).iloc[-1]

            # MA20 (A1策略需要)
            indicators['MA_20'] = calculate_moving_average(data['Close'], 20, 'SMA').iloc[-1]

            # 其他常用指标
            indicators['MA_10'] = calculate_moving_average(data['Close'], 10, 'SMA').iloc[-1]
            indicators['MA_50'] = calculate_moving_average(data['Close'], 50, 'SMA').iloc[-1]

        except Exception as e:
            logger.warning(f"指标计算失败: {e}")
            pass

        # 生成信号
        signals = strategy.generate_signals(symbol, data, indicators)

        print(f"🎯 生成信号数: {len(signals)}")

        # 显示信号详情
        if signals:
            for i, signal in enumerate(signals[:5], 1):  # 显示前5个
                action = signal.get('action', 'UNKNOWN')
                signal_type = signal.get('signal_type', 'UNKNOWN')
                confidence = signal.get('confidence', 0)
                reason = signal.get('reason', 'No reason provided')
                print(f"   {i}. {action} ({signal_type}) - 置信度: {confidence:.2f}")
                print(f"      原因: {reason}")
            if len(signals) > 5:
                print(f"   ... 还有 {len(signals) - 5} 个信号")
        else:
            print("   📭 未生成信号")

        return len(signals) > 0

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主测试函数"""
    print("="*70)
    print("🚀 A1-A11策略全面信号触发测试")
    print("="*70)

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
    detailed_results = {}

    for symbol in test_symbols:
        print(f"\n{'='*60}")
        print(f"📈 全面测试股票: {symbol}")
        print('='*60)

        symbol_results = []
        symbol_details = {}

        for strategy_name, strategy_class in strategies:
            success = test_strategy_comprehensive(strategy_name, strategy_class, symbol)
            symbol_results.append(success)
            symbol_details[strategy_name] = success

        successful = sum(symbol_results)
        print(f"\n📊 {symbol} 小结: {successful}/{len(strategies)} 策略成功")

        results.extend(symbol_results)
        detailed_results[symbol] = symbol_details

    # 总体统计
    print(f"\n{'='*70}")
    print("📊 总体测试结果")
    print('='*70)
    print(f"总测试数: {len(results)}")
    print(f"成功数: {sum(results)}")
    print(f"成功率: {sum(results)/len(results)*100:.1f}%")

    # 策略级别统计
    print(f"\n{'='*70}")
    print("📊 策略级别成功统计")
    print('='*70)

    strategy_success_count = {}
    for strategy_name, _ in strategies:
        strategy_success_count[strategy_name] = 0

    for symbol, details in detailed_results.items():
        for strategy_name, success in details.items():
            if success:
                strategy_success_count[strategy_name] += 1

    for strategy_name, count in strategy_success_count.items():
        status = "✅ 正常" if count > 0 else "❌ 无信号"
        print(f"{strategy_name}: {status} ({count}/3 股票成功)")

    if sum(results) > 0:
        print("\n✅ A1-A11策略信号触发测试完成！")
    else:
        print("\n❌ 所有策略都未生成信号，可能需要调整测试数据或策略参数")
if __name__ == '__main__':
    main()