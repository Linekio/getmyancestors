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

    def test_empty_date(self):
        self.assertEqual(
            normalize_gedcom_date(None),
            (None, None),
        )


if __name__ == "__main__":
    unittest.main()
