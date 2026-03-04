# -*- coding: utf-8 -*-
"""
ecs_route.py
Cable route length calculation using endpoint graph + Manhattan-like snap
and elbow arc length (Angle × Bend Radius) when available.

Public:
    compute_cable_route_length_m(doc, up_elem, down_elem)
"""

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    LocationPoint,
    LocationCurve,
    FilteredElementCollector,
)
from Autodesk.Revit.DB import Element


# ---------------- Unit constants ----------------
FT_TO_M = 0.3048
MM_TO_FT = 1.0 / 304.8


# ---------------- Basic helpers ----------------
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


def _dist(a, b):
    return a.DistanceTo(b)


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
    return (bb.Min + bb.Max) * 0.5


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


def _label_components(adj, nodes):
    """Return: comp_id_by_node, comp_size_by_id"""
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
    """Return True if fitting instance is a bend (not junction box, etc.)."""
    try:
        p = fitting.LookupParameter("Bend or Fitting")
        if p and p.HasValue:
            v = (p.AsString() or p.AsValueString() or "").strip().lower()
            return v == "bend"
    except:
        pass
    return False


def _get_elbow_arc_len_ft(fitting):
    """
    Return arc length in feet using:
        arc_len_ft = angle_rad * bend_radius_ft

    Uses instance parameters on the fitting instance:
        - "Angle" (stored in radians internally)
        - "Bend Radius" (stored in feet internally)
    """
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


# ---------------- Equipment connector snap ----------------
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


def _snap_to_best_component(pt, nodes, comp_id_by_node, comp_size_by_id, snap_ft):
    """Among nodes within snap_ft, pick node in largest component; tie-break by distance."""
    best = None
    best_comp_sz = -1
    best_d = 1e100

    for n in nodes:
        d = _dist(pt, n)
        if d > snap_ft:
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


# ----------------------------------------------------------------------
# Public entry: compute_cable_route_length_m
# (logic ported from your working CableLength script)
# ----------------------------------------------------------------------
def compute_cable_route_length_m(doc, up_elem, down_elem,
                                 endpoint_tol_mm=25.0,
                                 snap_mm=5000.0):
    """
    Compute cable route length (m) between up_elem and down_elem using:

        - Endpoint graph of conduits
        - Automatic snapping from equipment to nearest endpoint (within snap_mm)
        - Elbow arc length using Angle × Bend Radius

    This mirrors your working CableLength.pushbutton logic, just as a function.
    """
    ENDPOINT_TOL_FT = endpoint_tol_mm / 304.8
    SNAP_FT = snap_mm / 304.8

    # Collect conduits
    conduits = list(
        FilteredElementCollector(doc)
        .OfCategory(BuiltInCategory.OST_Conduit)
        .WhereElementIsNotElementType()
    )
    if not conduits:
        raise Exception("No conduit elements found in model.")

    # Build nodes & edges from conduit endpoints
    endpoints = []
    conduit_edges = []
    endpoint_dia = {}

    for c in conduits:
        a, b = _get_curve_endpoints(c)
        if not a or not b:
            continue
        dia_mm = _parse_trade_dia_mm(_get_param_text(c, "Diameter(Trade Size)"))
        endpoints.append(a)
        endpoints.append(b)
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

    # Close endpoint links (<= endpoint_tol_mm, diameter match)
    node_list = list(nodes)
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

    # Elbow links (using Bend or Fitting + Angle + Bend Radius)
    fittings = list(
        FilteredElementCollector(doc)
        .OfCategory(BuiltInCategory.OST_ConduitFitting)
        .WhereElementIsNotElementType()
    )
    elbow_items = []
    for f in fittings:
        if not _is_bend_fitting(f):
            continue
        ep = _get_loc_point(f) or _bbox_center(f)
        if ep:
            elbow_items.append((f, ep))

    for f, ep in elbow_items:
        # Find two closest endpoints (diameter match)
        closest = []
        for p in nodes:
            pdia = endpoint_dia.get(_pt_key(p))
            if pdia is None:
                continue
            closest.append((_dist(p, ep), pdia))
        closest.sort(key=lambda x: x[0])
        elbow_dia_mm = closest[0][1] if closest else None

        if elbow_dia_mm is None:
            continue

        near = []
        for p in nodes:
            pdia = endpoint_dia.get(_pt_key(p))
            if pdia != elbow_dia_mm:
                continue
            d = _dist(p, ep)
            near.append((d, p))
        near.sort(key=lambda x: x[0])
        if len(near) < 2:
            continue

        p1, p2 = near[0][1], near[1][1]

        # Weight = arc length if available, else chord distance
        arc_len_ft = _get_elbow_arc_len_ft(f)
        w = arc_len_ft if arc_len_ft is not None else _dist(p1, p2)
        _add_edge(nodes, adj, p1, p2, w)

    # Component-aware snapping (both ends)
    comp_id_by_node, comp_size_by_id = _label_components(adj, nodes)
    node_xyz_list = list(nodes)

    p_start = _get_best_electrical_connector_point(up_elem, node_xyz_list)
    p_end = _get_best_electrical_connector_point(down_elem, node_xyz_list)

    start_node, sd, scid, scsz = _snap_to_best_component(
        p_start, nodes, comp_id_by_node, comp_size_by_id, SNAP_FT
    )
    end_node, ed, ecid, ecsz = _snap_to_best_component(
        p_end, nodes, comp_id_by_node, comp_size_by_id, SNAP_FT
    )

    if not start_node or not end_node:
        raise Exception(
            "Could not snap to conduit network.\n"
            "Start (m): {:.2f}\nEnd (m): {:.2f}".format(sd * FT_TO_M, ed * FT_TO_M)
        )

    # Solve with Dijkstra on the graph
    start_key = "START"
    end_key = "END"
    _add_edge(nodes, adj, start_key, start_node, _dist(p_start, start_node))
    _add_edge(nodes, adj, end_key, end_node, _dist(p_end, end_node))

    length_ft = _dijkstra_noheap(nodes, adj, start_key, end_key)
    if length_ft is None:
        raise Exception(
            "No path found in conduit network.\n"
            "Start snap component size: {} (dist {:.2f}m)\n"
            "End snap component size: {} (dist {:.2f}m)".format(
                scsz, sd * FT_TO_M, ecsz, ed * FT_TO_M
            )
        )

    return length_ft * FT_TO_M


def _add_edge(nodes, adj, a, b, w):
    adj.setdefault(a, []).append((b, w))
    adj.setdefault(b, []).append((a, w))
    nodes.add(a)
    nodes.add(b)