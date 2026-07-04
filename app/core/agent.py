from typing import Any, Optional

from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.config import get_settings
from app.core.prompts.system_prompts import RETAIL_AGENT_SYSTEM_PROMPT
from app.core.tools.forecasting_tools import get_forecasting_tools
from app.core.tools.insight_tools import get_insight_tools
from app.core.tools.inventory_tools import get_inventory_tools
from app.core.tools.report_tools import get_report_tools
from app.utils.errors import AgentExecutionError
from app.utils.logger import get_logger

logger = get_logger(__name__)


def create_agent() -> AgentExecutor:
    """
    Create and configure the retail analytics agent.

    Uses OpenAI's function calling with a curated set of tools
    for inventory, forecasting, reporting, and insights.
    """
    settings = get_settings()

    # Initialize the LLM
    llm = ChatOpenAI(
        model=settings.openai_model,
        temperature=settings.openai_temperature,
        max_tokens=settings.openai_max_tokens,
        api_key=settings.openai_api_key,
    )

    # Gather all tools
    tools = (
        get_inventory_tools()
        + get_forecasting_tools()
        + get_report_tools()
        + get_insight_tools()
    )

    logger.info(
        "creating_agent",
        model=settings.openai_model,
        tools_count=len(tools),
        tool_names=[t.name for t in tools],
    )

    # Create the prompt template
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", RETAIL_AGENT_SYSTEM_PROMPT),
            MessagesPlaceholder("chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ]
    )

    # Create the agent
    agent = create_openai_tools_agent(llm, tools, prompt)

    # Create the executor
    agent_executor = AgentExecutor(
        agent=agent,
        tools=tools,
        max_iterations=settings.agent_max_iterations,
        verbose=settings.agent_verbose,
        handle_parsing_errors=True,
        return_intermediate_steps=True,
    )

    return agent_executor


def run_agent(
    message: str,
    chat_history: Optional[list[dict[str, str]]] = None,
) -> dict[str, Any]:
    """
    Execute the agent with a natural language message.

    Args:
        message: The user's natural language query
        chat_history: Previous conversation messages for context

    Returns:
        Dictionary with response, tools_used, and intermediate_steps
    """
    agent = create_agent()

    try:
        logger.info("agent_execution_start", message=message[:200])

        result = agent.invoke(
            {"input": message, "chat_history": chat_history or []},
        )

        # Extract tool usage info
        tools_used = []
        intermediate_steps = []

        if result.get("intermediate_steps"):
            for action, observation in result["intermediate_steps"]:
                tools_used.append(action.tool)
                intermediate_steps.append({
                    "tool": action.tool,
                    "input": str(action.tool_input)[:500],
                    "output": str(observation)[:1000]
                })

        logger.info(
            "agent_execution_complete",
            tools_used=list(set(tools_used)),
            output_length=len(result.get("output", "")),
        )

        settings = get_settings()
        return {
            "response": result.get("output", "No response generated."),
            "tools_used": list(set(tools_used)),
            "intermediate_steps": intermediate_steps if settings.agent_verbose else None,
        }

    except Exception as e:
        logger.error("agent_execution_error", error=str(e), message=message[:200])
        raise AgentExecutionError(f"Agent failed to complete: {e}")