# -*- coding: utf-8 -*-
"""
CSV reading utilities for Elecus.
Compatible with IronPython 2.7.
"""
import csv


def sniff_delimiter(path):
    """
    Detect CSV delimiter (comma or tab).
    
    Args:
        path: Path to CSV file
    
    Returns:
        Delimiter character (',' or '\t')
    """
    with open(path, "r") as f:
        sample = f.read(2048)
    tab_count = sample.count("\t")
    comma_count = sample.count(",")
    return "\t" if (tab_count > 0 and tab_count > comma_count) else ","


def read_csv_header(path):
    """
    Read first row of CSV as header.
    
    Args:
        path: Path to CSV file
    
    Returns:
        List of header strings
    """
    delim = sniff_delimiter(path)
    with open(path, "r") as f:
        reader = csv.reader(f, delimiter=delim)
        return next(reader)


def read_csv_rows(path, skip_header=True):
    """
    Read all rows from CSV.
    
    Args:
        path: Path to CSV file
        skip_header: If True, skip the first row
    
    Returns:
        List of rows (each row is a list of strings)
    """
    delim = sniff_delimiter(path)
    with open(path, "r") as f:
        reader = csv.reader(f, delimiter=delim)
        if skip_header:
            next(reader, None)
        return [row for row in reader if row]


def read_csv_as_dicts(path):
    """
    Read CSV as list of dictionaries (header as keys).
    
    Args:
        path: Path to CSV file
    
    Returns:
        List of dictionaries
    """
    delim = sniff_delimiter(path)
    with open(path, "r") as f:
        reader = csv.DictReader(f, delimiter=delim)
        return list(reader)


def read_csv_column(path, column_index=0, skip_header=True):
    """
    Read a single column from CSV.
    
    Args:
        path: Path to CSV file
        column_index: Index of column to read (0-based)
        skip_header: If True, skip the first row
    
    Returns:
        List of values from the specified column
    """
    rows = read_csv_rows(path, skip_header)
    values = []
    for row in rows:
        if len(row) > column_index:
            val = row[column_index].strip()
            if val:
                values.append(val)
    return values


def parse_temperature_values(string_list):
    """
    Parse temperature strings to integers.
    Handles formats like "30", "30°C", "30 °C", "30C".
    
    Args:
        string_list: List of temperature strings
    
    Returns:
        Sorted list of unique integer temperatures
    """
    result = []
    for s in string_list:
        cleaned = s.strip().lower()
        cleaned = cleaned.replace("°c", "").replace("°", "").replace("c", "").strip()
        try:
            result.append(int(float(cleaned)))
        except (ValueError, TypeError):
            pass
    return sorted(list(set(result)))