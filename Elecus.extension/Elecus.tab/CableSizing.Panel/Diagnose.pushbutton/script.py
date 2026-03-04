# -*- coding: utf-8 -*-
"""
Test script V3 - Check Wiring Settings (Ambient Temperature).
"""
from pyrevit import revit, script

from Autodesk.Revit.DB import *
from Autodesk.Revit.DB.Electrical import *

doc = revit.doc
output = script.get_output()

output.print_md("# Wiring Settings API Test")
output.print_md("---")

try:
    elec_setting = ElectricalSetting.GetElectricalSettings(doc)
    output.print_md("**ElectricalSetting:** ✓ Accessible")
    output.print_md("")
    
    # List all members containing "temp" or "ambient" or "wir"
    members = dir(elec_setting)
    
    output.print_md("## Temperature/Wiring Related Members")
    output.print_md("")
    
    relevant = [m for m in members if any(k in m.lower() for k in ["temp", "ambient", "wir", "volt"])]
    for m in relevant:
        output.print_md("- `{}`".format(m))
        
        # Try to get value
        try:
            val = getattr(elec_setting, m)
            output.print_md("  - Value: `{}`".format(val))
        except:
            output.print_md("  - (method or inaccessible)")
    
    output.print_md("")
    output.print_md("---")
    
    # Try direct access to common properties
    output.print_md("## Direct Property Access Attempts")
    output.print_md("")
    
    test_props = [
        "AmbientTemperature",
        "WiringAmbientTemperature", 
        "Temperature",
        "DefaultAmbientTemperature"
    ]
    
    for prop in test_props:
        try:
            val = getattr(elec_setting, prop)
            output.print_md("- `{}`: {}".format(prop, val))
        except AttributeError:
            output.print_md("- `{}`: Not found".format(prop))
        except Exception as e:
            output.print_md("- `{}`: Error - {}".format(prop, e))

except Exception as e:
    output.print_md("**ERROR:** {}".format(str(e)))
    import traceback
    output.print_md("```")
    output.print_md(traceback.format_exc())
    output.print_md("```")

output.print_md("---")
output.print_md("**Test Complete**")