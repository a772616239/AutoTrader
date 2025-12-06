# AutoTrader 故障排查指南

## 常见错误和解决方案

### 错误 1: "子类必须实现 generate_signals 方法"

**症状**：
```
ERROR - 分析 AAPL 时出错: 子类必须实现 generate_signals 方法
```

**原因**：
策略没有实现 `generate_signals()` 方法或实现不完整。

**解决方案**：

1. **检查策略类继承**：
   ```python
   # ✅ 正确
   class MyStrategy(BaseStrategy):
       def generate_signals(self, symbol: str, data: pd.DataFrame, 
                          indicators: Dict) -> List[Dict]:
           # 实现信号生成逻辑
           return signals
   ```

2. **检查方法签名**：
   确保方法签名完全一致：
   ```python
   def generate_signals(self, symbol: str, data: pd.DataFrame, 
                       indicators: Dict) -> List[Dict]:
   ```

3. **运行测试**：
   ```bash
   python test_all_strategies.py
   ```

4. **如果是 A3 策略**，确保已应用最新修复：
   ```bash
   git pull  # 获取最新代码
   ```

---

### 错误 2: "AttributeError: 'xxx' object has no attribute 'xxx'"

**症状**：
```
AttributeError: 'A3DualMAVolumeStrategy' object has no attribute 'calculate_indicators'
```

**原因**：
策略调用了不存在的方法。

**解决方案**：

1. **检查方法是否存在**：
   ```bash
   grep -n "def calculate_indicators" strategies/a3_dual_ma_volume.py
   ```

2. **如果方法不存在**，需要实现它或移除调用。

3. **对于 A3 策略**，已修复此问题，传入空字典即可：
   ```python
   signals = self.detect_buy_signal(symbol, data, {})
   ```

---

### 错误 3: "没有生成任何交易信号"

**症状**：
策略运行但没有生成信号。

**原因**：
- 数据不足
- 条件过于严格
- 参数设置不合理

**解决方案**：

1. **检查数据长度**：
   确保至少有 30 根 K 线
   ```python
   if len(data) < 30:
       logger.warning(f"数据不足，仅有 {len(data)} 条")
   ```

2. **调整参数**：
   参考各策略的参数调优指南

3. **启用调试日志**：
   ```python
   logging.basicConfig(level=logging.DEBUG)
   ```

---

### 错误 4: "IB 连接失败"

**症状**：
```
ERROR - IB未连接，无法提交订单
```

**原因**：
- IB TWS/Gateway 未启动
- 连接参数不正确
- 网络问题

**解决方案**：

1. **启动 IB TWS 或 Gateway**
2. **验证连接设置** (`config.py`)：
   ```python
   'ib_server': {
       'host': '127.0.0.1',
       'port': 7497,
       'client_id': 1,
   }
   ```
3. **检查防火墙设置**

---

### 错误 5: "资金不足或超过持仓限制"

**症状**：
```
REJECTED - 单股仓位超过限制
```

**原因**：
- 已有持仓 + 新委托 > $60,000
- 账户资金不足

**解决方案**：

1. **检查持仓**：
   ```bash
   # 查看 IB 中的持仓
   # 或在日志中查找仓位信息
   ```

2. **降低单笔交易额**：
   在 `config.py` 中减小 `per_trade_notional_cap`

3. **关闭一些持仓**：
   手动或通过策略卖出

---

## 诊断工具

### 运行完整测试套件
```bash
python test_all_strategies.py
```

预期输出：
```
✅ A1 Momentum Reversal 测试通过！
✅ A2 Z-Score 测试通过！
✅ A3 Dual MA + Volume 测试通过！

✅ 所有策略测试通过！
```

### 检查日志
```bash
tail -f logs/trading_system.log
```

关键信息：
- `INFO - ✅` : 成功操作
- `WARNING - ⚠️` : 警告信息
- `ERROR - ❌` : 错误信息

### 验证配置
```bash
python -c "from config import CONFIG, STRATEGY_CONFIG_MAP; print(CONFIG['strategy_a3'])"
```

---

## 快速修复清单

### 启动前检查
- [ ] Python 3.10+ 已安装
- [ ] 所有依赖已安装 (`pip install -r requirements.txt`)
- [ ] IB TWS/Gateway 已启动
- [ ] 网络连接正常
- [ ] 配置文件正确

### 如果 A3 策略出错
- [ ] 运行 `python test_all_strategies.py` 测试
- [ ] 检查 `strategies/a3_dual_ma_volume.py` 是否有 `generate_signals()` 方法
- [ ] 重新启动系统：`python main.py --strategy a3`

### 如果没有交易信号
- [ ] 检查股票数据是否足够（> 30 条）
- [ ] 检查成交量是否满足条件
- [ ] 调整参数使条件更宽松
- [ ] 查看日志找出被过滤的原因

### 如果交易失败
- [ ] 检查 IB 连接状态
- [ ] 检查账户资金
- [ ] 检查持仓限制是否超过
- [ ] 查看错误日志获取详细信息

---

## 获取帮助

### 查阅文档
- **快速参考**: `QUICK_REFERENCE.md`
- **A3 使用手册**: `A3_USAGE.md`
- **A3 详细指南**: `A3_STRATEGY_GUIDE.md`
- **实现报告**: `A3_IMPLEMENTATION_REPORT.md`

### 检查源代码
- `strategies/base_strategy.py` - 基类实现
- `strategies/a1_momentum_reversal.py` - A1 策略
- `strategies/a2_zscore.py` - A2 策略
- `strategies/a3_dual_ma_volume.py` - A3 策略

### 查看日志
系统日志位置：`logs/trading_system.log`

### 运行诊断
```bash
# 测试所有策略
python test_all_strategies.py

# 测试数据提供商
python -c "from data.data_provider import DataProvider; dp = DataProvider(); print(dp.get_intraday_data('AAPL', '5m', 5))"

# 测试 IB 连接
python -c "from trading.ib_trader import IBTrader; ib = IBTrader(); print('连接状态:', ib.connect())"
```

---

## 常见参数问题

### A3 没有交易信号，如何调整？

**问题症状**：
- 策略运行，但没有生成任何信号

**调试步骤**：
1. 检查日志中的过滤原因
2. 逐一放宽条件：
   - 降低 `volume_surge_ratio` (1.5 → 1.3)
   - 缩短均线周期 (fast: 9→6, slow: 21→15)
   - 增加 `min_volume_threshold` 的值

**示例配置**：
```python
{
    'fast_ma_period': 6,
    'slow_ma_period': 15,
    'volume_surge_ratio': 1.3,
    'min_volume_threshold': 300000,  # 降低从 500000
}
```

---

## 联系信息

如果问题仍未解决，请：
1. 收集完整的错误日志
2. 记录当时的系统状态
3. 检查是否有最新的补丁或更新

---

**最后更新**: 2025-12-06  
**版本**: 1.0
