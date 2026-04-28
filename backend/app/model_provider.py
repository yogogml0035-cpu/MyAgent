from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Protocol

import httpx

from .runtime import CancellationController
from .settings import MODEL_REGISTRY, Settings

MISSING_DEEPSEEK_API_KEY_MESSAGE = (
    "已选择 DeepSeek，但后端 .env 未配置 DEEPSEEK_API_KEY。"
    "配置后可启用实时模型回复；文档分析仍可使用本地确定性分析器。"
)


class ModelProvider(Protocol):
    def chat(
        self, message: str, model: str, controller: CancellationController | None = None
    ) -> str: ...

    def reason(
        self, prompt: str, model: str, controller: CancellationController | None = None
    ) -> str: ...


class ProviderRouter:
    def __init__(self, settings: Settings):
        self.providers: dict[str, ModelProvider] = {"deepseek": DeepSeekProvider(settings)}
        unsupported = model_provider_names() - self.providers.keys()
        if unsupported:
            raise ValueError(
                f"配置了不支持的模型服务提供方：{', '.join(sorted(unsupported))}"
            )

    def chat(
        self, message: str, model: str, controller: CancellationController | None = None
    ) -> str:
        return self._provider_for_model(model).chat(message, model, controller)

    def reason(
        self, prompt: str, model: str, controller: CancellationController | None = None
    ) -> str:
        return self._provider_for_model(model).reason(prompt, model, controller)

    def _provider_for_model(self, model: str) -> ModelProvider:
        for item in MODEL_REGISTRY:
            if item["id"] == model:
                return self.providers[str(item["provider"])]
        raise ValueError(f"不支持的模型：{model}")


def model_provider_names() -> set[str]:
    return {str(item["provider"]) for item in MODEL_REGISTRY}


def is_model_configuration_warning(message: str) -> bool:
    return message == MISSING_DEEPSEEK_API_KEY_MESSAGE


class DeepSeekProvider:
    def __init__(self, settings: Settings):
        self.settings = settings

    def chat(
        self, message: str, model: str, controller: CancellationController | None = None
    ) -> str:
        if not self.settings.deepseek_api_key:
            return MISSING_DEEPSEEK_API_KEY_MESSAGE
        if controller is not None:
            return self._chat_http_cancellable(message, model, controller)
        return self._chat_http(message, model)

    def _chat_http(self, message: str, model: str) -> str:
        response = httpx.post(
            f"{self.settings.deepseek_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {self.settings.deepseek_api_key}"},
            json=self._chat_payload(message, model),
            timeout=self.settings.deepseek_timeout_seconds,
        )
        response.raise_for_status()
        return self._extract_content(response)

    def reason(
        self, prompt: str, model: str, controller: CancellationController | None = None
    ) -> str:
        if not self.settings.deepseek_api_key:
            return (
                "模型推理未启用：后端未配置 DEEPSEEK_API_KEY，本轮子任务已使用"
                "本地确定性证据引擎。"
            )
        if controller is None:
            return self.chat(prompt, model)
        return self._chat_http_cancellable(prompt, model, controller)

    def _chat_http_cancellable(
        self, message: str, model: str, controller: CancellationController
    ) -> str:
        if controller.is_cancelled():
            raise RuntimeError("模型调用已取消")
        return asyncio.run(self._chat_http_cancellable_async(message, model, controller))

    async def _chat_http_cancellable_async(
        self, message: str, model: str, controller: CancellationController
    ) -> str:
        request_task = asyncio.create_task(self._chat_http_async(message, model))
        cancel_task = asyncio.create_task(wait_until_cancelled(controller))
        done, pending = await asyncio.wait(
            {request_task, cancel_task},
            return_when=asyncio.FIRST_COMPLETED,
        )

        if cancel_task in done:
            request_task.cancel()
            with suppress(asyncio.CancelledError):
                await request_task
            raise RuntimeError("模型调用已取消")

        for task in pending:
            task.cancel()
        with suppress(asyncio.CancelledError):
            await cancel_task
        return request_task.result()

    async def _chat_http_async(self, message: str, model: str) -> str:
        async with httpx.AsyncClient(timeout=self.settings.deepseek_timeout_seconds) as client:
            response = await client.post(
                f"{self.settings.deepseek_base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {self.settings.deepseek_api_key}"},
                json=self._chat_payload(message, model),
            )
        response.raise_for_status()
        return self._extract_content(response)

    @staticmethod
    def _chat_payload(message: str, model: str) -> dict[str, object]:
        return {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "你是谨慎的本地任务助手。默认使用中文简洁回复，除非用户明确要求其他语言。",
                },
                {"role": "user", "content": message},
            ],
        }

    @staticmethod
    def _extract_content(response: httpx.Response) -> str:
        data = response.json()
        return str(data["choices"][0]["message"]["content"])


async def wait_until_cancelled(controller: CancellationController) -> None:
    while not controller.is_cancelled():
        await asyncio.sleep(0.05)
