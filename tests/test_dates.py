import unittest

from getmyancestors.classes.dates import (
    normalize_gedcom_date,
)


class TestGedcomDates(
    unittest.TestCase
):
    def test_supported_dates(self):
        cases = (
            (
                "30 November 1989",
                None,
                "30 NOV 1989",
            ),
            (
                "7/16/1956",
                None,
                "16 JUL 1956",
            ),
            (
                "16/7/1956",
                None,
                "16 JUL 1956",
            ),
            (
                "15 de marzo de 1872",
                None,
                "15 MAR 1872",
            ),
            (
                "14 de xuño de 1880",
                None,
                "14 JUN 1880",
            ),
            (
                "March 1850",
                None,
                "MAR 1850",
            ),
            (
                "about 1850",
                None,
                "ABT 1850",
            ),
            (
                "hacia 1850",
                None,
                "ABT 1850",
            ),
            (
                "BEF 1870",
                None,
                "BEF 1870",
            ),
            (
                "AFT 1870",
                None,
                "AFT 1870",
            ),
            (
                "between 1850 and 1860",
                None,
                "BET 1850 AND 1860",
            ),
            (
                "entre 1850 y 1860",
                None,
                "BET 1850 AND 1860",
            ),
            (
                "FROM 1850 TO 1860",
                None,
                "FROM 1850 TO 1860",
            ),
            ("1850", None, "1850"),
            (
                "NOV 1880",
                None,
                "NOV 1880",
            ),
            (
                "1882-12-02",
                None,
                "02 DEC 1882",
            ),
            (
                "29 FEB 2000",
                None,
                "29 FEB 2000",
            ),
        )

        for (
            original,
            formal,
            expected,
        ) in cases:
            with self.subTest(
                original=original
            ):
                self.assertEqual(
                    normalize_gedcom_date(
                        original, formal
                    ),
                    (expected, None),
                )

    def test_ambiguous_date_without_formal(
        self,
    ):
        self.assertEqual(
            normalize_gedcom_date(
                "12/2/1882"
            ),
            ("(12/2/1882)", None),
        )

    def test_ambiguous_date_with_formal(
        self,
    ):
        self.assertEqual(
            normalize_gedcom_date(
                "12/2/1882",
                "+1882-12-02",
            ),
            (
                "INT 02 DEC 1882 (12/2/1882)",
                None,
            ),
        )

    def test_invalid_date_is_not_invented(
        self,
    ):
        self.assertEqual(
            normalize_gedcom_date(
                "29 FEB 1900"
            ),
            ("(29 FEB 1900)", None),
        )

    def test_long_unrecognized_date_is_preserved(
        self,
    ):
        original = "Possibly during the winter of the year 1850"
        self.assertEqual(
            normalize_gedcom_date(
                original
            ),
            (None, original),
        )

    def test_formal_dates_support_original_text_in_other_languages(self):
        cases = (
            ("12 mars 1892", "+1892-03-12", "INT 12 MAR 1892 (12 mars 1892)"),
            ("12 März 1892", "+1892-03-12", "INT 12 MAR 1892 (12 März 1892)"),
            ("12 novembre 1989", "+1989-11-12", "INT 12 NOV 1989 (12 novembre 1989)"),
            ("5 mei 1870", "+1870-05-05", "INT 05 MAY 1870 (5 mei 1870)"),
        )
        for original, formal, expected in cases:
            with self.subTest(original=original):
                self.assertEqual(
                    normalize_gedcom_date(original, formal),
                    (expected, None),
                )

    def test_formal_approximation_is_not_made_exact(self):
        self.assertEqual(
            normalize_gedcom_date("vers 1892", "A+1892"),
            ("ABT 1892", "vers 1892"),
        )
        self.assertEqual(
            normalize_gedcom_date("", "A+1880-03"),
            ("ABT MAR 1880", None),
        )

    def test_formal_date_does_not_override_conflicting_year(self):
        self.assertEqual(
            normalize_gedcom_date("12 mars 1892", "+1900-03-12"),
            ("(12 mars 1892)", None),
        )

    def test_formal_date_does_not_override_invalid_original(self):
        self.assertEqual(
            normalize_gedcom_date("29 FEB 1900", "+1900-03-01"),
            ("(29 FEB 1900)", None),
        )
        self.assertEqual(
            normalize_gedcom_date("1800-02-30", "+1800-03-01"),
            ("(1800-02-30)", None),
        )

    def test_unresolved_numeric_date_is_not_guessed(self):
        self.assertEqual(
            normalize_gedcom_date("12/2/1882", "+1882-11-03"),
            ("(12/2/1882)", None),
        )
        self.assertEqual(
            normalize_gedcom_date("12/2/1882", "+1882"),
            ("(12/2/1882)", None),
        )

    def test_original_text_survives_when_interpretation_is_too_long(self):
        original = "Possibly during the winter of the year 1850"
        self.assertEqual(
            normalize_gedcom_date(original, "+1850"),
            ("1850", original),
        )

    def test_complex_formal_dates_are_not_misread_as_simple_dates(self):
        for formal in ("+1850/+1860", "-0044", "R4/+1776/+1786", "+1892-03-12T15:00Z"):
            with self.subTest(formal=formal):
                self.assertEqual(
                    normalize_gedcom_date(None, formal),
                    (None, formal),
                )

    def test_empty_date(self):
        self.assertEqual(
            normalize_gedcom_date(None),
            (None, None),
        )


if __name__ == "__main__":
    unittest.main()
