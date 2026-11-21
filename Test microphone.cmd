@echo off
if "%~1"=="" (
    call "%~dp0Auto-C.cmd" --display --dry-run
) else (
    call "%~dp0Auto-C.cmd" --dry-run %*
)
