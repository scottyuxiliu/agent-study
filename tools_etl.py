
import logging
import shutil
import os
import subprocess
import csv
import re
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

@tool
def check_required_tools() -> bool:
    """
    This tool checks if system has all required tools to parse ETL files. This includes the following:
    - wpr.exe: Windows Performance Recorder. This tool is used to record Event Log Traces (ETL) files.
    - wpaexporter.exe: Windows Performance Analyzer Exporter. This tool is used to export Event Log Traces (ETL) files to CSV format.
    - etlwatch.exe: ETLWatch. This tool is used to export Event Log Traces (ETL) files to CSV format.

    Returns:
        bool: True if all required tools are present, False otherwise
    """
    # Log success/fail for each tool check. If return value is True, log success. If return value is False, log fail.
    LOGGER.info("Checking for required tools")
    
    check_wpr = _check_wpr()
    if check_wpr:
        LOGGER.info("Check for wpr.exe passed")
    else:
        LOGGER.error("Check for wpr.exe failed")
    
    check_wpaexporter = _check_wpaexporter()
    if check_wpaexporter:
        LOGGER.info("Check for wpaexporter.exe passed")
    else:
        LOGGER.error("Check for wpaexporter.exe failed")
    
    check_etlwatch = _check_etlwatch()
    if check_etlwatch:
        LOGGER.info("Check for etlwatch.exe passed")
    else:
        LOGGER.error("Check for etlwatch.exe failed")

    return check_wpr and check_wpaexporter and check_etlwatch


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


def _get_etlwatch_exe_path() -> str:
    """
    Private helper to find the latest version of ETLWatch.exe in the etlwatch folder.
    Returns the absolute path to the executable if found, otherwise an empty string.
    """
    etlwatch_root = os.path.join(os.getcwd(), "etlwatch")
    if not os.path.exists(etlwatch_root):
        LOGGER.error(f"etlwatch folder not found at {etlwatch_root}")
        return ""
    
    version_folders = [f for f in os.listdir(etlwatch_root) if os.path.isdir(os.path.join(etlwatch_root, f)) and f.startswith("v")]
    if not version_folders:
        LOGGER.error("No version folders found in etlwatch folder")
        return ""
    
    latest_version_folder = max(version_folders, key=lambda x: x[1:])
    etlwatch_exe = os.path.join(etlwatch_root, latest_version_folder, "ETLWatch.exe")
    
    if not os.path.exists(etlwatch_exe):
        LOGGER.error(f"ETLWatch.exe not found at {etlwatch_exe}")
        return ""
    
    return etlwatch_exe


def _check_etlwatch() -> bool:
    """
    This private function checks if ETLWatch.exe exists in the expected location.
    """
    exe_path = _get_etlwatch_exe_path()
    if exe_path:
        LOGGER.info(f"ETLWatch.exe found in {exe_path}")
        return True
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
    _wpaexporter_etl_to_csv(etl_file_path, "profilerundown")

    # Export to .csv file, using "profilesettingrundown" profile
    _wpaexporter_etl_to_csv(etl_file_path, "profilesettingrundown")

    # Get data from .csv files
    csv_file_path = _get_csv_file_path(os.path.join("wpaexporter_csv", "profilerundown"))
    profilerundown_data.extend(_parse_single_table_csv(csv_file_path, group_by=None, col_name_map=profilerundown_col_name_map))
    LOGGER.debug(f"profilerundown_data:\n")
    LOGGER.debug(tabulate(profilerundown_data, headers='keys', tablefmt='grid'))
    
    csv_file_path = _get_csv_file_path(os.path.join("wpaexporter_csv", "profilesettingrundown"))
    profilesettingrundown_data.extend(_parse_single_table_csv(csv_file_path, group_by=None, col_name_map=profilesettingrundown_col_name_map))
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

    # Filter out some columns to save tokens
    col_to_remove = [
        "Event Name",
        "Cpu",
        "ThreadId",
        "ProfilePriority",
        "ProfileFlags",
        "ProfileGuid",
        "ProfileActiveCount",
        "ProfileMaxActiveDurationInUs",
        "ProfileMinActiveDurationInUs",
        "ProfileTotalActiveDurationInUs",
        "Count",
        "Time (s)",
        "SettingGuid",
        "SettingValueSize"
    ]

    data = [{k: v for k, v in d.items() if k not in col_to_remove} for d in data]
    LOGGER.debug(f"data after removing columns to save tokens:\n{tabulate(data, headers='keys', tablefmt='grid')}")
    
    return data


# Define a private function to export ETL file to .csv file, using a specified WPA profile
# Return True if successful, False otherwise
def _wpaexporter_etl_to_csv(
    etl_file_path: Annotated[str, 'ETL file path'],
    profile_name: Annotated[str, 'Profile name']
) -> bool:
    """
    Use wpaexporter.exe to export ETL file to .csv file, using a specified WPA profile. Every WPA profile should have its own output folder, and the output folder should have same name as the specified WPA profile.
    
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


def _etlwatch_etl_to_csv(etl_file_path: str) -> bool:
    """
    Use ETLWatch.exe to export process data from an ETL file.
    Moves generated 'Stats.csv' and 'ThreadQosTimeLine.csv' to the 'etlwatch_csv' folder.
    """
    if not os.path.exists(etl_file_path):
        LOGGER.error(f"ETL file not found at: {etl_file_path}")
        return False

    etlwatch_exe = _get_etlwatch_exe_path()

    if not etlwatch_exe:
        return False

    output_folder = os.path.join(os.getcwd(), "etlwatch_csv")
    if not os.path.exists(output_folder):
        LOGGER.info(f"Creating output folder: {output_folder}")
        os.makedirs(output_folder)

    command = [
        etlwatch_exe,
        "-i", etl_file_path,
        "-a", "process"
    ]

    try:
        LOGGER.info(f"Running ETLWatch on: {etl_file_path}")
        with LogSpinner("Running ETLWatch analysis ..."):
            # Set check=False because ETLWatch might exit with an error code even if it generates files successfully
            result = subprocess.run(command, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        if result.returncode != 0:
            LOGGER.warning(f"ETLWatch exited with code {result.returncode}. Checking if files were still generated...")
            LOGGER.debug(f"ETLWatch Stderr: {result.stderr.decode('utf-8')}")

        # Files are generated in the current working directory
        files_to_move = ["Stats.csv", "ThreadQosTimeLine.csv"]
        valid_files = 0
        
        for file_name in files_to_move:
            source = os.path.join(os.getcwd(), file_name)
            # Check if file exists and is not empty
            if os.path.exists(source) and os.path.getsize(source) > 0:
                destination = os.path.join(output_folder, f"ETLWatchReport_{file_name}")
                LOGGER.info(f"Moving {file_name} to {destination}")
                shutil.move(source, destination)
                valid_files += 1
            else:
                LOGGER.warning(f"File {file_name} was either not found or is empty after ETLWatch run.")

        # Return True only if both required files were successfully generated and moved
        if valid_files == len(files_to_move):
            LOGGER.info("ETLWatch analysis completed and files were processed.")
            return True
        else:
            LOGGER.error(f"ETLWatch failed to generate one or more required files. (Found {valid_files}/{len(files_to_move)})")
            return False

    except Exception as e:
        LOGGER.error(f"An error occurred during ETLWatch processing: {e}")
        return False


@tool
def export_processes_data(
    etl_file_path: Annotated[str, 'ETL file path'],
    table_name: Annotated[str, 'Table name to return: "Clock interrupts", "Process lifetime", "CPU lifetime", or "all". Defaults to "all".'] = "all"
    ) -> list[dict] | tuple[list[dict], list[dict], list[dict]]:
    """
    This function uses ETLWatch to export processes data from ETL file and parse the resulting stats report. It extracts the following tables from the stats report:
    - Clock interrupts table: Shows the number of clock interrupts for each CPU core.
    - Process lifetime table: Shows the lifetime of each process at each Quality of Service (QoS) level. For details on QoS levels, see https://learn.microsoft.com/en-us/windows-hardware/customize/power-settings/configure-processor-power-management-options
    - CPU lifetime table: Shows the lifetime of each CPU at each QoS level. For details on QoS levels, see https://learn.microsoft.com/en-us/windows-hardware/customize/power-settings/configure-processor-power-management-options

    This function might take a while to run if the ETL file is large.

    Args:
        etl_file_path (str): Path to the ETL file to be processed.
        table_name (str): Table name to return: "Clock interrupts", "Process lifetime", "CPU lifetime", or "all". Defaults to "all".

    Returns:
        tuple[list[dict], list[dict], list[dict]] or list[dict]: 
            - If table_name is "all", it returns a tuple of three lists of dictionaries (clock_interrupts, process_lifetime, cpu_lifetime).
            - Otherwise, it returns only the requested list of dictionaries.
    """

    col_name_map = {
        "# ClockInterrupts": "Number of Clock Interrupts",
        "High (ms)": "High QoS (ms)",
        "Medium (ms)": "Medium QoS (ms)",
        "Low (ms)": "Low QoS (ms)",
        "Multimedia (ms)": "Multimedia QoS (ms)",
        "Deadline (ms)": "Deadline QoS (ms)",
        "EcoQos (ms)": "Eco QoS (ms)",
        "UtilityQos (ms)": "Utility QoS (ms)"
    }

    # Run ETLWatch to export the data to CSV files
    if not _etlwatch_etl_to_csv(etl_file_path):
        LOGGER.error("Failed to export data from ETL file using ETLWatch.")
        if table_name == "all":
            return [], [], []
        return []

    stats_file = os.path.join("etlwatch_csv", "ETLWatchReport_Stats.csv")
    
    if not os.path.exists(stats_file):
        LOGGER.error(f"Stats file not found: {stats_file}")
        if table_name == "all":
            return [], [], []
        return []

    LOGGER.info(f"Parsing ETLWatch stats report: {stats_file}")

    # data is a dictionary of tables from the stats file. It follows this structure:
    # Key: Table title
    # Value: List of dictionaries, where each dictionary represents a row in the table.
    data = _parse_multi_table_csv(stats_file, col_name_map=col_name_map)
    LOGGER.info(f"Successfully parsed {len(data)} tables from stats report.")

    # Get tables from data
    # titles containing "Clock Interrupts"
    clock_interrupts_table = next((v for k, v in data.items() if "Clock Interrupts" in k), [])
    # titles containing "Process Runtime by QOS"
    process_lifetime_table = next((v for k, v in data.items() if "Process Runtime by QOS" in k), [])
    # titles containing "Logical Processor (LP) Runtime by QOS"
    cpu_lifetime_table = next((v for k, v in data.items() if "Logical Processor (LP) Runtime by QOS" in k), [])

    # Filter/Select which table to return
    requested_table = table_name.lower()
    
    if requested_table == "clock interrupts":
        LOGGER.info(f"Returning Clock interrupts table:\n{tabulate(clock_interrupts_table, headers='keys', tablefmt='grid')}")
        return clock_interrupts_table
    elif requested_table == "process lifetime":
        LOGGER.info(f"Returning Process lifetime table:\n{tabulate(process_lifetime_table, headers='keys', tablefmt='grid')}")
        return process_lifetime_table
    elif requested_table == "cpu lifetime":
        LOGGER.info(f"Returning CPU lifetime table:\n{tabulate(cpu_lifetime_table, headers='keys', tablefmt='grid')}")
        return cpu_lifetime_table
    elif requested_table == "all":
        LOGGER.info(f"Returning all tables.")
        LOGGER.debug(f"Clock interrupts table:\n{tabulate(clock_interrupts_table, headers='keys', tablefmt='grid')}")
        LOGGER.debug(f"Process lifetime table:\n{tabulate(process_lifetime_table, headers='keys', tablefmt='grid')}")
        LOGGER.debug(f"CPU lifetime table:\n{tabulate(cpu_lifetime_table, headers='keys', tablefmt='grid')}")
        return clock_interrupts_table, process_lifetime_table, cpu_lifetime_table
    else:
        LOGGER.warning(f"Unknown table_name '{table_name}'. Defaulting to 'all'.")
        return clock_interrupts_table, process_lifetime_table, cpu_lifetime_table
    

# Create a function that exports process detailed stats data
def export_process_details():
    csv_path = os.path.join("etlwatch_csv", "ETLWatchReport_ThreadQosTimeLine_full.csv")

    summary = _parse_single_table_csv(csv_path, group_by=["Process", "CPU", "QoS level"], col_name_map={"Qos": "QoS level"})

    LOGGER.info(f"Thread QoS timeline summary:\n{tabulate(summary, headers='keys', tablefmt='grid')}")


def _format_setting_value(val: str) -> str:
    """
    Helper function to format setting values from a hex byte sequence to a single hex value.
    Input format: xxxxxxxx yy yy yy yy ...
    - xxxxxxxx: number of bytes (ignored)
    - yy: actual bytes in little-endian order (LSB first)

    Example: "00000004 e8 03 00 00" -> "0x000003e8"
    """
    parts = val.split()
    if len(parts) < 2:
        return val

    # parts[0] is the byte length, parts[1:] are the actual hex bytes
    data_bytes = parts[1:]

    # Special case: if there are 40 bytes (or any long sequence), only look at the first 4 bytes
    # per user request to handle specific PPM setting formats.
    if len(data_bytes) > 4:
        data_bytes = data_bytes[:4]

    # Combine bytes from right to left (most significant byte at the highest index)
    # The input sequence is e.g. [LSB, ..., MSB], so we reverse it to get [MSB, ..., LSB]
    data_bytes.reverse()

    return "0x" + "".join(data_bytes)


def _format_process_name(val: str) -> str:
    """
    Helper function to remove the trailing (PID) part from process values.
    Example: "chrome.exe (1234)" -> "chrome.exe"
    """
    if " (" in val:
        return val.split(" (")[0]
    return val


def _parse_single_table_csv(
    csv_file_path: str,
    group_by: list[str] = ["Process", "CPU", "Qos"],
    col_name_map: dict[str, str] = None
) -> list[dict]:
    """
    Parse a .csv file with a single table (e.g., ETLWatchReport_ThreadQosTimeLine.csv) using csv.DictReader.

    This function supports:
    - Reading large .csv files (e.g., >100MB).
    - Column name mapping.
    - Grouping by specified columns (e.g., ["Process", "CPU", "Qos"]). If col_name_map is provided, it groups by the mapped names provided in col_name_map.
    - If group_by is None, it returns every row without aggregation, still applying PID removal and column mapping.
    - Automatic PID removal for the "Process" column.

    Warning:
    - If group_by equals ["Process", "Qos"], it will produce inaccurate results since multiple CPUs can be assigned to a single process, and summing up the Runtime for all CPUs for a single process will give an inflated value.

    Args:
        csv_file_path (str): Path to the CSV file to parse.
        group_by (list[str], optional): List of column names to group by. If None, no expansion or aggregation is done. Defaults to ["Process", "CPU", "Qos"].
        col_name_map (dict[str, str], optional): Dictionary mapping original column names to target column names. Defaults to None.

    Returns:
        list[dict]: List of dictionaries, where each dictionary represents a row in the table.
    """
    if not os.path.exists(csv_file_path):
        LOGGER.error(f"File {csv_file_path} not found.")
        return []

    # Memory usage warning for large files when grouping is disabled
    if group_by is None:
        file_size_mb = os.path.getsize(csv_file_path) / (1024 * 1024)
        if file_size_mb > 10:  # 10MB threshold
            LOGGER.warning(f"File size is {file_size_mb:.2f}MB. Parsing with group_by=None may consume significant memory.")

    # Give warning when group_by equals ['Process', 'Qos']
    if group_by == ['Process', 'Qos']:
        LOGGER.warning("Grouping by ['Process', 'Qos'] may produce inaccurate results since multiple CPUs can be assigned to a single process, and summing up the Runtime for all CPUs for a single process will give an inflated value.")

    # Create an inverse map to find original names from target names (values in col_name_map)
    # e.g., if {"Qos": "QoS level"}, then inverse becomes {"QoS level": "Qos"}
    inverse_col_map = {v: k for k, v in (col_name_map or {}).items()}

    result = []
    summary = {}
    is_grouping = group_by is not None

    try:
        # Open file with utf-8-sig to handle Windows BOM and process line by line
        with open(csv_file_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                return []
            
            header_map = {fn.strip(): fn for fn in reader.fieldnames}
            
            # Pre-identify columns to extract
            group_keys = []
            if is_grouping:
                for col in group_by:
                    orig_name = inverse_col_map.get(col, col)
                    actual_key = header_map.get(orig_name)
                    if actual_key:
                        group_keys.append((col, actual_key))
                    else:
                        LOGGER.warning(f"Column '{col}' (original: '{orig_name}') not found in CSV headers.")
            else:
                # If not grouping, we map all available columns
                for fn in reader.fieldnames:
                    orig_name = fn.strip()
                    target_name = col_name_map.get(orig_name, orig_name)
                    group_keys.append((target_name, fn))

            # Identify Runtime column if we are grouping
            k_runtime = None
            if is_grouping:
                runtime_orig_name = inverse_col_map.get("Runtime", "Runtime")
                k_runtime = header_map.get(runtime_orig_name)

            row_count = 0
            for row in reader:
                # Build values for this row
                cleaned_values = []
                for target_name, actual_key in group_keys:
                    val = row.get(actual_key).strip()
                    orig_name = inverse_col_map.get(target_name, target_name)

                    # Special case: format Process name (remove PID)
                    if orig_name == "Process":
                        val = _format_process_name(val)

                    # Special case: format SettingValue column
                    if target_name == "SettingValue":
                        val = _format_setting_value(val)

                    cleaned_values.append(val)
                
                if is_grouping:
                    key = tuple(cleaned_values)
                    runtime_str = row.get(k_runtime).strip()
                    try:
                        runtime = float(runtime_str)
                    except ValueError:
                        runtime = 0.0
                    summary[key] = summary.get(key, 0.0) + runtime
                else:
                    # Not grouping: add full row dictionary to result
                    result.append(dict(zip([gk[0] for gk in group_keys], cleaned_values)))

                row_count += 1
                if row_count % 200000 == 0:
                    LOGGER.info(f"Processed {row_count} rows...")

    except Exception as e:
        LOGGER.error(f"Error processing CSV {csv_file_path}: {e}")
        return []

    if is_grouping:
        # Convert aggregated summary back into a result list
        for key_tuple, total_runtime in summary.items():
            row_dict = {col: val for col, val in zip(group_by, key_tuple)}
            row_dict["Total runtime"] = round(total_runtime, 6)
            result.append(row_dict)
        # Sort based on grouping columns
        result.sort(key=lambda x: [str(x.get(col)) for col in group_by])
    
    return result




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



def _parse_multi_table_csv(
    csv_file_path: str,
    col_name_map: dict[str, str] = None
) -> dict[str, list[dict]]:
    """
    Private helper to parse .csv files that contain multiple tables.
    Each table is typically preceded by a title. 
    Returns a dictionary where keys are table titles and values are lists of dictionaries.
    """
    if not os.path.exists(csv_file_path):
        LOGGER.error(f"File {csv_file_path} not found.")
        return {}

    tables = {}
    current_title = "Metadata"
    
    try:
        with open(csv_file_path, "r", encoding="utf-8-sig") as f:
            lines = [line.strip() for line in f.readlines()]
            
        i = 0
        
        while i < len(lines):
            line = lines[i]

            # Skip empty lines
            if not line:
                i += 1
                continue
            
            if "," in line:
                fields = [f.strip() for f in line.split(",")]
                
                if _feels_like_header(fields):
                    # Potential header found
                    rows = []
                    j = i + 1 # j is the starting line number for data rows, immediately after the header row, which is line i

                    # This loop does the following:
                    # - Continuity Check (Line 408): Continues as long as it finds lines that are not empty and contain a comma (,). This ensures it stops as soon as it hits a blank line or a new table title.
                    # - Row Parsing (Line 409): It splits the line at index j into a list of values (row_data).
                    # - Data Integrity (Lines 410-411): It checks if the number of values in the current row matches the number of headers/columns (fields) found at index i. If they match, it "zips" them together into a dictionary (e.g., {'Column1': 'Value1', 'Column2': 'Value2'}) and adds it to the rows list.
                    # - Iteration (Line 412): It increments j to move to the next line in the CSV.
                    while j < len(lines) and lines[j] and "," in lines[j]: 
                        row_data = [d.strip() for d in lines[j].split(",")]
                        if len(row_data) == len(fields):
                            rows.append(dict(zip(fields, row_data)))
                        j += 1
                    
                    if rows:
                        # After a table's rows are parsed but before they are added to the tables dictionary, the code now checks if a col_name_map was provided. If so, it iterates through each row and replaces the keys based on the mapping.
                        if col_name_map:
                            mapped_rows = []
                            for row in rows:
                                mapped_row = {col_name_map.get(k, k): v for k, v in row.items()}
                                mapped_rows.append(mapped_row)
                            rows = mapped_rows

                        title = current_title or "Unnamed Table"
                        unique_title = title
                        count = 1
                        
                        # If the title already exists in the dictionary, it appends a number suffix to make it unique.
                        while unique_title in tables:
                            unique_title = f"{title}_{count}"
                            count += 1
                        
                        # Add the table to the dictionary with the unique title as the key.
                        tables[unique_title] = rows
                        i = j
                        current_title = None
                        continue
                
                # If we get here, it wasn't a header or had no data rows
                # Handle it as metadata if it has 2 fields (Key, Value)
                if len(fields) == 2:
                    if "Metadata" not in tables:
                        tables["Metadata"] = []
                    tables["Metadata"].append({"Property": fields[0], "Value": fields[1]})
                
                i += 1
            else:
                # No comma, this is a title for the next table
                current_title = line
                i += 1
                
    except Exception as e:
        LOGGER.error(f"Error parsing multi-table CSV {csv_file_path}: {e}")

    # Log all tables using tabulate
    for table_name, table_data in tables.items():
        LOGGER.debug(f"Table name: {table_name}")
        LOGGER.debug(f"Table data:\n{tabulate(table_data, headers='keys', tablefmt='grid')}")
    
    return tables


def _feels_like_header(fields: list[str]) -> bool:
    """
    Private helper function to determine if a list of strings is a header row for a table, containing only column names.
    """
    if not fields:
        return False
    
    for val in fields:
        # Skip empty values
        if not val:
            continue

        # If value is strictly numeric or version-like, it's data, not a header
        if re.match(r"^-?[\d.]+(%|ms|us|ns|s|min)?$", val, re.IGNORECASE):
            return False

    # If we get here, it's a header
    return True

