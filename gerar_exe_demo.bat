@echo off
rem Gera "Assistente do Vendedor - DEMO.exe" na pasta dist\ (versao de demonstracao).
rem A demonstracao usa dados ficticios (src\demo.py): nao le config.json nem tokens
rem e nao acessa Bling, Trello, Tray ou WhatsApp. Por isso o .exe sai SEM os modulos de integracao
rem e sem as bibliotecas que so eles usam (internet, criptografia, navegador) - fica menor.
rem O Pillow entra: e ele que desenha as fichas dos cards.
rem Requer: py -m pip install --user pyinstaller customtkinter pillow
cd /d "%~dp0"
py -m PyInstaller --noconfirm --clean --onefile --windowed --name "Assistente do Vendedor - DEMO" ^
  --icon "%~dp0src\icone.ico" --add-data "%~dp0src\icone.ico;." --collect-data customtkinter ^
  --paths "%~dp0src" --hidden-import ferramentas_internas --hidden-import demo --hidden-import app ^
  --hidden-import configuracao --hidden-import notas_compras --hidden-import fichas --hidden-import prazos_frete ^
  --hidden-import PIL.ImageDraw --hidden-import PIL.ImageFont ^
  --exclude-module BLING --exclude-module TRAY --exclude-module WHATSAPP --exclude-module playwright ^
  --exclude-module requests --exclude-module urllib3 --exclude-module charset_normalizer ^
  --exclude-module idna --exclude-module certifi --exclude-module cryptography ^
  --exclude-module setuptools --exclude-module pkg_resources ^
  --workpath "%TEMP%\assistente_demo_build" --specpath "%TEMP%\assistente_demo_build" --distpath "%~dp0dist" ^
  "%~dp0src\app_demo.py"
if errorlevel 1 (
  echo.
  echo ERRO ao gerar o executavel. Se a demonstracao estiver aberta, feche-a e rode de novo.
  pause
  exit /b 1
)
echo.
echo Pronto: dist\Assistente do Vendedor - DEMO.exe
pause
