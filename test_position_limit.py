#!/usr/bin/env python3
"""
测试单股总仓位限制功能
"""
import logging
from momentum_reversal_main import MomentumReversalStrategy

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_position_limit():
    """测试位置限制检查"""
    
    # 创建策略实例
    config = {
        'max_position_notional': 60000.0,
        'initial_capital': 100000.0
    }
    
    strategy = MomentumReversalStrategy(config=config)
    
    # 测试用例
    test_cases = [
        {
            'name': '新股票，30000美元仓位（应该通过）',
            'symbol': 'AAPL',
            'new_value': 30000.0,
            'current_price': 150.0,
            'expected': True
        },
        {
            'name': '新股票，70000美元仓位（应该拒绝）',
            'symbol': 'GOOGL',
            'new_value': 70000.0,
            'current_price': 140.0,
            'expected': False
        },
        {
            'name': '边界值，60000美元仓位（应该通过）',
            'symbol': 'MSFT',
            'new_value': 60000.0,
            'current_price': 300.0,
            'expected': True
        },
    ]
    
    logger.info(\"开始测试单股总仓位限制功能...\\n\")
    
    for test_case in test_cases:
        logger.info(f\"测试: {test_case['name']}\")
        result = strategy.check_single_stock_position_limit(
            test_case['symbol'],
            test_case['new_value'],
            test_case['current_price']
        )
        
        status = \"✅ PASS\" if result == test_case['expected'] else \"❌ FAIL\"
        logger.info(f\"{status}\\n\")
    
    logger.info(\"测试完成！\")

if __name__ == '__main__':
    test_position_limit()
