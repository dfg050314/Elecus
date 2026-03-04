# -*- coding: utf-8 -*-
from pyrevit import revit, forms
from Autodesk.Revit.DB import (
    BuiltInCategory, FilteredElementCollector
)

from ecs_route import compute_cable_route_length_m

doc = revit.doc


def get_param_text(elem, pname):
    p = elem.LookupParameter(pname)
    if not p or not p.HasValue:
        return ""
    try:
        s = p.AsString()
        if s:
            return s
    except:
        pass
    try:
        vs = p.AsValueString()
        if vs:
            return vs
    except:
        pass
    return ""


# ---------------- UI: equipment selection ----------------
equip = []
for e in FilteredElementCollector(doc)\
        .OfCategory(BuiltInCategory.OST_ElectricalEquipment)\
        .WhereElementIsNotElementType():
    pn = get_param_text(e, "Panel Name")
    if pn:
        equip.append(("{} | id:{}".format(pn, e.Id.IntegerValue), e))

if not equip:
    forms.alert("No Electrical Equipment found with a non-empty 'Panel Name'.",
                title="Cable Length")
    raise SystemExit

equip.sort(key=lambda x: x[0].lower())
items = [x[0] for x in equip]
label_to_elem = {x[0]: x[1] for x in equip}

up_label = forms.SelectFromList.show(items,
                                     title="Select Upstream Equipment",
                                     multiselect=False)
if not up_label:
    raise SystemExit
up_elem = label_to_elem[up_label]

down_items = [i for i in items if i != up_label]
down_label = forms.SelectFromList.show(down_items,
                                       title="Select Downstream Equipment",
                                       multiselect=False)
if not down_label:
    raise SystemExit
down_elem = label_to_elem[down_label]

# ---------------- Route length computation ----------------
try:
    length_m = compute_cable_route_length_m(doc, up_elem, down_elem)
    forms.alert(
        "Upstream equipment:\n{}\n\nDownstream equipment:\n{}\n\n"
        "Route length (with elbow arcs):\n{:.2f} m".format(
            up_label, down_label, length_m
        ),
        title="Cable Length"
    )
except Exception as ex:
    forms.alert(
        "Cable length could not be computed.\n\nReason:\n{}".format(ex),
        title="Cable Length"
    )
    raise SystemExit