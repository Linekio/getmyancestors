"""Tests for GEDCOM fact descriptions."""

import io
import unittest

from getmyancestors.classes.gedcom import Gedcom
from getmyancestors.classes.tree import Fact, Fam, Tree


class TestFactDescriptions(unittest.TestCase):
    def make_fact(self, fact_type, value=None, date=None):
        data = {
            "type": fact_type,
            "attribution": {},
        }

        if value is not None:
            data["value"] = value

        if date is not None:
            data["date"] = {"original": date}

        return Fact(data, Tree())

    def export_fact(self, fact):
        output = io.StringIO()
        fact.print(output)
        return output.getvalue()

    def test_custom_fact_preserves_description(self):
        fact = self.make_fact(
            "data:,Military%20Award",
            "Awarded for volunteer service",
        )

        self.assertEqual(
            self.export_fact(fact),
            "1 FACT Awarded for volunteer service\n" "2 TYPE Military Award\n",
        )

    def test_custom_fact_without_value_uses_event(self):
        fact = self.make_fact("data:,Military%20Award")

        self.assertEqual(
            self.export_fact(fact),
            "1 EVEN\n" "2 TYPE Military Award\n",
        )

    def test_marriage_preserves_description(self):
        fact = self.make_fact(
            "http://gedcomx.org/Marriage",
            "Married at the family home",
            "12 MAR 1900",
        )

        self.assertEqual(
            self.export_fact(fact),
            "1 MARR\n"
            "2 DATE 12 MAR 1900\n"
            "2 NOTE Description: Married at the family home\n",
        )

    def test_marriage_without_description(self):
        fact = self.make_fact(
            "http://gedcomx.org/Marriage",
            date="12 MAR 1900",
        )

        self.assertEqual(
            self.export_fact(fact),
            "1 MARR\n" "2 DATE 12 MAR 1900\n",
        )

    def test_standard_attribute_is_unchanged(self):
        fact = self.make_fact(
            "http://gedcomx.org/Occupation",
            "Shipwright",
        )

        self.assertEqual(
            self.export_fact(fact),
            "1 OCCU Shipwright\n",
        )

    def test_custom_fact_survives_roundtrip(self):
        data = (
            "0 @I1@ INDI\n"
            "1 FACT Awarded for volunteer service\n"
            "2 TYPE Military Award\n"
            "0 TRLR\n"
        )

        imported = Gedcom(io.StringIO(data), Tree())
        fact = next(iter(imported.indi[1].facts))

        self.assertTrue(fact.custom)
        self.assertEqual(fact.type, "Military Award")
        self.assertEqual(
            fact.value,
            "Awarded for volunteer service",
        )

        self.assertEqual(
            self.export_fact(fact),
            "1 FACT Awarded for volunteer service\n" "2 TYPE Military Award\n",
        )

    def test_marriage_description_survives_roundtrip(self):
        data = (
            "0 @F1@ FAM\n"
            "1 MARR\n"
            "2 DATE 12 MAR 1900\n"
            "2 NOTE Description: Married at the family home\n"
            "0 TRLR\n"
        )

        imported = Gedcom(io.StringIO(data), Tree())
        fact = next(iter(imported.fam[1].facts))

        self.assertEqual(
            fact.type,
            "http://gedcomx.org/Marriage",
        )
        self.assertEqual(
            fact.value,
            "Married at the family home",
        )

        self.assertIn(
            "2 NOTE Description: Married at the family home\n",
            self.export_fact(fact),
        )

    def test_multiline_marriage_description(self):
        fact = self.make_fact(
            "http://gedcomx.org/Marriage",
            "Married in a chapel\nWitnesses attended",
        )

        exported = self.export_fact(fact)

        self.assertIn(
            "2 NOTE Description: Married in a chapel\n"
            "3 CONT Witnesses attended\n",
            exported,
        )

        imported = Gedcom(
            io.StringIO("0 @F1@ FAM\n" + exported + "0 TRLR\n"),
            Tree(),
        )

        imported_fact = next(iter(imported.fam[1].facts))

        self.assertEqual(
            imported_fact.value,
            "Married in a chapel\nWitnesses attended",
        )

    def test_regular_inline_note_is_preserved(self):
        data = (
            "0 @I1@ INDI\n"
            "1 BIRT\n"
            "2 NOTE Place documented in parish records\n"
            "0 TRLR\n"
        )

        imported = Gedcom(io.StringIO(data), Tree())
        fact = next(iter(imported.indi[1].facts))

        self.assertIsNone(fact.value)
        self.assertIsNotNone(fact.note)
        self.assertEqual(
            fact.note.text,
            "Place documented in parish records",
        )

    def test_regular_description_prefixed_note_is_preserved(self):
        data = (
            "0 @I1@ INDI\n"
            "1 BIRT\n"
            "2 NOTE Description: Original wording from the record\n"
            "0 TRLR\n"
        )

        imported = Gedcom(io.StringIO(data), Tree())
        fact = next(iter(imported.indi[1].facts))

        self.assertIsNone(fact.value)
        self.assertEqual(
            fact.note.text,
            "Description: Original wording from the record",
        )

    def test_marriage_note_is_not_assumed_to_be_a_description(self):
        data = (
            "0 @F1@ FAM\n"
            "1 MARR\n"
            "2 NOTE Witness details require verification\n"
            "0 TRLR\n"
        )

        imported = Gedcom(io.StringIO(data), Tree())
        fact = next(iter(imported.fam[1].facts))

        self.assertIsNone(fact.value)
        self.assertEqual(
            fact.note.text,
            "Witness details require verification",
        )

    def test_legacy_event_description_is_preserved(self):
        data = (
            "0 @I1@ INDI\n"
            "1 EVEN\n"
            "2 TYPE Military Award\n"
            "2 NOTE Description: Awarded for volunteer service\n"
            "0 TRLR\n"
        )

        imported = Gedcom(io.StringIO(data), Tree())
        fact = next(iter(imported.indi[1].facts))

        self.assertEqual(fact.type, "Military Award")
        self.assertEqual(
            fact.value,
            "Awarded for volunteer service",
        )

    def test_family_custom_fact_uses_event(self):
        fact = self.make_fact(
            "data:,Military%20Award",
            "Awarded for volunteer service",
        )

        family = Fam(tree=Tree(), num=1)
        family.facts.add(fact)

        output = io.StringIO()
        family.print(output)

        self.assertIn(
            "1 EVEN\n"
            "2 TYPE Military Award\n"
            "2 NOTE Description: Awarded for volunteer service\n",
            output.getvalue(),
        )

        imported = Gedcom(
            io.StringIO(output.getvalue() + "0 TRLR\n"),
            Tree(),
        )
        imported_fact = next(iter(imported.fam[1].facts))

        self.assertEqual(
            imported_fact.value,
            "Awarded for volunteer service",
        )


if __name__ == "__main__":
    unittest.main()
