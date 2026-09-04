@echo off
setlocal
pushd "%~dp0"
python tools\build.py --verify-only %*
set "ZX_RESULT=%ERRORLEVEL%"
popd
exit /b %ZX_RESULT%
