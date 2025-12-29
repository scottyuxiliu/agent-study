import logging

# Configure logging:
# Log to console with only INFO and above
# Log to file with DEBUG and above, and file name should be agent_study.log
# Need to show time (without milliseconds), current function, and message, separated by vertical bars
# We use the root logger (no name) so other modules inherit this config
# Note that Chainlit and OpenAI both use the root logger, so be careful when reading the logs
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
from langchain_core.messages import HumanMessage, SystemMessage, AIMessageChunk
from langchain_core.runnables.config import RunnableConfig
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

# Tool node
# Create a list of tools and define the tool node
tools = [
    add_numbers,
    is_even,
    check_weather
]
tool_node = ToolNode(tools)

# LLM node
# Initialize LLM and bind tools to it
llm = ChatOpenAI(model='gpt-4o-mini').bind_tools(tools)

def openai_chat_node(
    state: Annotated[AgentState, 'Old state']
) -> Annotated[dict, 'New state']:
    response = llm.invoke(state['messages'])
    
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

# Build graph
workflow = StateGraph(AgentState)

workflow.add_node('openai_chat_node', openai_chat_node)
workflow.add_node('tools', tool_node)

workflow.add_edge(START, 'openai_chat_node')
workflow.add_conditional_edges('openai_chat_node', tools_condition, 'tools')
workflow.add_edge('tools', 'openai_chat_node')

# Initialize memory
memory = MemorySaver()

# Initialize app
app = workflow.compile(checkpointer=memory)

@cl.on_message
async def main(message: str):
    # Create an empty message to stream into
    answer = cl.Message(content="")
    await answer.send()
    
    # Configure the runnable to associate the conversation with the user's session
    config: RunnableConfig = {'configurable': {'thread_id': cl.context.session.thread_id}}

    # Stream the graph's output
    for msg, _ in app.stream(
        {'messages': [HumanMessage(content=message.content)]},  # Pass the user's message
        config,
        stream_mode='messages',  # Stream individual message chunks
    ):
        # Check if the current streamed item is an AI message chunk
        if isinstance(msg, AIMessageChunk):
            answer.content += msg.content  # type: ignore # Append the content chunk
            await answer.update()  # Update the UI with the appended content