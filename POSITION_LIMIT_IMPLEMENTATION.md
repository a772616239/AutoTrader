# 单股总仓位限制功能实现总结

## 需求
在提交委托单前计算当前股票的总仓位（包括已持有的仓位 + 新的委托单），不能超过配置的单股总仓位限制（60,000美元）。

## 实现

### 1. 配置参数添加
在所有配置文件中添加了新参数：
- `max_position_notional`: 60000.0（单股总仓位上限，美元）

**更新的文件：**
- `/momentum_reversal_main.py` - 默认配置
- `/config.py` - 全局配置
- `/strategies/base_strategy.py` - 基础策略配置
- `/strategies/a1_momentum_reversal.py` - A1策略配置
- `/strategies/a2_zscore.py` - A2策略配置
- `/main.py` - 主程序配置

### 2. 检查方法实现
在 `momentum_reversal_main.py` 中添加了新方法：

```python
def check_single_stock_position_limit(self, symbol: str, new_position_value: float, 
                                      current_price: float) -> bool:
```

**功能:**
- 获取该股票的已有持仓（通过 `get_holding_for_symbol`）
- 计算已有持仓的美元价值（持仓数量 × 当前价格）
- 将新委托单的美元价值相加
- 比较总仓位价值与配置的上限
- 返回 True（符合限制）或 False（超过限制）

### 3. 订单提交前验证
在 `execute_signal` 方法中添加了检查逻辑：

```python
# 检查单股总仓位限制（仅对买入订单）
if signal['action'] == 'BUY':
    new_position_value = signal['position_size'] * current_price
    if not self.check_single_stock_position_limit(symbol, new_position_value, current_price):
        return {'status': 'REJECTED', 'reason': '单股仓位超过限制'}
```

**特点：**
- 仅对买入订单（BUY）进行检查
- 计算新委托单的美元价值（股数 × 当前价格）
- 如果检查失败，拒绝订单并返回错误原因

## 工作流程

1. 生成买入信号 → 
2. 计算仓位大小（受 $10,000 单笔上限约束）→ 
3. 执行信号时进行总仓位检查 →
   - 获取已有持仓 →
   - 计算总仓位价值 →
   - 与 $60,000 上限比较 →
   - 通过则下单，失败则拒绝

## 日志输出示例

```
✅ AAPL 仓位检查: 已持仓 100股 ($15,000.00), 新委托 $10,000.00, 总仓位 $25,000.00, 限制 $60,000.00
✅ AAPL 仓位检查通过
```

或

```
❌ AAPL 总仓位超过限制! 总值 $65,000.00 > 限制 $60,000.00, 拒绝下单
```

## 注意事项
- 检查仅对买入订单应用，卖出订单不受限制
- 使用当前价格计算已有持仓的美元价值（实时反映）
- 如果股票代码无持仓，则认为已有持仓为0
- 拒绝的订单会返回错误状态，不会提交到交易所
