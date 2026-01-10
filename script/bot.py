import os

os.environ["PANDAS_TA_NUMBA"] = "0"  # 关键：彻底禁用有问题的高速模块
import ccxt
import pandas as pd
import pandas_ta as ta
import time
from datetime import datetime, timedelta
import json
import csv
from pathlib import Path
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 配置区 ---
SYMBOL = 'BTC/USDT'
TIMEFRAME = '5m'
# SuperTrend 参数 (7, 3 是超短线经典配置)
ST_PERIOD = 7
ST_MULTIPLIER = 3.0


# --- 日志管理器类 ---
class TradeLogger:
    def __init__(self, log_dir="trade_logs"):
        """初始化日志管理器"""
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)

        # 当前日志文件
        self.current_date = None
        self.csv_file = None
        self.csv_writer = None

        # 初始化日志文件
        self._init_log_file()

        # JSON日志文件（用于详细记录）
        self.json_log_file = self.log_dir / f"trades_{datetime.now().strftime('%Y%m')}.json"
        self._load_json_log()

    def _init_log_file(self):
        """初始化CSV日志文件"""
        today = datetime.now().date()

        # 如果日期变化，创建新文件
        if self.current_date != today:
            self.current_date = today
            filename = f"trades_{today.strftime('%Y%m%d')}.csv"
            self.csv_file = self.log_dir / filename

            # 如果文件不存在，创建并写入表头
            if not self.csv_file.exists():
                with open(self.csv_file, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        '时间戳', '时间', '操作类型', '交易对', '方向',
                        '价格', '数量', '持仓状态', '入场价', '盈亏(%)',
                        '备注'
                    ])

            print(f"📝 日志文件: {self.csv_file}")

    def _load_json_log(self):
        """加载JSON日志文件"""
        if self.json_log_file.exists():
            try:
                with open(self.json_log_file, 'r', encoding='utf-8') as f:
                    self.json_log = json.load(f)
            except:
                self.json_log = {}
        else:
            self.json_log = {}

    def _save_json_log(self):
        """保存JSON日志"""
        with open(self.json_log_file, 'w', encoding='utf-8') as f:
            json.dump(self.json_log, f, ensure_ascii=False, indent=2)

    def log_trade(self, trade_data):
        """记录交易日志

        Args:
            trade_data: 字典，包含以下字段：
                - timestamp: 时间戳
                - operation: 操作类型 ('开多', '开空', '平多', '平空')
                - symbol: 交易对
                - direction: 方向 ('long', 'short')
                - price: 价格
                - amount: 数量 (可选)
                - position_status: 持仓状态
                - entry_price: 入场价 (平仓时)
                - pnl_percent: 盈亏百分比 (平仓时)
                - notes: 备注
        """
        # 确保日志文件是最新的
        self._init_log_file()

        # 获取时间
        trade_time = datetime.fromtimestamp(trade_data['timestamp'])

        # CSV记录
        with open(self.csv_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                trade_data['timestamp'],
                trade_time.strftime('%Y-%m-%d %H:%M:%S'),
                trade_data['operation'],
                trade_data.get('symbol', SYMBOL),
                trade_data.get('direction', ''),
                trade_data['price'],
                trade_data.get('amount', ''),
                trade_data.get('position_status', ''),
                trade_data.get('entry_price', ''),
                trade_data.get('pnl_percent', ''),
                trade_data.get('notes', '')
            ])

        # JSON记录（按天分组）
        day_key = trade_time.strftime('%Y%m%d')
        if day_key not in self.json_log:
            self.json_log[day_key] = []

        # 添加详细记录
        detailed_record = {
            'time': trade_time.strftime('%H:%M:%S.%f')[:-3],
            'datetime': trade_time.isoformat(),
            **trade_data
        }
        self.json_log[day_key].append(detailed_record)

        # 限制每天最多1000条记录
        if len(self.json_log[day_key]) > 1000:
            self.json_log[day_key] = self.json_log[day_key][-1000:]

        self._save_json_log()

        print(f"📋 交易已记录: {trade_data['operation']} @ {trade_data['price']:.2f}")

    def get_daily_summary(self, date_str=None):
        """获取每日交易总结"""
        if date_str is None:
            date_str = datetime.now().strftime('%Y%m%d')

        if date_str in self.json_log:
            trades = self.json_log[date_str]
            return self._calculate_summary(trades)
        return None

    def _calculate_summary(self, trades):
        """计算交易总结"""
        summary = {
            '总交易次数': len(trades),
            '盈利交易': 0,
            '亏损交易': 0,
            '总盈亏百分比': 0,
            '开多次数': 0,
            '开空次数': 0
        }

        for trade in trades:
            if trade['operation'] in ['开多', '开空']:
                if trade['operation'] == '开多':
                    summary['开多次数'] += 1
                else:
                    summary['开空次数'] += 1
            elif trade['operation'] in ['平多', '平空']:
                pnl = trade.get('pnl_percent', 0)
                summary['总盈亏百分比'] += pnl
                if pnl > 0:
                    summary['盈利交易'] += 1
                elif pnl < 0:
                    summary['亏损交易'] += 1

        return summary

    def print_daily_summary(self):
        """打印今日交易总结"""
        today = datetime.now().strftime('%Y%m%d')
        summary = self.get_daily_summary(today)

        if summary:
            print("\n" + "=" * 60)
            print(f"📊 今日交易总结 ({datetime.now().strftime('%Y-%m-%d')})")
            print("=" * 60)
            for key, value in summary.items():
                print(f"{key:>15}: {value}")
            print("=" * 60)


# --- TradingBot 类（集成日志）---
class TradingBot:
    def __init__(self, symbol, timeframe):
        self.symbol = symbol
        self.timeframe = timeframe
        self.position = None  # 当前持仓：'long'(多), 'short'(空), None(无)
        self.last_signal = None  # 上一次信号类型
        self.entry_price = None  # 入场价格
        self.entry_time = None  # 入场时间
        self.position_amount = 0.001  # 仓位大小（示例，可根据需要调整）

        # 初始化日志管理器
        self.logger = TradeLogger()

    def on_buy_signal(self, price, timestamp):
        """当买入信号出现时执行"""
        print(f"\n{'=' * 50}")
        print(f"📈 买入信号触发!")
        print(f"时间: {timestamp}")
        print(f"价格: {price:.2f}")
        print(f"当前持仓: {self.position}")
        print(f"{'=' * 50}")

        # 交易逻辑
        if self.position == 'short':
            print("🔄 执行平空操作...")
            self.close_position(price, "平空", timestamp)
            self.position = None

        if self.position is None:
            print("🟢 执行开多操作...")
            self.open_position('long', price, timestamp)
        else:
            print("⏸️ 已有持仓，忽略信号")
            self.log_trade({
                'timestamp': time.time(),
                'operation': '信号忽略',
                'price': price,
                'position_status': self.position,
                'notes': '已有持仓，忽略买入信号'
            })

    def on_sell_signal(self, price, timestamp):
        """当卖出信号出现时执行"""
        print(f"\n{'=' * 50}")
        print(f"📉 卖出信号触发!")
        print(f"时间: {timestamp}")
        print(f"价格: {price:.2f}")
        print(f"当前持仓: {self.position}")
        print(f"{'=' * 50}")

        # 交易逻辑
        if self.position == 'long':
            print("🔄 执行平多操作...")
            self.close_position(price, "平多", timestamp)
            self.position = None

        if self.position is None:
            print("🔴 执行开空操作...")
            self.open_position('short', price, timestamp)
        else:
            print("⏸️ 已有持仓，忽略信号")
            self.log_trade({
                'timestamp': time.time(),
                'operation': '信号忽略',
                'price': price,
                'position_status': self.position,
                'notes': '已有持仓，忽略卖出信号'
            })

    def open_position(self, side, price, timestamp):
        """开仓并记录日志"""
        self.position = side
        self.entry_price = price
        self.entry_time = timestamp

        operation = '开多' if side == 'long' else '开空'
        print(f"✅ {operation}仓已开 | 价格: {price:.2f} | 时间: {timestamp}")

        # 记录开仓日志
        self.log_trade({
            'timestamp': time.time(),
            'operation': operation,
            'direction': side,
            'price': price,
            'amount': self.position_amount,
            'position_status': side,
            'entry_price': price,
            'notes': f'SuperTrend信号 {operation}'
        })

        # 这里可以添加实际的下单代码
        # if side == 'long':
        #     order = exchange.create_order(SYMBOL, 'market', 'buy', self.position_amount)
        # elif side == 'short':
        #     order = exchange.create_order(SYMBOL, 'market', 'sell', self.position_amount)

    def close_position(self, price, reason, timestamp):
        """平仓并记录日志"""
        if self.position and self.entry_price:
            # 计算盈亏
            if self.position == 'long':
                pnl_percent = ((price - self.entry_price) / self.entry_price * 100)
            else:  # short
                pnl_percent = ((self.entry_price - price) / self.entry_price * 100)

            operation = '平多' if self.position == 'long' else '平空'
            pnl_symbol = '+' if pnl_percent > 0 else ''

            print(f"🏁 {operation} | 入场价: {self.entry_price:.2f} | "
                  f"出场价: {price:.2f} | 盈亏: {pnl_symbol}{pnl_percent:+.2f}%")

            # 记录平仓日志
            self.log_trade({
                'timestamp': time.time(),
                'operation': operation,
                'direction': self.position,
                'price': price,
                'amount': self.position_amount,
                'position_status': '无持仓',
                'entry_price': self.entry_price,
                'pnl_percent': round(pnl_percent, 2),
                'notes': f'{reason} | 盈亏: {pnl_symbol}{pnl_percent:+.2f}%'
            })
        else:
            print(f"⚠️  {reason} | 无持仓可平")

        self.position = None
        self.entry_price = None
        self.entry_time = None

    def log_trade(self, trade_data):
        """记录交易日志的便捷方法"""
        trade_data['symbol'] = self.symbol
        self.logger.log_trade(trade_data)

    def process_signal(self, signal_type, price, timestamp):
        """处理信号，避免重复触发"""
        if signal_type != self.last_signal:
            self.last_signal = signal_type

            if signal_type == "BUY":
                self.on_buy_signal(price, timestamp)
            elif signal_type == "SELL":
                self.on_sell_signal(price, timestamp)
            return True
        return False

    def get_position_info(self):
        """获取当前持仓信息"""
        if self.position and self.entry_price:
            current_time = datetime.now()
            entry_dt = self.entry_time
            if isinstance(entry_dt, pd.Timestamp):
                entry_dt = entry_dt.to_pydatetime()

            hold_time = current_time - entry_dt
            hold_minutes = hold_time.total_seconds() / 60

            return f"{self.position}仓 @ {self.entry_price:.2f} (持{hold_minutes:.1f}分钟)"
        return "无持仓"


# 创建交易机器人实例
bot = TradingBot(SYMBOL, TIMEFRAME)

my_proxy = 'http://127.0.0.1:10808'

# 初始化交易所
exchange = ccxt.okx({
    'verify': False, # 临时跳过 SSL 验证，确认是否为证书冲突
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'},
    # 'proxies': {
    #         'http': my_proxy,
    #         'https': my_proxy,
    # }
})


def fetch_data(symbol, timeframe):
    """获取最新的 K 线数据"""
    print(f"正在获取 {symbol} {timeframe} 数据...", end=" ")
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=100)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        print(f"成功，获取到 {len(df)} 条数据")
        return df
    except Exception as e:
        print(f"失败: {e}")
        raise


def get_signal(df):
    """计算 SuperTrend 信号"""
    st = ta.supertrend(df['high'], df['low'], df['close'],
                       length=ST_PERIOD, multiplier=ST_MULTIPLIER)
    df = pd.concat([df, st], axis=1)

    last_row = df.iloc[-1]
    prev_row = df.iloc[-2]
    direction_col = f'SUPERTd_{ST_PERIOD}_{ST_MULTIPLIER}'

    signal_type = None
    signal_text = ""

    if prev_row[direction_col] == -1 and last_row[direction_col] == 1:
        signal_type = "BUY"
        signal_text = "🚀 BUY (看涨信号出现)"
    elif prev_row[direction_col] == 1 and last_row[direction_col] == -1:
        signal_type = "SELL"
        signal_text = "🔻 SELL (看跌信号出现)"
    else:
        status = "持多中" if last_row[direction_col] == 1 else "持空中"
        signal_text = f"保持信号 ({status})"

    if signal_type:
        bot.process_signal(signal_type, last_row['close'], last_row['timestamp'])

    return signal_text, last_row['close'], df


def main():
    print(f"=== 5分钟级别 BTC SuperTrend 交易机器人启动 ===")
    print(f"交易对: {SYMBOL}")
    print(f"时间框架: {TIMEFRAME}")
    print(f"SuperTrend参数: {ST_PERIOD}/{ST_MULTIPLIER}")
    print(f"交易所: {exchange.id}")
    print(f"日志目录: trade_logs/")
    print("=" * 60)

    last_processed_time = None
    check_count = 0
    last_summary_print = datetime.now()

    try:
        while True:
            check_count += 1
            current_time = datetime.now()
            print(f"\n[检查 #{check_count}] {current_time.strftime('%Y-%m-%d %H:%M:%S')}")

            # 每1小时打印一次当日总结
            if (current_time - last_summary_print).seconds >= 3600:
                bot.logger.print_daily_summary()
                last_summary_print = current_time

            # 获取数据
            df = fetch_data(SYMBOL, TIMEFRAME)
            current_kline_time = df.iloc[-1]['timestamp']

            if current_kline_time != last_processed_time:
                signal, price, df_with_signals = get_signal(df)

                position_info = bot.get_position_info()
                print(f"[{current_time.strftime('%H:%M:%S')}] "
                      f"价格: {price:>10.2f} | "
                      f"信号: {signal:<20} | "
                      f"持仓: {position_info}")

                direction_col = f'SUPERTd_{ST_PERIOD}_{ST_MULTIPLIER}'
                last_direction = df_with_signals.iloc[-1][direction_col]
                print(f"       SuperTrend方向: {'🟢 看涨' if last_direction == 1 else '🔴 看跌'}")

                last_processed_time = current_kline_time
            else:
                position_info = bot.get_position_info()
                print(f"等待新K线生成... | 持仓: {position_info}")

            print(f"下次检查: {datetime.fromtimestamp(time.time() + 30).strftime('%H:%M:%S')}")
            time.sleep(30)

    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断程序")
        print("当前持仓状态:", bot.get_position_info())
        bot.logger.print_daily_summary()
        print("\n程序退出")

    except Exception as e:
        print(f"\n❌ 发生错误: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        print("等待30秒后重试...")
        time.sleep(30)


if __name__ == "__main__":
    main()