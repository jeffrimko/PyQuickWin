##==============================================================#
## SECTION: Imports                                             #
##==============================================================#

from __future__ import annotations
from dataclasses import dataclass, asdict
from enum import Enum, auto
from typing import Dict, List, Optional
import configparser
import csv
import sys
import os

from auxly.filesys import Dir, File, abspath, walkfiles, walkdirs
import auxly
import ujson
import yaml

from qwindow import App, Config, KeyKind, ProcessorBase, ProcessorOutput, MenuItem, SubprocessorBase, subprocessors
from winctrl import WinControl, WinInfo

##==============================================================#
## SECTION: Global Definitions                                  #
##==============================================================#

LAUNCH_PREFIX = "."
MATH_PREFIX = "="
DIRAGG_PREFIX = ">"

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

class ManagedWindow:
    def __init__(self, num: int, winfo: WinInfo):
        self._num = num
        self._winfo = winfo
        self._is_displayed = True

    def __repr__(self):
        return self.title

    @property
    def is_displayed(self) -> bool:
        return self._is_displayed

    @is_displayed.setter
    def is_displayed(self, value):
        self._is_displayed = value

    @property
    def num(self) -> str:
        return self._num

    @property
    def winfo(self) -> WinInfo:
        return self._winfo

    @property
    def title(self) -> str:
        return self._winfo.title

    @property
    def exe(self) -> str:
        return self._winfo.exe

class HistStore:
    def __init__(self, hist_path, max_entries):
        self._histfile = File(hist_path, make=True)
        self._max_entries = max_entries
        self._load()

    def get(self, prefix: str, idx: int) -> Optional[List[str]]:
        try:
            return self._filter(prefix)[idx]
        except IndexError:
            return None

    def _filter(self, prefix: str):
        result = []
        for hist in self._hists:
            if hist[0].startswith(prefix):
                result.append(hist)
        return result

    def len(self, prefix: str):
        return len(self._filter(prefix))

    def startswith(self, prefix: str):
        for hist in self._hists:
            if hist[0].startswith(prefix):
                return hist
        return None

    def add(self, key: str, value: str):
        new_hists = [[key, value]]
        new_keys = [key]
        for hist in self._hists:
            if hist[0] not in new_keys:
                new_hists.append(hist)
                new_keys.append(hist[0])
            if len(new_hists) >= self._max_entries:
                break
        self._hists = new_hists
        self._save()

    def _save(self):
        self._histfile.empty()
        self._histfile.write(yaml.safe_dump(self._hists))

    def _load(self):
        self._hists = yaml.safe_load(self._histfile.read()) or []

class HistManager:
    def __init__(self, hist_path, max_entries=1000):
        self._hists = HistStore(hist_path, max_entries)
        self._reset()

    @staticmethod
    def _get_selrowtext(pinput, rownum):
        try:
            return pinput.selrow[rownum]
        except Exception:
            return None

    @staticmethod
    def update(rownum, prefix=''):
        def m_wrapper(method):
            def a_wrapper(processor, pinput):
                if pinput.was_hidden or pinput.cmd == prefix:
                    processor._histmgr._reset()
                if pinput.key == KeyKind.PREV:
                    pout = ProcessorOutput()
                    pout.add_cmd(processor._histmgr._get_prev(pinput.cmd))
                    return pout
                elif pinput.key == KeyKind.NEXT:
                    pout = ProcessorOutput()
                    pout.add_cmd(processor._histmgr._get_next(pinput.cmd))
                    return pout
                if pinput.is_complete and pinput.cmd:
                    processor._histmgr.add(pinput.cmd, HistManager._get_selrowtext(pinput, rownum))
                return method(processor, pinput)
            return a_wrapper
        return m_wrapper

    def match(self, key, opts):
        hist = self._hists.startswith(key)
        if hist:
            fullname = hist[1]
            if fullname:
                return opts.index(fullname)
        return None

    def _reset(self):
        self._pointer = -1
        self._base = None

    def _try_set_base(self, value):
        if self._base is None:
            self._base = value
        elif value == '':
            self._base = None

    def _get_prev(self, value):
        self._try_set_base(value)
        self._pointer += 1
        if self._pointer >= self._hists.len(self._base):
            self._pointer = self._hists.len(self._base) - 1
        if self._hists.len(self._base) == 0:
            return ''
        return self._hists.get(self._base, self._pointer)[0]

    def _get_next(self, value):
        self._try_set_base(value)
        self._pointer -= 1
        if self._pointer < 0:
            self._pointer = 0
        if self._hists.len(self._base) == 0:
            return ''
        return self._hists.get(self._base, self._pointer)[0]

    def add(self, cmd, row):
        self._hists.add(cmd.strip(), row)

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
        self._allwins: List[ManagedWindow] = []  #: List of all known (not excluded) windows.
        self._selected_win = None
        self._excluder = WinExcluder(exclude_path)
        self._alias_file = File(alias_path, make=True)
        self._alias: Dict[WinInfo, str] = self._load_alias_file()
        self._orderby = None

    def reload_exclusions(self):
        self._excluder.reload_exclusions()

    def reset(self):
        self._allwins = []
        self._orderby = None
        winlist = WinControl.list()
        selected_winfo = self._selected_win.winfo if self._selected_win else None
        self._selected_win = None
        num = 1
        for winfo in winlist:
            if self._excluder.is_excluded(winfo):
                continue
            mwin = ManagedWindow(
                num,
                winfo,
            )
            self._allwins.append(mwin)
            if winfo == selected_winfo:
                self._selected_win = mwin
            num += 1
        if not self._selected_win and len(self._allwins) > 0:
            self._selected_win = self._allwins[0]

    def update(self, pinput):
        if pinput.was_hidden:
            self._selected_win = None
        elif pinput.lstview.selnum >= 0:
            self._selected_win = self.wins[pinput.lstview.selnum]

    def filter(self, cmdtext, getwintext=None, exact=False):
        def default(mwin: ManagedWindow):
            return self.get_alias(mwin)
        def should_display(mwin: ManagedWindow) -> bool:
            wintext = (getwintext or default)(mwin)
            if not wintext:
                return False
            if exact:
                return StrCompare.exact(cmdtext, wintext)
            return StrCompare.choice(cmdtext, wintext)
        displayed = []
        for win in self._allwins:
            win.is_displayed = should_display(win)
            should_update_selected_win = not win.is_displayed and win is self._selected_win
            if should_update_selected_win:
                if len(displayed) > 0:
                    self._selected_win = displayed[-1]
                else: self._selected_win = None
            if win.is_displayed:
                displayed.append(win)

    def set_orderby(self, orderby) -> bool:
        if not orderby:
            self._orderby = None
            return False
        def set_if_valid(validname):
            if validname.startswith(orderby):
                self._orderby = validname
                return True
        if set_if_valid('title'): return True
        if set_if_valid('exe'): return True
        if set_if_valid('alias'): return True
        self._orderby = None
        return False

    @property
    def orderby(self) -> Optional[str]:
        return self._orderby

    @property
    def selected_win(self) -> Optional[ManagedWindow]:
        return self._selected_win

    @property
    def selected_index(self) -> int:
        if not self._selected_win:
            return 0
        return self.wins.index(self._selected_win)

    @property
    def wins(self) -> List[ManagedWindow]:
        wins = [win for win in self._allwins if win.is_displayed]
        if self._orderby:
            def get_sortkey(mwin: ManagedWindow):
                if self._orderby == 'alias':
                    return self.get_alias(mwin)
                return getattr(mwin, self._orderby)
            return sorted(wins, key=get_sortkey)
        return wins

    def get_alias(self, mwin: ManagedWindow) -> str:
        return self._alias.get(mwin.winfo, "")

    def set_alias(self, mwin: ManagedWindow, alias: str):
        if not mwin:
            return
        alias_lookup = dict(zip(self._alias.values(), self._alias.keys()))
        alias_winfo = alias_lookup.get(alias, None)
        self._alias.pop(alias_winfo, None)
        self._alias[mwin.winfo] = alias
        self._save_alias_file()

    def delete_all_alias(self):
        self._alias = {}
        self._save_alias_file()

    def _save_alias_file(self):
        outlist = []
        prune = []
        winfos = [mwin.winfo for mwin in self._allwins]
        for k,v in self._alias.items():
            if not v or k not in winfos:
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

class MathProcessor(SubprocessorBase):
    @property
    def help(self) -> str:
        return "Math processor prefix: " + MATH_PREFIX

    def use_processor(self, pinput):
        if len(pinput.cmd) == 0:
            return False
        return pinput.cmd[0] == MATH_PREFIX

    def update(self, pinput):
        cmdtext = pinput.cmd.split("=", maxsplit=1)[1]
        output = ProcessorOutput()
        output.hide_rows()
        try:
            result = eval(cmdtext)
            output.add_out(f"Math result: {result}")
        except Exception:
            output.add_out(f"Math result:")
        return output

class DirAggProcessor(SubprocessorBase):
    def __init__(self, cfg):
        self._path = cfg['locations_file']
        self._cfg = {}
        self._selected = None
        self.reload_config()

    @property
    def help(self) -> str:
        return "DirAgg processor prefix: " + DIRAGG_PREFIX

    def reload_config(self):
        self._cfg = yaml.safe_load(File(self._path).read())
        self._selected = None

    def use_processor(self, pinput):
        if len(pinput.cmd) == 0:
            self._selected = None
            return False
        return pinput.cmd.startswith(DIRAGG_PREFIX)

    def update(self, pinput):
        cmdtext = pinput.cmd[1:].lstrip()
        if pinput.key == KeyKind.OUTOF:
            self._selected = None
        if self._selected is None:
            return self._show_root(pinput, cmdtext)
        return self._show_selected(pinput, cmdtext)

    def _show_selected(self, pinput, cmdtext):
        if pinput.is_complete:
            name, path = pinput.selrow
            dpath = Dir(path, name)
            auxly.open(dpath)
            return ProcessorOutput(hide=True)
        rows = []
        selected = self._cfg[self._selected]
        outtext = []
        outtext.append(f"DirAgg selected: {self._selected}")
        for path in selected:
            if not Dir(path).exists():
                outtext.append(f"Path not found: {path}")
                continue
            for dpath in walkdirs(path):
                name = dpath.name
                if name.startswith(".") or name.startswith("__"):
                    continue
                if not StrCompare.choice(cmdtext, dpath):
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
        if pinput.is_complete or pinput.key == KeyKind.INTO:
            self._selected = pinput.selrow[0]
            output = ProcessorOutput()
            output.add_cmd(DIRAGG_PREFIX)
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
        output.add_out("Select a DirAgg")
        return output

class LaunchProcessor(SubprocessorBase):
    def __init__(self, cfg):
        self._path = cfg['launch_dir']
        self._histmgr = HistManager(cfg['hist_file'])

    @property
    def help(self) -> str:
        return "Launch processor prefix: " + LAUNCH_PREFIX

    def use_processor(self, pinput):
        if len(pinput.cmd) == 0:
            return False
        return pinput.cmd[0] == LAUNCH_PREFIX

    @HistManager.update(0, LAUNCH_PREFIX)
    def update(self, pinput):
        if pinput.is_complete and pinput.selrow:
            stem,ext = pinput.selrow
            selpath = File(self._path, stem + ext)
            auxly.open(selpath)
            return ProcessorOutput(hide=True)
        cmdtext = pinput.cmd[1:].lstrip()
        output = ProcessorOutput()
        rows = []
        for f in walkfiles(self._path):
            if not StrCompare.choice(cmdtext, f.name):
                continue
            rows.append([f.stem, f.ext])

        selnum = self._histmgr.match(pinput.cmd.strip(), [r[0] for r in rows])
        if selnum is None:
            selnum = pinput.lstview.selnum
        output.add_out(f"Launch items found: {len(rows)}")
        output.add_rows(
            ["Name", "Ext"],
            [3,1],
            rows,
            selnum
        )
        return output

class Processor(ProcessorBase):
    def __init__(self, cfg, subprocessors=None):
        self._outtext: List[str] = []
        self._winmgr = WinManager(cfg['alias_file'], cfg['exclude_file'])
        self._histmgr = HistManager(cfg['hist_file'])
        self._subprocessors = subprocessors or []

    @property
    def help(self) -> str:
        lines = [
            'PyQuickWin commands:',
            '    Filters: t <TITLE> | e <EXECUTABLE> | l (current exe)',
            '    Aliases: s <SET> | g <GET> | d (delete all)',
            '    Col Order: o [alias|exe|title]'
        ]
        msg = os.linesep.join(lines) + os.linesep
        for sub in self._subprocessors:
            msg += sub.help + os.linesep
        return msg

    @subprocessors
    @HistManager.update(1)
    def update(self, pinput):
        self._winmgr.update(pinput)
        cmds = parse(pinput.cmdtext.text)
        if (not pinput.cmdtext.text) and (not cmds):
            self._winmgr.reset()

        cmd_on_complete = self._handle_incomplete(cmds)
        if pinput.is_complete:
            return self._handle_complete(cmd_on_complete)
        return self._render_rows()

    def reload_exclusions(self):
        self._winmgr.reload_exclusions()

    def _render_rows(self):
        wins = self._winmgr.wins
        self._outtext.append(f'Windows found: {len(wins)}')
        rows = []
        for win in wins:
            rows.append([
                format_num(win.num, len(wins)),
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
            self._winmgr.selected_index,
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
                winfo = self._winmgr.selected_win
                self._winmgr.filter(winfo.exe, lambda w: w.exe, exact=True)
            elif cmd.kind == CommandKind.ORD:
                self._winmgr.set_orderby(cmd.text)
            elif cmd.kind == CommandKind.SET:
                cmd_on_complete = cmd
            elif cmd.kind == CommandKind.ORD:
                cmd_on_complete = cmd
            elif cmd.kind == CommandKind.DEL:
                cmd_on_complete = cmd
            elif cmd.kind == CommandKind.UNK:
                cmd_on_complete = cmd
        return cmd_on_complete

    def _handle_complete(self, cmd):
        mwin = self._winmgr.selected_win
        if not cmd:
            if mwin:
                WinControl.show(mwin.winfo)
                return ProcessorOutput(hide=True)
            return None
        if cmd.kind == CommandKind.SET:
            self._winmgr.set_alias(mwin, cmd.text)
            if cmd.text:
                self._outtext.append('Set alias: ' + cmd.text)
            else:
                self._outtext.append('Cleared alias')
            output = ProcessorOutput()
            output.add_cmd('')
            return output
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
            return StrCompare.includes(test[1:], target)
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
    def includes(test: str, target: str) -> bool:
        ltest = test.lower()
        ltarg = target.lower()
        return ltest in ltarg

    @staticmethod
    @_argcheck
    def exact(test: str, target: str) -> bool:
        ltest = test.lower()
        ltarg = target.lower()
        return ltest == ltarg

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
    cfg_path = sys.argv[1]
    cfg = configparser.ConfigParser()
    cfg.read(cfg_path)

    explore = DirAggProcessor(dict(cfg.items('diragg')))
    subprocessors = [
        explore,
        LaunchProcessor(dict(cfg.items('launch'))),
        MathProcessor()
    ]

    processor = Processor(dict(cfg.items('quickwin')), subprocessors)
    config = Config(
        name='QuickWin',
        about='A window switcher',
        hotkey='CTRL+ALT+SPACE',
        iconpath=abspath("icon.png", __file__),
        winpct=[70, 70],
        comprops=[6, 1],
        menuitems=[
            MenuItem(
                name='Reload QuickWin exclusions',
                msg='Window exclusions have been reloaded from file',
                func=processor.reload_exclusions
            ),
            MenuItem(
                name='Reload DirAgg locations',
                msg='DirAgg locations configuration has been reloaded from file',
                func=explore.reload_config
            ),
        ]
    )
    App(config, processor)
