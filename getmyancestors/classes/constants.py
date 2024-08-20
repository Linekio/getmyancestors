# getmyancestors constants

# Subject to change: see https://www.familysearch.org/developers/docs/api/tree/Persons_resource
MAX_PERSONS = 200

FACT_TAG_EVENT_TYPE = {
    'BIRT': 'Birth',
    'DEAT': 'Death',
    'BURI': 'Burial',
    'CREM': 'Cremation',
    'NATU': 'Naturalization',
}

FACT_TAGS = {
    "http://gedcomx.org/Birth": "BIRT",
    "http://gedcomx.org/Christening": "CHR",
    "http://gedcomx.org/Death": "DEAT",
    "http://gedcomx.org/Burial": "BURI",
    "http://gedcomx.org/PhysicalDescription": "DSCR",
    "http://gedcomx.org/Occupation": "OCCU",
    "http://gedcomx.org/MilitaryService": "_MILT",
    "http://gedcomx.org/Marriage": "MARR",
    "http://gedcomx.org/Divorce": "DIV",
    "http://gedcomx.org/Annulment": "ANUL",
    "http://gedcomx.org/CommonLawMarriage": "_COML",
    "http://gedcomx.org/BarMitzvah": "BARM",
    "http://gedcomx.org/BatMitzvah": "BASM",
    "http://gedcomx.org/Naturalization": "NATU",
    "http://gedcomx.org/Residence": "RESI",
    "http://gedcomx.org/Religion": "RELI",
    "http://familysearch.org/v1/TitleOfNobility": "TITL",
    "http://gedcomx.org/Cremation": "CREM",
    "http://gedcomx.org/Caste": "CAST",
    "http://gedcomx.org/Nationality": "NATI",
}

FACT_EVEN = {
    "http://gedcomx.org/Stillbirth": "Stillborn",
    "http://familysearch.org/v1/Affiliation": "Affiliation",
    "http://gedcomx.org/Clan": "Clan Name",
    "http://gedcomx.org/NationalId": "National Identification",
    "http://gedcomx.org/Ethnicity": "Race",
    "http://familysearch.org/v1/TribeName": "Tribe Name",
}

ORDINANCES_STATUS = {
    "Ready": "QUALIFIED",
    "Completed": "COMPLETED",
    "Cancelled": "CANCELED",
    "InProgressPrinted": "SUBMITTED",
    "InProgressNotPrinted": "SUBMITTED",
    "NotNeeded": "INFANT",
}

# mergemyancestors constants and functions
def reversed_dict(d):
    return {val: key for key, val in d.items()}


FACT_TYPES = reversed_dict(FACT_TAGS)
ORDINANCES = reversed_dict(ORDINANCES_STATUS)
