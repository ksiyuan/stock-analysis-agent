"""
AkShare 股票数据获取与可视化示例脚本
====================================
演示：获取 A 股历史行情（东方财富优先、新浪回退）、
      计算技术指标（MA / MACD / RSI / KDJ / BOLL）、绘制 K 线图。

运行方式：
    python demo_akshare.py

图表输出目录：output/
数据规范遵循 .github/instructions/股票数据获取.instructions.md
"""

import os
import warnings

import akshare as ak
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # 无界面后端，直接保存图片
import matplotlib.pyplot as plt
from matplotlib import font_manager
import mplfinance as mpf

# mplfinance 内置样式查找特定 font weight 的良性警告，予以忽略
warnings.filterwarnings("ignore", message=r"findfont: Failed to find font weight")

# 注册系统中文字体（Windows），避免图表中文显示为方块
_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",    # 微软雅黑
    r"C:\Windows\Fonts\simhei.ttf",  # 黑体
    r"C:\Windows\Fonts\Deng.ttf",    # 等线
]
for _fp in _FONT_CANDIDATES:
    if os.path.exists(_fp):
        try:
            font_manager.fontManager.addfont(_fp)
        except Exception:
            pass
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DengXian", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

OUTPUT_DIR = "output"


def get_hist_with_fallback(symbol: str, start: str, end: str, adjust: str = "qfq") -> pd.DataFrame:
    """获取历史行情，东方财富优先，失败自动回退新浪数据源。

    参数:
        symbol: 6 位 A 股代码，如 "600519"
        start/end: 日期，格式 "YYYYMMDD"
        adjust: "qfq" 前复权 / "hfq" 后复权 / "" 不复权
    返回:
        DataFrame，统一列名：date/open/high/low/close/volume/amount
        （来源记录在 df.attrs["source"]）
    """
    sh = "sh" + symbol if symbol.startswith("6") else "sz" + symbol
    source = "东方财富"
    try:
        df = ak.stock_zh_a_hist(
            symbol=symbol, period="daily",
            start_date=start, end_date=end, adjust=adjust,
        )
        df = df.rename(columns={
            "日期": "date", "开盘": "open", "收盘": "close",
            "最高": "high", "最低": "low", "成交量": "volume", "成交额": "amount",
        })
    except Exception:
        source = "新浪财经"
        df = ak.stock_zh_a_daily(
            symbol=sh, start_date=start, end_date=end, adjust=adjust,
        )
        df = df[["date", "open", "high", "low", "close", "volume", "amount"]].copy()

    df = df.sort_values("date").reset_index(drop=True)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df.attrs["source"] = source
    return df


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """计算常用技术指标：MA5/10/20、MACD、RSI、KDJ、BOLL。"""
    out = df.copy()
    close, high, low = out["close"], out["high"], out["low"]

    # --- 均线 MA ---
    out["MA5"] = close.rolling(5).mean()
    out["MA10"] = close.rolling(10).mean()
    out["MA20"] = close.rolling(20).mean()

    # --- MACD (12, 26, 9) ---
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    out["DIF"] = ema12 - ema26
    out["DEA"] = out["DIF"].ewm(span=9, adjust=False).mean()
    out["MACD"] = (out["DIF"] - out["DEA"]) * 2

    # --- RSI (14) ---
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    out["RSI"] = 100 - 100 / (1 + rs)

    # --- KDJ (9, 3, 3) ---
    low9 = low.rolling(9).min()
    high9 = high.rolling(9).max()
    rsv = (close - low9) / (high9 - low9).replace(0, np.nan) * 100
    out["K"] = rsv.ewm(com=2, adjust=False).mean()   # SMA(RSV, 3)
    out["D"] = out["K"].ewm(com=2, adjust=False).mean()
    out["J"] = 3 * out["K"] - 2 * out["D"]

    # --- BOLL (20, 2) ---
    out["BOLL_MID"] = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    out["BOLL_UP"] = out["BOLL_MID"] + 2 * std20
    out["BOLL_LOW"] = out["BOLL_MID"] - 2 * std20

    return out


def plot_kline(df: pd.DataFrame, symbol: str, source: str) -> str:
    """绘制 K 线主图（蜡烛图 + 均线 + BOLL + 成交量）。"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    data = df.copy()
    data.index = pd.DatetimeIndex(data["date"])

    # 自定义样式：在 charles 基础上强制使用中文字体（否则 mplfinance 会覆盖为 DejaVu Sans）
    style = mpf.make_mpf_style(
        base_mpf_style="charles",
        rc={
            "font.family": "sans-serif",
            "font.sans-serif": ["Microsoft YaHei", "SimHei", "DejaVu Sans"],
            "font.weight": "normal",
            "axes.unicode_minus": False,
        },
    )

    addplots = [
        mpf.make_addplot(data["MA5"], color="orange", width=1.0, label="MA5"),
        mpf.make_addplot(data["MA10"], color="blue", width=1.0, label="MA10"),
        mpf.make_addplot(data["MA20"], color="purple", width=1.0, label="MA20"),
        mpf.make_addplot(data["BOLL_UP"], color="gray", width=0.8, linestyle="--"),
        mpf.make_addplot(data["BOLL_LOW"], color="gray", width=0.8, linestyle="--"),
    ]
    out_path = os.path.join(OUTPUT_DIR, f"{symbol}_kline.png")
    mpf.plot(
        data[["open", "high", "low", "close", "volume"]],
        type="candle", style=style, addplot=addplots,
        volume=True, title=f"\n{symbol} K线图（{source}）",
        ylabel="价格", ylabel_lower="成交量",
        figsize=(14, 8), savefig=dict(fname=out_path, dpi=100),
    )
    return out_path


def plot_indicators(df: pd.DataFrame, symbol: str, source: str) -> str:
    """绘制技术指标副图：MACD / RSI / KDJ。"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    dates = pd.to_datetime(df["date"])

    fig, axes = plt.subplots(3, 1, figsize=(14, 11), sharex=True)

    # --- MACD ---
    ax = axes[0]
    ax.plot(dates, df["DIF"], label="DIF", color="#1f77b4", linewidth=1)
    ax.plot(dates, df["DEA"], label="DEA", color="#ff7f0e", linewidth=1)
    ax.bar(dates, df["MACD"], label="MACD柱", color=np.where(df["MACD"] >= 0, "#d62728", "#2ca02c"), width=1)
    ax.axhline(0, color="black", linewidth=0.6)
    ax.set_title("MACD (12,26,9)")
    ax.legend(loc="upper left", ncol=3)
    ax.grid(True, alpha=0.3)

    # --- RSI ---
    ax = axes[1]
    ax.plot(dates, df["RSI"], color="#9467bd", linewidth=1.2)
    ax.axhline(70, color="#d62728", linestyle="--", linewidth=0.8)
    ax.axhline(30, color="#2ca02c", linestyle="--", linewidth=0.8)
    ax.fill_between(dates, 30, 70, color="gray", alpha=0.1)
    ax.set_title("RSI (14)  —  超买>70 / 超卖<30")
    ax.set_ylim(0, 100)
    ax.grid(True, alpha=0.3)

    # --- KDJ ---
    ax = axes[2]
    ax.plot(dates, df["K"], label="K", color="#1f77b4", linewidth=1)
    ax.plot(dates, df["D"], label="D", color="#ff7f0e", linewidth=1)
    ax.plot(dates, df["J"], label="J", color="#9467bd", linewidth=1)
    ax.axhline(80, color="#d62728", linestyle="--", linewidth=0.8)
    ax.axhline(20, color="#2ca02c", linestyle="--", linewidth=0.8)
    ax.set_title("KDJ (9,3,3)")
    ax.legend(loc="upper left", ncol=3)
    ax.grid(True, alpha=0.3)

    fig.suptitle(f"{symbol} 技术指标（{source}）")
    fig.tight_layout()
    out_path = os.path.join(OUTPUT_DIR, f"{symbol}_indicators.png")
    fig.savefig(out_path, dpi=100)
    plt.close(fig)
    return out_path


def main() -> None:
    symbol = "600519"  # 贵州茅台
    start, end = "20260701", "20260815"

    print(f"正在获取 {symbol} 的历史行情 ...")
    df = get_hist_with_fallback(symbol, start, end)
    source = df.attrs.get("source", "未知")
    print(f"数据来源: {source} | 共 {len(df)} 条记录")

    df = compute_indicators(df)

    cols = ["date", "open", "close", "high", "low", "volume",
            "MA5", "MA10", "MA20", "MACD", "RSI", "K", "D", "J"]
    print("\n最近 5 个交易日：")
    print(df[cols].tail(5).to_string(index=False))

    latest = df.iloc[-1]
    print("\n" + "=" * 52)
    print(f"最新收盘价: {latest['close']:.2f}  (数据截止 {latest['date']})")
    print(f"MA5 : {latest['MA5']:.2f}  |  MA10: {latest['MA10']:.2f}  |  MA20: {latest['MA20']:.2f}")
    print(f"MACD: DIF={latest['DIF']:.2f}  DEA={latest['DEA']:.2f}  柱={latest['MACD']:.2f}")
    print(f"RSI : {latest['RSI']:.2f}")
    print(f"KDJ : K={latest['K']:.2f}  D={latest['D']:.2f}  J={latest['J']:.2f}")
    print(f"BOLL: 上轨={latest['BOLL_UP']:.2f}  中轨={latest['BOLL_MID']:.2f}  下轨={latest['BOLL_LOW']:.2f}")

    trend = "多头排列" if latest["MA5"] > latest["MA10"] > latest["MA20"] else "非多头排列"
    print("-" * 52)
    print(f"均线形态: {trend}")
    print("=" * 52)

    kline_path = plot_kline(df, symbol, source)
    ind_path = plot_indicators(df, symbol, source)
    print(f"\n[OK] K 线图已保存: {kline_path}")
    print(f"[OK] 技术指标图已保存: {ind_path}")


if __name__ == "__main__":
    main()
