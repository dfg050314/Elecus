# -*- coding: utf-8 -*-
from Autodesk.Revit.DB import (
    BuiltInCategory,
    LocationPoint,
    LocationCurve,
    FilteredElementCollector,
    Domain,
    XYZ,
    BuiltInParameter,
)

FT_TO_M = 0.3048
FT_TO_MM = 304.8
MM_TO_FT = 1.0 / 304.8

_BRIDGE_KEYWORDS = ("manhole", "pull box", "junction box")


def _is_xyz(p):
    return hasattr(p, "X") and hasattr(p, "Y") and hasattr(p, "Z")


def _dist(a, b):
    return a.DistanceTo(b)


def _manhattan_ft(p1, p2):
    return abs(p2.X - p1.X) + abs(p2.Y - p1.Y) + abs(p2.Z - p1.Z)


def _get_param_text(elem, pname):
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


def _get_loc_point(e):
    loc = e.Location
    if isinstance(loc, LocationPoint):
        return loc.Point
    return None


def _get_curve_endpoints(e):
    loc = e.Location
    if isinstance(loc, LocationCurve):
        c = loc.Curve
        return c.GetEndPoint(0), c.GetEndPoint(1)
    return None, None


def _bbox_center(e):
    bb = e.get_BoundingBox(None)
    if not bb:
        return None
    mn = bb.Min
    mx = bb.Max
    if not _is_xyz(mn) or not _is_xyz(mx):
        return None
    return (mn + mx) * 0.5


def _parse_trade_dia_mm(val_str):
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


def _pt_key(p, prec=6):
    return (round(p.X, prec), round(p.Y, prec), round(p.Z, prec))


def _add_edge(nodes, adj, a, b, w):
    # Prevent accidental ints from polluting the node set
    if isinstance(a, int) or isinstance(b, int):
        raise Exception("_add_edge received int node")

    adj.setdefault(a, []).append((b, w))
    adj.setdefault(b, []).append((a, w))

    # Only add to nodes set if it's XYZ or the special START/END keys
    if _is_xyz(a) or a in ("START", "END"):
        nodes.add(a)
    if _is_xyz(b) or b in ("START", "END"):
        nodes.add(b)


def _label_components(adj, nodes):
    comp_id = {}
    comp_size = {}
    cid = 0
    for n in nodes:
        if n in comp_id:
            continue
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


def _dijkstra_noheap(nodes, adj, start_key, end_key):
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


# ---------------- Elbow helpers ----------------
def _is_bend_fitting(fitting):
    try:
        p = fitting.LookupParameter("Bend or Fitting")
        if p and p.HasValue:
            v = (p.AsString() or p.AsValueString() or "").strip().lower()
            return v == "bend"
    except:
        pass
    return False


def _get_elbow_arc_len_ft(fitting):
    try:
        p_ang = fitting.LookupParameter("Angle")
        p_rad = fitting.LookupParameter("Bend Radius")
        if not p_ang or not p_rad:
            return None
        if (not p_ang.HasValue) or (not p_rad.HasValue):
            return None
        angle_rad = float(p_ang.AsDouble())   # radians
        radius_ft = float(p_rad.AsDouble())   # feet
        if angle_rad <= 0 or radius_ft <= 0:
            return None
        return angle_rad * radius_ft
    except:
        return None


# ---------------- Equipment connector point ----------------
def _get_best_electrical_connector_point(elem, node_xyz_list):
    lp = _get_loc_point(elem)
    try:
        mep = elem.MEPModel
        if not mep:
            return lp
        cm = mep.ConnectorManager
        if not cm:
            return lp
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


# ---------------- Room / Space helpers ----------------
def _get_active_phase(doc):
    try:
        phase_id = doc.ActiveView.get_Parameter(BuiltInParameter.VIEW_PHASE).AsElementId()
        return doc.GetElement(phase_id)
    except:
        return None


def _get_room_id_at_point(doc, pt):
    try:
        phase = _get_active_phase(doc)
        if phase:
            r = doc.GetRoomAtPoint(pt, phase)
        else:
            r = doc.GetRoomAtPoint(pt)
        if r:
            return r.Id.IntegerValue
    except:
        pass
    return None


def _get_space_id_at_point(doc, pt):
    try:
        phase = _get_active_phase(doc)
        if phase and hasattr(doc, "GetSpaceAtPoint"):
            s = doc.GetSpaceAtPoint(pt, phase)
            if s:
                return s.Id.IntegerValue
        elif hasattr(doc, "GetSpaceAtPoint"):
            s = doc.GetSpaceAtPoint(pt)
            if s:
                return s.Id.IntegerValue
    except:
        pass
    return None


def _same_room_or_space(doc, p1, p2):
    r1 = _get_room_id_at_point(doc, p1)
    r2 = _get_room_id_at_point(doc, p2)
    if r1 is not None and r2 is not None:
        return (r1 == r2)

    s1 = _get_space_id_at_point(doc, p1)
    s2 = _get_space_id_at_point(doc, p2)
    if s1 is not None and s2 is not None:
        return (s1 == s2)

    return None


# ---------------- Bridge fitting helpers ----------------
def _is_bridge_fitting(doc, elem):
    try:
        if not elem.Category:
            return False
        if elem.Category.Id.IntegerValue != int(BuiltInCategory.OST_ConduitFitting):
            return False
    except:
        return False

    name_blob = ""
    try:
        t = doc.GetElement(elem.GetTypeId())
        if t:
            try:
                name_blob += " " + (t.Name or "")
            except:
                pass
            try:
                fam = getattr(t, "Family", None)
                if fam:
                    name_blob += " " + (fam.Name or "")
            except:
                pass
    except:
        pass

    s = (name_blob or "").lower()
    return any(k in s for k in _BRIDGE_KEYWORDS)


def _get_instance_transform(elem):
    try:
        return elem.GetTransform()
    except:
        return None


def _get_local_bbox_extents(elem, T_inv):
    bb = None
    try:
        bb = elem.get_BoundingBox(None)
    except:
        bb = None
    if not bb:
        return None

    mn = bb.Min
    mx = bb.Max
    if not _is_xyz(mn) or not _is_xyz(mx):
        return None

    corners = [
        XYZ(mn.X, mn.Y, mn.Z),
        XYZ(mx.X, mn.Y, mn.Z),
        XYZ(mn.X, mx.Y, mn.Z),
        XYZ(mx.X, mx.Y, mn.Z),
        XYZ(mn.X, mn.Y, mx.Z),
        XYZ(mx.X, mn.Y, mx.Z),
        XYZ(mn.X, mx.Y, mx.Z),
        XYZ(mx.X, mx.Y, mx.Z),
    ]

    xs, ys, zs = [], [], []
    for c in corners:
        lc = T_inv.OfPoint(c)
        xs.append(lc.X)
        ys.append(lc.Y)
        zs.append(lc.Z)

    local_min = XYZ(min(xs), min(ys), min(zs))
    local_max = XYZ(max(xs), max(ys), max(zs))
    return local_min, local_max


def _is_on_local_sidewall(local_pt, local_min, local_max, wall_tol_ft):
    dx = min(abs(local_pt.X - local_min.X), abs(local_max.X - local_pt.X))
    dy = min(abs(local_pt.Y - local_min.Y), abs(local_max.Y - local_pt.Y))
    return (dx <= wall_tol_ft) or (dy <= wall_tol_ft)


def _add_bridge_edges_for_boxes(doc, xyz_nodes, nodes, adj, wall_tol_mm):
    wall_tol_ft = wall_tol_mm * MM_TO_FT

    fittings = list(
        FilteredElementCollector(doc)
        .OfCategory(BuiltInCategory.OST_ConduitFitting)
        .WhereElementIsNotElementType()
    )

    for bf in fittings:
        if not _is_bridge_fitting(doc, bf):
            continue

        T = _get_instance_transform(bf)
        if not T:
            continue
        T_inv = T.Inverse

        ext = _get_local_bbox_extents(bf, T_inv)
        if not ext:
            continue
        local_min, local_max = ext

        ports = []
        for p in xyz_nodes:
            lp = T_inv.OfPoint(p)
            if _is_on_local_sidewall(lp, local_min, local_max, wall_tol_ft):
                ports.append(p)

        if len(ports) < 2:
            continue

        for i in range(len(ports)):
            for j in range(i + 1, len(ports)):
                p1 = ports[i]
                p2 = ports[j]
                w = _manhattan_ft(p1, p2)
                _add_edge(nodes, adj, p1, p2, w)


# ---------------- Room-aware snap ----------------
def _snap_equipment_to_network(doc, equip_pt, xyz_nodes, comp_id_by_node, comp_size_by_id,
                               cap_same_room_ft, cap_diff_or_unknown_ft):
    """
    Return: (best_node_xyz, heal_ft, same_space_flag)
    heal_ft = Manhattan(equip_pt, best_node_xyz)
    """
    best = None
    best_comp_sz = -1
    best_heal = 1e100
    best_same = None

    for n in xyz_nodes:
        same = _same_room_or_space(doc, equip_pt, n)
        cap = cap_same_room_ft if (same is True) else cap_diff_or_unknown_ft

        heal = _manhattan_ft(equip_pt, n)
        if heal > cap:
            continue

        cid = comp_id_by_node.get(n, None)
        csz = comp_size_by_id.get(cid, 0) if cid is not None else 0

        if (csz > best_comp_sz) or (csz == best_comp_sz and heal < best_heal):
            best = n
            best_comp_sz = csz
            best_heal = heal
            best_same = same

    if best is None:
        return None, None, None

    return best, best_heal, best_same


def compute_cable_route_length_m(doc, up_elem, down_elem,
                                 endpoint_tol_mm=25.0,
                                 snap_mm_diff_or_unknown=2500.0,
                                 bridge_wall_tol_mm=150.0):
    """
    Returns:
      (length_m, meta)

    meta fields:
      - heal_start_mm, heal_end_mm
      - start_same_space, end_same_space  (True/False/None)
      - warn (bool)
      - warn_threshold_mm
    """
    ENDPOINT_TOL_FT = endpoint_tol_mm * MM_TO_FT
    CAP_DIFF_FT = snap_mm_diff_or_unknown * MM_TO_FT
    CAP_SAME_FT = 1e30  # infinite

    conduits = list(
        FilteredElementCollector(doc)
        .OfCategory(BuiltInCategory.OST_Conduit)
        .WhereElementIsNotElementType()
    )
    if not conduits:
        raise Exception("No conduit elements found in model.")

    endpoints = []
    conduit_edges = []
    endpoint_dia = {}

    for c in conduits:
        a, b = _get_curve_endpoints(c)
        if not a or not b:
            continue
        dia_mm = _parse_trade_dia_mm(_get_param_text(c, "Diameter(Trade Size)"))
        endpoints.append(a); endpoints.append(b)
        endpoint_dia[_pt_key(a)] = dia_mm
        endpoint_dia[_pt_key(b)] = dia_mm
        conduit_edges.append((a, b, _dist(a, b)))

    node_map, nodes = {}, set()
    for p in endpoints:
        k = _pt_key(p)
        if k not in node_map:
            node_map[k] = p
            nodes.add(p)

    adj = {}
    for a, b, L in conduit_edges:
        na = node_map[_pt_key(a)]
        nb = node_map[_pt_key(b)]
        _add_edge(nodes, adj, na, nb, L)

    xyz_nodes = [p for p in nodes if _is_xyz(p)]

    # Close endpoint tolerance links (small)
    node_list = list(xyz_nodes)
    for i in range(len(node_list)):
        pi = node_list[i]
        dpi = endpoint_dia.get(_pt_key(pi))
        for j in range(i + 1, len(node_list)):
            pj = node_list[j]
            dpj = endpoint_dia.get(_pt_key(pj))
            if dpi is None or dpj is None or dpi != dpj:
                continue
            d = _dist(pi, pj)
            if d <= ENDPOINT_TOL_FT:
                _add_edge(nodes, adj, pi, pj, d)

    # Bridge boxes
    _add_bridge_edges_for_boxes(doc, xyz_nodes, nodes, adj, bridge_wall_tol_mm)

    # Elbow arc edges
    fittings = list(
        FilteredElementCollector(doc)
        .OfCategory(BuiltInCategory.OST_ConduitFitting)
        .WhereElementIsNotElementType()
    )

    for f in fittings:
        if not _is_bend_fitting(f):
            continue
        ep = _get_loc_point(f) or _bbox_center(f)
        if not ep:
            continue

        closest = []
        for p in xyz_nodes:
            pdia = endpoint_dia.get(_pt_key(p))
            if pdia is None:
                continue
            closest.append((_dist(p, ep), pdia, p))
        closest.sort(key=lambda x: x[0])
        if not closest:
            continue

        elbow_dia_mm = closest[0][1]
        if elbow_dia_mm is None:
            continue

        near = []
        for d0, pdia, p in closest:
            if pdia != elbow_dia_mm:
                continue
            near.append((d0, p))
        near.sort(key=lambda x: x[0])
        if len(near) < 2:
            continue

        p1, p2 = near[0][1], near[1][1]
        arc_len_ft = _get_elbow_arc_len_ft(f)
        w = arc_len_ft if arc_len_ft is not None else _dist(p1, p2)
        _add_edge(nodes, adj, p1, p2, w)

    # Components
    comp_id_by_node, comp_size_by_id = _label_components(adj, nodes)

    # Equipment points
    p_start = _get_best_electrical_connector_point(up_elem, xyz_nodes)
    p_end = _get_best_electrical_connector_point(down_elem, xyz_nodes)

    # Room-aware snap (Manhattan heal)
    start_node, heal_start_ft, start_same = _snap_equipment_to_network(
        doc, p_start, xyz_nodes, comp_id_by_node, comp_size_by_id, CAP_SAME_FT, CAP_DIFF_FT
    )
    end_node, heal_end_ft, end_same = _snap_equipment_to_network(
        doc, p_end, xyz_nodes, comp_id_by_node, comp_size_by_id, CAP_SAME_FT, CAP_DIFF_FT
    )

    if not start_node or not end_node:
        raise Exception("Could not snap equipment to conduit network within constraints.")

    # Solve path (heals included only at endpoints)
    start_key = "START"
    end_key = "END"
    _add_edge(nodes, adj, start_key, start_node, heal_start_ft)
    _add_edge(nodes, adj, end_key, end_node, heal_end_ft)

    length_ft = _dijkstra_noheap(nodes, adj, start_key, end_key)
    if length_ft is None:
        raise Exception("No path found in conduit network.")

    # Warning logic (endpoint heals only)
    heal_start_mm = (heal_start_ft or 0.0) * FT_TO_MM
    heal_end_mm = (heal_end_ft or 0.0) * FT_TO_MM

    start_considered = (start_same is not True)
    end_considered = (end_same is not True)

    warn_thresh_mm = 1000.0 if (start_considered and end_considered) else 500.0

    warn = False
    if start_considered and heal_start_mm > warn_thresh_mm:
        warn = True
    if end_considered and heal_end_mm > warn_thresh_mm:
        warn = True

    meta = {
        "heal_start_mm": heal_start_mm,
        "heal_end_mm": heal_end_mm,
        "start_same_space": start_same,
        "end_same_space": end_same,
        "warn": warn,
        "warn_threshold_mm": warn_thresh_mm,
    }

    return length_ft * FT_TO_M, meta