@echo off
echo Starting Whale's Journey Multiplayer Game...
echo.
echo Starting Python server...
start cmd /k python server.py
echo.
echo Opening game in browser...
timeout /t 2 /nobreak >nul
start "" "index.html"
echo.
echo Game started! Have fun!