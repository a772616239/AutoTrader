#!/usr/bin/env python3
"""
测试preselect信号生成修复
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from data.data_provider import DataProvider
from strategies.base_strategy import BaseStrategy

def test_preselect_signals():
    """测试preselect信号生成"""
    print("开始测试preselect信号生成...")

    # 初始化数据提供器
    data_provider = DataProvider(
        base_url='http://localhost:8001',
        max_retries=3
    )

    # 创建基础策略实例
    strategy = BaseStrategy()

    # 测试符号列表
    symbols = ['AAPL', 'MSFT']  # 使用简单的符号列表进行测试

    try:
        # 调用run_analysis_cycle
        print("调用run_analysis_cycle...")
        signals = strategy.run_analysis_cycle(data_provider, symbols)

        print(f"run_analysis_cycle完成，返回信号数量: {sum(len(sigs) for sigs in signals.values())}")

        # 检查是否生成了CSV文件
        import glob
        csv_files = glob.glob('preselect_signals_*.csv')
        if csv_files:
            print(f"找到preselect信号CSV文件: {csv_files[-1]}")
        else:
            print("未找到preselect信号CSV文件")

        # 检查signals_monitor.csv
        if os.path.exists('signals_monitor.csv'):
            print("找到signals_monitor.csv文件")
        else:
            print("未找到signals_monitor.csv文件")

        return True

    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_preselect_signals()
    print(f"测试结果: {'成功' if success else '失败'}")