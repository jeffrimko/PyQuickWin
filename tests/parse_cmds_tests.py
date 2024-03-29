"""Tests parse_cmds() function."""

##==============================================================#
## SECTION: Imports                                             #
##==============================================================#

from testlib import *

from pyquickwin import CommandKind, parse_cmds

##==============================================================#
## SECTION: Class Definitions                                   #
##==============================================================#

class TestCase(unittest.TestCase):

    def test_empty_input_should_return_empty_list(self):
        cmds = parse_cmds("")
        self.assertEqual(cmds, [])

    def test_blank_input_should_return_empty_list(self):
        cmds = parse_cmds("    ")
        self.assertEqual(cmds, [])

    def test_default_cmd_should_be_implicit_title(self):
        cmds = parse_cmds("hello")
        self.assertEqual(1, len(cmds))
        cmd = cmds[0]
        self.assertEqual(CommandKind.TITLE, cmd.kind)
        self.assertEqual("hello", cmd.text)

    def test_title_should_strip_whitespace_from_text(self):
        cmds = parse_cmds("  hello  ")
        self.assertEqual(1, len(cmds))
        cmd = cmds[0]
        self.assertEqual(CommandKind.TITLE, cmd.kind)
        self.assertEqual("hello", cmd.text)

    def test_title_can_be_input_explicitly(self):
        cmds = parse_cmds(";t hello")
        self.assertEqual(1, len(cmds))
        cmd = cmds[0]
        self.assertEqual(CommandKind.TITLE, cmd.kind)
        self.assertEqual("hello", cmd.text)

    def test_explicit_title_can_strip_whitespace(self):
        cmds = parse_cmds(";t  hello  ")
        self.assertEqual(1, len(cmds))
        cmd = cmds[0]
        self.assertEqual(CommandKind.TITLE, cmd.kind)
        self.assertEqual("hello", cmd.text)

    def test_explicit_title_can_parse_multiple_text_words(self):
        cmds = parse_cmds(";t hello world ")
        self.assertEqual(1, len(cmds))
        cmd = cmds[0]
        self.assertEqual(CommandKind.TITLE, cmd.kind)
        self.assertEqual("hello world", cmd.text)

    def test_set_alias_can_be_parsed(self):
        cmds = parse_cmds(";s alias")
        self.assertEqual(1, len(cmds))
        cmd = cmds[0]
        self.assertEqual(CommandKind.SET, cmd.kind)
        self.assertEqual("alias", cmd.text)

    def test_get_alias_can_be_parsed(self):
        cmds = parse_cmds(";g alias")
        self.assertEqual(1, len(cmds))
        cmd = cmds[0]
        self.assertEqual(CommandKind.GET, cmd.kind)
        self.assertEqual("alias", cmd.text)

    def test_order_can_be_parsed(self):
        cmds = parse_cmds(";o title")
        self.assertEqual(1, len(cmds))
        cmd = cmds[0]
        self.assertEqual(CommandKind.ORDER, cmd.kind)
        self.assertEqual("title", cmd.text)

    def test_executable_can_be_parsed(self):
        cmds = parse_cmds(";e notepad.exe")
        self.assertEqual(1, len(cmds))
        cmd = cmds[0]
        self.assertEqual(CommandKind.EXE, cmd.kind)
        self.assertEqual("notepad.exe", cmd.text)

    def test_limit_can_be_parsed(self):
        cmds = parse_cmds(";l")
        self.assertEqual(1, len(cmds))
        cmd = cmds[0]
        self.assertEqual(CommandKind.LIMIT, cmd.kind)
        self.assertEqual("", cmd.text)

    def test_delete_can_be_parsed(self):
        cmds = parse_cmds(";d")
        self.assertEqual(1, len(cmds))
        cmd = cmds[0]
        self.assertEqual(CommandKind.DELETE, cmd.kind)
        self.assertEqual("", cmd.text)

    def test_unknown_can_be_parsed(self):
        self.assertParsesToSingleUnkownCommand(";a")
        self.assertParsesToSingleUnkownCommand(";c")
        self.assertParsesToSingleUnkownCommand(";k")

    def test_multiple_commands_can_be_parsed(self):
        cmds = parse_cmds("hello world;e notepad.exe;s alias")
        self.assertEqual(3, len(cmds))
        cmd = cmds[0]
        self.assertEqual(CommandKind.TITLE, cmd.kind)
        self.assertEqual("hello world", cmd.text)
        cmd = cmds[1]
        self.assertEqual(CommandKind.EXE, cmd.kind)
        self.assertEqual("notepad.exe", cmd.text)
        cmd = cmds[2]
        self.assertEqual(CommandKind.SET, cmd.kind)
        self.assertEqual("alias", cmd.text)

    def test_multiple_commands_with_whitespace_between_can_be_parsed(self):
        cmds = parse_cmds("hello world  ;  e notepad.exe  ;  s alias")
        self.assertEqual(3, len(cmds))
        cmd = cmds[0]
        self.assertEqual(CommandKind.TITLE, cmd.kind)
        self.assertEqual("hello world", cmd.text)
        cmd = cmds[1]
        self.assertEqual(CommandKind.EXE, cmd.kind)
        self.assertEqual("notepad.exe", cmd.text)
        cmd = cmds[2]
        self.assertEqual(CommandKind.SET, cmd.kind)
        self.assertEqual("alias", cmd.text)

    def test_command_with_whitespace_between_semicolon_and_char_can_be_parsed(self):
        cmds = parse_cmds("; g alias ")
        self.assertEqual(1, len(cmds))
        cmd = cmds[0]
        self.assertEqual(CommandKind.GET, cmd.kind)
        self.assertEqual("alias", cmd.text)

    def test_limit_with_text_should_parse_as_unknown(self):
        self.assertParsesToSingleUnkownCommand(";l something")

    def test_delete_with_text_should_parse_as_unknown(self):
        self.assertParsesToSingleUnkownCommand(";d something")

    def test_commands_longer_than_single_char_should_parse_as_unknown(self):
        self.assertParsesToSingleUnkownCommand(";ge")
        self.assertParsesToSingleUnkownCommand(";get")
        self.assertParsesToSingleUnkownCommand(";set")
        self.assertParsesToSingleUnkownCommand(";title")
        self.assertParsesToSingleUnkownCommand(";delete")
        self.assertParsesToSingleUnkownCommand(";order")
        self.assertParsesToSingleUnkownCommand(";limit")
        self.assertParsesToSingleUnkownCommand(";exe")
        self.assertParsesToSingleUnkownCommand(";unkown")

    def assertParsesToSingleUnkownCommand(self, to_parse):
        cmds = parse_cmds(to_parse)
        self.assertEqual(1, len(cmds))
        cmd = cmds[0]
        self.assertEqual(CommandKind.UNKNOWN, cmd.kind)

##==============================================================#
## SECTION: Main Body                                           #
##==============================================================#

if __name__ == '__main__':
    unittest.main()
