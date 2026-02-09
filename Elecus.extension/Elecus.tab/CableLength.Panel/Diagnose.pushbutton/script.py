from pyrevit import revit, forms
from Autodesk.Revit.DB import BuiltInCategory, FilteredElementCollector, BuiltInParameter

doc = revit.doc
fittings = list(FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_ConduitFitting).WhereElementIsNotElementType())

lines = []
for f in fittings[:20]:
    try:
        t = doc.GetElement(f.GetTypeId())
        p = t.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM) if t else None
        tname = p.AsString() if p and p.HasValue else "<no type name param>"
        lines.append("id {} => {}".format(f.Id.IntegerValue, tname))
    except Exception as ex:
        lines.append("id {} => ERROR: {}".format(f.Id.IntegerValue, str(ex)))

forms.alert("\n".join(lines), title="ConduitFitting Type Name (param)")