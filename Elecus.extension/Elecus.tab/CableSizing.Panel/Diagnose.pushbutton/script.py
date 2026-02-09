# -*- coding: utf-8 -*-

from pyrevit import revit, forms
from Autodesk.Revit.DB import *

doc = revit.doc

# ----------------------------
# Helpers
# ----------------------------
def param_text(elem, bip):
    try:
        p = elem.get_Parameter(bip)
        if p and p.HasValue:
            return p.AsString() or p.AsValueString() or ""
    except:
        pass
    return ""

# ----------------------------
# Collect DCUs
# ----------------------------
dcus = (
    FilteredElementCollector(doc)
    .OfCategory(BuiltInCategory.OST_ElectricalFixtures)
    .WhereElementIsNotElementType()
    .ToElements()
)

lines = []
total = 0
connected = 0

# ----------------------------
# Probe
# ----------------------------
for dcu in dcus:
    total += 1

    panel = param_text(dcu, BuiltInParameter.RBS_ELEC_CIRCUIT_PANEL_PARAM)
    circuit = param_text(dcu, BuiltInParameter.RBS_ELEC_CIRCUIT_NUMBER)

    if not panel and not circuit:
        continue

    connected += 1

    lines.append(
        "DCU ID: {}\n"
        "  Panel: {}\n"
        "  Circuit: {}\n".format(
            dcu.Id.IntegerValue,
            panel or "<EMPTY>",
            circuit or "<EMPTY>"
        )
    )

# ----------------------------
# Report
# ----------------------------
header = (
    "DCU PARAMETER PROBE\n"
    "========================\n\n"
    "Total Electrical Fixtures: {}\n"
    "DCUs with panel/circuit: {}\n\n"
).format(total, connected)

if not lines:
    forms.alert(
        header + "NO DCUs appear to be circuited.",
        title="DCU Probe"
    )
else:
    forms.alert(
        header + "\n".join(lines),
        title="DCU Probe"
    )