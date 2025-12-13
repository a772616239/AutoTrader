#!/usr/bin/env python3
"""
信号跟踪器 - 每小时监控信号表现，计算盈亏并生成胜率报告
"""
import pandas as pd
import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List
from concurrent.futures import ThreadPoolExecutor, as_completed

from data.data_provider import DataProvider
import config as global_config

logger = logging.getLogger(__name__)


class SignalTracker:
    """信号跟踪器"""

    def __init__(self):
        self.data_provider = DataProvider(base_url=global_config.CONFIG['data_server']['base_url'])
        self.signals_file = 'signals_monitor.csv'
        self.tracking_file = 'signal_tracking.json'
        self.report_file = 'signal_performance_report.txt'

    def load_signals(self) -> pd.DataFrame:
        """加载信号文件"""
        try:
            if not os.path.exists(self.signals_file):
                logger.warning(f"信号文件不存在: {self.signals_file}")
                return pd.DataFrame()

            df = pd.read_csv(self.signals_file)
            logger.info(f"加载了 {len(df)} 个信号")
            return df
        except Exception as e:
            logger.error(f"加载信号文件失败: {e}")
            return pd.DataFrame()

    def load_tracking_data(self) -> Dict:
        """加载跟踪数据"""
        try:
            if os.path.exists(self.tracking_file):
                with open(self.tracking_file, 'r') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"加载跟踪数据失败: {e}")
            return {}

    def save_tracking_data(self, data: Dict):
        """保存跟踪数据"""
        try:
            with open(self.tracking_file, 'w') as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"保存跟踪数据失败: {e}")

    def get_current_price(self, symbol: str) -> float:
        """获取股票当前价格"""
        try:
            df = self.data_provider.get_intraday_data(symbol, interval='5m', lookback=5)
            if not df.empty:
                return df['Close'].iloc[-1]
            return None
        except Exception as e:
            logger.error(f"获取{symbol}当前价格失败: {e}")
            return None

    def update_signal_tracking(self, signals_df: pd.DataFrame) -> Dict:
        """更新信号跟踪数据"""
        tracking_data = self.load_tracking_data()
        updated_count = 0

        for _, signal in signals_df.iterrows():
            try:
                symbol = signal['symbol']
                signal_id = f"{symbol}_{signal.get('generated_at', '')}_{signal.get('signal_type', '')}"

                current_price = self.get_current_price(symbol)
                if current_price is None:
                    continue

                # 初始化或更新跟踪数据
                if signal_id not in tracking_data:
                    tracking_data[signal_id] = {
                        'symbol': symbol,
                        'strategy': signal.get('strategy', ''),
                        'signal_type': signal.get('signal_type', ''),
                        'action': signal.get('action', ''),
                        'initial_price': signal.get('price', current_price),
                        'initial_time': signal.get('generated_at', datetime.now().isoformat()),
                        'current_price': current_price,
                        'price_history': [],
                        'last_update': datetime.now().isoformat()
                    }
                else:
                    # 更新当前价格和历史记录
                    tracking_data[signal_id]['current_price'] = current_price
                    tracking_data[signal_id]['last_update'] = datetime.now().isoformat()

                    # 记录价格历史（每小时记录一次）
                    price_history = tracking_data[signal_id].get('price_history', [])
                    now = datetime.now()

                    # 只在整点或价格变化显著时记录
                    if not price_history or (now - datetime.fromisoformat(price_history[-1]['time'])).total_seconds() >= 3600:
                        price_history.append({
                            'time': now.isoformat(),
                            'price': current_price
                        })
                        # 保留最近24小时的历史
                        cutoff_time = now - timedelta(hours=24)
                        price_history = [h for h in price_history if datetime.fromisoformat(h['time']) > cutoff_time]
                        tracking_data[signal_id]['price_history'] = price_history

                updated_count += 1

            except Exception as e:
                logger.error(f"更新信号跟踪失败: {e}")
                continue

        self.save_tracking_data(tracking_data)
        logger.info(f"更新了 {updated_count} 个信号的跟踪数据")
        return tracking_data

    def calculate_signal_performance(self, tracking_data: Dict) -> Dict:
        """计算信号表现"""
        performance = {
            'total_signals': len(tracking_data),
            'strategy_performance': {},
            'overall_stats': {
                'total_return': 0.0,
                'winning_signals': 0,
                'losing_signals': 0,
                'win_rate': 0.0,
                'avg_return': 0.0,
                'max_return': 0.0,
                'min_return': 0.0
            }
        }

        returns = []

        for signal_id, data in tracking_data.items():
            try:
                initial_price = data.get('initial_price', 0)
                current_price = data.get('current_price', 0)
                action = data.get('action', '')
                strategy = data.get('strategy', 'unknown')

                if initial_price <= 0 or current_price <= 0:
                    continue

                # 计算收益率
                if action.upper() == 'BUY':
                    return_pct = (current_price - initial_price) / initial_price * 100
                elif action.upper() == 'SELL':
                    return_pct = (initial_price - current_price) / initial_price * 100
                else:
                    continue

                returns.append(return_pct)

                # 按策略统计
                if strategy not in performance['strategy_performance']:
                    performance['strategy_performance'][strategy] = {
                        'total_signals': 0,
                        'winning_signals': 0,
                        'losing_signals': 0,
                        'win_rate': 0.0,
                        'total_return': 0.0,
                        'avg_return': 0.0,
                        'returns': []
                    }

                strat_perf = performance['strategy_performance'][strategy]
                strat_perf['total_signals'] += 1
                strat_perf['total_return'] += return_pct
                strat_perf['returns'].append(return_pct)

                if return_pct > 0:
                    strat_perf['winning_signals'] += 1
                else:
                    strat_perf['losing_signals'] += 1

            except Exception as e:
                logger.error(f"计算信号表现失败 {signal_id}: {e}")
                continue

        # 计算总体统计
        if returns:
            performance['overall_stats']['total_return'] = sum(returns)
            performance['overall_stats']['winning_signals'] = sum(1 for r in returns if r > 0)
            performance['overall_stats']['losing_signals'] = sum(1 for r in returns if r <= 0)
            performance['overall_stats']['win_rate'] = performance['overall_stats']['winning_signals'] / len(returns) * 100
            performance['overall_stats']['avg_return'] = sum(returns) / len(returns)
            performance['overall_stats']['max_return'] = max(returns)
            performance['overall_stats']['min_return'] = min(returns)

        # 计算各策略统计
        for strategy, perf in performance['strategy_performance'].items():
            if perf['returns']:
                perf['win_rate'] = perf['winning_signals'] / perf['total_signals'] * 100
                perf['avg_return'] = sum(perf['returns']) / len(perf['returns'])

        return performance

    def generate_report(self, performance: Dict):
        """生成性能报告"""
        try:
            report_lines = []
            report_lines.append("=" * 60)
            report_lines.append("信号性能监控报告")
            report_lines.append("=" * 60)
            report_lines.append(f"报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            report_lines.append("")

            # 总体统计
            overall = performance['overall_stats']
            report_lines.append("总体统计:")
            report_lines.append(f"  总信号数: {performance['total_signals']}")
            report_lines.append(f"  胜率: {overall['win_rate']:.2f}%")
            report_lines.append(f"  盈利信号: {overall['winning_signals']}")
            report_lines.append(f"  亏损信号: {overall['losing_signals']}")
            report_lines.append(f"  平均收益率: {overall['avg_return']:.2f}%")
            report_lines.append(f"  最大收益率: {overall['max_return']:.2f}%")
            report_lines.append(f"  最小收益率: {overall['min_return']:.2f}%")
            report_lines.append("")

            # 各策略统计
            report_lines.append("各策略表现:")
            report_lines.append("-" * 40)

            for strategy, perf in sorted(performance['strategy_performance'].items()):
                report_lines.append(f"策略 {strategy}:")
                report_lines.append(f"  信号数: {perf['total_signals']}")
                report_lines.append(f"  胜率: {perf['win_rate']:.2f}%")
                report_lines.append(f"  平均收益率: {perf['avg_return']:.2f}%")
                report_lines.append("")

            # 保存报告
            with open(self.report_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(report_lines))

            logger.info(f"性能报告已保存到 {self.report_file}")

        except Exception as e:
            logger.error(f"生成报告失败: {e}")

    def run(self):
        """运行信号跟踪"""
        logger.info("开始信号跟踪...")

        # 加载信号
        signals_df = self.load_signals()
        if signals_df.empty:
            logger.warning("没有信号数据，跳过跟踪")
            return

        # 更新跟踪数据
        tracking_data = self.update_signal_tracking(signals_df)

        # 计算性能
        performance = self.calculate_signal_performance(tracking_data)

        # 生成报告
        self.generate_report(performance)

        logger.info("信号跟踪完成")


def main():
    """主函数"""
    # 设置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 创建信号跟踪器并运行
    tracker = SignalTracker()
    tracker.run()


if __name__ == '__main__':
    main()