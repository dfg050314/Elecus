# -*- coding: utf-8 -*-
"""
Centralized constants and configuration for Elecus.
"""
import os
from ecs_path import find_extension_root, get_data_dir, get_csa_dir

# -------------------------
# Tool Information
# -------------------------
TOOL_NAME = "Elecus"
TOOL_VERSION = "0.1.0"

# -------------------------
# Shared Parameter Names
# -------------------------
PARAM_AMBIENT_TEMP = "ECS_AmbientTemp_C"
PARAM_INSULATION_TEMP = "ECS_InsulationTemp_C"
PARAM_LENGTH_SAFETY_FACTOR = "ECS_LengthSafetyFactor_pct"

# List of all project-level parameters
PROJECT_PARAMS = [
    PARAM_AMBIENT_TEMP,
    PARAM_INSULATION_TEMP,
    PARAM_LENGTH_SAFETY_FACTOR,
]

# -------------------------
# Shared Parameter File
# -------------------------
SHARED_PARAM_FILENAME = "ECS_SharedParameter.txt"
SHARED_PARAM_GROUP = "ECS_Electrical"

# -------------------------
# CSV File Names
# -------------------------
CSV_TABLE_02 = "table_02.csv"
CSV_TABLE_05A = "table_05a.csv"

# -------------------------
# Path Manager Class
# -------------------------
class PathManager:
    """
    Manages all paths for the Elecus extension.
    Initialize once per script with the script's directory.
    """
    
    def __init__(self, script_dir):
        """
        Initialize paths based on script location.
        
        Args:
            script_dir: Directory of the calling script (use os.path.dirname(__file__))
        """
        self.script_dir = script_dir
        self.extension_root = find_extension_root(script_dir)
        
        if self.extension_root:
            self.data_dir = get_data_dir(self.extension_root)
            self.csa_dir = get_csa_dir(self.extension_root)
            self.shared_param_file = os.path.join(self.data_dir, SHARED_PARAM_FILENAME)
            self.table_02_path = os.path.join(self.csa_dir, CSV_TABLE_02)
            self.table_05a_path = os.path.join(self.csa_dir, CSV_TABLE_05A)
        else:
            self.data_dir = None
            self.csa_dir = None
            self.shared_param_file = None
            self.table_02_path = None
            self.table_05a_path = None
    
    def is_valid(self):
        """Check if extension root was found."""
        return self.extension_root is not None
    
    def get_missing_files(self):
        """
        Check for required files and return list of missing ones.
        
        Returns:
            List of missing file descriptions
        """
        missing = []
        
        if not self.is_valid():
            missing.append("Extension root not found")
            return missing
        
        if not os.path.isdir(self.csa_dir):
            missing.append("CSA_C22_1-24 folder")
            return missing
        
        if not os.path.isfile(self.table_02_path):
            missing.append(CSV_TABLE_02)
        
        if not os.path.isfile(self.table_05a_path):
            missing.append(CSV_TABLE_05A)
        
        return missing