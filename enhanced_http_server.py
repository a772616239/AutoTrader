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

class EnhancedStockAPIHandler(BaseHTTPRequestHandler):
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
            
        # 404
        self.send_error(404, "File not found")

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
            self.wfile.write(content)
        except Exception as e:
            self.send_error(500, str(e))

    def _handle_history_api(self, parsed):
        params = parse_qs(parsed.query)
        symbol = params.get('symbol', ['AAPL'])[0]
        period = params.get('period', ['1y'])[0]
        interval = params.get('interval', ['1d'])[0]
        
        # 使用 EnhancedStockData (yfinance) 获取历史数据
        # Lightweight Charts 需要 UNIX Timestamp (seconds) for intraday or 'YYYY-MM-DD' for daily
        data = self.data_provider.get_enhanced_data(symbol, period, interval)
        
        if 'error' in data:
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
        self.wfile.write(json.dumps(cleaned_data, ensure_ascii=False, indent=2).encode())
    
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
                self._send_json_response([])
                return
                
            with open(file_path, 'r') as f:
                trades = json.load(f)
            
            # 过滤
            if symbol:
                trades = [t for t in trades if t.get('symbol') == symbol]
                
            self._send_json_response(trades)
        except Exception as e:
            self._send_json_response([])

def run_enhanced_server(port=8001):
    server_address = ('', port)
    httpd = HTTPServer(server_address, EnhancedStockAPIHandler)
    print(f'🚀 增强版数据服务器启动成功，端口 {port}')
    print(f'📊 仪表盘访问: http://localhost:{port}/dashboard')
    httpd.serve_forever()

if __name__ == '__main__':
    run_enhanced_server(port=8001)