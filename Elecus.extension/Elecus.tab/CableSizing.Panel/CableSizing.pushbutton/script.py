# -*- coding: utf-8 -*-
import clr
from pyrevit import revit, forms
from Autodesk.Revit.DB import (
    BuiltInCategory, FilteredElementCollector, BuiltInParameter, ElementId,
    LocationPoint, LocationCurve, Domain, FamilyInstance
)

# WPF references
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")
clr.AddReference("System.Xml")
from System.Windows import Window
from System.Windows.Markup import XamlReader
from System.IO import StringReader
from System.Xml import XmlReader

doc = revit.doc

PI_SF_PCT = "PRN_LengthSafetyFactor_pct"
P_REF = "PRN_CableReferenceNo"

PT_PANELBOARD  = 14
PT_TRANSFORMER = 15
PT_SWITCHBOARD = 16
PT_OTHERPANEL  = 17
ALLOWED_PARTTYPE_INTS = {PT_PANELBOARD, PT_TRANSFORMER, PT_SWITCHBOARD, PT_OTHERPANEL}

# -------------------------
# Helpers
# -------------------------
def norm(s):
    try:
        return (s or "").replace(u"\u00A0", " ").strip().lower()
    except:
        return ""

def lp_text(elem, pname):
    try:
        p = elem.LookupParameter(pname)
        if not p or not p.HasValue:
            return ""
        return ((p.AsString() or p.AsValueString() or "")).strip()
    except:
        return ""

def parse_float(txt):
    s = (txt or "").strip()
    if not s:
        return None
    s = s.replace(",", ".")
    try:
        return float(s)
    except:
        return None

def get_project_sf_percent():
    """Return numeric percent (e.g. 10.0 for 10%), or 0.0."""
    try:
        pi = doc.ProjectInformation
        p = pi.LookupParameter(PI_SF_PCT)
        if not p or not p.HasValue:
            return 0.0
        vs = (p.AsValueString() or "").strip()
        if vs:
            try:
                return float(vs.replace("%", "").strip())
            except:
                pass
        try:
            return float(p.AsDouble())
        except:
            return 0.0
    except:
        return 0.0

def get_project_sf_multiplier():
    return 1.0 + (get_project_sf_percent() / 100.0)

def get_family_id_int(elem):
    try:
        if isinstance(elem, FamilyInstance):
            sym = elem.Symbol
            fam = sym.Family if sym else None
            if fam:
                return fam.Id.IntegerValue
    except:
        pass
    return elem.Id.IntegerValue

def panel_name_of_elem(elem):
    pn = lp_text(elem, "Panel Name")
    if pn:
        return pn
    pn = lp_text(elem, "Panel")
    if pn:
        return pn
    return "id:{}".format(elem.Id.IntegerValue)

def get_distribution_system_text(equip):
    return lp_text(equip, "Distribution System") or "-"

def upstream_display_for_equipment(e):
    pn = panel_name_of_elem(e)
    ds = get_distribution_system_text(e)
    fid = get_family_id_int(e)
    return u"{} | {} | ID: {}".format(pn, ds, fid)

def downstream_display_for_equipment(e):
    return upstream_display_for_equipment(e)

# --- DCU Voltage from connector parameter named exactly "Voltage" ---
def get_dcu_connector_voltage(fixt):
    """
    Revit 2024: read Voltage from the electrical Connector itself.
    Try these in order:
      1) connector.get_Parameter(...) by matching Definition.Name == "Voltage"
      2) connector.Voltage (property) fallback
    Returns display string (e.g. '230 V') or '' if not found.
    """
    try:
        mep = fixt.MEPModel
        if not mep:
            return ""
        cm = mep.ConnectorManager
        if not cm:
            return ""

        for c in cm.Connectors:
            # only electrical connectors
            try:
                if c.Domain != Domain.DomainElectrical:
                    continue
            except:
                continue

            # 1) parameter on connector (Definition.Name == "Voltage")
            # Connector in Revit exposes a Parameters collection in 2024.
            try:
                params = getattr(c, "Parameters", None)
                if params:
                    for p in params:
                        try:
                            if p and p.Definition and norm(p.Definition.Name) == "voltage" and p.HasValue:
                                s = (p.AsValueString() or p.AsString() or "").strip()
                                if s:
                                    return s
                        except:
                            pass
            except:
                pass

            # 2) fallback to property
            try:
                v = getattr(c, "Voltage", None)
                if v is not None:
                    vf = float(v)
                    if vf > 0:
                        if abs(vf - round(vf)) < 0.01:
                            return "{} V".format(int(round(vf)))
                        return "{:.1f} V".format(vf)
            except:
                pass

    except:
        pass

    return ""

def downstream_display_for_dcu(f):
    pn = panel_name_of_elem(f)
    volt = get_dcu_connector_voltage(f) or "-"
    fid = get_family_id_int(f)
    return u"{} | {} | ID: {}".format(pn, volt, fid)

def get_family_parttype_int(fi):
    try:
        fam = fi.Symbol.Family
        p = fam.get_Parameter(BuiltInParameter.FAMILY_CONTENT_PART_TYPE)
        return int(p.AsInteger()) if p and p.HasValue else None
    except:
        return None

# -------------------------
# Downstream filter (unique by element id)
# -------------------------
def downstream_for_upstream(upstream_panelname):
    up = (upstream_panelname or "").strip()
    res = []
    dbg = {"equip_added": 0, "dcu_added": 0, "dcu_rejected_upstream": 0}

    equip = (FilteredElementCollector(doc)
             .OfCategory(BuiltInCategory.OST_ElectricalEquipment)
             .WhereElementIsNotElementType())

    for e in equip:
        try:
            if norm(lp_text(e, "Supply From")) != norm(up):
                continue
            if get_family_parttype_int(e) in ALLOWED_PARTTYPE_INTS:
                res.append(e)
                dbg["equip_added"] += 1
        except:
            pass

    fixtures = (FilteredElementCollector(doc)
                .OfCategory(BuiltInCategory.OST_ElectricalFixtures)
                .WhereElementIsNotElementType())

    for f in fixtures:
        try:
            panel_param = f.get_Parameter(BuiltInParameter.RBS_ELEC_CIRCUIT_PANEL_PARAM)
            circuit_param = f.get_Parameter(BuiltInParameter.RBS_ELEC_CIRCUIT_NUMBER)

            if not panel_param or not panel_param.HasValue:
                dbg["dcu_rejected_upstream"] += 1
                continue

            panel_name = panel_param.AsString() or panel_param.AsValueString() or ""
            if norm(panel_name) != norm(up):
                dbg["dcu_rejected_upstream"] += 1
                continue

            if not circuit_param or not circuit_param.HasValue:
                continue

            res.append(f)
            dbg["dcu_added"] += 1
        except:
            pass

    by_id = {}
    for e in res:
        by_id[e.Id.IntegerValue] = e
    return list(by_id.values()), dbg

# -------------------------
# Cable length algorithm (unchanged; omitted comments for brevity)
# -------------------------
ENDPOINT_TOL_MM = 25.0
SNAP_MM = 5000.0
ELBOW_ENDPOINT_RADIUS_FACTOR = 1.3
DEFAULT_BEND_RADIUS_MM = 600.0
BEND_RADIUS_MM_BY_DIA = {21: 300.0, 27: 300.0, 41: 450.0, 53: 600.0, 103: 900.0}
ENDPOINT_TOL_FT = ENDPOINT_TOL_MM / 304.8
SNAP_FT = SNAP_MM / 304.8

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

def snap_to_best_component(pt, nodes, comp_id_by_node, comp_size_by_id):
    best = None
    best_comp_sz = -1
    best_d = 1e100
    for n in nodes:
        try:
            d = pt.DistanceTo(n)
        except:
            continue
        if d > SNAP_FT:
            continue
        cid = comp_id_by_node.get(n, None)
        csz = comp_size_by_id.get(cid, 0) if cid is not None else 0
        if (csz > best_comp_sz) or (csz == best_comp_sz and d < best_d):
            best = n
            best_comp_sz = csz
            best_d = d
    return best

def compute_route_length_m(up_elem, down_elem):
    conduits = list(
        FilteredElementCollector(doc)
        .OfCategory(BuiltInCategory.OST_Conduit)
        .WhereElementIsNotElementType()
    )
    if not conduits:
        raise Exception("No conduit elements found.")

    endpoints, conduit_edges, endpoint_dia = [], [], {}
    for c in conduits:
        a, b = get_curve_endpoints(c)
        if not a or not b:
            continue
        dia_mm = parse_trade_dia_mm(lp_text(c, "Diameter(Trade Size)"))
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

    fittings = list(
        FilteredElementCollector(doc)
        .OfCategory(BuiltInCategory.OST_ConduitFitting)
        .WhereElementIsNotElementType()
    )
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
        add_edge(nodes, adj, near[0][1], near[1][1], dist(near[0][1], near[1][1]))

    comp_id_by_node, comp_size_by_id = label_components(adj, nodes)
    node_xyz_list = list(nodes)

    p_start = get_best_electrical_connector_point(up_elem, node_xyz_list)
    p_end = get_best_electrical_connector_point(down_elem, node_xyz_list)

    start_node = snap_to_best_component(p_start, nodes, comp_id_by_node, comp_size_by_id)
    end_node = snap_to_best_component(p_end, nodes, comp_id_by_node, comp_size_by_id)

    if not start_node or not end_node:
        raise Exception("Could not snap to conduit network.")

    add_edge(nodes, adj, "START", start_node, dist(p_start, start_node))
    add_edge(nodes, adj, "END", end_node, dist(p_end, end_node))

    length_ft = dijkstra_noheap(nodes, adj, "START", "END")
    if length_ft is None:
        raise Exception("No path found in conduit network.")
    return length_ft * 0.3048

# -------------------------
# Upstream items
# -------------------------
up_display_to_elemid = {}
for e in (FilteredElementCollector(doc)
          .OfCategory(BuiltInCategory.OST_ElectricalEquipment)
          .WhereElementIsNotElementType()):
    pn = lp_text(e, "Panel Name")
    if not pn:
        continue
    disp = upstream_display_for_equipment(e)
    if disp not in up_display_to_elemid:
        up_display_to_elemid[disp] = e.Id.IntegerValue

upstream_displays = sorted(up_display_to_elemid.keys(), key=lambda x: x.lower())

if not upstream_displays:
    forms.alert("No upstream equipment found with non-empty 'Panel Name'.", title="Create Cable")
    raise SystemExit

# -------------------------
# WPF
# -------------------------
XAML = u"""
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="Create Cable" Height="500" Width="900"
        WindowStartupLocation="CenterScreen" ResizeMode="NoResize">
  <Grid Margin="12">
    <Grid.RowDefinitions>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="*"/>
      <RowDefinition Height="Auto"/>
    </Grid.RowDefinitions>
    <Grid.ColumnDefinitions>
      <ColumnDefinition Width="340"/>
      <ColumnDefinition Width="*"/>
    </Grid.ColumnDefinitions>

    <TextBlock Grid.Row="0" Grid.ColumnSpan="2" FontSize="14" FontWeight="Bold"
               Text="Create Cable" Margin="0,0,0,10"/>

    <TextBlock Grid.Row="1" Grid.Column="0" VerticalAlignment="Center"
               Text="Cable Reference No. (required):" Margin="0,0,8,6"/>
    <TextBox   Grid.Row="1" Grid.Column="1" Name="txtRef" Margin="0,0,0,6"/>

    <TextBlock Grid.Row="2" Grid.Column="0" VerticalAlignment="Center"
               Text="Upstream Panel Name:" Margin="0,0,8,6"/>
    <ComboBox  Grid.Row="2" Grid.Column="1" Name="cmbUpstream" Margin="0,0,0,6"
              IsEditable="True" IsTextSearchEnabled="True"/>

    <TextBlock Grid.Row="3" Grid.Column="0" VerticalAlignment="Center"
               Text="Downstream:" Margin="0,0,8,6"/>
    <ComboBox  Grid.Row="3" Grid.Column="1" Name="cmbDownstream" Margin="0,0,0,6"
              IsEditable="False"/>

    <TextBlock Grid.Row="4" Grid.Column="0" VerticalAlignment="Center"
               Name="lblLen" Text="Cable Length (m, with safety factor):" Margin="0,0,8,6"/>
    <TextBox   Grid.Row="4" Grid.Column="1" Name="txtLen" Margin="0,0,0,6"
               IsReadOnly="True"/>

    <TextBlock Grid.Row="5" Grid.Column="0" VerticalAlignment="Center"
               Text="Length override (m, optional):" Margin="0,0,8,6"/>
    <TextBox   Grid.Row="5" Grid.Column="1" Name="txtOverride" Margin="0,0,0,6"/>

    <TextBlock Grid.Row="6" Grid.ColumnSpan="2" Name="txtInfo" Margin="0,8,0,8"
               FontFamily="Consolas" TextWrapping="Wrap"/>

    <StackPanel Grid.Row="7" Grid.ColumnSpan="2" Orientation="Horizontal" HorizontalAlignment="Right">
      <Button Name="btnCalc" Content="Calculate Length" Width="130" Height="26" Margin="0,0,8,0" Padding="8,2"/>
      <Button Name="btnWriteRef" Content="Write Ref to Downstream" Width="190" Height="26" Margin="0,0,8,0" Padding="8,2"/>
      <Button Name="btnClose" Content="Close" Width="90" Height="26" Padding="8,2"/>
    </StackPanel>
  </Grid>
</Window>
"""

class Win(Window):
    def __init__(self):
        xml_reader = XmlReader.Create(StringReader(XAML))
        w = XamlReader.Load(xml_reader)
        self.Content = w.Content

        self.txtRef = w.FindName("txtRef")
        self.cmbUpstream = w.FindName("cmbUpstream")
        self.cmbDownstream = w.FindName("cmbDownstream")
        self.lblLen = w.FindName("lblLen")
        self.txtLen = w.FindName("txtLen")
        self.txtOverride = w.FindName("txtOverride")
        self.txtInfo = w.FindName("txtInfo")

        self.btnCalc = w.FindName("btnCalc")
        self.btnWriteRef = w.FindName("btnWriteRef")
        self.btnClose = w.FindName("btnClose")

        self.down_label_to_id = {}  # label -> element id

        for disp in upstream_displays:
            self.cmbUpstream.Items.Add(disp)

        self.cmbUpstream.SelectionChanged += self.on_up_changed
        self.cmbDownstream.SelectionChanged += self.on_down_changed
        self.txtOverride.TextChanged += self.on_override_changed

        self.btnCalc.Click += self.on_calc
        self.btnWriteRef.Click += self.on_write_ref
        self.btnClose.Click += self.on_close

        if self.cmbUpstream.Items.Count > 0:
            self.cmbUpstream.SelectedIndex = 0
            self.refresh()

    def selected_upstream_elem(self):
        disp = self.cmbUpstream.SelectedItem
        if not disp:
            return None
        eid = up_display_to_elemid.get(disp)
        return doc.GetElement(ElementId(eid)) if eid else None

    def selected_upstream_panelname(self):
        disp = self.cmbUpstream.SelectedItem or ""
        try:
            return disp.split("|")[0].strip()
        except:
            return disp.strip()

    def selected_downstream_elem(self):
        lbl = self.cmbDownstream.SelectedItem
        if not lbl:
            return None
        eid_int = self.down_label_to_id.get(lbl)
        return doc.GetElement(ElementId(eid_int)) if eid_int else None

    def set_sf_label(self):
        sf_pct = get_project_sf_percent()
        self.lblLen.Text = "Cable Length (m, with safety factor {}%):".format(int(round(sf_pct)))

    def set_length_outputs(self, run_m, source_note=""):
        self.set_sf_label()
        self.txtLen.Text = "{:.2f}{}".format(float(run_m), ("  " + source_note) if source_note else "")

    def refresh(self):
        self.set_sf_label()
        up_panelname = self.selected_upstream_panelname()

        self.cmbDownstream.Items.Clear()
        self.down_label_to_id = {}
        self.txtInfo.Text = ""
        self.txtLen.Text = ""
        self.txtOverride.Text = ""

        elems, dbg = downstream_for_upstream(up_panelname)

        # Build list keyed by unique element id
        pairs = []
        for e in elems:
            eid = e.Id.IntegerValue
            cat_id = e.Category.Id.IntegerValue if e.Category else -1
            if cat_id == int(BuiltInCategory.OST_ElectricalFixtures):
                lbl = downstream_display_for_dcu(e)
            else:
                lbl = downstream_display_for_equipment(e)
            pairs.append((lbl, eid))

        pairs.sort(key=lambda x: x[0].lower())

        for lbl, eid in pairs:
            final_lbl = lbl
            if final_lbl in self.down_label_to_id:
                # ensure unique label text even if same formatting happens
                final_lbl = u"{} (eid:{})".format(lbl, eid)
            self.down_label_to_id[final_lbl] = eid
            self.cmbDownstream.Items.Add(final_lbl)

        if self.cmbDownstream.Items.Count > 0:
            self.cmbDownstream.SelectedIndex = 0

        self.txtInfo.Text = (
            "Selected upstream (panel): {up}\n"
            "Total downstream: {total}\n"
            "Equipment added: {equip_added}\n"
            "DCU added: {dcu_added}\n"
            "DCU rejected (upstream mismatch or missing param): {dcu_rejected_upstream}\n"
        ).format(up=up_panelname, total=len(elems), **dbg)

        self.try_measure_and_fill()

    def try_measure_and_fill(self):
        up_elem = self.selected_upstream_elem()
        dn_elem = self.selected_downstream_elem()
        if not up_elem or not dn_elem:
            return

        sf = get_project_sf_multiplier()
        try:
            base_m = compute_route_length_m(up_elem, dn_elem)
            run_m = base_m * sf
            self.txtOverride.Text = "{:.2f}".format(run_m)
            self.set_length_outputs(run_m, source_note="(measured)")
        except:
            self.txtLen.Text = ""
            self.txtOverride.Text = ""

    def on_up_changed(self, sender, args):
        if self.cmbUpstream.SelectedIndex >= 0:
            self.refresh()

    def on_down_changed(self, sender, args):
        self.txtLen.Text = ""
        self.txtOverride.Text = ""
        self.try_measure_and_fill()

    def on_override_changed(self, sender, args):
        ov = parse_float(self.txtOverride.Text)
        if ov is None or ov <= 0:
            return
        self.set_length_outputs(ov, source_note="(override)")

    def on_calc(self, sender, args):
        ov = parse_float(self.txtOverride.Text)
        if ov is not None and ov > 0:
            self.set_length_outputs(ov, source_note="(override)")
            return
        self.try_measure_and_fill()

    def on_write_ref(self, sender, args):
        ref = (self.txtRef.Text or "").strip()
        if not ref:
            forms.alert("Cable Reference No. is required.", title="Create Cable")
            return

        dn_elem = self.selected_downstream_elem()
        if not dn_elem:
            forms.alert("Select downstream.", title="Create Cable")
            return

        with revit.Transaction("Write Cable Reference to Downstream"):
            p = dn_elem.LookupParameter(P_REF)
            if not p:
                forms.alert("Downstream element has no parameter: {}".format(P_REF), title="Create Cable")
                return
            p.Set(ref)

        forms.alert("Cable Reference saved on downstream element id: {}".format(dn_elem.Id.IntegerValue),
                    title="Create Cable")

    def on_close(self, sender, args):
        self.Close()

Win().ShowDialog()