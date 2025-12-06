#!/usr/bin/env python3
"""
测试 A3 策略完整日志输出
"""

import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta

# 配置日志以查看所有输出
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from strategies.a3_dual_ma_volume import A3DualMAVolumeStrategy

def create_test_data(periods=50):
    """创建测试数据 - 模拟带有均线交叉的市场"""
    np.random.seed(42)
    dates = pd.date_range('2025-01-01 10:00', periods=periods, freq='5min')
    
    # 生成价格数据 - 创建一个上升趋势后来一个下降
    base_price = 100
    trend = np.linspace(0, 2, periods // 2)  # 上升
    trend = np.concatenate([trend, np.linspace(2, 0.5, periods - periods // 2)])  # 下降
    close = base_price + trend + np.random.randn(periods) * 0.2
    
    data = pd.DataFrame({
        'Open': close + np.random.uniform(-0.3, 0.3, periods),
        'High': close + np.random.uniform(0.3, 1, periods),
        'Low': close - np.random.uniform(0.3, 1, periods),
        'Close': close,
        'Volume': np.random.uniform(2000000, 5000000, periods),
    }, index=dates)
    
    return data

def main():
    print("\n" + "="*80)
    print("A3 策略完整日志测试")
    print("="*80)
    
    strategy = A3DualMAVolumeStrategy()
    data = create_test_data(periods=50)
    
    print(f"\n📊 测试数据信息:")
    print(f"   数据条数: {len(data)}")
    print(f"   日期范围: {data.index[0]} 到 {data.index[-1]}")
    print(f"   价格范围: {data['Close'].min():.2f} - {data['Close'].max():.2f}")
    print(f"   成交量范围: {data['Volume'].min():.0f} - {data['Volume'].max():.0f}")
    
    print(f"\n" + "-"*80)
    print("开始分析...\n")
    
    # 运行分析
    signals = strategy.analyze('AAPL', data)
    
    print("\n" + "-"*80)
    print(f"\n✅ 分析结束!")
    print(f"生成信号数: {len(signals)}")
    
    if signals:
        print("\n生成的信号:")
        for i, signal in enumerate(signals, 1):
            print(f"\n信号 {i}:")
            for key, value in signal.items():
                print(f"  {key}: {value}")
    else:
        print("\n未生成任何信号（这是正常的，查看上面的日志了解原因）")
    
    print("\n" + "="*80)

if __name__ == '__main__':
    main()
