# -*- coding: utf-8 -*-
"""
Revit element and parameter utilities for Elecus.
"""
from pyrevit import revit, forms, script

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameterGroup,
    ExternalDefinitionCreationOptions,
    SpecTypeId,
)

import ecs_config


# -------------------------
# Parameter Reading
# -------------------------
def get_param_value(element, param_name, default=None):
    """
    Safely retrieve a parameter value from a Revit element.
    
    Args:
        element: Revit element (e.g., ProjectInformation, FamilyInstance)
        param_name: Name of the parameter
        default: Value to return if parameter not found or has no value
    
    Returns:
        Parameter value or default
    """
    try:
        param = element.LookupParameter(param_name)
        if param and param.HasValue:
            storage = param.StorageType.ToString()
            if storage == "Double":
                return param.AsDouble()
            elif storage == "Integer":
                return param.AsInteger()
            elif storage == "String":
                return param.AsString()
            elif storage == "ElementId":
                return param.AsElementId()
    except Exception as e:
        output = script.get_output()
        output.print_md("**Warning:** Could not read parameter `{}`: {}".format(param_name, e))
    return default


def set_param_value(element, param_name, value):
    """
    Safely set a parameter value on a Revit element.
    
    Args:
        element: Revit element
        param_name: Name of the parameter
        value: Value to set
    
    Returns:
        True if successful, False otherwise
    """
    try:
        param = element.LookupParameter(param_name)
        if param and not param.IsReadOnly:
            param.Set(value)
            return True
    except Exception as e:
        output = script.get_output()
        output.print_md("**Warning:** Could not set parameter `{}`: {}".format(param_name, e))
    return False


def require_param_value(element, param_name, tool_name="Elecus"):
    """
    Get parameter value or exit with error message.
    
    Args:
        element: Revit element
        param_name: Name of the parameter
        tool_name: Name to show in error dialog
    
    Returns:
        Parameter value (exits script if not found)
    """
    value = get_param_value(element, param_name)
    if value is None:
        forms.alert(
            "Required parameter '{}' is missing or has no value.\n\n"
            "Please run ECS Settings first.".format(param_name),
            title="{} - Missing Parameter".format(tool_name)
        )
        script.exit()
    return value


# -------------------------
# Project Information Helpers
# -------------------------
def get_project_info():
    """
    Get the ProjectInformation element from current document.
    
    Returns:
        ProjectInformation element
    """
    doc = revit.doc
    return doc.ProjectInformation


def get_project_param(param_name, default=None):
    """
    Get a parameter value from Project Information.
    
    Args:
        param_name: Name of the parameter
        default: Value to return if not found
    
    Returns:
        Parameter value or default
    """
    pi = get_project_info()
    return get_param_value(pi, param_name, default)


def require_project_param(param_name, tool_name="Elecus"):
    """
    Get a required parameter value from Project Information.
    Exits script if parameter is missing.
    
    Args:
        param_name: Name of the parameter
        tool_name: Name to show in error dialog
    
    Returns:
        Parameter value
    """
    pi = get_project_info()
    return require_param_value(pi, param_name, tool_name)


def set_project_param(param_name, value):
    """
    Set a parameter value on Project Information.
    Must be called within a transaction.
    
    Args:
        param_name: Name of the parameter
        value: Value to set
    
    Returns:
        True if successful
    """
    pi = get_project_info()
    return set_param_value(pi, param_name, value)


# -------------------------
# Design Criteria Helpers
# -------------------------
def get_design_criteria():
    """
    Get all ECS design criteria from Project Information.
    
    Returns:
        Dictionary with design criteria values, or None values if not set
    """
    return {
        "ambient_temp_c": get_project_param(ecs_config.PARAM_AMBIENT_TEMP),
        "insulation_temp_c": get_project_param(ecs_config.PARAM_INSULATION_TEMP),
        "length_safety_factor_pct": get_project_param(ecs_config.PARAM_LENGTH_SAFETY_FACTOR),
    }


def require_design_criteria(tool_name="Elecus"):
    """
    Get all ECS design criteria, exit if any are missing.
    
    Args:
        tool_name: Name to show in error dialog
    
    Returns:
        Dictionary with design criteria values
    """
    return {
        "ambient_temp_c": require_project_param(ecs_config.PARAM_AMBIENT_TEMP, tool_name),
        "insulation_temp_c": require_project_param(ecs_config.PARAM_INSULATION_TEMP, tool_name),
        "length_safety_factor_pct": require_project_param(ecs_config.PARAM_LENGTH_SAFETY_FACTOR, tool_name),
    }


# -------------------------
# Shared Parameter Binding
# -------------------------
def create_shared_param_file_if_missing(path):
    """
    Create a minimal shared parameter file if it doesn't exist.
    
    Args:
        path: Path to shared parameter file
    """
    import os
    
    folder = os.path.dirname(path)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    
    if not os.path.isfile(path):
        with open(path, "w") as f:
            f.write("# This is a Revit shared parameter file.\n")
            f.write("# Do not edit manually.\n")
            f.write("*META\tVERSION\tMINVERSION\n")
            f.write("META\t2\t1\n")
            f.write("*GROUP\tID\tNAME\n")
            f.write("GROUP\t1\t{}\n".format(ecs_config.SHARED_PARAM_GROUP))
            f.write("*PARAM\tGUID\tNAME\tDATATYPE\tDATACATEGORY\tGROUP\tVISIBLE\tDESCRIPTION\tUSERMODIFIABLE\tHIDEWHENNOVALUE\n")


def get_projectinfo_categoryset():
    """
    Create a CategorySet containing only ProjectInformation.
    
    Returns:
        CategorySet with ProjectInformation category
    """
    doc = revit.doc
    app = doc.Application
    cats = app.Create.NewCategorySet()
    cats.Insert(doc.Settings.Categories.get_Item(BuiltInCategory.OST_ProjectInformation))
    return cats


def bind_param_to_projectinfo(param_name, shared_param_file_path):
    """
    Bind a shared parameter to Project Information.
    Must be called within a transaction.
    
    Args:
        param_name: Name of the parameter to bind
        shared_param_file_path: Path to shared parameter file
    
    Returns:
        True if successful
    """
    doc = revit.doc
    app = doc.Application
    
    # Save current shared param file path
    prev_spf = app.SharedParametersFilename
    
    try:
        # Create file if needed
        create_shared_param_file_if_missing(shared_param_file_path)
        
        # Set our shared param file
        app.SharedParametersFilename = shared_param_file_path
        
        # Open the file
        spf = app.OpenSharedParameterFile()
        if spf is None:
            raise Exception("Could not open shared parameter file:\n{}".format(shared_param_file_path))
        
        # Find or create group
        group = None
        for g in spf.Groups:
            if g.Name == ecs_config.SHARED_PARAM_GROUP:
                group = g
                break
        if group is None:
            group = spf.Groups.Create(ecs_config.SHARED_PARAM_GROUP)
        
        # Find or create definition
        definition = None
        for d in group.Definitions:
            if d.Name == param_name:
                definition = d
                break
        if definition is None:
            opt = ExternalDefinitionCreationOptions(param_name, SpecTypeId.Number)
            definition = group.Definitions.Create(opt)
        
        # Bind to Project Information
        cats = get_projectinfo_categoryset()
        binding = app.Create.NewInstanceBinding(cats)
        bindings = doc.ParameterBindings
        
        param_group = BuiltInParameterGroup.PG_DATA
        ok = bindings.Insert(definition, binding, param_group)
        if not ok:
            bindings.ReInsert(definition, binding, param_group)
        
        return True
        
    finally:
        # Restore previous shared param file
        app.SharedParametersFilename = prev_spf


def ensure_project_params_exist(shared_param_file_path):
    """
    Ensure all ECS parameters exist in Project Information.
    Creates and binds them if missing.
    Must be called within a transaction.
    
    Args:
        shared_param_file_path: Path to shared parameter file
    
    Returns:
        List of parameter names that were created
    """
    pi = get_project_info()
    created = []
    
    for param_name in ecs_config.PROJECT_PARAMS:
        if not pi.LookupParameter(param_name):
            bind_param_to_projectinfo(param_name, shared_param_file_path)
            created.append(param_name)
    
    return created