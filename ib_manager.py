import time
import logging
from typing import Optional, List, Dict
from ib_insync import IB, Stock, Trade, LimitOrder, MarketOrder, Position

logger = logging.getLogger(__name__)

class IBTrader:
    """IB交易接口封装 (原逻辑)"""
    
    def __init__(self, host='127.0.0.1', port=7497, client_id=1):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.ib = IB()
        self.connected = False
        self.max_retries = 3
        logger.info(f"IB交易接口初始化: {host}:{port} (clientId={client_id})")
    
    def connect(self) -> bool:
        if self.connected:
            return True
            
        for attempt in range(self.max_retries):
            try:
                logger.info(f"尝试连接IB [尝试 {attempt+1}/{self.max_retries}]")
                self.ib.connect(self.host, self.port, clientId=self.client_id)
                
                if self.ib.isConnected():
                    self.connected = True
                    logger.info("✅ IB连接成功")
                    return True
                else:
                    logger.warning(f"IB连接状态检查失败，重试中...")
                    time.sleep(2)
                    
            except Exception as e:
                logger.error(f"连接IB失败: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(3 * (attempt + 1))
                else:
                    logger.error("❌ 所有重试失败，无法连接IB")
                    return False
        return False
    
    def disconnect(self):
        if self.connected:
            try:
                self.ib.disconnect()
                self.connected = False
                logger.info("IB连接已断开")
            except Exception as e:
                logger.error(f"断开IB连接时出错: {e}")
    
    def get_contract(self, symbol: str) -> Stock:
        try:
            contract = Stock(symbol, 'SMART', 'USD')
            self.ib.qualifyContracts(contract)
            return contract
        except Exception as e:
            logger.error(f"合约鉴定失败 {symbol}: {e}")
            raise
    
    def place_order(self, symbol: str, action: str, quantity: float, 
                   order_type: str = 'MKT', price: Optional[float] = None) -> Optional[Trade]:
        if not self.connected and not self.connect():
            logger.error("IB未连接，无法提交订单")
            return None
        
        try:
            contract = self.get_contract(symbol)
            if order_type == 'LMT' and price is not None:
                order = LimitOrder(action, quantity, price)
            elif order_type == 'MKT':
                order = MarketOrder(action, quantity)
            else:
                logger.error(f"不支持的订单类型或缺少价格参数: {order_type}")
                return None
            
            logger.info(f"提交订单: {action} {quantity} 股 {symbol} ({order_type} @ {price if price else '市价'})")
            trade = self.ib.placeOrder(contract, order)
            self.ib.sleep(1) # 稍微等待
            return trade
        except Exception as e:
            logger.error(f"提交订单失败 {symbol}: {e}")
            return None

    def get_holdings(self, symbol: Optional[str] = None) -> List[Position]:
        if not self.connected and not self.connect():
            return []
        try:
            positions = self.ib.positions()
            stock_positions = [p for p in positions if hasattr(p.contract, 'secType') and p.contract.secType == 'STK']
            
            if symbol:
                return [p for p in stock_positions if p.contract.symbol == symbol]
            return stock_positions
        except Exception as e:
            logger.error(f"获取持仓时发生错误: {e}")
            return []

    def get_net_liquidation(self) -> float:
        if not self.connected and not self.connect():
            return 0.0
        try:
            summary = self.ib.accountSummary()
            for item in summary:
                if item.tag == 'NetLiquidation':
                    return float(item.value)
        except Exception as e:
            logger.error(f"获取净资产失败: {e}")
        return 0.0