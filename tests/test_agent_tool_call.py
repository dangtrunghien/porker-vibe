from __future__ import annotations

import asyncio
import json

from pydantic import BaseModel
import pytest

from tests.mock.utils import mock_llm_chunk
from tests.stubs.fake_backend import FakeBackend
from tests.stubs.fake_tool import FakeTool
from vibe.core.agent import Agent
from vibe.core.config import SessionLoggingConfig, VibeConfig
from vibe.core.modes import AgentMode
from vibe.core.tools.base import BaseToolConfig, ToolPermission
from vibe.core.types import (
    ApprovalResponse,
    AssistantEvent,
    BaseEvent,
    FunctionCall,
    LLMMessage,
    Role,
    SyncApprovalCallback,
    ToolCall,
    ToolCallEvent,
    ToolResultEvent,
)


async def act_and_collect_events(agent: Agent, prompt: str) -> list[BaseEvent]:
    return [ev async for ev in agent.act(prompt)]


def make_config() -> VibeConfig:
    return VibeConfig(
        session_logging=SessionLoggingConfig(enabled=False),
        auto_compact_threshold=0,
        enabled_tools=[], # No specific tools enabled by default
        system_prompt_id="tests",
        include_project_context=False,
        include_prompt_detail=False,
    )




















@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exception_class",
    [
        pytest.param(KeyboardInterrupt, id="keyboard_interrupt"),
        pytest.param(asyncio.CancelledError, id="asyncio_cancelled"),
    ],
)
async def test_tool_call_can_be_interrupted(
    exception_class: type[BaseException],
) -> None:
    tool_call = ToolCall(
        id="call_8", index=0, function=FunctionCall(name="stub_tool", arguments="{}")
    )
    config = VibeConfig(
        session_logging=SessionLoggingConfig(enabled=False),
        auto_compact_threshold=0,
        enabled_tools=["stub_tool"],
    )
    agent = Agent(
        config,
        mode=AgentMode.AUTO_APPROVE,
        backend=FakeBackend([
            [mock_llm_chunk(content="Let me use the tool.", tool_calls=[tool_call])],
            [mock_llm_chunk(content="Tool execution completed.")],
        ]),
    )
    # no dependency injection available => monkey patch
    agent.tool_manager._available["stub_tool"] = FakeTool
    stub_tool_instance = agent.tool_manager.get("stub_tool")
    assert isinstance(stub_tool_instance, FakeTool)
    stub_tool_instance._exception_to_raise = exception_class()

    events: list[BaseEvent] = []
    with pytest.raises(exception_class):
        async for ev in agent.act("Execute tool"):
            events.append(ev)

    tool_result_event = next(
        (e for e in events if isinstance(e, ToolResultEvent)), None
    )
    assert tool_result_event is not None
    assert tool_result_event.error is not None
    assert "execution interrupted by user" in tool_result_event.error.lower()






