import logging

import json
from typing import Annotated
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import InjectedState

# Get the logger that was configured in main.py
LOGGER = logging.getLogger(__name__)

# Global to hold the graph instance for state history access
_GRAPH_INSTANCE = None

def set_graph_instance(graph):
    global _GRAPH_INSTANCE
    _GRAPH_INSTANCE = graph

# Create a simple tool that adds two numbers and returns the result
@tool
def add_numbers(
    num1: int,
    num2: int
) -> int:
    """
    Adds two numbers and returns the result
    """
    LOGGER.info(f'Adding {num1} and {num2}')
    return num1 + num2

# Create a simple tool that checks if a number is even and returns True or False
@tool
def is_even(
    num: int
) -> bool:
    """
    Checks if a number is even and returns True or False
    """
    LOGGER.info(f'Checking if {num} is even')
    return num % 2 == 0

# Create a simple tool that takes a city name and checks the weather
@tool
def check_weather(
    city: str
) -> str:
    """
    Checks the weather for a given city
    """
    LOGGER.info(f'Checking weather for {city}')
    return f'{city} has sunny weather'

@tool
def check_agent_state(state: Annotated[dict, InjectedState]) -> str:
    """
    Outputs statistics about the current AgentState, including message counts and table dimensions.
    This tool provides a summary of:
    1. For messages variable in AgentState: number of messages, total number of words, and estimated total number of tokens.
    2. For ppm_table, clock_interrupts_table, process_lifetime_table and cpu_lifetime_table: their dimensions (rows and columns).
    """
    LOGGER.info("Checking AgentState contents")
    
    # 1. Messages variable
    messages = state.get("messages", [])
    num_messages = len(messages)
    total_words = 0
    
    # Calculate total words in messages
    # Depending on if msg is a string or a list of strings, we need to handle it differently
    for msg in messages:
        content = ""
        if hasattr(msg, "content"):
            content = msg.content
        elif isinstance(msg, dict) and "content" in msg:
            content = msg["content"]
        
        if isinstance(content, str):
            total_words += len(content.split())
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and "text" in part:
                    total_words += len(part["text"].split())
                elif isinstance(part, str):
                    total_words += len(part.split())

    # Total tokens heuristic (1 word ≈ 1.3 tokens)
    total_tokens = int(total_words * 1.3)
    
    msg_stats = (
        f"Messages:\n"
        f"  - Count: {num_messages}\n"
        f"  - Total Words: {total_words}\n"
        f"  - Total Tokens (estimated): {total_tokens}"
    )

    # 2. Tables: ppm_table, clock_interrupts_table, process_lifetime_table, cpu_lifetime_table
    tables_to_check = [
        "ppm_table",
        "clock_interrupts_table",
        "process_lifetime_table",
        "cpu_lifetime_table"
    ]
    
    table_stats = ["Table Dimensions:"]
    for table_name in tables_to_check:
        table = state.get(table_name)
        if table is None:
            table_stats.append(f"  - {table_name}: Not present in state")
        elif not isinstance(table, list):
            table_stats.append(f"  - {table_name}: Present but not a list (type: {type(table).__name__})")
        else:
            rows = len(table)
            cols = 0
            if rows > 0 and isinstance(table[0], dict):
                cols = len(table[0].keys())
            table_stats.append(f"  - {table_name}: {rows} rows, {cols} columns")

    result = f"{msg_stats}\n\n" + "\n".join(table_stats)
    LOGGER.info(f"AgentState summary: {result}")
    return result

@tool
def check_workflow_history(
    mode: Annotated[str, "The mode to retrieve: 'snapshot' for current state or 'history' for full history"],
    config: RunnableConfig,
) -> str:
    """
    Shows the snapshot or history of the LangGraph workflow state for the current thread.
    Use 'snapshot' to see the most recent state values and metadata (like next nodes).
    Use 'history' to see a list of all previous states in the conversation history.
    """
    if _GRAPH_INSTANCE is None:
        return "Error: Graph instance not provided to tools_general. Please initialize it in app.py."
    
    try:
        if mode == 'snapshot':
            snapshot = _GRAPH_INSTANCE.get_state(config)
            # Format snapshot nicely
            res = [f"--- State Snapshot (Thread: {config['configurable'].get('thread_id', 'N/A')}) ---"]
            res.append(f"Next Nodes: {snapshot.next}")
            
            # Filter or limit values if needed, but for now show all (summarized if huge)
            values_str = json.dumps(snapshot.values, default=str, indent=2)
            if len(values_str) > 5000:
                values_str = values_str[:5000] + "... (truncated)"
            
            res.append(f"Values:\n{values_str}")
            return "\n".join(res)
        
        elif mode == 'history':
            history = list(_GRAPH_INSTANCE.get_state_history(config))
            res = [f"--- State History ({len(history)} snapshots) ---"]
            for i, snap in enumerate(history):
                source = snap.metadata.get('source', 'unknown')
                res.append(f"[{i}] Step: {source} | Next: {snap.next}")
                # We could add more details per snapshot if desired
            return "\n".join(res)
        
        else:
            return f"Invalid mode '{mode}'. Use 'snapshot' or 'history'."
            
    except Exception as e:
        LOGGER.error(f"Error in check_workflow_history: {e}")
        return f"Error retrieving state: {str(e)}"
