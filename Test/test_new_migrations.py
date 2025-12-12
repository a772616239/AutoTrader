#!/usr/bin/env python3
"""
测试新迁移的指标和策略
验证Finance目录迁移到strategies/的质量
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from datetime import datetime
import unittest
from strategies import indicators
from strategies.a23_aroon_oscillator import A23AroonOscillatorStrategy
from strategies.a24_ultimate_oscillator import A24UltimateOscillatorStrategy
from strategies.a25_pairs_trading import A25PairsTradingStrategy
from strategies.a26_williams_r import A26WilliamsRStrategy

class TestNewMigrations(unittest.TestCase):
    """测试新迁移的指标和策略"""

    def setUp(self):
        """设置测试数据"""
        np.random.seed(42)
        dates = pd.date_range('2024-01-01', periods=100, freq='D')

        # 创建测试价格数据
        base_price = 100
        prices = []
        for i in range(100):
            trend = 0.001 * (i - 50)  # 中间开始上涨
            shock = np.random.normal(0, 0.02)
            price = base_price * (1 + trend + shock)
            prices.append(max(price, 50))

        self.test_data = pd.DataFrame({
            'Open': [p * (1 + np.random.normal(0, 0.005)) for p in prices],
            'High': [p * (1 + abs(np.random.normal(0, 0.01))) for p in prices],
            'Low': [p * (1 - abs(np.random.normal(0, 0.01))) for p in prices],
            'Close': prices,
            'Volume': np.random.randint(1000000, 5000000, 100)
        }, index=dates)

        # 确保High >= Close >= Low
        self.test_data['High'] = np.maximum(self.test_data['High'], self.test_data['Close'])
        self.test_data['Low'] = np.minimum(self.test_data['Low'], self.test_data['Close'])

    def test_aroon_oscillator_indicator(self):
        """测试Aroon Oscillator指标"""
        print("🧪 测试Aroon Oscillator指标...")

        aroon_osc = indicators.calculate_aroon_oscillator(
            self.test_data['High'], self.test_data['Low'], period=25
        )

        # 检查返回值类型
        self.assertIsInstance(aroon_osc, pd.Series)

        # 检查数值范围 (-100 到 100)
        valid_values = aroon_osc.dropna()
        if len(valid_values) > 0:
            self.assertTrue(all(-100 <= x <= 100 for x in valid_values))

        # 检查是否有有效值产生
        self.assertGreater(len(valid_values), 0)

        print(f"   ✅ Aroon Oscillator指标测试通过 - 有效值: {len(valid_values)}")

    def test_ultimate_oscillator_indicator(self):
        """测试Ultimate Oscillator指标"""
        print("🧪 测试Ultimate Oscillator指标...")

        uo = indicators.calculate_ultimate_oscillator(
            self.test_data['High'], self.test_data['Low'], self.test_data['Close']
        )

        # 检查返回值类型
        self.assertIsInstance(uo, pd.Series)

        # 检查数值范围 (0 到 100)
        valid_values = uo.dropna()
        if len(valid_values) > 0:
            self.assertTrue(all(0 <= x <= 100 for x in valid_values))

        print(f"   ✅ Ultimate Oscillator指标测试通过 - 有效值: {len(valid_values)}")

    def test_chaikin_money_flow_indicator(self):
        """测试Chaikin Money Flow指标"""
        print("🧪 测试Chaikin Money Flow指标...")

        cmf = indicators.calculate_chaikin_money_flow(
            self.test_data['High'], self.test_data['Low'],
            self.test_data['Close'], self.test_data['Volume']
        )

        # 检查返回值类型
        self.assertIsInstance(cmf, pd.Series)

        # 检查数值范围 (-1 到 1)
        valid_values = cmf.dropna()
        if len(valid_values) > 0:
            self.assertTrue(all(-1 <= x <= 1 for x in valid_values))

        print(f"   ✅ Chaikin Money Flow指标测试通过 - 有效值: {len(valid_values)}")

    def test_ease_of_movement_indicator(self):
        """测试Ease of Movement指标"""
        print("🧪 测试Ease of Movement指标...")

        evm = indicators.calculate_ease_of_movement(
            self.test_data['High'], self.test_data['Low'], self.test_data['Volume']
        )

        # 检查返回值类型
        self.assertIsInstance(evm, pd.Series)

        # 检查是否有有效值产生
        valid_values = evm.dropna()
        self.assertGreater(len(valid_values), 0)

        print(f"   ✅ Ease of Movement指标测试通过 - 有效值: {len(valid_values)}")

    def test_force_index_indicator(self):
        """测试Force Index指标"""
        print("🧪 测试Force Index指标...")

        force_idx = indicators.calculate_force_index(
            self.test_data['Close'], self.test_data['Volume']
        )

        # 检查返回值类型
        self.assertIsInstance(force_idx, pd.Series)

        # 检查是否有有效值产生
        valid_values = force_idx.dropna()
        self.assertGreater(len(valid_values), 0)

        print(f"   ✅ Force Index指标测试通过 - 有效值: {len(valid_values)}")

    def test_williams_r_indicator(self):
        """测试Williams %R指标"""
        print("🧪 测试Williams %R指标...")

        williams_r = indicators.calculate_williams_r(
            self.test_data['High'], self.test_data['Low'], self.test_data['Close']
        )

        # 检查返回值类型
        self.assertIsInstance(williams_r, pd.Series)

        # 检查数值范围 (-100 到 0)
        valid_values = williams_r.dropna()
        if len(valid_values) > 0:
            self.assertTrue(all(-100 <= x <= 0 for x in valid_values))

        print(f"   ✅ Williams %R指标测试通过 - 有效值: {len(valid_values)}")

    def test_aroon_oscillator_strategy(self):
        """测试Aroon Oscillator策略"""
        print("🧪 测试Aroon Oscillator策略...")

        strategy = A23AroonOscillatorStrategy()

        # 测试策略初始化
        self.assertEqual(strategy.get_strategy_name(), "A23 Aroon Oscillator Strategy")

        # 测试信号生成 (使用较长的数据)
        long_data = self.test_data.tail(50)  # 使用后50天数据
        signals = strategy.generate_signals('TEST', long_data, {})

        # 检查返回值类型
        self.assertIsInstance(signals, list)

        print(f"   ✅ Aroon Oscillator策略测试通过 - 信号数量: {len(signals)}")

    def test_ultimate_oscillator_strategy(self):
        """测试Ultimate Oscillator策略"""
        print("🧪 测试Ultimate Oscillator策略...")

        strategy = A24UltimateOscillatorStrategy()

        # 测试策略初始化
        self.assertEqual(strategy.get_strategy_name(), "A24 Ultimate Oscillator Strategy")

        # 测试信号生成
        long_data = self.test_data.tail(50)
        signals = strategy.generate_signals('TEST', long_data, {})

        # 检查返回值类型
        self.assertIsInstance(signals, list)

        print(f"   ✅ Ultimate Oscillator策略测试通过 - 信号数量: {len(signals)}")

    def test_pairs_trading_strategy(self):
        """测试协整配对交易策略"""
        print("🧪 测试协整配对交易策略...")

        strategy = A25PairsTradingStrategy()

        # 测试策略初始化
        self.assertEqual(strategy.get_strategy_name(), "A25 Cointegration Pairs Trading Strategy")

        # 测试协整检验功能
        pair_info = strategy.find_cointegrated_pair('TEST1', 'TEST2', self.test_data, self.test_data)
        # 注意：同一数据不会协整，所以应该返回None
        self.assertIsNone(pair_info)

        # 测试信号生成
        signals = strategy.generate_signals('TEST', self.test_data, {})
        self.assertIsInstance(signals, list)

        print(f"   ✅ 协整配对交易策略测试通过 - 信号数量: {len(signals)}")

    def test_indicator_edge_cases(self):
        """测试指标的边界情况"""
        print("🧪 测试指标边界情况...")

        # 测试空数据
        empty_data = pd.DataFrame()
        result = indicators.calculate_aroon_oscillator(empty_data.get('High', pd.Series()), empty_data.get('Low', pd.Series()))
        self.assertTrue(result.empty)

        # 测试短数据
        short_data = self.test_data.head(5)
        result = indicators.calculate_aroon_oscillator(short_data['High'], short_data['Low'])
        # 短数据应该返回NaN或空结果
        self.assertTrue(result.isna().all() or result.empty)

        print("   ✅ 指标边界情况测试通过")

    def test_strategy_config(self):
        """测试策略配置"""
        print("🧪 测试策略配置...")

        strategies = [
            A23AroonOscillatorStrategy(),
            A24UltimateOscillatorStrategy(),
            A25PairsTradingStrategy(),
            A26WilliamsRStrategy()
        ]

        for strategy in strategies:
            config = strategy._default_config()
            self.assertIsInstance(config, dict)
            self.assertIn('initial_capital', config)
            self.assertIn('risk_per_trade', config)

        print("   ✅ 策略配置测试通过")

def run_performance_test():
    """运行性能测试"""
    print("\n⚡ 运行性能测试...")

    # 测试指标计算性能
    import time

    start_time = time.time()
    for _ in range(100):
        indicators.calculate_aroon_oscillator(
            test_data['High'], test_data['Low'], period=25
        )
    end_time = time.time()

    avg_time = (end_time - start_time) / 100
    print(f"   平均计算时间: {avg_time:.4f}秒")
    return avg_time

def main():
    """主函数"""
    print("🚀 新迁移组件测试套件")
    print("=" * 60)

    # 运行单元测试
    unittest.main(argv=[''], exit=False, verbosity=0)

    # 运行性能测试
    try:
        perf_time = run_performance_test()
        if perf_time < 0.01:  # 应该在10ms以内
            print("✅ 性能测试通过")
        else:
            print(f"⚠️ 性能较慢: {perf_time:.4f}秒")
    except Exception as e:
        print(f"⚠️ 性能测试失败: {e}")

    print("\n🎉 所有测试完成！")

if __name__ == '__main__':
    # 创建全局测试数据
    np.random.seed(42)
    dates = pd.date_range('2024-01-01', periods=200, freq='D')
    base_price = 100
    prices = []
    for i in range(200):
        trend = 0.001 * (i - 100)
        shock = np.random.normal(0, 0.02)
        price = base_price * (1 + trend + shock)
        prices.append(max(price, 50))

    test_data = pd.DataFrame({
        'Open': [p * (1 + np.random.normal(0, 0.005)) for p in prices],
        'High': [p * (1 + abs(np.random.normal(0, 0.01))) for p in prices],
        'Low': [p * (1 - abs(np.random.normal(0, 0.01))) for p in prices],
        'Close': prices,
        'Volume': np.random.randint(1000000, 5000000, 200)
    }, index=dates)

    test_data['High'] = np.maximum(test_data['High'], test_data['Close'])
    test_data['Low'] = np.minimum(test_data['Low'], test_data['Close'])

    main()