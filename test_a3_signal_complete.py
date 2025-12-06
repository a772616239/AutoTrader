#!/usr/bin/env python3
"""
测试 A3 策略信号完整性 - 验证 position_size 和 signal_hash
"""

import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from strategies.a3_dual_ma_volume import A3DualMAVolumeStrategy

def create_test_data(periods=50):
    """创建测试数据 - 模拟带有明显均线交叉的市场"""
    np.random.seed(42)
    dates = pd.date_range('2025-01-01 10:00', periods=periods, freq='5min')
    
    # 生成价格数据 - 创建一个上升趋势
    base_price = 100
    trend = np.linspace(0, 2, periods)  # 持续上升
    close = base_price + trend + np.random.randn(periods) * 0.1
    
    data = pd.DataFrame({
        'Open': close + np.random.uniform(-0.3, 0.3, periods),
        'High': close + np.random.uniform(0.5, 2, periods),
        'Low': close - np.random.uniform(0.5, 2, periods),
        'Close': close,
        'Volume': np.full(periods, 3000000),  # 固定高成交量
    }, index=dates)
    
    return data

def main():
    print("\n" + "="*80)
    print("A3 策略信号完整性测试")
    print("="*80)
    
    strategy = A3DualMAVolumeStrategy()
    data = create_test_data(periods=50)
    
    print(f"\n📊 测试数据信息:")
    print(f"   数据条数: {len(data)}")
    print(f"   价格范围: {data['Close'].min():.2f} - {data['Close'].max():.2f}")
    print(f"   成交量: {data['Volume'].iloc[-1]:.0f}")
    
    print(f"\n" + "-"*80)
    print("运行信号分析...\n")
    
    # 运行分析
    signals = strategy.analyze('AAPL', data)
    
    print("\n" + "-"*80)
    print(f"\n✅ 分析结束!")
    print(f"生成信号数: {len(signals)}")
    
    if signals:
        print("\n生成的信号详情:")
        for i, signal in enumerate(signals, 1):
            print(f"\n信号 {i}:")
            print(f"  symbol: {signal.get('symbol')}")
            print(f"  action: {signal.get('action')}")
            print(f"  signal_type: {signal.get('signal_type')}")
            print(f"  price: {signal.get('price'):.2f}")
            print(f"  confidence: {signal.get('confidence'):.1%}")
            print(f"  position_size: {signal.get('position_size')} ← 必需字段")
            print(f"  signal_hash: {signal.get('signal_hash')} ← 必需字段")
            
            # 检查必需字段
            required_fields = ['symbol', 'action', 'signal_type', 'price', 'confidence', 'position_size', 'signal_hash']
            missing = [f for f in required_fields if f not in signal]
            
            if missing:
                print(f"  ⚠️  缺少字段: {missing}")
            else:
                print(f"  ✓ 所有必需字段都存在")
    else:
        print("\n未生成任何信号")
    
    print("\n" + "="*80)

if __name__ == '__main__':
    main()
