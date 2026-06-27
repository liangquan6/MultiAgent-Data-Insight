"""W3.1 对照实验: SchemaMemory 压缩 vs 朴素 dump 的 token 开销对比。

宽表(50 列)才能体现压缩价值: verbose_schema 把 head()+dtypes()+describe() 全 dump,
列数越多 prompt 越胀; compact_schema 只留列名+类型+采样值, 常数小得多。

设计要点 (保证两组可比):
  - 同一份数据复制成两个不同名副本, 让 ConversationMemory 各走各的 jsonl,
    避免第二轮读到第一轮的续聊摘要, 污染 prompt。
  - 每组跑前清 results/plots 旧图, n_plots 只反映本轮。
  - schema_cap 调大到 20000, 让 verbose 的宽表 schema 完整注入, 不被默认 1500 截断。

跑 verbose / compact 两组, 算 token 节省百分比, 写 results/token_compare.json。

用法:
  python -m experiments.token_compare
"""
import asyncio
import glob
import json
import os
import shutil

import numpy as np
import pandas as pd

from main import main as run_analysis

N_COLS = 50       # 数值列数, 宽表才看得出压缩差异
N_ROWS = 200
N_GROUPS = 4
SCHEMA_CAP = 20000   # 放开截断, 让 verbose schema 完整进来
OUT_JSON = "results/token_compare.json"
PLOT_DIR = "results/plots"


def make_wide_dataset(path: str) -> None:
    """生成宽表: N_COLS 列数值 + 1 列类别, 存到 path。已存在则跳过。"""
    if os.path.exists(path):
        print(f"[数据] {path} 已存在, 跳过生成")
        return
    rng = np.random.default_rng(42)
    cols = {f"f{i}": rng.normal(loc=i * 0.1, scale=1.0, size=N_ROWS)
            for i in range(N_COLS)}
    cols["group"] = rng.choice(["A", "B", "C", "D"], size=N_ROWS)
    df = pd.DataFrame(cols)
    df.to_csv(path, index=False)
    print(f"[数据] 已生成 {path}, shape={df.shape}")


def _clear_plots() -> None:
    """清空 results/plots 下的旧图, 防止上一轮的图污染本轮 n_plots 统计。"""
    os.makedirs(PLOT_DIR, exist_ok=True)
    for f in glob.glob(os.path.join(PLOT_DIR, "plot_*.png")):
        os.remove(f)


def _reset_session(csv_path: str) -> None:
    """跑前清图 + 删同名 jsonl, 保证两组都从空会话开始。"""
    _clear_plots()
    jsonl = f"results/{os.path.basename(csv_path)}.jsonl"
    if os.path.exists(jsonl):
        os.remove(jsonl)


async def _run(schema_mode: str, csv_path: str) -> dict:
    """跑一次分析, 返回 main() 的 stats dict。"""
    _reset_session(csv_path)
    bar = "=" * 60
    print(f"\n{bar}\n[实验组] schema_mode={schema_mode}, data={csv_path}\n{bar}",
          flush=True)
    return await run_analysis(csv_path, mode="selector",
                              schema_mode=schema_mode, schema_cap=SCHEMA_CAP)


def _summarize(verbose_stats: dict, compact_stats: dict) -> dict:
    """算节省比例 + 给一句结论。"""
    v_total = verbose_stats["total_tokens"]
    c_total = compact_stats["total_tokens"]
    savings_pct = round((v_total - c_total) / v_total * 100, 1) if v_total else 0.0
    if c_total < v_total:
        conclusion = (f"compact 比 verbose 省 {savings_pct}% token "
                      f"({v_total} -> {c_total}), SchemaMemory 压缩有效")
    else:
        conclusion = (f"compact 反而更费 token ({v_total} -> {c_total}, "
                      f"{savings_pct}%), 可能列数不够或 LLM 调用波动, 需复跑")
    return {
        "dataset": f"wide_synth ({N_COLS} num cols + 1 category, {N_ROWS} rows)",
        "mode": "selector",
        "schema_cap": SCHEMA_CAP,
        "verbose": verbose_stats,
        "compact": compact_stats,
        "savings_pct": savings_pct,
        "conclusion": conclusion,
    }


async def run_experiment() -> dict:
    """跑 verbose / compact 两组, 落盘结果。"""
    os.makedirs("results", exist_ok=True)

    # 先造一份规范数据, 再复制成两个不同名副本 (各自走独立 jsonl, 不串味)
    base_csv = "data/wide_synth.csv"
    verbose_csv = "data/wide_synth_v.csv"
    compact_csv = "data/wide_synth_c.csv"
    make_wide_dataset(base_csv)
    shutil.copy(base_csv, verbose_csv)
    shutil.copy(base_csv, compact_csv)

    verbose_stats = await _run("verbose", verbose_csv)
    compact_stats = await _run("compact", compact_csv)

    result = _summarize(verbose_stats, compact_stats)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n=== 实验结果已写入 {OUT_JSON} ===")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    asyncio.run(run_experiment())
