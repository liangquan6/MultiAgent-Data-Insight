"""批量评测入口: N 个数据集 × M 种协作模式, 汇总成对比表 (W4 核心)。

跑法:
  python -m eval.benchmark              # 默认 4 数据集 × 3 模式 = 12 次
  python -m eval.benchmark --modes selector   # 只跑某模式

输出 results/benchmark.json: 每行含 data/mode/rounds/loops/tokens/seconds/
n_plots/completed/first_pass/tool_misuse, 供 README 对比表填数。
"""
import argparse
import asyncio
import glob
import json
import os
import time

import pandas as pd

from memory.schema_memory import SchemaMemory
from teams.team_factory import build_team
from eval.metrics import (
    completion_rate, first_pass_rate, loop_detection,
    token_efficiency, tool_misuse_rate, extract_tool_calls, summary,
)

PLOT_DIR = "results/plots"
TASK_TEMPLATE = (
    "数据集路径: {path}\n"
    "Schema 摘要: {schema}\n"
    "任务: 请四位协作完成数据分析, 最终由 Reporter 产出 markdown 报告。\n"
    "Reviewer 认为可以收尾时回复 PASS。"
)


def _clear_plots() -> None:
    """清旧图, 让本轮 n_plots 只反映自己。

    Windows 上偶尔有文件被锁 (上次进程句柄没释放 / 资源管理器占用),
    os.remove 会抛 PermissionError。这里逐个 try, 失败的跳过——
    n_plots 可能因此略偏大, 但不至于让整次跑批崩溃。
    """
    os.makedirs(PLOT_DIR, exist_ok=True)
    for f in glob.glob(os.path.join(PLOT_DIR, "*.png")):
        try:
            os.remove(f)
        except (PermissionError, OSError):
            pass


def _build_task(data_path: str) -> str:
    """复用 main.py 的 schema 注入: compact schema + task 模板。"""
    df = pd.read_csv(data_path)
    schema = SchemaMemory(df).get()
    return TASK_TEMPLATE.format(path=data_path, schema=schema[:1500])


async def run_one(data_path: str, mode: str, task: str) -> dict:
    """跑一次, 采集全套指标。transport 固定 direct (W4 只比模式, 不混 MCP 变量)。"""
    _clear_plots()
    team = await build_team(mode, transport="direct")
    t0 = time.time()
    result = await team.run(task=task)
    elapsed = round(time.time() - t0, 1)

    msgs = []
    for m in result.messages:
        msgs.append({
            "source": getattr(m, "source", ""),
            "content": m.content if isinstance(m.content, str) else str(m.content),
            "usage": getattr(m, "models_usage", None),
        })

    # token 求和: 只有 LLM 推理的消息带 usage
    total_tokens = 0
    for m in msgs:
        u = m["usage"]
        if u is not None:
            total_tokens += u.prompt_tokens + u.completion_tokens

    # 完成判定: 末条是 Reporter 且含 markdown 标题 (#) 且非"等图"占位
    last_reporter = ""
    for m in reversed(msgs):
        if m["source"] == "Reporter":
            last_reporter = m["content"]
            break
    completed = bool(last_reporter and "#" in last_reporter
                     and "等图" not in last_reporter and len(last_reporter) > 100)

    # 工具误用: 从 Coder 消息提取工具调用, 算报错占比
    tool_calls = extract_tool_calls(msgs)
    misuse = tool_misuse_rate(tool_calls)

    # 统计全部 png (含 LLM 自写 savefig 的固定名如 plot_box_f0.png),
    # 不只数 plot_*.png, 否则漏算 Coder 直接 plt.savefig 的产出。
    n_plots = len(glob.glob(os.path.join(PLOT_DIR, "*.png")))

    return {
        "data": os.path.basename(data_path),
        "mode": mode,
        "rounds": len(msgs),
        "loops": loop_detection(msgs),
        "tokens": total_tokens,
        "token_per_round": token_efficiency(msgs, total_tokens),
        "seconds": elapsed,
        "n_plots": n_plots,
        "completed": completed,
        "first_pass": False,   # 占位, main() 里按模式聚合算
        "tool_misuse": misuse,
        "n_tool_calls": len(tool_calls),
    }


def _aggregate(rows: list[dict]) -> dict:
    """按模式聚合: 完成率 / 一次通过率 / 平均轮数 / 平均 token / 平均耗时 / 循环率 / 工具误用。

    跳过 error 行 (某次跑批失败时只放 {data,mode,error}, 没有完整指标)。
    """
    modes = sorted({r["mode"] for r in rows})
    agg = {}
    for mode in modes:
        grp = [r for r in rows if r["mode"] == mode and "error" not in r]
        n = len(grp)
        if n == 0:
            agg[mode] = {"completion_rate": 0, "note": "all runs failed"}
            continue
        # 一次通过率: completed 且没循环 (近似: Reviewer 没要求返工)
        first_pass = sum(1 for r in grp if r["completed"] and not r["loops"]) / n
        agg[mode] = {
            "completion_rate": round(sum(1 for r in grp if r["completed"]) / n, 3),
            "first_pass_rate": round(first_pass, 3),
            "loop_rate": round(sum(1 for r in grp if r["loops"]) / n, 3),
            "avg_rounds": round(sum(r["rounds"] for r in grp) / n, 1),
            "avg_tokens": round(sum(r["tokens"] for r in grp) / n, 0),
            "avg_seconds": round(sum(r["seconds"] for r in grp) / n, 1),
            "avg_tool_misuse": round(sum(r["tool_misuse"] for r in grp) / n, 3),
        }
    return agg


async def main(dataset_meta: str = "eval/datasets_meta.json", modes=None):
    modes = modes or ["round_robin", "selector", "llm_selector"]
    with open(dataset_meta, encoding="utf-8") as f:
        datasets = json.load(f)

    rows = []
    total = len(datasets) * len(modes)
    i = 0
    for d in datasets:
        task = _build_task(d["path"])
        for mode in modes:
            i += 1
            print(f"\n[{i}/{total}] {d['name']} × {mode} ...", flush=True)
            try:
                row = await run_one(d["path"], mode, task)
            except Exception as e:
                # 单次失败不中断整批 (某模式卡死也保住已跑数据)
                row = {"data": d["name"], "mode": mode, "error": f"{type(e).__name__}: {e}"}
                print(f"  !! 失败: {row['error']}", flush=True)
            rows.append(row)
            if "error" not in row:
                print(f"  rounds={row['rounds']} tokens={row['tokens']} "
                      f"plots={row['n_plots']} completed={row['completed']} "
                      f"loops={row['loops']} misuse={row['tool_misuse']} {row['seconds']}s",
                      flush=True)
            # 每跑完一条就落盘, 防 12 次跑批中途崩丢全部数据
            os.makedirs("results", exist_ok=True)
            with open("results/benchmark.json", "w", encoding="utf-8") as f:
                json.dump({"rows": rows, "aggregate": _aggregate(rows)},
                          f, ensure_ascii=False, indent=2)

    print("\n=== 按模式汇总 ===")
    print(summary(_aggregate(rows)))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--modes", nargs="+",
                   choices=["round_robin", "selector", "llm_selector"],
                   default=None, help="只跑指定模式; 默认三种都跑")
    args = p.parse_args()
    asyncio.run(main(modes=args.modes))
