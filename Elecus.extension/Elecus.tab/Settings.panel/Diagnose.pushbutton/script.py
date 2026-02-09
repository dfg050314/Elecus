# -*- coding: utf-8 -*-
import os
from pyrevit import forms

SCRIPT_DIR = os.path.dirname(__file__)

def find_extension_root(start_dir):
    d = start_dir
    while True:
        if os.path.basename(d).lower().endswith(".extension"):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent

EXT_DIR = find_extension_root(SCRIPT_DIR)
DATA_DIR = os.path.join(EXT_DIR, "_data")
CSA_DIR = os.path.join(DATA_DIR, "CSA_C22_1-24")
TABLE_02 = os.path.join(CSA_DIR, "table_02.csv")
TABLE_05A = os.path.join(CSA_DIR, "table_05a.csv")

forms.alert(
    "RUNNING:\n{}\n\nEXT_DIR:\n{}\n\nT02 exists: {}\n{}\n\nT05A exists: {}\n{}".format(
        __file__, EXT_DIR,
        os.path.isfile(TABLE_02), TABLE_02,
        os.path.isfile(TABLE_05A), TABLE_05A
    ),
    title="PRN Settings - Verify"
)