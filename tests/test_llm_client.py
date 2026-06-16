import pytest

from steward.config import QwenSettings
from steward.llm.client import ChatResponse, FakeLLM, LLMError, QwenClient, ToolCall


def test_fake_llm_returns_scripted_responses_in_order():
    fake = FakeLLM(scripted=[ChatResponse(content="one"), ChatResponse(content="two")])
    assert fake.chat([{"role": "user", "content": "hi"}], []).content == "one"
    assert fake.chat([], []).content == "two"


def test_fake_llm_records_received_messages():
    fake = FakeLLM(scripted=[ChatResponse(content="ok")])
    fake.chat([{"role": "user", "content": "hello"}], [])
    assert fake.received[0][0]["content"] == "hello"


def test_fake_llm_raises_when_script_exhausted():
    fake = FakeLLM(scripted=[])
    with pytest.raises(AssertionError, match="exhausted"):
        fake.chat([], [])


def test_qwen_client_requires_api_key():
    with pytest.raises(LLMError, match="QWEN_API_KEY"):
        QwenClient(QwenSettings(api_key=None))


def test_tool_call_is_frozen_value_object():
    call = ToolCall(id="1", name="list_resources", arguments="{}")
    assert call.name == "list_resources"
    with pytest.raises(AttributeError):
        call.name = "other"


def test_fake_llm_does_not_mutate_its_script():
    script = [ChatResponse(content="one")]
    fake = FakeLLM(scripted=script)
    fake.chat([], [])
    assert len(script) == 1  # script list untouched after use
