##==============================================================#
## SECTION: Imports                                             #
##==============================================================#

from abc import ABC, abstractproperty
from collections import namedtuple
from dataclasses import dataclass, field
from enum import Enum, auto
from math import floor
from typing import List, Optional, Callable

from wx.lib.embeddedimage import PyEmbeddedImage
import wx
import wx.adv
import wx.dataview as dv

try:
    # On Windows this prevents wx fuzziness and corrects the detected display
    # resolution.
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(True)
except Exception:
    pass

##==============================================================#
## SECTION: Global Definitions                                  #
##==============================================================#

KeyBinding = namedtuple('KeyBinding', ['mod', 'key', 'func'])

##==============================================================#
## SECTION: Class Definitions                                   #
##==============================================================#

class _Default:
    icon = PyEmbeddedImage(
        "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAAABHNCSVQICAgIfAhkiAAAALhJ"
        "REFUWIXtl80SgyAMhHeR99Y+eJseLAdHbJM0TjiwN2dI+MgfQpYFmSqpu0+AEQDqrwXyeorH"
        "McvCEIBdm3F7/fr0FKgBRFaIrHkAdykdQFmEGm2HL233BAIAYmxYEqjePo9SBYBvBKppclDz"
        "prMcqAhbAtknJx+3AKRHgGhnv4iApQY+jtSWpOY27BnifNt5uyk9BekAoZNwl21yDBSBi/63"
        "yOMiLAXaf8AuwP9n94vzaTYBsgHeht4lXXmb7yQAAAAASUVORK5CYII=")

class KeyKind(Enum):
    NEXT = auto()
    PREV = auto()
    UNDO = auto()
    INTO = auto()
    OUTOF = auto()

@dataclass
class MenuItem:
    name: str
    msg: str
    func: Callable
    confirm: bool = False

@dataclass
class Config:
    name: str = ""
    version: str = ""
    about: str = "Built with QWindow"
    winpct: List[int] = field(default_factory=lambda: [60, 60])
    comprops: List[int] = field(default_factory=lambda: [6, 1])
    hotkey: Optional[str] = None
    iconpath: Optional[str] = None
    menuitems: Optional[List[MenuItem]] = None

@dataclass
class CmdtextState:
    text: Optional[str] = None

@dataclass
class LstviewState:
    colnames: List[str] = field(default_factory=lambda: [])
    colprops: List[int] = field(default_factory=lambda: [])
    colclick: Optional[List[Callable]] = None
    rows: List[List[str]] = field(default_factory=lambda: [])
    selnum: Optional[int] = None
    hide: bool = False

@dataclass
class OuttextState:
    text: Optional[str] = None

@dataclass
class ProcessorInput:
    cmdtext: Optional[CmdtextState] = None
    lstview: Optional[LstviewState] = None
    outtext: Optional[OuttextState] = None
    key: Optional[KeyKind] = None
    is_complete: bool = False
    was_hidden: bool = True

    @property
    def cmd(self) -> str:
        if self.cmdtext is not None:
            return self.cmdtext.text or ''
        return ''

    @property
    def selrow(self):
        try:
            return self.lstview.rows[self.lstview.selnum]
        except Exception:
            return None

@dataclass
class ProcessorOutput:
    cmdtext: Optional[CmdtextState] = None
    lstview: Optional[LstviewState] = None
    outtext: Optional[OuttextState] = None
    hide: bool = False

    def add_cmd(self, text: str):
        self.cmdtext = CmdtextState(text=text)

    def add_out(self, text: str):
        self.outtext = OuttextState(text=text)

    def hide_rows(self):
        self.lstview = LstviewState(hide=True)

    def add_rows(self, names, props, click, rows, selnum=None):
        self.lstview = LstviewState(colnames=names, colprops=props, colclick=click, rows=rows, selnum=selnum)

class ProcessorBase(ABC):
    @abstractproperty
    def help(self) -> str:
        pass
    def update(self, pinput: ProcessorInput) -> Optional[ProcessorOutput]:
        pass

class SubprocessorBase(ProcessorBase):
    def use_processor(self, pinput: ProcessorInput) -> bool:
        pass

class TaskBarIcon(wx.adv.TaskBarIcon):
    def __init__(self, app):
        self.app = app
        super(TaskBarIcon, self).__init__()
        self.SetIcon(self.app.icon, self.app.config.name)
        self.Bind(wx.adv.EVT_TASKBAR_LEFT_DOWN, self.OnLeftClick)

    @staticmethod
    def CreateMenuItem(menu, label, func):
        item = wx.MenuItem(menu, -1, label)
        menu.Bind(wx.EVT_MENU, func, id=item.GetId())
        menu.Append(item)
        return item

    def CreatePopupMenu(self):
        menu = wx.Menu()
        if self.app.config.menuitems:
            for item in self.app.config.menuitems:
                TaskBarIcon.CreateMenuItem(menu, item.name, self.CreatePopupFunc(item))
            menu.AppendSeparator()
        TaskBarIcon.CreateMenuItem(menu, 'Help', self.OnHelp)
        TaskBarIcon.CreateMenuItem(menu, 'About', self.OnAbout)
        TaskBarIcon.CreateMenuItem(menu, 'Exit', self.OnExit)
        return menu

    def CreatePopupFunc(self, item):
        return lambda _: self.ShowMenuItemDialog(item)

    def ShowMenuItemDialog(self, item):
        no = 8
        if item.confirm and wx.MessageBox("Perform this action?", item.name, wx.YES_NO) == no:
            return
        item.func()
        wx.MessageBox(item.msg, item.name, wx.OK)

    def OnLeftClick(self, event):
        self.app.mainwin.DoShow()

    def OnHelp(self, event):
        wx.MessageDialog(None, self.app.processor.help, 'Help', wx.OK | wx.ICON_INFORMATION).ShowModal()

    def OnAbout(self, event):
        about = wx.adv.AboutDialogInfo()
        about.SetIcon(self.app.icon)
        about.SetName(self.app.config.name)
        about.SetVersion(self.app.config.version)
        about.SetDescription(self.app.config.about)
        wx.adv.AboutBox(about)

    def OnExit(self, event):
        self.Destroy()
        self.app.mainwin.Destroy()

class App(wx.App):
    def __init__(self, config, processor):
        self.config = config
        self.processor = processor
        super(App, self).__init__()

    def InitIcon(self):
        try:
            self.icon = wx.Icon(wx.Bitmap(self.config.iconpath))
        except Exception:
            self.icon = _Default.icon.GetIcon()

    def OnInit(self):
        self.ValidateConfig()
        self.mainwin = MainWindow(self)
        self.mainwin.Show()
        self.mainwin.UpdateOutput()
        self.InitIcon()
        TaskBarIcon(self)
        self.InitSystemHotkey()
        self.MainLoop()
        return True

    def ValidateConfig(self):
        if not self.config.name:
            _WxUtils.ErrorOut("Name must be provided!")
        if self.config.winpct[0] > 100 or self.config.winpct[1] > 100:
            _WxUtils.ErrorOut("Window percentage (winpct) cannot exceed 100!")

    @staticmethod
    def ParseHotkey(hotkey):
        toks = hotkey.split("+")
        mod = 0
        for tok in toks[:-1]:
            mod |= _WxUtils.ConvertStrToWxkey(tok)
        return mod, _WxUtils.ConvertStrToWxkey(toks[-1])

    def InitSystemHotkey(self):
        hotkey = self.config.hotkey
        if not hotkey:
            return
        hotkey_mod, hotkey_code = App.ParseHotkey(hotkey)
        hotkey_id = wx.NewIdRef(count=1)
        hotkey_ok = self.mainwin.RegisterHotKey(hotkey_id, hotkey_mod, hotkey_code)
        if not hotkey_ok:
            _WxUtils.ErrorOut("The hotkey could not be registered, may already be in use!")
        self.mainwin.Bind(wx.EVT_HOTKEY, lambda _: self.mainwin.ToggleShow(), id=hotkey_id)
        return hotkey_ok

class MainWindow(wx.MiniFrame):
    def __init__(self, app):
        self.colclick = []
        self.size = _WxUtils.CalcSize(0, app.config.winpct)
        super(MainWindow, self).__init__(None, -1, "", size=self.size, style=wx.NO_BORDER | wx.STAY_ON_TOP)
        self.app = app
        fsizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(fsizer)

        panel = wx.Panel(self, -1, size=self.size)
        psizer = wx.BoxSizer(wx.VERTICAL)

        title = wx.StaticText(panel, -1, self.app.config.name)
        psizer.Add(title, flag=wx.TOP | wx.ALIGN_CENTER, border=8)
        self.cmdtext = wx.TextCtrl(panel, style=wx.TE_RICH2)
        self.cmdtext.SetFocus()
        psizer.Add(self.cmdtext, flag=wx.ALL | wx.EXPAND, border=8)

        lstview_prop, outtext_prop = self.app.config.comprops
        self.lstview = dv.DataViewListCtrl(panel)
        self.lstview.Bind(dv.EVT_DATAVIEW_COLUMN_HEADER_CLICK, self.OnColClick)
        psizer.Add(self.lstview, proportion=lstview_prop, flag=wx.RIGHT | wx.LEFT | wx.DOWN | wx.EXPAND, border=8)

        self.outtext = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2)
        psizer.Add(self.outtext, proportion=outtext_prop, flag=wx.RIGHT | wx.LEFT | wx.DOWN | wx.EXPAND, border=8)

        panel.SetSizer(psizer)
        fsizer.Add(panel)

        self.Center()
        self.Layout()

        keybindings = [
            KeyBinding("", "ESC", lambda _: self.DoHide()),
            KeyBinding("", "ENTER", self.OnRowActivate),
            KeyBinding("CTRL", "ENTER", self.OnRowActivate),
            KeyBinding("CTRL", "K", self.MoveViewUp),
            KeyBinding("CTRL", "J", self.MoveViewDown),
            KeyBinding("", "UP", self.MoveViewUp),
            KeyBinding("", "DOWN", self.MoveViewDown),
            KeyBinding("CTRL", "H", self.MoveViewTop),
            KeyBinding("CTRL", "M", self.MoveViewMiddle),
            KeyBinding("CTRL", "L", self.MoveViewBottom),
            KeyBinding("CTRL", "P", self.OnPrev),
            KeyBinding("CTRL", "N", self.OnNext),
            KeyBinding("CTRL", "U", self.OnUndo),
            KeyBinding("CTRL", "I", self.OnInto),
            KeyBinding("CTRL", "O", self.OnOutof),
            KeyBinding("CTRL", "D", self.OnClearCmd),
        ]

        accels = []
        for binding in keybindings:
            binding_id = wx.NewIdRef(count=1)
            self.Bind(wx.EVT_MENU, binding.func, id=binding_id)
            mod = wx.ACCEL_CTRL if binding.mod == "CTRL" else wx.ACCEL_NORMAL
            key = _WxUtils.ConvertStrToWxkey(binding.key)
            accels.append([mod, key, binding_id])
        atbl = wx.AcceleratorTable(accels)
        self.SetAcceleratorTable(atbl)

        self.cmdtext.Bind(wx.EVT_KEY_DOWN, self.OnCmdKeyDown)
        self.cmdtext.Bind(wx.EVT_TEXT, self.OnCmdChange)
        self.Bind(dv.EVT_DATAVIEW_ITEM_ACTIVATED, self.OnRowActivate)
        self.Bind(wx.EVT_CLOSE, self.OnCloseWindow)
        self.Bind(wx.EVT_ACTIVATE, self.OnActivate)

        self.pinput = ProcessorInput(
            cmdtext=CmdtextState(),
            lstview=LstviewState(),
            outtext=OuttextState(),
        )

    def ToggleShow(self):
        if self.IsShown():
            self.DoHide()
        else:
            self.DoShow()

    def OnCmdKeyDown(self, event):
        if not event.HasModifiers():
            event.Skip()
        elif event.GetModifiers() == wx.MOD_CONTROL:
            ignore_keys = [
                ord('E'),
                ord('R'),
                ord('I'),
                wx.WXK_SUBTRACT,
                wx.WXK_ADD,
                61  # Non-numeric equals sign (=).
            ]
            if event.GetKeyCode() in ignore_keys:
                return  # Prevents default key behavior.
        event.Skip()

    def DoHide(self):
        self.Hide()
        self.cmdtext.SetValue("")
        self.pinput.was_hidden = True

    def DoShow(self):
        self.Show()
        self.Raise()
        self.UpdateOutput()
        self.cmdtext.SetFocus()
        self.Layout()

    def OnActivate(self, event):
        lost_focus = self.FindFocus() is not None
        if lost_focus:
            self.DoHide()

    def OnCmdChange(self, event):
        self.UpdateOutput()

    def OnRowActivate(self, event):
        self.UpdateOutput(True)

    def SelectRowNum(self, rownum):
        count = self.lstview.GetItemCount()
        if count == 0:
            return
        num = rownum
        if count <= rownum:
            num = count - 1
        elif rownum < 0:
            num = 0
        item = self.lstview.RowToItem(num)
        self.lstview.Select(item)
        self.lstview.EnsureVisible(item)

    def MoveViewUp(self, event):
        row = self.lstview.GetSelectedRow()
        row -= 1
        if row < 0:
            row = self.lstview.GetItemCount() - 1
        self.SelectRowNum(row)

    def MoveViewDown(self, event):
        row = self.lstview.GetSelectedRow()
        row += 1
        if row >= self.lstview.GetItemCount():
            row = 0
        self.SelectRowNum(row)

    def MoveViewTop(self, event):
        self.SelectRowNum(0)

    def MoveViewBottom(self, event):
        self.SelectRowNum(self.lstview.GetItemCount() - 1)

    def MoveViewMiddle(self, event):
        row = self.lstview.GetItemCount() // 2
        self.SelectRowNum(row)

    def OnNext(self, event):
        self.UpdateOutput(key=KeyKind.NEXT)

    def OnPrev(self, event):
        self.UpdateOutput(key=KeyKind.PREV)

    def OnUndo(self, event):
        self.UpdateOutput(key=KeyKind.UNDO)

    def OnInto(self, event):
        self.UpdateOutput(key=KeyKind.INTO)

    def OnOutof(self, event):
        self.UpdateOutput(key=KeyKind.OUTOF)

    def OnClearCmd(self, event):
        self.cmdtext.SetValue('')
        self.cmdtext.SetFocus()

    def OnColClick(self, event):
        colnum = event.GetColumn()
        if len(self.colclick) < (colnum + 1):
            return
        colclick = self.colclick[colnum]
        if colclick:
            colclick(self.cmdtext.AppendText)

    def UpdateOutput(self, complete=False, key=None):
        if not self.IsShown():
            return

        self.pinput.is_complete = complete
        self.pinput.key = key
        self.pinput.cmdtext.text = self.cmdtext.GetValue()
        self.pinput.lstview.selnum = self.lstview.GetSelectedRow()
        out = self.app.processor.update(self.pinput)

        if out is None:
            return

        if out.lstview and out.lstview.colclick and len(out.lstview.colclick) > 0:
            self.colclick = out.lstview.colclick
        else:
            self.colclick = []

        self.pinput.was_hidden = False
        if out.hide:
            self.DoHide()
            self.pinput.cmdtext = CmdtextState()
            self.pinput.lstview = LstviewState()
            self.pinput.outtext = OuttextState()
            return

        lstview_prop, outtext_prop = self.app.config.comprops

        if lstview_prop == 0:
            self.lstview.Hide()
            self.Layout()
        elif out.lstview is not None:
            if out.lstview.hide:
                self.lstview.Hide()
                self.Layout()
            else:
                self.lstview.Show()
                self.Layout()
                self.lstview.ClearColumns()
                wmargin = 40  # Accounts for borders and scrollbar.
                proptotal = sum(out.lstview.colprops)
                for idx, colname in enumerate(out.lstview.colnames):
                    width = floor((self.size[0] - wmargin) * (out.lstview.colprops[idx] / proptotal))
                    self.lstview.AppendTextColumn(colname, width=width)
                self.lstview.DeleteAllItems()
                for row in out.lstview.rows:
                    if row:
                        self.lstview.AppendItem(row)
                if out.lstview.selnum is None:
                    self.SelectRowNum(0)
                else:
                    self.SelectRowNum(out.lstview.selnum)
                self.pinput.lstview = out.lstview

        if outtext_prop == 0:
            self.outtext.Hide()
            self.Layout()
        elif out.outtext is not None:
            if out.outtext.text is not None:
                self.outtext.SetValue(out.outtext.text)
                self.pinput.outtext.text = out.outtext.text

        # NOTE: Update cmdtext last! It will trigger another UpdateOutput()
        # call. Could cause race condition if not careful here.
        if out.cmdtext is not None and out.cmdtext.text is not None:
            self.cmdtext.SetValue(out.cmdtext.text)
            self.cmdtext.SetInsertionPoint(len(out.cmdtext.text))
            self.pinput.cmdtext.text = out.cmdtext.text

    def OnCloseWindow(self, event):
        pass # This disables ALT+F4

class _WxUtils:
    @staticmethod
    def ErrorOut(msg):
        wx.MessageBox(msg, 'QWindow Fatal Error', wx.OK | wx.ICON_ERROR)
        exit()

    @staticmethod
    def ConvertStrToWxkey(keystr):
        if len(keystr) == 1: return ord(keystr)
        ukeystr = keystr.upper()
        if ukeystr == "CTRL": return wx.MOD_CONTROL
        if ukeystr == "ALT": return wx.MOD_ALT
        if ukeystr == "SPACE": return wx.WXK_SPACE
        if ukeystr == "ESC": return wx.WXK_ESCAPE
        if ukeystr == "ENTER": return wx.WXK_RETURN
        if ukeystr == "UP": return wx.WXK_UP
        if ukeystr == "DOWN": return wx.WXK_DOWN
        if ukeystr == "LEFT": return wx.WXK_LEFT
        if ukeystr == "RIGHT": return wx.WXK_RIGHT

    @staticmethod
    def CalcSize(displaynum, winpct):
        displays = (wx.Display(i) for i in range(wx.Display.GetCount()))
        sizes = [display.GetGeometry().GetSize() for display in displays]
        monitor = sizes[displaynum]
        width = monitor[0]
        height = monitor[1]
        size = (
            int(width * winpct[0] / 100),
            int(height * winpct[1] / 100)
        )
        return size

##==============================================================#
## SECTION: Function Definitions                                #
##==============================================================#

def subprocessors(method):
    def wrapper(self, pinput):
        if hasattr(self, "_subprocessors"):
            for sub in self._subprocessors:
                if sub.use_processor(pinput):
                    return sub.update(pinput)
        return method(self, pinput)
    return wrapper

##==============================================================#
## SECTION: Main Body                                           #
##==============================================================#

if __name__ == '__main__':
    pass
