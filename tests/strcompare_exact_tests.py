"""Tests StrCompare.exact() method."""

##==============================================================#
## SECTION: Imports                                             #
##==============================================================#

from testlib import *
from testlib.strcompare import StrCompareTestCase

from pyquickwin import StrCompare

##==============================================================#
## SECTION: Class Definitions                                   #
##==============================================================#

class TestCase(StrCompareTestCase):

    def test_partial_input_should_not_return_match(self):
        self.assertFalse(StrCompare.exact("f", "finance"))
        self.assertFalse(StrCompare.exact("fin", "finance"))
        self.assertFalse(StrCompare.exact("financ", "finance"))

    def test_match_should_be_case_insensitive(self):
        self.assertTrue(StrCompare.exact("FINANCE", "finance"))
        self.assertTrue(StrCompare.exact("Finance", "finance"))

    def test_invalid_input_should_not_return_match(self):
        self.assertFalse(StrCompare.exact("-", "finance"))
        self.assertFalse(StrCompare.exact("x", "finance"))

##==============================================================#
## SECTION: Main Body                                           #
##==============================================================#

if __name__ == '__main__':
    unittest.main()
