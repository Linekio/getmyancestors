import io
import unittest

from getmyancestors.classes.gedcom import (
    Gedcom,
)
from getmyancestors.classes.tree import (
    Fact,
    Indi,
    Note,
    Ordinance,
    Tree,
)


class TestDateIntegration(
    unittest.TestCase
):
    def test_birth_date_export(self):
        fact = Fact(
            {
                "type": "http://gedcomx.org/Birth",
                "date": {
                    "original": "30 November 1989"
                },
                "attribution": {},
            }
        )

        output = io.StringIO()
        fact.print(output)

        self.assertIn(
            "2 DATE 30 NOV 1989\n",
            output.getvalue(),
        )

    def test_marriage_date_export(self):
        fact = Fact(
            {
                "type": "http://gedcomx.org/Marriage",
                "date": {
                    "original": "12/2/1882",
                    "formal": "+1882-12-02",
                },
                "attribution": {},
            }
        )

        output = io.StringIO()
        fact.print(output)

        self.assertIn(
            "2 DATE INT 02 DEC 1882 (12/2/1882)\n",
            output.getvalue(),
        )

    def test_ordinance_date_export(
        self,
    ):
        ordinance = Ordinance(
            {
                "completedDate": "30 November 1989",
                "status": "Ready",
            }
        )

        output = io.StringIO()
        ordinance.print(output)

        self.assertIn(
            "2 DATE 30 NOV 1989\n",
            output.getvalue(),
        )

    def test_unconverted_date_survives_roundtrip(
        self,
    ):
        original = "Possibly during the winter of the year 1850"

        tree = Tree()
        tree.display_name = "Test"
        tree.lang = "English"

        person = Indi(
            fid="TEST-123",
            tree=tree,
            num=1,
        )
        person.facts.add(
            Fact(
                {
                    "type": "http://gedcomx.org/Birth",
                    "date": {
                        "original": original
                    },
                    "attribution": {},
                },
                tree,
            )
        )

        tree.indi[person.fid] = person

        output = io.StringIO()
        tree.print(output)

        imported = Gedcom(
            io.StringIO(
                output.getvalue()
            ),
            Tree(),
        )

        imported_fact = next(
            iter(imported.indi[1].facts)
        )

        self.assertIsNone(
            imported_fact.date
        )
        self.assertIsNotNone(
            imported_fact.note
        )
        self.assertIn(
            original,
            imported_fact.note.text,
        )

    def test_multiline_note_has_no_trailing_spaces(
        self,
    ):
        note = Note(
            "First line   \nSecond line",
            num=99,
        )

        output = io.StringIO()
        note.print(output)

        for (
            line
        ) in (
            output.getvalue().splitlines()
        ):
            self.assertEqual(
                line,
                line.rstrip(" \t"),
            )


if __name__ == "__main__":
    unittest.main()
