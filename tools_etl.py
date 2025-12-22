
import logging
import shutil
import os

# Get the logger that was configured in main.py
LOGGER = logging.getLogger(__name__)

# Define function to check if "wpr" executable is present in system's PATH
def check_wpr() -> bool:
    """
    As a second step of checking if we can parse ETL, check if the "wpr" executable is present in the system's PATH
    """
    try:
        LOGGER.info("Checking for wpr executable in PATH")
        shutil.which("wpr")
        return True
    except Exception as e:
        LOGGER.error(f"Error checking for wpr: {e}")
        return False

# Define function to check if any of these folders exist, since they are common paths for Windows ADK:
def check_adk_directories() -> bool:
    """
    As a first step of checking if we can parse ETL, check if any of these folders exist, since they are common paths for Windows ADK:
    C:\\Program Files (x86)\\Windows Kits\\10\\Windows Performance Toolkit
    C:\\Program Files (x86)\\Windows Kits\\11\\Windows Performance Toolkit
    """
    common_paths = [
        r"C:\Program Files (x86)\Windows Kits\10\Windows Performance Toolkit",
        r"C:\Program Files (x86)\Windows Kits\11\Windows Performance Toolkit"
    ]

    for path in common_paths:
        LOGGER.info(f"Checking for folder: {path}")
        if os.path.exists(path):
            return True
    
    LOGGER.error("No Windows ADK found")
    return False
