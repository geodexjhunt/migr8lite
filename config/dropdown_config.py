# config/dropdown_config.py
DROPDOWN_LOOKUPS = [
    {
        "schema": "migr8man",
        "table": "objectfieldmapping",
        "column": "targetfieldname",
        "ref_schema": "migr8man",
        "ref_table": "targetfields",
        "ref_column_key": "fieldname",
        "ref_column_desc": "fielddescription",
        "filter": None  # Can add WHERE clause filtering later
    },
    # Add more as needed
       
    {
        "schema": "migr8man",
        "table": "Job",
        "column": "status",
        "ref_schema": "migr8ref",
        "ref_table": "status",
        "ref_column_key": "status",
        "ref_column_desc": "description",
        "filter": None  # Can add WHERE clause filtering later
    },
    {
        "schema": "migr8man",
        "table": "Job",
        "column": "purpose",
        "ref_schema": "migr8ref",
        "ref_table": "purpose",
        "ref_column_key": "purpose",
        "ref_column_desc": "description",
        "filter": None  # Can add WHERE clause filtering later
    },

]