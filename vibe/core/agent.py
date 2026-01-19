from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable
from enum import StrEnum, auto
from pathlib import Path
import time
from typing import TYPE_CHECKING, cast
from uuid import UUID, uuid4

from pydantic import BaseModel

from vibe.core.config import VibeConfig
from vibe.core.interaction_logger import InteractionLogger
from vibe.core.llm.backend.factory import BACKEND_FACTORY
from vibe.core.llm.format import APIToolFormatHandler, ResolvedMessage, ResolvedToolCall
from vibe.core.llm.types import BackendLike
from vibe.core.middleware import (
    AutoCompactMiddleware,
    AutoTaskTrackingMiddleware,
    ConversationContext,
    DependencyHealingMiddleware,
    LoopDetectionMiddleware,
    MiddlewareAction,
    MiddlewarePipeline,
    MiddlewareResult,
    PlanModeMiddleware,
    PriceLimitMiddleware,
    ResetReason,
    TurnLimitMiddleware,
)
from vibe.core.modes import AgentMode
from vibe.core.plan_document_manager import PlanDocumentManager
from vibe.core.plan_manager import PlanManager
from vibe.core.planning_models import ItemStatus
from vibe.core.prompts import UtilityPrompt
from vibe.core.skills.manager import SkillManager
from vibe.core.system_prompt import get_universal_system_prompt
from vibe.core.tools.base import (
    BaseTool,
    ToolError,
    ToolPermission,
    ToolPermissionError,
)
from vibe.core.tools.manager import ToolManager
from vibe.core.types import (
    AgentStats,
    ApprovalCallback,
    ApprovalResponse,
    AssistantEvent,
    AsyncApprovalCallback,
    BaseEvent,
    CompactEndEvent,
    CompactStartEvent,
    LLMChunk,
    LLMMessage,
    LLMUsage,
    ReasoningEvent,
    Role,
    SyncApprovalCallback,
    ToolCallEvent,
    ToolResultEvent,
)
from vibe.core.utils import (
    TOOL_ERROR_TAG,
    VIBE_STOP_EVENT_TAG,
    CancellationReason,
    get_user_agent,
    get_user_cancellation_message,
    is_user_cancellation_event,
)

if TYPE_CHECKING:
    from vibe.collaborative.vibe_integration import CollaborativeVibeIntegration


class ToolExecutionResponse(StrEnum):
    SKIP = auto()
    EXECUTE = auto()


class ToolDecision(BaseModel):
    verdict: ToolExecutionResponse
    feedback: str | None = None


class AgentError(Exception):
    """Base exception for Agent errors."""


class AgentStateError(AgentError):
    """Raised when agent is in an invalid state."""


class LLMResponseError(AgentError):
    """Raised when LLM response is malformed or missing expected data."""


class Agent:
    def __init__(
        self,
        config: VibeConfig,
        plan_manager: PlanManager | None = None,
        mode: AgentMode = AgentMode.DEFAULT,
        message_observer: Callable[[LLMMessage], None] | None = None,
        max_turns: int | None = None,
        max_price: float | None = None,
        backend: BackendLike | None = None,
        enable_streaming: bool = False,
        collaborative_integration: CollaborativeVibeIntegration | None = None,
    ) -> None:
        """Initialize the agent with configuration and mode."""
        self.config = config
        self.plan_manager = plan_manager or PlanManager(config.effective_workdir)
        self.plan_document_manager = PlanDocumentManager(config.effective_workdir)
        self.auto_task_tracking_middleware = AutoTaskTrackingMiddleware(
            self.plan_manager
        )
        self._current_plan_item_id: UUID | None = None
        self._mode = mode
        self._max_turns = max_turns
        self._max_price = max_price
        self.collaborative_integration = collaborative_integration

        self.tool_manager = ToolManager(lambda: self.config)
        self.skill_manager = SkillManager(lambda: self.config)
        self.format_handler = APIToolFormatHandler()

        # Inject managers into tools that need them
        self._inject_managers_into_tools()

        self.backend_factory = lambda: backend or self._select_backend()
        self.backend = self.backend_factory()

        self.message_observer = message_observer
        self._last_observed_message_index: int = 0
        self.middleware_pipeline = MiddlewarePipeline()
        self.enable_streaming = enable_streaming
        self._setup_middleware()

        system_prompt = get_universal_system_prompt(
            self.tool_manager,
            config,
            plan_manager=self.plan_manager,
            skill_manager=self.skill_manager,
        )
        self.messages = [LLMMessage(role=Role.system, content=system_prompt)]

        if self.message_observer:
            self.message_observer(self.messages[0])
            self._last_observed_message_index = 1

        self.stats = AgentStats()
        try:
            active_model = config.get_active_model()
            self.stats.input_price_per_million = active_model.input_price
            self.stats.output_price_per_million = active_model.output_price
        except ValueError:
            pass

        self.approval_callback: ApprovalCallback | None = None

        self.session_id = str(uuid4())

        self.interaction_logger = InteractionLogger(
            config.session_logging,
            self.session_id,
            self.auto_approve,
            config.effective_workdir,
        )

    @property
    def mode(self) -> AgentMode:
        return self._mode

    @property
    def auto_approve(self) -> bool:
        return self._mode.auto_approve

    def _select_backend(self) -> BackendLike:
        active_model = self.config.get_active_model()
        provider = self.config.get_provider_for_model(active_model)
        timeout = self.config.api_timeout
        return BACKEND_FACTORY[provider.backend](provider=provider, timeout=timeout)

    def add_message(self, message: LLMMessage) -> None:
        self.messages.append(message)

    def _flush_new_messages(self) -> None:
        if not self.message_observer:
            return

        if self._last_observed_message_index >= len(self.messages):
            return

        for msg in self.messages[self._last_observed_message_index :]:
            self.message_observer(msg)
        self._last_observed_message_index = len(self.messages)

    async def act(self, msg: str) -> AsyncGenerator[BaseEvent]:
        self._clean_message_history()
        async for event in self._conversation_loop(msg):
            yield event

    def _inject_managers_into_tools(self) -> None:
        """Inject managers into tools that need them."""
        try:
            # Inject plan_document_manager into PlanSync tool
            plan_sync_tool = self.tool_manager.get("plan_sync")
            plan_sync_tool._plan_document_manager = self.plan_document_manager
        except Exception:
            # PlanSync tool might not be available, that's okay
            pass

    def _setup_middleware(self) -> None:
        """Configure middleware pipeline for this conversation."""
        self.middleware_pipeline.clear()

        if self._max_turns is not None:
            self.middleware_pipeline.add(TurnLimitMiddleware(self._max_turns))

        if self._max_price is not None:
            self.middleware_pipeline.add(PriceLimitMiddleware(self._max_price))

        self.middleware_pipeline.add(PlanModeMiddleware(lambda: self._mode))

        # Add collaborative routing middleware if collaborative integration is available
        if self.collaborative_integration:
            from vibe.core.middleware import CollaborativeRoutingMiddleware

            self.middleware_pipeline.add(
                CollaborativeRoutingMiddleware(self.collaborative_integration)
            )

        self.middleware_pipeline.add(self.auto_task_tracking_middleware)
        self.middleware_pipeline.add(AutoCompactMiddleware(lambda: self._mode))
        self.middleware_pipeline.add(LoopDetectionMiddleware())
        self.middleware_pipeline.add(DependencyHealingMiddleware())
        self.middleware_pipeline.add(DependencyHealingMiddleware())

    async def _handle_middleware_result(
        self, result: MiddlewareResult
    ) -> AsyncGenerator[BaseEvent]:
        match result.action:
            case MiddlewareAction.STOP:
                yield AssistantEvent(
                    content=f"<{VIBE_STOP_EVENT_TAG}>{result.reason}</{VIBE_STOP_EVENT_TAG}>",
                    stopped_by_middleware=True,
                )

            case MiddlewareAction.INJECT_MESSAGE:
                if result.message and len(self.messages) > 0:
                    last_msg = self.messages[-1]
                    if last_msg.content:
                        last_msg.content += f"\n\n{result.message}"
                    else:
                        last_msg.content = result.message

            case MiddlewareAction.COMPACT:
                old_tokens = result.metadata.get(
                    "old_tokens", self.stats.context_tokens
                )
                threshold = result.metadata.get(
                    "threshold", self.config.auto_compact_threshold
                )

                yield CompactStartEvent(
                    current_context_tokens=old_tokens, threshold=threshold
                )

                summary = await self.compact()
                if summary is None:
                    summary = ""

                yield CompactEndEvent(
                    old_context_tokens=old_tokens,
                    new_context_tokens=self.stats.context_tokens,
                    summary_length=len(summary),
                )

            case MiddlewareAction.CONTINUE:
                pass

    def _get_context(self, turn_start_message_index: int) -> ConversationContext:
        return ConversationContext(
            messages=self.messages,
            stats=self.stats,
            config=self.config,
            current_turn_messages=self.messages[turn_start_message_index:],
        )

    async def _conversation_loop(self, user_msg: str) -> AsyncGenerator[BaseEvent]:
        self._clean_message_history()

        try:
            should_break_loop = False
            while not should_break_loop:
                turn_start_message_index = len(self.messages)

                result = await self.middleware_pipeline.run_before_turn(
                    self._get_context(turn_start_message_index)
                )
                async for event in self._handle_middleware_result(result):
                    yield event

                if result.action == MiddlewareAction.STOP:
                    return

                current_turn_message_content = user_msg  # Start with the user's message
                self._current_plan_item_id = None  # Reset for each turn

                # 1. Check for next actionable item in structured plan
                next_item = self.plan_manager.get_next_actionable_item()

                # 2. If no structured item, check for pending items in todos.md
                todo_instruction = None
                if not next_item:
                    pending_todo = self._get_next_pending_todo()
                    if pending_todo:
                        todo_instruction = (
                            f"The current todo list contains a pending task: {pending_todo}. "
                            "Please perform this task. If it requires tools, use them. "
                            f"Once completed, use `todo_write` to update the status to completed (pass task={pending_todo!r} and status='completed'). "
                            "IMPORTANT: Function in an autonomous loop until ALL todos are finished."
                        )

                if next_item and next_item.status == ItemStatus.PENDING:
                    self._current_plan_item_id = next_item.id
                    self.plan_manager.update_item_status(
                        next_item.id, ItemStatus.IN_PROGRESS
                    )
                    plan_instruction = (
                        f"The current plan requires you to work on: {next_item.name} (ID: {next_item.id}). "
                        f"Description: {next_item.description or 'No description provided.'}. "
                        "Please perform this task. If it requires tools, use them. "
                        "Once completed, report success. "
                        "IMPORTANT: Focus solely on completing this plan item. "
                        f"Your response to the original user message '{user_msg}' should be a brief acknowledgment that you are working on the plan item."
                    )
                    current_turn_message_content = plan_instruction
                elif todo_instruction:
                    current_turn_message_content = todo_instruction

                self.messages.append(
                    LLMMessage(role=Role.user, content=current_turn_message_content)
                )
                self.stats.steps += 1
                user_cancelled = False
                async for event in self._perform_llm_turn():
                    if is_user_cancellation_event(event):
                        user_cancelled = True
                    yield event

                last_message = self.messages[-1]

                # Check if there are more actionable items in the plan or todo list
                next_item_available = (
                    self.plan_manager.get_next_actionable_item() is not None
                    or self._get_next_pending_todo() is not None
                )

                # Stay in loop if we just executed a tool or if there's more work in the plan
                # If auto_approve is enabled, we also want to continue autonomously for plan/todo items
                should_break_loop = (
                    last_message.role != Role.tool
                    and not (self.auto_approve and next_item_available)
                    and not next_item_available
                )

                self._flush_new_messages()

                if user_cancelled:
                    return

                after_result = await self.middleware_pipeline.run_after_turn(
                    self._get_context(turn_start_message_index)
                )
                async for event in self._handle_middleware_result(after_result):
                    yield event

                if after_result.action == MiddlewareAction.STOP:
                    return

        finally:
            self._flush_new_messages()
            await self.interaction_logger.save_interaction(
                self.messages, self.stats, self.config, self.tool_manager
            )

    async def _perform_llm_turn(self) -> AsyncGenerator[BaseEvent, None]:
        if self.enable_streaming:
            async for event in self._stream_assistant_events():
                yield event
        else:
            assistant_event = await self._get_assistant_event()
            if assistant_event.content:
                yield assistant_event

        last_message = self.messages[-1]

        parsed = self.format_handler.parse_message(last_message)
        resolved = self.format_handler.resolve_tool_calls(
            parsed, self.tool_manager, self.config
        )

        if not resolved.tool_calls and not resolved.failed_calls:
            return

        async for event in self._handle_tool_calls(resolved):
            yield event

    async def _stream_assistant_events(
        self,
    ) -> AsyncGenerator[AssistantEvent | ReasoningEvent]:
        content_buffer = ""
        reasoning_buffer = ""
        chunks_with_content = 0
        chunks_with_reasoning = 0
        BATCH_SIZE = 5

        async for chunk in self._chat_streaming():
            if chunk.message.reasoning_content:
                if content_buffer:
                    yield AssistantEvent(content=content_buffer)
                    content_buffer = ""
                    chunks_with_content = 0

                reasoning_buffer += chunk.message.reasoning_content
                chunks_with_reasoning += 1

                if chunks_with_reasoning >= BATCH_SIZE:
                    yield ReasoningEvent(content=reasoning_buffer)
                    reasoning_buffer = ""
                    chunks_with_reasoning = 0

            if chunk.message.content:
                if reasoning_buffer:
                    yield ReasoningEvent(content=reasoning_buffer)
                    reasoning_buffer = ""
                    chunks_with_reasoning = 0

                content_buffer += chunk.message.content
                chunks_with_content += 1

                if chunks_with_content >= BATCH_SIZE:
                    yield AssistantEvent(content=content_buffer)
                    content_buffer = ""
                    chunks_with_content = 0

        if reasoning_buffer:
            yield ReasoningEvent(content=reasoning_buffer)

        if content_buffer:
            yield AssistantEvent(content=content_buffer)

    async def _get_assistant_event(self) -> AssistantEvent:
        llm_result = await self._chat()
        return AssistantEvent(content=llm_result.message.content or "")

    async def _handle_tool_calls(
        self, resolved: ResolvedMessage
    ) -> AsyncGenerator[ToolCallEvent | ToolResultEvent]:
        async for event in self._handle_failed_calls(resolved.failed_calls):
            yield event

        for tool_call in resolved.tool_calls:
            async for event in self._process_single_tool_call(tool_call):
                yield event

    async def _handle_failed_calls(
        self, failed_calls: list
    ) -> AsyncGenerator[ToolResultEvent]:
        """Handle failed tool calls and yield result events."""
        for failed in failed_calls:
            error_msg = f"<{TOOL_ERROR_TAG}>{failed.tool_name}: {failed.error}</{TOOL_ERROR_TAG}>"
            yield ToolResultEvent(
                tool_name=failed.tool_name,
                tool_class=None,
                error=error_msg,
                tool_call_id=failed.call_id,
            )
            self.stats.tool_calls_failed += 1
            self.messages.append(
                self.format_handler.create_failed_tool_response_message(
                    failed, error_msg
                )
            )

    async def _process_single_tool_call(
        self, tool_call: ResolvedToolCall
    ) -> AsyncGenerator[ToolCallEvent | ToolResultEvent]:
        """Process a single tool call and yield events."""
        tool_call_id = tool_call.call_id

        yield ToolCallEvent(
            tool_name=tool_call.tool_name,
            tool_class=tool_call.tool_class,
            args=tool_call.validated_args,
            tool_call_id=tool_call_id,
        )

        try:
            tool_instance = self.tool_manager.get(tool_call.tool_name)
        except Exception as exc:
            yield self._create_tool_error_result(
                tool_call, f"Error getting tool '{tool_call.tool_name}': {exc}"
            )
            return

        decision = await self._should_execute_tool(
            tool_instance, tool_call.validated_args, tool_call_id
        )

        if decision.verdict == ToolExecutionResponse.SKIP:
            for event in self._handle_skipped_tool(tool_call, decision):
                yield event
            return

        self.stats.tool_calls_agreed += 1
        if self._current_plan_item_id:
            self.auto_task_tracking_middleware.register_tool_call_for_plan_item(
                tool_call_id, self._current_plan_item_id
            )

        async for event in self._execute_tool(tool_call, tool_instance):
            yield event

    def _handle_skipped_tool(
        self, tool_call: ResolvedToolCall, decision: ToolDecision
    ) -> list[ToolResultEvent]:
        """Handle a skipped tool call."""
        self.stats.tool_calls_rejected += 1
        skip_reason = decision.feedback or str(
            get_user_cancellation_message(
                CancellationReason.TOOL_SKIPPED, tool_call.tool_name
            )
        )
        self.messages.append(
            LLMMessage.model_validate(
                self.format_handler.create_tool_response_message(tool_call, skip_reason)
            )
        )
        return [
            ToolResultEvent(
                tool_name=tool_call.tool_name,
                tool_class=tool_call.tool_class,
                skipped=True,
                skip_reason=skip_reason,
                tool_call_id=tool_call.call_id,
            )
        ]

    def _create_tool_error_result(
        self, tool_call: ResolvedToolCall, error_msg: str
    ) -> ToolResultEvent:
        """Create an error result event and append message."""
        self.messages.append(
            LLMMessage.model_validate(
                self.format_handler.create_tool_response_message(tool_call, error_msg)
            )
        )
        return ToolResultEvent(
            tool_name=tool_call.tool_name,
            tool_class=tool_call.tool_class,
            error=error_msg,
            tool_call_id=tool_call.call_id,
        )

    async def _execute_tool(
        self, tool_call: ResolvedToolCall, tool_instance: BaseTool
    ) -> AsyncGenerator[ToolResultEvent]:
        """Execute a tool and yield the result event."""
        try:
            start_time = time.perf_counter()
            result_model = await tool_instance.invoke(**tool_call.args_dict)
            duration = time.perf_counter() - start_time

            text = "\n".join(f"{k}: {v}" for k, v in result_model.model_dump().items())
            self.messages.append(
                LLMMessage.model_validate(
                    self.format_handler.create_tool_response_message(tool_call, text)
                )
            )
            yield ToolResultEvent(
                tool_name=tool_call.tool_name,
                tool_class=tool_call.tool_class,
                result=result_model,
                duration=duration,
                tool_call_id=tool_call.call_id,
            )
            self.stats.tool_calls_succeeded += 1

        except (asyncio.CancelledError, KeyboardInterrupt) as exc:
            yield self._handle_cancellation(tool_call, exc)
            raise

        except (ToolError, ToolPermissionError) as exc:
            yield self._handle_tool_exception(tool_call, tool_instance, exc)

        except Exception as exc:
            yield self._handle_unexpected_exception(tool_call, tool_instance, exc)

    def _handle_cancellation(
        self, tool_call: ResolvedToolCall, exc: Exception
    ) -> ToolResultEvent:
        """Handle cancellation or keyboard interrupt."""
        cancel = str(get_user_cancellation_message(CancellationReason.TOOL_INTERRUPTED))
        self.messages.append(
            LLMMessage.model_validate(
                self.format_handler.create_tool_response_message(tool_call, cancel)
            )
        )
        return ToolResultEvent(
            tool_name=tool_call.tool_name,
            tool_class=tool_call.tool_class,
            error=cancel,
            tool_call_id=tool_call.call_id,
        )

    def _handle_tool_exception(
        self, tool_call: ResolvedToolCall, tool_instance: BaseTool, exc: Exception
    ) -> ToolResultEvent:
        """Handle ToolError or ToolPermissionError."""
        error_msg = f"<{TOOL_ERROR_TAG}>{tool_instance.get_name()} failed: {exc}</{TOOL_ERROR_TAG}>"
        if isinstance(exc, ToolPermissionError):
            self.stats.tool_calls_agreed -= 1
            self.stats.tool_calls_rejected += 1
        else:
            self.stats.tool_calls_failed += 1
        self.messages.append(
            LLMMessage.model_validate(
                self.format_handler.create_tool_response_message(tool_call, error_msg)
            )
        )
        return ToolResultEvent(
            tool_name=tool_call.tool_name,
            tool_class=tool_call.tool_class,
            error=error_msg,
            tool_call_id=tool_call.call_id,
        )

    def _handle_unexpected_exception(
        self, tool_call: ResolvedToolCall, tool_instance: BaseTool, exc: Exception
    ) -> ToolResultEvent:
        """Handle unexpected exceptions during tool execution."""
        from pathlib import Path

        error_log_path = Path.home() / ".vibe" / "error.log"
        log_success = self._log_error_to_file(error_log_path, tool_call, exc)

        import traceback

        tb = traceback.format_exc()

        if log_success:
            error_msg = (
                f"<{TOOL_ERROR_TAG}>{tool_instance.get_name()} failed with {type(exc).__name__}: {exc}\n\n"
                f"FULL TRACEBACK:\n{tb}\n\n"
                f"See ~/.vibe/error.log for persistent logs.</{TOOL_ERROR_TAG}>"
            )
        else:
            error_msg = (
                f"<{TOOL_ERROR_TAG}>{tool_instance.get_name()} failed with {type(exc).__name__}: {exc}\n\n"
                f"FULL TRACEBACK:\n{tb}\n\n"
                f"(Error logging failed - check terminal output)</{TOOL_ERROR_TAG}>"
            )

        self.stats.tool_calls_failed += 1
        self.messages.append(
            LLMMessage.model_validate(
                self.format_handler.create_tool_response_message(tool_call, error_msg)
            )
        )
        return ToolResultEvent(
            tool_name=tool_call.tool_name,
            tool_class=tool_call.tool_class,
            error=error_msg,
            tool_call_id=tool_call.call_id,
        )

    def _log_error_to_file(
        self, error_log_path: Path, tool_call: ResolvedToolCall, exc: Exception
    ) -> bool:
        """Log error to file and return success status."""
        from datetime import datetime
        import sys
        import traceback

        try:
            error_log_path.parent.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(error_log_path, "a", encoding="utf-8") as f:
                f.write(f"\n{'=' * 80}\n")
                f.write(f"[{timestamp}] Tool Execution Error: {tool_call.tool_name}\n")
                f.write(f"{'=' * 80}\n")
                f.write(f"Error Type: {type(exc).__name__}\n")
                f.write(f"Error Message: {exc!s}\n")
                f.write(f"Tool: {tool_call.tool_name}\n")
                f.write(f"Tool Args: {tool_call.args_dict}\n")
                f.write("\nTraceback:\n")
                f.write(traceback.format_exc())
                f.write(f"\n{'=' * 80}\n")
                f.flush()
            return True
        except Exception as log_err:
            try:
                sys.stderr.write("\n[VIBE ERROR LOGGER FAILED]\n")
                sys.stderr.write(f"Original error: {type(exc).__name__}: {exc}\n")
                sys.stderr.write(
                    f"Logging error: {type(log_err).__name__}: {log_err}\n"
                )
                sys.stderr.write(f"Attempted log path: {error_log_path}\n")
                sys.stderr.write(traceback.format_exc())
                sys.stderr.flush()
            except Exception:
                pass
            return False

    async def _chat(self, max_tokens: int | None = None) -> LLMChunk:
        active_model = self.config.get_active_model()
        provider = self.config.get_provider_for_model(active_model)

        available_tools = self.format_handler.get_available_tools(
            self.tool_manager, self.config
        )
        tool_choice = self.format_handler.get_tool_choice()

        try:
            start_time = time.perf_counter()
            async with self.backend as backend:
                result = await backend.complete(
                    model=active_model,
                    messages=self.messages,
                    temperature=active_model.temperature,
                    tools=available_tools,
                    tool_choice=tool_choice,
                    extra_headers={
                        "user-agent": get_user_agent(provider.backend),
                        "x-affinity": self.session_id,
                    },
                    max_tokens=max_tokens,
                )
            end_time = time.perf_counter()

            if result.usage is None:
                raise LLMResponseError(
                    "Usage data missing in non-streaming completion response"
                )
            self._update_stats(usage=result.usage, time_seconds=end_time - start_time)

            processed_message = self.format_handler.process_api_response_message(
                result.message
            )
            self.messages.append(processed_message)
            return LLMChunk(message=processed_message, usage=result.usage)

        except Exception as e:
            raise RuntimeError(
                f"API error from {provider.name} (model: {active_model.name}): {e}"
            ) from e

    async def _chat_streaming(
        self, max_tokens: int | None = None
    ) -> AsyncGenerator[LLMChunk]:
        active_model = self.config.get_active_model()
        provider = self.config.get_provider_for_model(active_model)

        available_tools = self.format_handler.get_available_tools(
            self.tool_manager, self.config
        )
        tool_choice = self.format_handler.get_tool_choice()
        try:
            start_time = time.perf_counter()
            usage = LLMUsage()
            chunk_agg = LLMChunk(message=LLMMessage(role=Role.assistant))
            async with self.backend as backend:
                async for chunk in backend.complete_streaming(
                    model=active_model,
                    messages=self.messages,
                    temperature=active_model.temperature,
                    tools=available_tools,
                    tool_choice=tool_choice,
                    extra_headers={
                        "user-agent": get_user_agent(provider.backend),
                        "x-affinity": self.session_id,
                    },
                    max_tokens=max_tokens,
                ):
                    processed_message = (
                        self.format_handler.process_api_response_message(chunk.message)
                    )
                    processed_chunk = LLMChunk(
                        message=processed_message, usage=chunk.usage
                    )
                    chunk_agg += processed_chunk
                    usage += chunk.usage or LLMUsage()
                    yield processed_chunk
            end_time = time.perf_counter()

            if chunk_agg.usage is None:
                raise LLMResponseError(
                    "Usage data missing in final chunk of streamed completion"
                )
            self._update_stats(usage=usage, time_seconds=end_time - start_time)

            self.messages.append(chunk_agg.message)

        except Exception as e:
            raise RuntimeError(
                f"API error from {provider.name} (model: {active_model.name}): {e}"
            ) from e

    def _update_stats(self, usage: LLMUsage, time_seconds: float) -> None:
        self.stats.last_turn_duration = time_seconds
        self.stats.last_turn_prompt_tokens = usage.prompt_tokens
        self.stats.last_turn_completion_tokens = usage.completion_tokens
        self.stats.session_prompt_tokens += usage.prompt_tokens
        self.stats.session_completion_tokens += usage.completion_tokens
        self.stats.context_tokens = usage.prompt_tokens + usage.completion_tokens
        if time_seconds > 0 and usage.completion_tokens > 0:
            self.stats.tokens_per_second = usage.completion_tokens / time_seconds

    async def _should_execute_tool(
        self, tool: BaseTool, args: BaseModel, tool_call_id: str
    ) -> ToolDecision:
        if self.auto_approve:
            return ToolDecision(verdict=ToolExecutionResponse.EXECUTE)

        allowlist_denylist_result = tool.check_allowlist_denylist(args)
        if allowlist_denylist_result == ToolPermission.ALWAYS:
            return ToolDecision(verdict=ToolExecutionResponse.EXECUTE)
        elif allowlist_denylist_result == ToolPermission.NEVER:
            denylist_patterns = tool.config.denylist
            denylist_str = ", ".join(repr(pattern) for pattern in denylist_patterns)
            return ToolDecision(
                verdict=ToolExecutionResponse.SKIP,
                feedback=f"Tool '{tool.get_name()}' blocked by denylist: [{denylist_str}]",
            )

        tool_name = tool.get_name()
        perm = self.tool_manager.get_tool_config(tool_name).permission

        if perm is ToolPermission.ALWAYS:
            return ToolDecision(verdict=ToolExecutionResponse.EXECUTE)
        if perm is ToolPermission.NEVER:
            return ToolDecision(
                verdict=ToolExecutionResponse.SKIP,
                feedback=f"Tool '{tool_name}' is permanently disabled",
            )

        return await self._ask_approval(tool_name, args, tool_call_id)

    async def _ask_approval(
        self, tool_name: str, args: BaseModel, tool_call_id: str
    ) -> ToolDecision:
        if not self.approval_callback:
            return ToolDecision(
                verdict=ToolExecutionResponse.SKIP,
                feedback="Tool execution not permitted.",
            )
        if asyncio.iscoroutinefunction(self.approval_callback):
            async_callback = cast(AsyncApprovalCallback, self.approval_callback)
            response, feedback = await async_callback(tool_name, args, tool_call_id)
        else:
            sync_callback = cast(SyncApprovalCallback, self.approval_callback)
            response, feedback = sync_callback(tool_name, args, tool_call_id)

        match response:
            case ApprovalResponse.YES:
                return ToolDecision(
                    verdict=ToolExecutionResponse.EXECUTE, feedback=feedback
                )
            case ApprovalResponse.NO:
                return ToolDecision(
                    verdict=ToolExecutionResponse.SKIP, feedback=feedback
                )

    def _clean_message_history(self) -> None:
        ACCEPTABLE_HISTORY_SIZE = 2
        if len(self.messages) < ACCEPTABLE_HISTORY_SIZE:
            return
        self._fill_missing_tool_responses()
        self._ensure_assistant_after_tools()

    def _fill_missing_tool_responses(self) -> None:
        i = 1
        while i < len(self.messages):  # noqa: PLR1702
            msg = self.messages[i]

            if msg.role == "assistant" and msg.tool_calls is not None:
                expected_responses = len(msg.tool_calls)

                if expected_responses > 0:
                    actual_responses = 0
                    j = i + 1
                    while j < len(self.messages) and self.messages[j].role == "tool":
                        actual_responses += 1
                        j += 1

                    if actual_responses < expected_responses:
                        insertion_point = i + 1 + actual_responses

                        for call_idx in range(actual_responses, expected_responses):
                            tool_call_data = msg.tool_calls[call_idx]
                            if tool_call_data is None:
                                continue

                            empty_response = LLMMessage(
                                role=Role.tool,
                                tool_call_id=tool_call_data.id or "",
                                name=(tool_call_data.function.name or "")
                                if tool_call_data.function
                                else "",
                                content=str(
                                    get_user_cancellation_message(
                                        CancellationReason.TOOL_NO_RESPONSE
                                    )
                                ),
                            )

                            self.messages.insert(insertion_point, empty_response)
                            insertion_point += 1

                    i = i + 1 + expected_responses
                    continue

            i += 1

    def _ensure_assistant_after_tools(self) -> None:
        MIN_MESSAGE_SIZE = 2
        if len(self.messages) < MIN_MESSAGE_SIZE:
            return

        last_msg = self.messages[-1]
        if last_msg.role is Role.tool:
            empty_assistant_msg = LLMMessage(role=Role.assistant, content="Understood.")
            self.messages.append(empty_assistant_msg)

    def _reset_session(self) -> None:
        self.session_id = str(uuid4())
        self.interaction_logger.reset_session(self.session_id)

    def set_approval_callback(self, callback: ApprovalCallback) -> None:
        self.approval_callback = callback

    async def clear_history(self) -> None:
        await self.interaction_logger.save_interaction(
            self.messages, self.stats, self.config, self.tool_manager
        )
        self.messages = self.messages[:1]

        self.stats = AgentStats()

        try:
            active_model = self.config.get_active_model()
            self.stats.update_pricing(
                active_model.input_price, active_model.output_price
            )
        except ValueError:
            pass

        self.middleware_pipeline.reset()
        self.tool_manager.reset_all()
        self._reset_session()

    async def compact(self) -> str:
        """Compact the conversation history."""
        try:
            self._clean_message_history()
            await self.interaction_logger.save_interaction(
                self.messages, self.stats, self.config, self.tool_manager
            )

            last_user_message = None
            for msg in reversed(self.messages):
                if msg.role == Role.user:
                    last_user_message = msg.content
                    break

            summary_request = UtilityPrompt.COMPACT.read()
            self.messages.append(LLMMessage(role=Role.user, content=summary_request))
            self.stats.steps += 1

            summary_result = await self._chat()
            if summary_result.usage is None:
                raise LLMResponseError(
                    "Usage data missing in compaction summary response"
                )
            summary_content = summary_result.message.content or ""

            if last_user_message:
                summary_content += (
                    f"\n\nLast request from user was: {last_user_message}"
                )

            system_message = self.messages[0]
            summary_message = LLMMessage(role=Role.user, content=summary_content)
            self.messages = [system_message, summary_message]

            active_model = self.config.get_active_model()
            provider = self.config.get_provider_for_model(active_model)

            async with self.backend as backend:
                actual_context_tokens = await backend.count_tokens(
                    model=active_model,
                    messages=self.messages,
                    tools=self.format_handler.get_available_tools(
                        self.tool_manager, self.config
                    ),
                    extra_headers={"user-agent": get_user_agent(provider.backend)},
                )

            self.stats.context_tokens = actual_context_tokens

            self._reset_session()
            await self.interaction_logger.save_interaction(
                self.messages, self.stats, self.config, self.tool_manager
            )

            self.middleware_pipeline.reset(reset_reason=ResetReason.COMPACT)

            return summary_content or ""

        except Exception:
            await self.interaction_logger.save_interaction(
                self.messages, self.stats, self.config, self.tool_manager
            )
            raise

    async def switch_mode(self, new_mode: AgentMode) -> None:
        if new_mode == self._mode:
            return
        new_config = VibeConfig.load(
            workdir=self.config.workdir, **new_mode.config_overrides
        )

        await self.reload_with_initial_messages(config=new_config)
        self._mode = new_mode

    async def reload_with_initial_messages(
        self,
        config: VibeConfig | None = None,
        max_turns: int | None = None,
        max_price: float | None = None,
    ) -> None:
        await self.interaction_logger.save_interaction(
            self.messages, self.stats, self.config, self.tool_manager
        )

        preserved_messages = self.messages[1:] if len(self.messages) > 1 else []

        if config is not None:
            self.config = config
            self.backend = self.backend_factory()

        if max_turns is not None:
            self._max_turns = max_turns
        if max_price is not None:
            self._max_price = max_price

        self.tool_manager = ToolManager(lambda: self.config)
        self.skill_manager = SkillManager(lambda: self.config)

        # Re-inject managers into tools after re-creating tool_manager
        self._inject_managers_into_tools()

        new_system_prompt = get_universal_system_prompt(
            self.tool_manager,
            self.config,
            plan_manager=self.plan_manager,
            skill_manager=self.skill_manager,
        )
        self.messages = [LLMMessage(role=Role.system, content=new_system_prompt)]

        if preserved_messages:
            self.messages.extend(preserved_messages)

        if len(self.messages) == 1:
            self.stats.reset_context_state()

        try:
            active_model = self.config.get_active_model()
            self.stats.update_pricing(
                active_model.input_price, active_model.output_price
            )
        except ValueError:
            pass

        self._last_observed_message_index = 0

        self._setup_middleware()

        if self.message_observer:
            for msg in self.messages:
                self.message_observer(msg)
            self._last_observed_message_index = len(self.messages)

        self.tool_manager.reset_all()

        await self.interaction_logger.save_interaction(
            self.messages, self.stats, self.config, self.tool_manager
        )

    def _get_next_pending_todo(self) -> str | None:
        """Parse .vibe/plans/todos.md and return the first pending task."""
        todo_path = self.config.effective_workdir / ".vibe" / "plans" / "todos.md"
        if not todo_path.exists():
            return None

        try:
            content = todo_path.read_text(encoding="utf-8")
            import re

            pattern = re.compile(r"^\s*-\s*\[([\s])\]\s*(.+?)(?:\s*<!--.*-->)?$")
            for line in content.splitlines():
                match = pattern.match(line)
                if match:
                    return match.group(2).strip()
        except Exception:
            pass
        return None
