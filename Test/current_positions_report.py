#!/usr/bin/env python3
"""
当前持仓利润统计报告生成器
统计各量化策略当前持有的股票相对于买入价格的利润百分比
"""
import json
import logging
from datetime import datetime
from collections import defaultdict
from data.data_provider import DataProvider

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class CurrentPositionsReport:
    """当前持仓利润统计报告"""

    def __init__(self, trades_file='data/trades.json'):
        self.trades_file = trades_file
        self.data_provider = DataProvider()
        self.trades = []
        self.positions = {}  # symbol -> position info
        self.strategy_positions = defaultdict(list)  # strategy -> list of positions

    def load_trades(self):
        """加载交易记录"""
        try:
            with open(self.trades_file, 'r', encoding='utf-8') as f:
                self.trades = json.load(f)
            logger.info(f"成功加载 {len(self.trades)} 条交易记录")
        except Exception as e:
            logger.error(f"加载交易记录失败: {e}")
            self.trades = []

    def analyze_positions(self):
        """分析当前持仓"""
        # 按股票分组交易记录
        symbol_trades = defaultdict(list)

        for trade in self.trades:
            if trade.get('status') == 'EXECUTED':
                symbol = trade['symbol']
                action = trade['action']
                symbol_trades[symbol].append(trade)

        # 计算每个股票的持仓
        for symbol, trades in symbol_trades.items():
            # 分离买入和卖出交易
            buys = [t for t in trades if t['action'] == 'BUY']
            sells = [t for t in trades if t['action'] == 'SELL']

            # 计算净持仓
            total_buy_quantity = sum(t['size'] for t in buys)
            total_sell_quantity = sum(t['size'] for t in sells)

            net_quantity = total_buy_quantity - total_sell_quantity

            if net_quantity > 0:
                # 计算平均买入成本
                total_buy_cost = sum(t['price'] * t['size'] for t in buys)
                avg_cost = total_buy_cost / total_buy_quantity

                # 获取当前股价
                current_price = self.get_current_price(symbol)

                if current_price > 0:
                    # 计算利润百分比
                    profit_pct = ((current_price - avg_cost) / avg_cost) * 100

                    # 获取策略信息（从买入交易中获取）
                    strategy_type = self.get_strategy_type(buys[0])

                    position = {
                        'symbol': symbol,
                        'quantity': net_quantity,
                        'avg_cost': avg_cost,
                        'current_price': current_price,
                        'profit_pct': profit_pct,
                        'total_value': current_price * net_quantity,
                        'strategy': strategy_type,
                        'last_buy_time': max(t['timestamp'] for t in buys)
                    }

                    self.positions[symbol] = position
                    self.strategy_positions[strategy_type].append(position)

                    logger.info(f"{symbol}: 持有 {net_quantity} 股, 平均成本 ${avg_cost:.2f}, 当前价 ${current_price:.2f}, 利润 {profit_pct:.2f}%")

    def get_current_price(self, symbol):
        """获取当前股价"""
        try:
            # 获取最近5分钟的数据，取最新一条的收盘价
            df = self.data_provider.get_intraday_data(symbol, interval='5m', lookback=1)
            if not df.empty:
                return df['Close'].iloc[-1]
            else:
                logger.warning(f"无法获取 {symbol} 的当前股价")
                return 0.0
        except Exception as e:
            logger.error(f"获取 {symbol} 当前股价失败: {e}")
            return 0.0

    def get_strategy_type(self, trade):
        """从交易记录中获取策略类型"""
        signal_type = trade.get('signal_type', '')

        # 根据信号类型映射到策略
        strategy_map = {
            'RSI_OVERSOLD': 'a1_momentum_reversal',
            'RSI_OVERBOUGHT': 'a1_momentum_reversal',
            'MA_GOLDEN_CROSS': 'a11_moving_average_crossover',
            'MA_DEATH_CROSS': 'a11_moving_average_crossover',
            'MACD_GOLDEN_CROSS': 'a2_zscore',
            'MACD_DEATH_CROSS': 'a2_zscore',
            'BB_LOWER_BREAKOUT': 'a3_dual_ma_volume',
            'BB_UPPER_BREAKOUT': 'a3_dual_ma_volume',
            'PULLBACK_BUY_UPTREND': 'a4_pullback',
            'PULLBACK_SELL_DOWNTREND': 'a4_pullback',
            'MORNING_MOMENTUM': 'a5_multifactor_ai',
            'MULTIFACTOR_AI_BUY': 'a5_multifactor_ai',
            'MULTIFACTOR_AI_SELL': 'a5_multifactor_ai',
            'CTA_BREAKOUT_LONG': 'a7_cta_trend',
            'CTA_BREAKDOWN_SHORT': 'a7_cta_trend',
            'NEWS_SENTIMENT_BUY': 'a6_news_trading',
            'NEWS_SENTIMENT_SELL': 'a6_news_trading'
        }

        return strategy_map.get(signal_type, 'unknown')

    def generate_report(self):
        """生成报告"""
        report_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        report_date = datetime.now().strftime('%Y-%m-%d')

        report = f"尾盘量化策略当前持仓利润统计报告\n"
        report += f"报告生成时间: {report_time}\n"
        report += f"统计日期: {report_date}\n\n"

        total_positions_value = 0
        total_profit = 0

        # 按策略分组显示
        for strategy, positions in self.strategy_positions.items():
            if not positions:
                continue

            strategy_name = self.get_strategy_display_name(strategy)
            report += f"{strategy_name} ({strategy}):\n"

            strategy_total_value = 0
            strategy_total_profit = 0

            for position in sorted(positions, key=lambda x: x['profit_pct'], reverse=True):
                profit_symbol = "+" if position['profit_pct'] >= 0 else ""
                report += f"  {position['symbol']} (当前价: ${position['current_price']:.2f}):\n"
                report += f"    持有: {position['quantity']} 股 平均成本: ${position['avg_cost']:.2f} 总价值: ${position['total_value']:.2f}\n"
                report += f"    利润: {profit_symbol}${position['total_value'] - (position['avg_cost'] * position['quantity']):.2f} ({profit_symbol}{position['profit_pct']:.2f}%)\n"
                strategy_total_value += position['total_value']
                strategy_total_profit += position['total_value'] - (position['avg_cost'] * position['quantity'])

            # 策略汇总
            strategy_profit_pct = (strategy_total_profit / strategy_total_value * 100) if strategy_total_value > 0 else 0
            profit_symbol = "+" if strategy_profit_pct >= 0 else ""
            report += f"  策略汇总:\n"
            report += f"    总持仓价值: ${strategy_total_value:.2f}\n"
            report += f"    总利润: {profit_symbol}${strategy_total_profit:.2f} ({profit_symbol}{strategy_profit_pct:.2f}%)\n"
            report += "\n"

            total_positions_value += strategy_total_value
            total_profit += strategy_total_profit

        # 总汇总
        total_profit_pct = (total_profit / total_positions_value * 100) if total_positions_value > 0 else 0
        profit_symbol = "+" if total_profit_pct >= 0 else ""
        report += "汇总:\n"
        report += f"  总持仓价值: ${total_positions_value:.2f}\n"
        report += f"  总利润: {profit_symbol}${total_profit:.2f} ({profit_symbol}{total_profit_pct:.2f}%)"

        return report

    def get_strategy_display_name(self, strategy_code):
        """获取策略显示名称"""
        name_map = {
            'a1_momentum_reversal': '动量反转策略',
            'a2_zscore': 'Z-Score均值回归',
            'a3_dual_ma_volume': '双均线成交量突破',
            'a4_pullback': '回调交易策略',
            'a5_multifactor_ai': '多因子AI融合',
            'a6_news_trading': '新闻交易策略',
            'a7_cta_trend': 'CTA趋势跟踪',
            'a11_moving_average_crossover': '移动平均交叉',
            'unknown': '未知策略'
        }
        return name_map.get(strategy_code, strategy_code)

    def save_report(self, filename=None):
        """保存报告到文件"""
        if filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'logs/current_positions_report_{timestamp}.txt'

        report = self.generate_report()

        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(report)
            logger.info(f"报告已保存到: {filename}")
            return filename
        except Exception as e:
            logger.error(f"保存报告失败: {e}")
            return None

def main():
    """主函数"""
    report_generator = CurrentPositionsReport()

    # 加载交易记录
    report_generator.load_trades()

    # 分析持仓
    report_generator.analyze_positions()

    # 生成并保存报告
    filename = report_generator.save_report()

    if filename:
        print(f"当前持仓利润报告已生成: {filename}")
        print("\n报告内容:")
        print(report_generator.generate_report())
    else:
        print("报告生成失败")

if __name__ == "__main__":
    main()