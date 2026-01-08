import os
os.environ["PANDAS_TA_NUMBA"] = "0"  # 关键：彻底禁用有问题的高速模块
import ccxt
import pandas as pd
import pandas_ta as ta
import time
from datetime import datetime

# --- 配置区 ---
SYMBOL = 'BTC/USDT'
TIMEFRAME = '5m'
# SuperTrend 参数 (7, 3 是超短线经典配置)
ST_PERIOD = 7
ST_MULTIPLIER = 3.0

# 初始化交易所 (币安)
exchange = ccxt.binance()


def fetch_data(symbol, timeframe):
    """获取最新的 K 线数据"""
    print(f"正在获取 {symbol} {timeframe} 数据...")
    # 获取最近 100 根 K 线
    bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=100)
    df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df


def get_signal(df):
    """计算 SuperTrend 信号"""
    # 使用 pandas_ta 计算 SuperTrend
    # 它返回四个列，我们主要用 SUPERTd (方向: 1为涨, -1为跌)
    st = ta.supertrend(df['high'], df['low'], df['close'], length=ST_PERIOD, multiplier=ST_MULTIPLIER)

    # 拼接数据
    df = pd.concat([df, st], axis=1)

    # 获取最后两行用于判断信号交叉
    last_row = df.iloc[-1]
    prev_row = df.iloc[-2]

    direction_col = f'SUPERTd_{ST_PERIOD}_{ST_MULTIPLIER}'

    # 逻辑判断
    if prev_row[direction_col] == -1 and last_row[direction_col] == 1:
        return "🚀 BUY (看涨信号出现)", last_row['close']
    elif prev_row[direction_col] == 1 and last_row[direction_col] == -1:
        return "🔻 SELL (看跌信号出现)", last_row['close']
    else:
        status = "持多中" if last_row[direction_col] == 1 else "持空中"
        return f"保持信号 ({status})", last_row['close']


def main():
    print(f"--- 5分钟级别 BTC 信号监控启动 ---")
    last_processed_time = None

    while True:
        try:
            df = fetch_data(SYMBOL, TIMEFRAME)
            current_time = df.iloc[-1]['timestamp']

            # 只有当新的 K 线生成或第一次运行时才打印
            if current_time != last_processed_time:
                signal, price = get_signal(df)
                now = datetime.now().strftime('%H:%M:%S')
                print(f"[{now}] 价格: {price} | 信号: {signal}")
                last_processed_time = current_time

            # 每 30 秒轮询一次
            time.sleep(30)

        except Exception as e:
            print(f"发生错误: {e}")
            time.sleep(10)


if __name__ == "__main__":
    main()