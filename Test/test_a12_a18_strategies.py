#!/usr/bin/env python3
"""
测试A12-A18策略的信号生成能力
使用真实的历史数据测试各个策略
"""
import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta
import sys
import os

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.data_provider import DataProvider
from strategies.a12_stochastic_rsi import A12StochasticRSIStrategy
from strategies.a13_ema_crossover import A13EMACrossoverStrategy
from strategies.a14_rsi_trendline import A14RSITrendlineStrategy
from strategies.a15_pairs_trading import A15PairsTradingStrategy
from strategies.a16_roc import A16ROCStrategy
from strategies.a17_cci import A17CCIStrategy
from strategies.a18_isolation_forest import A18IsolationForestStrategy

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class StrategyTester:
    """策略测试器"""

    def __init__(self):
        """初始化测试器"""
        self.data_provider = DataProvider(
            base_url='http://localhost:8001',
            max_retries=3
        )

        # 测试股票列表
        self.test_symbols = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA']

        # 策略列表
        self.strategies = [
            ("A12 Stochastic RSI", A12StochasticRSIStrategy),
            ("A13 EMA Crossover", A13EMACrossoverStrategy),
            ("A14 RSI Trendline", A14RSITrendlineStrategy),
            ("A15 Pairs Trading", A15PairsTradingStrategy),
            ("A16 ROC", A16ROCStrategy),
            ("A17 CCI", A17CCIStrategy),
            ("A18 Isolation Forest", A18IsolationForestStrategy),
        ]

    def get_historical_data(self, symbol: str, days: int = 30) -> pd.DataFrame:
        """
        获取历史数据

        Args:
            symbol: 股票代码
            days: 获取天数

        Returns:
            pd.DataFrame: 历史数据
        """
        try:
            logger.info(f"📊 获取 {symbol} 的 {days} 天历史数据...")

            # 计算日期范围
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)

            # 获取日线数据
            data = self.data_provider.get_historical_data(
                symbol=symbol,
                start_date=start_date.strftime('%Y-%m-%d'),
                end_date=end_date.strftime('%Y-%m-%d'),
                interval='1d'
            )

            if data is None or data.empty:
                logger.warning(f"⚠️ 无法获取 {symbol} 的历史数据")
                return None

            logger.info(f"✅ {symbol} 数据获取成功: {len(data)} 条记录")
            return data

        except Exception as e:
            logger.error(f"❌ 获取 {symbol} 数据失败: {e}")
            return None

    def test_strategy(self, strategy_name: str, strategy_class, symbol: str, data: pd.DataFrame):
        """
        测试单个策略

        Args:
            strategy_name: 策略名称
            strategy_class: 策略类
            symbol: 股票代码
            data: 历史数据

        Returns:
            dict: 测试结果
        """
        try:
            logger.info(f"\n🔬 测试 {strategy_name} 对 {symbol}")

            # 创建策略实例
            strategy = strategy_class()
            logger.info(f"✅ 策略实例创建成功: {strategy.get_strategy_name()}")

            # 计算技术指标
            indicators = {}
            try:
                # 计算ATR
                from strategies.indicators import calculate_atr
                if len(data) >= 14:
                    indicators['ATR'] = calculate_atr(data['High'], data['Low'], data['Close']).iloc[-1]
                    logger.info(f"📊 ATR计算成功: ${indicators['ATR']:.4f}")
            except Exception as e:
                logger.warning(f"⚠️ ATR计算失败: {e}")

            # 生成信号
            signals = strategy.generate_signals(symbol, data, indicators)

            # 分析结果
            result = {
                'strategy': strategy_name,
                'symbol': symbol,
                'signals_count': len(signals),
                'signals': signals,
                'success': True,
                'error': None
            }

            logger.info(f"🎯 {strategy_name} 测试完成 - 生成信号数: {len(signals)}")

            # 显示信号详情
            if signals:
                for i, signal in enumerate(signals, 1):
                    action = signal.get('action', 'UNKNOWN')
                    signal_type = signal.get('signal_type', 'UNKNOWN')
                    confidence = signal.get('confidence', 0)
                    reason = signal.get('reason', 'No reason provided')

                    logger.info(f"   📈 信号 {i}: {action} ({signal_type}) - 置信度: {confidence:.2f}")
                    logger.info(f"      原因: {reason}")
            else:
                logger.info("   📭 未生成任何信号")

            return result

        except Exception as e:
            logger.error(f"❌ {strategy_name} 测试失败: {e}")
            import traceback
            logger.debug(traceback.format_exc())

            return {
                'strategy': strategy_name,
                'symbol': symbol,
                'signals_count': 0,
                'signals': [],
                'success': False,
                'error': str(e)
            }

    def run_tests(self):
        """运行所有测试"""
        logger.info("="*80)
        logger.info("🚀 A12-A18策略信号生成测试")
        logger.info("="*80)

        # 检查数据服务器连接
        logger.info("🔍 检查数据服务器连接...")
        market_status = self.data_provider.get_market_status()
        if not market_status['server_available']:
            logger.error("❌ 数据服务器不可用，请确保数据服务器正在运行")
            return False

        logger.info("✅ 数据服务器连接正常")
        logger.info(f"   可用标的数: {len(market_status['symbols_available'])}")

        all_results = []

        # 对每个测试股票运行所有策略
        for symbol in self.test_symbols:
            logger.info(f"\n{'='*60}")
            logger.info(f"📈 测试股票: {symbol}")
            logger.info('='*60)

            # 获取数据
            data = self.get_historical_data(symbol, days=30)
            if data is None:
                logger.warning(f"⚠️ 跳过 {symbol} 的测试")
                continue

            # 对每个策略进行测试
            symbol_results = []
            for strategy_name, strategy_class in self.strategies:
                result = self.test_strategy(strategy_name, strategy_class, symbol, data)
                symbol_results.append(result)
                all_results.append(result)

            # 股票小结
            successful_tests = sum(1 for r in symbol_results if r['success'])
            total_signals = sum(r['signals_count'] for r in symbol_results)

            logger.info(f"\n📊 {symbol} 测试小结:")
            logger.info(f"   成功策略数: {successful_tests}/{len(self.strategies)}")
            logger.info(f"   总信号数: {total_signals}")

        # 总体统计
        self.print_summary(all_results)
        return True

    def print_summary(self, results):
        """打印测试总结"""
        logger.info(f"\n{'='*80}")
        logger.info("📊 测试总结报告")
        logger.info('='*80)

        total_tests = len(results)
        successful_tests = sum(1 for r in results if r['success'])
        total_signals = sum(r['signals_count'] for r in results)

        logger.info(f"总测试数: {total_tests}")
        logger.info(f"成功测试数: {successful_tests}")
        logger.info(f"失败测试数: {total_tests - successful_tests}")
        logger.info(f"总信号数: {total_signals}")

        # 按策略统计
        strategy_stats = {}
        for result in results:
            strategy = result['strategy']
            if strategy not in strategy_stats:
                strategy_stats[strategy] = {'tests': 0, 'signals': 0, 'success': 0}

            strategy_stats[strategy]['tests'] += 1
            strategy_stats[strategy]['signals'] += result['signals_count']
            if result['success']:
                strategy_stats[strategy]['success'] += 1

        logger.info(f"\n按策略统计:")
        for strategy, stats in strategy_stats.items():
            success_rate = stats['success'] / stats['tests'] * 100 if stats['tests'] > 0 else 0
            logger.info(f"   {strategy}: {stats['success']}/{stats['tests']} 成功 ({success_rate:.1f}%) - {stats['signals']} 信号")

        # 按股票统计
        symbol_stats = {}
        for result in results:
            symbol = result['symbol']
            if symbol not in symbol_stats:
                symbol_stats[symbol] = {'tests': 0, 'signals': 0, 'success': 0}

            symbol_stats[symbol]['tests'] += 1
            symbol_stats[symbol]['signals'] += result['signals_count']
            if result['success']:
                symbol_stats[symbol]['success'] += 1

        logger.info(f"\n按股票统计:")
        for symbol, stats in symbol_stats.items():
            success_rate = stats['success'] / stats['tests'] * 100 if stats['tests'] > 0 else 0
            logger.info(f"   {symbol}: {stats['success']}/{stats['tests']} 成功 ({success_rate:.1f}%) - {stats['signals']} 信号")

        if successful_tests == total_tests:
            logger.info("\n✅ 所有策略测试成功！A12-A18策略可以正常生成交易信号。")
        else:
            logger.warning(f"\n⚠️ {total_tests - successful_tests} 个策略测试失败，请检查上述错误信息。")

        if total_signals > 0:
            logger.info(f"\n🎯 测试期间共生成 {total_signals} 个交易信号，说明策略具有信号生成能力。")
        else:
            logger.warning("\n📭 测试期间未生成任何交易信号，可能需要调整策略参数或使用不同的测试数据。")

def main():
    """主函数"""
    tester = StrategyTester()
    success = tester.run_tests()

    return 0 if success else 1

if __name__ == '__main__':
    exit(main())</content>
</xai:function_call">{"path":"Test/test_a12_a18_strategies.py","operation":"created","notice":"You do not need to re-read the file, as you have seen all changes Proceed with the task using these changes as the new baseline."}  
<xai:function_call name="execute_command">
<parameter name="command">cd /Users/wangxufeng/AutoTrader && python Test/test_a12_a18_strategies.py