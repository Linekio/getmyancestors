import io
import unittest

from getmyancestors.classes.gedcom import Gedcom
from getmyancestors.classes.tree import Fact, Indi, Name, Tree

SAMPLE_GEDCOM = """0 HEAD
1 CHAR UTF-8
1 GEDC
2 VERS 5.5.1
2 FORM LINEAGE-LINKED
0 @I1@ INDI
1 NAME John /Doe/
2 GIVN John
2 SURN Doe
1 SEX M
1 BIRT
2 DATE 1 JAN 1980
2 PLAC Springfield
1 FAMC @F1@
1 _FSFTID KW7V-Y32
0 @I2@ INDI
1 NAME Jane /Smith/
1 SEX F
1 FAMS @F1@
1 _FSFTID KW7V-Y33
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 CHIL @I3@
1 _FSFTID F123-456
0 @I3@ INDI
1 NAME Baby /Doe/
1 SEX M
1 FAMC @F1@
1 _FSFTID KW7V-Y34
0 TRLR
"""


class TestGedcomLogic(unittest.TestCase):
    def test_parse_gedcom(self):
        """Test parsing of a GEDCOM string using the Gedcom class."""
        f = io.StringIO(SAMPLE_GEDCOM)
        tree = Tree()

        # The Gedcom class takes a file-like object and a tree
        ged = Gedcom(f, tree)

        # Verify Individuals
        # The parser seems to use the number from @I{num}@ as the key in ged.indi
        self.assertIn(1, ged.indi)
        self.assertIn(2, ged.indi)
        self.assertIn(3, ged.indi)

        john = ged.indi[1]
        self.assertEqual(john.gender, "M")
        self.assertEqual(john.fid, "KW7V-Y32")

        # Check Name - The parsing logic for names is a bit complex in __get_name
        # It populates birthnames by default if no type is specified
        # BUT the first name found is assigned to self.name, NOT birthnames
        self.assertIsNotNone(john.name)
        self.assertEqual(john.name.given, "John")
        self.assertEqual(john.name.surname, "Doe")

        # Verify birthnames if any additional names present (none in this sample)
        # self.assertTrue(len(john.birthnames) > 0)

        # Verify Family
        self.assertIn(1, ged.fam)
        fam = ged.fam[1]
        self.assertEqual(fam.husb_num, 1)  # Points to I1
        self.assertEqual(fam.wife_num, 2)  # Points to I2
        self.assertIn(3, fam.chil_num)  # Points to I3
        self.assertEqual(fam.fid, "F123-456")

    def test_tree_export(self):
        """Test that a Tree object can be exported to GEDCOM format."""
        tree = Tree()
        tree.display_name = "Test User"
        tree.lang = "en"

        # Create Individual
        indi = Indi("KW7V-Y32", tree, num=1)
        indi.gender = "M"

        name = Name()
        name.given = "John"
        name.surname = "Doe"
        name.full = (
            "John Doe"  # Some print methods use .full if available or construct it
        )
        indi.birthnames.add(name)

        fact = Fact()
        fact.tag = "BIRT"
        fact.type = "http://gedcomx.org/Birth"
        fact.date = "1 JAN 1980"
        fact.place = tree.ensure_place("Springfield")
        indi.facts.add(fact)

        tree.indi["KW7V-Y32"] = indi

        # Validate output
        output = io.StringIO()
        tree.print(output)
        content = output.getvalue()

        self.assertIn("0 HEAD", content)
        self.assertIn("1 NAME John /Doe/", content)
        # ID is derived from fid if present
        self.assertIn("0 @IKW7V-Y32@ INDI", content)
        self.assertIn("1 SEX M", content)
        self.assertIn("1 BIRT", content)
        self.assertIn("2 DATE 1 JAN 1980", content)
        self.assertIn("0 TRLR", content)


if __name__ == "__main__":
    unittest.main()
