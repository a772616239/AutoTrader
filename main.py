#!/usr/bin/env python3
"""
动量反转日内交易系统 (多策略版本)
支持A1动量反转策略、A2 Z-Score策略和A3双均线成交量突破策略
"""
import sys
import os
import time
import schedule
import warnings
import logging
import importlib
import re
import json
from datetime import datetime, timedelta
from typing import Dict, List
from collections import defaultdict
from config import STRATEGY_CONFIG_MAP
try:
    import pytz
    HAS_PYTZ = True
except ImportError:
    HAS_PYTZ = False
    logging.warning("pytz未安装，将使用本地时间。建议安装pytz以支持美东时间: pip install pytz")

# 添加模块路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from trading.ib_trader import IBTrader
from data.data_provider import DataProvider
from strategy_manager import StrategyManager

warnings.filterwarnings('ignore')

def cleanup_old_logs(log_dir: str, days_to_keep: int = 3):
    """
    清理指定天数前的旧日志文件

    参数:
        log_dir: 日志目录路径
        days_to_keep: 保留天数，默认3天
    """
    if not os.path.exists(log_dir):
        return

    # 计算截止日期（三天前）
    cutoff_date = datetime.now() - timedelta(days=days_to_keep)
    deleted_count = 0

    # 匹配日志文件名的正则表达式
    # 支持 trading_YYYYMMDD.log 和 trading_YYYYMMDD_HHMMSS.log 格式
    log_pattern = re.compile(r'trading_(\d{8})(?:_\d{6})?\.log$')

    try:
        for filename in os.listdir(log_dir):
            if not filename.endswith('.log'):
                continue

            match = log_pattern.match(filename)
            if not match:
                continue

            # 提取日期并转换为datetime对象
            date_str = match.group(1)
            try:
                file_date = datetime.strptime(date_str, '%Y%m%d')
            except ValueError:
                continue

            # 删除三天前的文件
            if file_date < cutoff_date:
                file_path = os.path.join(log_dir, filename)
                try:
                    os.remove(file_path)
                    deleted_count += 1
                    print(f"已删除旧日志文件: {filename}")
                except OSError as e:
                    print(f"删除日志文件失败 {filename}: {e}")

        if deleted_count > 0:
            print(f"日志清理完成，共删除 {deleted_count} 个三天前日志文件")

    except Exception as e:
        print(f"日志清理过程中出错: {e}")

# ==================== 全局日志配置 ====================
# 先导入config获取日志配置
import config as config_module

log_config = config_module.CONFIG.get('logging', {})
debug_mode = log_config.get('debug_mode', False)
log_level = logging.DEBUG if debug_mode else logging.INFO

# 根据调试模式决定日志文件名
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)

if debug_mode:
    # 调试模式：每次运行生成带完整时间戳的新日志文件
    log_file = log_config.get('file', os.path.join(log_dir, f'trading_{datetime.now():%Y%m%d_%H%M%S}.log'))
else:
    # 非调试模式：生成每日日期日志文件
    log_file = os.path.join(log_dir, f'trading_{datetime.now():%Y%m%d}.log')

logging.basicConfig(
    level=log_level,
    format=log_config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s'),
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# 清理三天前的旧日志文件
cleanup_old_logs(log_dir)

logger.info(f"日志文件保存在: {os.path.abspath(log_file)}")

def generate_end_of_day_profit_report(target_date=None):
    """
    生成尾盘利润统计报告
    统计各量化策略的买入卖出股票及利润百分比
    计算买入价格vs当前价格 和 卖出价格vs当前价格的利润率

    参数:
        target_date: 指定日期 (datetime.date对象)，如果为None则使用今天
    """
    try:
        # 读取交易记录
        trades_file = 'data/trades.json'
        if not os.path.exists(trades_file):
            logger.warning("交易记录文件不存在")
            return

        with open(trades_file, 'r', encoding='utf-8') as f:
            all_trades = json.load(f)

        # 获取目标日期
        from datetime import datetime, timezone
        if target_date is None:
            target_date = datetime.now(timezone.utc).date()

        # 过滤指定日期的交易
        trades = []
        for trade in all_trades:
            try:
                # 解析交易时间戳
                trade_time = datetime.fromisoformat(trade['timestamp'].replace('Z', '+00:00'))
                if trade_time.date() == target_date:
                    trades.append(trade)
            except (ValueError, KeyError):
                # 如果时间戳格式错误，跳过这条记录
                continue

        logger.info(f"✅ 日期过滤完成: 只统计 {target_date.strftime('%Y-%m-%d')} 当天的交易记录")
        logger.info(f"   找到 {len(trades)} 条当日交易 (总历史记录: {len(all_trades)} 条)")

        # 读取策略映射
        symbol_strategy_map = config_module.CONFIG.get('symbol_strategy_map', {})

        # 初始化数据提供器获取当前价格
        data_provider = None
        try:
            data_provider = DataProvider(
                base_url=config_module.CONFIG.get('data_server', {}).get('base_url', 'http://localhost:8001'),
                max_retries=3
            )
        except Exception as e:
            logger.warning(f"初始化数据提供器失败: {e}，将使用交易记录中的价格作为当前价格")

        # 获取所有涉及的股票列表
        all_symbols = set()
        for trade in trades:
            if trade['status'] == 'EXECUTED':
                all_symbols.add(trade['symbol'])

        # 获取当前价格
        current_prices = {}
        if data_provider and all_symbols:
            try:
                logger.info(f"正在获取 {len(all_symbols)} 个股票的当前价格...")
                for symbol in all_symbols:
                    try:
                        # 获取最近5分钟的数据来获取当前价格
                        df = data_provider.get_intraday_data(symbol, interval='5m', lookback=1)
                        if df is not None and not df.empty:
                            current_prices[symbol] = df['Close'].iloc[-1]
                            logger.debug(f"获取到 {symbol} 当前价格: ${current_prices[symbol]:.2f}")
                        else:
                            logger.warning(f"无法获取 {symbol} 的当前价格")
                    except Exception as e:
                        logger.warning(f"获取 {symbol} 当前价格失败: {e}")
            except Exception as e:
                logger.warning(f"批量获取当前价格失败: {e}")

        logger.info(f"成功获取 {len(current_prices)} 个股票的当前价格")

        # 信号类型到策略的映射
        signal_to_strategy = {
            # A1 动量反转策略
            'MORNING_MOMENTUM': 'a1',
            'AFTERNOON_REVERSAL': 'a1',
            'TECHNICAL_SELL': 'a1',
            'STRONG_TECHNICAL_SELL': 'a1',
            'DYNAMIC_STOP_LOSS': 'a1',
            'FULL_TAKE_PROFIT': 'a1',
            'PARTIAL_TAKE_PROFIT': 'a1',
            'QUICK_LOSS': 'a1',
            'MAX_HOLDING': 'a1',
            'VOLATILITY_EXIT': 'a1',
            'RESISTANCE_SELL': 'a1',
            'MOMENTUM_DECAY': 'a1',

            # A3 双均线成交量突破策略
            'BB_LOWER_BREAKOUT': 'a3',
            'MA_DEATH_CROSS': 'a3',

            # A4 回调交易策略
            'PULLBACK_BUY_UPTREND': 'a4',
            'PULLBACK_SELL_DOWNTREND': 'a4',

            # A5 多因子AI策略
            'MULTIFACTOR_AI_BUY': 'a5',
            'MULTIFACTOR_AI_SELL': 'a5',

            # A7 CTA趋势策略
            'CTA_BREAKOUT_LONG': 'a7',
            'CTA_BREAKDOWN_SHORT': 'a7',

            # A8 RSI震荡策略
            'RSI_OVERSOLD': 'a8',
            'RSI_OVERBOUGHT': 'a8',

            # A9 MACD交叉策略
            'MACD_GOLDEN_CROSS': 'a9',
            'MACD_DEATH_CROSS': 'a9',

            # A10 布林带策略
            'BB_UPPER_BREAKOUT': 'a10',
            'BB_MIDDLE_CROSS': 'a10',

            # A11 移动平均交叉策略
            'MA_GOLDEN_CROSS': 'a11',
            'MA_DEATH_CROSS': 'a11',

            # A12 Stochastic RSI策略
            'STOCH_RSI_OVERSOLD': 'a12',
            'STOCH_RSI_OVERBOUGHT': 'a12',

            # A13 EMA交叉策略
            'EMA_GOLDEN_CROSS': 'a13',
            'EMA_DEATH_CROSS': 'a13',

            # A14 RSI趋势线策略
            'RSI_TRENDLINE_BUY': 'a14',

            # A22 超级趋势策略
            'SUPER_TREND_LONG': 'a22',
            'SUPER_TREND_SHORT': 'a22',

            # A23 Aroon震荡策略
            'AROON_UPTREND': 'a23',
            'AROON_DOWNTREND': 'a23',

            # A24 终极震荡策略
            'ULTIMATE_OVERSOLD': 'a24',
            'ULTIMATE_OVERBOUGHT': 'a24',

            # A25 配对交易策略（增强版）
            'PAIRS_LONG': 'a25',
            'PAIRS_SHORT': 'a25',

            # A26 Williams %R策略
            'WILLIAMS_OVERSOLD': 'a26',
            'WILLIAMS_OVERBOUGHT': 'a26',

            # A27 Minervini趋势策略
            'MINERVINI_BUY': 'a27',
            'MINERVINI_SELL': 'a27',

            # A28 真实强度指数策略
            'TSI_BULLISH': 'a28',
            'TSI_BEARISH': 'a28',

            # A29 随机震荡策略
            'STOCHASTIC_OVERSOLD': 'a29',
            'STOCHASTIC_OVERBOUGHT': 'a29',

            # A30 IBD RS评级策略
            'IBD_HIGH_RS': 'a30',
            'IBD_LOW_RS': 'a30',

            # A31 资金流量指数策略
            'MFI_OVERSOLD': 'a31',
            'MFI_OVERBOUGHT': 'a31',

            # A32 Keltner通道策略
            'KELTNER_BREAKOUT': 'a32',
            'KELTNER_PULLBACK': 'a32',

            # A33 枢轴点策略
            'PIVOT_BREAKOUT': 'a33',
            'PIVOT_SUPPORT': 'a33',

            # A34 线性回归策略
            'LINEAR_REGRESSION_UPTREND': 'a34',
            'LINEAR_REGRESSION_DOWNTREND': 'a34',

            # A35 MLP神经网络策略
            'MLP_PREDICTION_BUY': 'a35',
            'MLP_PREDICTION_SELL': 'a35',
        }

        # 策略统计数据 - 按策略->股票分组，存储交易详情
        strategy_stats = defaultdict(lambda: defaultdict(lambda: {
            'buy_trades': [],  # 存储买入交易详情
            'sell_trades': [], # 存储卖出交易详情
            'executed_trades': 0,
            'failed_trades': 0
        }))

        # 处理每笔交易
        for trade in trades:
            symbol = trade['symbol']
            action = trade['action']
            price = trade['price']
            size = trade['size']
            signal_type = trade['signal_type']
            status = trade['status']

            # 确定策略
            strategy = symbol_strategy_map.get(symbol)
            if not strategy:
                # 尝试从信号类型推断策略
                strategy = signal_to_strategy.get(signal_type)
            if not strategy:
                continue

            if status == 'EXECUTED':
                strategy_stats[strategy][symbol]['executed_trades'] += 1

                # 存储交易详情
                trade_detail = {
                    'price': price,
                    'size': size,
                    'amount': price * size,
                    'timestamp': trade['timestamp'],
                    'position_avg_cost': trade.get('position_avg_cost', 0)
                }

                if action == 'BUY':
                    strategy_stats[strategy][symbol]['buy_trades'].append(trade_detail)
                elif action == 'SELL':
                    strategy_stats[strategy][symbol]['sell_trades'].append(trade_detail)
            else:
                strategy_stats[strategy][symbol]['failed_trades'] += 1

        # 生成报告
        logger.info("\n" + "="*80)
        logger.info("📊 尾盘量化策略利润统计报告")
        logger.info("="*80)
        logger.info(f"报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"统计日期: {target_date.strftime('%Y-%m-%d')}")
        logger.info(f"总交易记录数: {len(trades)}")
        logger.info("")

        total_all_buy = 0.0
        total_all_sell = 0.0
        total_all_profit = 0.0

        # 策略名称映射
        strategy_names = {
            'a1': '动量反转策略',
            'a2': 'Z-Score均值回归',
            'a3': '双均线成交量突破',
            'a4': '回调交易策略',
            'a5': '多因子AI融合',
            'a6': '新闻交易策略',
            'a7': 'CTA趋势跟踪',
            'a8': 'RSI震荡策略',
            'a9': 'MACD交叉策略',
            'a10': '布林带策略',
            'a11': '移动平均交叉',
            'a12': 'Stochastic RSI策略',
            'a13': 'EMA交叉策略',
            'a14': 'RSI趋势线策略',
            'a15': '配对交易策略',
            'a16': 'ROC动量策略',
            'a17': 'CCI顺势策略',
            'a18': 'IsolationForest异常检测策略',
            'a22': '超级趋势策略',
            'a23': 'Aroon震荡策略',
            'a24': '终极震荡策略',
            'a25': '配对交易策略（增强版）',
            'a26': 'Williams %R策略',
            'a27': 'Minervini趋势策略',
            'a28': '真实强度指数策略',
            'a29': '随机震荡策略',
            'a30': 'IBD RS评级策略',
            'a31': '资金流量指数策略',
            'a32': 'Keltner通道策略',
            'a33': '枢轴点策略',
            'a34': '线性回归策略',
            'a35': 'MLP神经网络策略'
        }

        for strategy_code, symbol_stats in strategy_stats.items():
            strategy_name = strategy_names.get(strategy_code, f'策略{strategy_code}')
            strategy_total_buy = 0.0
            strategy_total_sell = 0.0
            strategy_total_profit = 0.0
            strategy_symbols = set()

            logger.info(f"🎯 {strategy_name} ({strategy_code})")
            logger.info(f"   标的数量: {len(symbol_stats)}")

            # 显示每个股票的统计
            for symbol, stats in symbol_stats.items():
                current_price = current_prices.get(symbol, 0)

                # 计算每笔交易的利润（差额 × 数量）
                buy_profit_info = []
                total_buy_profit = 0.0
                total_buy_amount = 0.0
                for i, trade in enumerate(stats['buy_trades']):
                    total_buy_amount += trade['amount']
                    if current_price > 0:
                        # 买入利润 = (当前价格 - 买入价格) × 数量
                        profit_per_share = current_price - trade['price']
                        total_profit = profit_per_share * trade['size']
                        total_buy_profit += total_profit
                        profit_pct = (current_price - trade['price']) / trade['price'] * 100
                        # 提取交易时间 (HH:MM格式)
                        trade_time = trade['timestamp'][11:16]  # HH:MM格式
                        buy_profit_info.append(f"{trade_time} {trade['price']:.2f}→{current_price:.2f} (${total_profit:+.2f}, {profit_pct:+.2f}%)")
                    else:
                        trade_date = trade['timestamp'][:10]
                        buy_profit_info.append(f"{trade_date} {trade['price']:.2f} (无当前价)")

                # 计算卖出交易的利润
                sell_profit_info = []
                total_sell_profit = 0.0
                total_sell_amount = 0.0
                # 使用trades.json中存储的position_avg_cost（用于持仓成本利润计算）
                avg_buy_cost = 0
                if stats['sell_trades']:
                    # 从卖出交易中获取position_avg_cost
                    avg_buy_cost = stats['sell_trades'][0].get('position_avg_cost', 0)

                for i, trade in enumerate(stats['sell_trades']):
                    total_sell_amount += trade['amount']
                    if current_price > 0:
                        # 卖出利润 = (卖出价格 - 当前价格) × 数量
                        profit_per_share = trade['price'] - current_price
                        total_profit = profit_per_share * trade['size']
                        total_sell_profit += total_profit
                        profit_pct = (current_price - trade['price']) / trade['price'] * 100
                        trade_time = trade['timestamp'][11:16]
                        sell_profit_info.append(f"{trade_time} {trade['price']:.2f}→{current_price:.2f} (${total_profit:+.2f}, {profit_pct:+.2f}%)")

                        # 添加持仓成本利润计算（使用trades.json中的position_avg_cost）
                        position_avg_cost = trade.get('position_avg_cost', 0)
                        if position_avg_cost > 0:
                            position_profit_per_share = trade['price'] - position_avg_cost
                            position_total_profit = position_profit_per_share * trade['size']
                            sell_profit_info.append(f"  持仓成本利润: ({trade['price']:.2f} - {position_avg_cost:.2f}) × {trade['size']} = ${position_total_profit:+.2f}")
                    else:
                        trade_date = trade['timestamp'][:10]
                        sell_profit_info.append(f"{trade_date} {trade['price']:.2f} (无当前价)")

                # 股票总利润 = 买入利润 + 卖出利润
                stock_total_profit = total_buy_profit + total_sell_profit

                strategy_total_buy += total_buy_amount
                strategy_total_sell += total_sell_amount
                strategy_total_profit += stock_total_profit
                strategy_symbols.add(symbol)

                # 计算总股数
                total_buy_shares = sum(trade['size'] for trade in stats['buy_trades'])
                total_sell_shares = sum(trade['size'] for trade in stats['sell_trades'])

                logger.info(f"   📈 {symbol} (当前价: ${current_price:.2f}):")
                if stats['buy_trades']:
                    logger.info(f"      买入: {len(stats['buy_trades'])}笔 {total_buy_shares}股 总额${total_buy_amount:,.2f}")
                    for info in buy_profit_info:
                        logger.info(f"         {info}")
                if stats['sell_trades']:
                    logger.info(f"      卖出: {len(stats['sell_trades'])}笔 {total_sell_shares}股 总额${total_sell_amount:,.2f}")
                    for info in sell_profit_info:
                        logger.info(f"         {info}")

                logger.info(f"      总利润: ${stock_total_profit:,.2f}")

            # 策略汇总
            strategy_profit_pct = (strategy_total_profit / strategy_total_buy * 100) if strategy_total_buy > 0 else 0.0
            total_executed = sum(stats['executed_trades'] for stats in symbol_stats.values())
            total_failed = sum(stats['failed_trades'] for stats in symbol_stats.values())

            logger.info(f"   📊 策略汇总:")
            logger.info(f"      总买入: ${strategy_total_buy:,.2f}")
            logger.info(f"      总卖出: ${strategy_total_sell:,.2f}")
            logger.info(f"      总利润: ${strategy_total_profit:,.2f} ({strategy_profit_pct:+.2f}%)")
            logger.info(f"      执行成功: {total_executed}笔, 失败: {total_failed}笔")
            logger.info("")

            total_all_buy += strategy_total_buy
            total_all_sell += strategy_total_sell
            total_all_profit += strategy_total_profit

        # 总计
        total_profit_pct = (total_all_profit / total_all_buy * 100) if total_all_buy > 0 else 0.0

        logger.info("="*80)
        logger.info("📈 全策略汇总")
        logger.info(f"   总买入金额: ${total_all_buy:,.2f}")
        logger.info(f"   总卖出金额: ${total_all_sell:,.2f}")
        logger.info(f"   总利润: ${total_all_profit:,.2f} ({total_profit_pct:+.2f}%)")
        logger.info(f"   参与策略数: {len(strategy_stats)}")
        logger.info("="*80)

        # 保存报告到文件
        report_file = f"logs/profit_report_{target_date.strftime('%Y%m%d')}_{datetime.now().strftime('%H%M%S')}.txt"
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("尾盘量化策略利润统计报告\n")
            f.write(f"报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"统计日期: {target_date.strftime('%Y-%m-%d')}\n\n")

            for strategy_code, symbol_stats in strategy_stats.items():
                strategy_name = strategy_names.get(strategy_code, f'策略{strategy_code}')
                f.write(f"{strategy_name} ({strategy_code}):\n")

                strategy_total_buy = 0.0
                strategy_total_sell = 0.0
                strategy_total_profit = 0.0

                # 显示每个股票的统计
                for symbol, stats in symbol_stats.items():
                    current_price = current_prices.get(symbol, 0)

                    # 计算每笔交易的利润（差额 × 数量）
                    buy_profit_info = []
                    total_buy_profit = 0.0
                    total_buy_amount = 0.0
                    for trade in stats['buy_trades']:
                        total_buy_amount += trade['amount']
                        if current_price > 0:
                            profit_per_share = current_price - trade['price']
                            total_profit = profit_per_share * trade['size']
                            total_buy_profit += total_profit
                            profit_pct = (current_price - trade['price']) / trade['price'] * 100
                            trade_time = trade['timestamp'][11:16]
                            buy_profit_info.append(f"{trade_time} {trade['price']:.2f}→{current_price:.2f} (${total_profit:+.2f}, {profit_pct:+.2f}%)")
                        else:
                            trade_date = trade['timestamp'][:10]
                            buy_profit_info.append(f"{trade_date} {trade['price']:.2f} (无当前价)")

                    # 计算卖出交易的利润
                    sell_profit_info = []
                    total_sell_profit = 0.0
                    total_sell_amount = 0.0

                    # 使用trades.json中存储的position_avg_cost（用于持仓成本利润计算）
                    avg_buy_cost = 0
                    if stats['sell_trades']:
                        # 从卖出交易中获取position_avg_cost
                        avg_buy_cost = stats['sell_trades'][0].get('position_avg_cost', 0)

                    for trade in stats['sell_trades']:
                        total_sell_amount += trade['amount']
                        if current_price > 0:
                            profit_per_share = trade['price'] - current_price
                            total_profit = profit_per_share * trade['size']
                            total_sell_profit += total_profit
                            profit_pct = (current_price - trade['price']) / trade['price'] * 100
                            trade_time = trade['timestamp'][11:16]
                            sell_profit_info.append(f"{trade_time} {trade['price']:.2f}→{current_price:.2f} (${total_profit:+.2f}, {profit_pct:+.2f}%)")

                            # 添加持仓成本利润计算（使用trades.json中的position_avg_cost）
                            position_avg_cost = trade.get('position_avg_cost', 0)
                            if position_avg_cost > 0:
                                position_profit_per_share = trade['price'] - position_avg_cost
                                position_total_profit = position_profit_per_share * trade['size']
                                sell_profit_info.append(f"  持仓成本利润: ({trade['price']:.2f} - {position_avg_cost:.2f}) × {trade['size']} = ${position_total_profit:+.2f}")
                        else:
                            trade_date = trade['timestamp'][:10]
                            sell_profit_info.append(f"{trade_date} {trade['price']:.2f} (无当前价)")

                    stock_total_profit = total_buy_profit + total_sell_profit

                    strategy_total_buy += total_buy_amount
                    strategy_total_sell += total_sell_amount
                    strategy_total_profit += stock_total_profit

                    # 计算总股数
                    total_buy_shares = sum(trade['size'] for trade in stats['buy_trades'])
                    total_sell_shares = sum(trade['size'] for trade in stats['sell_trades'])

                    f.write(f"  {symbol} (当前价: ${current_price:.2f}):\n")
                    if stats['buy_trades']:
                        f.write(f"    买入: {len(stats['buy_trades'])}笔 {total_buy_shares}股 总额${total_buy_amount:,.2f}\n")
                        for info in buy_profit_info:
                            f.write(f"      {info}\n")
                    if stats['sell_trades']:
                        f.write(f"    卖出: {len(stats['sell_trades'])}笔 {total_sell_shares}股 总额${total_sell_amount:,.2f}\n")
                        for info in sell_profit_info:
                            f.write(f"      {info}\n")

                    f.write(f"    总利润: ${stock_total_profit:,.2f}\n")

                # 策略汇总
                strategy_profit_pct = (strategy_total_profit / strategy_total_buy * 100) if strategy_total_buy > 0 else 0.0
                f.write(f"  策略汇总:\n")
                f.write(f"    总买入: ${strategy_total_buy:,.2f}\n")
                f.write(f"    总卖出: ${strategy_total_sell:,.2f}\n")
                f.write(f"    总利润: ${strategy_total_profit:,.2f} ({strategy_profit_pct:+.2f}%)\n\n")

            f.write("汇总:\n")
            f.write(f"  总买入: ${total_all_buy:,.2f}\n")
            f.write(f"  总卖出: ${total_all_sell:,.2f}\n")
            f.write(f"  总利润: ${total_all_profit:,.2f} ({total_profit_pct:+.2f}%)\n")

        logger.info(f"✅ 利润报告已保存到: {report_file}")

    except Exception as e:
        logger.error(f"生成利润报告时出错: {e}")
        import traceback
        logger.debug(traceback.format_exc())

# ==================== 策略工厂 ====================
class StrategyFactory:
    """策略工厂，用于创建和切换策略"""

    @classmethod
    def create_strategy(cls, strategy_name: str, config: Dict = None, ib_trader = None):
        """
        创建策略实例

        参数:
            strategy_name: 策略名称 ('a1' 或 'a2')
            config: 策略配置
            ib_trader: IB交易接口

        返回:
            策略实例
        """
        from strategy_manager import STRATEGY_CLASSES

        if strategy_name not in STRATEGY_CLASSES:
            raise ValueError(f"未知的策略: {strategy_name}。可用策略: {list(STRATEGY_CLASSES.keys())}")

        strategy_class = STRATEGY_CLASSES[strategy_name]
        return strategy_class(config=config, ib_trader=ib_trader)
    
    @classmethod
    def list_strategies(cls) -> List[str]:
        """获取所有可用策略列表"""
        from strategy_manager import STRATEGY_CLASSES
        return list(STRATEGY_CLASSES.keys())
    
    @classmethod
    def get_strategy_description(cls, strategy_name: str) -> str:
        """获取策略描述"""
        descriptions = {
            'a1': '动量反转策略 - 基于早盘动量/午盘反转信号',
            'a2': 'Z-Score均值回归策略 - 基于统计套利',
            'a3': '双均线成交量突破策略 - 基于趋势突破',
            'a4': '回调交易策略 - 基于斐波那契回撤',
            'a5': '多因子AI融合策略 - 整合流动性、基本面、情绪、动量',
            'a6': '新闻交易策略 - 基于实时新闻情绪分析',
            'a7': 'CTA趋势跟踪策略 - 基于唐奇安通道突破',
            'a8': 'RSI震荡策略 - 基于相对强弱指数超买超卖',
            'a9': 'MACD交叉策略 - 基于MACD线条交叉信号',
            'a10': '布林带策略 - 基于布林带价格突破',
            'a11': '均线交叉策略 - 基于移动平均线交叉',
            'a12': 'Stochastic RSI策略 - 结合随机指标和RSI的增强震荡策略',
            'a13': 'EMA交叉策略 - 基于指数移动平均线交叉的多资产组合策略',
            'a14': 'RSI趋势线策略 - 基于RSI和长期趋势的筛选策略',
            'a15': '配对交易策略 - 基于协整关系的统计套利策略',
            'a16': 'ROC动量策略 - 基于价格变化率的动量指标',
            'a17': 'CCI顺势策略 - 基于顺势指标的超买超卖策略',
            'a18': 'IsolationForest异常检测策略 - 基于机器学习的异常价格检测',
            'a22': '超级趋势策略 - 基于ATR和趋势跟踪的突破策略',
            'a23': 'Aroon震荡策略 - 基于Aroon指标的趋势和震荡分析',
            'a24': '终极震荡策略 - 结合动量、体积和价格的综合指标',
            'a25': '配对交易策略 - 基于协整关系的统计套利策略（增强版）',
            'a26': 'Williams %R策略 - 基于威廉指标的超买超卖策略',
            'a27': 'Minervini趋势策略 - 基于Mark Minervini八条趋势原则',
            'a28': '真实强度指数策略 - 结合价格和成交量的动量指标',
            'a29': '随机震荡策略 - 基于随机指标的超买超卖策略',
            'a30': 'IBD RS评级策略 - 基于Investor\'s Business Daily相对强度',
            'a31': '资金流量指数策略 - 基于成交量和价格的资金流向分析',
            'a32': 'Keltner通道策略 - 基于ATR的波动率通道策略',
            'a33': '枢轴点策略 - 基于支撑阻力位的突破策略',
            'a34': '线性回归策略 - 基于价格趋势线的统计分析',
            'a35': 'MLP神经网络策略 - 基于多层感知器的机器学习预测',
        }
        return descriptions.get(strategy_name, '未知策略')

# ==================== 主交易系统 ====================
class TradingSystem:
    """主交易系统控制器"""
    
    def __init__(self, config_file: str = None, strategy_name: str = 'a1'):
        # 初始化配置模块引用
        self.config_module = None

        self.config = self._load_config(config_file)
        self.start_time = datetime.now()

        # 初始化组件
        self.data_provider = None
        self.ib_trader = None
        self.strategy = None
        self.current_strategy_name = strategy_name
        
        # 系统状态
        self.is_running = False
        self.cycle_count = 0
        self.last_signals = {}
        self.config_needs_reload = False
        
        logger.info("=" * 70)
        logger.info("多策略日内交易系统")
        logger.info(f"当前策略: {strategy_name} - {StrategyFactory.get_strategy_description(strategy_name)}")
        logger.info("=" * 70)
        logger.info(f"日志文件: {log_file}")
    
    def _load_config(self, config_file: str = None, force_reload: bool = False) -> Dict:
        """加载配置"""
        # 默认配置（作为后备）
        default_strategy_config = {
            'initial_capital': 100000.0,
            'risk_per_trade': 0.01,
            'max_position_size': 0.05,
            'ib_order_type': 'MKT',
            'ib_limit_offset': 0.01,
            'min_cash_buffer': 0.3,
            'per_trade_notional_cap': 10000.0,
            'max_position_notional': 60000.0,
            'max_active_positions': 5,
            'default_max_signals_per_cycle': 3,
            'max_signals_per_cycle': {
                'a2': 2,
            }
        }

        # 首先尝试从 config.py 加载配置
        try:
            if self.config_module and force_reload:
                # 重新加载已导入的模块
                self.config_module = importlib.reload(self.config_module)
                logger.info("🔄 已重新加载 config.py")
            elif not self.config_module:
                # 首次导入
                import config as global_config
                self.config_module = global_config
                logger.info("✅ 从 config.py 加载配置")
            else:
                # 使用已缓存的模块
                global_config = self.config_module

            if hasattr(global_config, 'CONFIG'):
                # 使用全局配置，但保留默认值作为后备
                config = global_config.CONFIG.copy()
                # 确保必要的配置键存在
                if 'trading' not in config:
                    config['trading'] = {}
                if 'strategy' not in config:
                    config['strategy'] = default_strategy_config
                    logger.info("   使用默认 strategy 配置")
                return config
        except Exception as e:
            logger.warning(f"从 config.py 加载配置失败: {e}，使用默认配置")
        
        # 如果加载失败，使用默认配置
        default_config = {
            'data_server': {
                'base_url': 'http://localhost:8001',
                'retry_attempts': 3
            },
            'ib_server': {
                'host': '127.0.0.1',
                'port': 7497,
                'client_id': 1
            },
            'trading': {
#                 'symbols': [
#     # A1 动量反转（原 5 + 新增 2）
#     'AMD', 'META', 'INTC', 'RIVN', 'COIN',
#     'SQ', 'ZM',

#     # A2 Z-Score 均值回归（原 5 + 新增 2）
#     'XOM', 'CVX', 'JPM', 'PFE', 'JNJ',
#     'BAC', 'GS',

#     # A3 双均线量能（原 5 + 新增 2）
#     'TEAM', 'GOOGL', 'WDC', 'CRM', 'ORCL',
#     'AVGO', 'IBM',

#     # A4 回调买入（原 5 + 新增 2）
#     'AMZN', 'BKNG', 'TSLA', 'NFLX', 'DIS',
#     'NKE', 'SBUX',

#     # A5 多因子 AI（原 5 + 新增 2）
#     'NVDA', 'MSFT', 'ETN', 'SNOW', 'AI',
#     'PLTR', 'DDOG',

#     # A7 CTA 趋势（原 5 + 新增 2）
#     'OKLO', 'SMCI', 'LEU', 'TSM', 'BA',
#     'ASML', 'LLY'
# ]
# ,
                'scan_interval_minutes': 1,
                'trading_hours': {
                    'start': '00:00',
                    'end': '15:45'
                },
                'close_all_positions_before_market_close': False,
                'close_positions_time': '15:45'
            },
            'strategy': default_strategy_config
        }
        
        return default_config
    
    def initialize(self, strategy_name: str = None) -> bool:
        """初始化系统"""
        logger.info("\n初始化交易系统...")
        
        # 如果指定了新策略，切换策略
        if strategy_name and strategy_name != self.current_strategy_name:
            logger.info(f"切换到策略: {strategy_name}")
            self.current_strategy_name = strategy_name
        
        # 1. 初始化数据提供器
        data_config = self.config['data_server']
        self.data_provider = DataProvider(
            base_url=data_config['base_url'],
            max_retries=data_config.get('retry_attempts', 3)
        )
        
        # 2. 初始化IB交易接口
        ib_config = self.config['ib_server']
        self.ib_trader = IBTrader(
            host=ib_config['host'],
            port=ib_config['port'],
            client_id=ib_config['client_id'],
            manual_available_funds=ib_config.get('manual_available_funds')
        )
        
        # 连接IB
        if not self.ib_trader.connect():
            logger.warning("⚠️  IB连接失败，将使用模拟交易模式")
            self.ib_trader = None
        
        # 3. 初始化策略
        strategy_config = self.config['strategy']
        self.strategy = StrategyFactory.create_strategy(
            self.current_strategy_name, 
            strategy_config, 
            self.ib_trader
        )
        
        logger.info(f"\n✅ 系统初始化完成")
        logger.info(f"当前策略: {self.strategy.get_strategy_name()}")
        logger.info(f"交易标的: {', '.join(self.config['trading']['symbols'][:5])}...")
        logger.info(f"扫描间隔: {self.config['trading']['scan_interval_minutes']} 分钟")
        logger.info(f"交易时间: {self.config['trading']['trading_hours']['start']} - "
                   f"{self.config['trading']['trading_hours']['end']}")
        logger.info(f"IB连接: {'✅ 成功' if self.ib_trader and self.ib_trader.connected else '❌ 失败/模拟'}")

        # 输出IB账户资产信息
        if self.ib_trader and self.ib_trader.connected:
            try:
                logger.info("\n💰 IB账户资产信息:")
                net_liq = self.ib_trader.get_net_liquidation()
                available = self.ib_trader.get_available_funds()
                logger.info(f"  净资产 (Net Liquidation): ${net_liq:,.2f}")
                logger.info(f"  可用资金 (Available Funds): ${available:,.2f}")

                # 获取并显示更多账户信息
                account_summary = self.ib_trader.get_account_summary()
                if account_summary:
                    logger.info("  详细账户信息:")
                    key_fields = ['TotalCashValue', 'BuyingPower', 'TotalCashBalance', 'GrossPositionValue', 'UnrealizedPnL']
                    for field in key_fields:
                        if field in account_summary:
                            value = account_summary[field]['value']
                            currency = account_summary[field]['currency']
                            logger.info(f"    {field}: {value} {currency}")
            except Exception as e:
                logger.warning(f"获取IB账户资产信息失败: {e}")
        else:
            logger.info("IB未连接，跳过账户资产信息显示")
        
        return True
    
    def switch_strategy(self, new_strategy_name: str):
        """
        切换策略
        
        参数:
            new_strategy_name: 新策略名称 ('a1' 或 'a2')
        """
        if new_strategy_name == self.current_strategy_name:
            logger.info(f"已是当前策略: {new_strategy_name}")
            return
        
        if new_strategy_name not in StrategyFactory.list_strategies():
            logger.error(f"未知的策略: {new_strategy_name}")
            logger.info(f"可用策略: {StrategyFactory.list_strategies()}")
            return
        
        logger.info(f"正在切换策略: {self.current_strategy_name} -> {new_strategy_name}")
        
        # 保存当前策略状态
        if self.strategy:
            logger.info(f"保存 {self.strategy.get_strategy_name()} 的交易历史...")
            # 这里可以添加保存策略状态的逻辑
        
        # 创建新策略
        self.current_strategy_name = new_strategy_name
        strategy_config = self.config['strategy']
        self.strategy = StrategyFactory.create_strategy(
            new_strategy_name, 
            strategy_config, 
            self.ib_trader
        )
        
        logger.info(f"✅ 策略切换完成")
        logger.info(f"新策略: {self.strategy.get_strategy_name()}")
        logger.info(f"策略描述: {StrategyFactory.get_strategy_description(new_strategy_name)}")
    
    def _get_eastern_time(self) -> datetime:
        """获取当前美东时间"""
        if HAS_PYTZ:
            try:
                eastern = pytz.timezone('US/Eastern')
                return datetime.now(eastern)
            except Exception as e:
                logger.warning(f"获取美东时间失败: {e}，使用本地时间")
                return datetime.now()
        else:
            # 如果没有pytz，使用本地时间（假设本地时间就是美东时间）
            return datetime.now()
    
    def _within_trading_hours(self) -> bool:
        """检查是否在交易时间内"""
        hours = self.config['trading']['trading_hours']
        start = datetime.strptime(hours['start'], '%H:%M').time()
        end = datetime.strptime(hours['end'], '%H:%M').time()
        current = self._get_eastern_time().time()
        
        return start <= current <= end
    
    def _check_and_reconnect_ib(self) -> bool:
        """检查IB连接状态，如果断开则尝试重连"""
        if not self.ib_trader:
            logger.debug("IB交易接口未初始化")
            return False
        
        # 检查连接健康状态
        if self.ib_trader.is_connection_healthy():
            return True
        
        # 连接异常，尝试重连
        logger.warning("⚠️  IB连接异常，尝试重连...")
        if self.ib_trader.reconnect():
            logger.info("✅ IB重连成功")
            # 更新策略中的ib_trader引用
            if self.strategy:
                self.strategy.ib_trader = self.ib_trader
            return True
        else:
            logger.error("❌ IB重连失败，本周期将跳过需要IB的操作")
            return False
    
    def trading_cycle(self):
        """交易循环"""
        if not self.is_running:
            logger.warning("📭 系统未运行")
            return
        
        self.cycle_count += 1

        # 检查是否需要重新加载配置
        if self.config_needs_reload:
            logger.info("🔄 检测到配置更新请求，重新加载配置...")
            self.config = self._load_config(force_reload=True)
            self.config_needs_reload = False
            logger.info("✅ 配置已重新加载")

        # 检查外部重新加载请求（API调用后）
        if os.path.exists('config/.reload_needed'):
            try:
                with open('config/.reload_needed', 'r') as f:
                    reason = f.read().strip()
                logger.info(f"🔄 检测到外部配置更新请求: {reason}，重新加载配置...")
                self.config = self._load_config(force_reload=True)
                os.remove('config/.reload_needed')
                logger.info("✅ 配置已重新加载")
            except Exception as e:
                logger.warning(f"处理重新加载请求失败: {e}")

        current_time = self._get_eastern_time()  # 使用美东时间
        local_time = datetime.now()
        
        logger.info(f"\n{'='*60}")
        logger.info(f"交易周期 #{self.cycle_count} - 美东时间: {current_time.strftime('%Y-%m-%d %H:%M:%S')} (本地: {local_time.strftime('%H:%M:%S')})")
        logger.info(f"当前策略: {self.strategy.get_strategy_name()}")
        logger.info('='*60)
        
        # 检查并确保IB连接正常
        ib_connected = self._check_and_reconnect_ib()
        if not ib_connected:
            logger.warning("⚠️  IB未连接，本周期将跳过需要IB的操作（如清仓、下单等）")
        
        # 检查是否需要收盘前清仓
        close_positions_enabled = self.config['trading'].get('close_all_positions_before_market_close', False)
        close_time_str = self.config['trading'].get('close_positions_time', '15:45')
        
        logger.info(f"🔍 清仓配置检查: enabled={close_positions_enabled}, time={close_time_str}")
        
        if not close_positions_enabled:
            logger.warning(f"⏰ 收盘前清仓功能未启用 (close_all_positions_before_market_close=False)")
            logger.warning(f"   如需启用，请在config.py中设置: 'close_all_positions_before_market_close': True")
        else:
            try:
                close_time = datetime.strptime(close_time_str, '%H:%M').time()
                current_time_only = current_time.time()
                
                logger.info(f"⏰ 清仓检查: 当前美东时间={current_time_only.strftime('%H:%M:%S')}, 清仓时间={close_time_str}")
                logger.info(f"   时间比较结果: {current_time_only} >= {close_time} = {current_time_only >= close_time}")
                
                # 检查是否到达清仓时间
                if current_time_only >= close_time:
                    logger.info(f"⏰ 到达清仓时间 ({close_time_str})，开始清仓所有持仓...")
                    
                    # 确保IB连接正常才能执行清仓
                    if not ib_connected:
                        logger.error("❌ IB未连接，无法执行清仓操作，请检查IB连接")
                        # 继续执行其他逻辑，但跳过清仓
                    else:
                        # 清仓所有持仓（支持单策略和多策略模式）
                        try:
                            import config as global_config
                            symbol_map = global_config.CONFIG.get('symbol_strategy_map')
                            
                            if symbol_map and self.ib_trader:
                                # 多策略模式：从IB获取所有持仓，按策略分组清仓
                                try:
                                    all_holdings = self.ib_trader.get_holdings()
                                    if all_holdings:
                                        # 按策略分组持仓
                                        strategy_positions = {}
                                        for pos in all_holdings:
                                            symbol = pos.contract.symbol
                                            strat_name = symbol_map.get(symbol, self.current_strategy_name)
                                            if strat_name not in strategy_positions:
                                                strategy_positions[strat_name] = []
                                            strategy_positions[strat_name].append(symbol)
                                        
                                        # 为每个策略清仓
                                        for strat_name, symbols in strategy_positions.items():
                                            try:
                                                cfg_key = global_config.STRATEGY_CONFIG_MAP.get(strat_name)
                                                strat_cfg = global_config.CONFIG.get(cfg_key, {}) if cfg_key else {}
                                                strat_instance = StrategyFactory.create_strategy(strat_name, config=strat_cfg, ib_trader=self.ib_trader)
                                                strat_instance.close_all_positions(reason=f"收盘前清仓 ({close_time_str})")
                                            except Exception as e:
                                                logger.error(f"清仓策略 {strat_name} 时出错: {e}")
                                    else:
                                        logger.info("当前无持仓，无需清仓")
                                except Exception as e:
                                    logger.error(f"获取持仓信息失败: {e}，尝试使用当前策略清仓")
                                    self.strategy.close_all_positions(reason=f"收盘前清仓 ({close_time_str})")
                            else:
                                # 单策略模式：直接清仓当前策略
                                self.strategy.close_all_positions(reason=f"收盘前清仓 ({close_time_str})")
                        except Exception as e:
                            logger.error(f"执行收盘前清仓时出错: {e}")
                            import traceback
                            logger.debug(traceback.format_exc())
                        
                        # 清仓后，本周期不再执行其他交易逻辑
                        logger.info("✅ 清仓完成，本周期结束")

                        # 生成尾盘利润统计报告
                        generate_end_of_day_profit_report()
                        return
                else:
                    time_diff = (datetime.combine(datetime.today(), close_time) - 
                                datetime.combine(datetime.today(), current_time_only)).total_seconds() / 60
                    if time_diff > 0:
                        logger.debug(f"   距离清仓时间还有 {int(time_diff)} 分钟")
                    else:
                        logger.warning(f"   时间比较异常: 当前时间 {current_time_only} vs 清仓时间 {close_time}")
            except Exception as e:
                logger.warning(f"❌ 解析清仓时间配置失败: {e}")
                import traceback
                logger.debug(traceback.format_exc())
        
        # 检查交易时间
        allow_outside_hours = self.config['trading'].get('allow_orders_outside_trading_hours', False)
        if not self._within_trading_hours():
            if not allow_outside_hours:
                logger.info("⏸️  非交易时间，跳过...")
                return
            else:
                logger.info("⏸️  非交易时间，继续执行（策略将使用市价单）...")
        
        # 周期开始前取消所有未完成委托 (如果配置启用)
        if self.config['trading'].get('auto_cancel_orders', True):
            if self.ib_trader and self.ib_trader.connected:
                try:
                    # 先查询并更新订单状态到 trades.json
                    logger.info("查询订单状态并更新交易记录...")
                    updated = self.ib_trader.update_pending_trade_statuses()
                    if updated > 0:
                        logger.info(f"✅ 已更新 {updated} 个订单状态")
                    
                    # 然后取消所有未完成订单
                    self.ib_trader.cancel_all_orders_global()
                    cancelled = self.ib_trader.cancel_open_orders()
                    if cancelled:
                        logger.info(f"本周期开始已取消 {cancelled} 个未完成委托")
                except Exception as e:
                    logger.warning(f"取消未完成委托失败: {e}")

        
        
        # 获取市场状态
        market_status = self.data_provider.get_market_status()
        if not market_status['server_available']:
            logger.error("❌ 数据服务器不可用")
            return
        
        logger.info(f"市场状态: 服务器可用 - {market_status['server_available']}, "
                   f"可用标的: {len(market_status['symbols_available'])}")
        
        # 打印IB账户信息
        if self.ib_trader and self.ib_trader.connected:
            net_liq = self.ib_trader.get_net_liquidation()
            available = self.ib_trader.get_available_funds()
            logger.info(f"IB账户 - 净资产: ${net_liq:,.2f}, 可用资金: ${available:,.2f}")

            # 打印完整账户摘要用于调试
            if available == 0:
                logger.info("检测到可用资金为0，打印完整账户摘要进行诊断...")
                self.ib_trader.print_account_summary()
        
        # 运行策略分析
        symbols = self.config['trading']['symbols']

        # 如果配置中存在 symbol->strategy 映射，则使用 StrategyManager 并行执行各自策略
        try:
            import config as global_config
            symbol_map = global_config.CONFIG.get('symbol_strategy_map')
        except Exception:
            symbol_map = None

        if symbol_map:
            from queue import Queue, Empty
            mgr = StrategyManager(self.data_provider, self.ib_trader, config=global_config.CONFIG)
            signal_queue = Queue()
            # 启动流式运行，工作线程会把信号放入 signal_queue，主线程可即时消费
            executor, futures = mgr.stream_run(symbols, signal_queue)
            signals = {}
        else:
            # 单策略模式 - force_market_orders已在策略初始化时设置
            try:
                signals = self.strategy.run_analysis_cycle(self.data_provider, symbols)
            except Exception as e:
                logger.error(f"策略运行出错: {e}")
                import traceback
                logger.error(f"详细错误: {traceback.format_exc()}")
                signals = {}
        
        # 处理信号：流式模式下主线程即时消费 signal_queue 并执行下单
        if symbol_map and self.ib_trader:
            # 多策略模式已在上面处理
            from queue import Empty
            logger.info("开始在主线程即时消费信号队列并下单")
            # 在工作线程运行期间，持续消费队列
            try:
                # 只要还有未完成的 future，就尝试获取队列中的信号并执行
                import concurrent.futures
                while True:
                    # 处理队列中所有可用的信号
                    try:
                        sym, sig = signal_queue.get(timeout=0.8)
                    except Empty:
                        # 若队列空，检查是否所有 futures 已完成
                        if all(f.done() for f in futures):
                            break
                        else:
                            continue
                    indicators_get=sig.get('indicators_get')
                    df=sig.get('df')
                    data_provider=sig.get('data_provider')
                    
                    # 立刻为该信号创建带 IB 的策略执行实例并下单
                    origin = sig.get('origin_strategy') or symbol_map.get(sym) or self.current_strategy_name
                    try:
                        cfg_key = global_config.STRATEGY_CONFIG_MAP.get(origin)
                        strat_cfg = global_config.CONFIG.get(cfg_key, {}) if cfg_key else {}
                    except Exception:
                        strat_cfg = {}
                    try:
                        exec_strategy = StrategyFactory.create_strategy(origin, config=strat_cfg, ib_trader=self.ib_trader)
                    except Exception:
                        exec_strategy = self.strategy if self.strategy else StrategyFactory.create_strategy(self.current_strategy_name, config=strat_cfg, ib_trader=self.ib_trader)

                    try:
                        exec_strategy.sync_positions_from_ib()
                    except Exception:
                        pass

                    current_price = sig.get('price')
                    if current_price is None:
                        try:
                            df = self.data_provider.get_intraday_data(sym, interval='5m', lookback=1)
                            if df is not None and not df.empty:
                                current_price = df['Close'].iloc[-1]
                        except Exception:
                            current_price = sig.get('price', 0)

                    try:
                        atr = None
                        if isinstance(sig.get('indicators'), dict) and sig['indicators'].get('ATR'):
                            atr = sig['indicators'].get('ATR')
                        if atr is None:
                            try:
                                df = self.data_provider.get_intraday_data(sym, interval='5m', lookback=30)
                                if df is not None and not df.empty:
                                    atr = (df['High'].rolling(20).max().iloc[-1] - df['Low'].rolling(20).min().iloc[-1]) / 20
                            except Exception:
                                atr = None

                        new_size = exec_strategy.calculate_position_size(sig, atr)
                        sig['position_size'] = new_size
                    except Exception as e:
                        logger.warning(f"重新计算仓位失败 ({sym}): {e}")

                    try:
                        result = exec_strategy.execute_signal(sig, current_price)
                        logger.info(f"执行信号结果1: {sym} {sig['action']} -> {result.get('status')}, 原因: {result.get('reason','')}")
                    except Exception as e:
                        logger.error(f"执行信号出错 {sym}: {e}")
                        
                   # 所有策略都生成信号（使用相同的df和indicators）
                    from config import STRATEGY_CONFIG_MAP
                    all_strategies = list(STRATEGY_CONFIG_MAP.keys())
                    all_signals = {}
                    
                    for strategy_name in all_strategies:
                        try:
                            # 获取策略配置
                            cfg_key = STRATEGY_CONFIG_MAP.get(strategy_name)
                            strat_cfg = config_module.CONFIG.get(cfg_key, {}) if cfg_key else {}
                            # 创建策略实例
                            from main import StrategyFactory
                            exec_strategy = StrategyFactory.create_strategy(strategy_name, config=strat_cfg, ib_trader=self.ib_trader)
                            # 使用该策略生成信号
                            signals = exec_strategy.generate_signals(sym, df, indicators_get)
                            if signals:
                                if sym not in all_signals:
                                    all_signals[sym] = []
                                all_signals[sym].extend(signals)
                                logger.info(f"[base_strategy]  {sym} + {strategy_name} 生成 {len(signals)} 个信号")
                        except Exception as e:
                            logger.info(f"[base_strategy]策略 {strategy_name} 处理 {sym} 时出错: {e}")
                            continue
                   
                     # 对preselect_a2的所有股票生成信号并保存到新文件
                     
                    try:
                        logger.info(f"🔄 [base_strategy]开始执行preselect信号生成，当前all_signals长度: {sum(len(signals) for signals in all_signals.values())}")
                        self._generate_preselect_signals(data_provider, all_signals)
                        logger.info(f"✅ [base_strategy]preselect信号生成完成，更新后all_signals长度: {sum(len(signals) for signals in all_signals.values())}")
                        self._save_signals_to_csv(all_signals)
                    except Exception as e:
                        logger.info(f"[base_strategy]执行preselect信号生成时出错: {e}")
                        import traceback
                        logger.info(f"[base_strategy]: {traceback.format_exc()}")
                    logger.info(f"🏁 [base_strategy]run_analysis_cycle 执行完成，返回信号数量: {sum(len(signals) for signals in all_signals.values())}")
                    

                        
                # 所有 futures 完成后，drain队列以处理残留
                while True:
                    try:
                        sym, sig = signal_queue.get_nowait()
                    except Empty:
                        break
                    try:
                        

                        
                        
                        origin = sig.get('origin_strategy') or symbol_map.get(sym) or self.current_strategy_name
                        cfg_key = global_config.STRATEGY_CONFIG_MAP.get(origin)
                        strat_cfg = global_config.CONFIG.get(cfg_key, {}) if cfg_key else {}
                        exec_strategy = StrategyFactory.create_strategy(origin, config=strat_cfg, ib_trader=self.ib_trader)
                        # exec_strategy.force_market_orders = force_market_orders
                        self.force_market_orders = not self._within_trading_hours()
                        exec_strategy.sync_positions_from_ib()
                        current_price = sig.get('price') or 0
                        atr = None
                        new_size = exec_strategy.calculate_position_size(sig, atr)
                        sig['position_size'] = new_size
                        result = exec_strategy.execute_signal(sig, current_price)
                        
                        # 对所有策略都生成信号（使用相同的df和indicators）
                     
                        all_strategies = list(STRATEGY_CONFIG_MAP.keys())
                        all_signals = {}
                        for strategy_name in all_strategies:
                            try:
                                # 获取策略配置
                                cfg_key = STRATEGY_CONFIG_MAP.get(strategy_name)
                                strat_cfg = config_module.CONFIG.get(cfg_key, {}) if cfg_key else {}

                                # 创建策略实例
                                from main import StrategyFactory
                                exec_strategy = StrategyFactory.create_strategy(strategy_name, config=strat_cfg, ib_trader=self.ib_trader)

                                # 使用该策略生成信号
                                signals = exec_strategy.generate_signals(sym, df, indicators_get)

                                if signals:
                                    if sym not in all_signals:
                                        all_signals[sym] = []
                                    all_signals[sym].extend(signals)
                                    logger.info(f"[base_strategy]  {sym} + {strategy_name} 生成 {len(signals)} 个信号")

                            except Exception as e:
                                logger.info(f"[base_strategy]策略 {strategy_name} 处理 {sym} 时出错: {e}")
                                continue

                        # 执行当前策略生成的信号（如果有的话）
                        current_signals = self.generate_signals(sym, df, indicators_get)
                        if current_signals:
                            if sym not in all_signals:
                                all_signals[sym] = []
                            all_signals[sym].extend(current_signals)

                            # 执行信号
                            for signal in current_signals:
                                # 使用信号中的价格，确保与仓位计算时价格一致
                                current_price = signal.get('price', df['Close'].iloc[-1])
                                try:
                                    result = self.execute_signal(signal, current_price, self.force_market_orders)
                                    logger.info(f"[base_strategy]信号执行结果: {result}")
                                except Exception as e:
                                    logger.info(f"[base_strategy]执行信号时出错: {e}")
                                    continue
                         # 对preselect_a2的所有股票生成信号并保存到新文件
                         
                        try:
                            logger.info(f"🔄 [base_strategy]开始执行preselect信号生成，当前all_signals长度: {sum(len(signals) for signals in all_signals.values())}")
                            self._generate_preselect_signals(data_provider, all_signals)
                            logger.info(f"✅ [base_strategy]preselect信号生成完成，更新后all_signals长度: {sum(len(signals) for signals in all_signals.values())}")

                            self._save_signals_to_csv(all_signals)
                        except Exception as e:
                            logger.info(f"[base_strategy]执行preselect信号生成时出错: {e}")
                            import traceback
                            logger.info(f"[base_strategy]: {traceback.format_exc()}")

                        logger.info(f"🏁 [base_strategy]run_analysis_cycle 执行完成，返回信号数量: {sum(len(signals) for signals in all_signals.values())}")
                        
                        
                        logger.info(f"get_nowait执行信号结果: {sym} {sig['action']} -> {result.get('status')}, 原因: {result.get('reason','')}")
                    except Exception as e:
                        logger.error(f"处理残留信号出错 {sym}: {e}")
                    
            finally:
                try:
                    # 等待 futures 完成并关闭 executor
                    for f in futures:
                        f.result(timeout=1)
                except Exception:
                    pass
                try:
                    executor.shutdown(wait=False)
                except Exception:
                    pass

        self.last_signals = signals
        
        # 生成状态报告
        self._status_report()
        
        logger.info(f"交易周期 #{self.cycle_count} 完成")
        logger.info('='*60)
    
    def _generate_preselect_signals(self, data_provider, all_signals: Dict[str, List[Dict]]):
        """对preselect_a2的所有股票生成信号并保存到新文件"""
        logger.info("🚀 _generate_preselect_signals方法被调用")
        try:
            # 从config获取所有preselect_a2股票
            preselect_symbols = list(config_module.CONFIG.get('symbol_strategy_map', {}).keys())
            logger.info(f"📊 获取到preselect_symbols: {len(preselect_symbols)} 个")
            if not preselect_symbols:
                logger.info("⚠️ 未找到preselect_a2股票配置")
                return

            # 获取所有可用的策略
            from config import STRATEGY_CONFIG_MAP
            all_strategies = list(STRATEGY_CONFIG_MAP.keys())
            logger.info(f"📊 获取到all_strategies: {len(all_strategies)} 个")
            if not all_strategies:
                logger.warning("⚠️ 未找到策略配置映射")
                return

            logger.info(f"🔍 开始生成preselect_a2信号: {len(preselect_symbols)} 个股票 × {len(all_strategies)} 个策略...")

            preselect_signals = []

            for symbol in preselect_symbols:
                try:
                    # 获取股票数据
                    df = data_provider.get_intraday_data(symbol, interval='5m', lookback=300)

                    if df.empty or len(df) < 30:
                        logger.debug(f"跳过 {symbol}，数据不足")
                        continue

                    # 获取技术指标（所有策略共享相同的indicators）
                    indicators = data_provider.get_technical_indicators(symbol, '1d', '5m')

                    # 对每个策略都生成信号
                    for strategy_name in all_strategies:
                        try:
                            # 获取策略配置
                            cfg_key = STRATEGY_CONFIG_MAP.get(strategy_name)
                            strat_cfg = config_module.CONFIG.get(cfg_key, {}) if cfg_key else {}

                            # 创建策略实例 - 使用strategy_manager中的STRATEGY_CLASSES
                            try:
                                from main import StrategyFactory
                                exec_strategy = StrategyFactory.create_strategy(strategy_name, config=strat_cfg, ib_trader=self.ib_trader)
                            except ImportError:
                                # 直接使用strategy_manager中的STRATEGY_CLASSES
                                from strategy_manager import STRATEGY_CLASSES
                                strategy_class = STRATEGY_CLASSES.get(strategy_name)
                                if strategy_class:
                                    exec_strategy = strategy_class(config=strat_cfg, ib_trader=self.ib_trader)
                                else:
                                    continue

                            # 使用该策略生成信号
                            signals = exec_strategy.generate_signals(symbol, df, indicators)

                            if signals:
                                # 为每个信号添加策略信息
                                for signal in signals:
                                    signal_copy = signal.copy()
                                    signal_copy['strategy'] = strategy_name
                                    signal_copy['symbol'] = symbol
                                    signal_copy['generated_at'] = datetime.now().isoformat()
                                    preselect_signals.append(signal_copy)

                                    # 同时添加到all_signals中（用于当前周期的信号处理）
                                    if symbol not in all_signals:
                                        all_signals[symbol] = []
                                    all_signals[symbol].append(signal_copy)

                                logger.debug(f"  {symbol} + {strategy_name} 生成 {len(signals)} 个信号")

                        except Exception as e:
                            logger.debug(f"策略 {strategy_name} 处理 {symbol} 时出错: {e}")
                            continue

                except Exception as e:
                    logger.warning(f"处理 {symbol} 时出错: {e}")
                    continue

            logger.info(f"✅ preselect_a2信号生成完成，共收集 {len(preselect_signals)} 个信号")

            # 保存到新的CSV文件
            self._save_preselect_signals_to_csv(preselect_signals)

        except Exception as e:
            logger.error(f"生成preselect_a2信号失败: {e}")

    def _save_preselect_signals_to_csv(self, signals: List[Dict]):
        """保存preselect_a2信号到CSV文件"""
        try:
            import pandas as pd
            import os

            if not signals:
                logger.info("没有preselect_a2信号需要保存")
                return

            # 转换为DataFrame
            df = pd.DataFrame(signals)

            # 确保必要的列存在
            required_cols = ['symbol', 'strategy', 'signal_type', 'action', 'price', 'confidence', 'generated_at']
            for col in required_cols:
                if col not in df.columns:
                    df[col] = None

            # 重新排列列顺序
            df = df[required_cols + [col for col in df.columns if col not in required_cols]]

            # 保存到CSV文件
            filename = f'preselect_signals_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
            df.to_csv(filename, index=False)
            logger.info(f"preselect_a2信号已保存到 {filename}，共 {len(signals)} 个信号")

        except Exception as e:
            logger.error(f"保存preselect_a2信号到CSV失败: {e}")

    def _save_signals_to_csv(self, all_signals: Dict[str, List[Dict]]):
        """保存所有生成的信号到CSV文件（用于信号监控）"""
        logger.info("💾 _save_signals_to_csv方法被调用")
        try:
            import pandas as pd
            import os

            # 展平信号数据
            flattened_signals = []
            for symbol, signals in all_signals.items():
                for signal in signals:
                    signal_copy = signal.copy()
                    signal_copy['symbol'] = symbol
                    signal_copy['generated_at'] = datetime.now().isoformat()
                    flattened_signals.append(signal_copy)

            logger.info(f"📊 展平后信号数量: {len(flattened_signals)}")
            if not flattened_signals:
                logger.info("没有信号需要保存")
                return

            # 转换为DataFrame
            df = pd.DataFrame(flattened_signals)

            # 确保必要的列存在
            required_cols = ['symbol', 'strategy', 'signal_type', 'action', 'price', 'confidence', 'generated_at']
            for col in required_cols:
                if col not in df.columns:
                    df[col] = None

            # 重新排列列顺序
            df = df[required_cols + [col for col in df.columns if col not in required_cols]]

            # 保存到CSV
            filename = 'signals_monitor.csv'
            df.to_csv(filename, index=False)
            logger.info(f"信号已保存到 {filename}，共 {len(flattened_signals)} 个信号")

        except Exception as e:
            logger.error(f"保存信号到CSV失败: {e}")

    def _status_report(self):
        """状态报告"""
        if not self.strategy:
            return

        report = self.strategy.generate_report()

        logger.info(f"\n📈 系统状态:")
        logger.info(f"  策略: {report['strategy_name']}")
        logger.info(f"  净资产: ${report['equity']:,.2f}")
        logger.info(f"  总交易: {report['total_trades']}")
        logger.info(f"  持仓数量: {report['positions_open']}")

        if report['positions_open'] > 0:
            logger.info(f"  持仓标的: {', '.join(report['open_positions'][:5])}")
            if len(report['open_positions']) > 5:
                logger.info(f"    ... 共 {len(report['open_positions'])} 个持仓")

        logger.info(f"  IB连接: {'✅' if report['ib_connected'] else '❌'}")

        # 处理 self.last_signals 可能是字典或列表的情况
        if isinstance(self.last_signals, dict):
            total_signals = sum(len(sigs) for sigs in self.last_signals.values())
        elif isinstance(self.last_signals, list):
            total_signals = len(self.last_signals)
        else:
            total_signals = 0

        if total_signals > 0:
            logger.info(f"  本期信号: {total_signals}")
    
    def list_strategies(self):
        """列出所有可用策略"""
        strategies = StrategyFactory.list_strategies()
        logger.info("\n📋 可用策略:")
        for strategy in strategies:
            desc = StrategyFactory.get_strategy_description(strategy)
            current = " (当前)" if strategy == self.current_strategy_name else ""
            logger.info(f"  {strategy}: {desc}{current}")
    
    def start(self, strategy_name: str = None):
        """启动系统"""
        logger.info("\n启动交易系统...")
        
        if strategy_name:
            self.switch_strategy(strategy_name)
        
        if not self.initialize():
            logger.error("初始化失败，系统退出")
            return
        
        self.is_running = True
        
        interval = self.config['trading']['scan_interval_minutes']
        schedule.every(interval).minutes.at(":00").do(self.trading_cycle)
        
        logger.info(f"\n✅ 系统已启动，每 {interval} 分钟扫描一次")
        logger.info("可用命令:")
        logger.info("  - 在控制台输入 'switch a1' 切换到动量反转策略")
        logger.info("  - 在控制台输入 'switch a2' 切换到Z-Score策略")
        logger.info("  - 在控制台输入 'switch a3' 切换到双均线成交量突破策略")
        logger.info("  - 在控制台输入 'switch a4' 切换到回调交易策略")
        logger.info("  - 在控制台输入 'switch a5' 切换到多因子AI融合策略")
        logger.info("  - 在控制台输入 'switch a6' 切换到新闻交易策略")
        logger.info("  - 在控制台输入 'switch a7' 切换到CTA趋势跟踪策略")
        logger.info("  - 在控制台输入 'switch a8-a18' 切换到技术指标策略")
        logger.info("  - 在控制台输入 'list' 查看所有策略")
        logger.info("  - 按 Ctrl+C 停止系统\n")
        
        self.trading_cycle()
        
        try:
            while self.is_running:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("\n\n🛑 收到停止信号...")
            self.stop()
    
    def stop(self):
        """停止系统"""
        logger.info("停止交易系统...")
        self.is_running = False
        schedule.clear()
        
        runtime = datetime.now() - self.start_time
        logger.info(f"\n⏱️  运行时间: {runtime}")
        logger.info(f"总交易周期: {self.cycle_count}")
        logger.info(f"最终策略: {self.strategy.get_strategy_name() if self.strategy else '无'}")
        
        # 断开IB连接
        if self.ib_trader:
            self.ib_trader.disconnect()
        
        logger.info("系统已安全停止")

# ==================== 命令行交互 ====================
def command_line_interface(system: TradingSystem):
    """命令行交互界面"""
    import threading
    
    def command_processor():
        while system.is_running:
            try:
                cmd = input().strip().lower()
                
                if cmd == 'switch a1':
                    system.switch_strategy('a1')
                elif cmd == 'switch a2':
                    system.switch_strategy('a2')
                elif cmd == 'switch a3':
                    system.switch_strategy('a3')
                elif cmd == 'switch a4':
                    system.switch_strategy('a4')
                elif cmd == 'switch a5':
                    system.switch_strategy('a5')
                elif cmd == 'switch a6':
                    system.switch_strategy('a6')
                elif cmd == 'switch a7':
                    system.switch_strategy('a7')
                elif cmd == 'switch a8':
                    system.switch_strategy('a8')
                elif cmd == 'switch a9':
                    system.switch_strategy('a9')
                elif cmd == 'switch a10':
                    system.switch_strategy('a10')
                elif cmd == 'switch a11':
                    system.switch_strategy('a11')
                elif cmd == 'switch a12':
                    system.switch_strategy('a12')
                elif cmd == 'switch a13':
                    system.switch_strategy('a13')
                elif cmd == 'switch a14':
                    system.switch_strategy('a14')
                elif cmd == 'switch a15':
                    system.switch_strategy('a15')
                elif cmd == 'switch a16':
                    system.switch_strategy('a16')
                elif cmd == 'switch a17':
                    system.switch_strategy('a17')
                elif cmd == 'switch a18':
                    system.switch_strategy('a18')
                elif cmd == 'switch a22':
                    system.switch_strategy('a22')
                elif cmd == 'switch a23':
                    system.switch_strategy('a23')
                elif cmd == 'switch a24':
                    system.switch_strategy('a24')
                elif cmd == 'switch a25':
                    system.switch_strategy('a25')
                elif cmd == 'switch a26':
                    system.switch_strategy('a26')
                elif cmd == 'switch a27':
                    system.switch_strategy('a27')
                elif cmd == 'switch a28':
                    system.switch_strategy('a28')
                elif cmd == 'switch a29':
                    system.switch_strategy('a29')
                elif cmd == 'switch a30':
                    system.switch_strategy('a30')
                elif cmd == 'switch a31':
                    system.switch_strategy('a31')
                elif cmd == 'switch a32':
                    system.switch_strategy('a32')
                elif cmd == 'switch a33':
                    system.switch_strategy('a33')
                elif cmd == 'switch a34':
                    system.switch_strategy('a34')
                elif cmd == 'switch a35':
                    system.switch_strategy('a35')
                elif cmd == 'list':
                    system.list_strategies()
                elif cmd == 'status':
                    system._status_report()
                elif cmd == 'help':
                    print("\n可用命令:")
                    print("  switch a1    - 切换到动量反转策略")
                    print("  switch a2    - 切换到Z-Score策略")
                    print("  switch a3    - 切换到双均线成交量突破策略")
                    print("  switch a4    - 切换到回调交易策略")
                    print("  switch a5    - 切换到多因子AI融合策略")
                    print("  switch a6    - 切换到新闻交易策略")
                    print("  switch a7    - 切换到CTA趋势跟踪策略")
                    print("  switch a8    - 切换到RSI震荡策略")
                    print("  switch a9    - 切换到MACD交叉策略")
                    print("  switch a10   - 切换到布林带策略")
                    print("  switch a11   - 切换到均线交叉策略")
                    print("  switch a12   - 切换到Stochastic RSI策略")
                    print("  switch a13   - 切换到EMA交叉策略")
                    print("  switch a14   - 切换到RSI趋势线策略")
                    print("  switch a15   - 切换到配对交易策略")
                    print("  switch a16   - 切换到ROC动量策略")
                    print("  switch a17   - 切换到CCI顺势策略")
                    print("  switch a18   - 切换到IsolationForest异常检测策略")
                    print("  list         - 列出所有可用策略")
                    print("  status       - 显示当前状态")
                    print("  help         - 显示帮助信息")
                    print("  quit         - 退出系统")
                elif cmd == 'quit':
                    system.stop()
                    break
                elif cmd:
                    print(f"未知命令: {cmd}")
                    print("输入 'help' 查看可用命令")
                    
            except EOFError:
                break
            except Exception as e:
                logger.error(f"命令处理错误: {e}")
    
    # 启动命令处理线程
    thread = threading.Thread(target=command_processor, daemon=True)
    thread.start()

# ==================== 主程序入口 ====================
def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='多策略交易系统')
    parser.add_argument('--strategy', '-s', choices=['a1', 'a2', 'a3', 'a4', 'a5', 'a6', 'a7', 'a8', 'a9', 'a10', 'a11', 'a12', 'a13', 'a14', 'a15', 'a16', 'a17', 'a18', 'a22', 'a23', 'a24', 'a25', 'a26', 'a27', 'a28', 'a29', 'a30', 'a31', 'a32', 'a33', 'a34', 'a35'], default='a1',
                       help='初始策略 (a1-a7: 核心策略, a8-a18: 技术指标策略, a22-a35: 高级策略)')
    parser.add_argument('--interactive', '-i', action='store_true',
                       help='启用命令行交互模式')
    
    args = parser.parse_args()
    
    logger.info("🚀 多策略交易系统启动")
    logger.info(f"初始策略: {args.strategy}")
    logger.info(f"日志文件: {log_file}")
    logger.info("=" * 70)
    
    system = TradingSystem(strategy_name=args.strategy)
    
    # 启动命令行交互（如果启用）
    if args.interactive:
        logger.info("命令行交互模式已启用")
        command_line_interface(system)
    
    try:
        system.start()
    except Exception as e:
        logger.error(f"\n❌ 系统运行出错: {e}")
        import traceback
        traceback.print_exc()

def generate_profit_report_for_date(date_str=None):
    """
    为指定日期生成利润报告

    参数:
        date_str: 日期字符串，格式为 YYYY-MM-DD，如果为None则使用今天
    """
    from datetime import datetime
    target_date = None
    if date_str:
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            logger.error(f"日期格式错误，请使用 YYYY-MM-DD 格式: {date_str}")
            return

    generate_end_of_day_profit_report(target_date)

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='量化策略利润报告生成器')
    parser.add_argument('--date', '-d', help='指定统计日期 (YYYY-MM-DD格式)，默认今天')
    parser.add_argument('--report', action='store_true', help='生成利润报告')

    args = parser.parse_args()

    if args.report:
        generate_profit_report_for_date(args.date)
    else:
        main()
