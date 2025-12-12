#!/usr/bin/env python3
"""
更新trades.json，为每个买入交易添加position_avg_cost字段
"""
import json
import logging
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def update_trades_with_position_cost(trades_file='data/trades.json'):
    """为每个买入交易添加position_avg_cost字段"""

    # 读取交易记录
    try:
        with open(trades_file, 'r', encoding='utf-8') as f:
            trades = json.load(f)
        logger.info(f"成功加载 {len(trades)} 条交易记录")
    except Exception as e:
        logger.error(f"加载交易记录失败: {e}")
        return False

    # 按股票分组交易记录
    symbol_trades = defaultdict(list)

    for trade in trades:
        if trade.get('status') == 'EXECUTED':
            symbol_trades[trade['symbol']].append(trade)

    # 为每个股票计算持仓成本并更新交易记录
    updated_count = 0

    for symbol, symbol_trades_list in symbol_trades.items():
        # 分离买入和卖出交易
        buy_trades = [t for t in symbol_trades_list if t['action'] == 'BUY']
        sell_trades = [t for t in symbol_trades_list if t['action'] == 'SELL']

        if not buy_trades:
            continue

        # 计算平均买入成本
        total_buy_cost = sum(trade['price'] * trade['size'] for trade in buy_trades)
        total_buy_shares = sum(trade['size'] for trade in buy_trades)
        avg_buy_cost = total_buy_cost / total_buy_shares if total_buy_shares > 0 else 0

        # 为每个买入交易添加position_avg_cost字段
        for trade in buy_trades:
            if 'position_avg_cost' not in trade:
                trade['position_avg_cost'] = avg_buy_cost
                updated_count += 1
                logger.debug(f"更新 {symbol} 买入交易 position_avg_cost: ${avg_buy_cost:.2f}")

        # 为卖出交易也添加position_avg_cost字段（用于计算持仓成本利润）
        for trade in sell_trades:
            if 'position_avg_cost' not in trade:
                trade['position_avg_cost'] = avg_buy_cost
                updated_count += 1
                logger.debug(f"更新 {symbol} 卖出交易 position_avg_cost: ${avg_buy_cost:.2f}")

    # 保存更新后的交易记录
    try:
        with open(trades_file, 'w', encoding='utf-8') as f:
            json.dump(trades, f, indent=2, ensure_ascii=False)
        logger.info(f"✅ 成功更新 {updated_count} 条交易记录的position_avg_cost字段")
        return True
    except Exception as e:
        logger.error(f"保存交易记录失败: {e}")
        return False

if __name__ == "__main__":
    success = update_trades_with_position_cost()
    if success:
        print("交易记录已成功更新")
    else:
        print("交易记录更新失败")