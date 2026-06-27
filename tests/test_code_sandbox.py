"""code_sandbox 单元测试 (W3.3)。

覆盖三类:
1. 静态黑名单: import os / open / exec / __import__ / subprocess 应被拒
2. 白名单注入: import pandas 应被剥掉后正常运行
3. 超时兜底: while True 死循环应被终止, 返回 ok=False 且 error 含 timeout

跑法:
  python -m pytest tests/test_code_sandbox.py -v
  (无 pytest 时) python -m unittest tests.test_code_sandbox -v
"""
import os
import sys
import unittest

# 让 tests/ 能 import 到项目根的 tools 包
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.code_sandbox import run_code


class TestStaticBlocklist(unittest.TestCase):
    """静态 AST 黑名单: 高危调用/import 编译前就拒, 根本不进子进程。"""

    def test_import_os_rejected(self):
        r = run_code("import os\nos.system('echo hi')")
        self.assertFalse(r["ok"])
        self.assertIn("禁止 import", r["error"])

    def test_import_subprocess_rejected(self):
        r = run_code("import subprocess\nsubprocess.run(['ls'])")
        self.assertFalse(r["ok"])
        self.assertIn("禁止 import", r["error"])

    def test_open_rejected(self):
        r = run_code("open('/etc/passwd').read()")
        self.assertFalse(r["ok"])
        self.assertIn("禁止调用", r["error"])

    def test_exec_rejected(self):
        r = run_code("exec('print(1)')")
        self.assertFalse(r["ok"])
        self.assertIn("禁止调用", r["error"])

    def test_dunder_import_rejected(self):
        r = run_code("__import__('os').system('echo hi')")
        self.assertFalse(r["ok"])
        self.assertIn("禁止调用", r["error"])

    def test_syntax_error_rejected(self):
        r = run_code("def f(")  # 语法错误
        self.assertFalse(r["ok"])
        self.assertIn("syntax", r["error"])


class TestWhitelistInjection(unittest.TestCase):
    """白名单模块 (pandas/numpy/matplotlib) 已注入, import 行被剥掉后正常运行。"""

    def test_import_pandas_stripped_and_runs(self):
        r = run_code("import pandas as pd\ndf = pd.DataFrame({'x':[1,2]})\nprint(len(df))",
                     save_dir="results/plots")
        self.assertTrue(r["ok"], msg=f"应正常运行, 实际: {r}")
        self.assertEqual(r["stdout"].strip(), "2")

    def test_import_numpy_stripped_and_runs(self):
        r = run_code("import numpy as np\nprint(int(np.array([1,2,3]).sum()))",
                     save_dir="results/plots")
        self.assertTrue(r["ok"], msg=f"应正常运行, 实际: {r}")
        self.assertEqual(r["stdout"].strip(), "6")


class TestNormalExecution(unittest.TestCase):
    """正常代码应返回 ok=True, stdout 正确, 画图时 plot_path 非空。"""

    def test_simple_print(self):
        r = run_code("print('hello sandbox')", save_dir="results/plots")
        self.assertTrue(r["ok"])
        self.assertIn("hello", r["stdout"])

    def test_plot_generates_path(self):
        r = run_code("plt.plot([1,2,3]); plt.title('t')", save_dir="results/plots")
        self.assertTrue(r["ok"], msg=f"画图应成功, 实际: {r}")
        self.assertIsNotNone(r.get("plot_path"))
        self.assertTrue(r["plot_path"].endswith(".png"))

    def test_runtime_error_caught(self):
        r = run_code("x = [1,2]\nprint(x[99])")  # IndexError
        self.assertFalse(r["ok"])
        self.assertIn("IndexError", r["error"])


class TestTimeoutGuard(unittest.TestCase):
    """W3.3 核心: 超时兜底。死循环应被 terminate, 主进程不卡死, 返回明确错误。"""

    def test_infinite_loop_times_out(self):
        # 设 3s 超时; while True 必然触发
        r = run_code("i=0\nwhile True:\n    i+=1", timeout=3)
        self.assertFalse(r["ok"])
        self.assertIn("timeout", r["error"].lower())
        # 主进程能拿到结果说明没卡死 (能走到断言就是证明)

    def test_slow_but_completes(self):
        # sleep 1s, 超时设 5s, 应正常完成而非超时
        r = run_code("import time\ntime.sleep(1)\nprint('done')", timeout=5,
                     save_dir="results/plots")
        self.assertTrue(r["ok"], msg=f"应正常完成, 实际: {r}")
        self.assertIn("done", r["stdout"])

    def test_timeout_default_applied(self):
        # 不传 timeout, 用默认 30s; 这里跑个能快速完成的, 验证默认值不误伤
        r = run_code("print('fast')", save_dir="results/plots")
        self.assertTrue(r["ok"])
        self.assertIn("fast", r["stdout"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
