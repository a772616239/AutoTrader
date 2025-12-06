#!/usr/bin/env python3
"""
验证所有策略都实现了 generate_signals 方法
"""
import pandas as pd
import numpy as np
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_test_data(periods=50):
    """创建测试数据"""
    dates = pd.date_range('2025-01-01', periods=periods, freq='5min')
    np.random.seed(42)
    close = np.random.uniform(100, 110, periods)
    close = np.cumsum(np.random.randn(periods) * 0.5) + 100  # 更现实的价格走势
    
    data = pd.DataFrame({
        'Open': close + np.random.uniform(-0.5, 0.5, periods),
        'High': close + np.random.uniform(0, 2, periods),
        'Low': close - np.random.uniform(0, 2, periods),
        'Close': close,
        'Volume': np.random.uniform(1000000, 3000000, periods),
    }, index=dates)
    
    return data

def test_strategy(strategy_name, strategy_class):
    """测试单个策略"""
    try:
        print(f"\n{'='*60}")
        print(f"测试策略: {strategy_name}")
        print(f"{'='*60}")
        
        # 创建策略实例
        strategy = strategy_class()
        print(f"✅ 策略加载成功: {strategy.get_strategy_name()}")
        
        # 创建测试数据
        data = create_test_data(50)
        print(f"✅ 测试数据创建成功: {len(data)} 条记录")
        
        # 测试 generate_signals 方法
        indicators = {}
        signals = strategy.generate_signals('TEST', data, indicators)
        print(f"✅ generate_signals 执行成功，生成信号数: {len(signals)}")
        
        # 显示生成的信号
        if signals:
            for i, signal in enumerate(signals, 1):
                print(f"   信号 {i}: {signal.get('signal_type')} - {signal.get('action')}")
        else:
            print("   (未生成信号)")
        
        print(f"✅ {strategy_name} 测试通过！")
        return True
        
    except Exception as e:
        print(f"❌ {strategy_name} 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主测试函数"""
    print("\n" + "="*60)
    print("AutoTrader 策略测试套件")
    print("="*60)
    
    from strategies.a1_momentum_reversal import A1MomentumReversalStrategy
    from strategies.a2_zscore import A2ZScoreStrategy
    from strategies.a3_dual_ma_volume import A3DualMAVolumeStrategy
    
    strategies = [
        ("A1 Momentum Reversal", A1MomentumReversalStrategy),
        ("A2 Z-Score", A2ZScoreStrategy),
        ("A3 Dual MA + Volume", A3DualMAVolumeStrategy),
    ]
    
    results = []
    for name, strategy_class in strategies:
        results.append(test_strategy(name, strategy_class))
    
    # 总结
    print(f"\n{'='*60}")
    print("测试总结")
    print(f"{'='*60}")
    passed = sum(results)
    total = len(results)
    print(f"通过: {passed}/{total}")
    
    if passed == total:
        print("✅ 所有策略测试通过！系统已准备好运行。")
        return 0
    else:
        print("❌ 部分策略测试失败，请检查日志。")
        return 1

if __name__ == '__main__':
    exit(main())
