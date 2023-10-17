"""Provides a library to aid testing."""

##==============================================================#
## SECTION: Imports                                             #
##==============================================================#

from io import StringIO
import os
import os.path as op
import sys
import subprocess
import unittest

appdir = op.normpath(op.join(op.abspath(op.dirname(__file__)), r"../app"))
sys.path.insert(0, appdir)
libdir = op.normpath(op.join(op.abspath(op.dirname(__file__)), r"../lib"))
sys.path.insert(0, libdir)
