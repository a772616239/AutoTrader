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
from datetime import datetime
from typing import Dict, List

# 添加模块路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from trading.ib_trader import IBTrader
from data.data_provider import DataProvider
from strategies.a1_momentum_reversal import A1MomentumReversalStrategy
from strategies.a2_zscore import A2ZScoreStrategy
from strategies.a3_dual_ma_volume import A3DualMAVolumeStrategy
from strategies.a4_pullback import A4PullbackStrategy
from strategies.a5_multifactor_ai import A5MultiFactorAI
from strategy_manager import StrategyManager

warnings.filterwarnings('ignore')

# ==================== 全局日志配置 ====================
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "trading_system.log")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)
logger.info(f"日志文件保存在: {os.path.abspath(log_file)}")

# ==================== 策略工厂 ====================
class StrategyFactory:
    """策略工厂，用于创建和切换策略"""
    
    STRATEGIES = {
        'a1': A1MomentumReversalStrategy,
        'a2': A2ZScoreStrategy,
        'a3': A3DualMAVolumeStrategy,
        'a4': A4PullbackStrategy,
        'a5': A5MultiFactorAI,
    }
    
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
        if strategy_name not in cls.STRATEGIES:
            raise ValueError(f"未知的策略: {strategy_name}。可用策略: {list(cls.STRATEGIES.keys())}")
        
        strategy_class = cls.STRATEGIES[strategy_name]
        return strategy_class(config=config, ib_trader=ib_trader)
    
    @classmethod
    def list_strategies(cls) -> List[str]:
        """获取所有可用策略列表"""
        return list(cls.STRATEGIES.keys())
    
    @classmethod
    def get_strategy_description(cls, strategy_name: str) -> str:
        """获取策略描述"""
        descriptions = {
            'a1': '动量反转策略 - 基于早盘动量/午盘反转信号',
            'a2': 'Z-Score均值回归策略 - 基于统计套利',
            'a3': '双均线成交量突破策略 - 基于趋势突破',
            'a4': '回调交易策略 - 基于斐波那契回撤',
            'a5': '多因子AI融合策略 - 整合流动性、基本面、情绪、动量',
        }
        return descriptions.get(strategy_name, '未知策略')

# ==================== 主交易系统 ====================
class TradingSystem:
    """主交易系统控制器"""
    
    def __init__(self, config_file: str = None, strategy_name: str = 'a1'):
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
        
        logger.info("=" * 70)
        logger.info("多策略日内交易系统")
        logger.info(f"当前策略: {strategy_name} - {StrategyFactory.get_strategy_description(strategy_name)}")
        logger.info("=" * 70)
        logger.info(f"日志文件: {log_file}")
    
    def _load_config(self, config_file: str) -> Dict:
        """加载配置"""
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
                'symbols': ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'META','MU','INTC','AMD',
                            'NFLX','BIDU','JD','BABA','TCEHY','PYPL','SHOP','CRM','ORCL','IBM',
                            'CSCO','QCOM','TXN','AVGO','ADBE','INTU','ZM','DOCU','SNOW','UBER',
                            'LYFT'],
                'scan_interval_minutes': 1,
                'trading_hours': {
                    'start': '00:00',
                    'end': '15:45'
                }
            },
            'strategy': {
                'initial_capital': 100000.0,
                'risk_per_trade': 0.01,
                'max_position_size': 0.05,
                'ib_order_type': 'MKT',
                'ib_limit_offset': 0.01,
                'min_cash_buffer': 0.3,
                'per_trade_notional_cap': 10000.0,
                'max_position_notional': 60000.0,  # 单股总仓位上限（美元）
                'max_active_positions': 5,
                'default_max_signals_per_cycle': 3,
                'max_signals_per_cycle': {
                    'a2': 2,  # A2 每周期最多 2 个委托（主线程层面的限制）
                }
            }
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
            client_id=ib_config['client_id']
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
    
    def _within_trading_hours(self) -> bool:
        """检查是否在交易时间内"""
        hours = self.config['trading']['trading_hours']
        start = datetime.strptime(hours['start'], '%H:%M').time()
        end = datetime.strptime(hours['end'], '%H:%M').time()
        current = datetime.now().time()
        
        return start <= current <= end
    
    def trading_cycle(self):
        """交易循环"""
        if not self.is_running:
            logger.warning("📭 系统未运行")
            return
        
        self.cycle_count += 1
        current_time = datetime.now()
        
        logger.info(f"\n{'='*60}")
        logger.info(f"交易周期 #{self.cycle_count} - {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"当前策略: {self.strategy.get_strategy_name()}")
        logger.info('='*60)
        
        # 检查交易时间
        # if not self._within_trading_hours():
        #     logger.info("⏸️  非交易时间，跳过...")
        #     return
        
        # 周期开始前取消所有未完成委托
        if self.ib_trader and self.ib_trader.connected:
            try:
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
            signals = self.strategy.run_analysis_cycle(self.data_provider, symbols)
        
        # 处理信号：流式模式下主线程即时消费 signal_queue 并执行下单
        if symbol_map and self.ib_trader:
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
                        logger.info(f"执行信号结果: {sym} {sig['action']} -> {result.get('status')}, 原因: {result.get('reason','')}")
                    except Exception as e:
                        logger.error(f"执行信号出错 {sym}: {e}")

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
                        exec_strategy.sync_positions_from_ib()
                        current_price = sig.get('price') or 0
                        atr = None
                        new_size = exec_strategy.calculate_position_size(sig, atr)
                        sig['position_size'] = new_size
                        result = exec_strategy.execute_signal(sig, current_price)
                        logger.info(f"执行信号结果: {sym} {sig['action']} -> {result.get('status')}, 原因: {result.get('reason','')}")
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
        
        total_signals = sum(len(sigs) for sigs in self.last_signals.values())
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
    parser.add_argument('--strategy', '-s', choices=['a1', 'a2', 'a3', 'a4', 'a5'], default='a1',
                       help='初始策略 (a1: 动量反转, a2: Z-Score, a3: 双均线成交量突破, a4: 回调交易, a5: 多因子AI融合)')
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

if __name__ == "__main__":
    main()
