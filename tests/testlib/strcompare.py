from base import *
from pyquickwin import StrCompare

##==============================================================#
## SECTION: Class Definitions                                   #
##==============================================================#

class StrCompareTestCase(unittest.TestCase):

    def test_no_target_should_not_return_match(self):
        self.assertFalse(StrCompare.exact("finance", ""))

    def test_no_input_or_test_should_return_match(self):
        self.assertTrue(StrCompare.exact("", ""))

    def test_empty_input_should_return_match(self):
        self.assertTrue(StrCompare.progressive("", "finance"))

    def test_exact_input_should_return_match(self):
        self.assertTrue(StrCompare.progressive("finance", "finance"))

##==============================================================#
## SECTION: Main Body                                           #
##==============================================================#

if __name__ == '__main__':
    unittest.main()
