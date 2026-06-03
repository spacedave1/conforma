import pytest

from conforma.providers import FakeProvider, llm_provider


@pytest.mark.asyncio
async def test_fake_provider_structured_completion() -> None:
    provider = FakeProvider("fake")
    result = await provider.structured_completion(
        messages=[{"role": "user", "content": "Return ok."}],
        response_schema={
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
        },
    )

    assert result == {"data": {"answer": "fake response"}}


def test_llm_provider_rejects_real_platform_without_factory() -> None:
    with pytest.raises(RuntimeError, match="provider_factory"):
        llm_provider(model="model", platform="openai")
