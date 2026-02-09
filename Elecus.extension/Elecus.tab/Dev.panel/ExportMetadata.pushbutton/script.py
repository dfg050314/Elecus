# -*- coding: utf-8 -*-
"""
Export Metadata - Generate project structure and environment information.
"""
import os
import json
import getpass
import datetime
import platform
from collections import OrderedDict

import clr
clr.AddReference("System")
from System import AppDomain
from System.Diagnostics import FileVersionInfo

from pyrevit import script, revit

doc = revit.doc

# -------------------------
# Configuration
# -------------------------
DATA_DIR_NAME = "_data"
LIB_DIR_NAME = "lib"
OUT_JSON_NAME = "project_metadata.json"
LANGUAGE = "en-US"


# -------------------------
# Utility Functions
# -------------------------
def utc_now_iso():
    """Get current UTC time in ISO format."""
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def iso_from_epoch(epoch_seconds):
    """Convert epoch timestamp to ISO format."""
    return datetime.datetime.utcfromtimestamp(epoch_seconds).replace(microsecond=0).isoformat() + "Z"


def find_extension_root(start_dir):
    """Walk up directory tree to find *.extension folder."""
    p = start_dir
    while True:
        if p.lower().endswith(".extension"):
            return p
        np = os.path.dirname(p)
        if np == p:
            return None
        p = np


# -------------------------
# Metadata Reading
# -------------------------
def get_lib_metadata(lib_dir):
    """
    Read tool metadata from lib/__init__.py.
    
    Returns:
        OrderedDict with tool_name, version, schema_version, author, description
    """
    defaults = OrderedDict([
        ("tool_name", "unknown"),
        ("version", "unknown"),
        ("schema_version", "unknown"),
        ("author", "unknown"),
        ("description", "")
    ])
    
    init_path = os.path.join(lib_dir, "__init__.py")
    if not os.path.isfile(init_path):
        return defaults
    
    # Mapping from __init__.py variable names to output keys
    var_mapping = {
        "__tool_name__": "tool_name",
        "__version__": "version",
        "__schema_version__": "schema_version",
        "__author__": "author",
        "__description__": "description"
    }
    
    try:
        with open(init_path, "r") as f:
            for line in f:
                stripped = line.strip()
                for var_name, key in var_mapping.items():
                    if stripped.startswith(var_name):
                        parts = stripped.split("=", 1)
                        if len(parts) == 2:
                            value = parts[1].strip().strip('"').strip("'")
                            defaults[key] = value
                        break
    except Exception:
        pass
    
    return defaults


# -------------------------
# Scanning Functions
# -------------------------
def scan_extension_buttons(extension_root):
    """Scan for all pushbutton scripts in the extension."""
    buttons = []
    for root, dirs, files in os.walk(extension_root):
        if DATA_DIR_NAME in root.split(os.sep) or LIB_DIR_NAME in root.split(os.sep):
            continue
        if root.lower().endswith(".pushbutton"):
            for f in files:
                if f.lower() == "script.py":
                    script_path = os.path.join(root, f)
                    buttons.append(OrderedDict([
                        ("button_folder", os.path.relpath(root, extension_root).replace("\\", "/")),
                        ("script_path", os.path.relpath(script_path, extension_root).replace("\\", "/"))
                    ]))
                    break
    buttons.sort(key=lambda x: x["script_path"].lower())
    return buttons


def scan_lib_modules(lib_dir):
    """Scan for all Python modules in the lib folder."""
    modules = []
    if not os.path.isdir(lib_dir):
        return modules
    
    for root, dirs, files in os.walk(lib_dir):
        for fn in files:
            if fn.lower().endswith(".py"):
                fp = os.path.join(root, fn)
                st = os.stat(fp)
                module_name = os.path.splitext(fn)[0]
                rel_path = os.path.relpath(fp, lib_dir).replace("\\", "/")
                
                modules.append(OrderedDict([
                    ("module_name", module_name),
                    ("relative_path", rel_path),
                    ("size_bytes", int(st.st_size)),
                    ("modified_utc", iso_from_epoch(st.st_mtime))
                ]))
    
    modules.sort(key=lambda x: x["relative_path"].lower())
    return modules


def list_files_recursive(root_dir):
    """List all files in a directory recursively."""
    files_out = []
    if not os.path.isdir(root_dir):
        return files_out
    
    for root, dirs, files in os.walk(root_dir):
        for fn in files:
            fp = os.path.join(root, fn)
            if not os.path.isfile(fp):
                continue
            st = os.stat(fp)
            files_out.append(OrderedDict([
                ("name", fn),
                ("relative_path", os.path.relpath(fp, root_dir).replace("\\", "/")),
                ("ext", os.path.splitext(fn)[1].lower()),
                ("size_bytes", int(st.st_size)),
                ("modified_utc", iso_from_epoch(st.st_mtime))
            ]))
    files_out.sort(key=lambda x: x["relative_path"].lower())
    return files_out


# -------------------------
# Environment Info Functions
# -------------------------
def get_revit_version_info():
    """Get Revit version information."""
    app = doc.Application
    return OrderedDict([
        ("version_name", getattr(app, "VersionName", "")),
        ("version_number", getattr(app, "VersionNumber", "")),
        ("sub_version_number", getattr(app, "SubVersionNumber", ""))
    ])


def get_file_version(path):
    """Get file version from a DLL or EXE."""
    if not path or not os.path.exists(path):
        return ""
    fvi = FileVersionInfo.GetVersionInfo(path)
    return (fvi.ProductVersion or fvi.FileVersion or "").strip()


def is_year_based_version(ver_str):
    """Check if version string looks like a year."""
    try:
        parts = ver_str.split(".")
        if parts and parts[0].isdigit():
            year = int(parts[0])
            return 2015 <= year <= 2100
    except Exception:
        pass
    return False


def get_pyrevit_info():
    """Get pyRevit version information from loaded assemblies."""
    candidates = []
    for asm in AppDomain.CurrentDomain.GetAssemblies():
        try:
            an = asm.GetName()
            name = (an.Name or "")
            if "pyrevit" not in name.lower():
                continue
            try:
                loc = asm.Location or ""
            except Exception:
                loc = ""
            try:
                av = str(an.Version)
            except Exception:
                av = ""
            fv = get_file_version(loc) if loc else ""
            candidates.append((name, loc, fv, av))
        except Exception:
            pass

    chosen = None
    for name, loc, fv, av in candidates:
        if name.lower() == "pyrevitlabs.pyrevit.runtime.shared":
            chosen = (name, loc, fv, av)
            break
    if not chosen:
        for name, loc, fv, av in candidates:
            v = fv or av or ""
            if v and not is_year_based_version(v):
                chosen = (name, loc, fv, av)
                break
    if not chosen and candidates:
        chosen = candidates[0]

    name, loc, fv, av = chosen if chosen else ("", "", "", "")
    fullv = fv or av or ""
    src = "assembly:{}{}".format(name, (" @ " + loc) if loc else "")

    return OrderedDict([
        ("engine", "IronPython"),
        ("version_full", fullv),
        ("source", src)
    ])


def get_ironpython_info():
    """Get IronPython version information."""
    import sys
    return OrderedDict([
        ("version_full", str(getattr(sys, "version", "") or ""))
    ])


# -------------------------
# Main Execution
# -------------------------
this_script_dir = os.path.dirname(script.get_script_path())
extension_root = find_extension_root(this_script_dir) or this_script_dir

data_dir = os.path.join(extension_root, DATA_DIR_NAME)
lib_dir = os.path.join(extension_root, LIB_DIR_NAME)

if not os.path.exists(data_dir):
    os.makedirs(data_dir)

json_path = os.path.join(data_dir, OUT_JSON_NAME)

# -------------------------
# Get Tool Metadata from lib/__init__.py
# -------------------------
lib_metadata = get_lib_metadata(lib_dir)

# -------------------------
# Build Payload (Ordered)
# -------------------------
extension_name = os.path.basename(extension_root)
timestamp = utc_now_iso()

payload = OrderedDict([
    ("meta", OrderedDict([
        ("tool_name", lib_metadata["tool_name"]),
        ("tool_version", lib_metadata["version"]),
        ("schema_version", lib_metadata["schema_version"]),
        ("author", lib_metadata["author"]),
        ("description", lib_metadata["description"])
    ])),
    ("generated", OrderedDict([
        ("timestamp_utc", timestamp),
        ("user", getpass.getuser()),
        ("machine", platform.node())
    ])),
    ("environment", OrderedDict([
        ("language", LANGUAGE),
        ("revit", get_revit_version_info()),
        ("pyrevit", get_pyrevit_info()),
        ("ironpython", get_ironpython_info())
    ])),
    ("tool_structure", OrderedDict([
        ("extension_root", extension_root),
        ("extension_name", extension_name),
        ("data_folder", data_dir),
        ("data_files", list_files_recursive(data_dir)),
        ("lib_folder", lib_dir),
        ("lib_modules", scan_lib_modules(lib_dir)),
        ("buttons", scan_extension_buttons(extension_root))
    ]))
])

# -------------------------
# Write Output
# -------------------------
with open(json_path, "w") as f:
    json.dump(payload, f, indent=2)

# -------------------------
# Display Results
# -------------------------
output = script.get_output()
output.print_md("**Extension:** `{}`".format(extension_name))
output.print_md("**Generated:** {}".format(timestamp))
output.print_md("**JSON saved to:** `{}`".format(json_path))