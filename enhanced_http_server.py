#!/usr/bin/env python3
"""
增强版HTTP服务器，提供多维股票数据
curl "http://localhost:8001/enhanced-data?symbol=AAPL&period=3mo"
curl "http://localhost:8001/analysis-report?symbol=MSFT"

"""
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import os
import mimetypes
import enhanced_stock_data as esd
from datetime import datetime
import math
import numpy as np
import yfinance as yf

class EnhancedStockAPIHandler(BaseHTTPRequestHandler):
    # 类级别变量，用于重用IB连接（确保在主线程中）
    _shared_ib_trader = None

    @classmethod
    def get_shared_ib_trader(cls):
        """获取共享的IB交易接口，确保在主线程中初始化"""
        if cls._shared_ib_trader is None or not cls._shared_ib_trader.is_connection_healthy():
            try:
                # 动态导入IBTrader
                import sys
                if os.getcwd() not in sys.path:
                    sys.path.append(os.getcwd())
                from trading.ib_trader import IBTrader

                # 创建或重新连接IB连接
                cls._shared_ib_trader = IBTrader( port=7496, client_id=1)
                if not cls._shared_ib_trader.connect():
                    print("[ERROR] 无法连接到IB")
                    return None
                print("[LOG] IB连接已初始化并在主线程中共享")
            except Exception as e:
                print(f"[ERROR] 初始化IB连接失败: {str(e)}")
                return None
        return cls._shared_ib_trader

    def __init__(self, *args, **kwargs):
        self.data_provider = esd.EnhancedStockData()
        self.web_dir = os.path.join(os.getcwd(), 'web')
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        
        # 静态文件服务
        if path == '/' or path == '/dashboard' or path == '/dashboard1':
            self._serve_file('dashboard1.html')
            return
        elif '.' in path: # 简单的文件后缀检查
            filename = path.lstrip('/')
            if os.path.exists(os.path.join(self.web_dir, filename)):
                self._serve_file(filename)
                return

        # API 路由
        if path == '/api/history':
            self._handle_history_api(parsed)
            return
        elif path == '/api/indicators':
            self._handle_indicators_api(parsed)
            return
        elif path == '/enhanced-data':
            self._handle_enhanced_data(parsed)
            return
        elif path == '/batch-data':
            self._handle_batch_data(parsed)
            return
        elif path == '/analysis-report':
            self._handle_analysis_report(parsed)
            return
        elif path == '/api/symbols':
            self._handle_symbols_api()
            return
        elif path == '/api/trades':
            self._handle_trades_api(parsed)
            return
        elif path == '/api/update-strategy':
            self._handle_update_strategy_api(parsed)
            return
        elif path == '/api/runtime-strategy':
            self._handle_runtime_strategy_api(parsed)
            return
        elif path == '/api/price-update':
            self._handle_price_update_api(parsed)
            return
        elif path == '/api/account':
            self._handle_account_api()
            return
        elif path == '/api/ib/connect':
            self._handle_ib_connect_api()
            return
        elif path == '/api/ib/disconnect':
            self._handle_ib_disconnect_api()
            return
        elif path == '/api/ib/status':
            self._handle_ib_status_api()
            return
        elif path == '/api/ib/reconnect':
            self._handle_ib_reconnect_api()
            return
        elif path == '/api/ib/holdings':
            self._handle_ib_holdings_api()
            return
        elif path == '/api/ib/cancel-orders':
            self._handle_ib_cancel_orders_api()
            return
        elif path == '/api/ib/update-trades':
            self._handle_ib_update_trades_api()
            return
        elif path == '/api/trading/execute-signal':
            self._handle_execute_signal_api()
            return

        # 404
        self.send_error(404, "File not found")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def _serve_file(self, filename):
        filepath = os.path.join(self.web_dir, filename)
        if not os.path.exists(filepath):
            self.send_error(404, "File not found")
            return
            
        mime_type, _ = mimetypes.guess_type(filepath)
        if mime_type is None:
            mime_type = 'application/octet-stream'
            
        try:
            with open(filepath, 'rb') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-type', mime_type)
            self.end_headers()
            try:
                self.wfile.write(content)
            except BrokenPipeError:
                # 客户端已断开连接，忽略错误
                pass
        except Exception as e:
            self.send_error(500, str(e))

    def _handle_history_api(self, parsed):
        params = parse_qs(parsed.query)
        symbol = params.get('symbol', ['AAPL'])[0]
        period = params.get('period', ['1y'])[0]
        interval = params.get('interval', ['1d'])[0]

        print(f"[LOG] 获取历史数据 - 符号: {symbol}, 周期: {period}, 间隔: {interval}")

        # 使用 EnhancedStockData (yfinance) 获取历史数据
        # Lightweight Charts 需要 UNIX Timestamp (seconds) for intraday or 'YYYY-MM-DD' for daily
        data = self.data_provider.get_enhanced_data(symbol, period, interval)

        if 'error' in data:
            print(f"[ERROR] 获取历史数据失败 - 符号: {symbol}, 错误: {data.get('error')}")
            self._send_json_response(data)
            return
            
        raw_data = data.get('raw_data', [])
        formatted_data = []
        
        for item in raw_data:
            # 格式化为 Lightweight Charts 格式
            # time: '2019-04-11' or timestamp
            ts_str = item['time']
            try:
                # 解析时间戳 - 确保一致性
                if 'T' in ts_str:
                    # ISO format with time
                    dt = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                else:
                    # Just date
                    dt = datetime.strptime(ts_str.split(' ')[0], '%Y-%m-%d')
                
                # 对于日线、周线、月线，统一使用 'YYYY-MM-DD' 格式
                if interval in ['1d', '1wk', '1mo']:
                    time_val = dt.strftime('%Y-%m-%d')
                else:
                    # 分钟线使用 Unix 时间戳
                    time_val = int(dt.timestamp())
            except Exception as e:
                # 如果解析失败，尝试直接使用原始值
                print(f"⚠️ Time parsing error for {ts_str}: {e}")
                time_val = ts_str.split('T')[0] if 'T' in ts_str else ts_str

            # 验证数据的有效性 (Lightweight Charts 不接受 null/NaN 的价格)
            o, h, l, c, v = item['open'], item['high'], item['low'], item['close'], item['volume']
            
            # 检查是否有无效值
            has_invalid = False
            for val in [o, h, l, c]:
                if val is None:
                    has_invalid = True
                    break
                if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
                    has_invalid = True
                    break
            
            if has_invalid:
                continue

            record = {
                'time': time_val,
                'open': o,
                'high': h,
                'low': l,
                'close': c,
                'volume': v
            }
            # Add all other fields (indicators) - ensure they're properly formatted
            for k, v in item.items():
                if k not in record and k != 'timestamp':
                    # Convert numpy types and handle NaN
                    if v is not None:
                        if isinstance(v, (np.integer, np.floating)):
                            v = float(v)
                        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                            v = None
                    record[k] = v
            formatted_data.append(record)
            
        # Construct rich response
        response_data = {
            'candles': formatted_data,
            'info': data.get('company_info', {}),
            'signals': data.get('trading_signals', []),
            'risk': data.get('risk_metrics', {})
        }

        print(f"[LOG] 历史数据获取成功 - 符号: {symbol}, 数据点数: {len(formatted_data)}, 信号数: {len(response_data['signals'])}, 风险指标: {len(response_data['risk'])}")
        # 输出股价信息
        company_info = response_data['info']
        current_price = company_info.get('currentPrice', 'N/A')
        post_market_price = company_info.get('postMarketPrice', 'N/A')
        pre_market_price = company_info.get('preMarketPrice', 'N/A')
        previous_close = company_info.get('previousClose', 'N/A')
        print(f"[PRICE LOG] 当前股价: {current_price}, 前收盘价: {previous_close}, 盘前价: {pre_market_price}, 盘后价: {post_market_price}")

        # 尝试从历史数据中提取夜盘价格（最新的盘后交易数据）
        after_hours_prices = []
        for item in reversed(raw_data):  # 从最新数据开始检查
            ts_str = item['time']
            try:
                if 'T' in ts_str:
                    dt = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                else:
                    dt = datetime.strptime(ts_str.split(' ')[0], '%Y-%m-%d')

                # 检查是否为盘后时间（美东时间16:00后）
                if hasattr(dt, 'hour') and dt.hour >= 16:
                    after_hours_prices.append({
                        'time': ts_str,
                        'close': item.get('close'),
                        'volume': item.get('volume')
                    })
                    if len(after_hours_prices) >= 3:  # 只取最近3个夜盘价格
                        break
            except:
                continue

        if after_hours_prices:
            latest_after_hours = after_hours_prices[0]
            print(f"[NIGHT SESSION LOG] 最新夜盘价格 - 时间: {latest_after_hours['time']}, 收盘价: {latest_after_hours['close']}, 成交量: {latest_after_hours['volume']}")
            if len(after_hours_prices) > 1:
                print(f"[NIGHT SESSION LOG] 最近夜盘价格历史: {after_hours_prices}")

        # 输出最后几个数据点的详细信息
        if formatted_data:
            last_candle = formatted_data[-1]
            print(f"[HISTORY LOG] 最新数据点 - 时间: {last_candle.get('time')}, 开盘: {last_candle.get('open')}, 收盘: {last_candle.get('close')}, 成交量: {last_candle.get('volume')}")

        self._send_json_response(response_data)

    def _handle_indicators_api(self, parsed):
        # 复用 get_enhanced_data 中的指标计算
        params = parse_qs(parsed.query)
        symbol = params.get('symbol', ['AAPL'])[0]
        period = params.get('period', ['1y'])[0]
        interval = params.get('interval', ['1d'])[0]
        
        data = self.data_provider.get_enhanced_data(symbol, period, interval)
        if 'error' in data:
            self._send_json_response(data)
            return

        # 这里的 indicators 是最后一个点的，我们需要序列数据
        # 由于 EnhancedStockData 只返回了最后一个点的指标 (为了 API 效率)
        # 我们需要修改 EnhancedStockData 或者在这里重新计算序列
        # 暂时返回 raw_data 中的价格，前端可以用 JS 库计算，或者后端需要增强
        # 为了演示，我们暂时只返回 data 结构
        self._send_json_response(data)

    def _handle_enhanced_data(self, parsed):
        params = parse_qs(parsed.query)
        symbol = params.get('symbol', ['AAPL'])[0]
        period = params.get('period', ['1mo'])[0]
        interval = params.get('interval', ['1d'])[0]
        data = self.data_provider.get_enhanced_data(symbol, period, interval)
        self._send_json_response(data)

    def _handle_batch_data(self, parsed):
        params = parse_qs(parsed.query)
        symbols = params.get('symbols', ['AAPL,MSFT'])[0].split(',')
        batch_result = {}
        for symbol in symbols[:5]:
            batch_result[symbol] = self.data_provider.get_enhanced_data(symbol.strip(), '1mo', '1d')
        self._send_json_response(batch_result)

    def _handle_analysis_report(self, parsed):
        params = parse_qs(parsed.query)
        symbol = params.get('symbol', ['AAPL'])[0]
        data = self.data_provider.get_enhanced_data(symbol, '3mo', '1d')
        report = self._generate_analysis_report(data)
        self._send_json_response(report)
    
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        try:
            data = json.loads(post_data)
            symbol = data.get('symbol', 'AAPL')
            features = data.get('features', ['all'])
            result = self.data_provider.get_enhanced_data(symbol, '1mo', '1d')
            if features != ['all']:
                filtered = {}
                for feature in features:
                    if feature in result:
                        filtered[feature] = result[feature]
                result = filtered
            self._send_json_response(result)
        except Exception as e:
            self._send_json_response({'error': str(e)})

    def _send_json_response(self, data):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        # 清理数据中的 NaN 和 Infinity
        cleaned_data = self._clean_data(data)
        try:
            self.wfile.write(json.dumps(cleaned_data, ensure_ascii=False, indent=2).encode())
        except BrokenPipeError:
            # 客户端已断开连接，忽略错误
            pass
    
    def _clean_data(self, obj):
        """递归清理 NaN 和 Infinity"""
        if isinstance(obj, float):
            if math.isnan(obj) or math.isinf(obj):
                return None
            return obj
        elif isinstance(obj, dict):
            return {k: self._clean_data(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._clean_data(v) for v in obj]
        return obj

    def _generate_analysis_report(self, data):
        # ... logic as before ...
        if 'error' in data: return data
        return {
            'summary': {'symbol': data.get('metadata', {}).get('symbol'), 'time': datetime.now().isoformat()},
            'details': 'Analysis logic simplified for brevity in this update'
        }

    def _handle_symbols_api(self):
        try:
            # 动态导入配置
            import sys
            if os.getcwd() not in sys.path:
                sys.path.append(os.getcwd())
            from config import CONFIG
            
            symbols = CONFIG.get('trading', {}).get('symbols', [])
            symbol_strategy_map = CONFIG.get('symbol_strategy_map', {})
            
            # Return array of objects with symbol and strategy
            result = []
            for sym in symbols:
                strategy = symbol_strategy_map.get(sym, 'N/A')
                result.append({
                    'symbol': sym,
                    'strategy': strategy.upper() if strategy != 'N/A' else 'N/A'
                })
            
            self._send_json_response(result)
        except Exception as e:
            # Fallback to simple symbol list
            self._send_json_response([
                {'symbol': 'AAPL', 'strategy': 'A4'},
                {'symbol': 'NVDA', 'strategy': 'A4'},
                {'symbol': 'TSLA', 'strategy': 'A4'}
            ])

    def _handle_trades_api(self, parsed):
        params = parse_qs(parsed.query)
        symbol = params.get('symbol', [None])[0]

        try:
            file_path = os.path.join(os.getcwd(), 'data', 'trades.json')
            if not os.path.exists(file_path):
                print(f"[LOG] 交易数据文件不存在: {file_path}")
                self._send_json_response([])
                return

            with open(file_path, 'r') as f:
                trades = json.load(f)

            # 获取股价信息
            if symbol:
                try:
                    ticker = yf.Ticker(symbol)
                    info = ticker.info
                    current_price = info.get('currentPrice', info.get('regularMarketPrice', 'N/A'))
                    post_market_price = info.get('postMarketPrice', 'N/A')
                    pre_market_price = info.get('preMarketPrice', 'N/A')
                    previous_close = info.get('previousClose', 'N/A')
                    print(f"[PRICE LOG] 符号: {symbol} - 当前股价: {current_price}, 前收盘价: {previous_close}, 盘前价: {pre_market_price}, 盘后价: {post_market_price}")
                except Exception as e:
                    print(f"[PRICE LOG] 获取股价信息失败: {str(e)}")

            # 过滤
            if symbol:
                filtered_trades = [t for t in trades if t.get('symbol') == symbol]
                print(f"[LOG] 获取交易数据 - 符号: {symbol}, 总交易数: {len(trades)}, 过滤后: {len(filtered_trades)}")
                # 输出每个交易的详细信息
                for trade in filtered_trades:
                    print(f"[TRADE LOG] 符号: {trade.get('symbol')}, 类型: {trade.get('type')}, 价格: {trade.get('price')}, 数量: {trade.get('quantity')}, 时间: {trade.get('timestamp')}")
                trades = filtered_trades
            else:
                print(f"[LOG] 获取所有交易数据 - 总交易数: {len(trades)}")
                # 输出所有交易的详细信息
                for trade in trades:
                    print(f"[TRADE LOG] 符号: {trade.get('symbol')}, 类型: {trade.get('type')}, 价格: {trade.get('price')}, 数量: {trade.get('quantity')}, 时间: {trade.get('timestamp')}")

            self._send_json_response(trades)
        except Exception as e:
            print(f"[ERROR] 获取交易数据时出错: {str(e)}")
            self._send_json_response([])

    def _handle_update_strategy_api(self, parsed):
        """更新股票策略映射"""
        try:
            params = parse_qs(parsed.query)
            symbol = params.get('symbol', [None])[0]
            strategy = params.get('strategy', [None])[0]
            
            if not symbol or not strategy:
                self._send_json_response({'success': False, 'error': 'Missing symbol or strategy'})
                return
            
            # Read config.py
            config_path = 'config.py'
            if not os.path.exists(config_path):
                self._send_json_response({'success': False, 'error': 'config.py not found'})
                return
            
            with open(config_path, 'r', encoding='utf-8') as f:
                config_content = f.read()
            
            # Update or add the strategy mapping
            # Look for SYMBOL_STRATEGY_MAP section
            import re
            
            # Find the merged_map.update section or create it
            pattern = r"(merged_map\.update\(\{[^}]*\}\))"
            
            # Create the new mapping entry
            new_entry = f"    '{symbol}': '{strategy.lower()}',\n"
            
            # Check if symbol already exists in the update block
            if re.search(rf"'{symbol}':\s*'[^']*'", config_content):
                # Replace existing entry
                config_content = re.sub(
                    rf"('{symbol}':\s*)'[^']*'",
                    rf"\1'{strategy.lower()}'",
                    config_content
                )
            else:
                # Add new entry to merged_map.update block
                # Find the update block and add before the closing })
                if 'merged_map.update({' in config_content:
                    config_content = re.sub(
                        r'(merged_map\.update\(\{\n)',
                        rf'\1{new_entry}',
                        config_content
                    )
                else:
                    # Create new update block before the print statements
                    insert_pos = config_content.find('# 显示策略分配情况')
                    if insert_pos > 0:
                        config_content = (
                            config_content[:insert_pos] +
                            f"merged_map.update({{\n{new_entry}}})\n\n" +
                            config_content[insert_pos:]
                        )
            
            # Write back to config.py
            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(config_content)
            
            # Reload config module
            import sys
            if 'config' in sys.modules:
                del sys.modules['config']
            
            self._send_json_response({'success': True, 'symbol': symbol, 'strategy': strategy})
            
        except Exception as e:
            self._send_json_response({'success': False, 'error': str(e)})

    def _handle_runtime_strategy_api(self, parsed):
        """仅更新运行时的策略映射，不写入 config.py。"""
        try:
            params = parse_qs(parsed.query)
            symbol = params.get('symbol', [None])[0]
            strategy = params.get('strategy', [None])[0]

            if not symbol or not strategy:
                self._send_json_response({'success': False, 'error': 'Missing symbol or strategy'})
                return

            # 动态导入并更新内存中的 CONFIG
            import importlib
            import sys
            if os.getcwd() not in sys.path:
                sys.path.append(os.getcwd())
            config_module = importlib.import_module('config')
            # 刷新模块，确保取到最新 CONFIG 引用
            importlib.reload(config_module)

            cfg = config_module.CONFIG
            symbol_map = cfg.get('symbol_strategy_map', {})
            symbol_map[symbol] = strategy.lower()
            cfg['symbol_strategy_map'] = symbol_map

            # 创建重新加载标志文件
            os.makedirs('config', exist_ok=True)
            with open('config/.reload_needed', 'w') as f:
                f.write(f"{datetime.now().isoformat()}: Strategy updated for {symbol} to {strategy}")

            # 返回更新后的映射
            self._send_json_response({'success': True, 'symbol': symbol, 'strategy': strategy})
        except Exception as e:
            self._send_json_response({'success': False, 'error': str(e)})

    def _handle_price_update_api(self, parsed):
        """轻量级价格更新API，只返回最新价格和最近数据点"""
        try:
            params = parse_qs(parsed.query)
            symbol = params.get('symbol', ['AAPL'])[0]
            interval = params.get('interval', ['1d'])[0]

            # 使用yfinance快速获取最新价格信息
            ticker = yf.Ticker(symbol)
            info = ticker.info

            # 获取最近的几个数据点（用于更新图表）
            # 对于实时更新，我们只需要最新的1-2个数据点
            period = '1d' if interval in ['1m', '5m', '15m', '30m', '60m'] else '5d'
            hist = ticker.history(period=period, interval=interval, prepost=True)

            if hist.empty:
                self._send_json_response({'error': 'No data available'})
                return

            # 只取最新的几个数据点
            latest_count = 3 if interval in ['1m', '5m'] else 1
            latest_data = hist.tail(latest_count)

            # 格式化最新数据点
            formatted_latest = []
            for idx, row in latest_data.iterrows():
                record = {
                    'time': idx.isoformat() if hasattr(idx, 'isoformat') else str(idx),
                    'open': float(row['Open']) if not np.isnan(row['Open']) else None,
                    'high': float(row['High']) if not np.isnan(row['High']) else None,
                    'low': float(row['Low']) if not np.isnan(row['Low']) else None,
                    'close': float(row['Close']) if not np.isnan(row['Close']) else None,
                    'volume': int(row['Volume']) if 'Volume' in row and not np.isnan(row['Volume']) else 0,
                }
                formatted_latest.append(record)

            # 构建轻量级响应
            price_update = {
                'symbol': symbol,
                'timestamp': datetime.now().isoformat(),
                'company_info': {
                    'currentPrice': info.get('currentPrice', info.get('regularMarketPrice', 0)),
                    'previousClose': info.get('previousClose', 0),
                    'regularMarketPrice': info.get('regularMarketPrice', 0),
                    'preMarketPrice': info.get('preMarketPrice', None),
                    'postMarketPrice': info.get('postMarketPrice', None),
                    'regularMarketTime': info.get('regularMarketTime', None),
                    'preMarketTime': info.get('preMarketTime', None),
                    'postMarketTime': info.get('postMarketTime', None)
                },
                'latest_data': formatted_latest
            }

            self._send_json_response(price_update)

        except Exception as e:
            self._send_json_response({'error': f'Price update failed: {str(e)}'})

    def _handle_account_api(self):
        """处理IB账户信息API（使用共享的IB连接，确保在主线程中执行）"""
        try:
            # 获取共享的IB连接（在主线程中）
            trader = self.get_shared_ib_trader()
            if not trader:
                self._send_json_response({'error': '无法连接到IB'})
                return

            # 获取可用资金
            availableFunds = trader.get_available_funds()

            # 获取净资产
            netLiquidation = trader.get_net_liquidation()

            # 获取持仓信息
            holdings = trader.get_holdings()
            positions = []

            for pos in holdings:
                # 获取当前市场价格（简化版，使用yfinance）
                try:
                    import yfinance as yf
                    ticker = yf.Ticker(pos.contract.symbol)
                    current_price = ticker.info.get('currentPrice', ticker.info.get('regularMarketPrice', pos.avgCost))
                except:
                    current_price = pos.avgCost  # 如果获取失败，使用平均成本

                market_value = current_price * pos.position
                total_cost = pos.avgCost * pos.position
                unrealized_pnl = market_value - total_cost

                positions.append({
                    'symbol': pos.contract.symbol,
                    'position': pos.position,
                    'avgCost': pos.avgCost,
                    'marketValue': market_value,
                    'totalCost': total_cost,
                    'unrealizedPnL': unrealized_pnl,
                    'currentPrice': current_price
                })

            # 注意：不再断开连接，保持连接活跃以供后续使用

            # 返回数据
            account_data = {
                'availableFunds': availableFunds,
                'netLiquidation': netLiquidation,
                'positions': positions
            }

            self._send_json_response(account_data)

        except Exception as e:
            print(f"[ERROR] 获取账户信息失败: {str(e)}")
            self._send_json_response({'error': f'获取账户信息失败: {str(e)}'})

    def _handle_ib_connect_api(self):
        """连接IB API"""
        try:
            trader = self.get_shared_ib_trader()
            if trader and trader.connected:
                self._send_json_response({'success': True, 'message': 'IB已连接'})
            else:
                self._send_json_response({'success': False, 'error': 'IB连接失败'})
        except Exception as e:
            self._send_json_response({'success': False, 'error': str(e)})

    def _handle_ib_disconnect_api(self):
        """断开IB连接"""
        try:
            trader = self._shared_ib_trader
            if trader:
                trader.disconnect()
                self._shared_ib_trader = None
            self._send_json_response({'success': True, 'message': 'IB连接已断开'})
        except Exception as e:
            self._send_json_response({'success': False, 'error': str(e)})

    def _handle_ib_status_api(self):
        """检查IB连接状态"""
        try:
            trader = self._shared_ib_trader
            if trader and trader.is_connection_healthy():
                self._send_json_response({'connected': True, 'healthy': True})
            else:
                self._send_json_response({'connected': False, 'healthy': False})
        except Exception as e:
            self._send_json_response({'connected': False, 'healthy': False, 'error': str(e)})

    def _handle_ib_reconnect_api(self):
        """重连IB"""
        try:
            trader = self.get_shared_ib_trader()
            if trader and trader.connected:
                self._send_json_response({'success': True, 'message': 'IB已连接'})
            else:
                self._send_json_response({'success': False, 'error': 'IB重连失败'})
        except Exception as e:
            self._send_json_response({'success': False, 'error': str(e)})

    def _handle_ib_holdings_api(self):
        """获取IB持仓信息"""
        try:
            trader = self.get_shared_ib_trader()
            if not trader:
                self._send_json_response({'error': '无法连接到IB'})
                return

            holdings = trader.get_holdings()
            positions = []

            for pos in holdings:
                try:
                    import yfinance as yf
                    ticker = yf.Ticker(pos.contract.symbol)
                    current_price = ticker.info.get('currentPrice', ticker.info.get('regularMarketPrice', pos.avgCost))
                except:
                    current_price = pos.avgCost

                market_value = current_price * pos.position
                total_cost = pos.avgCost * pos.position
                unrealized_pnl = market_value - total_cost

                positions.append({
                    'symbol': pos.contract.symbol,
                    'position': pos.position,
                    'avgCost': pos.avgCost,
                    'marketValue': market_value,
                    'totalCost': total_cost,
                    'unrealizedPnL': unrealized_pnl,
                    'currentPrice': current_price
                })

            self._send_json_response({'positions': positions})
        except Exception as e:
            self._send_json_response({'error': str(e)})

    def _handle_ib_cancel_orders_api(self):
        """取消所有未完成订单"""
        try:
            trader = self.get_shared_ib_trader()
            if not trader:
                self._send_json_response({'error': '无法连接到IB'})
                return

            # 更新订单状态
            updated = trader.update_pending_trade_statuses()
            # 取消未完成订单
            cancelled = trader.cancel_open_orders()

            self._send_json_response({
                'success': True,
                'updated_trades': updated,
                'cancelled_orders': cancelled
            })
        except Exception as e:
            self._send_json_response({'success': False, 'error': str(e)})

    def _handle_ib_update_trades_api(self):
        """更新待处理交易状态"""
        try:
            trader = self.get_shared_ib_trader()
            if not trader:
                self._send_json_response({'error': '无法连接到IB'})
                return

            updated = trader.update_pending_trade_statuses()
            self._send_json_response({'success': True, 'updated_trades': updated})
        except Exception as e:
            self._send_json_response({'success': False, 'error': str(e)})

    def _handle_execute_signal_api(self):
        """执行交易信号"""
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(post_data)

            symbol = data.get('symbol')
            signal = data.get('signal')
            strategy_name = data.get('strategy', 'a1')
            current_price = data.get('current_price')

            if not symbol or not signal:
                self._send_json_response({'success': False, 'error': '缺少symbol或signal参数'})
                return

            # 动态导入策略
            import sys
            if os.getcwd() not in sys.path:
                sys.path.append(os.getcwd())

            from strategies.base_strategy import BaseStrategy
            from strategy_manager import StrategyManager

            # 获取IB trader
            trader = self.get_shared_ib_trader()
            if not trader:
                self._send_json_response({'success': False, 'error': '无法连接到IB'})
                return

            # 创建策略实例
            strategy_class_map = {
                'a1': 'strategies.a1_momentum_reversal.A1MomentumReversalStrategy',
                'a2': 'strategies.a2_zscore.A2ZScoreStrategy',
                'a3': 'strategies.a3_dual_ma_volume.A3DualMAVolumeStrategy',
                'a4': 'strategies.a4_pullback.A4PullbackStrategy',
                'a5': 'strategies.a5_multifactor_ai.A5MultiFactorAI',
                'a6': 'strategies.a6_news_trading.A6NewsTrading',
                'a7': 'strategies.a7_cta_trend.A7CTATrendStrategy',
                'a8': 'strategies.a8_rsi_oscillator.A8RSIOscillatorStrategy',
                'a9': 'strategies.a9_macd_crossover.A9MACDCrossoverStrategy',
                'a10': 'strategies.a10_bollinger_bands.A10BollingerBandsStrategy',
                'a11': 'strategies.a11_moving_average_crossover.A11MovingAverageCrossoverStrategy'
            }

            if strategy_name not in strategy_class_map:
                self._send_json_response({'success': False, 'error': f'未知策略: {strategy_name}'})
                return

            # 动态导入策略类
            module_name, class_name = strategy_class_map[strategy_name].rsplit('.', 1)
            module = __import__(module_name, fromlist=[class_name])
            strategy_class = getattr(module, class_name)

            # 创建策略实例
            strategy = strategy_class(config={}, ib_trader=trader)

            # 执行信号
            result = strategy.execute_signal(signal, current_price)

            self._send_json_response({'success': True, 'result': result})

        except Exception as e:
            self._send_json_response({'success': False, 'error': str(e)})

def run_enhanced_server(port=8001):
    # 在服务器启动前初始化IB连接
    print("正在初始化IB连接...")
    trader = EnhancedStockAPIHandler.get_shared_ib_trader()
    if trader:
        print("✅ IB连接初始化成功")

        # 获取并打印账户信息
        try:
            available_funds = trader.get_available_funds()
            net_liquidation = trader.get_net_liquidation()
            holdings = trader.get_holdings()

            print("📊 账户信息:")
            print(f"   可用资金: ${available_funds:,.2f}")
            print(f"   净资产: ${net_liquidation:,.2f}")
            print(f"   持仓数量: {len(holdings)} 个股票")

            if holdings:
                print("   持仓详情:")
                for pos in holdings:
                    print(f"     {pos.contract.symbol}: {pos.position} 股 @ ${pos.avgCost:.2f}")
        except Exception as e:
            print(f"⚠️ 获取账户信息失败: {str(e)}")
    else:
        print("❌ IB连接初始化失败，但服务器将继续启动")

    server_address = ('', port)
    httpd = HTTPServer(server_address, EnhancedStockAPIHandler)
    print(f'🚀 增强版数据服务器启动成功，端口 {port}')
    print(f'📊 仪表盘访问: http://localhost:{port}/dashboard')
    httpd.serve_forever()

if __name__ == '__main__':
    run_enhanced_server(port=8001)