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
from tools_etl import check_required_tools, export_ppm_data, export_processes_data, export_process_details
from tools_general import add_numbers, is_even, check_weather

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

# Create a list of tools
tools = [
    add_numbers,
    is_even,
    check_weather
]



def main():
    # Create a big logger heading with title "Agent Study"
    LOGGER.info('-' * 80)
    LOGGER.info('Agent Study')
    LOGGER.info('-' * 80)

    # Load API keys from .env file
    load_dotenv()

    # 

    # Create graph
    graph_builder.add_node('openai_chat_node', openai_chat_node)
    graph_builder.add_node('tools', ToolNode(tools))
    graph_builder.add_edge(START, 'openai_chat_node')
    graph_builder.add_conditional_edges('openai_chat_node', tools_condition, 'tools')
    graph_builder.add_edge('tools', 'openai_chat_node')
    graph = graph_builder.compile()

    # Test graph and log final state
    # test_message = HumanMessage(content='Does my laptop support parsing ETL files?')
    # final_state = graph.invoke({'messages': [test_message]})

    # LOGGER.debug(f'Final state: {final_state}')

    # Test check_required_tools tool
    # check_required_tools()

    # Test export_ppm_data tool
    export_ppm_data('C:\\Users\\scott\\Downloads\\agent_study.etl')

    # Test export_processes_data tool
    # export_processes_data('C:\\Users\\scott\\Downloads\\agent_study.etl')

    # Test export_process_details tool
    # export_process_details()



if __name__ == "__main__":
    main()
