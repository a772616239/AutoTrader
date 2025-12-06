#!/usr/bin/env python3
"""
双策略量化交易系统主程序
"""
import time
import logging
import schedule
import os
import argparse
from datetime import datetime

# 导入模块
from ib_manager import IBTrader
from data_provider import DataProvider
from strategy_a1 import MomentumReversalEngine
from strategy_a2 import ZScoreStrategy

# 配置日志
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(log_dir, "main_system.log"), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("MainController")

# ================= 配置区 =================
WATCHLIST = ['AAPL', 'TSLA', 'NVDA', 'AMD', 'SPY', 'QQQ']
ACTIVE_STRATEGY_NAME = "a1"  # 默认策略: 'a1' 或 'a2'
# =========================================

def get_strategy(name, ib, data):
    """策略工厂"""
    if name == "a1":
        return MomentumReversalEngine(ib, data)
    elif name == "a2":
        return ZScoreStrategy(ib, data)
    else:
        raise ValueError(f"未知策略: {name}")

def execute_signal(ib: IBTrader, signal: dict):
    """统一执行逻辑"""
    if not signal: return
    
    symbol = signal['symbol']
    action = signal['action']
    price = signal.get('price')
    reason = signal.get('reason', '')
    
    logger.info(f"⚡ 捕捉到信号 [{signal['signal_type']}]: {action} {symbol} @ {price} | 原因: {reason}")
    
    # 计算仓位 (简化版，固定100股或根据资金计算)
    quantity = 100 
    
    # 下单
    ib.place_order(symbol, action, quantity)

def trading_job(strategy, watchlist):
    """定时任务核心逻辑"""
    logger.info(f"--- 执行扫描 ({strategy.name}) ---")
    
    # 1. 同步持仓状态
    strategy.sync_positions()
    
    # 2. 遍历股票池
    for symbol in watchlist:
        try:
            # 3. 运行策略分析
            signal = strategy.run_analysis(symbol)
            
            # 4. 执行信号
            if signal:
                execute_signal(strategy.ib_trader, signal)
                
        except Exception as e:
            logger.error(f"处理 {symbol} 时出错: {e}")

def main():
    global ACTIVE_STRATEGY_NAME
    
    # 简单的命令行参数支持
    import sys
    if len(sys.argv) > 1:
        ACTIVE_STRATEGY_NAME = sys.argv[1] # python main.py a2

    logger.info("=== 启动量化交易系统 ===")
    
    # 1. 初始化基础设施
    ib = IBTrader(port=7497, client_id=10)
    data = DataProvider()
    
    if not ib.connect():
        logger.error("无法启动：IB连接失败")
        return

    # 2. 加载策略
    try:
        strategy = get_strategy(ACTIVE_STRATEGY_NAME, ib, data)
        logger.info(f"已激活策略: {strategy.name}")
    except Exception as e:
        logger.error(str(e))
        return

    # 3. 设置定时任务 (每1分钟扫描一次)
    schedule.every(1).minutes.do(trading_job, strategy, WATCHLIST)
    
    logger.info("系统就绪，开始主循环...")
    logger.info(f"监控股票池: {WATCHLIST}")

    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("用户停止系统")
        ib.disconnect()

if __name__ == "__main__":
    main()