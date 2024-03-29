::=============================================================::
:: SECTION: Environment Setup                                  ::
::=============================================================::

@set TITLE=%~n0 "%~dp0"
@cd /d %~dp0 && echo off && title %TITLE%

::=============================================================::
:: SECTION: Main Body                                          ::
::=============================================================::

set ALL_OK=1
set DEP_OK=1
call:ChkDep^
    "Python"^
    "Python language interpreter."^
    "https://www.python.org"^
    "3.8+"^
    python -V
if %DEP_OK% equ 0 (
    set ALL_OK=0
    pause
)
set DEP_OK=1
call:ChkDep^
    "Pip"^
    "Python package manager."^
    "https://www.python.org"^
    "latest"^
    pip -V
if %DEP_OK% equ 0 (
    set ALL_OK=0
    pause
)
set DEP_OK=1
call:ChkDep^
    "Auxly"^
    "Python helper library."^
    "https://pypi.org/project/auxly/"^
    "latest"^
    python -c "import auxly"
if %DEP_OK% equ 0 (
    set ALL_OK=0
    pause
)
set DEP_OK=1
call:ChkDep^
    "PyYAML"^
    "Python YAML parser."^
    "https://pypi.org/project/PyYAML/"^
    "latest"^
    python -c "import yaml"
if %DEP_OK% equ 0 (
    set ALL_OK=0
    pause
)
set DEP_OK=1
call:ChkDep^
    "psutil"^
    "Python process monitor."^
    "https://pypi.org/project/psutil/"^
    "latest"^
    python -c "import psutil"
if %DEP_OK% equ 0 (
    set ALL_OK=0
    pause
)
set DEP_OK=1
call:ChkDep^
    "UltraJSON"^
    "Python JSON parser."^
    "https://pypi.org/project/ujson/"^
    "latest"^
    python -c "import ujson"
if %DEP_OK% equ 0 (
    set ALL_OK=0
    pause
)
set DEP_OK=1
call:ChkDep^
    "wxPython"^
    "Python GUI toolkit."^
    "https://pypi.org/project/wxPython/"^
    "latest"^
    python -c "import wx"
if %DEP_OK% equ 0 (
    set ALL_OK=0
    pause
)

echo --------
if %ALL_OK% equ 1 (
    echo [!] All dependencies successfully met.
) else (
    echo [WARNING] Some dependencies missing.
)
echo --------

pause
exit /b 0

::=============================================================::
:: SECTION: Function Definitions                               ::
::=============================================================::

::-------------------------------------------------------------::
:: Checks if a dependency is available.
::
:: **Params**:
::  - 1 - Name of dependency.
::  - 2 - Description of dependency.
::  - 3 - Reference website or where to obtain info.
::  - 4 - Recommended version.
::  - 5+ - Non-blocking command to check if installed; usually version display
::         or help.
::
:: **Attention**:
:: Do not use quotes around the non-blocking command.
:: Quotes may be included in the remaining params if they are needed for the
:: non-blocking call.
::
:: **Preconditions**:
:: The global variable DEP_OK should be set to 1 before the first call to this
:: function.
::
:: **Postconditions**:
:: The global variable DEP_OK will be set to 0 if a dependency check fails.
:: This variable is not set back to 1 by this function, it may be explicitly
:: set outside the function
::
:: **Example**:
:: call::ChkDep^
::     "Utility"^
::     "Does something."^
::     "www.website.com"^
::     "1.2.3"^
::     utility -h
:: call::ChkDep^
::     "Utility"^
::     "Does something."^
::     "www.website.com"^
::     "1.2.3"^
::     utility -c "non-blocking cmd"
::-------------------------------------------------------------::
:ChkDep
echo Checking dependency %~1...
shift
echo     %~1
shift
echo     Reference: %~1
shift
echo     Recommended version: %~1
shift
echo     --------
set CMD=%1
shift
:chkdep_shift_next
if [%1] neq [] (
    set CMD=%CMD% %1
    shift
    goto:chkdep_shift_next
)
call %CMD% > NUL 2>&1
if %ERRORLEVEL% neq 0 (
    echo     NOT FOUND!
    set DEP_OK=0
    goto:eof
)
echo     OK.
goto:eof
