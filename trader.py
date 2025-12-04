from ib_insync import *
from typing import Optional, Union

# ----------------- 交易函数封装 (修改版) -----------------

def get_contract(ib: IB, symbol: str) -> Stock:
    """
    根据股票代码创建并鉴定合约。
    需要传入已连接的 IB 实例。
    """
    contract = Stock(symbol, 'SMART', 'USD')
    # 使用传入的 IB 实例进行合约鉴定
    ib.qualifyContracts(contract) 
    return contract

def place_order(
    ib: IB,  # <-- 新增：传入已连接的 IB 实例
    symbol: str, 
    action: str, 
    quantity: float, 
    order_type: str = 'MKT', 
    price: Optional[float] = None
) -> Optional[Trade]:
    """
    通用订单提交函数。
    """
    if not ib.isConnected():
        print("错误：IB 连接未建立。请先连接。")
        return None
        
    try:
        # 使用传入的 IB 实例进行合约鉴定
        contract = get_contract(ib, symbol) 
        
        if order_type == 'LMT' and price is not None:
            order = LimitOrder(action, quantity, price)
        elif order_type == 'MKT':
            order = MarketOrder(action, quantity)
        else:
            print(f"不支持的订单类型或缺少价格参数：{order_type}")
            return None

        print(f"正在提交订单: {action} {quantity} 股 {symbol} ({order_type} @ {price if price else 'N/A'})...")
        
        # 使用传入的 IB 实例提交订单
        trade = ib.placeOrder(contract, order)
        
        # 等待订单状态更新 (非阻塞等待)
        ib.sleep(1)
        
        print(f"订单提交成功。ID: {trade.order.orderId}, 当前状态: {trade.orderStatus.status}")
        
        return trade
        
    except Exception as e:
        # 捕获资金不足等错误，并打印
        print(f"提交订单时发生错误: {e}")
        return None

def place_buy_order(ib: IB, symbol: str, quantity: float, order_type: str = 'MKT', price: Optional[float] = None) -> Optional[Trade]:
    """
    封装的买入订单函数。
    """
    return place_order(ib, symbol, 'BUY', quantity, order_type, price)

def place_sell_order(ib: IB, symbol: str, quantity: float, order_type: str = 'MKT', price: Optional[float] = None) -> Optional[Trade]:
    """
    封装的卖出订单函数。
    """
    return place_order(ib, symbol, 'SELL', quantity, order_type, price)

# ----------------- 主程序示例 (调用方式修改) -----------------

if __name__ == '__main__':
    ib = IB()
    
    try:
        ib.connect('127.0.0.1', 7497, clientId=1)
        print("成功连接到盈透证券模拟账户。")
    except ConnectionRefusedError:
        print("连接失败。请检查 TWS/Gateway 是否运行并登录，端口是否为 7497。")
        exit()

    # --- 示例 1: 市价买入 5 股 (注意：现在第一个参数是 ib) ---
    print("\n--- 示例 1: 市价买入 (MKT) ---")
    buy_trade_mkt = place_buy_order(ib, 'MSFT', 5) # <-- 关键修改：传入 ib
    
    ib.sleep(3)
    if buy_trade_mkt:
        print(f"市价买入最终状态: {buy_trade_mkt.orderStatus.status}")
        
    
    # --- 示例 2: 限价卖出 10 股 (注意：现在第一个参数是 ib) ---
    print("\n--- 示例 2: 限价卖出 (LMT) ---")
    sell_trade_lmt = place_sell_order(ib, 'MSFT', 10, 'LMT', price=100.00) # <-- 关键修改：传入 ib

    ib.sleep(3)
    if sell_trade_lmt:
        print(f"限价卖出最终状态: {sell_trade_lmt.orderStatus.status}")
        
    
    # 断开连接
    ib.disconnect()
    print("\n已断开连接。")