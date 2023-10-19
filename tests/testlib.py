"""Provides a library to aid testing."""

##==============================================================#
## SECTION: Imports                                             #
##==============================================================#

import os.path as op
import sys
import unittest

##==============================================================#
## SECTION: Function Definitions                                #
##==============================================================#

def _add_relative_dir_to_syspath(reldir):
    absdir = op.normpath(op.join(op.abspath(op.dirname(__file__)), reldir))
    sys.path.insert(0, absdir)

##==============================================================#
## SECTION: Special Setup                                       #
##==============================================================#

_add_relative_dir_to_syspath("../app")
_add_relative_dir_to_syspath("../lib")
