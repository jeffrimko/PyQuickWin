##==============================================================#
## SECTION: Imports                                             #
##==============================================================#

from dataclasses import dataclass, asdict
from enum import Enum, auto
from operator import attrgetter
from typing import Dict, List, Optional
import configparser
import csv
import sys
import os

from auxly.filesys import Dir, File, abspath, walkfiles, walkdirs
import auxly
import ujson
import yaml

from qwindow import App, Config, ProcessorBase, ProcessorOutput, MenuItem, SubprocessorBase, subprocessors
from winctrl import WinControl, WinInfo

##==============================================================#
## SECTION: Class Definitions                                   #
##==============================================================#

class CommandKind(Enum):
    UNK = auto()
    TITLE = auto()
    EXE = auto()
    SET = auto()
    GET = auto()
    LIM = auto()
    DEL = auto()
    ORD = auto()

@dataclass
class Command:
    kind: CommandKind
    text: str

class WinExcluder:
    def __init__(self, exclude_path):
        self._exclude_path = exclude_path
        self._excludes = []
        self.reload_exclusions()

    def reload_exclusions(self):
        self._excludes = []
        with open(self._exclude_path, newline='') as csvfile:
            reader = csv.reader(csvfile)
            for row in reader:
                self._excludes.append(row)

    def is_excluded(self, winfo: WinInfo):
        for title,exe in self._excludes:
            if title and exe and title == winfo.title and exe == winfo.exe:
                return True
            elif title and title == winfo.title:
                return True
            elif exe and exe == winfo.exe:
                return True
        return False

class WinManager:
    def __init__(self, alias_path, exclude_path):
        #: List of all known windows.
        self._allwins: List[WinInfo] = []

        #: Index numbers of known windows included in output.
        self._outwinnums: List[int] = []

        self._alias_file = File(alias_path)
        self._alias: Dict[WinInfo, str] = self._load_alias_file()
        self._selected_outwinnum = 0
        self._excluder = WinExcluder(exclude_path)

    def reload_exclusions(self):
        self._excluder.reload_exclusions()

    def reset(self, orderby):
        self._allwins = []
        winlist = WinControl.list()
        if orderby:
            winlist.sort(key=attrgetter(orderby))
        for win in winlist:
            if self._excluder.is_excluded(win):
                continue
            self._allwins.append(win)
        self._reset_outwinnums()

    def update(self, pinput):
        self._selected_outwinnum = self._get_outwinnum(pinput.lstview.selnum)
        if pinput.was_hidden:
            self._selected_outwinnum = 0
        self._reset_outwinnums()

    def filter(self, cmdtext, getwintext=None):
        default = lambda w: self._alias.get(w)
        def compare(wnum):
            wintext = (getwintext or default)(self._allwins[wnum])
            if wintext is None:
                return False
            return StrCompare.choice(cmdtext, wintext)
        self._outwinnums = list(filter(compare, self._outwinnums))
        try:
            self._outwinnums.index(self._selected_outwinnum)
        except ValueError:
            if self._outwinnums and self._selected_outwinnum is not None:
                self._selected_outwinnum = min(
                    self._outwinnums,
                    key=lambda n: abs(n - self._selected_outwinnum)
                )
            else:
                self._selected_outwinnum = None

    @property
    def selected_winfo(self):
        if self._selected_outwinnum is None: return None
        rownum = self._outwinnums.index(self._selected_outwinnum)
        winfo = self._get_winfo(rownum)
        return winfo

    @property
    def selected_rownum(self):
        if self._selected_outwinnum is None: return None
        return self._outwinnums.index(self._selected_outwinnum)

    @property
    def len_outwins(self):
        return len(self._outwinnums)

    def iter_out(self):
        for num in self._outwinnums:
            yield num, self._allwins[num]

    @property
    def len_allwins(self):
        return len(self._allwins)

    def get_alias(self, winfo):
        return self._alias.get(winfo, "")

    def set_alias(self, winfo, alias):
        alias_lookup = dict(zip(self._alias.values(), self._alias.keys()))
        alias_winfo = alias_lookup.get(alias, None)
        self._alias.pop(alias_winfo, None)
        self._alias[winfo] = alias
        self._save_alias_file()

    def delete_all_alias(self):
        self._alias = {}
        self._save_alias_file()

    def _save_alias_file(self):
        outlist = []
        prune = []
        for k,v in self._alias.items():
            if not v or k not in self._allwins:
                prune.append(k)
            else:
                outlist.append([asdict(k), v])
        self._alias_file.write(ujson.dumps(outlist))
        for p in prune:
            del self._alias[p]

    def _load_alias_file(self):
        alias = {}
        try:
            inlist = ujson.loads(self._alias_file.read())
        except TypeError:
            return alias
        for i in inlist:
            alias[WinInfo(**i[0])] = i[1]
        return alias

    def _get_winfo(self, rownum) -> Optional[WinInfo]:
        try:
            return self._allwins[self._outwinnums[rownum]]
        except IndexError:
            return None

    def _reset_outwinnums(self):
        self._outwinnums = list(range(len(self._allwins)))

    def _get_outwinnum(self, rownum):
        if not self._outwinnums:
            return None
        try:
            return self._outwinnums[rownum if rownum > 0 else 0]
        except IndexError:
            return None

class MathProcessor(SubprocessorBase):
    PREFIX = "="

    @property
    def help(self) -> str:
        return "Math processor prefix: " + MathProcessor.PREFIX

    def use_processor(self, pinput):
        if len(pinput.cmdtext.text) == 0:
            return False
        return pinput.cmdtext.text[0] == MathProcessor.PREFIX

    def update(self, pinput):
        cmdtext = pinput.cmdtext.text.split("=", maxsplit=1)[1]
        output = ProcessorOutput()
        output.hide_rows()
        try:
            result = eval(cmdtext)
            output.add_out(f"Result: {result}")
        except:
            output.add_out(f"Result:")
        return output

class ExploreProcessor(SubprocessorBase):
    PREFIX = ">"
    def __init__(self, path):
        self._path = path
        self._cfg = {}
        self._selected = None
        self.reload_config()

    @property
    def help(self) -> str:
        return "Explore processor prefix: " + ExploreProcessor.PREFIX

    def reload_config(self):
        self._cfg = yaml.safe_load(File(self._path).read())
        self._selected = None

    def use_processor(self, pinput):
        if len(pinput.cmdtext.text) == 0:
            self._selected = None
            return False
        return pinput.cmdtext.text.startswith(ExploreProcessor.PREFIX)

    def update(self, pinput):
        cmdtext = pinput.cmdtext.text[1:].lstrip()
        if self._selected is None:
            return self._show_root(pinput, cmdtext)
        return self._show_selected(pinput, cmdtext)

    def _show_selected(self, pinput, cmdtext):
        if pinput.is_complete:
            name, path = pinput.get_selrow()
            dpath = Dir(path, name)
            auxly.open(dpath)
            return ProcessorOutput(hide=True)
        rows = []
        selected = self._cfg[self._selected]
        outtext = []
        outtext.append(f"Exploring: {self._selected}")
        for path in selected:
            if not Dir(path).exists():
                outtext.append(f"Path not found: {path}")
                continue
            for dpath in walkdirs(path):
                name = dpath.name
                if name.startswith(".") or name.startswith("__"):
                    continue
                if not StrCompare.choice(cmdtext, name):
                    continue
                rows.append([name, path])
        output = ProcessorOutput()
        output.add_rows(
            ["Name", "Path"],
            [1, 1],
            rows,
            pinput.lstview.selnum
        )
        output.add_out("\n".join(outtext))
        return output

    def _show_root(self, pinput, cmdtext):
        if pinput.is_complete:
            self._selected = pinput.get_selrow()[0]
            output = ProcessorOutput()
            output.add_cmd(ExploreProcessor.PREFIX)
            return output
        rows = []
        for k in self._cfg.keys():
            if not StrCompare.choice(cmdtext, k):
                continue
            rows.append([k])
        output = ProcessorOutput()
        output.add_rows(
            ["Name"],
            [1],
            rows,
            pinput.lstview.selnum
        )
        output.add_out("Select an item")
        return output

class LaunchProcessor(SubprocessorBase):
    PREFIX = ":"
    def __init__(self, path):
        self._path = path

    @property
    def help(self) -> str:
        return "Launch processor prefix: " + LaunchProcessor.PREFIX

    def use_processor(self, pinput):
        if len(pinput.cmdtext.text) == 0:
            return False
        return pinput.cmdtext.text[0] == LaunchProcessor.PREFIX

    def update(self, pinput):
        if pinput.is_complete:
            stem,ext = pinput.get_selrow()
            selpath = File(self._path, stem + ext)
            auxly.open(selpath)
            return ProcessorOutput(hide=True)
        cmdtext = pinput.cmdtext.text[1:].lstrip()
        output = ProcessorOutput()
        rows = []
        for f in walkfiles(self._path):
            if not StrCompare.choice(cmdtext, f.name):
                continue
            rows.append([f.stem, f.ext])
        output.add_out(f"Items found: {len(rows)}")
        output.add_rows(
            ["Name", "Ext"],
            [3,1],
            rows,
            pinput.lstview.selnum
        )
        return output

class Processor(ProcessorBase):
    def __init__(self, alias_path, exclude_path, subprocessors=None):
        self._outtext: List[str] = []
        self._orderby = ""
        self._winmgr = WinManager(alias_path, exclude_path)
        self._subprocessors = subprocessors or []

    @property
    def help(self) -> str:
        lines = [
            'PyQuickWin commands:',
            '    Filters: t <TITLE> | e <EXECUTABLE> | l (current exe)',
            '    Aliases: s <SET> | g <GET> | d (delete all)',
            '    Col Order: o <TITLE|EXE>'
        ]
        msg = os.linesep.join(lines) + os.linesep
        for sub in self._subprocessors:
            msg += sub.help + os.linesep
        return msg

    @subprocessors
    def update(self, pinput):
        self._winmgr.update(pinput)
        cmds = parse(pinput.cmdtext.text)
        if (not pinput.cmdtext.text) and (not cmds):
            self._winmgr.reset(self._orderby)

        cmd_on_complete = self._handle_incomplete(cmds)
        if pinput.is_complete:
            return self._handle_complete(cmd_on_complete)
        return self._render_rows()

    def reload_exclusions(self):
        self._winmgr.reload_exclusions()

    def _render_rows(self):
        self._outtext.append(f'Windows found: {self._winmgr.len_outwins}')
        self._outtext.append(f'Ordering rows by: {self._orderby or "default"}')
        rows = []
        for num, win in self._winmgr.iter_out():
            rows.append([
                format_num(num + 1, self._winmgr.len_allwins),
                win.title,
                win.exe,
                self._winmgr.get_alias(win)
            ])
        output = ProcessorOutput()
        output.add_out(self._render_outtext())
        output.add_rows(
            ["Number", "Title", "Executable", "Alias"],
            [6, 74, 10, 10],
            rows,
            self._winmgr.selected_rownum
        )
        return output

    def _render_outtext(self):
        if not self._outtext:
            return None
        outtext = ""
        for line in self._outtext:
            outtext += line + "\n"
        self._outtext = []
        return outtext

    def _handle_incomplete(self, cmds):
        cmd_on_complete = None
        for cmd in cmds:
            if cmd.kind == CommandKind.TITLE:
                self._winmgr.filter(cmd.text, lambda w: w.title)
            elif cmd.kind == CommandKind.EXE:
                self._winmgr.filter(cmd.text, lambda w: w.exe)
            elif cmd.kind == CommandKind.GET:
                self._winmgr.filter(cmd.text)
            elif cmd.kind == CommandKind.LIM:
                winfo = self._winmgr.selected_winfo
                self._winmgr.filter(winfo.exe, lambda w: w.exe)
            elif cmd.kind == CommandKind.SET:
                cmd_on_complete = cmd
            elif cmd.kind == CommandKind.ORD:
                cmd_on_complete = cmd
            elif cmd.kind == CommandKind.DEL:
                cmd_on_complete = cmd
            elif cmd.kind == CommandKind.UNK:
                cmd_on_complete = cmd
        return cmd_on_complete

    def _set_orderby(self, orderby):
        lorderby = orderby.lower()
        if lorderby == 'default':
            self._orderby = ""
            return True
        elif lorderby in ['title', 'exe']:
            self._orderby = lorderby
            return True
        return False

    def _handle_complete(self, cmd):
        winfo = self._winmgr.selected_winfo
        if not cmd:
            if winfo:
                WinControl.show(winfo)
                return ProcessorOutput(hide=True)
            return None
        if cmd.kind == CommandKind.SET:
            self._winmgr.set_alias(winfo, cmd.text)
            self._outtext.append('Set alias: ' + cmd.text)
            output = ProcessorOutput()
            output.add_cmd('')
            return output
        if cmd.kind == CommandKind.ORD:
            if not self._set_orderby(cmd.text):
                curr = self._orderby or "default"
                self._outtext.append(
                    f'Order by change invalid, current value: {curr}'
                )
        elif cmd.kind == CommandKind.DEL:
            self._winmgr.delete_all_alias()
            self._outtext.append("All aliases deleted")
        else:
            self._outtext.append('Unknown command')
        output = ProcessorOutput()
        output.add_cmd('')
        return output

class StrCompare:

    def _argcheck(method):
        def wrapper(test, target):
            if not test: return True
            if not target: return False
            return method(test, target)
        return wrapper

    @staticmethod
    @_argcheck
    def choice(test: str, target: str) -> bool:
        if test.startswith("'"):
            return StrCompare.exact(test[1:], target)
        return StrCompare.progressive(test, target)

    @staticmethod
    @_argcheck
    def progressive(test: str, target: str) -> bool:
        ltest = test.lower()
        ltarg = target.lower()
        prev = 0
        for c in ltest:
            try:
                index = ltarg.index(c, prev)
                if index < prev:
                    return False
                prev = index + 1
            except ValueError:
                return False
        return True

    @staticmethod
    @_argcheck
    def exact(test: str, target: str) -> bool:
        ltest = test.lower()
        ltarg = target.lower()
        return ltest in ltarg

##==============================================================#
## SECTION: Function Definitions                                #
##==============================================================#

def format_num(num: int, padref=0) -> str:
    padlen = len(str(padref))
    return str(num).zfill(padlen)

def parse(input_cmd: str) -> List[Command]:
    def tokenize():
        toks = []
        tok = ""
        for c in input_cmd:
            if c == ";":
                if tok:
                    toks.append(tok)
                    tok = ""
            tok += c
        toks.append(tok)
        return toks
    def totext(tok):
        segs = tok.split(maxsplit=1)
        if len(segs) < 2:
            return ""
        return segs[1]
    cmds = []
    for tok in tokenize():
        if not tok:
            continue
        tok = tok.lstrip()
        if not tok.startswith(";"):
            cmds.append(Command(CommandKind.TITLE, tok))
            continue
        tok = tok[1:].lstrip()
        if tok.startswith("t "):
            cmds.append(Command(CommandKind.TITLE, totext(tok)))
        elif tok.startswith("e "):
            cmds.append(Command(CommandKind.EXE, totext(tok)))
        elif tok == "g" or tok.startswith("g "):
            cmds.append(Command(CommandKind.GET, totext(tok)))
        elif tok == "s" or tok.startswith("s "):
            cmds.append(Command(CommandKind.SET, totext(tok)))
        elif tok.startswith("o"):
            cmds.append(Command(CommandKind.ORD, totext(tok)))
        elif tok == "l" or tok.startswith("l "):
            cmds.append(Command(CommandKind.LIM, totext(tok)))
        elif tok.strip() == "d":
            cmds.append(Command(CommandKind.DEL, totext(tok)))
        else:
            cmds.append(Command(CommandKind.UNK, totext(tok)))
    return cmds

##==============================================================#
## SECTION: Main Body                                           #
##==============================================================#

if __name__ == '__main__':
    # TODO: Maybe split up config by processor
    cfg_path = sys.argv[1]
    cfg = configparser.ConfigParser()
    cfg.read(cfg_path)
    alias_path = cfg.get('paths', 'alias_file')
    exclude_path = cfg.get('paths', 'exclude_file')
    explore_path = cfg.get('paths', 'explore_file')
    launch_path = cfg.get('paths', 'launch_dir')
    explore = ExploreProcessor(explore_path)
    subprocessors = [
        explore,
        LaunchProcessor(launch_path),
        MathProcessor()
    ]
    processor = Processor(alias_path, exclude_path, subprocessors)
    config = Config(
        name='QuickWin',
        about='A window switcher',
        hotkey='CTRL+ALT+SPACE',
        iconpath=abspath("icon.png", __file__),
        winpct=[70, 70],
        comprops=[6, 1],
        menuitems=[
            MenuItem(
                name='Reload exclusions',
                msg='Window exclusions have been reloaded from file',
                func=processor.reload_exclusions
            ),
            MenuItem(
                name='Reload explore',
                msg='Explore configuration has been reloaded from file',
                func=explore.reload_config
            )
        ]
    )
    App(config, processor)
