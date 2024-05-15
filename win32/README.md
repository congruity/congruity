This directory contains binary files needed to build the installer.

- `libconcord-1.5-py3-none-win32.whl`

  Binary package that contains the `libconcord` bindings, DLLs, and dependencies.  This package is produced by `make_wheel.py` in the `concordance` repo and the associated `ci-windows.yml` workflow.
  
- `msvcp140.dll`

  Redistributable Microsoft Visual C++ 2015 DLL required for `wxPython` to work.