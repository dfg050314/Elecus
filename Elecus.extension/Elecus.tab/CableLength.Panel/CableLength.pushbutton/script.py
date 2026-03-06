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
for e in (FilteredElementCollector(doc)
          .OfCategory(BuiltInCategory.OST_ElectricalEquipment)
          .WhereElementIsNotElementType()):
    pn = get_param_text(e, "Panel Name")
    if pn:
        equip.append(("{} | id:{}".format(pn, e.Id.IntegerValue), e))

if not equip:
    forms.alert(
        "No Electrical Equipment found with a non-empty 'Panel Name'.",
        title="Cable Length"
    )
    raise SystemExit

equip.sort(key=lambda x: x[0].lower())
items = [x[0] for x in equip]
label_to_elem = {x[0]: x[1] for x in equip}

up_label = forms.SelectFromList.show(
    items,
    title="Select Upstream Equipment",
    multiselect=False
)
if not up_label:
    raise SystemExit
up_elem = label_to_elem[up_label]

down_items = [i for i in items if i != up_label]
down_label = forms.SelectFromList.show(
    down_items,
    title="Select Downstream Equipment",
    multiselect=False
)
if not down_label:
    raise SystemExit
down_elem = label_to_elem[down_label]

# ---------------- Route length computation ----------------
try:
    length_m, meta = compute_cable_route_length_m(doc, up_elem, down_elem)

    msg = (
        "Upstream equipment:\n{}\n\n"
        "Downstream equipment:\n{}\n\n"
        "Route length:\n{:.2f} m"
    ).format(up_label, down_label, length_m)

    # Warning shown only when criteria are met
    if meta and meta.get("warn"):
        warn_lines = []
        thr = float(meta.get("warn_threshold_mm", 0.0) or 0.0)

        heal_start_mm = float(meta.get("heal_start_mm", 0.0) or 0.0)
        heal_end_mm = float(meta.get("heal_end_mm", 0.0) or 0.0)

        start_same = meta.get("start_same_space", None)
        end_same = meta.get("end_same_space", None)

        # Only list sides that triggered and are NOT confirmed same-space
        if (start_same is not True) and (heal_start_mm > thr):
            warn_lines.append(u"- Upstream: {} — {:.0f} mm".format(up_label, heal_start_mm))
        if (end_same is not True) and (heal_end_mm > thr):
            warn_lines.append(u"- Downstream: {} — {:.0f} mm".format(down_label, heal_end_mm))

        if warn_lines:
            warn_msg = (
                "Warning: Large offset detected between equipment and raceway endpoint.\n"
                "Please verify raceway continuity near the final connection(s):\n\n"
                "{}"
            ).format("\n".join(warn_lines))

            msg += "\n\n" + warn_msg

    forms.alert(msg, title="Cable Length")

except Exception as ex:
    forms.alert(
        "Cable length could not be computed.\n\nReason:\n{}".format(ex),
        title="Cable Length"
    )
    raise SystemExit