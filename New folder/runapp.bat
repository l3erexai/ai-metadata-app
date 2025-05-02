@echo off
echo Starting AI Metadata App... Please wait.
cd /d "%~dp0"
py -m streamlit run 555.py
echo App server started. Check your web browser.
pause