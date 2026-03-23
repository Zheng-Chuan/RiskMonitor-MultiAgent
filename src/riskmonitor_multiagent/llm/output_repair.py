"""LLM 输出自动修复模块.

提供 JSON 解析和 Schema 验证的自动修复功能.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class OutputRepairError(Exception):
    """输出修复失败异常."""
    pass


def extract_json_from_text(text: str) -> Optional[str]:
    """
    从文本中提取 JSON(处理 LLM 输出前后有多余文本的情况).

    支持:
    - 纯 JSON
    - ```json ... ``` 包裹
    - {...} 包裹但周围有其他文本
    """
    if not text:
        return None

    text = text.strip()

    # 1. 尝试直接解析
    try:
        json.loads(text)
        return text
    except Exception:
        pass

    # 2. 尝试 ```json ... ``` 格式
    code_block_pattern = r"```(?:json)?\s*([\s\S]*?)\s*```"
    matches = re.findall(code_block_pattern, text)
    for match in matches:
        try:
            json.loads(match.strip())
            return match.strip()
        except Exception:
            pass

    # 3. 尝试从文本中找到 {...} 部分
    brace_pattern = r"(\{[\s\S]*\})"
    matches = re.findall(brace_pattern, text)
    for match in matches:
        try:
            json.loads(match)
            return match
        except Exception:
            pass

    return None


def fix_common_json_issues(text: str) -> str:
    """
    修复常见的 JSON 格式问题.

    修复:
    - 尾随逗号
    - 单引号改为双引号
    - 未加引号的 key
    - 注释
    """
    if not text:
        return text

    result = text.strip()

    # 移除单行注释 // ...
    result = re.sub(r"//.*$", "", result, flags=re.MULTILINE)

    # 移除多行注释 /* ... */
    result = re.sub(r"/\*[\s\S]*?\*/", "", result)

    # 尝试修复尾随逗号
    # 在对象最后一个值后
    result = re.sub(r",\s*([}\]])", r"\1", result)

    return result


def parse_with_retry(
    text: str,
    model: Type[T],
    max_fix_attempts: int = 2,
) -> T:
    """
    解析 JSON 并自动修复常见问题.

    Args:
        text: LLM 输出文本
        model: Pydantic 模型
        max_fix_attempts: 最大修复尝试次数

    Returns:
        解析后的 Pydantic 模型

    Raises:
        OutputRepairError: 解析失败且无法修复
    """
    current_text = text
    last_error: Optional[Exception] = None

    for attempt in range(max_fix_attempts + 1):
        try:
            # 1. 尝试提取 JSON
            json_str = extract_json_from_text(current_text)
            if json_str is None:
                raise OutputRepairError("No JSON found in text")

            # 2. 修复常见 JSON 问题
            if attempt > 0:
                json_str = fix_common_json_issues(json_str)

            # 3. 解析为 dict
            data = json.loads(json_str)

            # 4. 验证 Schema
            result = model.model_validate(data)
            return result

        except json.JSONDecodeError as e:
            last_error = e
            logger.debug(f"JSON parse failed (attempt {attempt+1}/{max_fix_attempts+1}): {e}")
        except ValidationError as e:
            last_error = e
            logger.debug(f"Schema validation failed (attempt {attempt+1}/{max_fix_attempts+1}): {e}")
        except Exception as e:
            last_error = e
            logger.debug(f"Unexpected error (attempt {attempt+1}/{max_fix_attempts+1}): {e}")

    raise OutputRepairError(f"Failed to parse and repair after {max_fix_attempts+1} attempts") from last_error


def build_repair_prompt(
    original_prompt: list[dict[str, str]],
    error: Exception,
    model_class: Type[BaseModel],
) -> list[dict[str, str]]:
    """
    构建自动修复的提示词.

    Args:
        original_prompt: 原始提示词
        error: 发生的错误
        model_class: Pydantic 模型类

    Returns:
        修复后的提示词列表
    """
    repair_messages = original_prompt.copy()

    # 添加错误反馈
    error_msg = f"""Your previous output had an error:

Error: {type(error).__name__}
Message: {str(error)}

Please correct this and output valid JSON strictly following this schema:
{model_class.model_json_schema()}

Important:
- Output ONLY valid JSON, no extra text
- Do NOT wrap JSON in code blocks
- Ensure all required fields are present
- Ensure field types are correct
"""

    repair_messages.append({
        "role": "user",
        "content": error_msg,
    })

    return repair_messages
