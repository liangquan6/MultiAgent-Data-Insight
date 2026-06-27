"""安全代码沙箱。

策略 (比单纯 RestrictedPython 更可控, 也更适合讲面试):

1. 静态黑名单: 编译前用 AST 扫一遍, 禁掉 ImportError / open 文件 / exec / eval /
   __import__ / subprocess / os.system 等 7 类高危调用, 命中直接拒收。
2. 白名单注入: pandas / numpy / matplotlib / plt 已经作为对象注入到运行命名空间,
   代码里写 `import matplotlib.pyplot as plt` 这种语句会在编译前被剥掉——
   模块对象已经在那, 不需要真的执行 import, 也杜绝了 RestrictedPython 的 __import__ guard 触发链。
3. 受控执行: 用 exec 在隔离的 globals 里跑, stdout 重定向到 buffer。
4. 进程级超时 (W3.3): exec 在子进程里跑, 主进程 join(timeout) 兜底——
   LLM 写出 while True 死循环 / 跑不完的大计算时, 超时直接 terminate 子进程,
   返回 "[sandbox timeout] 执行超过 Ns 被终止", Agent 能拿到错误继续走, 不会卡死整个 run。
   (Windows 无 signal.alarm, 必须用 multiprocessing 进程隔离; Linux 上同理更稳。)

这套组合的优势面试能讲: 静态 + 运行时双保险, 比 RestrictedPython 的 guard 链更直白
( RestrictedPython 那一套 _getitem_/_getiter_/_print_/_write_ 链式 guard 调试坑很多)。

已知未做 (诚实边界): 内存限制 (OOM, 如 np.zeros((10**9,10**9))) 在 Windows 上无 rlimit,
  仅靠超时间接兜底 (OOM 通常先拖慢再超时); 真生产建议上容器 + cgroups。
"""
import ast
import io
import os
import re as _re
import tempfile
import time
import contextlib
import multiprocessing as _mp

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
# 修 matplotlib 中文方框: 默认 DejaVu Sans 不含 CJK, 指定 Windows 自带 SimHei
matplotlib.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False
import matplotlib.pyplot as plt


# 已注入到运行命名空间的模块对象, 代码里 import 这几个名字会被静态剥掉
INJECTED_NAMES = {"pandas", "numpy", "matplotlib", "plt", "pd", "np"}

# 高危函数名: 出现在 Call 节点里直接拒
DANGEROUS_CALLS = {
    "open", "exec", "eval", "compile", "__import__",
    "system", "popen", "spawn", "fork", "kill", "remove", "unlink",
    "rmdir", "rename", "chmod", "chown",
}
# 违禁 import 顶层模块名
DANGEROUS_IMPORTS = {
    "os", "sys", "subprocess", "socket", "shutil", "pathlib",
    "ctypes", "multiprocessing", "threading", "asyncio",
    "pickle", "marshal", "builtins", "runpy",
}

# 把代码里对白名单模块的 import 行剥掉 (因为对象已注入), 用正则足够, 不上 AST
_IMPORT_STRIP = _re.compile(
    r'^[ \t]*(?:import[ \t]+|from[ \t]+)(?:pandas|numpy|matplotlib|plt|pd|np)'
    r'(?:\.[\w.]+)?[ \t]*(?:import[ \t\w,]+)?(?:[ \t]+as[ \t]+\w+)?[ \t]*$',
    _re.MULTILINE,
)


def _static_check(code: str) -> str | None:
    """AST 扫一遍, 命中高危调用直接返回理由, 否则返回 None (放行)。"""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return f"syntax error: {e}"
    for node in ast.walk(tree):
        # 检查 Import / ImportFrom 顶层模块
        if isinstance(node, ast.Import):
            for n in node.names:
                root = n.name.split(".")[0]
                if root in DANGEROUS_IMPORTS:
                    return f"禁止 import: {n.name}"
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] in DANGEROUS_IMPORTS:
                return f"禁止 from import: {node.module}"
        # 检查不可控的 dangerously 调用: 直接 call 名为危险函数
        if isinstance(node, ast.Call):
            f = node.func
            name = None
            if isinstance(f, ast.Name):
                name = f.id
            elif isinstance(f, ast.Attribute):
                name = f.attr
            if name in DANGEROUS_CALLS:
                return f"禁止调用: {name}"
    return None


# 运行时全局名字: 沙箱里实际可用的一组
def _build_namespace(df, save_dir: str) -> dict:
    ns = {
        # 数据/可视化
        "pd": pd, "np": np, "plt": plt,
        "pandas": pd, "numpy": np, "matplotlib": plt,
        # 安全内置
        "print": print, "len": len, "range": range, "enumerate": enumerate,
        "zip": zip, "map": map, "list": list, "dict": dict, "set": set,
        "tuple": tuple, "sorted": sorted, "sum": sum, "min": min, "max": max,
        "abs": abs, "round": round, "str": str, "int": int, "float": float,
        "bool": bool, "type": type, "isinstance": isinstance,
        "ValueError": ValueError, "TypeError": TypeError, "KeyError": KeyError,
        "IndexError": IndexError, "Exception": Exception,
        # 常量
        "__name__": "sandbox", "SAVE_DIR": save_dir,
    }
    if df is not None:
        ns["df"] = df
    return ns


# 子进程执行的默认超时 (秒)。LLM 写死循环/大计算时兜底, 避免卡死整个 run。
# 调用方可经 run_code(..., timeout=) 覆盖。
_DEFAULT_TIMEOUT = 30


def _exec_child(code_str: str, df, save_dir: str, queue: "_mp.Queue") -> None:
    """子进程入口: 在隔离命名空间里 exec, 把 stdout/plot_path/error 回传主进程。

    放子进程跑的原因: LLM 可能写出 while True 死循环或吃满内存的代码,
    主进程靠 join(timeout) 兜底, 超时就 terminate, 不让卡死波及整个 Agent run。
    传源码字符串而非 compiled 对象: Windows spawn 模式要 pickle 传参, code object 不可 pickle,
    所以编译挪到子进程内做。df 走 pickle 传过来 (DataFrame 可 pickle)。
    """
    plt.close("all")
    try:
        compiled = compile(code_str, "<agent_code>", "exec")
    except SyntaxError as e:
        queue.put({"ok": False, "error": f"syntax: {e}", "stdout": ""})
        return
    ns = _build_namespace(df, save_dir)
    buf = io.StringIO()
    plot_path = None
    try:
        with contextlib.redirect_stdout(buf):
            exec(compiled, ns)
        if plt.get_fignums():
            # 用毫秒时间戳保证唯一, 否则多张图全覆盖成 plot.png, Reporter 拿不到 >=2 张图就拒写报告
            fname = f"plot_{int(time.time()*1000)}.png"
            plot_path = os.path.join(save_dir, fname)
            plt.savefig(plot_path, dpi=100, bbox_inches="tight")
        queue.put({"ok": True, "stdout": buf.getvalue(), "plot_path": plot_path})
    except Exception as e:
        queue.put({"ok": False, "error": f"{type(e).__name__}: {e}", "stdout": buf.getvalue()})


def run_code(code: str, df=None, save_dir: str | None = None,
             timeout: int | float | None = None) -> dict:
    """执行受限代码, 返回 {ok, stdout, error, plot_path}。

    Args:
        code: LLM 生成的 Python 代码
        df:   当前数据集, 作为 `df` 注入到代码命名空间
        save_dir: 图片保存目录
        timeout: 执行超时秒数 (默认 30); 超时子进程被 terminate, 返回 timeout 错误
    """
    save_dir = save_dir or tempfile.mkdtemp()
    os.makedirs(save_dir, exist_ok=True)
    timeout = timeout if timeout is not None else _DEFAULT_TIMEOUT

    # 步骤 1: 剥白名单内的 import 行 (模块对象已注入, 不需要真 import)
    code = _IMPORT_STRIP.sub("# (import stripped; module already injected)", code)

    # 步骤 2: AST 静态检查高危调用 / 危险 import
    block_reason = _static_check(code)
    if block_reason:
        return {"ok": False, "error": f"[sandbox rejected] {block_reason}", "stdout": ""}

    # 步骤 3: 主进程预编译做语法检查 (子进程还会再编译一次, 因为 code object 不可 pickle)
    try:
        compile(code, "<agent_code>", "exec")
    except SyntaxError as e:
        return {"ok": False, "error": f"syntax: {e}", "stdout": ""}

    # 步骤 4: 子进程受控执行 + 超时兜底 (W3.3)
    # 用 multiprocessing 而非 signal.alarm: Windows 无 SIGALRM, 进程隔离跨平台都稳。
    # ctx="spawn": 不 fork 父进程内存, 子进程干净; Windows 默认就是 spawn。
    # 传源码字符串 (可 pickle), 编译在子进程内做 (code object 不可 pickle)。
    ctx = _mp.get_context("spawn")
    queue: "_mp.Queue" = ctx.Queue()
    proc = ctx.Process(target=_exec_child, args=(code, df, save_dir, queue))
    proc.start()
    proc.join(timeout)
    if proc.is_alive():
        # 超时: 杀子进程, 返回明确错误让 Agent 能继续 (而非整个 run 卡死)
        proc.terminate()
        proc.join(2)  # 给点时间清理
        if proc.is_alive():
            proc.kill()
        return {"ok": False, "error": f"[sandbox timeout] 执行超过 {timeout}s 被终止",
                "stdout": ""}
    # 子进程正常退出, 取结果 (exitcode<0 说明被信号杀, 也要兜底)
    if proc.exitcode and proc.exitcode < 0:
        return {"ok": False,
                "error": f"[sandbox crashed] 子进程退出码 {proc.exitcode} (可能 OOM/段错误)",
                "stdout": ""}
    try:
        return queue.get_nowait()
    except Exception:
        return {"ok": False, "error": "[sandbox error] 子进程未返回结果", "stdout": ""}


# 单元测试见 tests/test_code_sandbox.py (W3.3):
#  - import os / open('/etc') / exec(...) / subprocess.run / __import__ 应被静态拒
#  - import pandas (应被剥掉, 正常运行)
#  - while True 死循环应触发超时终止, 返回 ok=False 且 error 含 timeout
#  - 正常 plt 画图应返回 ok=True + plot_path