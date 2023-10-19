##==============================================================#
## SECTION: Imports                                             #
##==============================================================#

from abc import ABC, abstractstaticmethod
from dataclasses import dataclass
import ctypes

import auxly
import psutil

try:
    import win32api
    import win32gui
    import win32process
    import win32con
except:
    pass

##==============================================================#
## SECTION: Class Definitions                                   #
##==============================================================#

##-- Generic ---------------------------------------------------#

@dataclass(frozen=True, eq=True)
class WinInfoBase:
    title: str
    exe: str
    pid: int

class WinControlBase(ABC):
    @abstractstaticmethod
    def show(self, winfo):
        pass
    @abstractstaticmethod
    def list(self):
        pass

##-- Windows ---------------------------------------------------#

if auxly.iswindows():

    @dataclass(frozen=True, eq=True)
    class WinInfo(WinInfoBase):
        hwnd: int

        def __hash__(self):
            return hash((self.exe, self.pid, self.hwnd))
        def __eq__(self, other):
            return hash(self) == hash(other)

    class WinControl(WinControlBase):
        @staticmethod
        def show(winfo):
            if win32gui.IsIconic(winfo.hwnd):
                win32gui.ShowWindow(winfo.hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(winfo.hwnd)

        @staticmethod
        def list():
            windows = []
            def cb(hwnd, lparam):
                if win32gui.IsWindowVisible(hwnd) and _is_alttab_win(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    exe = psutil.Process(pid).name()
                    info = WinInfo(title, exe, pid, hwnd)
                    windows.append(info)
            win32gui.EnumWindows(cb, None)
            return windows

    def _is_alttab_win(hwnd):
        if win32gui.GetWindowTextLength(hwnd) == 0:
            return False
        if ctypes.windll.user32.GetShellWindow() == hwnd:
            return False
        style = win32api.GetWindowLong(hwnd, win32con.GWL_STYLE)
        if (style & win32con.WS_EX_TOOLWINDOW):
            return False
        return True

##-- Linux  ----------------------------------------------------#

if auxly.islinux():

    @dataclass(frozen=True, eq=True)
    class WinInfo(WinInfoBase):
        pass  # Not implemented

    class WinControl(WinControlBase):
        @staticmethod
        def show(winfo):
            pass  # Not implemented

        @staticmethod
        def list():
            pass  # Not implemented

##==============================================================#
## SECTION: Main Body                                           #
##==============================================================#

if __name__ == '__main__':
    pass
