# -*- coding: utf-8 -*-
"""
ECS Settings - Configure Elecus design criteria.
"""
import os
import clr

from pyrevit import revit, forms, script

# -------------------------
# Import Elecus library modules
# -------------------------
from ecs_config import (
    TOOL_NAME,
    PARAM_AMBIENT_TEMP,
    PARAM_INSULATION_TEMP,
    PARAM_LENGTH_SAFETY_FACTOR,
    PathManager,
)
from ecs_csv import read_csv_header, read_csv_column, parse_temperature_values
from ecs_revit import (
    get_project_info,
    get_param_value,
    set_param_value,
    ensure_project_params_exist,
)

# -------------------------
# WPF assemblies
# -------------------------
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")
clr.AddReference("System.Xml")

from System.Windows import Window
from System.Windows.Markup import XamlReader
from System.IO import StringReader
from System.Xml import XmlReader

# -------------------------
# Initialize paths
# -------------------------
SCRIPT_DIR = os.path.dirname(__file__)
paths = PathManager(SCRIPT_DIR)

if not paths.is_valid():
    forms.alert(
        "Could not locate .extension root from:\n{}".format(SCRIPT_DIR),
        title="{} Settings".format(TOOL_NAME)
    )
    script.exit()

# -------------------------
# Check for required files
# -------------------------
missing_files = paths.get_missing_files()
if missing_files:
    forms.alert(
        "Missing required file(s):\n\n- {}\n\nExpected location:\n{}".format(
            "\n- ".join(missing_files),
            paths.csa_dir
        ),
        title="{} Settings".format(TOOL_NAME)
    )
    script.exit()

# -------------------------
# Ensure parameters exist in project
# -------------------------
with revit.Transaction("{} - Install Parameters".format(TOOL_NAME)):
    created_params = ensure_project_params_exist(paths.shared_param_file)

if created_params:
    output = script.get_output()
    output.print_md("**Created parameters:** {}".format(", ".join(created_params)))

# -------------------------
# Read dropdown options from CSV
# -------------------------
header_02 = read_csv_header(paths.table_02_path)
insul_temp_from_table2 = parse_temperature_values(header_02[2:])

header_05a = read_csv_header(paths.table_05a_path)
insul_temp_from_table5a = parse_temperature_values(header_05a[1:])

ambient_vals = read_csv_column(paths.table_05a_path, column_index=0, skip_header=True)
ambient_temp_options = parse_temperature_values(ambient_vals)

insul_temp_options = insul_temp_from_table5a or insul_temp_from_table2

if not ambient_temp_options or not insul_temp_options:
    forms.alert(
        "Could not load dropdown options from CSA CSV files.",
        title="{} Settings".format(TOOL_NAME)
    )
    script.exit()

# -------------------------
# Get existing values from project
# -------------------------
pi = get_project_info()
amb_saved = get_param_value(pi, PARAM_AMBIENT_TEMP)
ins_saved = get_param_value(pi, PARAM_INSULATION_TEMP)
sf_saved = get_param_value(pi, PARAM_LENGTH_SAFETY_FACTOR)


def pick_default(options, existing):
    """Select default value from options based on existing value."""
    try:
        ex = int(round(existing))
        if ex in options:
            return ex
    except (TypeError, ValueError):
        pass
    return options[0]


def format_saved_int(value):
    """Format saved value as integer string."""
    if value is None:
        return "None"
    try:
        return str(int(round(value)))
    except (TypeError, ValueError):
        return "None"


ambient_default = pick_default(ambient_temp_options, amb_saved)
insul_default = pick_default(insul_temp_options, ins_saved)

try:
    sf_default_int = int(round(sf_saved)) if sf_saved is not None else 10
except (TypeError, ValueError):
    sf_default_int = 10
sf_default_str = str(sf_default_int)

amb_saved_txt = format_saved_int(amb_saved)
ins_saved_txt = format_saved_int(ins_saved)
sf_saved_txt = format_saved_int(sf_saved)

# -------------------------
# WPF UI Definition
# -------------------------
XAML = u"""
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="Elecus Settings" Height="320" Width="500"
        WindowStartupLocation="CenterScreen" ResizeMode="NoResize">
  <Grid Margin="12">
    <Grid.RowDefinitions>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="*"/>
    </Grid.RowDefinitions>
    <Grid.ColumnDefinitions>
      <ColumnDefinition Width="220"/>
      <ColumnDefinition Width="*"/>
    </Grid.ColumnDefinitions>

    <TextBlock Grid.Row="0" Grid.ColumnSpan="2" FontSize="14" FontWeight="Bold" 
               Text="Electrical Design Criteria" Margin="0,0,0,8"/>

    <TextBlock Grid.Row="1" Grid.Column="0" VerticalAlignment="Center" 
               Text="Ambient temperature (°C):" Margin="0,0,8,2"/>
    <ComboBox  Grid.Row="1" Grid.Column="1" Name="cmbAmbient" Margin="0,0,0,2"/>
    <TextBlock Grid.Row="2" Grid.Column="1" Name="txtAmbientCurrent" 
               Foreground="Gray" Margin="0,0,0,8"/>

    <TextBlock Grid.Row="3" Grid.Column="0" VerticalAlignment="Center" 
               Text="Insulation temperature (°C):" Margin="0,0,8,2"/>
    <ComboBox  Grid.Row="3" Grid.Column="1" Name="cmbInsulation" Margin="0,0,0,2"/>
    <TextBlock Grid.Row="4" Grid.Column="1" Name="txtInsulationCurrent" 
               Foreground="Gray" Margin="0,0,0,8"/>

    <TextBlock Grid.Row="5" Grid.Column="0" VerticalAlignment="Center" 
               Text="Cable length safety factor (% add-on):" Margin="0,0,8,2"/>
    <TextBox   Grid.Row="5" Grid.Column="1" Name="txtSafety" Margin="0,0,0,2"/>
    <TextBlock Grid.Row="6" Grid.Column="1" Name="txtSafetyCurrent" 
               Foreground="Gray" Margin="0,0,0,8"/>

    <StackPanel Grid.Row="7" Grid.ColumnSpan="2" Orientation="Horizontal" 
                HorizontalAlignment="Right">
      <Button Name="btnSave" Content="Save" Width="90" Margin="0,0,8,0"/>
      <Button Name="btnCancel" Content="Cancel" Width="90"/>
    </StackPanel>
  </Grid>
</Window>
"""


class SettingsWindow(Window):
    """WPF Settings dialog window."""
    
    def __init__(self):
        xml_reader = XmlReader.Create(StringReader(XAML))
        w = XamlReader.Load(xml_reader)

        self.Content = w.Content
        self.Title = w.Title
        self.Height = w.Height
        self.Width = w.Width
        self.WindowStartupLocation = w.WindowStartupLocation
        self.ResizeMode = w.ResizeMode

        # Get UI controls
        self.cmbAmbient = w.FindName("cmbAmbient")
        self.cmbInsulation = w.FindName("cmbInsulation")
        self.txtSafety = w.FindName("txtSafety")
        self.txtAmbientCurrent = w.FindName("txtAmbientCurrent")
        self.txtInsulationCurrent = w.FindName("txtInsulationCurrent")
        self.txtSafetyCurrent = w.FindName("txtSafetyCurrent")
        self.btnSave = w.FindName("btnSave")
        self.btnCancel = w.FindName("btnCancel")

        # Populate dropdowns
        for v in ambient_temp_options:
            self.cmbAmbient.Items.Add(v)
        for v in insul_temp_options:
            self.cmbInsulation.Items.Add(v)

        # Set defaults
        self.cmbAmbient.SelectedItem = ambient_default
        self.cmbInsulation.SelectedItem = insul_default
        self.txtSafety.Text = sf_default_str

        # Show current values
        self.txtAmbientCurrent.Text = "Current: {} °C".format(amb_saved_txt)
        self.txtInsulationCurrent.Text = "Current: {} °C".format(ins_saved_txt)
        self.txtSafetyCurrent.Text = "Current: {} %".format(sf_saved_txt)

        # Wire up events
        self.btnSave.Click += self.on_save
        self.btnCancel.Click += self.on_cancel

        self.result = None

    def on_save(self, sender, args):
        """Handle Save button click."""
        try:
            amb = int(self.cmbAmbient.SelectedItem)
            ins = int(self.cmbInsulation.SelectedItem)
            sf_int = int(self.txtSafety.Text)
        except (TypeError, ValueError):
            forms.alert(
                "Invalid input. Safety factor must be an integer (e.g., 10).",
                title="{} Settings".format(TOOL_NAME)
            )
            return

        if sf_int < 0:
            forms.alert(
                "Safety factor must be >= 0.",
                title="{} Settings".format(TOOL_NAME)
            )
            return

        self.result = (amb, ins, sf_int)
        self.Close()

    def on_cancel(self, sender, args):
        """Handle Cancel button click."""
        self.result = None
        self.Close()


# -------------------------
# Show dialog
# -------------------------
win = SettingsWindow()
win.ShowDialog()

if not win.result:
    script.exit()

ambient_pick, insul_pick, sf_pct_int = win.result

# -------------------------
# Save to Project Information
# -------------------------
with revit.Transaction("{} - Save Settings".format(TOOL_NAME)):
    set_param_value(pi, PARAM_AMBIENT_TEMP, float(ambient_pick))
    set_param_value(pi, PARAM_INSULATION_TEMP, float(insul_pick))
    set_param_value(pi, PARAM_LENGTH_SAFETY_FACTOR, float(sf_pct_int))

# -------------------------
# Confirmation
# -------------------------
length_multiplier = 1.0 + sf_pct_int / 100.0

forms.alert(
    "Saved Elecus Settings:\n\n"
    "Ambient (°C): {}\n"
    "Insulation (°C): {}\n"
    "Safety add-on (%): {}\n"
    "Length multiplier: {:.3f}".format(
        ambient_pick, insul_pick, sf_pct_int, length_multiplier
    ),
    title="{} Settings".format(TOOL_NAME)
)