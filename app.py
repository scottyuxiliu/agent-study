import logging

# Configure logging:
# Log to console with only INFO and above
# Log to file with DEBUG and above, and file name should be agent_study.log
# Need to show time (without milliseconds), current function, and message, separated by vertical bars
# We use the root logger (no name) so other modules inherit this config
LOGGER = logging.getLogger()
LOGGER.setLevel(logging.DEBUG)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)s | %(funcName)s | %(message)s'))

file_handler = logging.FileHandler('agent_study.log')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)s | %(funcName)s | %(message)s'))

LOGGER.addHandler(console_handler)
LOGGER.addHandler(file_handler)

import shutil
import chainlit as cl
from dotenv import load_dotenv
from typing import Annotated, TypedDict, Any
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import tools_condition, ToolNode
import json
from langchain_core.messages import HumanMessage, SystemMessage, AIMessageChunk, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from api_openai import get_available_models
from tools_etl import check_prerequisites, export_ppm_data, export_processes_data, export_process_details
from tools_general import add_numbers, is_even, check_weather

# Load API keys from .env file
load_dotenv()

# Agent state
# Define AgentState class for LangGraph
# It should have message history
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    ppm_table: list[dict]
    clock_interrupts_table: list[dict]
    process_lifetime_table: list[dict]
    cpu_lifetime_table: list[dict]
    


# Tool node
# Create a list of tools and define the tool node
tools = [
    check_prerequisites,
    export_ppm_data,
    export_processes_data
]
tool_node = ToolNode(tools)

# LLM node
# Initialize LLM and bind tools to it
llm = ChatOpenAI(model='gpt-4o-mini').bind_tools(tools)

def call_llm(
    state: Annotated[AgentState, 'Old state']
) -> Annotated[dict, 'New state']:
    LOGGER.debug(f'state ({type(state)}): {state}')
    LOGGER.debug(f'state messages ({type(state["messages"])}): {state["messages"]}')

    # Build a summary of what's in 'System Memory'
    memory_parts = []
    if state.get("ppm_table"): memory_parts.append("- PPM table")
    if state.get("clock_interrupts_table"): memory_parts.append("- Clock interrupts table")
    if state.get("process_lifetime_table"): memory_parts.append("- Process lifetime table")
    if state.get("cpu_lifetime_table"): memory_parts.append("- CPU lifetime table")

    memory_info = ""
    if memory_parts:
        memory_info = f"\n\n[SYSTEM MEMORY: The following tables are already loaded and available in the history for reference:\n" + "\n".join(memory_parts) + "\n]"

    # Add system instructions before the user message
    system_instructions = SystemMessage(
        content=(
            "You are a performance analysis assistant. Follow these rules strictly:\n"
            "1. If a user mentions a trace or performance issue, you MUST call the 'check_prerequisites' tool first. Do not proceed with analysis until this check passes.\n"
            "2. When you decide to use a tool, you MUST include BOTH your text reasoning AND the tool call in the SAME response message. Do not wait for a second turn.\n"
            "3. Explicitly say which tool you are about to use (e.g., 'I will now call the export_ppm_data tool to...').\n"
            "4. If a user mentions a trace but hasn't provided a file path, ask for the full path to the .etl file. Do not guess.\n"
            f"{memory_info}"
        )
    )

    response = llm.invoke([system_instructions] + state['messages'])
    
    LOGGER.debug(f'response ({type(response)}): {response}')
    LOGGER.info(f'response content: {response.content}')

    # If response has tool calls, log them here
    if response.tool_calls:
        LOGGER.info(f'tool calls ({type(response.tool_calls)}): {response.tool_calls}')

        for tool_call in response.tool_calls:
            LOGGER.info(f'tool call name ({type(tool_call["name"])}): {tool_call["name"]}')
            LOGGER.info(f'tool call args ({type(tool_call["args"])}): {tool_call["args"]}')
    else:
        LOGGER.info('No tool calls found')
    
    return {'messages': response}

def process_tool_outputs(state: AgentState):
    """
    Look for results from 'export_ppm_data' and 'export_processes_data' 
    and update the corresponding state keys.
    """
    updates = {}
    
    # The last message(s) will be ToolMessages after the 'tools' node runs
    for message in reversed(state["messages"]):
        if not isinstance(message, ToolMessage):
            break

        try:
            # Parse the content (ToolNode usually stringifies it)
            content = message.content
            if isinstance(content, str) and (content.startswith('[') or content.startswith('{') or content.startswith('(')):
                # Replace potential Python-style tuples with lists for JSON compatibility if needed
                # or use ast.literal_eval if you strictly expect Python objects
                import ast
                data = ast.literal_eval(content)
            else:
                data = content

            if message.name == "export_ppm_data":
                updates["ppm_table"] = data
            
            elif message.name == "export_processes_data":
                # This tool can return a single list (one table) or a tuple of 3 lists (all tables)
                # Check for the (all) case where we expect a list/tuple of 3 items
                if isinstance(data, (list, tuple)) and len(data) == 3 and all(isinstance(x, list) for x in data):
                    updates["clock_interrupts_table"] = data[0]
                    updates["process_lifetime_table"] = data[1]
                    updates["cpu_lifetime_table"] = data[2]
                else:
                    # Single table case. We don't strictly know WHICH one without looking at tool args,
                    # but we can check the context or just update all that were provided.
                    # As a simple heuristic, if the data has "Clock Interrupts" it's that table, etc.
                    # However, based on the tool return logic, we'll just try to match based on keys.
                    if isinstance(data, list) and len(data) > 0:
                        first_row_keys = data[0].keys()
                        if "Number of Clock Interrupts" in first_row_keys:
                            updates["clock_interrupts_table"] = data
                        elif "Process" in first_row_keys:
                             updates["process_lifetime_table"] = data
                        elif "CPU" in first_row_keys and "Process" not in first_row_keys:
                             updates["cpu_lifetime_table"] = data

        except Exception as e:
            LOGGER.error(f"Failed to parse data from tool '{message.name}': {e}")
            
    return updates

# Build graph
workflow = StateGraph(AgentState)

workflow.add_node('openai_chat', call_llm)
workflow.add_node('tools', tool_node)
workflow.add_node('process_outputs', process_tool_outputs)

workflow.add_edge(START, 'openai_chat')
workflow.add_conditional_edges('openai_chat', tools_condition, 'tools')
workflow.add_edge('tools', 'process_outputs')
workflow.add_edge('process_outputs', 'openai_chat')

# Initialize in-memory storage for conversation history
memory = MemorySaver()

# Compile the graph, passing in the memory saver
app = workflow.compile(checkpointer=memory)

@cl.set_starters
async def set_starters():
    return [
        cl.Starter(
            label="What is FreqCap value?",
            message="What is FreqCap PPM setting value in my log?",
            icon="/public/terminal.svg",
        ),
        cl.Starter(
            label="What are cores busy running?",
            message="What CPU cores are busy and what are they busy running?",
            icon="/public/cpu.svg",
        ),
        cl.Starter(
            label="How much time spent in each QoS level?",
            message="What QoS levels are there and how much time do we spend in each QoS level?",
            icon="/public/activity.svg",
        ),
    ]


@cl.on_message
async def main(message: str):
    # Create a big logger heading with title "Agent Study"
    LOGGER.info('-' * 80)
    LOGGER.info('Agent Study')
    LOGGER.info('-' * 80)
    
    # graph = cl.user_session.get("graph")

    # Create a message placeholder for user to stream into
    answer = cl.Message(content="")
    # We delay sending the message until we actually have content to show
    has_sent_answer = False

    # Configure the runnable to associate the conversation with the user's session
    config: RunnableConfig = {'configurable': {'thread_id': cl.context.session.thread_id}}

    # Run the graph and stream updates
    async for msg, metadata in app.astream(
        {"messages": [HumanMessage(content=message.content)]},
        stream_mode="messages",
        config=config
    ):
        if isinstance(msg, AIMessageChunk):
            if msg.content:
                if not has_sent_answer:
                    await answer.send()
                    has_sent_answer = True
                answer.content += msg.content
                await answer.update()
            
            # Detect if a tool is being called and show it in the UI
            if msg.tool_call_chunks:
                for chunk in msg.tool_call_chunks:
                    if chunk.get("name"):
                        tool_name = chunk["name"]
                        await cl.Message(content=f"🔧 **Starting tool:** `{tool_name}`...").send()
        
        elif isinstance(msg, ToolMessage):
             # When a tool finishes, let the user know
             await cl.Message(content=f"✅ **Tool complete:** `{msg.name}`").send()
             # Reset for the next turn
             answer = cl.Message(content="")
             has_sent_answer = False

    # Test check_prerequisites tool
    # check_prerequisites()

    # Test export_ppm_data tool
    # export_ppm_data('C:\\Users\\scott\\Downloads\\agent_study.etl')

    # Test export_processes_data tool
    # export_processes_data('C:\\Users\\scott\\Downloads\\Repositories\\agent-study\\etl\\amd_teams2_3x3v_000\\amd_teams2_3x3v_000.etl')

    # Test export_process_details tool
    # export_process_details()
