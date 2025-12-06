#!/usr/bin/env python3
"""
测试 A3 策略日志输出
"""

import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from strategies.a3_dual_ma_volume import A3DualMAVolumeStrategy

def create_test_data(periods=50):
    """创建测试数据"""
    np.random.seed(42)
    dates = pd.date_range('2025-01-01 09:30', periods=periods, freq='5min')
    
    # 生成价格数据
    close = np.cumsum(np.random.randn(periods) * 0.5) + 100
    
    data = pd.DataFrame({
        'Open': close + np.random.uniform(-0.5, 0.5, periods),
        'High': close + np.random.uniform(0.5, 2, periods),
        'Low': close - np.random.uniform(0.5, 2, periods),
        'Close': close,
        'Volume': np.random.uniform(1000000, 5000000, periods),
    }, index=dates)
    
    return data

def test_buy_signal_logging():
    """测试买入信号日志"""
    print("\n" + "="*80)
    print("测试 A3 策略 detect_buy_signal 日志输出")
    print("="*80)
    
    strategy = A3DualMAVolumeStrategy()
    data = create_test_data(periods=50)
    
    print(f"\n📊 测试数据: {len(data)} 条记录")
    print(f"   日期范围: {data.index[0]} 到 {data.index[-1]}")
    print(f"   价格范围: {data['Close'].min():.2f} - {data['Close'].max():.2f}")
    print(f"   成交量范围: {data['Volume'].min():.0f} - {data['Volume'].max():.0f}")
    
    print("\n🔍 检测买入信号...")
    print("-" * 80)
    
    signal = strategy.detect_buy_signal('AAPL', data, {})
    
    print("-" * 80)
    
    if signal:
        print(f"\n✓ 买入信号生成成功！")
        print(f"  信号类型: {signal['signal_type']}")
        print(f"  行动: {signal['action']}")
        print(f"  价格: {signal['price']:.2f}")
        print(f"  置信度: {signal['confidence']:.1%}")
        print(f"  理由: {signal['reason']}")
    else:
        print(f"\n✗ 未生成买入信号（查看上面的日志了解原因）")

if __name__ == '__main__':
    test_buy_signal_logging()
