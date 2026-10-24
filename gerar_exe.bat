@echo off
rem Gera "Assistente do Vendedor.exe" (versao REAL, usa o src\config.json) na pasta dist\.
rem Depois, coloque o .exe ao lado do config.json. Para testar sem credenciais: gerar_exe_demo.bat
rem Requer: py -m pip install --user pyinstaller customtkinter requests pillow playwright
rem          py -m playwright install chromium   (navegador do envio automatico pelo WhatsApp)
cd /d "%~dp0"
py -m PyInstaller --noconfirm --clean --onefile --windowed --name "Assistente do Vendedor" ^
  --icon "%~dp0src\icone.ico" --add-data "%~dp0src\icone.ico;." --collect-data customtkinter ^
  --paths "%~dp0src" --hidden-import ferramentas_internas --hidden-import BLING --hidden-import TRAY ^
  --hidden-import configuracao --hidden-import notas_compras --hidden-import fichas --hidden-import prazos_frete ^
  --hidden-import WHATSAPP --hidden-import PIL.ImageGrab --hidden-import PIL.ImageDraw --hidden-import PIL.ImageFont ^
  --collect-all playwright ^
  --workpath "%TEMP%\assistente_build" --specpath "%TEMP%\assistente_build" --distpath "%~dp0dist" ^
  "%~dp0src\app.py"
if errorlevel 1 (
  echo.
  echo ERRO ao gerar o executavel. Veja as mensagens acima.
  pause
  exit /b 1
)
echo.
echo Pronto: dist\Assistente do Vendedor.exe (coloque-o ao lado do config.json)
pause
