#!/usr/bin/env python3
"""
A5 策略日志测试脚本
运行单个交易周期并查看详细的 A5 日志输出
"""
import sys
import logging
from datetime import datetime
from data.data_provider import DataProvider
from strategies.a5_multifactor_ai import A5MultiFactorAI
from config import CONFIG

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def test_a5_logging():
    """测试 A5 策略的日志输出"""
    
    print("\n" + "="*70)
    print("A5 多因子AI融合策略 - 日志测试")
    print("="*70 + "\n")
    
    # 初始化数据供应商
    data_provider = DataProvider(CONFIG['data_server'])
    
    # 测试 AAPL 和 MSFT
    test_symbols = ['AAPL', 'MSFT']
    
    for symbol in test_symbols:
        print(f"\n{'='*70}")
        print(f"测试标的: {symbol}")
        print('='*70 + "\n")
        
        try:
            # 获取 A5 配置
            strategy_config = CONFIG.get('strategy_a5', {})
            
            # 创建 A5 策略实例
            a5_strategy = A5MultiFactorAI(symbol, data_provider, strategy_config)
            
            print(f"✅ A5 策略实例创建成功")
            print(f"   - 最小信心度: {a5_strategy.min_confidence}")
            print(f"   - 买入阈值: {a5_strategy.buy_threshold}")
            print(f"   - 卖出阈值: {a5_strategy.sell_threshold}")
            print(f"   - 因子权重 - 流动性: {a5_strategy.liquidity_weight:.2f}, "
                  f"基本面: {a5_strategy.fundamental_weight:.2f}, "
                  f"情绪: {a5_strategy.sentiment_weight:.2f}, "
                  f"动量: {a5_strategy.momentum_weight:.2f}\n")
            
            # 生成信号
            print(f"开始生成 {symbol} 信号...\n")
            signals = a5_strategy.generate_signals()
            
            print(f"\n本次生成 {len(signals)} 个信号")
            for i, signal in enumerate(signals, 1):
                print(f"  信号 {i}: {signal['action']} {signal['quantity']} 股 @ ${signal['price']:.2f} "
                      f"(信心度: {signal['confidence']:.3f})")
        
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "="*70)
    print("测试完成")
    print("="*70 + "\n")

if __name__ == '__main__':
    test_a5_logging()
