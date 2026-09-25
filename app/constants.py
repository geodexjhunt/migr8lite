# ---------- Constants ----------
from anyio import Path


SETTINGS_FILE = Path("settings.json")
SQLSERVER_MAX_IDENTIFIER_LEN = 128
INCREMENT_SUFFIX_RESERVE = 4  # reserve space for _001, _002, etc. when incrementing table names
SANITIZED_BASE_MAX_LEN = SQLSERVER_MAX_IDENTIFIER_LEN - INCREMENT_SUFFIX_RESERVE

DEFAULT_SETTINGS = {
    "database_profiles": [],
    "last_table_exists_choice": "1 - Skip file",
    "operable_filetypes": {
        "csv":   {"type": "Text",     "subtype": None},
        "txt":   {"type": "Text",     "subtype": None},
        "xls":   {"type": "Excel",    "subtype": None},
        "xlsx":  {"type": "Excel",    "subtype": None},
        "mdb":   {"type": "Database", "subtype": "Access"},
        "accdb": {"type": "Database", "subtype": "Access"},
    },
}