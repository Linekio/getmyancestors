import sys
import re
import time
import asyncio
import os
from urllib.parse import unquote, unquote_plus
from datetime import datetime
from typing import Set, Dict, List, Tuple, Union, Optional, BinaryIO, Any
# global imports
import babelfish
import geocoder
import requests
import xml.etree.cElementTree as ET
from xml.etree.cElementTree import Element
from requests_cache import CachedSession

# local imports
import getmyancestors
from getmyancestors.classes.constants import (
    MAX_PERSONS,
    FACT_EVEN,
    FACT_TAGS,
    ORDINANCES_STATUS,
)


COUNTY = 'County'
COUNTRY = 'Country'
CITY = 'City'

GEONAME_FEATURE_MAP = {
    'ADM1': COUNTY, #	first-order administrative division	a primary administrative division of a country, such as a state in the United States
    'ADM1H': COUNTY, #  historical first-order administrative division	a former first-order administrative division
    'ADM2': COUNTY, #	second-order administrative division	a subdivision of a first-order administrative division
    'ADM2H': COUNTY, #	historical second-order administrative division	a former second-order administrative division
    'ADM3': COUNTY, #	third-order administrative division	a subdivision of a second-order administrative division
    'ADM3H': COUNTY, #	historical third-order administrative division	a former third-order administrative division
    'ADM4': COUNTY, #	fourth-order administrative division	a subdivision of a third-order administrative division
    'ADM4H': COUNTY, #	historical fourth-order administrative division	a former fourth-order administrative division
    'ADM5': COUNTY, #	fifth-order administrative division	a subdivision of a fourth-order administrative division
    'ADM5H': COUNTY, #	historical fifth-order administrative division	a former fifth-order administrative division
    'ADMD': COUNTY, #	administrative division	an administrative division of a country, undifferentiated as to administrative level
    'ADMDH': COUNTY, #	historical administrative division 	a former administrative division of a political entity, undifferentiated as to administrative level
    # 'LTER': 	leased area	a tract of land leased to another country, usually for military installations
    'PCL': COUNTRY, # political entity	
    'PCLD': COUNTRY, # dependent political entity	
    'PCLF': COUNTRY, # freely associated state	
    'PCLH': COUNTRY, # historical political entity	a former political entity
    'PCLI': COUNTRY, # independent political entity	
    'PCLIX': COUNTRY, # section of independent political entity	
    'PCLS': COUNTRY, # semi-independent political entity

    'PPL': CITY, # populated place	a city, town, village, or other agglomeration of buildings where people live and work
    'PPLA': CITY, # seat of a first-order administrative division	seat of a first-order administrative division (PPLC takes precedence over PPLA)
    'PPLA2': CITY, # seat of a second-order administrative division	
    'PPLA3': CITY, # seat of a third-order administrative division	
    'PPLA4': CITY, # seat of a fourth-order administrative division	
    'PPLA5': CITY, # seat of a fifth-order administrative division	
    'PPLC': CITY, # capital of a political entity	
    'PPLCH': CITY, # historical capital of a political entity	a former capital of a political entity
    'PPLF': CITY, # farm village	a populated place where the population is largely engaged in agricultural activities
    'PPLG': CITY, # seat of government of a political entity	
    'PPLH': CITY, # historical populated place	a populated place that no longer exists
    'PPLL': CITY, # populated locality	an area similar to a locality but with a small group of dwellings or other buildings
    'PPLQ': CITY, # abandoned populated place	
    'PPLR': CITY, # religious populated place	a populated place whose population is largely engaged in religious occupations
    'PPLS': CITY, # populated places	cities, towns, villages, or other agglomerations of buildings where people live and work
    'PPLW': CITY, # destroyed populated place	a village, town or city destroyed by a natural disaster, or by war
    'PPLX': CITY, # section of populated place

}

# getmyancestors classes and functions
def cont(string):
    """parse a GEDCOM line adding CONT and CONT tags if necessary"""
    level = int(string[:1]) + 1
    lines = string.splitlines()
    res = list()
    max_len = 255
    for line in lines:
        c_line = line
        to_conc = list()
        while len(c_line.encode("utf-8")) > max_len:
            index = min(max_len, len(c_line) - 2)
            while (
                len(c_line[:index].encode("utf-8")) > max_len
                or re.search(r"[ \t\v]", c_line[index - 1 : index + 1])
            ) and index > 1:
                index -= 1
            to_conc.append(c_line[:index])
            c_line = c_line[index:]
            max_len = 248
        to_conc.append(c_line)
        res.append(("\n%s CONC " % level).join(to_conc))
        max_len = 248
    return ("\n%s CONT " % level).join(res) + "\n"

class Note:
    """GEDCOM Note class
    :param text: the Note content
    :param tree: a Tree object
    :param num: the GEDCOM identifier
    """

    counter = {}

    def __init__(self, text="", tree=None, num=None, num_prefix=None, note_type=None):
        self._handle = None
        self.note_type = note_type or 'Source Note'
        self.num_prefix = num_prefix
        if num:
            self.num = num
        else:
            Note.counter[num_prefix or 'None'] = Note.counter.get(num_prefix or 'None', 0) + 1
            self.num = Note.counter[num_prefix or 'None']
        print(f'##### Creating Note: {num_prefix}, {self.num}', file=sys.stderr)
        self.text = text.strip()

        if tree:
            tree.notes.append(self)

    @property
    def id(self):
        return f'{self.num_prefix}_{self.num}' if self.num_prefix != None else self.num

    def print(self, file=sys.stdout):
        """print Note in GEDCOM format"""
        print(f'Note: {self.text}', file=sys.stderr)
        file.write(cont("0 @N%s@ NOTE %s" % (self.id, self.text)))

    def link(self, file=sys.stdout, level=1):
        """print the reference in GEDCOM format"""
        print(f'Linking Note: {self.id}', file=sys.stderr)
        file.write("%s NOTE @N%s@\n" % (level, self.id))

    
    @property
    def handle(self):
        if not self._handle:
            self._handle = '_' + os.urandom(10).hex()

        return self._handle

    def printxml(self, parent_element: Element) -> None:
        note_element = ET.SubElement(
            parent_element,
            'note', 
            handle=self.handle,
            # change='1720382308', 
            id=self.id, 
            type='Source Note'
        )
        ET.SubElement(note_element, 'text').text = self.text

class Source:
    """GEDCOM Source class
    :param data: FS Source data
    :param tree: a Tree object
    :param num: the GEDCOM identifier
    """

    counter = 0

    def __init__(self, data=None, tree=None, num=None):
        if num:
            self.num = num
        else:
            Source.counter += 1
            self.num = Source.counter

        self._handle = None

        self.tree = tree
        self.url = self.citation = self.title = self.fid = None
        self.notes = set()
        if data:
            self.fid = data["id"]
            if "about" in data:
                self.url = data["about"].replace(
                    "familysearch.org/platform/memories/memories",
                    "www.familysearch.org/photos/artifacts",
                )
            if "citations" in data:
                self.citation = data["citations"][0]["value"]
            if "titles" in data:
                self.title = data["titles"][0]["value"]
            if "notes" in data:
                notes = [ n['text'] for n in data["notes"] if n["text"] ]
                for idx, n in enumerate(notes):
                    self.notes.add(Note(
                        n,
                        self.tree,
                        num="S%s-%s" % (self.id, idx),
                        note_type='Source Note'
                    ))
            self.modified = data['attribution']['modified']

    @property
    def id(self):
        return 'S' + str(self.fid or self.num)
    

    @property
    def handle(self):
        if not self._handle:
            self._handle = '_' + os.urandom(10).hex()

        return self._handle

    def print(self, file=sys.stdout):
        """print Source in GEDCOM format"""
        file.write("0 @S%s@ SOUR \n" % self.id)
        if self.title:
            file.write(cont("1 TITL " + self.title))
        if self.citation:
            file.write(cont("1 AUTH " + self.citation))
        if self.url:
            file.write(cont("1 PUBL " + self.url))
        for n in self.notes:
            n.link(file, 1)
        file.write("1 REFN %s\n" % self.fid)

    def link(self, file=sys.stdout, level=1):
        """print the reference in GEDCOM format"""
        file.write("%s SOUR @S%s@\n" % (level, self.id))

    def printxml(self, parent_element: Element) -> None:
        
    #         <source handle="_fa593c277b471380bbcc5282e8f" change="1720382301" id="SQ8M5-NSP">
    #   <stitle>Palkovics Cser József, &quot;Hungary Civil Registration, 1895-1980&quot;</stitle>
    #   <sauthor>&quot;Hungary Civil Registration, 1895-1980&quot;, , &lt;i&gt;FamilySearch&lt;/i&gt; (https://www.familysearch.org/ark:/61903/1:1:6JBQ-NKWD : Thu Mar 07 10:23:43 UTC 2024), Entry for Palkovics Cser József and Palkovics Cser István, 27 Aug 1928.</sauthor>
    #   <spubinfo>https://familysearch.org/ark:/61903/1:1:6JBQ-NKWD</spubinfo>
    #   <srcattribute type="REFN" value="Q8M5-NSP"/>
    # </source>
        source_element = ET.SubElement(
            parent_element,
            'source',
            handle=self.handle,
            change=str(int(self.modified / 1000)),
            id=self.id
        )
        if self.title:
            ET.SubElement(source_element, 'stitle').text = self.title
        if self.citation:
            ET.SubElement(source_element, 'sauthor').text = self.citation
        if self.url:
            ET.SubElement(source_element, 'spubinfo').text = self.url
        if self.fid:
            ET.SubElement(source_element, 'srcattribute', type='REFN', value=self.fid)


class Fact:
    """GEDCOM Fact class
    :param data: FS Fact data
    :param tree: a tree object
    """

    counter = {}

    def __init__(self, data=None, tree: Optional['Tree']=None, num_prefix=None):
        self.value = self.type = self.date = None
        self.date_type = None
        self.place: Optional[Place] = None
        self.note = None
        self._handle: Optional[str] = None
        if data:
            if "value" in data:
                self.value = data["value"]
            if "type" in data:
                self.type = data["type"]
                self.fs_type = self.type
                if self.type in FACT_EVEN:
                    self.type = tree.fs._(FACT_EVEN[self.type])
                elif self.type[:6] == "data:,":
                    self.type = unquote(self.type[6:])
                elif self.type not in FACT_TAGS:
                    self.type = None


        self.num_prefix = f'{num_prefix}_{FACT_TAGS[self.type]}' if num_prefix and self.type in FACT_TAGS else num_prefix
        Fact.counter[self.num_prefix or 'None'] = Fact.counter.get(self.num_prefix or 'None', 0) + 1
        self.num = Fact.counter[self.num_prefix or 'None']
        if data:
            if "date" in data:
                if 'formal' in data['date']:
                    self.date = data['date']['formal'].split('+')[-1].split('/')[0]
                    if data['date']['formal'].startswith('A+'):
                        self.date_type = 'about'
                    if data['date']['formal'].startswith('/+'):
                        self.date_type = 'before'
                    if data['date']['formal'].endswith('/'):
                        self.date_type = 'after'
                else:
                    self.date = data["date"]["original"]
            if "place" in data:
                place = data["place"]
                place_name = place["original"]
                place_id = place["description"][1:] if "description" in place and place["description"][1:] in tree.places else None
                self.place = tree.ensure_place(place_name, place_id)
            if "changeMessage" in data["attribution"]:
                self.note = Note(
                    data["attribution"]["changeMessage"], 
                    tree,
                    num_prefix='E' + self.num_prefix if self.num_prefix else None,
                    note_type='Event Note',
                )
            if self.type == "http://gedcomx.org/Death" and not (
                self.date or self.place
            ):
                self.value = "Y"

        if tree:
            tree.facts.add(self)
        

    @property
    def id(self):
        return f'{self.num_prefix}_{self.num}' if self.num_prefix != None else self.num


    @property
    def handle(self):
        if not self._handle:
            self._handle = '_' + os.urandom(10).hex()

        return self._handle

    def printxml(self, parent_element):
            
        event_element = ET.SubElement(
            parent_element,
            'event',
            handle=self.handle,
            # change='1720382301',
            id=self.id
        )

        ET.SubElement(event_element, 'type').text = (
            unquote_plus(self.type[len('http://gedcomx.org/'):])
            if self.type.startswith('http://gedcomx.org/')
            else self.type
        )
        # FACT_TAGS.get(self.type, self.type)
        if self.date:
            params={
                'val': self.date,
            }
            if self.date_type is not None:
                params['type'] = self.date_type
            ET.SubElement(event_element, 'datestr', **params)
        if self.place:
            ET.SubElement(event_element, 'place', hlink=self.place.handle)
        if self.note:
            ET.SubElement(event_element, 'noteref', hlink=self.note.handle)

    def print(self, file=sys.stdout):
        """print Fact in GEDCOM format
        the GEDCOM TAG depends on the type, defined in FACT_TAGS
        """
        if self.type in FACT_TAGS:
            tmp = "1 " + FACT_TAGS[self.type]
            if self.value:
                tmp += " " + self.value
            file.write(cont(tmp))
        elif self.type:
            file.write("1 EVEN\n2 TYPE %s\n" % self.type)
            if self.value:
                file.write(cont("2 NOTE Description: " + self.value))
        else:
            return
        if self.date:
            file.write(cont("2 DATE " + self.date))
        if self.place:
            self.place.print(file, 2)
        if self.map:
            latitude, longitude = self.map
            file.write("3 MAP\n4 LATI %s\n4 LONG %s\n" % (latitude, longitude))
        if self.note:
            self.note.link(file, 2)


class Memorie:
    """GEDCOM Memorie class
    :param data: FS Memorie data
    """

    def __init__(self, data=None):
        self.description = self.url = None
        if data and "links" in data:
            self.url = data["about"]
            if "titles" in data:
                self.description = data["titles"][0]["value"]
            if "descriptions" in data:
                self.description = (
                    "" if not self.description else self.description + "\n"
                ) + data["descriptions"][0]["value"]

    def print(self, file=sys.stdout):
        """print Memorie in GEDCOM format"""
        file.write("1 OBJE\n2 FORM URL\n")
        if self.description:
            file.write(cont("2 TITL " + self.description))
        if self.url:
            file.write(cont("2 FILE " + self.url))


NAME_MAP = {
    "preferred" : 'Preeferred Name',
    "nickname" : 'Nickname',
    "birthname": 'Birth Name',
    "aka": 'Also Known As',
    "married": 'Married Name',
}

class Name:
    """GEDCOM Name class
    :param data: FS Name data
    :param tree: a Tree object
    """

    def __init__(self, data=None, tree=None, owner_fis=None, kind=None, alternative: bool=False):
        self.given = ""
        self.surname = ""
        self.prefix = None
        self.suffix = None
        self.note = None
        self.alternative = alternative
        self.owner_fis = owner_fis
        self.kind = kind
        if data:
            if "parts" in data["nameForms"][0]:
                for z in data["nameForms"][0]["parts"]:
                    if z["type"] == "http://gedcomx.org/Given":
                        self.given = z["value"]
                    if z["type"] == "http://gedcomx.org/Surname":
                        self.surname = z["value"]
                    if z["type"] == "http://gedcomx.org/Prefix":
                        self.prefix = z["value"]
                    if z["type"] == "http://gedcomx.org/Suffix":
                        self.suffix = z["value"]
            if "changeMessage" in data["attribution"]:
                self.note = Note(
                    data["attribution"]["changeMessage"],
                    tree,
                    num_prefix=f'NAME_{owner_fis}_{kind}',
                    note_type='Name Note',
                )

    def printxml(self, parent_element):
        params = {}
        if self.kind is not None:
            params['type'] = NAME_MAP.get(self.kind, self.kind)
        if self.alternative:
            params['alt'] = '1'
        person_name = ET.SubElement(parent_element, 'name', **params)
        ET.SubElement(person_name, 'first').text = self.given
        ET.SubElement(person_name, 'surname').text = self.surname
        # TODO prefix / suffix


    def print(self, file=sys.stdout, typ=None):
        """print Name in GEDCOM format
        :param typ: type for additional names
        """
        tmp = "1 NAME %s /%s/" % (self.given, self.surname)
        if self.suffix:
            tmp += " " + self.suffix
        file.write(cont(tmp))
        if typ:
            file.write("2 TYPE %s\n" % typ)
        if self.prefix:
            file.write("2 NPFX %s\n" % self.prefix)
        if self.note:
            self.note.link(file, 2)



class Place:
    """GEDCOM Place class
    :param name: the place name
    :param tree: a Tree object
    :param num: the GEDCOM identifier
    """

    counter = 0

    def __init__(
            self, 
            id: str, 
            name: str, 
            type: Optional[str]=None, 
            parent: Optional['Place']=None,
            latitude: Optional[float]=None,
            longitude: Optional[float]=None):
        self._handle = None
        self.name = name
        self.type = type
        self.id = id
        self.parent = parent
        self.latitude = latitude
        self.longitude = longitude

    @property
    def handle(self):
        if not self._handle:
            self._handle = '_' + os.urandom(10).hex()

        return self._handle


    def print(self, file=sys.stdout, indentation=0):
        """print Place in GEDCOM format"""
        file.write("%d @P%s@ PLAC %s\n" % (indentation, self.num, self.name))

    def printxml(self, parent_element):


    #     <placeobj handle="_fac310617a8744e1d62f3d0dafe" change="1723223127" id="P0000" type="Country">
    #   <pname value="Magyarország"/>
    # </placeobj>
    # <placeobj handle="_fac310962e15149e8244c2ccade" change="1723223149" id="P0001" type="County">
    #   <pname value="Fejér"/>
    #   <placeref hlink="_fac310617a8744e1d62f3d0dafe"/>
    # </placeobj>
        place_element = ET.SubElement(
            parent_element, 
            'placeobj',
            handle=self.handle,
            # change='1720382307',
            id=self.id,
            type=self.type or 'Unknown'
        )
        # ET.SubElement(place_element, 'ptitle').text = self.name
        ET.SubElement(place_element, 'pname', value=self.name)
        if self.parent:
            ET.SubElement(place_element, 'placeref', hlink=self.parent.handle)
        if self.latitude and self.longitude:
            ET.SubElement(place_element, 'coord', long=str(self.longitude), lat=str(self.latitude))

class Ordinance:
    """GEDCOM Ordinance class
    :param data: FS Ordinance data
    """

    def __init__(self, data=None):
        self.date = self.temple_code = self.status = self.famc = None
        if data:
            if "completedDate" in data:
                self.date = data["completedDate"]
            if "completedTemple" in data:
                self.temple_code = data["completedTemple"]["code"]
            self.status = data["status"]

    def print(self, file=sys.stdout):
        """print Ordinance in Gecom format"""
        if self.date:
            file.write(cont("2 DATE " + self.date))
        if self.temple_code:
            file.write("2 TEMP %s\n" % self.temple_code)
        if self.status in ORDINANCES_STATUS:
            file.write("2 STAT %s\n" % ORDINANCES_STATUS[self.status])
        if self.famc:
            file.write("2 FAMC @F%s@\n" % self.famc.num)

class Citation:

    def __init__(self, data: Dict[str, Any], source: Source):
        self._handle = None
        self.id = data["id"]
        self.source = source
        self.message = (
            data["attribution"]["changeMessage"]
            if "changeMessage" in data["attribution"]
            else None
        )
        # TODO create citation note out of this.
        self.modified = data['attribution']['modified']

    
    @property
    def handle(self):
        if not self._handle:
            self._handle = '_' + os.urandom(10).hex()

        return self._handle

    def printxml(self, parent_element: Element):
        
#     <citation handle="_fac4a72a01b1681293ea1ee8d9" change="1723265781" id="C0000">
#       <dateval val="1998-05-03"/>
#       <confidence>2</confidence>
#       <noteref hlink="_fac4a71ac2c6c5749abd6a0bd72"/>
#       <sourceref hlink="_fac4a70566329a02afcc10731f5"/>
#     </citation>
        citation_element = ET.SubElement(
            parent_element,
            'citation',
            handle=self.handle,
            change=str(int(self.modified / 1000)),
            id='C' + str(self.id)
        )
        ET.SubElement(citation_element, 'confidence').text = '2'
        ET.SubElement(citation_element, 'sourceref', hlink=self.source.handle)


class Indi:
    """GEDCOM individual class
    :param fid' FamilySearch id
    :param tree: a tree object
    :param num: the GEDCOM identifier
    """

    counter = 0

    def __init__(self, fid: str, tree: 'Tree', num=None):
        self._handle = None
        if num:
            self.num = num
        else:
            Indi.counter += 1
            self.num = Indi.counter
        self.fid = fid
        self.tree = tree
        self.famc: Set['Fam'] = set()
        self.fams: Set['Fam'] = set()
        # self.famc_fid = set()
        # self.fams_fid = set()
        # self.famc_num = set()
        # self.fams_num = set()
        # self.famc_ids = set()
        # self.fams_ids = set()
        self.name: Optional[Name] = None
        self.gender = None
        self.living = None
        self.parents: Set[Tuple[str, str]] = set() # (father_id, mother_id)
        self.spouses: Set[Tuple[str, str, str]]  = set() # (person1, person2, relfid)
        self.children: Set[Tuple[str, str, str]] = set() # (father_id, mother_id, child_id)
        self.baptism = self.confirmation = self.initiatory = None
        self.endowment = self.sealing_child = None
        self.nicknames: Set[Name] = set()
        self.birthnames: Set[Name] = set()
        self.married: Set[Name] = set()
        self.aka: Set[Name] = set()
        self.facts: Set[Fact] = set()
        self.notes: Set[Note] = set()
        # self.sources: Set[Source] = set()
        self.citations: Set[Citation] = set()
        self.memories = set()

    def add_data(self, data):
        """add FS individual data"""
        if data:
            self.living = data["living"]
            for x in data["names"]:
                alt = not x.get('preferred', False)
                if x["type"] == "http://gedcomx.org/Nickname":
                    self.nicknames.add(Name(x, self.tree, self.fid, "nickname", alt))
                elif x["type"] == "http://gedcomx.org/BirthName":
                    self.birthnames.add(Name(x, self.tree, self.fid, "birthname", alt))
                elif x["type"] == "http://gedcomx.org/AlsoKnownAs":
                    self.aka.add(Name(x, self.tree, self.fid, "aka", alt))
                elif x["type"] == "http://gedcomx.org/MarriedName":
                    self.married.add(Name(x, self.tree, self.fid, "married", alt))
                else:
                    print('Unknown name type: ' + x.get('type'), file=sys.stderr)
                    raise 'Unknown name type'
            if "gender" in data:
                if data["gender"]["type"] == "http://gedcomx.org/Male":
                    self.gender = "M"
                elif data["gender"]["type"] == "http://gedcomx.org/Female":
                    self.gender = "F"
                elif data["gender"]["type"] == "http://gedcomx.org/Unknown":
                    self.gender = "U"
            if "facts" in data:
                for x in data["facts"]:
                    if x["type"] == "http://familysearch.org/v1/LifeSketch":
                        self.notes.add(
                            Note(
                                "=== %s ===\n%s"
                                % (self.tree.fs._("Life Sketch"), x.get("value", "")),
                                self.tree,
                                num_prefix=f'INDI_{self.fid}',
                                note_type='Person Note',
                            )
                        )
                    else:
                        self.facts.add(Fact(x, self.tree, num_prefix=f'INDI_{self.fid}'))
            if "sources" in data:
                sources = self.tree.fs.get_url(
                    "/platform/tree/persons/%s/sources" % self.fid
                )
                if sources:
                    quotes = dict()
                    for quote in sources["persons"][0]["sources"]:
                        source_id = quote["descriptionId"]
                        source_data = next(
                            (s for s in sources['sourceDescriptions'] if s['id'] == source_id),
                            None,
                        )
                        source = self.tree.ensure_source(source_data)
                        if source:
                            citation = self.tree.ensure_citation(quote, source)
                            self.citations.add(citation)

            for evidence in data.get("evidence", []):
                memory_id, *_ = evidence["id"].partition("-")
                url = "/platform/memories/memories/%s" % memory_id
                memorie = self.tree.fs.get_url(url)
                if memorie and "sourceDescriptions" in memorie:
                    for x in memorie["sourceDescriptions"]:
                        if x["mediaType"] == "text/plain":
                            text = "\n".join(
                                val.get("value", "")
                                for val in x.get("titles", [])
                                + x.get("descriptions", [])
                            )
                            self.notes.add(
                                Note(
                                    text,
                                    self.tree,
                                    num_prefix=f'INDI_{self.fid}',
                                    note_type='Person Note',
                                ))
                        else:
                            self.memories.add(Memorie(x))

    def add_fams(self, fam: 'Fam'):
        """add family fid (for spouse or parent)"""
        self.fams.add(fam)

    def add_famc(self, fam: 'Fam'):
        """add family fid (for child)"""
        self.famc.add(fam)

    def get_notes(self):
        """retrieve individual notes"""
        print(f'Getting Notes for {self.fid}', file=sys.stderr)
        notes = self.tree.fs.get_url("/platform/tree/persons/%s/notes" % self.fid)
        if notes:
            for n in notes["persons"][0]["notes"]:
                text_note = "=== %s ===\n" % n["subject"] if "subject" in n else ""
                text_note += n["text"] + "\n" if "text" in n else ""
                self.notes.add(
                    Note(
                        text_note,
                        self.tree,
                        num_prefix=f'INDI_{self.fid}',
                        note_type='Person Note',
                    ))

    def get_ordinances(self):
        """retrieve LDS ordinances
        need a LDS account
        """
        res = []
        famc = False
        if self.living:
            return res, famc
        url = "/service/tree/tree-data/reservations/person/%s/ordinances" % self.fid
        data = self.tree.fs.get_url(url, {})
        if data:
            for key, o in data["data"].items():
                if key == "baptism":
                    self.baptism = Ordinance(o)
                elif key == "confirmation":
                    self.confirmation = Ordinance(o)
                elif key == "initiatory":
                    self.initiatory = Ordinance(o)
                elif key == "endowment":
                    self.endowment = Ordinance(o)
                elif key == "sealingsToParents":
                    for subo in o:
                        self.sealing_child = Ordinance(subo)
                        relationships = subo.get("relationships", {})
                        father = relationships.get("parent1Id")
                        mother = relationships.get("parent2Id")
                        if father and mother:
                            famc = father, mother
                elif key == "sealingsToSpouses":
                    res += o
        return res, famc

    def get_contributors(self):
        """retrieve contributors"""
        temp = set()
        url = "/platform/tree/persons/%s/changes" % self.fid
        data = self.tree.fs.get_url(url, {"Accept": "application/x-gedcomx-atom+json"})
        if data:
            for entries in data["entries"]:
                for contributors in entries["contributors"]:
                    temp.add(contributors["name"])
        if temp:
            text = "=== %s ===\n%s" % (
                self.tree.fs._("Contributors"),
                "\n".join(sorted(temp)),
            )
            for n in self.tree.notes:
                if n.text == text:
                    self.notes.add(n)
                    return
            self.notes.add(Note(text, self.tree, num_prefix=f'INDI_{self.fid}_CONTRIB', note_type='Contribution Note'))

    @property
    def id(self):
        return self.fid or self.num
    

    @property
    def handle(self):
        if not self._handle:
            self._handle = '_' + os.urandom(10).hex()

        return self._handle

    def printxml(self, parent_element):

        # <person handle="_fa593c2779e5ed1c947416cba9e" change="1720382301" id="IL43B-D2H">
        #     <gender>M</gender>
        #     <name type="Birth Name">
        #         <first>József</first>
        #         <surname>Cser</surname>
        #         <noteref hlink="_fa593c2779f7c527e3afe4623b9"/>
        #     </name>
        #     <eventref hlink="_fa593c277a0712aa4241bbf47db" role="Primary"/>
        #     <attribute type="_FSFTID" value="L43B-D2H"/>
        #     <childof hlink="_fa593c277af212e6c1f9f44bc4a"/>
        #     <parentin hlink="_fa593c277af72c83e0e3fbf6ed2"/>
        #     <citationref hlink="_fa593c277b7715371c26d1b0a81"/>
        # </person>
        person = ET.SubElement(parent_element, 
                'person', 
                handle=self.handle, 
                # change='1720382301', 
                id='I' + str(self.id))
        if self.fid:
            ET.SubElement(person, 'attribute', type='_FSFTID', value=self.fid)

        if self.name:
            self.name.printxml(person)
        for name in self.nicknames | self.birthnames | self.aka | self.married:
            name.printxml(person)
        
        gender = ET.SubElement(person, 'gender')
        gender.text = self.gender
        
        if self.fams:
            for fam in self.fams:
                ET.SubElement(person, 'parentin', hlink=fam.handle)

        if self.famc:
            for fam in self.famc:
                ET.SubElement(person, 'childof', hlink=fam.handle)


        ET.SubElement(person, 'attribute', type="_FSFTID", value=self.fid)

        
        for fact in self.facts:
            ET.SubElement(person, 'eventref', hlink=fact.handle, role='Primary')

        for citation in self.citations:
            ET.SubElement(person, 'citationref', hlink=citation.handle)

        for note in self.notes:
            ET.SubElement(person, 'noteref', hlink=note.handle)

    #   <noteref hlink="_fac4a686369713d9cd55159ada9"/>
    #   <citationref hlink="_fac4a72a01b1681293ea1ee8d9"/>


    def print(self, file=sys.stdout):
        """print individual in GEDCOM format"""
        file.write("0 @I%s@ INDI\n" % self.id)
        if self.name:
            self.name.print(file)
        for o in self.nicknames:
            file.write(cont("2 NICK %s %s" % (o.given, o.surname)))
        for o in self.birthnames:
            o.print(file)
        for o in self.aka:
            o.print(file, "aka")
        for o in self.married:
            o.print(file, "married")
        if self.gender:
            file.write("1 SEX %s\n" % self.gender)
        for o in self.facts:
            o.print(file)
        for o in self.memories:
            o.print(file)
        if self.baptism:
            file.write("1 BAPL\n")
            self.baptism.print(file)
        if self.confirmation:
            file.write("1 CONL\n")
            self.confirmation.print(file)
        if self.initiatory:
            file.write("1 WAC\n")
            self.initiatory.print(file)
        if self.endowment:
            file.write("1 ENDL\n")
            self.endowment.print(file)
        if self.sealing_child:
            file.write("1 SLGC\n")
            self.sealing_child.print(file)
        for fam in self.fams:
            file.write("1 FAMS @F%s@\n" % fam.id)
        for fam in self.famc:
            file.write("1 FAMC @F%s@\n" % fam.id)
        # print(f'Fams Ids: {self.fams_ids}, {self.fams_fid}, {self.fams_num}', file=sys.stderr)
        # for num in self.fams_ids:
        # print(f'Famc Ids: {self.famc_ids}', file=sys.stderr)
        # for num in self.famc_ids:
            # file.write("1 FAMC @F%s@\n" % num)
        file.write("1 _FSFTID %s\n" % self.fid)
        for o in self.notes:
            o.link(file)
        for source, quote in self.sources:
            source.link(file, 1)
            if quote:
                file.write(cont("2 PAGE " + quote))


class Fam:
    """GEDCOM family class
    :param husb: husbant fid
    :param wife: wife fid
    :param tree: a Tree object
    :param num: a GEDCOM identifier
    """

    counter = 0

    def __init__(self, husband: Indi | None, wife: Indi | None, tree: 'Tree'):
        self._handle = None
        self.num = Fam.gen_id(husband, wife)
        self.fid = None
        self.husband = husband
        self.wife = wife
        self.tree = tree
        self.children: Set[Indi] = set()
        self.facts: Set[Fact] = set()
        self.sealing_spouse = None
        self.notes = set()
        self.sources = set()

    @property
    def handle(self):
        if not self._handle:
            self._handle = '_' + os.urandom(10).hex()

        return self._handle
    
    @staticmethod
    def gen_id(husband: Indi | None, wife: Indi | None) -> str:
        if husband and wife:
            return f'FAM_{husband.id}-{wife.id}'
        elif husband:
            return f'FAM_{husband.id}-UNK'
        elif wife:
            return f'FAM_UNK-{wife.id}'
        else:
            Fam.counter += 1
            return f'FAM_UNK-UNK-{Fam.counter}'

    def add_child(self, child: Indi | None):
        """add a child fid to the family"""
        if child is not None:
            self.children.add(child)

    def add_marriage(self, fid: str):
        """retrieve and add marriage information
        :param fid: the marriage fid
        """
        if not self.fid:
            self.fid = fid
            url = "/platform/tree/couple-relationships/%s" % self.fid
            data = self.tree.fs.get_url(url)
            if data:
                if "facts" in data["relationships"][0]:
                    for x in data["relationships"][0]["facts"]:
                        self.facts.add(Fact(x, self.tree, num_prefix=f'FAM_{self.fid}'))
                if "sources" in data["relationships"][0]:
                    quotes = dict()
                    for x in data["relationships"][0]["sources"]:
                        quotes[x["descriptionId"]] = (
                            x["attribution"]["changeMessage"]
                            if "changeMessage" in x["attribution"]
                            else None
                        )
                    new_sources = quotes.keys() - self.tree.sources.keys()
                    if new_sources:
                        sources = self.tree.fs.get_url(
                            "/platform/tree/couple-relationships/%s/sources" % self.fid
                        )
                        for source in sources["sourceDescriptions"]:
                            if (
                                source["id"] in new_sources
                                and source["id"] not in self.tree.sources
                            ):
                                self.tree.sources[source["id"]] = Source(
                                    source, self.tree
                                )
                    for source_fid in quotes:
                        self.sources.add(
                            (self.tree.sources[source_fid], quotes[source_fid])
                        )

    def get_notes(self):
        """retrieve marriage notes"""
        if self.fid:
            notes = self.tree.fs.get_url(
                "/platform/tree/couple-relationships/%s/notes" % self.fid
            )
            if notes:
                for n in notes["relationships"][0]["notes"]:
                    text_note = "=== %s ===\n" % n["subject"] if "subject" in n else ""
                    text_note += n["text"] + "\n" if "text" in n else ""
                    self.notes.add(Note(text_note, self.tree, num_prefix=f'FAM_{self.fid}', note_type='Marriage Note'))

    def get_contributors(self):
        """retrieve contributors"""
        if self.fid:
            temp = set()
            url = "/platform/tree/couple-relationships/%s/changes" % self.fid
            data = self.tree.fs.get_url(
                url, {"Accept": "application/x-gedcomx-atom+json"}
            )
            if data:
                for entries in data["entries"]:
                    for contributors in entries["contributors"]:
                        temp.add(contributors["name"])
            if temp:
                text = "=== %s ===\n%s" % (
                    self.tree.fs._("Contributors"),
                    "\n".join(sorted(temp)),
                )
                for n in self.tree.notes:
                    if n.text == text:
                        self.notes.add(n)
                        return
                self.notes.add(Note(text, self.tree, num_prefix=f'FAM_{self.fid}_CONTRIB', note_type='Contribution Note'))

    @property
    def id(self):
        return self.num
    
    def printxml(self, parent_element):
        # <family handle="_fa593c277af212e6c1f9f44bc4a" change="1720382301" id="F9MKP-K92">
        #   <rel type="Unknown"/>
        #   <father hlink="_fa593c277f14dc6db9ab19cbe09"/>
        #   <mother hlink="_fa593c277cd4af15983d7064c59"/>
        #   <childref hlink="_fa593c279e1466787c923487b98"/>
        #   <attribute type="_FSFTID" value="9MKP-K92"/>
        # </family>
        family = ET.SubElement(parent_element, 
                'family', 
                handle=self.handle, 
                # change='1720382301', 
                id=self.id)
        ET.SubElement(family, 'rel', type='Unknown')
        if self.husband:
            ET.SubElement(family, 'father', hlink=self.husband.handle)
        if self.wife:
            ET.SubElement(family, 'mother', hlink=self.wife.handle)
        for child in self.children:
            ET.SubElement(family, 'childref', hlink=child.handle)
        for fact in self.facts:
            ET.SubElement(family, 'eventref', hlink=fact.handle, role='Primary')

    def print(self, file=sys.stdout):
        """print family information in GEDCOM format"""
        file.write("0 @F%s@ FAM\n" % self.id)
        if self.husband:
            file.write("1 HUSB @I%s@\n" % self.husband.id)
        if self.wife:
            file.write("1 WIFE @I%s@\n" % self.wife.id)
        for child in self.children:
            file.write("1 CHIL @I%s@\n" % child.id)
        for o in self.facts:
            o.print(file)
        if self.sealing_spouse:
            file.write("1 SLGS\n")
            self.sealing_spouse.print(file)
        if self.fid:
            file.write("1 _FSFTID %s\n" % self.fid)
        for o in self.notes:
            o.link(file)
        for source, quote in self.sources:
            source.link(file, 1)
            if quote:
                file.write(cont("2 PAGE " + quote))


class Tree:
    """family tree class
    :param fs: a Session object
    """

    def __init__(self, fs: Optional[requests.Session]=None, exclude: List[str]=None, geonames_key=None):
        self.fs = fs
        self.geonames_key = geonames_key
        self.indi: Dict[str, Indi] = dict()
        self.fam: Dict[str, Fam] = dict()
        self.notes = list()
        self.facts: Set[Fact] = set()
        self.sources: Dict[str, Source] = dict()
        self.citations: Dict[str, Citation] = dict()
        self.places: List[Place] = []
        self.places_by_names: Dict[str, Place] = dict()
        self.place_cache: Dict[str, Tuple[float, float]] = dict()
        self.display_name = self.lang = None
        self.exclude: List[str] = exclude or []
        self.place_counter = 0
        if fs:
            self.display_name = fs.display_name
            self.lang = babelfish.Language.fromalpha2(fs.lang).name

        self.geosession = CachedSession('http_cache', backend='filesystem', expire_after=86400)

    def add_indis(self, fids_in: List[str]):
        """add individuals to the family tree
        :param fids: an iterable of fid
        """
        fids = []
        for fid in fids_in:
            if fid not in self.exclude:
                fids.append(fid)
            else:
                print(
                    "Excluding %s from the family tree" % fid, file=sys.stderr
                )

        async def add_datas(loop, data):
            futures = set()
            for person in data["persons"]:
                self.indi[person["id"]] = Indi(person["id"], self)
                futures.add(
                    loop.run_in_executor(None, self.indi[person["id"]].add_data, person)
                )
            for future in futures:
                await future

        new_fids = [fid for fid in fids if fid and fid not in self.indi]
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        while new_fids:
            data = self.fs.get_url(
                "/platform/tree/persons?pids=" + ",".join(new_fids[:MAX_PERSONS])
            )
            if data:
                if "places" in data:
                    for place in data["places"]:
                        if place["id"] not in self.place_cache:
                            self.place_cache[place["id"]] = (
                                place["latitude"],
                                place["longitude"],
                            )
                loop.run_until_complete(add_datas(loop, data))
                if "childAndParentsRelationships" in data:
                    for rel in data["childAndParentsRelationships"]:
                        father: str | None = rel.get("parent1", {}).get("resourceId")
                        mother: str | None = rel.get("parent2", {}).get("resourceId")
                        child: str | None = rel.get("child", {}).get("resourceId")
                        if child in self.indi:
                            self.indi[child].parents.add((father, mother))
                        if father in self.indi:
                            self.indi[father].children.add((father, mother, child))
                        if mother in self.indi:
                            self.indi[mother].children.add((father, mother, child))
                if "relationships" in data:
                    for rel in data["relationships"]:
                        if rel["type"] == "http://gedcomx.org/Couple":
                            person1 = rel["person1"]["resourceId"]
                            person2 = rel["person2"]["resourceId"]
                            relfid = rel["id"]
                            if person1 in self.indi:
                                self.indi[person1].spouses.add(
                                    (person1, person2, relfid)
                                )
                            if person2 in self.indi:
                                self.indi[person2].spouses.add(
                                    (person1, person2, relfid)
                                )
            new_fids = new_fids[MAX_PERSONS:]

    def ensure_source(self, source_data: Dict[str, Any]) -> Source:
        if source_data["id"] not in self.sources:
            self.sources[source_data["id"]] = Source(source_data, self)
        return self.sources.get(source_data["id"])
    
    def ensure_citation(self, data: Dict[str, Any], source: Source) -> Citation:
        citation_id = data["id"]
        if citation_id not in self.citations:
            self.citations[citation_id] = Citation(data, source)
        return self.citations[citation_id]

    def ensure_family(self, father: Optional['Indi'], mother: Optional['Indi']) -> Fam:
        fam_id = Fam.gen_id(father, mother)
        if fam_id not in self.fam:
            self.fam[fam_id] = Fam(father, mother, self)
        return self.fam[fam_id]


    def place_by_geoname_id(self, id: str) -> Optional[Place]:
        for place in self.places:
            if place.id == id:
                return place
        return None

    def get_by_geonames_id(self, geonames_id: str) -> Place:
        print('Fetching place hierarchy for', geonames_id, file=sys.stderr)
        hierarchy = geocoder.geonames(
            geonames_id,
            key=self.geonames_key,
            lang=['hu', 'en', 'de'],
            method='hierarchy',
            session=self.geosession,
        )

        if hierarchy and hierarchy.ok:
            last_place = None
            for item in hierarchy.geojson.get('features', []):
                properties = item.get('properties', {})
                code = properties.get('code')
                
                if code in ['AREA', 'CONT']:
                    continue
                
                print('Properties', properties, file=sys.stderr)
                id = 'GEO' + str(properties['geonames_id'])
                place = self.place_by_geoname_id(id)
                if place is None:
                    place = Place(
                        id,
                        properties.get('address'),
                        GEONAME_FEATURE_MAP.get(code, 'Unknown'),
                        last_place,
                        properties.get('lat'),
                        properties.get('lng')
                    )
                    self.places.append(place)
                last_place = place
            return last_place

    @property        
    def _next_place_counter(self):
        self.place_counter += 1
        return self.place_counter

        
    def ensure_place(self, place_name: str, fid: Optional[str] = None, coord: Optional[Tuple[float, float]] = None) -> Place:
        if place_name not in self.places_by_names:
            place = None
            if self.geonames_key:
                print('Fetching place', place_name, file=sys.stderr)
                geoname_record = geocoder.geonames(
                    place_name,
                    key=self.geonames_key,
                    session=self.geosession,
                )
                if geoname_record and geoname_record.ok:
                    place = self.get_by_geonames_id(geoname_record.geonames_id)
            if place is None:
                coord = self.place_cache.get(fid) if coord is None else coord
                place = Place(
                    'PFSID' + fid if fid is not None else 'P' + str(self._next_place_counter),
                    place_name,
                    latitude=coord[0] if coord is not None else None,
                    longitude=coord[1] if coord is not None else None
                )
                self.places.append(place)
            self.places_by_names[place_name] = place
        return self.places_by_names[place_name]

    # def add_fam(self, father, mother):
    #     """add a family to the family tree
    #     :param father: the father fid or None
    #     :param mother: the mother fid or None
    #     """
    #     if (father, mother) not in self.fam:
    #         self.fam[(father, mother)] = Fam(father, mother, self)

    def add_trio(self, father: Indi | None, mother: Indi | None, child: Indi | None):
        """add a children relationship to the family tree
        :param father: the father fid or None
        :param mother: the mother fid or None
        :param child: the child fid or None
        """
        fam = self.ensure_family(father, mother)
        if child is not None:
            fam.add_child(child)
            child.add_famc(fam)
        
        if father is not None:
            father.add_fams(fam)
        if mother is not None:
            mother.add_fams(fam)

    def add_parents(self, fids: Set[str]):
        """add parents relationships
        :param fids: a set of fids
        """
        parents = set()
        for fid in fids & self.indi.keys():
            for couple in self.indi[fid].parents:
                parents |= set(couple)
        if parents:
            self.add_indis(parents)
        for fid in fids & self.indi.keys():
            for father, mother in self.indi[fid].parents:
                if (
                    mother in self.indi
                    and father in self.indi
                    or not father
                    and mother in self.indi
                    or not mother
                    and father in self.indi
                ):
                    self.add_trio(
                        self.indi.get(father), 
                        self.indi.get(mother), 
                        self.indi.get(fid),
                    )
        return set(filter(None, parents))

    def add_spouses(self, fids: Set[str]):
        """add spouse relationships
        :param fids: a set of fid
        """

        async def add(loop, rels: Set[Tuple[str, str, str]]):
            futures = set()
            for father, mother, relfid in rels:
                if father in self.exclude or mother in self.exclude:
                    continue
                fam_id = Fam.gen_id(self.indi[father], self.indi[mother])
                if self.fam.get(fam_id):
                    futures.add(
                        loop.run_in_executor(
                            None, self.fam[fam_id].add_marriage, relfid
                        )
                    )
            for future in futures:
                await future

        rels: Set[Tuple[str, str, str]] = set()
        for fid in fids & self.indi.keys():
            rels |= self.indi[fid].spouses
        loop = asyncio.get_event_loop()
        if rels:
            self.add_indis(
                set.union(*({father, mother} for father, mother, relfid in rels))
            )
            for father, mother, _ in rels:
                if father in self.indi and mother in self.indi:
                    father_indi = self.indi[father]
                    mother_indi = self.indi[mother]
                    fam = self.ensure_family(father_indi, mother_indi)
                    father_indi.add_fams(fam)
                    mother_indi.add_fams(fam)

            loop.run_until_complete(add(loop, rels))

    def add_children(self, fids):
        """add children relationships
        :param fids: a set of fid
        """
        rels: Set[Tuple[str, str, str]] = set()
        for fid in fids & self.indi.keys():
            rels |= self.indi[fid].children if fid in self.indi else set()
        children = set()
        if rels:
            self.add_indis(set.union(*(set(rel) for rel in rels)))
            for father, mother, child in rels:
                if child in self.indi and (
                    mother in self.indi
                    and father in self.indi
                    or not father
                    and mother in self.indi
                    or not mother
                    and father in self.indi
                ):
                    self.add_trio(
                        self.indi.get(father),
                        self.indi.get(mother),
                        self.indi.get(child),
                    )
                    children.add(child)
        return children

    def add_ordinances(self, fid):
        """retrieve ordinances
        :param fid: an individual fid
        """
        if fid in self.indi:
            ret, famc = self.indi[fid].get_ordinances()
            if famc and famc in self.fam:
                self.indi[fid].sealing_child.famc = self.fam[famc]
            for o in ret:
                spouse_id = o["relationships"]["spouseId"]
                if (fid, spouse_id) in self.fam:
                    self.fam[fid, spouse_id].sealing_spouse = Ordinance(o)
                elif (spouse_id, fid) in self.fam:
                    self.fam[spouse_id, fid].sealing_spouse = Ordinance(o)

    def reset_num(self):
        """reset all GEDCOM identifiers"""
        # for husb, wife in self.fam:
        #     self.fam[(husb, wife)].husb_num = self.indi[husb].num if husb else None
        #     self.fam[(husb, wife)].wife_num = self.indi[wife].num if wife else None
        #     self.fam[(husb, wife)].chil_num = set(
        #         self.indi[chil].num for chil in self.fam[(husb, wife)].chil_fid
        #     )
        # for fid in self.indi:
        #     self.indi[fid].famc_num = set(
        #         self.fam[(husb, wife)].num for husb, wife in self.indi[fid].famc_fid
        #     )
        #     self.indi[fid].fams_num = set(
        #         self.fam[(husb, wife)].num for husb, wife in self.indi[fid].fams_fid
        #     )            
        #     self.indi[fid].famc_ids = set(
        #         self.fam[(husb, wife)].id for husb, wife in self.indi[fid].famc_fid
        #     )
        #     self.indi[fid].fams_ids = set(
        #         self.fam[(husb, wife)].id for husb, wife in self.indi[fid].fams_fid
        #     )

    def printxml(self, file: BinaryIO):

#         root = ET.Element("root")
#         doc = ET.SubElement(root, "doc")

#         ET.SubElement(doc, "field1", name="blah").text = "some value1"
#         ET.SubElement(doc, "field2", name="asdfasd").text = "some vlaue2"

#         tree = ET.ElementTree(root)
#         tree.write("filename.xml")

#         <?xml version="1.0" encoding="UTF-8"?>
# <!DOCTYPE database PUBLIC "-//Gramps//DTD Gramps XML 1.7.1//EN"
# "http://gramps-project.org/xml/1.7.1/grampsxml.dtd">
# <database xmlns="http://gramps-project.org/xml/1.7.1/">
#   <header
#     <created date="2024-07-07" version="5.2.2"/>
#     <researcher>
#       <resname>Barnabás Südy</resname>
#     </researcher>
#   </header>

        root = ET.Element("database", xmlns="http://gramps-project.org/xml/1.7.1/")

        header = ET.SubElement(root, "header")
        ET.SubElement(header, "created", date=datetime.strftime(datetime.now(), "%Y-%m-%d"), version="5.2.2")
        researcher = ET.SubElement(header, "researcher")
        resname = ET.SubElement(researcher, "resname")
        resname.text = self.display_name

        people = ET.SubElement(root, "people")
        for indi in sorted(self.indi.values(), key=lambda x: x.num):
            indi.printxml(people)

        families = ET.SubElement(root, "families")
        for fam in sorted(self.fam.values(), key=lambda x: x.num):
            fam.printxml(families)

        events = ET.SubElement(root, "events")
        for fact in self.facts:
            fact.printxml(events)

        notes = ET.SubElement(root, "notes")
        for note in sorted(self.notes, key=lambda x: x.id):
            note.printxml(notes)

        places = ET.SubElement(root, "places")
        for place in self.places:
            place.printxml(places)

        sources = ET.SubElement(root, "sources")
        for source in self.sources.values():
            source.printxml(sources)

        citations = ET.SubElement(root, "citations")
        for citation in self.citations.values():
            citation.printxml(citations)

        tree = ET.ElementTree(root)

        doctype='<!DOCTYPE database PUBLIC "-//Gramps//DTD Gramps XML 1.7.1//EN" "http://gramps-project.org/xml/1.7.1/grampsxml.dtd">'
        file.write(doctype.encode('utf-8'))
        tree.write(file, 'utf-8')
        

    def print(self, file=sys.stdout):
        """print family tree in GEDCOM format"""
        file.write("0 HEAD\n")
        file.write("1 CHAR UTF-8\n")
        file.write("1 GEDC\n")
        file.write("2 VERS 5.5.1\n")
        file.write("2 FORM LINEAGE-LINKED\n")
        file.write("1 SOUR getmyancestors\n")
        file.write("2 VERS %s\n" % getmyancestors.__version__)
        file.write("2 NAME getmyancestors\n")
        file.write("1 DATE %s\n" % time.strftime("%d %b %Y"))
        file.write("2 TIME %s\n" % time.strftime("%H:%M:%S"))
        file.write("1 SUBM @SUBM@\n")
        file.write("0 @SUBM@ SUBM\n")
        file.write("1 NAME %s\n" % self.display_name)
        # file.write("1 LANG %s\n" % self.lang)

        for fid in sorted(self.indi, key=lambda x: self.indi.__getitem__(x).num):
            self.indi[fid].print(file)
        for fam in sorted(self.fam.values(), key=lambda x: x.num):
            fam.print(file)
        sources = sorted(self.sources.values(), key=lambda x: x.num)
        for s in sources:
            s.print(file)
        notes = sorted(self.notes, key=lambda x: x.id)
        for i, n in enumerate(notes):
            if i > 0:
                if n.id == notes[i - 1].id:
                    continue
            n.print(file)
        file.write("0 TRLR\n")
