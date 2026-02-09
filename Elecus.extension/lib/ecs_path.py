# -*- coding: utf-8 -*-
"""
Path resolution utilities for Elecus.
"""
import os


def find_extension_root(start_dir):
    """
    Walk up directory tree to find *.extension folder.
    
    Args:
        start_dir: Starting directory path (usually script's __file__ directory)
    
    Returns:
        Path to .extension folder, or None if not found
    """
    current = start_dir
    while True:
        if os.path.basename(current).lower().endswith(".extension"):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def get_data_dir(extension_root):
    """
    Get the _data directory path.
    
    Args:
        extension_root: Path to .extension folder
    
    Returns:
        Path to _data folder
    """
    return os.path.join(extension_root, "_data")


def get_csa_dir(extension_root):
    """
    Get the CSA_C22_1-24 directory path.
    
    Args:
        extension_root: Path to .extension folder
    
    Returns:
        Path to CSA_C22_1-24 folder
    """
    return os.path.join(extension_root, "_data", "CSA_C22_1-24")


def ensure_directory_exists(path):
    """
    Create directory if it doesn't exist.
    
    Args:
        path: Directory path to create
    
    Returns:
        True if directory exists or was created
    """
    if not os.path.isdir(path):
        os.makedirs(path)
    return os.path.isdir(path)


def file_exists(path):
    """
    Check if file exists.
    
    Args:
        path: File path to check
    
    Returns:
        True if file exists
    """
    return os.path.isfile(path)