import io
import unittest

from getmyancestors.classes.tree import (
    Source,
)


class TestSourceExport(
    unittest.TestCase
):
    def test_source_header_has_no_trailing_spaces(
        self,
    ):
        source = Source(num=1)
        source.fid = "SOURCE-123"

        output = io.StringIO()
        source.print(output)

        expected = "0 @S1@ SOUR\n1 REFN SOURCE-123\n"

        self.assertEqual(
            expected, output.getvalue()
        )


if __name__ == "__main__":
    unittest.main()
