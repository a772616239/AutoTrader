#!/usr/bin/env python3
"""
测试新移植的量化策略 (A12-A14)
验证策略是否能正常生成信号
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from strategies import A12StochasticRSIStrategy, A13EMACrossoverStrategy, A14RSITrendlineStrategy

def create_test_data(symbol='AAPL', periods=300):
    """创建测试用的股票数据"""
    np.random.seed(42)  # 固定随机种子以获得可重复的结果

    # 生成日期索引
    end_date = datetime.now()
    start_date = end_date - timedelta(days=periods)
    dates = pd.date_range(start=start_date, end=end_date, freq='D')

    # 生成价格数据 (模拟股票价格走势)
    base_price = 150.0
    price_changes = np.random.normal(0.001, 0.02, len(dates))  # 每天1%均值，2%标准差的变化
    prices = base_price * np.exp(np.cumsum(price_changes))

    # 生成成交量数据
    volumes = np.random.normal(1000000, 200000, len(dates))
    volumes = np.maximum(volumes, 10000)  # 确保最小成交量

    # 生成OHLC数据
    highs = prices * (1 + np.abs(np.random.normal(0, 0.01, len(dates))))
    lows = prices * (1 - np.abs(np.random.normal(0, 0.01, len(dates))))
    opens = prices * (1 + np.random.normal(0, 0.005, len(dates)))

    # 创建DataFrame
    df = pd.DataFrame({
        'Open': opens,
        'High': highs,
        'Low': lows,
        'Close': prices,
        'Volume': volumes
    }, index=dates)

    return df

def test_strategy(strategy_class, strategy_name, symbol='AAPL'):
    """测试单个策略"""
    print(f"\n{'='*50}")
    print(f"测试策略: {strategy_name}")
    print(f"{'='*50}")

    # 创建测试数据
    test_data = create_test_data(symbol, periods=300)
    print(f"测试数据: {len(test_data)} 条记录, 时间范围: {test_data.index[0].date()} 到 {test_data.index[-1].date()}")

    # 初始化策略
    try:
        strategy = strategy_class()
        print(f"✅ 策略初始化成功")
        print(f"   策略名称: {strategy.get_strategy_name()}")
        print(f"   配置参数: {len(strategy.config)} 项")
    except Exception as e:
        print(f"❌ 策略初始化失败: {e}")
        return False

    # 测试信号生成
    try:
        # 计算技术指标 (模拟)
        indicators = {
            'ATR': test_data['Close'].iloc[-1] * 0.02,  # 2%的ATR
            'RSI': 50.0,
            'MACD': 0.0
        }

        signals = strategy.generate_signals(symbol, test_data, indicators)
        print(f"✅ 信号生成成功")
        print(f"   生成信号数量: {len(signals)}")

        if signals:
            print("   信号详情:")
            for i, signal in enumerate(signals, 1):
                print(f"     {i}. {signal['action']} {signal['symbol']} @ ${signal['price']:.2f} "
                      f"(置信度: {signal['confidence']:.2f})")
                print(f"        原因: {signal['reason']}")
        else:
            print("   ℹ️  没有生成交易信号 (可能是因为市场条件不符合策略要求)")

    except Exception as e:
        print(f"❌ 信号生成失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    # 测试退出条件 (如果有持仓)
    try:
        if hasattr(strategy, 'positions') and symbol in strategy.positions:
            current_price = test_data['Close'].iloc[-1]
            exit_signal = strategy.check_exit_conditions(symbol, current_price)
            if exit_signal:
                print(f"✅ 退出条件检查成功")
                print(f"   退出信号: {exit_signal['action']} (原因: {exit_signal['reason']})")
            else:
                print("   ℹ️  没有触发退出条件")
        else:
            print("   ℹ️  没有持仓，跳过退出条件测试")
    except Exception as e:
        print(f"❌ 退出条件检查失败: {e}")
        return False

    return True

def main():
    """主测试函数"""
    print("🚀 开始测试新移植的量化策略")
    print("测试策略: A12 (Stochastic RSI), A13 (EMA交叉), A14 (RSI趋势线)")

    strategies_to_test = [
        (A12StochasticRSIStrategy, "A12 Stochastic RSI"),
        (A13EMACrossoverStrategy, "A13 EMA交叉"),
        (A14RSITrendlineStrategy, "A14 RSI趋势线")
    ]

    results = []
    for strategy_class, strategy_name in strategies_to_test:
        success = test_strategy(strategy_class, strategy_name)
        results.append((strategy_name, success))

    # 总结测试结果
    print(f"\n{'='*50}")
    print("测试结果总结")
    print(f"{'='*50}")

    all_passed = True
    for strategy_name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"{strategy_name}: {status}")
        if not success:
            all_passed = False

    print(f"\n总体结果: {'✅ 所有测试通过' if all_passed else '❌ 部分测试失败'}")

    if all_passed:
        print("\n🎉 恭喜！所有新移植的策略都可以正常工作。")
        print("您现在可以使用这些策略进行交易:")
        print("  python main.py --strategy a12  # Stochastic RSI策略")
        print("  python main.py --strategy a13  # EMA交叉策略")
        print("  python main.py --strategy a14  # RSI趋势线策略")
    else:
        print("\n⚠️  请检查失败的策略并修复问题后再使用。")

if __name__ == "__main__":
    main()