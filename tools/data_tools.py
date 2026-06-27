"""数据分析工具集。

每个函数都是一个可被 Agent 通过 function calling 调用的工具。签名要清晰,
docstring 会被 AutoGen 转成 function schema 喂给模型, 不要乱写。
"""
import json
import os
import pandas as pd
from .code_sandbox import run_code


def load_csv(path: str) -> str:
    """加载 CSV 文件, 返回 shape 与前 5 行摘要。"""
    df = pd.read_csv(path)
    summary = {
        "shape": list(df.shape),
        "columns": list(df.columns),
        "dtypes": {c: str(t) for c, t in df.dtypes.items()},
        "head": df.head().to_dict(orient="records"),
    }
    return json.dumps(summary, ensure_ascii=False, default=str)


def profile_dataset(path: str) -> str:
    """产出数据集画像: 缺失率、唯一值数、数值列统计、可疑异常值。"""
    df = pd.read_csv(path)
    info = {
        "shape": list(df.shape),
        "missing_rate": (df.isna().mean().round(3).to_dict()),
        "nunique": df.nunique().to_dict(),
        "numeric_describe": df.describe().round(2).to_dict(),
    }
    return json.dumps(info, ensure_ascii=False, default=str)


# 默认图存这里; LLM 不传 save_dir 也兜得住 (os 在文件头已 import)
PLOT_DIR = os.path.join("results", "plots")

# 图片后缀: LLM 常误把"想要的文件名"塞进 save_dir (如 results/plots/sepal_scatter.png),
# 若不拦, os.makedirs 会把 sepal_scatter.png 当目录建, 真图存进 sepal_scatter.png/plot_xxx.png,
# 路径变成 xxx.png\plot_xxx.png, Reviewer 反复拦"非法路径"却改不掉 → 返工循环吃满消息预算。
# (W5 追踪到的真实 bug, 直接导致 W4 完成率低)
_IMG_SUFFIXES = (".png", ".jpg", ".jpeg", ".svg", ".pdf")


def _ensure_dir(save_dir: str) -> str:
    """确保 save_dir 是个目录, 返回目录路径。

    防 LLM 误传文件路径: 若 save_dir 以图片后缀结尾 (如 sepal_scatter.png),
    剥离后缀取其父目录, 而不是把 .png 当目录建 (否则产生 xxx.png/ 伪目录 +
    路径污染成 xxx.png\\plot_xxx.png, 触发 Reviewer 返工循环)。
    空串兜底回 PLOT_DIR。
    """
    if not save_dir:
        save_dir = PLOT_DIR
    low = save_dir.lower()
    if low.endswith(_IMG_SUFFIXES):
        # 剥掉文件名, 取所在目录 (results/plots/sepal_scatter.png → results/plots)
        save_dir = os.path.dirname(save_dir)
    if save_dir:
        os.makedirs(save_dir, exist_ok=True)
    return save_dir


def plot_distribution(path: str, column: str, save_dir: str = "") -> str:
    """画某列分布直方图, 返回图片路径。

    save_dir 可省略, 默认存 results/plots/。
    """
    save_dir = _ensure_dir(save_dir or PLOT_DIR)
    code = f"df['{column}'].plot.hist(title='{column} 次数分布')"
    df = pd.read_csv(path)
    res = run_code(code, df=df, save_dir=save_dir)
    out = res.get("plot_path") or res.get("error", "plot failed")
    # 带工具名+参数, 让 Reviewer 看得见: 调的是 plot_distribution 画哪个列的直方图
    return f"[plot_distribution(column={column})] {out}"


def correlation_heatmap(path: str, save_dir: str = "") -> str:
    """画数值列相关性热力图, 返回图片路径。"""
    save_dir = _ensure_dir(save_dir or PLOT_DIR)
    code = (
        "fig, ax = plt.subplots(figsize=(8,6))\n"
        "cax = ax.imshow(df.corr(numeric_only=True), cmap='coolwarm', vmin=-1, vmax=1)\n"
        "ax.set_xticks(range(len(df.columns))); ax.set_xticklabels(df.columns, rotation=45, ha='right')\n"
        "ax.set_yticks(range(len(df.columns))); ax.set_yticklabels(df.columns)\n"
        "fig.colorbar(cax); plt.tight_layout()\n"
    )
    df = pd.read_csv(path)
    res = run_code(code, df=df, save_dir=save_dir)
    out = res.get("plot_path") or res.get("error", "plot failed")
    return f"[correlation_heatmap()] {out}"


def scatter_plot(path: str, x: str, y: str, hue: str = "", save_dir: str = "") -> str:
    """画散点图 (x vs y, 可按 hue 列着色), 返回图片路径。

    适合观察两个数值列是否随类别分开, 例如: scatter_plot(path, x='sepal_len', y='petal_len', hue='species')
    """
    save_dir = _ensure_dir(save_dir or PLOT_DIR)
    # 显式拼代码, 不用 f-string 嵌套 (之前 set_title 括号没闭合, 沙箱语法报错)
    title = f"{x} vs {y}" + (f" (by {hue})" if hue else "")
    if hue:
        scatter_line = f"ax.scatter(df['{x}'], df['{y}'], c=df['{hue}'].astype('category').cat.codes, cmap='viridis')"
    else:
        scatter_line = f"ax.scatter(df['{x}'], df['{y}'])"
    code = (
        "fig, ax = plt.subplots(figsize=(7,5))\n"
        f"{scatter_line}\n"
        f"ax.set_xlabel('{x}'); ax.set_ylabel('{y}')\n"
        f"ax.set_title('{title}')\n"
        "plt.tight_layout()\n"
    )
    df = pd.read_csv(path)
    res = run_code(code, df=df, save_dir=save_dir)
    out = res.get("plot_path") or res.get("error", "plot failed")
    return f"[scatter_plot(x={x}, y={y}, hue={hue})] {out}"


def box_plot(path: str, groupby: str, column: str, save_dir: str = "") -> str:
    """按 groupby 列分组, 画 column 列的箱线图, 返回图片路径。

    适合比较不同类别在某数值列上的分布差异,
    例如: box_plot(path, groupby='species', column='petal_len')
    """
    save_dir = _ensure_dir(save_dir or PLOT_DIR)
    # column/groupby 是参数值, 要直接拼进代码字符串, 不能当变量名 (沙箱命名空间里没有它们)
    code = (
        "fig, ax = plt.subplots(figsize=(7,5))\n"
        f"groups = [g['{column}'].values for _, g in df.groupby('{groupby}')]\n"
        f"labels = [str(name) for name, _ in df.groupby('{groupby}')]\n"
        "ax.boxplot(groups, labels=labels)\n"
        f"ax.set_xlabel('{groupby}'); ax.set_ylabel('{column}')\n"
        f"ax.set_title('{column} by {groupby}')\n"
        "plt.tight_layout()\n"
    )
    df = pd.read_csv(path)
    res = run_code(code, df=df, save_dir=save_dir)
    out = res.get("plot_path") or res.get("error", "plot failed")
    return f"[box_plot(groupby={groupby}, column={column})] {out}"


def groupby_aggregate(path: str, groupby: str, columns: list[str], agg_funcs: list[str]) -> str:
    """按 groupby 列分组, 对 columns 各列做 agg_funcs 指定的聚合, 返回 JSON 结果。

    agg_funcs 可选: mean / std / min / max / median / count
    示例: groupby_aggregate(path, groupby='species', columns=['petal_len','petal_wid'], agg_funcs=['mean','std'])
    """
    df = pd.read_csv(path)
    try:
        # 安全校验: groupby 字段必须存在、columns 必须存在且都是能聚合的
        if groupby not in df.columns:
            return f"[groupby_aggregate] 错误: 列 '{groupby}' 不存在于数据集"
        for c in columns:
            if c not in df.columns:
                return f"[groupby_aggregate] 错误: 列 '{c}' 不存在"
        # 受控聚合函数白名单
        allowed = {"mean", "std", "min", "max", "median", "count"}
        bad = set(agg_funcs) - allowed
        if bad:
            return f"[groupby_aggregate] 错误: 不支持的聚合 {bad}, 仅允许 {allowed}"
        result = df.groupby(groupby)[columns].agg(agg_funcs).round(3)
        return f"[groupby_aggregate(groupby={groupby}, cols={columns}, aggs={agg_funcs})]\n{result.to_json()}"
    except Exception as e:
        return f"[groupby_aggregate] 错误: {type(e).__name__}: {e}"


def detect_outliers(path: str, column: str) -> str:
    """用 IQR 法检测某列异常值, 返回异常数量与示例。"""
    df = pd.read_csv(path)
    s = df[column]
    if not pd.api.types.is_numeric_dtype(s):
        return f"{column} 非数值列, 跳过"
    q1, q3 = s.quantile(0.25), s.quantile(0.75)
    iqr = q3 - q1
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    out = df[(s < lo) | (s > hi)]
    return json.dumps({"n_outliers": len(out), "bounds": [round(lo, 2), round(hi, 2)],
                       "sample": out.head(3).to_dict(orient="records")}, ensure_ascii=False, default=str)


# TODO(P1): 加 MCP 协议暴露 plot_distribution, 体验一遍 MCP 标准工具调用 -> 简历"MCP"坐实