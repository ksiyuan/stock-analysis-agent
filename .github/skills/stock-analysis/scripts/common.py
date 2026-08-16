# -*- coding: utf-8 -*-
"""
股票分析技能 - 公共工具模块
提供：工作区路径解析、中文字体注册、同花顺文件解析、行情获取、技术指标计算
所有脚本统一 import 本模块，保证路径与口径一致。
"""
import os
import sys
import time
import pickle

import numpy as np
import pandas as pd

# ---------- 控制台 UTF-8 输出（避免 GBK 打印中文报错） ----------
def setup_console_utf8():
    """强制 stdout/stderr 使用 UTF-8，避免 Windows GBK 控制台无法打印中文/特殊字符。"""
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if sys.stderr and hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


setup_console_utf8()

# ---------- 工作区路径 ----------
# 技能脚本位于 .github/skills/stock-analysis/scripts/，向上 4 级即工作区根目录
_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.abspath(os.path.join(_SCRIPTS_DIR, "..", "..", "..", ".."))
OUT = os.path.join(BASE, "output")
DATA_PKL = os.path.join(OUT, "market_data.pkl")


def setup_paths(work_base=None, out_dir=None):
    """允许通过命令行参数覆盖工作区路径。"""
    global BASE, OUT, DATA_PKL
    if work_base:
        BASE = work_base
    if out_dir:
        OUT = out_dir
    else:
        OUT = os.path.join(BASE, "output")
    DATA_PKL = os.path.join(OUT, "market_data.pkl")
    os.makedirs(OUT, exist_ok=True)
    return BASE, OUT


def parse_cli(default_base=None):
    """解析命令行：python xxx.py [工作区路径] [输出目录]"""
    global BASE, OUT
    if len(sys.argv) > 1 and sys.argv[1] not in ("", "-"):
        setup_paths(sys.argv[1])
    else:
        setup_paths(default_base or BASE)
    if len(sys.argv) > 2:
        setup_paths(BASE, sys.argv[2])
    return BASE, OUT


# ---------- 中文字体（matplotlib 3.11） ----------
def setup_fonts():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as font_manager
    fm = font_manager.fontManager
    for fp in [r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf",
               r"C:\Windows\Fonts\Deng.ttf"]:
        if os.path.exists(fp):
            try:
                fm.addfont(fp)
            except Exception:
                pass
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DengXian", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    return plt


# ---------- 同花顺导出文件解析 ----------
def load_ths(path):
    """同花顺导出的 .xls 是 GBK + Tab 分隔的「假 xls」。"""
    for enc in ["gbk", "gb18030", "utf-8"]:
        try:
            df = pd.read_csv(path, sep="\t", encoding=enc, dtype=str)
            df.columns = [str(c).strip() for c in df.columns]
            return df
        except Exception:
            continue
    raise ValueError(f"无法解析 {path}")


def clean_codes(df):
    """证券代码补前导零。"""
    df = df.copy()
    df["证券代码"] = df["证券代码"].astype(str).str.zfill(6)
    return df


# ---------- 行情获取（东方财富优先，新浪回退，带重试） ----------
def get_stock(symbol, start, end, tries=3):
    """个股行情。symbol: 6位代码。返回 (df, 来源)。已做前复权(qfq)+拆股检测。"""
    import akshare as ak
    sh = "sh" + symbol if symbol.startswith("6") else "sz" + symbol
    for _ in range(tries):
        try:
            df = ak.stock_zh_a_hist(symbol=symbol, period="daily",
                                    start_date=start, end_date=end, adjust="qfq")
            df = df.rename(columns={"日期": "date", "开盘": "open", "收盘": "close",
                                    "最高": "high", "最低": "low",
                                    "成交量": "volume", "成交额": "amount"})
            df = adjust_splits(df)
            return df[["date", "open", "high", "low", "close", "volume", "amount"]], "东方财富"
        except Exception:
            try:
                df = ak.stock_zh_a_daily(symbol=sh, start_date=start,
                                         end_date=end, adjust="qfq")
                df = adjust_splits(df)
                return df[["date", "open", "high", "low", "close", "volume", "amount"]], "新浪"
            except Exception:
                time.sleep(1)
    return None, "FAILED"


def get_etf(symbol, start, end, tries=3):
    """ETF 行情：新浪 fund_etf_hist_sina（稳定，未复权→自动拆股前复权），东方财富 fund_etf_hist_em 回退。"""
    import akshare as ak
    sh = ("sh" if symbol.startswith("5") else "sz") + symbol
    s_norm = _norm_date(start, "1900-01-01")   # YYYY-MM-DD 用于新浪字符串比较
    s_em = start.replace("-", "") if start else None  # YYYYMMDD 用于东方财富
    e_em = end.replace("-", "") if end else None
    for _ in range(tries):
        try:
            df = ak.fund_etf_hist_sina(symbol=sh)
            df = df.rename(columns={"date": "date", "open": "open", "high": "high",
                                    "low": "low", "close": "close",
                                    "volume": "volume", "amount": "amount"})
            df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
            df = df[df["date"] >= s_norm]
            df = df.sort_values("date").reset_index(drop=True)
            df = adjust_splits(df)  # 新浪未复权：拆分/送转前复权
            return df[["date", "open", "high", "low", "close", "volume", "amount"]], "新浪ETF"
        except Exception:
            try:
                df = ak.fund_etf_hist_em(symbol=symbol, period="daily",
                                         start_date=s_em, end_date=e_em, adjust="qfq")
                df = df.rename(columns={"日期": "date", "开盘": "open", "收盘": "close",
                                        "最高": "high", "最低": "low",
                                        "成交量": "volume", "成交额": "amount"})
                df = adjust_splits(df)
                return df[["date", "open", "high", "low", "close", "volume", "amount"]], "东方财富ETF"
            except Exception:
                time.sleep(1)
    return None, "FAILED"


def adjust_splits(df, drop_threshold=-25.0):
    """检测除权/拆分（送转、基金份额拆分）造成的价格跳变，对跳变前价格做前复权。

    适用：未复权数据（如新浪 fund_etf_hist_sina，无 adjust 参数）。
    跳变判定：单日收盘跌幅 < drop_threshold（默认 -25%，排除主板/创业板/科创板的
    正常涨跌停 -10%/-20%）。对每个跳变点 idx（从前往后，累计复权）：
      ratio = close[idx] / close[idx-1]（<1 表示拆细，如 1拆3 → ratio≈1/3）
      将 idx 之前所有 open/high/low/close 乘以 ratio，使历史价格与现价连续。
    已复权数据（qfq/hfq）不会有跳变，函数自动无操作。
    """
    df = df.copy().reset_index(drop=True)
    close = df["close"].astype(float)
    ret = close.pct_change() * 100
    jump = df.index[(ret < drop_threshold) & (df.index > 0)].tolist()
    if not jump:
        return df
    for idx in jump:  # 从前往后，ratio 用原始（未复权）close 计算
        r = close.iloc[idx] / close.iloc[idx - 1]
        if not (0 < r < 1):  # 只处理拆细；并股/异常跳过
            continue
        mask = df.index < idx
        for c in ("open", "high", "low", "close"):
            df.loc[mask, c] = df.loc[mask, c] * r
    return df


def fetch_market(targets, start, end, out_pkl=None):
    """批量获取行情并保存 pickle。targets: [(code, name, type)]  type=stock/etf。"""
    data = {}
    for code, name, typ in targets:
        fn = get_stock if typ == "stock" else get_etf
        df, src = fn(code, start, end)
        if df is not None and len(df) > 0:
            df = adjust_splits(df)  # 拆股/送转前复权（未复权源必需，否则前高/涨幅全错）
            df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
            data[code] = {"name": name, "type": typ, "source": src, "df": df}
            print(f"[OK] {code} {name} rows={len(df)} src={src}")
        else:
            print(f"[FAIL] {code} {name}")
        time.sleep(0.3)
    if out_pkl:
        with open(out_pkl, "wb") as f:
            pickle.dump(data, f)
        print(f"[OK] 行情已保存: {out_pkl}（{len(data)} 只）")
    return data


# ---------- 美股/港股行情（新浪源，稳定；用于中美联动策略第6条） ----------
def _norm_date(d, default):
    """把 YYYYMMDD 规范为 YYYY-MM-DD；None 时返回 default。"""
    if not d:
        return default
    d = str(d).replace("-", "")
    if len(d) == 8:
        return f"{d[:4]}-{d[4:6]}-{d[6:]}"
    return str(d)


def get_us_stock(symbol, start=None, end=None):
    """美股日线（新浪）。symbol: 如 'AMAT'/'FRO'/'NVDA'。返回 (df, 来源)。"""
    import akshare as ak
    try:
        df = ak.stock_us_daily(symbol=symbol)
        df = df.rename(columns={"date": "date", "open": "open", "high": "high",
                                "low": "low", "close": "close",
                                "volume": "volume"})
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        s = _norm_date(start, "1900-01-01")
        e = _norm_date(end, "2100-12-31")
        df = df[(df["date"] >= s) & (df["date"] <= e)]
        df = df.sort_values("date").reset_index(drop=True)
        df["amount"] = np.nan
        return df[["date", "open", "high", "low", "close", "volume", "amount"]], "新浪美股"
    except Exception:
        return None, "FAILED"


def get_hk_stock(symbol, start=None, end=None):
    """港股日线（新浪）。symbol: 5位代码如 '00700'/'09988'。返回 (df, 来源)。"""
    import akshare as ak
    try:
        df = ak.stock_hk_daily(symbol=symbol)
        df = df.rename(columns={"date": "date", "open": "open", "high": "high",
                                "low": "low", "close": "close",
                                "volume": "volume", "amount": "amount"})
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        s = _norm_date(start, "1900-01-01")
        e = _norm_date(end, "2100-12-31")
        df = df[(df["date"] >= s) & (df["date"] <= e)]
        df = df.sort_values("date").reset_index(drop=True)
        return df[["date", "open", "high", "low", "close", "volume", "amount"]], "新浪港股"
    except Exception:
        return None, "FAILED"


def fetch_global(targets, start=None, end=None, out_pkl=None):
    """批量获取美股/港股行情。targets: [(code, name, market)]  market=us/hk。"""
    data = {}
    for code, name, market in targets:
        fn = get_us_stock if market == "us" else get_hk_stock
        df, src = fn(code, start, end)
        if df is not None and len(df) > 0:
            data[code] = {"name": name, "type": market, "source": src, "df": df}
            print(f"[OK] {code} {name} rows={len(df)} src={src}")
        else:
            print(f"[FAIL] {code} {name}")
        time.sleep(0.3)
    if out_pkl:
        with open(out_pkl, "wb") as f:
            pickle.dump(data, f)
        print(f"[OK] 全球行情已保存: {out_pkl}（{len(data)} 只）")
    return data


def load_market(pkl_path=None):
    with open(pkl_path or DATA_PKL, "rb") as f:
        return pickle.load(f)


# ---------- 技术指标 ----------
def compute_indicators(df):
    """MA5/10/20、MACD(12,26,9)、RSI(14)、KDJ(9,3,3)、BOLL(20,2)。"""
    out = df.copy()
    close, high, low = out["close"], out["high"], out["low"]
    out["MA5"] = close.rolling(5).mean()
    out["MA10"] = close.rolling(10).mean()
    out["MA20"] = close.rolling(20).mean()
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    out["DIF"] = ema12 - ema26
    out["DEA"] = out["DIF"].ewm(span=9, adjust=False).mean()
    out["MACD"] = (out["DIF"] - out["DEA"]) * 2
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    out["RSI"] = 100 - 100 / (1 + rs)
    low9 = low.rolling(9).min()
    high9 = high.rolling(9).max()
    rsv = (close - low9) / (high9 - low9).replace(0, np.nan) * 100
    out["K"] = rsv.ewm(com=2, adjust=False).mean()
    out["D"] = out["K"].ewm(com=2, adjust=False).mean()
    out["J"] = 3 * out["K"] - 2 * out["D"]
    out["BOLL_MID"] = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    out["BOLL_UP"] = out["BOLL_MID"] + 2 * std20
    out["BOLL_LOW"] = out["BOLL_MID"] - 2 * std20
    return out


def trend_comment(s):
    """根据指标摘要生成中文技术面结论。"""
    parts = []
    parts.append("站上20日均线，中期趋势偏多" if s["close"] > s["MA20"] else "跌破20日均线，中期趋势偏弱")
    if s["DIF"] > s["DEA"] and s["MACD"] > 0:
        parts.append("MACD金叉且红柱，动能向上")
    elif s["DIF"] < s["DEA"] and s["MACD"] < 0:
        parts.append("MACD死叉且绿柱，动能向下")
    elif s["DIF"] > s["DEA"]:
        parts.append("MACD金叉但柱体转弱")
    else:
        parts.append("MACD死叉但柱体收敛")
    if s["RSI"] >= 70:
        parts.append(f"RSI={s['RSI']} 超买，注意回调")
    elif s["RSI"] <= 30:
        parts.append(f"RSI={s['RSI']} 超卖，或有反弹")
    else:
        parts.append(f"RSI={s['RSI']} 中性区间")
    if s["J"] > 100:
        parts.append("KDJ-J 超买")
    elif s["J"] < 0:
        parts.append("KDJ-J 超卖")
    if s["pos_60"] >= 80:
        parts.append(f"位于60日区间高位({s['pos_60']}%)")
    elif s["pos_60"] <= 20:
        parts.append(f"位于60日区间低位({s['pos_60']}%)")
    if s.get("support"):
        parts.append(f"支撑位≈{s['support']}")
    if s.get("resistance"):
        parts.append(f"压力位≈{s['resistance']}")
    if s.get("breakout"):
        parts.append(s["breakout"])
    return "；".join(parts)


def support_resistance(df, lookback=60):
    """计算关键支撑/压力位（结合近60日高低点 + 20日均线，供用户第1/3条策略使用）。
    返回 (support, resistance, 说明)。"""
    tail = df.tail(lookback)
    hi = float(tail["high"].max())
    lo = float(tail["low"].min())
    ma20 = float(df["close"].tail(20).mean())
    close = float(df["close"].iloc[-1])
    support = max(lo, ma20 * 0.97)
    resistance = min(hi, max(close, ma20 * 1.03))
    return round(support, 3), round(resistance, 3)


def volume_breakout(df, vol_ratio=1.5, lookback=20):
    """检测是否放量突破：当日收盘 > 20日最高(压力位) 且 量 > 20日均量*vol_ratio。
    供用户第1条策略「放量突破关键压力位→2~3成仓尝试」。返回 (是否, 说明)。"""
    if len(df) < 21:
        return False, ""
    last = df.iloc[-1]
    prev = df.iloc[-21:-1]
    hi20 = prev["high"].max()
    vol20 = prev["volume"].mean()
    if last["close"] > hi20 and last["volume"] > vol20 * vol_ratio:
        return True, f"放量突破20日高点{hi20:.3f}（量{last['volume']/vol20:.1f}倍均量），符合放量突破压力位信号"
    return False, ""

