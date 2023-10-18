"""Tests StrCompare.progressive() method."""

##==============================================================#
## SECTION: Imports                                             #
##==============================================================#

from testlib import *

from pyquickwin import StrCompare

##==============================================================#
## SECTION: Class Definitions                                   #
##==============================================================#

class TestCase(unittest.TestCase):

    def test_partial_input_should_return_match(self):
        self.assertTrue(StrCompare.progressive("f", "finance"))
        self.assertTrue(StrCompare.progressive("fin", "finance"))
        self.assertTrue(StrCompare.progressive("fnc", "finance"))
        self.assertTrue(StrCompare.progressive("fce", "finance"))
        self.assertTrue(StrCompare.progressive("face", "finance"))
        self.assertTrue(StrCompare.progressive("ice", "finance"))
        self.assertTrue(StrCompare.progressive("nn", "finance"))
        self.assertTrue(StrCompare.progressive("financ", "finance"))

    def test_empty_input_should_return_match(self):
        self.assertTrue(StrCompare.progressive("", "finance"))

    def test_exact_input_should_return_match(self):
        self.assertTrue(StrCompare.progressive("finance", "finance"))

    def test_match_should_be_case_insensitive(self):
        self.assertTrue(StrCompare.progressive("F", "finance"))
        self.assertTrue(StrCompare.progressive("FIN", "finance"))
        self.assertTrue(StrCompare.progressive("FINANCE", "finance"))
        self.assertTrue(StrCompare.progressive("Finance", "finance"))

    def test_invalid_input_should_not_return_match(self):
        self.assertFalse(StrCompare.progressive("-", "finance"))
        self.assertFalse(StrCompare.progressive("x", "finance"))
        self.assertFalse(StrCompare.progressive("n i f", "finance"))
        self.assertFalse(StrCompare.progressive("f i n", "finance"))
        self.assertFalse(StrCompare.progressive("nif", "finance"))
        self.assertFalse(StrCompare.progressive("ecnanif", "finance"))
        self.assertFalse(StrCompare.progressive("nnn", "finance"))
        self.assertFalse(StrCompare.progressive("nin", "finance"))

##==============================================================#
## SECTION: Main Body                                           #
##==============================================================#

if __name__ == '__main__':
    unittest.main()

