##==============================================================#
## SECTION: Imports                                             #
##==============================================================#

from __future__ import annotations
from dataclasses import dataclass, asdict
from enum import Enum, auto
from functools import wraps
from typing import Callable, Dict, List, Optional
import csv
import os
import sys

from auxly.filesys import Dir, File, Path, abspath, walkall, walkfiles, walkdirs
import auxly
import pyperclip
import ujson
import yaml

sys.path.append(abspath("../lib", __file__))

from qwindow import (
    App,
    Config,
    EventKind,
    HotKeyKind,
    MenuItem,
    ProcessorBase,
    ProcessorInput,
    ProcessorOutput,
    SubprocessorBase,
    subprocessors,
)
from winctrl import WinControl, WinInfo

##==============================================================#
## SECTION: Global Definitions                                  #
##==============================================================#

DIRAGG_PREFIX = ">"
DIRLIST_PREFIX = "/"
LAUNCH_PREFIX = "."
MATH_PREFIX = "="
QUICKCMD_PREFIX = "`"

##==============================================================#
## SECTION: Special Function Definitions                        #
##==============================================================#

def fatal(msg):
    sys.exit(f"ERROR: {msg}")

def update_histmgr(method):
    """Decorator on a processor's update call to handle managing history."""
    def a_wrapper(processor, pinput):
        histmgr: HistManager = getattr(processor, "_histmgr", None)
        if histmgr is None:
            fatal(f"Processor {processor} has no HistManager attribute named _histmgr!")
        if pinput.was_hidden or processor.was_activated:
            histmgr.reset()
        if pinput.event.is_hotkey(HotKeyKind.PREV):
            pout = ProcessorOutput()
            pout.add_cmd(histmgr.get_prev_cmd(pinput.cmd))
            return pout
        elif pinput.event.is_hotkey(HotKeyKind.NEXT):
            pout = ProcessorOutput()
            pout.add_cmd(histmgr.get_next_cmd(pinput.cmd))
            return pout
        if pinput.is_complete and pinput.cmd:
            histmgr.add(pinput)
        return method(processor, pinput)
    return a_wrapper

##==============================================================#
## SECTION: Class Definitions                                   #
##==============================================================#

class CommandKind(Enum):
    """The kinds of QuickWin commands handled by the processor."""
    UNKNOWN = auto()
    TITLE = auto()
    EXE = auto()
    SET = auto()
    GET = auto()
    LIMIT = auto()
    DELETE = auto()
    ORDER = auto()

@dataclass
class Command:
    """A QuickWin command."""
    kind: CommandKind
    text: str

@dataclass
class HistEntry:
    """A single processor history entry."""
    cmd: str
    row: Optional[str]

class ManagedWindow:
    """An OS window that is able to be managed by the QuickWin processor."""
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
    def is_displayed(self, value: bool):
        self._is_displayed = value

    @property
    def num(self) -> int:
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
    """Handles persisting and retrieving from the HistEntry list."""
    def __init__(self, hist_path: str, max_entries: int, save_rownum: Optional[int] = None):
        self._histfile = File(hist_path, make=True)
        self._max_entries = max_entries
        self._save_rownum = save_rownum
        self._hists: List[HistEntry] = []
        self._load()

    def get(self, prefix: Optional[str] = None, idx: int = 0) -> Optional[HistEntry]:
        try:
            return self._filter(prefix)[idx]
        except IndexError:
            return None

    def len(self, prefix: Optional[str] = None) -> int:
        return len(self._filter(prefix))

    def add(self, pinput: ProcessorInput):
        cmd = pinput.cmd.strip()
        row = None
        if self._save_rownum is not None:
            row = get_selrowtext(pinput, self._save_rownum)
        new_hists = [HistEntry(cmd, row)]
        new_cmds = [cmd]
        for hist in self._hists:
            if hist.cmd not in new_cmds:
                new_hists.append(hist)
                new_cmds.append(hist.cmd)
            if len(new_hists) >= self._max_entries:
                break
        self._hists = new_hists
        self._save()

    def _filter(self, prefix: Optional[str]) -> List[HistEntry]:
        result = []
        for hist in self._hists:
            if hist.cmd.startswith(prefix or ''):
                result.append(hist)
        return result

    def _save(self):
        to_save = None
        if self._save_rownum is not None:
            to_save = [[entry.cmd, entry.row] for entry in self._hists]
        else:
            to_save = [entry.cmd for entry in self._hists]
        self._histfile.empty()
        save_output(self._histfile, to_save)

    def _load(self):
        loaded = load_output(self._histfile) or []
        if len(loaded) > 0 and isinstance(loaded[0], str):
            self._hists = [HistEntry(cmd, None) for cmd in loaded]
        else:
            self._hists = [HistEntry(*entry) for entry in loaded]

class HistManager:
    """Manages history for a processor."""
    def __init__(self, hist_path, save_rownum=None, max_entries=1000):
        self._hists = HistStore(hist_path, max_entries, save_rownum)
        self.reset()

    def add(self, pinput):
        self._hists.add(pinput)

    def match_to_row(self, cmd_prefix: str, rows_to_match: List[str]) -> Optional[int]:
        hist = self._hists.get(cmd_prefix)
        if hist:
            row = hist.row
            if row and row in rows_to_match:
                return rows_to_match.index(row)
        return None

    def reset(self):
        self._pointer = -1
        self._cmd_prefix = None

    def get_next_entry(self, cmd_prefix: str) -> Optional[HistEntry]:
        self._try_set_cmd_prefix(cmd_prefix)
        self._pointer += 1
        if self._pointer >= self._hists.len(self._cmd_prefix):
            self._pointer = self._hists.len(self._cmd_prefix) - 1
        if self._hists.len(self._cmd_prefix) == 0:
            return None
        return self._hists.get(self._cmd_prefix, self._pointer)

    def get_next_cmd(self, cmd_prefix: str) -> Optional[str]:
        entry = self.get_next_entry(cmd_prefix)
        return entry.cmd if entry else None

    def get_prev_entry(self, cmd_prefix: str) -> Optional[HistEntry]:
        self._try_set_cmd_prefix(cmd_prefix)
        self._pointer -= 1
        if self._pointer < 0:
            self._pointer = 0
        if self._hists.len(self._cmd_prefix) == 0:
            return None
        return self._hists.get(self._cmd_prefix, self._pointer)

    def get_prev_cmd(self, cmd_prefix: str) -> Optional[str]:
        entry = self.get_prev_entry(cmd_prefix)
        return entry.cmd if entry else None

    def _try_set_cmd_prefix(self, cmd_prefix):
        should_set = self._cmd_prefix is None
        should_set |= self._hists.len(self._cmd_prefix) == 0
        if should_set:
            self._cmd_prefix = cmd_prefix
        elif cmd_prefix == '':
            self._cmd_prefix = None

class WinExcluder:
    """Checks if an OS window should be excluded from the QuickWin list."""
    def __init__(self, exclude_path):
        self._exclude_path = exclude_path
        self._exclusions = []
        self.reload_exclusions()

    def reload_exclusions(self):
        self._exclusions = []
        if self._exclude_path and os.path.isfile(self._exclude_path):
            self._exclusions = load_config(self._exclude_path)

    def is_excluded(self, winfo: WinInfo) -> bool:
        for exclusion in self._exclusions:
            title = exclusion.get('title')
            exe = exclusion.get('exe')
            if title and exe and title == winfo.title and exe == winfo.exe:
                return True
            elif title and title == winfo.title:
                return True
            elif exe and exe == winfo.exe:
                return True
        return False

class WinManager:
    """Manages the list of OS windows for the QuickWin processor."""
    def __init__(self, alias_path, exclude_path):
        self._allwins: List[ManagedWindow] = []  #: List of all known (not excluded) windows.
        self._selected_win = None
        self._excluder = WinExcluder(exclude_path)
        self._alias_file = File(alias_path, make=True)
        self._alias: Dict[WinInfo, str] = self._load_alias_file()
        self._orderby = None

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
        return self.displayed_wins.index(self._selected_win)

    @property
    def len_allwins(self) -> int:
        return len(self._allwins)

    @property
    def displayed_wins(self) -> List[ManagedWindow]:
        wins = [win for win in self._allwins if win.is_displayed]
        if self._orderby:
            def get_sortkey(mwin: ManagedWindow):
                if self._orderby == 'alias':
                    return self.get_alias(mwin)
                return getattr(mwin, self._orderby)
            return sorted(wins, key=get_sortkey)
        return wins

    def reload_exclusions(self):
        self._excluder.reload_exclusions()

    def refresh(self):
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

    def update(self, pinput, with_refresh=True):
        def update_selected_win():
            clear_selected = pinput.was_hidden
            if clear_selected:
                self._selected_win = None
                return
            select_from_input = pinput.lstview.selnum >= 0 and len(self.displayed_wins) > pinput.lstview.selnum
            if select_from_input:
                self._selected_win = self.displayed_wins[pinput.lstview.selnum]
                return

        update_selected_win()
        for win in self._allwins:
            win.is_displayed = True

        # Refresh must run after update.
        if with_refresh:
            self.refresh()

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
        prev_displayed_win = None
        for win in self.displayed_wins:
            win.is_displayed = should_display(win)
            should_update_selected_win = not win.is_displayed and win is self._selected_win
            if should_update_selected_win:
                if prev_displayed_win:
                    self._selected_win = prev_displayed_win
                else:
                    self._selected_win = None
            if win.is_displayed:
                prev_displayed_win = win

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

    def get_alias(self, mwin: ManagedWindow) -> str:
        return self._alias.get(mwin.winfo, "")

    def set_alias(self, mwin: ManagedWindow, alias: str):
        if not mwin:
            return
        alias_lookup = dict(zip(self._alias.values(), self._alias.keys()))
        alias_winfo = alias_lookup.get(alias, None)
        if alias_winfo:
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
        save_output(self._alias_file, outlist)
        for p in prune:
            del self._alias[p]

    def _load_alias_file(self) -> Dict[WinInfo, str]:
        alias = {}
        try:
            inlist = load_output(self._alias_file)
        except Exception:
            return alias
        for i in inlist:
            alias[WinInfo(**i[0])] = i[1]
        return alias

class DirListProcessor(SubprocessorBase):

    def __init__(self):
        self.dirhist = []

    @property
    def currdir(self) -> Optional[Dir]:
        if not self.dirhist:
            return None
        return self.dirhist[-1]

    @property
    def prefix(self):
        return DIRLIST_PREFIX

    @property
    def help(self) -> str:
        return "DirList processor prefix: " + self.prefix

    def on_activate(self, pinput):
        self._load_initial_dir(pinput)

    def use_processor(self, pinput):
        if len(pinput.cmd) == 0:
            return False
        return pinput.cmd[0] == self.prefix

    def _get_path(self, row):
        try:
            itemname = row[0]
            if row[1] == "dir":
                itemname = itemname[1:]  # Remove the added slash prefix.
                return Path(self.currdir, itemname)
            return Path(self.currdir, itemname)
        except:
            return None

    def update(self, pinput):
        reset_cmd = False
        out_txt = ""
        path = self._get_path(pinput.selrow)
        if pinput.is_complete:
            auxly.open(path)
            return ProcessorOutput(hide=True)
        elif pinput.event.is_hotkey(HotKeyKind.INTO):
            if path.isdir():
                self.dirhist.append(path)
                reset_cmd = True
            elif path.isfile():
                pyperclip.copy(path)
                out_txt = "Copied path to clipboard: " + path
        elif pinput.event.is_hotkey(HotKeyKind.OUTOF):
            self.dirhist.append(self.currdir.parent)
            reset_cmd = True
        elif pinput.event.is_hotkey(HotKeyKind.PREV):
            if len(self.dirhist) > 1:
                self.dirhist.pop()
                reset_cmd = True
            else:
                out_txt = "No previous path history available"
        return self._render_rows(pinput, reset_cmd, out_txt)

    @staticmethod
    def _get_fallback_dir():
        return Dir("C:\\")

    def _load_initial_dir(self, pinput):
        _, title, exe, _ = pinput.selrow
        if exe.lower() != "explorer.exe":
            self.dirhist = [DirListProcessor._get_fallback_dir()]
            return
        initial_dir = Dir(DirListProcessor._remove_git_branch_suffix(title))
        if not initial_dir.isdir():
            self.dirhist = [DirListProcessor._get_fallback_dir()]
            return
        self.dirhist = [initial_dir]

    @staticmethod
    def _get_rows(cmdtxt, targetdir):
        rows = []
        try:
            for item in walkall(targetdir):
                if StrCompare.choice(cmdtxt, item.name):
                    if item.isdir():
                        rows.append([f"/{item.name}", "dir"])
                    elif item.isfile():
                        rows.append([item.name, "file"])
        except:
            pass
        return rows

    def _render_rows(self, pinput, reset_cmd=False, out_txt=""):
        cmdtxt = pinput.cmd.split(self.prefix, maxsplit=1)[1]
        rows = DirListProcessor._get_rows(cmdtxt, self.currdir)
        output = ProcessorOutput()
        selnum = pinput.lstview.selnum
        if reset_cmd:
            output.add_cmd(self.prefix)
            selnum = 0
        output.add_rows(
            ["Name", "Type"],
            [5, 1],
            rows,
            selnum
        )
        try:
            selected_path = self._get_path(rows[selnum])
        except:
            selected_path = ""
        output.add_txt(f"Listing dir content: {self.currdir}\nCurrent selected: {selected_path}\n{out_txt}")
        return output

    @staticmethod
    def _remove_git_branch_suffix(dirpath):
        if not dirpath.endswith("]"):
            return dirpath
        square_bracket_start_index = dirpath.rfind("[")
        if square_bracket_start_index == -1:
            return dirpath
        return dirpath[:square_bracket_start_index].strip()

class MathProcessor(SubprocessorBase):
    """Processor to perform simple math calculations."""

    @property
    def prefix(self):
        return MATH_PREFIX

    @property
    def help(self) -> str:
        return "Math processor prefix: " + self.prefix

    def use_processor(self, pinput):
        if len(pinput.cmd) == 0:
            return False
        return pinput.cmd[0] == self.prefix

    def update(self, pinput):
        cmdtext = pinput.cmd.split(self.prefix, maxsplit=1)[1]
        output = ProcessorOutput()
        output.hide_rows()
        try:
            result = eval(cmdtext)
            output.add_txt(f"Math result: {result}")
        except Exception:
            output.add_txt(f"Math result:")
        return output

class QuickCmdProcessor(SubprocessorBase):
    """Processor to perform simple math calculations."""
    def __init__(self, cfg):
        hist_path = format_outpath(cfg, "quickcmd-hist")
        self._histmgr = HistManager(hist_path, 0)
        self._path = cfg['config_file']
        self._cmds = None
        self.reload_config()

    @property
    def prefix(self):
        return QUICKCMD_PREFIX

    @property
    def help(self) -> str:
        return "QuickCmd processor prefix: " + self.prefix

    def use_processor(self, pinput):
        if len(pinput.cmd) == 0:
            return False
        return pinput.cmd[0] == self.prefix

    @update_histmgr
    def update(self, pinput):
        if pinput.selrow and (pinput.is_complete or pinput.event.is_hotkey(HotKeyKind.INTO)):
            return self._set_cmd(pinput)
        cmdtext = remove_prefix(self.prefix, pinput.cmd)
        rows = self._filter_rows(cmdtext)
        try_sel_prev = self.was_activated
        if try_sel_prev:
            try:
                entry = self._histmgr.get_prev_entry(self.prefix)
                names = [row[0] for row in rows]
                selnum = names.index(entry.row)
            except:
                selnum = 0
        else:
            selnum = pinput.lstview.selnum
        output = ProcessorOutput()
        output.add_txt(f"Found {len(rows)} matching QuickCmds")
        output.add_rows(
            ["Name", "Command"],
            [1, 3],
            rows,
            selnum
        )
        return output

    def _filter_rows(self, filter_text):
        result = []
        for name,cmd in self._cmds.items():
            if not StrCompare.choice(filter_text, name):
                continue
            result.append([name, cmd])
        return result

    def _set_cmd(self, pinput):
        output = ProcessorOutput()
        _,cmd = pinput.selrow
        output.add_cmd(cmd)
        return output

    def reload_config(self):
        self._cmds = load_config(self._path)

class DirAggProcessor(SubprocessorBase):
    """Processor that aggregates child directories from multiple parents and
    allows the user to open one."""
    def __init__(self, cfg):
        self._path = cfg['locations_file']
        self._cfg = {}
        self._category: Optional[str] = None
        self.reload_config()

    @property
    def prefix(self) -> str:
        return DIRAGG_PREFIX

    @property
    def help(self) -> str:
        return "DirAgg processor prefix: " + self.prefix

    def reload_config(self):
        self._cfg = load_config(self._path)
        self._category = None

    def use_processor(self, pinput):
        if len(pinput.cmd) == 0:
            self._category = None
            return False
        return pinput.cmd.startswith(self.prefix)

    @property
    def _categories(self) -> List[str]:
        return self._cfg.keys()

    def update(self, pinput) -> Optional[ProcessorOutput]:
        cmdtext = pinput.cmd[len(self.prefix):].lstrip()

        should_get_category_from_cmdtext = self._category is None and cmdtext.count(self.prefix) > 0
        if should_get_category_from_cmdtext:
            cattext = cmdtext.split(self.prefix)[0]
            should_use_selected_row = len(cattext) == 0
            if should_use_selected_row:
                self._category = get_selrowtext(pinput, 0)
            else:
                categories = self._filter_categories(cattext)
                if len(categories) > 0:
                    self._category = categories[0]

        should_split_off_cmdtext = self._category is not None and cmdtext.count(self.prefix) > 0
        if should_split_off_cmdtext:
            cmdtext = cmdtext.split(self.prefix)[1]

        if pinput.event.is_hotkey(HotKeyKind.OUTOF):
            self._category = None
            output = ProcessorOutput()
            output.add_cmd(self.prefix)
            return output

        if self._category is None:
            return self._show_available_categories(pinput, cmdtext)
        return self._show_selected_category(pinput, cmdtext)

    def _show_selected_category(self, pinput, cmdtext):
        if pinput.is_complete:
            name, path = pinput.selrow
            dpath = Dir(path, name)
            auxly.open(dpath)
            return ProcessorOutput(hide=True)
        rows = []
        category = self._cfg[self._category]
        outtext = []
        outtext.append(f"DirAgg selected category: {self._category}")
        for path in category:
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
        output.add_txt("\n".join(outtext))
        return output

    def _filter_categories(self, filter_text: str) -> List[str]:
        result = []
        for c in self._categories:
            if not StrCompare.choice(filter_text, c):
                continue
            result.append(c)
        return result

    def _show_available_categories(self, pinput, cmdtext):
        if pinput.selrow and (pinput.is_complete or pinput.event.is_hotkey(HotKeyKind.INTO)):
            self._category = pinput.selrow[0]
            output = ProcessorOutput()
            output.add_cmd(self.prefix)
            return output
        categories = self._filter_categories(cmdtext)
        output = ProcessorOutput()
        output.add_rows(
            ["Name"],
            [1],
            [[c] for c in categories],
            pinput.lstview.selnum
        )
        output.add_txt("Select a DirAgg category")
        return output

class LaunchProcessor(SubprocessorBase):
    """Processor that lists child items from a directory and allows the user to
    open one."""
    def __init__(self, cfg):
        self._path = cfg['launch_dir']
        hist_path = format_outpath(cfg, "launch-hist")
        self._histmgr = HistManager(hist_path, 0)

    @property
    def prefix(self) -> str:
        return LAUNCH_PREFIX

    @property
    def help(self) -> str:
        return "Launch processor prefix: " + self.prefix

    def use_processor(self, pinput):
        if len(pinput.cmd) == 0:
            return False
        return pinput.cmd[0] == self.prefix

    @update_histmgr
    def update(self, pinput):
        if pinput.is_complete and pinput.selrow:
            return self._open_selected(pinput)
        if pinput.event.kind == EventKind.CMD_CHANGE:
            cmdtext = pinput.cmd[1:].lstrip()
            rows = []
            for f in walkfiles(self._path):
                if not StrCompare.choice(cmdtext, f.name):
                    continue
                rows.append([f.stem, f.ext])
            selnum = self._histmgr.match_to_row(pinput.cmd.strip(), [r[0] for r in rows])
            if selnum is None:
                selnum = pinput.lstview.selnum
            output = ProcessorOutput()
            output.add_txt(f"Launch items found: {len(rows)}")
            output.add_rows(
                ["Name", "Ext"],
                [3, 1],
                rows,
                selnum
            )
            return output

    def _open_selected(self, pinput):
        stem,ext = pinput.selrow
        selpath = File(self._path, stem + ext)
        auxly.open(selpath)
        return ProcessorOutput(hide=True)

class Processor(ProcessorBase):
    """The main QuickWin processor. Provides a list of OS windows and allows
    the user to select one to switch to (similar to ALT+TAB)."""
    def __init__(self, cfg, subprocessors=None):
        super(Processor, self).__init__()
        self._outtext: List[str] = []
        alias_path = format_outpath(cfg, "quickwin-alias")
        self._winmgr = WinManager(alias_path, cfg.get('exclude_file'))
        hist_path = format_outpath(cfg, "quickwin-hist")
        self._histmgr = HistManager(hist_path)
        self._subprocessors = subprocessors or []

    @property
    def prefix(self) -> str:
        return ''

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
    @update_histmgr
    def update(self, pinput):
        self._winmgr.update(pinput)
        cmds = parse_cmds(pinput.cmdtext.text)
        cmd_on_complete = self._handle_incomplete(cmds)
        if pinput.is_complete:
            return self._handle_complete(cmd_on_complete)
        poutput = self._render_rows()
        poutput = self._handle_colclick(pinput, poutput)
        poutput = self._handle_rowclick(pinput, poutput)
        return poutput

    def reload_exclusions(self):
        self._winmgr.reload_exclusions()

    def _handle_rowclick(self, pinput, poutput):
        if pinput.event.kind == EventKind.ROW_RCLICK:
            if pinput.event.colnum == 2:
                exe = pinput.lstview.rows[pinput.event.rownum][2]
                poutput.add_cmd(pinput.cmd + f";e {exe}")
            elif pinput.event.colnum == 3:
                poutput.add_cmd(pinput.cmd + ";g")
        return poutput

    def _handle_colclick(self, pinput, poutput):
        if pinput.event.kind == EventKind.COL_LCLICK:
            if pinput.event.colnum == 0:
                poutput.add_cmd(pinput.cmd + ";o default")
            if pinput.event.colnum == 1:
                poutput.add_cmd(pinput.cmd + ";o title")
            if pinput.event.colnum == 2:
                poutput.add_cmd(pinput.cmd + ";o exe")
            if pinput.event.colnum == 3:
                poutput.add_cmd(pinput.cmd + ";o alias")
        return poutput

    def _render_rows(self):
        displayed_wins = self._winmgr.displayed_wins
        len_allwins = self._winmgr.len_allwins
        self._outtext.append(f'Windows found: {len(displayed_wins)}')
        rows = []
        for win in displayed_wins:
            rows.append([
                format_num(win.num, len_allwins),
                win.title,
                win.exe,
                self._winmgr.get_alias(win)
            ])
        output = ProcessorOutput()
        output.add_txt(self._render_outtext())
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
            elif cmd.kind == CommandKind.LIMIT:
                winfo = self._winmgr.selected_win
                if winfo:
                    self._winmgr.filter(winfo.exe, lambda w: w.exe, exact=True)
            elif cmd.kind == CommandKind.ORDER:
                self._winmgr.set_orderby(cmd.text)
            elif cmd.kind == CommandKind.SET:
                cmd_on_complete = cmd
            elif cmd.kind == CommandKind.DELETE:
                cmd_on_complete = cmd
            elif cmd.kind == CommandKind.UNKNOWN:
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
        elif cmd.kind == CommandKind.DELETE:
            self._winmgr.delete_all_alias()
            self._outtext.append("All aliases deleted")
        else:
            self._outtext.append('Unknown command')
        output = ProcessorOutput()
        output.add_cmd('')
        return output

class StrCompare:
    """Provides various string comparison methods."""
    @staticmethod
    def _argcheck(method: Callable[[str, str], bool]):
        @wraps(method)
        def wrapper(test: str, target: str) -> bool:
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

def remove_prefix(prefix, text) -> str:
    try:
        return text.split(prefix, maxsplit=1)[1]
    except:
        return text or ""

def get_selrowtext(pinput, rownum) -> str:
    try:
        return pinput.selrow[rownum]
    except Exception:
        return ''

def format_num(num: int, padref=0) -> str:
    padlen = len(str(padref))
    return str(num).zfill(padlen)

def parse_cmds(input_cmd: str) -> List[Command]:
    def tokenize():
        toks = []
        tok = ""
        for c in input_cmd.strip():
            if c == ";":
                if tok:
                    toks.append(tok)
                    tok = ""
            tok += c
        toks.append(tok)
        return toks
    def get_text(tok):
        segs = tok.split(maxsplit=1)
        if len(segs) < 2:
            return ""
        return segs[1]
    def is_command_char(tok: str, char: str, allow_text=True) -> bool:
        if tok.strip() == char:
            return True
        if allow_text and tok.startswith(char + " "):
            return True
        return False
    cmds = []
    for tok in tokenize():
        if not tok:
            continue
        tok = tok.strip()
        if not tok.startswith(";"):
            cmds.append(Command(CommandKind.TITLE, tok))
            continue
        # The lstrip allows spaces between the semicolon and command character.
        tok = tok[1:].lstrip()
        if is_command_char(tok, "t"):
            cmds.append(Command(CommandKind.TITLE, get_text(tok)))
        elif is_command_char(tok, "e"):
            cmds.append(Command(CommandKind.EXE, get_text(tok)))
        elif is_command_char(tok, "g"):
            cmds.append(Command(CommandKind.GET, get_text(tok)))
        elif is_command_char(tok, "s"):
            cmds.append(Command(CommandKind.SET, get_text(tok)))
        elif is_command_char(tok, "o"):
            cmds.append(Command(CommandKind.ORDER, get_text(tok)))
        elif is_command_char(tok, "l", False):
            cmds.append(Command(CommandKind.LIMIT, ""))
        elif is_command_char(tok, "d", False):
            cmds.append(Command(CommandKind.DELETE, ""))
        else:
            cmds.append(Command(CommandKind.UNKNOWN, get_text(tok)))
    return cmds

def format_outpath(cfg, file_stem) -> str:
    return os.path.join(cfg['output_dir'], file_stem + ".json")

def save_output(out_file, output):
    json = ujson.dumps(output)
    out_file.write(json)

def load_output(out_file: File):
    if not out_file.isfile():
        return None
    raw = out_file.read()
    if not raw:
        return raw
    return ujson.loads(raw)

def load_config(cfg_path):
    if not cfg_path:
        fatal("Config path not provided!")
    cfile = File(cfg_path)
    if not cfile.isfile():
        fatal(f"Config file does not exist! {cfg_path}")
    return yaml.safe_load(cfile.read())

def get_processor_config(main_cfg, processor_name) -> Optional[Dict[str, str]]:
    processor_cfg = main_cfg.get(processor_name)
    if processor_cfg is None:
        return None
    if processor_name != '__common__':
        common_cfg = main_cfg['__common__']
        for key, value in common_cfg.items():
            if not processor_cfg.get(key):
                processor_cfg[key] = value
    return processor_cfg

def start_app():
    if len(sys.argv) != 2:
        fatal("Must provide config file as argument!")
    cfg_path = sys.argv[1]
    main_cfg = load_config(cfg_path)
    if not main_cfg.get('__common__'):
        fatal("Config file must contain a '__common__' key!")
    if not main_cfg.get('__common__').get('output_dir'):
        fatal("Config file must contain a 'output_dir' key!")

    menuitems = []
    subprocessors = [MathProcessor(), DirListProcessor()]
    processor_cfg = get_processor_config(main_cfg, 'diragg')
    if processor_cfg:
        diragg = DirAggProcessor(processor_cfg)
        subprocessors.append(diragg)
        menuitems.append(
            MenuItem(
                name='Reload DirAgg locations',
                msg='DirAgg locations configuration has been reloaded from file',
                func=diragg.reload_config
            )
        )
    processor_cfg = get_processor_config(main_cfg, 'launch')
    if processor_cfg:
        launch = LaunchProcessor(processor_cfg)
        subprocessors.append(launch)

    processor_cfg = get_processor_config(main_cfg, 'quickcmd')
    if processor_cfg:
        quickcmd = QuickCmdProcessor(processor_cfg)
        subprocessors.append(quickcmd)
        menuitems.append(
            MenuItem(
                name='Reload QuickCmd config',
                msg='QuickCmd configuration has been reloaded from file',
                func=quickcmd.reload_config
            )
        )

    processor_cfg = get_processor_config(main_cfg, 'quickwin') or get_processor_config(main_cfg, '__common__')
    processor = Processor(processor_cfg, subprocessors)
    menuitems.append(
        MenuItem(
            name='Reload QuickWin exclusions',
            msg='Window exclusions have been reloaded from file',
            func=processor.reload_exclusions
        )
    )

    config = Config(
        name='QuickWin',
        about='A window switcher',
        hotkey='CTRL+ALT+SPACE',
        iconpath=abspath("icon.png", __file__),
        winpct=[70, 70],
        comprops=[6, 1],
        menuitems=menuitems
    )
    App(config, processor)

##==============================================================#
## SECTION: Main Body                                           #
##==============================================================#

if __name__ == '__main__':
    start_app()
