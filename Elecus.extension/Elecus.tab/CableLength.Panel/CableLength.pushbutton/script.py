# -*- coding: utf-8 -*-
from pyrevit import revit, forms
from Autodesk.Revit.DB import (
    BuiltInCategory, FilteredElementCollector, BuiltInParameter,
    LocationPoint, LocationCurve, Domain
)

doc = revit.doc

# ---- tuning (metric) ----
ENDPOINT_TOL_MM = 25.0
SNAP_MM = 5000.0

# elbow detection + sizing
ELBOW_ENDPOINT_RADIUS_FACTOR = 1.3
DEFAULT_BEND_RADIUS_MM = 600.0
BEND_RADIUS_MM_BY_DIA = {21: 300.0, 27: 300.0, 41: 450.0, 53: 600.0, 103: 900.0}

ENDPOINT_TOL_FT = ENDPOINT_TOL_MM / 304.8
SNAP_FT = SNAP_MM / 304.8

def get_param_text(elem, pname):
    p = elem.LookupParameter(pname)
    if not p or not p.HasValue:
        return ""
    try:
        s = p.AsString()
        if s: return s
    except: pass
    try:
        vs = p.AsValueString()
        if vs: return vs
    except: pass
    return ""

def dist(a, b): return a.DistanceTo(b)

def get_loc_point(e):
    loc = e.Location
    if isinstance(loc, LocationPoint):
        return loc.Point
    return None

def get_curve_endpoints(e):
    loc = e.Location
    if isinstance(loc, LocationCurve):
        c = loc.Curve
        return c.GetEndPoint(0), c.GetEndPoint(1)
    return None, None

def bbox_center(e):
    bb = e.get_BoundingBox(None)
    if not bb:
        return None
    return (bb.Min + bb.Max) * 0.5

def add_edge(nodes, adj, a, b, w):
    adj.setdefault(a, []).append((b, w))
    adj.setdefault(b, []).append((a, w))
    nodes.add(a); nodes.add(b)

def dijkstra_noheap(nodes, adj, start_key, end_key):
    INF = 1e100
    distmap = {k: INF for k in nodes}
    distmap[start_key] = 0.0
    visited = set()
    while True:
        u = None
        best = INF
        for k, d in distmap.items():
            if k not in visited and d < best:
                best = d
                u = k
        if u is None:
            return None
        if u == end_key:
            return distmap[u]
        visited.add(u)
        for v, w in adj.get(u, []):
            nd = distmap[u] + float(w)
            if nd < distmap.get(v, INF):
                distmap[v] = nd

def get_best_electrical_connector_point(e, node_xyz_list):
    lp = get_loc_point(e)
    try:
        mep = e.MEPModel
        if not mep: return lp
        cm = mep.ConnectorManager
        if not cm: return lp
        conns_raw = list(cm.Connectors)
    except:
        return lp

    elec = []
    for c in conns_raw:
        if not hasattr(c, "Origin"):
            continue
        try:
            if c.Domain == Domain.DomainElectrical:
                elec.append(c)
        except:
            pass
    if not elec:
        return lp

    best_pt = None
    best_d = 1e100
    for c in elec:
        cp = c.Origin
        for np in node_xyz_list:
            d = cp.DistanceTo(np)
            if d < best_d:
                best_d = d
                best_pt = cp
    return best_pt if best_pt else lp

def get_type_name(elem):
    try:
        t = doc.GetElement(elem.GetTypeId())
        if not t:
            return ""
        p = t.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
        if p and p.HasValue:
            return p.AsString() or ""
    except:
        pass
    return ""

def parse_trade_dia_mm(val_str):
    if not val_str:
        return None
    s = val_str.lower().replace("ø", "").replace("mm", " ").strip()
    digits = ""
    for ch in s:
        if ch.isdigit():
            digits += ch
        elif digits:
            break
    try:
        return int(digits) if digits else None
    except:
        return None

def pt_key(p, prec=6):
    return (round(p.X, prec), round(p.Y, prec), round(p.Z, prec))

def label_components(adj, nodes):
    """Return: comp_id_by_node, comp_size_by_id"""
    comp_id = {}
    comp_size = {}
    cid = 0
    for n in nodes:
        if n in comp_id:
            continue
        # BFS
        stack = [n]
        comp_nodes = []
        while stack:
            u = stack.pop()
            if u in comp_id:
                continue
            comp_id[u] = cid
            comp_nodes.append(u)
            for v, w in adj.get(u, []):
                if v not in comp_id:
                    stack.append(v)
        comp_size[cid] = len(comp_nodes)
        cid += 1
    return comp_id, comp_size

def snap_to_best_component(pt, nodes, comp_id_by_node, comp_size_by_id):
    """Among nodes within SNAP_FT, pick node in largest component; tie-break by distance."""
    best = None
    best_comp_sz = -1
    best_d = 1e100

    for n in nodes:
        d = dist(pt, n)
        if d > SNAP_FT:
            continue
        cid = comp_id_by_node.get(n, None)
        csz = comp_size_by_id.get(cid, 0) if cid is not None else 0

        if (csz > best_comp_sz) or (csz == best_comp_sz and d < best_d):
            best = n
            best_comp_sz = csz
            best_d = d

    if best is None:
        return None, 1e100, None, None

    best_cid = comp_id_by_node.get(best, None)
    return best, best_d, best_cid, best_comp_sz

# ---------------- UI ----------------
equip = []
for e in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_ElectricalEquipment).WhereElementIsNotElementType():
    pn = get_param_text(e, "Panel Name")
    if pn:
        equip.append(("{} | id:{}".format(pn, e.Id.IntegerValue), e))

if not equip:
    forms.alert("No Electrical Equipment found with a non-empty 'Panel Name'.")
    raise SystemExit

equip.sort(key=lambda x: x[0].lower())
items = [x[0] for x in equip]
label_to_elem = {x[0]: x[1] for x in equip}

up_label = forms.SelectFromList.show(items, title="Select Upstream Equipment", multiselect=False)
if not up_label: raise SystemExit
up_elem = label_to_elem[up_label]

down_items = [i for i in items if i != up_label]
down_label = forms.SelectFromList.show(down_items, title="Select Downstream Equipment", multiselect=False)
if not down_label: raise SystemExit
down_elem = label_to_elem[down_label]

# ---------------- build graph (conduits + close endpoints + elbow links) ----------------
conduits = list(FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Conduit).WhereElementIsNotElementType())
if not conduits:
    forms.alert("No conduit elements found.")
    raise SystemExit

endpoints, conduit_edges, endpoint_dia = [], [], {}
for c in conduits:
    a, b = get_curve_endpoints(c)
    if not a or not b:
        continue
    dia_mm = parse_trade_dia_mm(get_param_text(c, "Diameter(Trade Size)"))
    endpoints.append(a); endpoints.append(b)
    endpoint_dia[pt_key(a)] = dia_mm
    endpoint_dia[pt_key(b)] = dia_mm
    conduit_edges.append((a, b, dist(a, b)))

node_map, nodes = {}, set()
for p in endpoints:
    k = pt_key(p)
    if k not in node_map:
        node_map[k] = p
        nodes.add(p)

adj = {}
for a, b, L in conduit_edges:
    na = node_map[pt_key(a)]
    nb = node_map[pt_key(b)]
    add_edge(nodes, adj, na, nb, L)

# close endpoint links (<= 25mm, diameter match)
node_list = list(nodes)
for i in range(len(node_list)):
    pi = node_list[i]
    dpi = endpoint_dia.get(pt_key(pi))
    for j in range(i + 1, len(node_list)):
        pj = node_list[j]
        dpj = endpoint_dia.get(pt_key(pj))
        if dpi is None or dpj is None or dpi != dpj:
            continue
        d = dist(pi, pj)
        if d <= ENDPOINT_TOL_FT:
            add_edge(nodes, adj, pi, pj, d)

# elbow links
fittings = list(FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_ConduitFitting).WhereElementIsNotElementType())
elbow_pts = []
for f in fittings:
    tname = get_type_name(f).lower()
    if "elbow" not in tname:
        continue
    if ("junction" in tname) or ("manhole" in tname):
        continue
    ep = get_loc_point(f) or bbox_center(f)
    if ep:
        elbow_pts.append(ep)

elbow_links = 0
for ep in elbow_pts:
    closest = []
    for p in nodes:
        pdia = endpoint_dia.get(pt_key(p))
        if pdia is None:
            continue
        closest.append((dist(p, ep), pdia))
    closest.sort(key=lambda x: x[0])
    elbow_dia_mm = closest[0][1] if closest else None

    bend_mm = BEND_RADIUS_MM_BY_DIA.get(elbow_dia_mm, DEFAULT_BEND_RADIUS_MM)
    elbow_radius_ft = (bend_mm * ELBOW_ENDPOINT_RADIUS_FACTOR) / 304.8

    near = []
    for p in nodes:
        pdia = endpoint_dia.get(pt_key(p))
        if elbow_dia_mm is not None and pdia != elbow_dia_mm:
            continue
        d = dist(p, ep)
        if d <= elbow_radius_ft:
            near.append((d, p))
    near.sort(key=lambda x: x[0])
    if len(near) < 2:
        continue

    p1, p2 = near[0][1], near[1][1]
    add_edge(nodes, adj, p1, p2, dist(p1, p2))
    elbow_links += 1

# ---------------- component-aware snapping (both ends) ----------------
comp_id_by_node, comp_size_by_id = label_components(adj, nodes)

node_xyz_list = list(nodes)
p_start = get_best_electrical_connector_point(up_elem, node_xyz_list)
p_end = get_best_electrical_connector_point(down_elem, node_xyz_list)

start_node, sd, scid, scsz = snap_to_best_component(p_start, nodes, comp_id_by_node, comp_size_by_id)
end_node, ed, ecid, ecsz = snap_to_best_component(p_end, nodes, comp_id_by_node, comp_size_by_id)

if not start_node or not end_node:
    forms.alert("Could not snap to conduit network.\nStart (m): {:.2f}\nEnd (m): {:.2f}".format(sd * 0.3048, ed * 0.3048))
    raise SystemExit

# solve
start_key = "START"
end_key = "END"
add_edge(nodes, adj, start_key, start_node, dist(p_start, start_node))
add_edge(nodes, adj, end_key, end_node, dist(p_end, end_node))

length_ft = dijkstra_noheap(nodes, adj, start_key, end_key)
if length_ft is None:
    forms.alert(
        "No path found.\n"
        "Start snap component size: {} (dist {:.2f}m)\n"
        "End snap component size: {} (dist {:.2f}m)\n"
        "Elbows detected: {}\nElbow links added: {}".format(
            scsz, sd * 0.3048, ecsz, ed * 0.3048, len(elbow_pts), elbow_links
        ),
        title="Cable Length Debug"
    )
    raise SystemExit

length_m = length_ft * 0.3048
forms.alert(
    "Upstream equipment:\n{}\n\nDownstream equipment:\n{}\n\nRoute length:\n{:.2f} m\n\nElbows detected: {}\nElbow links added: {}".format(
        up_label, down_label, length_m, len(elbow_pts), elbow_links
    ),
    title="Cable Length"
)