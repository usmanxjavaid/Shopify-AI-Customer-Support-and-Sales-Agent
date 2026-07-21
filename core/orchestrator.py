"""
core/orchestrator.py
---------------------
The agent brain — ties together the LLM, tools, memory, and guardrails.

Flow per message:
    1. Load conversation history from memory
    2. Send history + new message + tool schemas to the LLM
    3. If LLM requests a tool call -> execute it -> feed result back -> repeat
    4. If LLM gives a final text reply -> return it
    5. Save the new turn to memory

LLM provider strategy:
    Primary:  OpenRouter (deepseek/deepseek-chat) — better tool-calling quality
    Fallback: Groq (llama-3.3-70b-versatile) — used if OpenRouter fails for any reason

Both providers use the OpenAI-compatible chat completions format,
so we can call either with the same request structure.
"""

import json
import requests
from typing import Optional

from config import settings
from core.models import NormalizedMessage, AgentResponse
from core.prompts import SYSTEM_PROMPT
from core.tool_schemas import TOOL_SCHEMAS
from core import memory
from logger import get_logger

logger = get_logger(__name__)

# Maps tool names to actual Python functions.
# Imported here (not at module top) to avoid circular imports,
# since tools may eventually import from core too.
from tools.shopify_tools import (
    get_order_status,
    get_all_products,
    get_product_details,
    initiate_refund,
    escalate_to_human,
)

TOOL_FUNCTIONS = {
    "get_order_status": get_order_status,
    "get_all_products": get_all_products,
    "get_product_details": get_product_details,
    "initiate_refund": initiate_refund,
    "escalate_to_human": escalate_to_human,
}

MAX_TOOL_ITERATIONS = 5


# ------------------------------------------------------------------
# LLM calling with fallback
# ------------------------------------------------------------------

def _call_openrouter(messages: list[dict]) -> Optional[dict]:
    """
    Calls OpenRouter's chat completions endpoint.

    Args:
        messages: Full message list including system prompt, history,
                  and the new user message (OpenAI format).

    Returns:
        The raw response JSON dict, or None if the call failed.
    """
    try:
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.OPENROUTER_MODEL,
                "messages": messages,
                "tools": TOOL_SCHEMAS,
            },
            timeout=30,
        )
        response.raise_for_status()
        logger.debug("OpenRouter call succeeded")
        return response.json()

    except requests.exceptions.RequestException as e:
        logger.warning(f"OpenRouter call failed: {e}")
        return None


def _call_groq(messages: list[dict]) -> Optional[dict]:
    """
    Calls Groq's chat completions endpoint (OpenAI-compatible format).
    Used as a fallback if OpenRouter fails.

    Args:
        messages: Full message list, same format as OpenRouter.

    Returns:
        The raw response JSON dict, or None if the call failed.
    """
    try:
        response = requests.post(
            url="https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.GROQ_MODEL,
                "messages": messages,
                "tools": TOOL_SCHEMAS,
            },
            timeout=30,
        )
        response.raise_for_status()
        logger.debug("Groq fallback call succeeded")
        return response.json()

    except requests.exceptions.RequestException as e:
        logger.error(f"Groq fallback call also failed: {e}")
        return None


def _call_llm(messages: list[dict]) -> Optional[dict]:
    """
    Calls the LLM with primary/fallback logic.

    Tries OpenRouter first. If that fails for any reason
    (timeout, rate limit, API error), falls back to Groq.

    Args:
        messages: Full conversation messages in OpenAI format.

    Returns:
        Raw LLM response JSON, or None if both providers failed.
    """
    result = _call_openrouter(messages)

    if result is not None:
        return result

    logger.warning("Falling back to Groq after OpenRouter failure")
    return _call_groq(messages)


# ------------------------------------------------------------------
# Tool execution
# ------------------------------------------------------------------

def _execute_tool(tool_name: str, arguments: dict) -> str:
    """
    Executes a tool by name with the given arguments.

    Args:
        tool_name: Name of the tool the LLM requested.
        arguments: Parsed arguments dict from the LLM's tool call.

    Returns:
        The tool's plain text result, or an error message if the
        tool doesn't exist or raised an exception.
    """
    func = TOOL_FUNCTIONS.get(tool_name)

    if func is None:
        logger.error(f"LLM requested unknown tool: {tool_name}")
        return f"Error: tool '{tool_name}' does not exist."

    try:
        logger.info(f"Executing tool: {tool_name} | args: {arguments}")
        result = func(**arguments)
        return result

    except Exception as e:
        logger.error(f"Tool '{tool_name}' raised an exception: {e}")
        return f"Error executing {tool_name}: {e}"


# ------------------------------------------------------------------
# Main orchestration loop
# ------------------------------------------------------------------

def handle_message(msg: NormalizedMessage) -> AgentResponse:
    """
    Processes a single customer message through the full agent loop.

    Args:
        msg: The normalized incoming message from any channel.

    Returns:
        AgentResponse with the final reply text and escalation status.
    """
    logger.info(f"Handling message from {msg.channel}:{msg.user_id}")

    # Load conversation history
    history = memory.get_history(msg.channel, msg.user_id)

    # Build the full message list for the LLM
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": msg.text})

    escalated = False
    tool_used = None

    # Tool-calling loop
    for iteration in range(MAX_TOOL_ITERATIONS):
        response = _call_llm(messages)

        if response is None:
            logger.error("Both LLM providers failed")
            reply_text = (
                "I'm having trouble connecting right now. "
                "Let me get a human to help you instead."
            )
            escalated = True
            break

        choice = response["choices"][0]
        message = choice["message"]

        logger.debug(f"LLM raw message: {message}")

        # Case 1: LLM wants to call a tool
        if message.get("tool_calls"):
            # Append the assistant's tool-call message to context
            messages.append(message)

            for tool_call in message["tool_calls"]:
                tool_name = tool_call["function"]["name"]
                tool_args = json.loads(tool_call["function"]["arguments"])

                tool_used = tool_name
                if tool_name == "escalate_to_human":
                    escalated = True

                tool_result = _execute_tool(tool_name, tool_args)

                # Feed the tool result back into the conversation
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": tool_result,
                })

            # Loop again — LLM will now respond using the tool result
            continue

        # Case 2: LLM gave a final text reply
        reply_text = message.get("content", "")
        logger.info(f"Final reply generated after {iteration + 1} iteration(s)")
        break

    else:
        # Loop exhausted MAX_TOOL_ITERATIONS without a final answer
        logger.warning("Max tool iterations reached without final answer")
        reply_text = (
            "I'm having trouble completing this request. "
            "Let me connect you with a human agent."
        )
        escalated = True

    # Save this turn to memory
    memory.append_turn(msg.channel, msg.user_id, "user", msg.text)
    memory.append_turn(msg.channel, msg.user_id, "assistant", reply_text)

    return AgentResponse(
        text=reply_text,
        escalated=escalated,
        tool_used=tool_used,
    )


logger.debug("core.orchestrator loaded successfully")