"""SchemaMemory: 把 DataFrame 元信息结构化压缩。

痛点: 数据集 schema 一旦上百列, 每轮全量塞给模型会爆 token。这里把列名 /
类型 / 统计缩成一份紧凑文本, 复用多轮; 列数 / 对话轮数变化时才刷新。
"""
import json
import pandas as pd


class SchemaMemory:
    def __init__(self, df: pd.DataFrame):
        self._snapshot = self._build(df)
        self._last_shape = df.shape

    @staticmethod
    def _build(df: pd.DataFrame) -> str:
        info = {
            "shape": list(df.shape),
            "columns": [{"name": c, "dtype": str(df[c].dtype),
                         "nunique": int(df[c].nunique()),
                         "missing": float(round(df[c].isna().mean(), 3))}
                        for c in df.columns],
            "numeric": df.describe().round(2).to_dict() if df.shape[1] else {},
        }
        return json.dumps(info, ensure_ascii=False, default=str)

    def get(self) -> str:
        return self._snapshot

    def should_refresh(self, df: pd.DataFrame) -> bool:
        return df.shape != self._last_shape

    def refresh(self, df: pd.DataFrame) -> None:
        if self.should_refresh(df):
            self._snapshot = self._build(df)
            self._last_shape = df.shape

    @staticmethod
    def verbose_schema(df: pd.DataFrame) -> str:
        """未压缩的 schema dump, 作为「无记忆」对照组基线。

        模拟"不压缩直接把 head/dtypes/describe 全塞给模型"的朴素做法,
        和 get() 的紧凑 JSON 对照, 量化 SchemaMemory 的 token 节省。
        """
        parts = [
            df.head().to_string(),
            df.dtypes.to_string(),
            df.describe().to_string(),
        ]
        return "\n".join(parts)


# TODO(P1): 量化指标 —— 对比「无记忆 vs SchemaMemory」, 测单次完整分析 token 消耗下降 %
# → 已由 experiments/token_compare.py 落地, 产物 results/token_compare.json