# agent-study
This repo is mainly for studying agents

## Tools and Functions in `tools_etl.py`

### `LogSpinner` (Class)
A simple terminal spinner for indicating activity during long-running tasks.

### `@tool check_prerequisites`
This tool checks if system has all required tools to parse ETL files. This includes the following:
- `wpr.exe`: Windows Performance Recorder. This tool is used to record Event Log Traces (ETL) files.
- `wpaexporter.exe`: Windows Performance Analyzer Exporter. This tool is used to export Event Log Traces (ETL) files to CSV format.
- `etlwatch.exe`: ETLWatch. This tool is used to export Event Log Traces (ETL) files to CSV format.

**Returns:**
- `bool`: True if all required tools are present, False otherwise

### `export_ppm_data`
This tool uses wpaexporter.exe to export:
- Processor Power Management (PPM) power profiles (https://learn.microsoft.com/en-us/windows-hardware/customize/power-settings/configure-processor-power-management-options#power-profiles)
- Power type, DC or AC
- Processor Power Management (PPM) settings and their values

**Args:**
- `etl_file_path` (str): Path to the ETL file

**Returns:**
- `list[dict]`: List of dictionaries containing Processor Power Management (PPM) power profiles, power type, and Processor Power Management (PPM) settings and their values

### `@tool export_processes_data`
This function uses ETLWatch to export processes data from ETL file and parse the resulting stats report. It extracts the following tables from the stats report:
- Clock interrupts table: Shows the number of clock interrupts for each CPU core.
- Process lifetime table: Shows the lifetime of each process at each Quality of Service (QoS) level. For details on QoS levels, see https://learn.microsoft.com/en-us/windows-hardware/customize/power-settings/configure-processor-power-management-options
- CPU lifetime table: Shows the lifetime of each CPU at each QoS level. For details on QoS levels, see https://learn.microsoft.com/en-us/windows-hardware/customize/power-settings/configure-processor-power-management-options

This function might take a while to run if the ETL file is large.

**Args:**
- `etl_file_path` (str): Path to the ETL file to be processed.

**Returns:**
- `tuple[list[dict], list[dict], list[dict]]`: A tuple of three lists of dictionaries, where:
    - the first list of dictionaries is the clock interrupts table.
    - the second list of dictionaries is the process lifetime table.
    - and the third list of dictionaries is the CPU lifetime table.

### `export_process_details()`
Exports process detailed stats data (Parses `ETLWatchReport_ThreadQosTimeLine_full.csv`).

### `_check_wpr`
This private function checks if "wpr" executable is present in system's PATH.

### `_check_wpaexporter`
This private function checks if wpaexporter.exe exists in any of the common paths.

### `_get_etlwatch_exe_path`
Private helper to find the latest version of ETLWatch.exe in the etlwatch folder. Returns the absolute path to the executable if found, otherwise an empty string.

### `_check_etlwatch`
This private function checks if ETLWatch.exe exists in the expected location.

### `_wpaexporter_etl_to_csv`
Use `wpaexporter.exe` to export ETL file to .csv file, using a specified WPA profile. Every WPA profile should have its own output folder, and the output folder should have same name as the specified WPA profile.

**Args:**
- `etl_file_path` (str): Path to the ETL file
- `profile_name` (str): Name of the WPA profile

**Returns:**
- `bool`: True if successful, False otherwise

### `_etlwatch_etl_to_csv`
Use `ETLWatch.exe` to export process data from an ETL file. Moves generated 'Stats.csv' and 'ThreadQosTimeLine.csv' to the 'etlwatch_csv' folder.

### `_format_setting_value`
Helper function to format setting values from a hex byte sequence to a single hex value.
Input format: `xxxxxxxx yy yy yy yy ...`
- `xxxxxxxx`: number of bytes (ignored)
- `yy`: actual bytes in little-endian order (LSB first)

Example: `"00000004 e8 03 00 00"` -> `"0x000003e8"`

### `_format_process_name`
Helper function to remove the trailing (PID) part from process values.
Example: `"chrome.exe (1234)"` -> `"chrome.exe"`

### `_parse_single_table_csv`
Parse a .csv file with a single table (e.g., `ETLWatchReport_ThreadQosTimeLine.csv`) using `csv.DictReader`.

This function supports:
- Reading large .csv files (e.g., >100MB).
- Column name mapping.
- Grouping by specified columns (e.g., `["Process", "CPU", "Qos"]`).
- Automatic PID removal for the "Process" column.

**Args:**
- `csv_file_path` (str): Path to the CSV file to parse.
- `group_by` (list[str]): List of column names to group by.
- `col_name_map` (dict[str, str]): Dictionary mapping original column names to target column names.

**Returns:**
- `list[dict]`: List of dictionaries, where each dictionary represents a row in the table.

### `_get_csv_file_path`
Find the first .csv file in the folder and return its path.

### `_parse_multi_table_csv`
Private helper to parse .csv files that contain multiple tables. Each table is typically preceded by a title. Returns a dictionary where keys are table titles and values are lists of dictionaries.

### `_feels_like_header`
Private helper function to determine if a list of strings is a header row for a table, containing only column names.
