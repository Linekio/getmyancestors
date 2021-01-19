#!/usr/bin/env python3
# coding: utf-8
"""
   getmyancestors.py - Retrieve GEDCOM data from FamilySearch Tree
   Copyright (C) 2014-2016 Giulio Genovese (giulio.genovese@gmail.com)

   This program is free software: you can redistribute it and/or modify
   it under the terms of the GNU General Public License as published by
   the Free Software Foundation, either version 3 of the License, or
   (at your option) any later version.

   This program is distributed in the hope that it will be useful,
   but WITHOUT ANY WARRANTY; without even the implied warranty of
   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
   GNU General Public License for more details.

   You should have received a copy of the GNU General Public License
   along with this program.  If not, see <http://www.gnu.org/licenses/>.

   Written by Giulio Genovese <giulio.genovese@gmail.com>
   and by Benoît Fontaine <benoitfontaine.ba@gmail.com>
"""

# global import
from __future__ import print_function
import re
import sys
import time
from urllib.parse import unquote
import getpass
import asyncio
import argparse
import requests
import babelfish

# local import
from translation import translations


# is subject to change: see https://www.familysearch.org/developers/docs/api/tree/Persons_resource
MAX_PERSONS = 200

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


def cont(string):
    """ parse a GEDCOM line adding CONT and CONT tags if necessary """
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


class Session:
    """ Create a FamilySearch session
        :param username and password: valid FamilySearch credentials
        :param verbose: True to active verbose mode
        :param logfile: a file object or similar
        :param timeout: time before retry a request
    """

    def __init__(self, username, password, verbose=False, logfile=False, timeout=60):
        self.username = username
        self.password = password
        self.verbose = verbose
        self.logfile = logfile
        self.timeout = timeout
        self.fid = self.lang = self.display_name = None
        self.counter = 0
        self.logged = self.login()

    def write_log(self, text):
        """ write text in the log file """
        log = "[%s]: %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), text)
        if self.verbose:
            sys.stderr.write(log)
        if self.logfile:
            self.logfile.write(log)

    def login(self):
        """ retrieve FamilySearch session ID
            (https://familysearch.org/developers/docs/guides/oauth2)
        """
        while True:
            try:
                url = "https://www.familysearch.org/auth/familysearch/login"
                self.write_log("Downloading: " + url)
                r = requests.get(url, params={"ldsauth": False}, allow_redirects=False)
                url = r.headers["Location"]
                self.write_log("Downloading: " + url)
                r = requests.get(url, allow_redirects=False)
                idx = r.text.index('name="params" value="')
                span = r.text[idx + 21 :].index('"')
                params = r.text[idx + 21 : idx + 21 + span]

                url = "https://ident.familysearch.org/cis-web/oauth2/v3/authorization"
                self.write_log("Downloading: " + url)
                r = requests.post(
                    url,
                    data={"params": params, "userName": self.username, "password": self.password},
                    allow_redirects=False,
                )

                if "The username or password was incorrect" in r.text:
                    self.write_log("The username or password was incorrect")
                    return False

                if "Invalid Oauth2 Request" in r.text:
                    self.write_log("Invalid Oauth2 Request")
                    time.sleep(self.timeout)
                    continue

                url = r.headers["Location"]
                self.write_log("Downloading: " + url)
                r = requests.get(url, allow_redirects=False)
                self.fssessionid = r.cookies["fssessionid"]
            except requests.exceptions.ReadTimeout:
                self.write_log("Read timed out")
                continue
            except requests.exceptions.ConnectionError:
                self.write_log("Connection aborted")
                time.sleep(self.timeout)
                continue
            except requests.exceptions.HTTPError:
                self.write_log("HTTPError")
                time.sleep(self.timeout)
                continue
            except KeyError:
                self.write_log("KeyError")
                time.sleep(self.timeout)
                continue
            except ValueError:
                self.write_log("ValueError")
                time.sleep(self.timeout)
                continue
            self.write_log("FamilySearch session id: " + self.fssessionid)
            self.set_current()
            return True

    def get_url(self, url, headers=None):
        """ retrieve JSON structure from a FamilySearch URL """
        self.counter += 1
        if headers is None:
            headers = {"Accept": "application/x-gedcomx-v1+json"}
        while True:
            try:
                self.write_log("Downloading: " + url)
                r = requests.get(
                    "https://familysearch.org" + url,
                    cookies={"fssessionid": self.fssessionid},
                    timeout=self.timeout,
                    headers=headers,
                )
            except requests.exceptions.ReadTimeout:
                self.write_log("Read timed out")
                continue
            except requests.exceptions.ConnectionError:
                self.write_log("Connection aborted")
                time.sleep(self.timeout)
                continue
            self.write_log("Status code: %s" % r.status_code)
            if r.status_code == 204:
                return None
            if r.status_code in {404, 405, 410, 500}:
                self.write_log("WARNING: " + url)
                return None
            if r.status_code == 401:
                self.login()
                continue
            try:
                r.raise_for_status()
            except requests.exceptions.HTTPError:
                self.write_log("HTTPError")
                if r.status_code == 403:
                    if (
                        "message" in r.json()["errors"][0]
                        and r.json()["errors"][0]["message"] == "Unable to get ordinances."
                    ):
                        self.write_log(
                            "Unable to get ordinances. "
                            "Try with an LDS account or without option -c."
                        )
                        return "error"
                    self.write_log(
                        "WARNING: code 403 from %s %s"
                        % (url, r.json()["errors"][0]["message"] or "")
                    )
                    return None
                time.sleep(self.timeout)
                continue
            try:
                return r.json()
            except Exception as e:
                self.write_log("WARNING: corrupted file from %s, error: %s" % (url, e))
                return None

    def set_current(self):
        """ retrieve FamilySearch current user ID, name and language """
        url = "/platform/users/current"
        data = self.get_url(url)
        if data:
            self.fid = data["users"][0]["personId"]
            self.lang = data["users"][0]["preferredLanguage"]
            self.display_name = data["users"][0]["displayName"]

    def _(self, string):
        """ translate a string into user's language
            TODO replace translation file for gettext format
        """
        if string in translations and self.lang in translations[string]:
            return translations[string][self.lang]
        return string


class Note:
    """ GEDCOM Note class
        :param text: the Note content
        :param tree: a Tree object
        :param num: the GEDCOM identifier
    """

    counter = 0

    def __init__(self, text="", tree=None, num=None):
        if num:
            self.num = num
        else:
            Note.counter += 1
            self.num = Note.counter
        self.text = text.strip()

        if tree:
            tree.notes.append(self)

    def print(self, file=sys.stdout):
        """ print Note in GEDCOM format """
        file.write(cont("0 @N%s@ NOTE %s" % (self.num, self.text)))

    def link(self, file=sys.stdout, level=1):
        """ print the reference in GEDCOM format """
        file.write("%s NOTE @N%s@\n" % (level, self.num))


class Source:
    """ GEDCOM Source class
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
                for n in data["notes"]:
                    if n["text"]:
                        self.notes.add(Note(n["text"], self.tree))

    def print(self, file=sys.stdout):
        """ print Source in GEDCOM format """
        file.write("0 @S%s@ SOUR \n" % self.num)
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
        """ print the reference in GEDCOM format """
        file.write("%s SOUR @S%s@\n" % (level, self.num))


class Fact:
    """ GEDCOM Fact class
        :param data: FS Fact data
        :param tree: a tree object
    """

    def __init__(self, data=None, tree=None):
        self.value = self.type = self.date = self.place = self.note = self.map = None
        if data:
            if "value" in data:
                self.value = data["value"]
            if "type" in data:
                self.type = data["type"]
                if self.type in FACT_EVEN:
                    self.type = tree.fs._(FACT_EVEN[self.type])
                elif self.type[:6] == "data:,":
                    self.type = unquote(self.type[6:])
                elif self.type not in FACT_TAGS:
                    self.type = None
            if "date" in data:
                self.date = data["date"]["original"]
            if "place" in data:
                place = data["place"]
                self.place = place["original"]
                if "description" in place and place["description"][1:] in tree.places:
                    self.map = tree.places[place["description"][1:]]
            if "changeMessage" in data["attribution"]:
                self.note = Note(data["attribution"]["changeMessage"], tree)
            if self.type == "http://gedcomx.org/Death" and not (self.date or self.place):
                self.value = "Y"

    def print(self, file=sys.stdout):
        """ print Fact in GEDCOM format
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
            file.write(cont("2 PLAC " + self.place))
        if self.map:
            latitude, longitude = self.map
            file.write("3 MAP\n4 LATI %s\n4 LONG %s\n" % (latitude, longitude))
        if self.note:
            self.note.link(file, 2)


class Memorie:
    """ GEDCOM Memorie class
        :param data: FS Memorie data
    """

    def __init__(self, data=None):
        self.description = self.url = None
        if data and "links" in data:
            self.url = data["about"]
            if "titles" in data:
                self.description = data["titles"][0]["value"]
            if "descriptions" in data:
                self.description = ("" if not self.description else self.description + "\n") + data[
                    "descriptions"
                ][0]["value"]

    def print(self, file=sys.stdout):
        """ print Memorie in GEDCOM format """
        file.write("1 OBJE\n2 FORM URL\n")
        if self.description:
            file.write(cont("2 TITL " + self.description))
        if self.url:
            file.write(cont("2 FILE " + self.url))


class Name:
    """ GEDCOM Name class
        :param data: FS Name data
        :param tree: a Tree object
    """

    def __init__(self, data=None, tree=None):
        self.given = ""
        self.surname = ""
        self.prefix = None
        self.suffix = None
        self.note = None
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
                self.note = Note(data["attribution"]["changeMessage"], tree)

    def print(self, file=sys.stdout, typ=None):
        """ print Name in GEDCOM format
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


class Ordinance:
    """ GEDCOM Ordinance class
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
        """ print Ordinance in Gecom format """
        if self.date:
            file.write(cont("2 DATE " + self.date))
        if self.temple_code:
            file.write("2 TEMP %s\n" % self.temple_code)
        if self.status in ORDINANCES_STATUS:
            file.write("2 STAT %s\n" % ORDINANCES_STATUS[self.status])
        if self.famc:
            file.write("2 FAMC @F%s@\n" % self.famc.num)


class Indi:
    """ GEDCOM individual class
        :param fid' FamilySearch id
        :param tree: a tree object
        :param num: the GEDCOM identifier
    """

    counter = 0

    def __init__(self, fid=None, tree=None, num=None):
        if num:
            self.num = num
        else:
            Indi.counter += 1
            self.num = Indi.counter
        self.fid = fid
        self.tree = tree
        self.famc_fid = set()
        self.fams_fid = set()
        self.famc_num = set()
        self.fams_num = set()
        self.name = None
        self.gender = None
        self.living = None
        self.parents = set()
        self.spouses = set()
        self.children = set()
        self.baptism = self.confirmation = self.initiatory = None
        self.endowment = self.sealing_child = None
        self.nicknames = set()
        self.facts = set()
        self.birthnames = set()
        self.married = set()
        self.aka = set()
        self.notes = set()
        self.sources = set()
        self.memories = set()

    def add_data(self, data):
        """ add FS individual data """
        if data:
            self.living = data["living"]
            for x in data["names"]:
                if x["preferred"]:
                    self.name = Name(x, self.tree)
                else:
                    if x["type"] == "http://gedcomx.org/Nickname":
                        self.nicknames.add(Name(x, self.tree))
                    if x["type"] == "http://gedcomx.org/BirthName":
                        self.birthnames.add(Name(x, self.tree))
                    if x["type"] == "http://gedcomx.org/AlsoKnownAs":
                        self.aka.add(Name(x, self.tree))
                    if x["type"] == "http://gedcomx.org/MarriedName":
                        self.married.add(Name(x, self.tree))
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
                            )
                        )
                    else:
                        self.facts.add(Fact(x, self.tree))
            if "sources" in data:
                sources = self.tree.fs.get_url("/platform/tree/persons/%s/sources" % self.fid)
                if sources:
                    quotes = dict()
                    for quote in sources["persons"][0]["sources"]:
                        quotes[quote["descriptionId"]] = (
                            quote["attribution"]["changeMessage"]
                            if "changeMessage" in quote["attribution"]
                            else None
                        )
                    for source in sources["sourceDescriptions"]:
                        if source["id"] not in self.tree.sources:
                            self.tree.sources[source["id"]] = Source(source, self.tree)
                        self.sources.add((self.tree.sources[source["id"]], quotes[source["id"]]))
            if "evidence" in data:
                url = "/platform/tree/persons/%s/memories" % self.fid
                memorie = self.tree.fs.get_url(url)
                if memorie and "sourceDescriptions" in memorie:
                    for x in memorie["sourceDescriptions"]:
                        if x["mediaType"] == "text/plain":
                            text = "\n".join(
                                val.get("value", "")
                                for val in x.get("titles", []) + x.get("descriptions", [])
                            )
                            self.notes.add(Note(text, self.tree))
                        else:
                            self.memories.add(Memorie(x))

    def add_fams(self, fams):
        """ add family fid (for spouse or parent)"""
        self.fams_fid.add(fams)

    def add_famc(self, famc):
        """ add family fid (for child) """
        self.famc_fid.add(famc)

    def get_notes(self):
        """ retrieve individual notes """
        notes = self.tree.fs.get_url("/platform/tree/persons/%s/notes" % self.fid)
        if notes:
            for n in notes["persons"][0]["notes"]:
                text_note = "=== %s ===\n" % n["subject"] if "subject" in n else ""
                text_note += n["text"] + "\n" if "text" in n else ""
                self.notes.add(Note(text_note, self.tree))

    def get_ordinances(self):
        """ retrieve LDS ordinances
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
        """ retrieve contributors """
        temp = set()
        url = "/platform/tree/persons/%s/changes" % self.fid
        data = self.tree.fs.get_url(url, {"Accept": "application/x-gedcomx-atom+json"})
        if data:
            for entries in data["entries"]:
                for contributors in entries["contributors"]:
                    temp.add(contributors["name"])
        if temp:
            text = "=== %s ===\n%s" % (self.tree.fs._("Contributors"), "\n".join(sorted(temp)))
            for n in self.tree.notes:
                if n.text == text:
                    self.notes.add(n)
                    return
            self.notes.add(Note(text, self.tree))

    def print(self, file=sys.stdout):
        """ print individual in GEDCOM format """
        file.write("0 @I%s@ INDI\n" % self.num)
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
        for num in self.fams_num:
            file.write("1 FAMS @F%s@\n" % num)
        for num in self.famc_num:
            file.write("1 FAMC @F%s@\n" % num)
        file.write("1 _FSFTID %s\n" % self.fid)
        for o in self.notes:
            o.link(file)
        for source, quote in self.sources:
            source.link(file, 1)
            if quote:
                file.write(cont("2 PAGE " + quote))


class Fam:
    """ GEDCOM family class
        :param husb: husbant fid
        :param wife: wife fid
        :param tree: a Tree object
        :param num: a GEDCOM identifier
    """

    counter = 0

    def __init__(self, husb=None, wife=None, tree=None, num=None):
        if num:
            self.num = num
        else:
            Fam.counter += 1
            self.num = Fam.counter
        self.husb_fid = husb if husb else None
        self.wife_fid = wife if wife else None
        self.tree = tree
        self.husb_num = self.wife_num = self.fid = None
        self.facts = set()
        self.sealing_spouse = None
        self.chil_fid = set()
        self.chil_num = set()
        self.notes = set()
        self.sources = set()

    def add_child(self, child):
        """ add a child fid to the family """
        if child not in self.chil_fid:
            self.chil_fid.add(child)

    def add_marriage(self, fid):
        """ retrieve and add marriage information
            :param fid: the marriage fid
        """
        if not self.fid:
            self.fid = fid
            url = "/platform/tree/couple-relationships/%s" % self.fid
            data = self.tree.fs.get_url(url)
            if data:
                if "facts" in data["relationships"][0]:
                    for x in data["relationships"][0]["facts"]:
                        self.facts.add(Fact(x, self.tree))
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
                                self.tree.sources[source["id"]] = Source(source, self.tree)
                    for source_fid in quotes:
                        self.sources.add((self.tree.sources[source_fid], quotes[source_fid]))

    def get_notes(self):
        """ retrieve marriage notes """
        if self.fid:
            notes = self.tree.fs.get_url("/platform/tree/couple-relationships/%s/notes" % self.fid)
            if notes:
                for n in notes["relationships"][0]["notes"]:
                    text_note = "=== %s ===\n" % n["subject"] if "subject" in n else ""
                    text_note += n["text"] + "\n" if "text" in n else ""
                    self.notes.add(Note(text_note, self.tree))

    def get_contributors(self):
        """ retrieve contributors """
        if self.fid:
            temp = set()
            url = "/platform/tree/couple-relationships/%s/changes" % self.fid
            data = self.tree.fs.get_url(url, {"Accept": "application/x-gedcomx-atom+json"})
            if data:
                for entries in data["entries"]:
                    for contributors in entries["contributors"]:
                        temp.add(contributors["name"])
            if temp:
                text = "=== %s ===\n%s" % (self.tree.fs._("Contributors"), "\n".join(sorted(temp)))
                for n in self.tree.notes:
                    if n.text == text:
                        self.notes.add(n)
                        return
                self.notes.add(Note(text, self.tree))

    def print(self, file=sys.stdout):
        """ print family information in GEDCOM format """
        file.write("0 @F%s@ FAM\n" % self.num)
        if self.husb_num:
            file.write("1 HUSB @I%s@\n" % self.husb_num)
        if self.wife_num:
            file.write("1 WIFE @I%s@\n" % self.wife_num)
        for num in self.chil_num:
            file.write("1 CHIL @I%s@\n" % num)
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
    """ family tree class
        :param fs: a Session object
    """

    def __init__(self, fs=None):
        self.fs = fs
        self.indi = dict()
        self.fam = dict()
        self.notes = list()
        self.sources = dict()
        self.places = dict()
        self.display_name = self.lang = None
        if fs:
            self.display_name = fs.display_name
            self.lang = babelfish.Language.fromalpha2(fs.lang).name

    def add_indis(self, fids):
        """ add individuals to the family tree
            :param fids: an iterable of fid
        """

        async def add_datas(loop, data):
            futures = set()
            for person in data["persons"]:
                self.indi[person["id"]] = Indi(person["id"], self)
                futures.add(loop.run_in_executor(None, self.indi[person["id"]].add_data, person))
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
                        if place["id"] not in self.places:
                            self.places[place["id"]] = (
                                str(place["latitude"]),
                                str(place["longitude"]),
                            )
                loop.run_until_complete(add_datas(loop, data))
                if "childAndParentsRelationships" in data:
                    for rel in data["childAndParentsRelationships"]:
                        father = rel["parent1"]["resourceId"] if "parent1" in rel else None
                        mother = rel["parent2"]["resourceId"] if "parent2" in rel else None
                        child = rel["child"]["resourceId"] if "child" in rel else None
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
                                self.indi[person1].spouses.add((person1, person2, relfid))
                            if person2 in self.indi:
                                self.indi[person2].spouses.add((person1, person2, relfid))
            new_fids = new_fids[MAX_PERSONS:]

    def add_fam(self, father, mother):
        """ add a family to the family tree
            :param father: the father fid or None
            :param mother: the mother fid or None
        """
        if (father, mother) not in self.fam:
            self.fam[(father, mother)] = Fam(father, mother, self)

    def add_trio(self, father, mother, child):
        """ add a children relationship to the family tree
            :param father: the father fid or None
            :param mother: the mother fid or None
            :param child: the child fid or None
        """
        if father in self.indi:
            self.indi[father].add_fams((father, mother))
        if mother in self.indi:
            self.indi[mother].add_fams((father, mother))
        if child in self.indi and (father in self.indi or mother in self.indi):
            self.indi[child].add_famc((father, mother))
            self.add_fam(father, mother)
            self.fam[(father, mother)].add_child(child)

    def add_parents(self, fids):
        """ add parents relationships
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
                    self.add_trio(father, mother, fid)
        return set(filter(None, parents))

    def add_spouses(self, fids):
        """ add spouse relationships
            :param fids: a set of fid
        """

        async def add(loop, rels):
            futures = set()
            for father, mother, relfid in rels:
                if (father, mother) in self.fam:
                    futures.add(
                        loop.run_in_executor(None, self.fam[(father, mother)].add_marriage, relfid)
                    )
            for future in futures:
                await future

        rels = set()
        for fid in fids & self.indi.keys():
            rels |= self.indi[fid].spouses
        loop = asyncio.get_event_loop()
        if rels:
            self.add_indis(set.union(*({father, mother} for father, mother, relfid in rels)))
            for father, mother, _ in rels:
                if father in self.indi and mother in self.indi:
                    self.indi[father].add_fams((father, mother))
                    self.indi[mother].add_fams((father, mother))
                    self.add_fam(father, mother)
            loop.run_until_complete(add(loop, rels))

    def add_children(self, fids):
        """ add children relationships
            :param fids: a set of fid
        """
        rels = set()
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
                    self.add_trio(father, mother, child)
                    children.add(child)
        return children

    def add_ordinances(self, fid):
        """ retrieve ordinances
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
        """ reset all GEDCOM identifiers """
        for husb, wife in self.fam:
            self.fam[(husb, wife)].husb_num = self.indi[husb].num if husb else None
            self.fam[(husb, wife)].wife_num = self.indi[wife].num if wife else None
            self.fam[(husb, wife)].chil_num = set(
                self.indi[chil].num for chil in self.fam[(husb, wife)].chil_fid
            )
        for fid in self.indi:
            self.indi[fid].famc_num = set(
                self.fam[(husb, wife)].num for husb, wife in self.indi[fid].famc_fid
            )
            self.indi[fid].fams_num = set(
                self.fam[(husb, wife)].num for husb, wife in self.indi[fid].fams_fid
            )

    def print(self, file=sys.stdout):
        """ print family tree in GEDCOM format """
        file.write("0 HEAD\n")
        file.write("1 CHAR UTF-8\n")
        file.write("1 GEDC\n")
        file.write("2 VERS 5.5.1\n")
        file.write("2 FORM LINEAGE-LINKED\n")
        file.write("1 SOUR getmyancestors\n")
        file.write("2 VERS 1.0\n")
        file.write("2 NAME getmyancestors\n")
        file.write("1 DATE %s\n" % time.strftime("%d %b %Y"))
        file.write("2 TIME %s\n" % time.strftime("%H:%M:%S"))
        file.write("1 SUBM @SUBM@\n")
        file.write("0 @SUBM@ SUBM\n")
        file.write("1 NAME %s\n" % self.display_name)
        file.write("1 LANG %s\n" % self.lang)

        for fid in sorted(self.indi, key=lambda x: self.indi.__getitem__(x).num):
            self.indi[fid].print(file)
        for husb, wife in sorted(self.fam, key=lambda x: self.fam.__getitem__(x).num):
            self.fam[(husb, wife)].print(file)
        sources = sorted(self.sources.values(), key=lambda x: x.num)
        for s in sources:
            s.print(file)
        notes = sorted(self.notes, key=lambda x: x.num)
        for i, n in enumerate(notes):
            if i > 0:
                if n.num == notes[i - 1].num:
                    continue
            n.print(file)
        file.write("0 TRLR\n")


def main():
    parser = argparse.ArgumentParser(
        description="Retrieve GEDCOM data from FamilySearch Tree (4 Jul 2016)",
        add_help=False,
        usage="getmyancestors.py -u username -p password [options]",
    )
    parser.add_argument("-u", "--username", metavar="<STR>", type=str, help="FamilySearch username")
    parser.add_argument("-p", "--password", metavar="<STR>", type=str, help="FamilySearch password")
    parser.add_argument(
        "-i",
        "--individuals",
        metavar="<STR>",
        nargs="+",
        type=str,
        help="List of individual FamilySearch IDs for whom to retrieve ancestors",
    )
    parser.add_argument(
        "-a",
        "--ascend",
        metavar="<INT>",
        type=int,
        default=4,
        help="Number of generations to ascend [4]",
    )
    parser.add_argument(
        "-d",
        "--descend",
        metavar="<INT>",
        type=int,
        default=0,
        help="Number of generations to descend [0]",
    )
    parser.add_argument(
        "-m",
        "--marriage",
        action="store_true",
        default=False,
        help="Add spouses and couples information [False]",
    )
    parser.add_argument(
        "-r",
        "--get-contributors",
        action="store_true",
        default=False,
        help="Add list of contributors in notes [False]",
    )
    parser.add_argument(
        "-c",
        "--get_ordinances",
        action="store_true",
        default=False,
        help="Add LDS ordinances (need LDS account) [False]",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=False,
        help="Increase output verbosity [False]",
    )
    parser.add_argument(
        "-t", "--timeout", metavar="<INT>", type=int, default=60, help="Timeout in seconds [60]"
    )
    parser.add_argument(
        "--show-password",
        action="store_true",
        default=False,
        help="Show password in .settings file [False]",
    )
    try:
        parser.add_argument(
            "-o",
            "--outfile",
            metavar="<FILE>",
            type=argparse.FileType("w", encoding="UTF-8"),
            default=sys.stdout,
            help="output GEDCOM file [stdout]",
        )
        parser.add_argument(
            "-l",
            "--logfile",
            metavar="<FILE>",
            type=argparse.FileType("w", encoding="UTF-8"),
            default=False,
            help="output log file [stderr]",
        )
    except TypeError:
        sys.stderr.write("Python >= 3.4 is required to run this script\n")
        sys.stderr.write("(see https://docs.python.org/3/whatsnew/3.4.html#argparse)\n")
        sys.exit(2)

    # extract arguments from the command line
    try:
        parser.error = parser.exit
        args = parser.parse_args()
    except SystemExit:
        parser.print_help(file=sys.stderr)
        sys.exit(2)
    if args.individuals:
        for fid in args.individuals:
            if not re.match(r"[A-Z0-9]{4}-[A-Z0-9]{3}", fid):
                sys.exit("Invalid FamilySearch ID: " + fid)

    args.username = args.username if args.username else input("Enter FamilySearch username: ")
    args.password = (
        args.password if args.password else getpass.getpass("Enter FamilySearch password: ")
    )

    time_count = time.time()

    # Report settings used when getmyancestors.py is executed.
    if args.outfile.name != "<stdout>":

        def parse_action(act):
            if not args.show_password and act.dest == "password":
                return "******"
            value = getattr(args, act.dest)
            return str(getattr(value, "name", value))

        formatting = "{:74}{:\t>1}\n"
        settings_name = args.outfile.name.split(".")[0] + ".settings"
        try:
            with open(settings_name, "w") as settings_file:
                settings_file.write(formatting.format("time stamp: ", time.strftime("%X %x %Z")))
                for action in parser._actions:
                    settings_file.write(
                        formatting.format(action.option_strings[-1], parse_action(action))
                    )
        except OSError as exc:
            print("Unable to write %s: %s" % (settings_name, repr(exc)), file=sys.stderr)

    # initialize a FamilySearch session and a family tree object
    print("Login to FamilySearch...", file=sys.stderr)
    fs = Session(args.username, args.password, args.verbose, args.logfile, args.timeout)
    if not fs.logged:
        sys.exit(2)
    _ = fs._
    tree = Tree(fs)

    # check LDS account
    if args.get_ordinances:
        test = fs.get_url("/service/tree/tree-data/reservations/person/%s/ordinances" % fs.fid, {})
        if test["status"] != "OK":
            sys.exit(2)

    try:
        # add list of starting individuals to the family tree
        todo = args.individuals if args.individuals else [fs.fid]
        print(_("Downloading starting individuals..."), file=sys.stderr)
        tree.add_indis(todo)

        # download ancestors
        todo = set(todo)
        done = set()
        for i in range(args.ascend):
            if not todo:
                break
            done |= todo
            print(_("Downloading %s. of generations of ancestors...") % (i + 1),
                  file=sys.stderr)
            todo = tree.add_parents(todo) - done

        # download descendants
        todo = set(tree.indi.keys())
        done = set()
        for i in range(args.descend):
            if not todo:
                break
            done |= todo
            print(_("Downloading %s. of generations of descendants...") %
                  (i + 1), file=sys.stderr)
            todo = tree.add_children(todo) - done

        # download spouses
        if args.marriage:
            print(_("Downloading spouses and marriage information..."),
                  file=sys.stderr)
            todo = set(tree.indi.keys())
            tree.add_spouses(todo)

        # download ordinances, notes and contributors
        async def download_stuff(loop):
            futures = set()
            for fid, indi in tree.indi.items():
                futures.add(loop.run_in_executor(None, indi.get_notes))
                if args.get_ordinances:
                    futures.add(loop.run_in_executor(None, tree.add_ordinances, fid))
                if args.get_contributors:
                    futures.add(loop.run_in_executor(None, indi.get_contributors))
            for fam in tree.fam.values():
                futures.add(loop.run_in_executor(None, fam.get_notes))
                if args.get_contributors:
                    futures.add(loop.run_in_executor(None, fam.get_contributors))
            for future in futures:
                await future

        loop = asyncio.get_event_loop()
        print(
            _("Downloading notes")
            + (
                (("," if args.get_contributors else _(" and")) + _(" ordinances"))
                if args.get_ordinances
                else ""
            )
            + (_(" and contributors") if args.get_contributors else "")
            + "...",
            file=sys.stderr
        )
        loop.run_until_complete(download_stuff(loop))

    finally:
        # compute number for family relationships and print GEDCOM file
        tree.reset_num()
        tree.print(args.outfile)
        print(
            _(
                "Downloaded %s individuals, %s families, %s sources and %s notes "
                "in %s seconds with %s HTTP requests."
            )
            % (
                str(len(tree.indi)),
                str(len(tree.fam)),
                str(len(tree.sources)),
                str(len(tree.notes)),
                str(round(time.time() - time_count)),
                str(fs.counter),
            ),
            file=sys.stderr
        )


if __name__ == "__main__":
    main()
