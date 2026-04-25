@echo off
REM Double-click this file to start the Glam Shelf Twin.
REM A terminal window will open and stay open while the server runs.
REM To stop the server, close this window (or press Ctrl+C inside it).

cd /d "%~dp0"
call venv\Scripts\activate.bat
echo.
echo ============================================================
echo   Glam Shelf Twin is starting...
echo   Once you see "Running on http://127.0.0.1:5000",
echo   open http://localhost:5000 in your browser.
echo   CLOSE THIS WINDOW to stop the server.
echo ============================================================
echo.
python app.py
pause
