#!/usr/bin/env python3
"""
调试A3策略的信号生成
"""
import pandas as pd
import numpy as np
from datetime import datetime
from strategies.a3_dual_ma_volume import A3DualMAVolumeStrategy
from strategies.indicators import calculate_moving_average

def create_test_data():
    """创建测试数据，确保产生均线交叉"""
    np.random.seed(42)
    periods = 100
    dates = pd.date_range('2024-10-01', periods=periods, freq='D')

    # 创建价格数据：确保在最后几根K线形成金叉
    base_price = 180
    prices = np.zeros(periods)

    # 大部分时间价格相对稳定
    prices[:periods-10] = base_price * (1 + np.random.normal(0, 0.02, periods-10))

    # 在最后10根K线制造金叉：先下降再上升
    cross_point = periods - 5
    prices[cross_point-5:cross_point] = base_price * (1 + np.linspace(-0.05, -0.08, 5))  # 下降
    prices[cross_point:] = base_price * (1 + np.linspace(-0.08, 0.05, 5))  # 上升形成金叉

    # 添加一些噪声
    noise = np.random.normal(0, 0.005, periods)
    prices *= (1 + noise)

    # 生成OHLCV
    high_mult = 1 + np.random.uniform(0, 0.01, periods)
    low_mult = 1 - np.random.uniform(0, 0.01, periods)

    # 成交量：在金叉点大幅放大
    volume_base = 50000000
    volumes = np.full(periods, volume_base * 0.5)  # 正常成交量
    volumes[cross_point:] = volume_base * 4.0  # 金叉点成交量大幅放大

    data = pd.DataFrame({
        'Open': prices * (1 + np.random.uniform(-0.002, 0.002, periods)),
        'High': prices * high_mult,
        'Low': prices * low_mult,
        'Close': prices,
        'Volume': volumes
    }, index=dates)

    # 确保数据有效性
    data['High'] = np.maximum(data['High'], data[['Open', 'Close']].max(axis=1))
    data['Low'] = np.minimum(data['Low'], data[['Open', 'Close']].min(axis=1))

    return data

def debug_a3_strategy():
    """调试A3策略"""
    print("🔬 调试A3策略信号生成")

    # 创建测试数据
    data = create_test_data()
    print(f"✅ 创建测试数据: {len(data)} 条记录")
    print(f"   价格范围: ${data['Close'].min():.2f} - ${data['Close'].max():.2f}")
    print(f"   成交量范围: {data['Volume'].min():.0f} - {data['Volume'].max():.0f}")

    # 计算均线
    fast_ma = calculate_moving_average(data['Close'], 9, 'EMA')
    slow_ma = calculate_moving_average(data['Close'], 21, 'EMA')

    print("\n📊 均线分析:")
    print(f"   快线(EMA9) 最新: {fast_ma.iloc[-1]:.2f}")
    print(f"   慢线(EMA21) 最新: {slow_ma.iloc[-1]:.2f}")

    # 检查交叉
    if len(fast_ma) >= 3 and len(slow_ma) >= 3:
        prev_fast = fast_ma.iloc[-2]
        prev_slow = slow_ma.iloc[-2]
        curr_fast = fast_ma.iloc[-1]
        curr_slow = slow_ma.iloc[-1]

        print(f"   前一根: 快线={prev_fast:.2f}, 慢线={prev_slow:.2f}")
        print(f"   当前: 快线={curr_fast:.2f}, 慢线={curr_slow:.2f}")

        bullish_cross = (prev_fast <= prev_slow) and (curr_fast > curr_slow)
        print(f"   金叉检测: {bullish_cross}")

    # 检查成交量
    current_volume = data['Volume'].iloc[-1]
    print(f"\n📊 成交量分析:")
    print(f"   当前成交量: {current_volume:.0f}")
    print(f"   最小成交量要求: 500000")

    volume_breakout = current_volume >= 500000
    print(f"   成交量满足要求: {volume_breakout}")

    # 创建策略实例并测试
    strategy = A3DualMAVolumeStrategy()
    signals = strategy.generate_signals('AAPL', data, {})

    print(f"\n🎯 信号生成结果: {len(signals)} 个信号")
    if signals:
        for i, signal in enumerate(signals, 1):
            print(f"   {i}. {signal.get('action')} - 置信度: {signal.get('confidence', 0):.2f}")
            print(f"      原因: {signal.get('reason', 'No reason')}")
    else:
        print("   📭 未生成信号")

        # 手动检查各个条件
        print("\n🔍 手动条件检查:")        # 1. 数据长度检查
        min_required = max(9, 21) + 5
        print(f"   数据长度: {len(data)} >= {min_required} ? {len(data) >= min_required}")

        # 2. 持仓检查
        print(f"   当前持仓: {strategy.positions}")

        # 3. 均线交叉检查
        if len(data) >= min_required:
            fast_ma_calc, slow_ma_calc = strategy.calculate_moving_averages(data)
            crossover_signal, confidence = strategy.detect_ma_crossover(data, fast_ma_calc, slow_ma_calc)
            print(f"   均线交叉信号: {crossover_signal}, 置信度: {confidence:.2f}")

            # 4. 价格位置检查
            current_price = data['Close'].iloc[-1]
            current_slow_ma = slow_ma_calc.iloc[-1]
            price_above_slow = current_price > current_slow_ma
            print(f"   价格在慢线上方: {current_price:.2f} > {current_slow_ma:.2f} ? {price_above_slow}")

            # 5. 成交量突破检查
            volume_breakout, volume_ratio = strategy.detect_volume_breakout(data)
            print(f"   成交量突破: {volume_breakout}, 比率: {volume_ratio:.2f}")
            print(f"   最后5根成交量: {data['Volume'].iloc[-5:].values}")
            print(f"   平均成交量: {volume_sma.iloc[-1]:.0f}")

            # 6. 最小成交量检查
            min_volume_ok = current_volume >= strategy.config['min_volume_threshold']
            print(f"   最小成交量: {current_volume:.0f} >= {strategy.config['min_volume_threshold']} ? {min_volume_ok}")

if __name__ == '__main__':
    debug_a3_strategy()