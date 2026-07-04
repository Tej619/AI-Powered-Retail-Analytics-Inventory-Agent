import json
from typing import Any, Optional

from openai import AsyncOpenAI, OpenAI
from openai.types.chat import ChatCompletion

from app.config import get_settings
from app.utils.errors import OpenAIError
from app.utils.logger import get_logger

logger = get_logger(__name__)


class OpenAIService:
    """
    Wrapper around OpenAI API with retry logic, logging, and error handling.
    """

    _instance: Optional["OpenAIService"] = None

    def __new__(cls) -> "OpenAIService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_client"):
            return

        settings = get_settings()
        self._client = OpenAI(api_key=settings.openai_api_key)
        self._async_client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = settings.openai_model
        self._temperature = settings.openai_temperature
        self._max_tokens = settings.openai_max_tokens
        self._embedding_model = settings.openai_embedding_model

        logger.info("openai_service_initialized", model=self._model)

    @property
    def client(self) -> OpenAI:
        return self._client

    @property
    def async_client(self) -> AsyncOpenAI:
        return self._async_client

    def chat_completion(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[dict[str, str]] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        tool_choice: Optional[str | dict] = None,
        seed: Optional[int] = None,
    ) -> ChatCompletion:
        """
        Execute a chat completion request with error handling and logging.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Override default model
            temperature: Override default temperature
            max_tokens: Override default max tokens
            response_format: e.g. {"type": "json_object"}
            tools: List of tool/function definitions for function calling
            tool_choice: "auto", "none", "required", or specific tool
            seed: Deterministic generation seed

        Returns:
            ChatCompletion response object
        """
        kwargs: dict[str, Any] = {
            "model": model or self._model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self._temperature,
            "max_tokens": max_tokens or self._max_tokens,
        }

        if response_format:
            kwargs["response_format"] = response_format
        if tools:
            kwargs["tools"] = tools
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice
        if seed is not None:
            kwargs["seed"] = seed

        try:
            logger.debug(
                "openai_request",
                model=kwargs["model"],
                messages_count=len(messages),
                has_tools=tools is not None,
            )

            response = self._client.chat.completions.create(**kwargs)

            logger.info(
                "openai_response",
                model=response.model,
                finish_reason=response.choices[0].finish_reason,
                prompt_tokens=response.usage.prompt_tokens if response.usage else None,
                completion_tokens=response.usage.completion_tokens if response.usage else None,
            )

            return response

        except Exception as e:
            logger.error("openai_request_failed", error=str(e), model=kwargs["model"])
            raise OpenAIError(
                f"OpenAI API request failed: {e}",
                model=kwargs["model"],
            )

    def chat_completion_json(
        self,
        messages: list[dict[str, str]],
        output_schema: Optional[dict] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Chat completion that returns parsed JSON.
        Automatically sets response_format and parses the response.
        """
        response = self.chat_completion(
            messages=messages,
            response_format={"type": "json_object"},
            **kwargs,
        )

        content = response.choices[0].message.content or "{}"

        try:
            result = json.loads(content)
        except json.JSONDecodeError as e:
            logger.error("json_parse_failed", content=content[:500], error=str(e))
            raise OpenAIError(
                f"Failed to parse JSON response: {e}",
                model=response.model,
                details={"raw_content": content[:1000]},
            )

        return result

    def extract_with_schema(
        self,
        text: str,
        system_prompt: str,
        output_schema: dict[str, Any],
        model: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Use structured output / function calling to extract data
        from unstructured text into a defined schema.

        This uses OpenAI's function calling for reliable extraction.
        """
        schema_definition = {
            "type": "function",
            "function": {
                "name": "extract_data",
                "description": "Extract structured data from the provided text.",
                "parameters": output_schema,
            },
        }

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ]

        response = self.chat_completion(
            messages=messages,
            tools=[schema_definition],
            tool_choice={"type": "function", "function": {"name": "extract_data"}},
            model=model,
        )

        # Extract the function call arguments
        choice = response.choices[0]
        if choice.message.tool_calls:
            args = choice.message.tool_calls[0].function.arguments
            try:
                return json.loads(args)
            except json.JSONDecodeError:
                pass

        # Fallback: try parsing content as JSON
        if choice.message.content:
            try:
                return json.loads(choice.message.content)
            except json.JSONDecodeError:
                pass

        logger.error("extraction_failed", text_length=len(text))
        raise OpenAIError(
            "Failed to extract structured data from text",
            model=model or self._model,
        )

    def generate_embedding(self, text: str) -> list[float]:
        """Generate an embedding vector for the given text."""
        try:
            response = self._client.embeddings.create(
                model=self._embedding_model,
                input=text,
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error("embedding_failed", error=str(e))
            raise OpenAIError(f"Embedding generation failed: {e}", model=self._embedding_model)

    async def async_chat_completion(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> ChatCompletion:
        """Async version of chat_completion."""
        settings = get_settings()
        kwargs.setdefault("model", self._model)
        kwargs.setdefault("temperature", self._temperature)
        kwargs.setdefault("max_tokens", self._max_tokens)
        kwargs["messages"] = messages

        try:
            response = await self._async_client.chat.completions.create(**kwargs)
            return response
        except Exception as e:
            logger.error("async_openai_failed", error=str(e))
            raise OpenAIError(f"Async OpenAI request failed: {e}", model=kwargs.get("model"))


def get_openai_service() -> OpenAIService:
    return OpenAIService()