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
from dotenv import load_dotenv
from typing import Annotated, TypedDict, Any
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import tools_condition, ToolNode
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from api_openai import get_available_models
from tools_etl import check_adk_directories, check_wpr

# Define AgentState class for LangGraph
# It should have message history
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]


# Create graph_builder using StateGraph
graph_builder = StateGraph(AgentState)


# Create OpenAI chat node using ChatOpenAI
def openai_chat_node(
    state: Annotated[AgentState, 'Old state']
) -> Annotated[dict, 'New state']:
    llm = ChatOpenAI(model='gpt-4o-mini')
    llm_with_tools = llm.bind_tools(tools) # Bind available tools to LLM

    LOGGER.debug(f'state ({type(state)}): {state}')
    LOGGER.debug(f'state messages ({type(state["messages"])}): {state["messages"]}')

    # Add system message to explain why tools are being used. Append it to the end of state messages passed into this function.
    state['messages'].append(SystemMessage(content='Before calling a tool, explain your reasoning in the message content.'))
    
    response = llm_with_tools.invoke(state['messages'])
    
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


# Create a simple function that adds two numbers and returns the result
def add_numbers(
    num1: int,
    num2: int
) -> int:
    """
    Adds two numbers and returns the result
    """
    LOGGER.info(f'Adding {num1} and {num2}')
    return num1 + num2

# Create a simple function that checks if a number is even and returns True or False
def is_even(
    num: int
) -> bool:
    """
    Checks if a number is even and returns True or False
    """
    LOGGER.info(f'Checking if {num} is even')
    return num % 2 == 0

# Create a simple function that takes a city name and checks the weather
def check_weather(
    city: str
) -> str:
    """
    Checks the weather for a given city
    """
    LOGGER.info(f'Checking weather for {city}')
    return f'{city} has sunny weather'

# Create a list of tools
tools = [
    add_numbers,
    is_even,
    check_weather,
    check_adk_directories,
    check_wpr
]



def main():
    # Create a big logger heading with title "Agent Study"
    LOGGER.info('-' * 80)
    LOGGER.info('Agent Study')
    LOGGER.info('-' * 80)

    # Load API keys from .env file
    load_dotenv()

    # Create graph
    graph_builder.add_node('openai_chat_node', openai_chat_node)
    graph_builder.add_node('tools', ToolNode(tools))
    graph_builder.add_edge(START, 'openai_chat_node')
    graph_builder.add_conditional_edges('openai_chat_node', tools_condition, 'tools')
    graph_builder.add_edge('tools', 'openai_chat_node')
    graph = graph_builder.compile()

    # Test graph and log final state
    test_message = HumanMessage(content='Does my laptop support parsing ETL files?')
    final_state = graph.invoke({'messages': [test_message]})

    LOGGER.debug(f'Final state: {final_state}')



if __name__ == "__main__":
    main()
