#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
# SPDX-FileCopyrightText: 2023 UnionTech Software Technology Co., Ltd.
# SPDX-License-Identifier: GPL-2.0-only
# pylint: disable=all
"""VLM element locator - detection layer component, read-only operations."""
from __future__ import annotations

import base64
import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

import httpx

if TYPE_CHECKING:
    from src.vlm.config import VLMConfig

logger = logging.getLogger(__name__)


def _extract_json(content: str) -> Any:
    """Extract JSON from VLM response content, handling code blocks."""
    if not content:
        return None
    content = content.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        json_lines = []
        in_block = False
        for line in lines:
            if line.startswith("```"):
                in_block = not in_block
                continue
            if in_block:
                json_lines.append(line)
        content = "\n".join(json_lines)
    try:
        data = json.loads(content)
        if isinstance(data, list) and len(data) > 0:
            return data[0]
        return data
    except (json.JSONDecodeError, TypeError):
        return None


@dataclass
class ClickTarget:
    """VLM returned click target."""

    x: int
    y: int
    confidence: float = 1.0
    label: str = ""


@dataclass
class VLMAssertResult:
    """VLM assertion result."""

    verdict: str
    confidence: float
    reason: str = ""


class VLMLocator(ABC):
    """VLM locator abstract base class."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check if backend is available."""

    @abstractmethod
    def locate_element(
        self,
        image_path: str,
        description: str,
        crop_meta: dict = None,  # type: ignore[assignment]
    ) -> ClickTarget:
        """
        Locate UI element through natural language description.

        Args:
            image_path: Screenshot path
            description: Element description, e.g. "main menu button"
            crop_meta: Cropping metadata for coordinate restoration

        Returns:
            ClickTarget or None
        """

    @abstractmethod
    def evaluate_assertion(
        self,
        image_path: str,
        assertion: str,
        expected: str,
    ) -> VLMAssertResult:
        """
        Evaluate visual assertion.

        Args:
            image_path: Screenshot path
            assertion: Assertion description
            expected: Expected state

        Returns:
            VLMAssertResult or None
        """

    @abstractmethod
    def decide_tool_call(
        self,
        image_path: str,
        instruction: str,
        tools: list,
        context: dict = None,  # type: ignore[assignment]
    ) -> dict:
        """
        Agent mode: let VLM decide which tool to call.

        Args:
            image_path: Current screenshot
            instruction: Execution instruction
            tools: Available tools list (OpenAI Function Calling format)
            context: Context information (AT-SPI tree summary etc.)

        Returns:
            {"tool_calls": [...], "content": "..."} or {"error": "..."}
        """


    @abstractmethod
    def evaluate_with_reference(
        self,
        reference_path: str,
        actual_path: str,
        feature: str,
        mode: str = "strict",
    ) -> "VLMAssertResult":
        """Compose expected-reference and actual-screenshot into one image and
        judge whether the actual screenshot presents the expected state.

        Args:
            reference_path: Expected-state reference image
            actual_path: Actual screenshot of the app under test
            feature: Assertion feature description (what state is verified)
            mode: "strict" — any style diff (border/color/highlight/alpha)
                  counts as FAIL, only time/date value changes tolerated;
                  "tolerant" — only the feature's state matters

        Returns:
            VLMAssertResult or None
        """



class OpenAICompatLocator(VLMLocator):
    """OpenAI compatible API VLM locator."""

    def __init__(self, config: "VLMConfig") -> None:
        self._config = config
        self._client = httpx.Client(timeout=config.backend.timeout)

    def is_available(self) -> bool:
        try:
            resp = self._client.get(
                "{}/models".format(self._config.backend.base_url.rstrip("/")),
                headers={"Authorization": "Bearer {}".format(self._config.backend.api_key)},
                timeout=5.0,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def _encode_image(self, image_path: str) -> str:
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError("Image not found: {}".format(image_path))
        raw = path.read_bytes()
        if len(raw) > 20 * 1024 * 1024:
            raise ValueError("Image too large: {} bytes (max 20MB)".format(len(raw)))
        return base64.b64encode(raw).decode("utf-8")

    def _call_api(
        self,
        messages: list,
        tools: list = None,  # type: ignore[assignment]
    ) -> dict:
        payload = {
            "model": self._config.backend.model,
            "messages": messages,
            "max_tokens": 1024,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        url = self._config.backend.base_url.rstrip("/")
        if url.startswith("http://") and not url.startswith(("http://localhost", "http://127.0.0.1")):
            logger.warning("VLM API key transmitted over insecure HTTP")
        for attempt in range(self._config.backend.max_retries):
            try:
                resp = self._client.post(
                    "{}/chat/completions".format(
                        self._config.backend.base_url.rstrip("/")
                    ),
                    headers={
                        "Authorization": "Bearer {}".format(
                            self._config.backend.api_key
                        ),
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                if attempt == self._config.backend.max_retries - 1:
                    return {
                        "error": "HTTP {} (response body omitted for security)".format(
                            e.response.status_code
                        )
                    }
                time.sleep(self._config.backend.retry_delay)
            except Exception as e:
                if attempt == self._config.backend.max_retries - 1:
                    return {"error": str(e)}
                time.sleep(self._config.backend.retry_delay)

        return {"error": "Max retries exceeded"}

    def locate_element(
        self,
        image_path: str,
        description: str,
        crop_meta: dict = None,  # type: ignore[assignment]
    ) -> ClickTarget:
        """Locate element through description."""

        img_b64 = self._encode_image(image_path)

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "data:image/png;base64,{}".format(img_b64)
                        },
                    },
                    {
                        "type": "text",
                        "text": "请定位以下 UI 元素：{}\n\n"
                                "要求：\n"
                                "1. 返回元素中心点的屏幕坐标 (x, y)\n"
                                '2. 以 JSON 格式返回：{{"x": <int>, "y": <int>, '
                                '"confidence": <float>, "label": "<str>"}}\n'
                                "3. confidence 范围 0.0-1.0，表示定位置信度\n"
                                '4. 如果无法定位，返回 {{"error": "原因"}}\n'.format(
                            description
                        ),
                    },
                ],
            }
        ]

        result = self._call_api(messages)

        if "error" in result:
            return None  # type: ignore[return-value]

        try:
            content = result["choices"][0]["message"]["content"]
            data = _extract_json(content)
            if not data or "error" in data:
                return None  # type: ignore[return-value]

            target = ClickTarget(
                x=data["x"],
                y=data["y"],
                confidence=data.get("confidence", 0.8),
                label=data.get("label", ""),
            )

            if crop_meta:
                # crop_region dimensions = screen pixel size of the captured region
                crop_region_w = crop_meta.get("cropped_width", 1) or 1
                crop_region_h = crop_meta.get("cropped_height", 1) or 1
                # vlm_image dimensions = actual pixel size sent to VLM (may be resized)
                vlm_w = crop_meta.get("vlm_width", crop_region_w) or 1
                vlm_h = crop_meta.get("vlm_height", crop_region_h) or 1
                # Map: VLM coords -> crop region -> add screen offset
                target.x = int(
                    target.x * crop_region_w / vlm_w
                    + crop_meta.get("offset_x", 0)
                )
                target.y = int(
                    target.y * crop_region_h / vlm_h
                    + crop_meta.get("offset_y", 0)
                )

            return target
        except Exception as e:
            logger.error("VLM locate_element failed: {}".format(e))
            return None  # type: ignore[return-value]

    def evaluate_assertion(
        self,
        image_path: str,
        assertion: str,
        expected: str,
    ) -> VLMAssertResult:
        """Evaluate visual assertion."""

        img_b64 = self._encode_image(image_path)

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "data:image/png;base64,{}".format(img_b64)
                        },
                    },
                    {
                        "type": "text",
                        "text": "请评估以下断言：\n\n"
                                "断言：{}\n"
                                "期望：{}\n\n"
                                "要求：\n"
                                '1. 返回 JSON 格式：{{"verdict": "PASS"|"FAIL", '
                                '"confidence": <float>, "reason": "<str>"}}\n'
                                "2. confidence 范围 0.0-1.0\n"
                                "3. reason 简要说明判断依据\n".format(
                            assertion, expected
                        ),
                    },
                ],
            }
        ]

        result = self._call_api(messages)

        if "error" in result:
            return None  # type: ignore[return-value]

        try:
            content = result["choices"][0]["message"]["content"]
            data = _extract_json(content)
            if not data:
                return None  # type: ignore[return-value]
            return VLMAssertResult(
                verdict=data.get("verdict", "FAIL").upper(),
                confidence=data.get("confidence", 0.5),
                reason=data.get("reason", ""),
            )
        except Exception as e:
            logger.error("VLM evaluate_assertion failed: {}".format(e))
            return None  # type: ignore[return-value]

    def decide_tool_call(
        self,
        image_path: str,
        instruction: str,
        tools: list,
        context: dict = None,  # type: ignore[assignment]
    ) -> dict:
        """Agent mode: let VLM choose tool."""

        img_b64 = self._encode_image(image_path)

        context_str = ""
        if context:
            context_str = "\n## 当前 UI 状态\n{}".format(
                json.dumps(context, ensure_ascii=False, indent=2)
            )

        messages = [
            {
                "role": "system",
                "content": "你是一个桌面应用测试执行 Agent。\n"
                "你有权调用工具来操作 UI。\n"
                "每次只调用一个工具。\n"
                "如果操作完成，调用 finish() 工具。\n",
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "data:image/png;base64,{}".format(img_b64)
                        },
                    },
                    {
                        "type": "text",
                        "text": "{}\n## 任务\n{}\n\n"
                        "请选择合适的工具执行操作。\n".format(
                            context_str, instruction
                        ),
                    },
                ],
            },
        ]

        return self._call_api(messages, tools=tools)

    def evaluate_with_reference(
        self,
        reference_path: str,
        actual_path: str,
        feature: str,
        mode: str = "strict",
        ignore_patterns: Optional[list[str]] = None,
    ) -> VLMAssertResult:
        """Compose expected-reference and actual into one image, then judge.

        llama-server (this build) drops the second image on multi-image requests,
        so the pair is pasted into a single canvas with neutral-gray side labels.
        Only time/date value differences are tolerated by the strict prompt.
        """
        from PIL import Image, ImageDraw, ImageFont

        ref = Image.open(reference_path).convert("RGB")
        actual = Image.open(actual_path).convert("RGB")
        height = max(ref.height, actual.height)
        ref = ref.resize((int(ref.width * height / ref.height), height))
        actual = actual.resize((int(actual.width * height / actual.height), height))

        canvas = Image.new(
            "RGB", (ref.width + actual.width + 4, height + 30), (30, 30, 30)
        )
        canvas.paste(ref, (2, 32))
        canvas.paste(actual, (ref.width + 2, 32))
        draw = ImageDraw.Draw(canvas)
        try:
            font = ImageFont.truetype(
                "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 22
            )
        except Exception:
            font = ImageFont.load_default()
        draw.text((ref.width // 2 - 40, 4), "LEFT=期望", fill=(200, 200, 200), font=font)
        draw.text(
            (ref.width + actual.width // 2 - 40, 4),
            "RIGHT=实际",
            fill=(200, 200, 200),
            font=font,
        )
        if canvas.width > 1024:
            canvas = canvas.resize((1024, int(canvas.height * 1024 / canvas.width)))

        from io import BytesIO

        buf = BytesIO()
        canvas.save(buf, format="PNG")
        img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        strict_rule = (
            "任何边框/颜色/高亮/透明度/布局差异都算 FAIL，仅时间/进度数值变化可忽略。"
            if mode == "strict"
            else "仅关注特征本身的状态是否一致，其他区域差异可忽略。"
        )
        ignore_note = ""
        if ignore_patterns:
            ignore_note = "可忽略的差异：{}。".format("、".join(ignore_patterns))
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "data:image/png;base64,{}".format(img_b64)
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "任务：UI测试断言。\n"
                            "左半=期望参考（灰色标签 LEFT=期望），右半=实际截图"
                            "（灰色标签 RIGHT=实际），忽略标签文字本身。\n"
                            "验证特征：{}\n\n"
                            "判定规则：\n"
                            "1. 先描述左侧期望中该特征如何呈现，再描述右侧实际中该特征如何呈现；\n"
                            "2. {}\n"
                            "3. {}\n"
                            '4. 输出JSON：{{"verdict": "PASS"|"FAIL"|"UNSURE", '
                            '"confidence": 0.0-1.0, "reason": "左右各自状态+差异证据"}}\n'
                            "5. confidence < 0.6 时必须输出 UNSURE。"
                        ).format(feature, strict_rule, ignore_note)
                    },
                ],
            }
        ]

        result = self._call_api(messages)
        if "error" in result:
            logger.error("evaluate_with_reference failed: {}".format(result["error"]))
            return None  # type: ignore[return-value]

        try:
            content = result["choices"][0]["message"]["content"]
            data = _extract_json(content)
            if not data:
                return None  # type: ignore[return-value]
            return VLMAssertResult(
                verdict=data.get("verdict", "FAIL").upper(),
                confidence=data.get("confidence", 0.5),
                reason=data.get("reason", ""),
            )
        except Exception as e:
            logger.error("evaluate_with_reference parse failed: {}".format(e))
            return None  # type: ignore[return-value]


def create_vlm_locator(config) -> VLMLocator:  # type: ignore[type-arg]
    """Factory function: create VLM locator."""
    return OpenAICompatLocator(config)
