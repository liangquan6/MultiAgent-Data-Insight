"""生成评测用的合成数据集 (W4 benchmark 输入 + W5 业务演示)。

为什么不直接下 Kaggle: 外部下载慢/不稳, 且评测关心的是 Agent 协作行为
(循环/返工/工具误用), 数据是否"真实"不影响这些指标的可靠性。合成集能
精确控制结构 (宽表/时序/混合类型), 覆盖 Agent 可能踩的不同坑。

已有 (W3.1 生成): iris.csv (窄表分类), wide_synth.csv (宽表)。
本脚本补: trends.csv (时序), mixed.csv (混合类型 + 缺失),
changsha_housing.csv (W5 业务演示: 长沙二手房, 混合类型 + 刻意缺失)。
"""
import os

import numpy as np
import pandas as pd


def make_trends(path: str = "data/trends.csv") -> None:
    """时序数据: 日期 + 上升趋势 + 周期 + 噪声。测 Agent 对时序/周期的识别。"""
    if os.path.exists(path):
        print(f"[数据] {path} 已存在, 跳过")
        return
    rng = np.random.default_rng(7)
    n = 200
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    trend = np.linspace(50, 120, n)                       # 上升趋势
    weekly = 8 * np.sin(np.arange(n) * 2 * np.pi / 7)     # 周周期
    noise = rng.normal(0, 3, n)
    df = pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "value": (trend + weekly + noise).round(2),
        "visits": rng.poisson(lam=200, size=n),
        "channel": rng.choice(["search", "direct", "ads"], size=n),
    })
    df.to_csv(path, index=False)
    print(f"[数据] 已生成 {path}, shape={df.shape}")


def make_mixed(path: str = "data/mixed.csv") -> None:
    """混合类型: 数值 + 类别 + 日期 + 刻意缺失。测 Agent 对脏数据的处理。"""
    if os.path.exists(path):
        print(f"[数据] {path} 已存在, 跳过")
        return
    rng = np.random.default_rng(11)
    n = 150
    df = pd.DataFrame({
        "id": range(1, n + 1),
        "age": rng.integers(18, 70, n).astype(float),
        "income": rng.normal(8000, 2000, n).round(0),
        "city": rng.choice(["北京", "上海", "广州", "深圳", "成都"], n),
        "joined": pd.date_range("2022-01-01", periods=n, freq="3D").strftime("%Y-%m-%d"),
        "score": rng.uniform(40, 100, n).round(1),
    })
    # 刻意挖缺失: income 随机缺 8%, score 缺 5%
    miss_income = rng.random(n) < 0.08
    miss_score = rng.random(n) < 0.05
    df.loc[miss_income, "income"] = np.nan
    df.loc[miss_score, "score"] = np.nan
    df.to_csv(path, index=False)
    print(f"[数据] 已生成 {path}, shape={df.shape}, 缺失: income={miss_income.sum()} score={miss_score.sum()}")


def make_changsha_housing(path: str = "data/changsha_housing.csv") -> None:
    """长沙二手房 (W5 业务演示数据)。

    结构贴近真实挂牌: 区域/面积/总价/单价/户型/楼层/朝向/装修/建成年代/
    关注人数/带看次数。价格按"区域档位 × 面积 × 房龄 × 装修"叠加噪声生成,
    单价与面积负相关 (大户型单价略低), 房龄越新单价越高。
    刻意挖缺失 (朝向/装修/带看) 模拟真实挂牌的字段不全。
    Agent 需自行派生房龄、单价=总价/面积等字段, 考察脏数据处理 + 特征工程。
    """
    if os.path.exists(path):
        print(f"[数据] {path} 已存在, 跳过")
        return
    rng = np.random.default_rng(2024)
    n = 300
    # 区域档位 (元/㎡ 基准): 中心高, 远郊低
    districts = {
        "芙蓉区": 13500, "天心区": 12800, "岳麓区": 12200,
        "开福区": 11500, "雨花区": 11200, "望城区": 8500, "长沙县": 7800,
    }
    dist_names = list(districts)
    dist_base = np.array([districts[d] for d in dist_names])
    dist_idx = rng.integers(0, len(dist_names), n)
    area = rng.normal(105, 35, n).clip(40, 260).round(1)            # 面积 ㎡
    # 大户型单价略低: 每 +50㎡ 单价 -6%
    size_factor = 1 - (area - 100) / 50 * 0.06
    built_year = rng.integers(2002, 2024, n)                        # 建成年代
    age_factor = 1 - (2024 - built_year) * 0.012                    # 每年 -1.2%
    reno = rng.choice(["精装", "简装", "毛坯"], n, p=[0.45, 0.40, 0.15])
    reno_factor = np.where(reno == "精装", 1.05, np.where(reno == "简装", 1.0, 0.93))
    orient = rng.choice(["南", "东南", "东", "北", "西南", "西"], n)
    unit_price = (dist_base[dist_idx] * size_factor * age_factor * reno_factor)
    unit_price *= rng.normal(1.0, 0.08, n)                          # 个盘噪声
    unit_price = unit_price.round(0)
    total_price = (unit_price * area / 10000).round(1)              # 总价 万元
    layouts = rng.choice(["1室1厅", "2室1厅", "2室2厅", "3室2厅", "4室2厅", "3室1厅"],
                         n, p=[0.08, 0.30, 0.22, 0.25, 0.08, 0.07])
    floor = rng.integers(1, 33, n)
    total_floor = np.where(floor > 6, rng.integers(18, 34, n), rng.integers(6, 12, n))
    fav = rng.poisson(40, n)                                        # 关注人数
    view = rng.poisson(8, n)                                        # 带看次数
    df = pd.DataFrame({
        "小区": [f"小区{rng.integers(1, 80)}" for _ in range(n)],
        "区域": [dist_names[i] for i in dist_idx],
        "面积": area,
        "总价": total_price,
        "单价": unit_price,
        "户型": layouts,
        "楼层": floor,
        "总楼层": total_floor,
        "朝向": orient,
        "装修": reno,
        "建成年代": built_year,
        "关注人数": fav,
        "带看次数": view,
    })
    # 刻意挖缺失: 朝向缺 6%, 装修缺 4%, 带看次数缺 10% (挂牌太久没人看)
    df.loc[rng.random(n) < 0.06, "朝向"] = np.nan
    df.loc[rng.random(n) < 0.04, "装修"] = np.nan
    df.loc[rng.random(n) < 0.10, "带看次数"] = np.nan
    df.to_csv(path, index=False)
    print(f"[数据] 已生成 {path}, shape={df.shape}")


if __name__ == "__main__":
    make_trends()
    make_mixed()
    make_changsha_housing()
