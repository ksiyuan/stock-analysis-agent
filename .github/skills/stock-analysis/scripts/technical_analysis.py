# -*- coding: utf-8 -*-
"""
技术面分析：MA/MACD/RSI/KDJ/BOLL + K线图 + 指标图
用法: python technical_analysis.py [工作区路径] [输出目录]
依赖: 先运行 fetch_market.py 生成 market_data.pkl
"""
import os
import json
import numpy as np
import pandas as pd
import mplfinance as mpf

import common

BASE, OUT = common.parse_cli()
plt = common.setup_fonts()

DATA = common.load_market()


def plot_kline(df, code, name, source):
    data = df.copy()
    data.index = pd.DatetimeIndex(data["date"])
    style = mpf.make_mpf_style(
        base_mpf_style="charles",
        rc={"font.family": "sans-serif",
            "font.sans-serif": ["Microsoft YaHei", "SimHei", "DejaVu Sans"],
            "font.weight": "normal", "axes.unicode_minus": False},
    )
    addplots = [
        mpf.make_addplot(data["MA5"], color="orange", width=1.0),
        mpf.make_addplot(data["MA10"], color="blue", width=1.0),
        mpf.make_addplot(data["MA20"], color="purple", width=1.0),
        mpf.make_addplot(data["BOLL_UP"], color="gray", width=0.8, linestyle="--"),
        mpf.make_addplot(data["BOLL_LOW"], color="gray", width=0.8, linestyle="--"),
    ]
    path = os.path.join(OUT, f"analysis_{code}_kline.png")
    mpf.plot(data[["open", "high", "low", "close", "volume"]],
             type="candle", style=style, addplot=addplots, volume=True,
             title=f"\n{code} {name} K线（{source}）", ylabel="价格",
             ylabel_lower="成交量", figsize=(13, 7),
             savefig=dict(fname=path, dpi=110))
    return path


def plot_indicators(df, code, name, source):
    dates = pd.to_datetime(df["date"])
    fig, axes = plt.subplots(3, 1, figsize=(13, 10), sharex=True)
    ax = axes[0]
    ax.plot(dates, df["DIF"], label="DIF", color="#1f77b4", lw=1)
    ax.plot(dates, df["DEA"], label="DEA", color="#ff7f0e", lw=1)
    ax.bar(dates, df["MACD"], label="MACD", color=np.where(df["MACD"] >= 0, "#d62728", "#2ca02c"), width=1)
    ax.axhline(0, color="black", lw=0.6)
    ax.set_title("MACD (12,26,9)")
    ax.legend(loc="upper left", ncol=3, fontsize=8)
    ax.grid(True, alpha=0.3)
    ax = axes[1]
    ax.plot(dates, df["RSI"], color="#9467bd", lw=1.2)
    ax.axhline(70, color="#d62728", ls="--", lw=0.8)
    ax.axhline(30, color="#2ca02c", ls="--", lw=0.8)
    ax.fill_between(dates, 30, 70, color="gray", alpha=0.1)
    ax.set_title("RSI(14) 超买>70 / 超卖<30")
    ax.set_ylim(0, 100)
    ax.grid(True, alpha=0.3)
    ax = axes[2]
    ax.plot(dates, df["K"], label="K", color="#1f77b4", lw=1)
    ax.plot(dates, df["D"], label="D", color="#ff7f0e", lw=1)
    ax.plot(dates, df["J"], label="J", color="#9467bd", lw=1)
    ax.axhline(80, color="#d62728", ls="--", lw=0.8)
    ax.axhline(20, color="#2ca02c", ls="--", lw=0.8)
    ax.set_title("KDJ (9,3,3)")
    ax.legend(loc="upper left", ncol=3, fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.suptitle(f"{code} {name} 技术指标（{source}）")
    fig.tight_layout()
    path = os.path.join(OUT, f"analysis_{code}_indicators.png")
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


def summarize(df):
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last
    ret5 = (last["close"] / df.iloc[-6]["close"] - 1) * 100 if len(df) > 5 else np.nan
    ret20 = (last["close"] / df.iloc[-21]["close"] - 1) * 100 if len(df) > 20 else np.nan
    ret60 = (last["close"] / df.iloc[-61]["close"] - 1) * 100 if len(df) > 60 else np.nan
    hi60 = df["high"].tail(60).max()
    lo60 = df["low"].tail(60).min()
    support, resistance = common.support_resistance(df)
    breakout, breakout_note = common.volume_breakout(df)
    cycle_high = common.cycle_high(df["close"])  # 本轮上涨高点（策略⑩卖出基准）
    return {
        "date": str(last["date"]), "close": round(float(last["close"]), 3),
        "chg_pct": round((last["close"] / prev["close"] - 1) * 100, 2),
        "ret5": round(ret5, 2), "ret20": round(ret20, 2), "ret60": round(ret60, 2),
        "MA5": round(float(last["MA5"]), 3), "MA10": round(float(last["MA10"]), 3),
        "MA20": round(float(last["MA20"]), 3),
        "RSI": round(float(last["RSI"]), 1),
        "K": round(float(last["K"]), 1), "D": round(float(last["D"]), 1), "J": round(float(last["J"]), 1),
        "DIF": round(float(last["DIF"]), 3), "DEA": round(float(last["DEA"]), 3),
        "MACD": round(float(last["MACD"]), 3),
        "BOLL_UP": round(float(last["BOLL_UP"]), 3),
        "BOLL_MID": round(float(last["BOLL_MID"]), 3),
        "BOLL_LOW": round(float(last["BOLL_LOW"]), 3),
        "hi60": round(float(hi60), 3), "lo60": round(float(lo60), 3),
        "pos_60": round((last["close"] - lo60) / (hi60 - lo60) * 100, 1) if hi60 > lo60 else 50.0,
        "cycle_high": cycle_high,  # 本轮上涨高点（用户策略⑩）
        "support": support, "resistance": resistance,
        "breakout": breakout_note if breakout else "",
    }


if __name__ == "__main__":
    summary_rows = []
    json_out = {}
    for code, v in DATA.items():
        df = common.compute_indicators(v["df"].copy())
        s = summarize(df)
        s["code"], s["name"], s["type"] = code, v["name"], v["type"]
        s["comment"] = common.trend_comment(s)
        summary_rows.append(s)
        json_out[code] = s
        try:
            plot_kline(df, code, v["name"], v["source"])
            plot_indicators(df, code, v["name"], v["source"])
            print(f"[OK] {code} {v['name']} 图已生成")
        except Exception as e:
            print(f"[WARN] {code} 绘图失败: {type(e).__name__} {str(e)[:80]}")

    smry = pd.DataFrame(summary_rows).sort_values("code")
    smry.to_csv(os.path.join(OUT, "技术指标汇总.csv"), index=False, encoding="utf-8-sig")
    with open(os.path.join(OUT, "技术指标.json"), "w", encoding="utf-8") as f:
        json.dump(json_out, f, ensure_ascii=False, indent=1)
    print(f"\n[OK] 技术指标汇总.csv / 技术指标.json 已保存到 {OUT}")
