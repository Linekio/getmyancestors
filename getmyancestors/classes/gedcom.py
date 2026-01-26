# mergemyancestors classes
from getmyancestors.classes.tree import (
    Indi,
    Fact,
    Fam,
    Memorie,
    Name,
    Note,
    Ordinance,
    Source,
)
from getmyancestors.classes.constants import FACT_TYPES, ORDINANCES


class Gedcom:
    """Parse a GEDCOM file into a Tree"""

    def __init__(self, file, tree):
        self.f = file
        self.num = None
        self.tree = tree
        self.level = 0
        self.pointer = None
        self.tag = None
        self.data = None
        self.flag = False
        self.indi = dict()
        self.fam = dict()
        self.note = dict()
        self.sour = dict()
        self.__parse()
        self.__add_id()

    def __parse(self):
        """Parse the GEDCOM file into self.tree"""
        while self.__get_line():
            if self.tag == "INDI":
                self.num = int(self.pointer[2 : len(self.pointer) - 1])
                self.indi[self.num] = Indi(tree=self.tree, num=self.num)
                self.__get_indi()
            elif self.tag == "FAM":
                self.num = int(self.pointer[2 : len(self.pointer) - 1])
                if self.num not in self.fam:
                    self.fam[self.num] = Fam(tree=self.tree, num=self.num)
                self.__get_fam()
            elif self.tag == "NOTE":
                self.num = int(self.pointer[2 : len(self.pointer) - 1])
                if self.num not in self.note:
                    self.note[self.num] = Note(tree=self.tree, num=self.num)
                self.__get_note()
            elif self.tag == "SOUR" and self.pointer:
                self.num = int(self.pointer[2 : len(self.pointer) - 1])
                if self.num not in self.sour:
                    self.sour[self.num] = Source(num=self.num)
                self.__get_source()
            elif self.tag == "SUBM" and self.pointer:
                self.__get_subm()

    def __get_subm(self):
        while self.__get_line() and self.level > 0:
            if not self.tree.display_name or not self.tree.lang:
                if self.tag == "NAME":
                    self.tree.display_name = self.data
                elif self.tag == "LANG":
                    self.tree.lang = self.data
        self.flag = True

    def __get_line(self):
        """Parse a new line
        If the flag is set, skip reading a newline
        """
        if self.flag:
            self.flag = False
            return True
        words = self.f.readline().split()

        if not words:
            return False
        self.level = int(words[0])
        if words[1][0] == "@":
            self.pointer = words[1]
            self.tag = words[2]
            self.data = " ".join(words[3:])
        else:
            self.pointer = None
            self.tag = words[1]
            self.data = " ".join(words[2:])
        return True

    def __get_indi(self):
        """Parse an individual (Analisa um registro de indivíduo no GEDCOM)"""
        # Continua lendo linhas enquanto houver linhas no arquivo e
        # o nível (level) da linha for maior que 0 (indicando que pertence ao INDI atual)
        while self.f and self.__get_line() and self.level > 0:
            # Verifica a tag (tipo de informação) da linha atual

            # --- NOME ---
            if self.tag == "NAME":
                # Chama o método específico para analisar o nome
                self.__get_name()

            # --- SEXO ---
            elif self.tag == "SEX":
                # Define o gênero do indivíduo ('M', 'F' ou 'U')
                self.indi[self.num].gender = self.data

            # --- FATOS/EVENTOS ---
            # Verifica se a tag é um tipo de fato conhecido ou um evento genérico
            elif self.tag in FACT_TYPES or self.tag == "EVEN":
                # Analisa o fato e o adiciona ao conjunto de fatos do indivíduo
                self.indi[self.num].facts.add(self.__get_fact())

            # --- ORDENAÇAS LDS ---
            elif self.tag == "BAPL":
                # Batismo LDS
                self.indi[self.num].baptism = self.__get_ordinance()
            elif self.tag == "CONL":
                # Confirmação LDS
                self.indi[self.num].confirmation = self.__get_ordinance()
            elif self.tag == "WAC":
                # Iniciática LDS
                self.indi[self.num].initiatory = self.__get_ordinance()
            elif self.tag == "ENDL":
                # Dote LDS
                self.indi[self.num].endowment = self.__get_ordinance()
            elif self.tag == "SLGC":
                # Selo aos pais LDS
                self.indi[self.num].sealing_child = self.__get_ordinance()

            # --- RELACIONAMENTOS FAMILIARES ---
            elif self.tag == "FAMS":
                # Adiciona o número da família onde este indivíduo é cônjuge
                # ao conjunto de números de família do cônjuge (fams_num)
                self.indi[self.num].fams_num.add(int(self.data[2 : len(self.data) - 1]))
            elif self.tag == "FAMC":
                # Adiciona o número da família onde este indivíduo é filho
                # ao conjunto de números de família filial (famc_num)
                self.indi[self.num].famc_num.add(int(self.data[2 : len(self.data) - 1]))

            # --- IDENTIFICADOR DO FAMILYSEARCH ---
            elif self.tag == "_FSFTID":
                # Armazena o ID do FamilySearch do indivíduo
                self.indi[self.num].fid = self.data

            # --- NOTAS ---
            elif self.tag == "NOTE":
                # Extrai o número da nota referenciada (@N123@ -> 123)
                num = int(self.data[2 : len(self.data) - 1])
                # Se a nota ainda não foi criada no dicionário temporário, cria
                if num not in self.note:
                    self.note[num] = Note(tree=self.tree, num=num)
                # Adiciona a nota ao conjunto de notas do indivíduo
                self.indi[self.num].notes.add(self.note[num])

            # --- FONTES ---
            elif self.tag == "SOUR":
                # Analisa o link para a fonte e adiciona ao indivíduo
                self.indi[self.num].sources.add(self.__get_link_source())

            # --- OBJETOS (Memórias) ---
            elif self.tag == "OBJE":
                # Analisa o objeto (memória) e adiciona ao indivíduo
                self.indi[self.num].memories.add(self.__get_memorie())

        # Define a flag para indicar que o parsing deste INDI terminou
        # e a próxima chamada a __get_line deve reutilizar a última linha lida
        self.flag = True

    def __get_fam(self):
        """Parse a family"""
        while self.__get_line() and self.level > 0:
            if self.tag == "HUSB":
                self.fam[self.num].husb_num = int(self.data[2 : len(self.data) - 1])
            elif self.tag == "WIFE":
                self.fam[self.num].wife_num = int(self.data[2 : len(self.data) - 1])
            elif self.tag == "CHIL":
                self.fam[self.num].chil_num.add(int(self.data[2 : len(self.data) - 1]))
            elif self.tag in FACT_TYPES:
                self.fam[self.num].facts.add(self.__get_fact())
            elif self.tag == "SLGS":
                self.fam[self.num].sealing_spouse = self.__get_ordinance()
            elif self.tag == "_FSFTID":
                self.fam[self.num].fid = self.data
            elif self.tag == "NOTE":
                num = int(self.data[2 : len(self.data) - 1])
                if num not in self.note:
                    self.note[num] = Note(tree=self.tree, num=num)
                self.fam[self.num].notes.add(self.note[num])
            elif self.tag == "SOUR":
                self.fam[self.num].sources.add(self.__get_link_source())
        self.flag = True

    def __get_name(self):
        """Parse a name"""
        parts = self.__get_text().split("/")
        name = Name()
        added = False
        name.given = parts[0].strip()
        name.surname = parts[1].strip()
        if parts[2]:
            name.suffix = parts[2]
        if not self.indi[self.num].name:
            self.indi[self.num].name = name
            added = True
        while self.__get_line() and self.level > 1:
            if self.tag == "NPFX":
                name.prefix = self.data
            elif self.tag == "TYPE":
                if self.data == "aka":
                    self.indi[self.num].aka.add(name)
                    added = True
                elif self.data == "married":
                    self.indi[self.num].married.add(name)
                    added = True
            elif self.tag == "NICK":
                nick = Name()
                nick.given = self.data
                self.indi[self.num].nicknames.add(nick)
            elif self.tag == "NOTE":
                num = int(self.data[2 : len(self.data) - 1])
                if num not in self.note:
                    self.note[num] = Note(tree=self.tree, num=num)
                name.note = self.note[num]
        if not added:
            self.indi[self.num].birthnames.add(name)
        self.flag = True

    def __get_fact(self):
        """Parse a fact"""
        fact = Fact()
        if self.tag != "EVEN":
            fact.type = FACT_TYPES[self.tag]
            fact.value = self.data
        while self.__get_line() and self.level > 1:
            if self.tag == "TYPE":
                fact.type = self.data
            if self.tag == "DATE":
                fact.date = self.__get_text()
            elif self.tag == "PLAC":
                fact.place = self.__get_text()
            elif self.tag == "MAP":
                fact.map = self.__get_map()
            elif self.tag == "NOTE":
                if self.data[:12] == "Description:":
                    fact.value = self.data[13:]
                    continue
                num = int(self.data[2 : len(self.data) - 1])
                if num not in self.note:
                    self.note[num] = Note(tree=self.tree, num=num)
                fact.note = self.note[num]
            elif self.tag == "CONT":
                fact.value += "\n" + self.data
            elif self.tag == "CONC":
                fact.value += self.data
        self.flag = True
        return fact

    def __get_map(self):
        """Parse map coordinates"""
        latitude = None
        longitude = None
        while self.__get_line() and self.level > 3:
            if self.tag == "LATI":
                latitude = self.data
            elif self.tag == "LONG":
                longitude = self.data
        self.flag = True
        return (latitude, longitude)

    def __get_text(self):
        """Parse a multiline text"""
        text = self.data
        while self.__get_line():
            if self.tag == "CONT":
                text += "\n" + self.data
            elif self.tag == "CONC":
                text += self.data
            else:
                break
        self.flag = True
        return text

    def __get_source(self):
        """Parse a source"""
        while self.__get_line() and self.level > 0:
            if self.tag == "TITL":
                self.sour[self.num].title = self.__get_text()
            elif self.tag == "AUTH":
                self.sour[self.num].citation = self.__get_text()
            elif self.tag == "PUBL":
                self.sour[self.num].url = self.__get_text()
            elif self.tag == "REFN":
                self.sour[self.num].fid = self.data
                if self.data in self.tree.sources:
                    self.sour[self.num] = self.tree.sources[self.data]
                else:
                    self.tree.sources[self.data] = self.sour[self.num]
            elif self.tag == "NOTE":
                num = int(self.data[2 : len(self.data) - 1])
                if num not in self.note:
                    self.note[num] = Note(tree=self.tree, num=num)
                self.sour[self.num].notes.add(self.note[num])
        self.flag = True

    def __get_link_source(self):
        """Parse a link to a source"""
        num = int(self.data[2 : len(self.data) - 1])
        if num not in self.sour:
            self.sour[num] = Source(num=num)
        page = None
        while self.__get_line() and self.level > 1:
            if self.tag == "PAGE":
                page = self.__get_text()
        self.flag = True
        return (self.sour[num], page)

    def __get_memorie(self):
        """Parse a memorie"""
        memorie = Memorie()
        while self.__get_line() and self.level > 1:
            if self.tag == "TITL":
                memorie.description = self.__get_text()
            elif self.tag == "FILE":
                memorie.url = self.__get_text()
        self.flag = True
        return memorie

    def __get_note(self):
        """Parse a note"""
        self.note[self.num].text = self.__get_text()
        self.flag = True

    def __get_ordinance(self):
        """Parse an ordinance"""
        ordinance = Ordinance()
        while self.__get_line() and self.level > 1:
            if self.tag == "DATE":
                ordinance.date = self.__get_text()
            elif self.tag == "TEMP":
                ordinance.temple_code = self.data
            elif self.tag == "STAT":
                ordinance.status = ORDINANCES[self.data]
            elif self.tag == "FAMC":
                num = int(self.data[2 : len(self.data) - 1])
                if num not in self.fam:
                    self.fam[num] = Fam(tree=self.tree, num=num)
                ordinance.famc = self.fam[num]
        self.flag = True
        return ordinance

    def __add_id(self):
        """Reset GEDCOM identifiers"""
        for num in self.fam:
            if self.fam[num].husb_num:
                self.fam[num].husb_fid = self.indi[self.fam[num].husb_num].fid
            if self.fam[num].wife_num:
                self.fam[num].wife_fid = self.indi[self.fam[num].wife_num].fid
            for chil in self.fam[num].chil_num:
                self.fam[num].chil_fid.add(self.indi[chil].fid)
        for num in self.indi:
            for famc in self.indi[num].famc_num:
                self.indi[num].famc_fid.add(
                    (self.fam[famc].husb_fid, self.fam[famc].wife_fid)
                )
            for fams in self.indi[num].fams_num:
                self.indi[num].fams_fid.add(
                    (self.fam[fams].husb_fid, self.fam[fams].wife_fid)
                )
