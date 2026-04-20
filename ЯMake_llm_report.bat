@echo off
chcp 65001 >nul
python "T:\test_python\индексатор и взаимосвязи\guicodes_s3_sp_cli.py" "%~dp0." -o "%~dp0LLM_report.md"
timeout /t 20