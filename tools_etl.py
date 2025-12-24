
import logging
import shutil
import os
import subprocess
import csv
import glob
import sys
import time
import threading
from tabulate import tabulate
from itertools import cycle
from typing import Annotated
from langchain_core.tools import tool

# Get the logger that was configured in main.py
LOGGER = logging.getLogger(__name__)

class LogSpinner:
    """
    A simple terminal spinner for indicating activity during long-running tasks.
    """
    def __init__(self, message="Working"):
        self.spinner = cycle(['|', '/', '-', '\\'])
        self.message = message
        self.running = False
        self.thread = None

    def spin(self):
        while self.running:
            # Write directly to stdout to bypass logger formatting for the animation
            sys.stdout.write(f"\r{self.message} {next(self.spinner)}   ")
            sys.stdout.flush()
            time.sleep(0.1)
        # Clear the spinner line
        sys.stdout.write("\r" + " " * (len(self.message) + 10) + "\r")
        sys.stdout.flush()

    def __enter__(self):
        self.running = True
        self.thread = threading.Thread(target=self.spin, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.running = False
        if self.thread:
            self.thread.join()


# Create a tool to check if system has all required tools to parse ETL files. This includes the following:
# - wpr.exe
# - wpaexporter.exe
# @tool # Comment out this line for now to disable the tool
def check_required_tools() -> bool:
    """
    This tool checks if system has all required tools to parse ETL files. This includes the following:
    - wpr.exe
    - wpaexporter.exe

    Returns:
        bool: True if all required tools are present, False otherwise
    """
    return _check_wpr() and _check_wpaexporter()


# Define a private function to check if "wpr" executable is present in system's PATH
def _check_wpr() -> bool:
    """
    This private function checks if "wpr" executable is present in system's PATH
    """
    try:
        LOGGER.info("Checking for wpr executable in PATH")
        shutil.which("wpr")
        LOGGER.info("wpr executable found")
        return True
    except Exception as e:
        LOGGER.error(f"Error checking for wpr: {e}")
        return False


# Define a private function to check if wpaexporter.exe exists in any of the common paths
def _check_wpaexporter() -> bool:
    """
    This private function checks if wpaexporter.exe exists in any of the common paths
    """
    common_paths = [
        r"C:\Program Files (x86)\Windows Kits\10\Windows Performance Toolkit",
        r"C:\Program Files (x86)\Windows Kits\11\Windows Performance Toolkit"
    ]

    for path in common_paths:
        LOGGER.info(f"Checking for wpaexporter.exe in folder: {path}")
        if os.path.exists(os.path.join(path, "wpaexporter.exe")):
            LOGGER.info("wpaexporter.exe found")
            return True
    
    LOGGER.error("wpaexporter.exe not found")
    return False


# Create a tool that uses wpaexporter.exe to export PPM settings and their values

# @tool # Comment out this line for now to disable the tool
def export_ppm_data(
    etl_file_path: Annotated[str, 'ETL file path']
) -> list[dict]:
    """
    This tool uses wpaexporter.exe to export:
    - Processor Power Management (PPM) power profiles (https://learn.microsoft.com/en-us/windows-hardware/customize/power-settings/configure-processor-power-management-options#power-profiles)
    - Power type, DC or AC
    - Processor Power Management (PPM) settings and their values

    Args:
        etl_file_path (str): Path to the ETL file

    Returns:
        list[dict]: List of dictionaries containing Processor Power Management (PPM) power profiles, power type, and Processor Power Management (PPM) settings and their values
    """
    profilerundown_col_name_map = {
        'Field 1': 'ProfileName',
        'Field 2': 'ProfileId',
        'Field 3': 'ProfilePriority',
        'Field 4': 'ProfileFlags',
        'Field 5': 'ProfileGuid',
        'Field 6': 'ProfileActiveCount',
        'Field 7': 'ProfileMaxActiveDurationInUs',
        'Field 8': 'ProfileMinActiveDurationInUs',
        'Field 9': 'ProfileTotalActiveDurationInUs'
    }

    profilesettingrundown_col_name_map = {
        'Field 1': 'ProfileId',
        'Field 2': 'SettingName',
        'Field 3': 'SettingType',
        'Field 4': 'SettingClass',
        'Field 5': 'SettingGuid',
        'Field 6': 'SettingValueSize',
        'Field 7': 'SettingValue'
    }

    data = []
    profilerundown_data = []
    profilesettingrundown_data = []

    # Export to .csv file, using "profilerundown" profile
    _export_etl_to_csv(etl_file_path, "profilerundown")

    # Export to .csv file, using "profilesettingrundown" profile
    _export_etl_to_csv(etl_file_path, "profilesettingrundown")

    # Get data from .csv files
    csv_file_path = _get_csv_file_path(os.path.join("wpaexporter_csv", "profilerundown"))
    profilerundown_data.extend(_parse_csv(csv_file_path, col_name_map=profilerundown_col_name_map))
    LOGGER.debug(f"profilerundown_data:\n")
    LOGGER.debug(tabulate(profilerundown_data, headers='keys', tablefmt='grid'))
    
    csv_file_path = _get_csv_file_path(os.path.join("wpaexporter_csv", "profilesettingrundown"))
    profilesettingrundown_data.extend(_parse_csv(csv_file_path, col_name_map=profilesettingrundown_col_name_map))
    LOGGER.debug(f"profilesettingrundown_data:\n")
    LOGGER.debug(tabulate(profilesettingrundown_data, headers='keys', tablefmt='grid'))

    # Join tables on ProfileId
    # Map ProfileId to its data for quick lookup
    LOGGER.info("Joining tables on ProfileId")
    profiles_map = {p.get('ProfileId'): p for p in profilerundown_data}
    
    for setting in profilesettingrundown_data:
        profile_id = setting.get('ProfileId')
        if profile_id in profiles_map:
            # Merge profile info and setting info into a new dictionary
            merged_entry = {**profiles_map[profile_id], **setting}
            data.append(merged_entry)
        else:
            # If no matching profile is found, just keep the setting data
            data.append(setting)

    # Use tabulate to log data in a table format
    LOGGER.debug(f"data:\n")
    LOGGER.debug(tabulate(data, headers='keys', tablefmt='grid'))

    # TODO: Filter out some columns to save tokens
    
    return data


# Define a private function to export ETL file to .csv file, using a specified WPA profile
# Return True if successful, False otherwise
def _export_etl_to_csv(
    etl_file_path: Annotated[str, 'ETL file path'],
    profile_name: Annotated[str, 'Profile name']
) -> bool:
    """
    Use wpaexporter.exe to export ETL file to .csv file, using a specified WPA profile.

    The output folder should have same name as the specified WPA profile.
    
    Args:
        etl_file_path (str): Path to the ETL file
        profile_name (str): Name of the WPA profile

    Returns:
        bool: True if successful, False otherwise
    """

    # Check if profile exists. Profile path should be .\\wpaexporter_profiles\\<profile_name>.wpaProfile
    profile_path = os.path.join("wpaexporter_profiles", f"{profile_name}.wpaProfile")
    if not os.path.exists(profile_path):
        LOGGER.error(f"Profile {profile_path} does not exist")
        return False

    # Check if output folder exists. If not, create it. It should be .\\wpaexporter_csv\\<profile_name>
    output_folder = os.path.join("wpaexporter_csv", profile_name)
    if not os.path.exists(output_folder):
        LOGGER.warning(f"Output folder {output_folder} does not exist. Creating it...")
        os.makedirs(output_folder)

    # Use subprocess to call wpaexporter.exe to export profile rundown to .csv file
    command = [
        "C:\\Program Files (x86)\\Windows Kits\\10\\Windows Performance Toolkit\\wpaexporter.exe",
        "-i",
        etl_file_path,
        "-profile",
        profile_path,
        "-outputfolder",
        output_folder
    ]

    try:
        LOGGER.info(f"Exporting from .etl to .csv (WPA profile: {profile_name})")
        LOGGER.info(f"ETL file path: {etl_file_path}")
        LOGGER.info(f"Profile path: {profile_path}")
        LOGGER.info(f"Output folder: {output_folder}")
        
        # Use simple spinner to indicate activity
        with LogSpinner(f"Exporting WPA profile {profile_name} to .csv ..."):
            result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        LOGGER.info(f"Success!")
        LOGGER.debug(f"Output:\n{result.stdout.decode('utf-8')}")
        # LOGGER.debug(f"Error:\n{result.stderr.decode('utf-8')}")
        return True
    except subprocess.CalledProcessError as e:
        LOGGER.error(f"Error exporting WPA profile {profile_name}: {e.stderr.decode('utf-8')}")
        return False


# Define a private helper to find the first CSV in a folder and parse it
def _get_csv_file_path(folder_path: Annotated[str, '.csv folder path']) -> str:
    """
    Find the first .csv file in the folder and return its path.
    """
    csv_files = glob.glob(os.path.join(folder_path, "*.csv"))
    if not csv_files:
        LOGGER.error(f"No CSV files found in {folder_path}")
        return ""
    
    # Use the first one found
    return csv_files[0]


# Define a private function to parse .csv file and return a list of dictionaries
def _parse_csv(
    csv_file_path: Annotated[str, 'CSV file path'],
    col_name_map: Annotated[dict[str, str], 'Column name mapping'] = None
) -> list[dict]:
    """
    Parse .csv file and return a list of dictionaries.
    Uses 'utf-8-sig' to handle potential Byte Order Mark (BOM) from Windows tools.
    If col_name_map is provided, renames columns in the returned dictionaries.
    """
    
    try:
        with open(csv_file_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            data = list(reader)
            
            if col_name_map:
                mapped_data = []
                for row in data:
                    # Create a new dictionary with mapped keys, keeping original if no mapping exists
                    mapped_row = {col_name_map.get(k, k): v for k, v in row.items()}
                    mapped_data.append(mapped_row)
                return mapped_data
                
            return data
    except Exception as e:
        LOGGER.error(f"Error parsing CSV file {csv_file_path}: {e}")
        return []
