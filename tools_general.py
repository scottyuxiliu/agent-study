import logging

from langchain_core.tools import tool

# Get the logger that was configured in main.py
LOGGER = logging.getLogger(__name__)

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