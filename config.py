"""模型与嵌入工厂。

沿用简历里"工厂模式管理模型与嵌入实例、配置与代码解耦"的思路: 同一份代码
不写死 OpenAI 还是 DashScope, 切换只改 .env。

坑: AutoGen 的 OpenAIChatCompletionClient 内部维护一张 OpenAI 官方模型白名单,
非 OpenAI 模型(如 DashScope 的 qwen-plus)必须手传 model_info 声明它的能力
(是否支持 function call / json / 上下文长度), 否则报
"model_info is required when model name is not a valid OpenAI model"。
"""
import os
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_core.models import ModelFamily, ModelInfo
from dotenv import load_dotenv

load_dotenv()

MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4o-mini")
BASE_URL = os.getenv("OPENAI_BASE_URL")
API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY")


# DashScope qwen 系列能力声明: 支持 function call / json, 上下文 128k.
# 这一份 ModelInfo 沿用 AutoGen 官方示例对阿里云 qwen 的推荐配置。
_QWEN_INFO = ModelInfo(
    vision=False, function_calling=True, json_output=True,
    family=ModelFamily.UNKNOWN, structured_output=False,
)


def get_model_client(name: str = "default") -> OpenAIChatCompletionClient:
    """统一模型工厂。后续多模型对比时, 按 name 返回不同 client。

    非 OpenAI 官方模型要走 model_info 分支, 否则白名单校验会拦下来。
    判断依据: 模型名是否以 gpt/ft:gpt/o1/o3 开头。
    """
    is_openai = MODEL_NAME.startswith(("gpt-", "ft:gpt-", "o1-", "o3-"))
    return OpenAIChatCompletionClient(
        model=MODEL_NAME,
        base_url=BASE_URL,
        api_key=API_KEY,
        model_info=_QWEN_INFO if not is_openai else None,
        temperature=0.3 if is_openai else None,   # qwen 不一定吃 temperature, 谨慎传
    )


# 嵌入工厂(评测 / 向量召回用; 若只用结构化 schema 压缩可暂不启用)
def get_embedder():
    from openai import OpenAI
    return OpenAI(base_url=BASE_URL, api_key=API_KEY)