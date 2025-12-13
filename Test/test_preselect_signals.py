#!/usr/bin/env python3
"""
测试preselect_a2信号生成功能
"""
import sys
import os
import logging
from datetime import datetime

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_preselect_signals():
    """测试preselect_a2信号生成功能"""
    try:
        from strategies.base_strategy import BaseStrategy
        from config import CONFIG

        print("="*60)
        print("🧪 测试preselect_a2信号生成功能")
        print("="*60)

        # 创建基础策略实例（用于测试）
        strategy = BaseStrategy()

        # 获取preselect_a2股票列表
        preselect_symbols = list(CONFIG.get('symbol_strategy_map', {}).keys())
        print(f"📊 preselect_a2股票数量: {len(preselect_symbols)}")
        print(f"📋 股票列表: {preselect_symbols[:10]}{'...' if len(preselect_symbols) > 10 else ''}")

        if not preselect_symbols:
            print("❌ 未找到preselect_a2股票配置")
            return False

        # 创建模拟数据提供者（不依赖外部服务器）
        class MockDataProvider:
            def get_intraday_data(self, symbol, interval='5m', lookback=300):
                import pandas as pd
                import numpy as np
                from datetime import datetime, timedelta

                # 生成模拟数据
                dates = pd.date_range(end=datetime.now(), periods=lookback, freq='5min')
                np.random.seed(hash(symbol) % 2**32)  # 基于股票代码生成确定性随机数

                # 模拟价格数据
                base_price = 100 + hash(symbol) % 900  # 100-1000之间的价格
                returns = np.random.normal(0, 0.001, len(dates))  # 小幅随机波动
                prices = base_price * (1 + np.cumsum(returns))

                df = pd.DataFrame({
                    'Open': prices * (1 + np.random.uniform(-0.001, 0.001, len(dates))),
                    'High': prices * (1 + np.random.uniform(0, 0.002, len(dates))),
                    'Low': prices * (1 - np.random.uniform(0, 0.002, len(dates))),
                    'Close': prices,
                    'Volume': np.random.uniform(10000, 1000000, len(dates))
                }, index=dates)

                return df

            def get_technical_indicators(self, symbol, timeframe='1d', interval='5m'):
                # 返回基本的空指标字典
                return {}

        data_provider = MockDataProvider()

        # 测试生成preselect信号
        print(f"\n🔄 开始生成preselect信号...")

        # 调用生成preselect信号的方法
        all_signals = {}
        strategy._generate_preselect_signals(data_provider, all_signals)

        # 检查结果
        preselect_signal_count = sum(len(signals) for symbol, signals in all_signals.items()
                                   if symbol in preselect_symbols)

        print(f"✅ preselect信号生成完成:")
        print(f"   股票数量: {len([s for s in all_signals.keys() if s in preselect_symbols])}")
        print(f"   信号总数: {preselect_signal_count}")

        # 检查是否生成了CSV文件
        import glob
        csv_files = glob.glob('preselect_signals_*.csv')
        if csv_files:
            latest_file = max(csv_files, key=os.path.getctime)
            print(f"   CSV文件: {latest_file}")

            # 读取并显示文件内容摘要
            import pandas as pd
            df = pd.read_csv(latest_file)
            print(f"   文件记录数: {len(df)}")

            if len(df) > 0:
                # 显示策略分布
                strategy_counts = df['strategy'].value_counts()
                print(f"   策略分布:")
                for strategy, count in strategy_counts.items():
                    print(f"     {strategy}: {count} 个信号")

                # 显示前3个信号
                print(f"   前3个信号示例:")
                for i, (_, row) in enumerate(df.head(3).iterrows()):
                    print(f"     {i+1}. {row['symbol']} {row['strategy']} {row['action']} @ ${row['price']:.2f}")

        else:
            print("❌ 未找到生成的CSV文件")

        # 测试信号表现分析（如果有历史文件）
        print(f"\n🔄 测试信号表现分析...")
        try:
            strategy.analyze_signal_performance(data_provider)
        except Exception as e:
            print(f"ℹ️ 信号表现分析测试跳过: {e}")

        # 检查是否生成了分析文件
        perf_files = glob.glob('signal_performance_*.csv')
        summary_files = glob.glob('strategy_win_rates_*.csv')

        if perf_files or summary_files:
            print(f"✅ 信号表现分析完成:")
            if perf_files:
                latest_perf = max(perf_files, key=os.path.getctime)
                perf_df = pd.read_csv(latest_perf)
                print(f"   详细表现文件: {latest_perf} ({len(perf_df)} 条记录)")

            if summary_files:
                latest_summary = max(summary_files, key=os.path.getctime)
                summary_df = pd.read_csv(latest_summary)
                print(f"   策略汇总文件: {latest_summary} ({len(summary_df)} 个策略)")

                if len(summary_df) > 0:
                    print(f"   策略胜率摘要:")
                    for _, row in summary_df.iterrows():
                        print(f"     {row['strategy']}: 胜率 {row['win_rate_pct']:.1f}%, "
                              f"平均盈亏 {row['avg_profit_loss_pct']:.2f}% ({int(row['total_signals'])} 个信号)")
        else:
            print("ℹ️ 无历史信号文件可供分析（这是正常的，如果是首次运行）")

        print(f"\n✅ 测试完成！")
        return True

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = test_preselect_signals()
    sys.exit(0 if success else 1)