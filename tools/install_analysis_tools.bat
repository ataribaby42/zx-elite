@echo off
setlocal
pushd "%~dp0.."
python -m pip install --target tools\deps skoolkit==10.0
set "ZX_RESULT=%ERRORLEVEL%"
popd
exit /b %ZX_RESULT%
