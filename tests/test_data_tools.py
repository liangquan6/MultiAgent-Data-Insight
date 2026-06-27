"""data_tools 单元测试 —— 聚焦 _ensure_dir 路径污染修复 (W5)。

背景: LLM 误把"想要的图名"塞进 save_dir (如 results/plots/sepal_scatter.png),
旧版 _ensure_dir 不校验地把 .png 当目录建, 真图存进 sepal_scatter.png/plot_xxx.png,
路径污染成 xxx.png\\plot_xxx.png, 触发 Reviewer 返工循环吃满消息预算。
修复: 检测图片后缀就剥离成父目录。

跑法:
  python -m unittest tests.test_data_tools -v
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.data_tools import _ensure_dir, PLOT_DIR


class TestEnsureDirPathPollution(unittest.TestCase):
    """_ensure_dir 不能把图片后缀路径当目录建 (W5 bug 修复)。"""

    def setUp(self):
        # 每个测试用独立临时目录, 跑完自清, 不污染 results/plots
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_png_suffix_stripped_not_dir(self):
        # LLM 误传 sepal_scatter.png 给 save_dir
        r = _ensure_dir(os.path.join(self.tmp, "sepal_scatter.png"))
        self.assertEqual(r, self.tmp)  # 应剥离成父目录
        self.assertFalse(os.path.isdir(os.path.join(self.tmp, "sepal_scatter.png")),
                         ".png 不能被当目录建")

    def test_jpg_suffix_stripped(self):
        r = _ensure_dir(os.path.join(self.tmp, "foo.jpg"))
        self.assertEqual(r, self.tmp)
        self.assertFalse(os.path.isdir(os.path.join(self.tmp, "foo.jpg")))

    def test_nested_png_path_stripped(self):
        # results/plots/sub/fig.png → 应得 results/plots/sub
        r = _ensure_dir(os.path.join(self.tmp, "sub", "fig.png"))
        self.assertEqual(r, os.path.join(self.tmp, "sub"))
        self.assertFalse(os.path.isdir(os.path.join(self.tmp, "sub", "fig.png")))
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, "sub")))  # 父目录该被建

    def test_normal_dir_unaffected(self):
        # 正常目录路径 (无图片后缀) 不受影响
        target = os.path.join(self.tmp, "normal_dir")
        r = _ensure_dir(target)
        self.assertEqual(r, target)
        self.assertTrue(os.path.isdir(target))

    def test_empty_string_falls_back_to_plot_dir(self):
        # 空串兜底回 PLOT_DIR, 不报错
        r = _ensure_dir("")
        self.assertEqual(r, PLOT_DIR)

    def test_no_pseudo_dir_created_in_plot_run(self):
        # 模拟连续调用多种误传, 确认 self.tmp 下没有 .png 伪目录
        for name in ["a.png", "b.jpg", "c/foo.png"]:
            _ensure_dir(os.path.join(self.tmp, name))
        png_dirs = [d for d in os.listdir(self.tmp)
                    if os.path.isdir(os.path.join(self.tmp, d)) and d.endswith(".png")]
        self.assertEqual(png_dirs, [], f"不该有 .png 伪目录, 实际: {png_dirs}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
