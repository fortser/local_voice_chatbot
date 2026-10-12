@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title Шурочка - установка и проверка

rem ==========================================================================
rem  Шурочка: установка зависимостей, дополнительных модулей и проверка.
rem
rem  Запуск двойным щелчком или из консоли:
rem    install_and_test.bat               всё, с вопросами по ходу
rem    install_and_test.bat --yes         без вопросов, ответы по умолчанию
rem    install_and_test.bat --no-gigaam   без модуля GigaAM-v3
rem    install_and_test.bat --no-tests    без автотестов
rem
rem  Шаги:
rem    1. Проверка Python
rem    2. Обновление pip
rem    3. PyTorch с поддержкой CUDA. С PyPI на Windows ставится только
rem       CPU-сборка, поэтому torch ставится отдельно и закрепляется:
rem       остальные пакеты не смогут его подменить.
rem    4. requirements.txt, включая фильтр речи silero-vad
rem    5. Дополнительный модуль GigaAM-v3: requirements-gigaam.txt и torchaudio
rem    6. Проверка окружения и Silero VAD на настоящей модели
rem    7. Автотесты pytest
rem    8. По желанию: ручная проверка фильтров с микрофоном
rem ==========================================================================

rem ---- Настройки -----------------------------------------------------------
rem Python проекта. Можно указать лаунчер: set "PY=py -3.10"
set "PY=python"
rem CUDA-сборка PyTorch для чистой установки; совместима с coqui-tts.
set "TORCH_VERSION=2.6.0"
set "TORCH_INDEX=https://download.pytorch.org/whl/cu124"
rem Прокси, если PyPI, download.pytorch.org или Hugging Face недоступны:
rem set "HTTPS_PROXY=http://127.0.0.1:10808"
rem set "HTTP_PROXY=http://127.0.0.1:10808"
rem --------------------------------------------------------------------------

set "WITH_GIGAAM=1"
set "WITH_TESTS=1"
set "ASK=1"
set "FAILED="
set "CONSTRAINTS=%TEMP%\shura_constraints.txt"

:parse_args
if "%~1"=="" goto args_done
if /i "%~1"=="--yes" set "ASK=0"
if /i "%~1"=="-y" set "ASK=0"
if /i "%~1"=="--no-gigaam" set "WITH_GIGAAM=0"
if /i "%~1"=="--no-tests" set "WITH_TESTS=0"
if /i "%~1"=="--help" goto usage
if /i "%~1"=="/?" goto usage
shift
goto parse_args
:args_done

if not exist "requirements.txt" (
    echo [ОШИБКА] Не найден requirements.txt. Положите этот файл в корень проекта.
    goto finish
)

rem ==== 1. Python ===========================================================
call :header 1 "Проверка Python"
%PY% --version >nul 2>&1
if errorlevel 1 (
    echo   [ОШИБКА] Python не найден по команде "%PY%".
    echo   Установите Python 3.10 и отметьте "Add python.exe to PATH",
    echo   или укажите путь в строке set "PY=..." в начале этого файла.
    set "FAILED= [Python не найден]"
    goto summary
)
%PY% --version
for /f "delims=" %%v in ('%PY% -c "import sys; print(sys.version_info[0]*100 + sys.version_info[1])"') do set "PYVER=%%v"
if "!PYVER!"=="310" goto python_ok
if "!PYVER!"=="311" goto python_ok
echo   [ВНИМАНИЕ] Проект рассчитан на Python 3.10-3.11.
echo   На этой версии numpy 1.26.4, coqui-tts или openai-whisper могут не установиться.
call :ask "Всё равно продолжить" 1
if errorlevel 1 goto summary
:python_ok

rem ==== 2. pip ==============================================================
call :header 2 "Обновление pip"
%PY% -m pip install --upgrade pip
if errorlevel 1 call :fail "обновление pip"

rem ==== 3. PyTorch ==========================================================
call :header 3 "PyTorch с поддержкой CUDA"
call :torch_info
if not defined TORCH_VER goto torch_install
if "!TORCH_CU!"=="cpu" goto torch_cpu
echo   Уже установлен PyTorch !TORCH_VER!, CUDA !TORCH_CU!, видеокарта доступна: !TORCH_GPU!
goto torch_check_gpu

:torch_install
echo   PyTorch не найден. Ставлю CUDA-сборку %TORCH_VERSION% из %TORCH_INDEX%
%PY% -m pip install torch==%TORCH_VERSION% torchaudio==%TORCH_VERSION% --index-url %TORCH_INDEX%
if errorlevel 1 call :fail "установка PyTorch"
call :torch_info
goto torch_check_gpu

:torch_cpu
echo   [ВНИМАНИЕ] Установлен PyTorch !TORCH_VER! БЕЗ поддержки CUDA.
echo   Whisper и GigaAM на видеокарте с ним не запустятся.
call :ask "Переустановить PyTorch %TORCH_VERSION% с CUDA" 2
if errorlevel 1 goto torch_check_gpu
%PY% -m pip install --force-reinstall --no-deps torch==%TORCH_VERSION% torchaudio==%TORCH_VERSION% --index-url %TORCH_INDEX%
if errorlevel 1 call :fail "переустановка PyTorch"
call :torch_info

:torch_check_gpu
if /i "!TORCH_GPU!"=="False" if not "!TORCH_CU!"=="cpu" (
    echo   [ВНИМАНИЕ] PyTorch собран с CUDA, но видеокарта недоступна. Проверьте драйвер NVIDIA.
)
call :write_constraints

rem ==== 4. Основные зависимости ============================================
call :header 4 "Основные зависимости: requirements.txt"
%PY% -m pip install -r requirements.txt -c "%CONSTRAINTS%"
if errorlevel 1 call :fail "requirements.txt"

rem ==== 5. GigaAM-v3 ========================================================
if "%WITH_GIGAAM%"=="0" goto gigaam_skipped
call :header 5 "Дополнительный модуль: GigaAM-v3"
%PY% -c "import torchaudio" >nul 2>&1
if errorlevel 1 call :install_torchaudio
%PY% -m pip install -r requirements-gigaam.txt -c "%CONSTRAINTS%"
if errorlevel 1 call :fail "зависимости GigaAM-v3"
echo   Модель включается в программе: Настройки - Распознавание речи - GigaAM-v3.
call :ask "Скачать веса GigaAM-v3 сейчас, чтобы первый запуск не ждал загрузки" 2
if errorlevel 1 goto gigaam_done
echo   Загружаю модель на процессоре только для скачивания и проверки весов...
%PY% -c "from core.gigaam_stt import GigaAMSTT; m = GigaAMSTT(device='cpu'); m.load_model(); print('  GigaAM-v3 OK:', m.model_name)"
if errorlevel 1 call :fail "загрузка весов GigaAM-v3"
goto gigaam_done
:gigaam_skipped
call :header 5 "Дополнительный модуль GigaAM-v3 пропущен по флагу --no-gigaam"
:gigaam_done

rem ==== 6. Проверка окружения ==============================================
call :header 6 "Проверка окружения и фильтра речи Silero VAD"
set "CHECK_ARGS="
if "%WITH_GIGAAM%"=="1" set "CHECK_ARGS=--gigaam"
%PY% scripts\check_environment.py %CHECK_ARGS%
if errorlevel 1 call :fail "проверка окружения"

rem ==== 7. Автотесты ========================================================
if "%WITH_TESTS%"=="0" goto tests_skipped
call :header 7 "Автотесты pytest, без микрофона и долгих GPU-тестов"
%PY% -m pytest -q -m "not slow and not gpu"
if errorlevel 1 call :fail "автотесты pytest"
goto tests_done
:tests_skipped
call :header 7 "Автотесты пропущены по флагу --no-tests"
:tests_done

rem ==== 8. Ручная проверка ==================================================
call :header 8 "Ручная проверка фильтров с микрофоном"
echo   Скрипт покажет «сырой» Whisper и результат с фильтрами на тишине,
echo   щелчках и вашей фразе. Нужен микрофон, около двух минут.
call :ask "Запустить ручную проверку сейчас" 2
if errorlevel 1 goto summary
set "MANUAL_ARGS="
if "%WITH_GIGAAM%"=="0" goto manual_run
call :ask "Сравнить в этой проверке с GigaAM-v3" 2
if not errorlevel 1 set "MANUAL_ARGS=--gigaam"
:manual_run
%PY% stage_test\check_stage_speech_filters.py !MANUAL_ARGS!
if errorlevel 1 call :fail "ручная проверка не принята"

rem ==== Итог ================================================================
:summary
echo.
echo ============================================================
if defined FAILED (
    echo   Готово с ошибками:!FAILED!
    echo   Прокрутите окно вверх к строкам [ОШИБКА] и [FAIL].
) else (
    echo   Готово: зависимости установлены, проверки пройдены.
    echo   Запуск программы: go.bat
)
echo ============================================================

:finish
if exist "%CONSTRAINTS%" del "%CONSTRAINTS%" >nul 2>&1
if "%ASK%"=="1" pause
if defined FAILED (endlocal & exit /b 1)
endlocal & exit /b 0


rem ==========================================================================
rem  Подпрограммы
rem ==========================================================================

:usage
echo Использование: install_and_test.bat [--yes] [--no-gigaam] [--no-tests]
echo   --yes         без вопросов: ответы по умолчанию, без паузы в конце
echo   --no-gigaam   не ставить дополнительный модуль GigaAM-v3
echo   --no-tests    не запускать автотесты
endlocal & exit /b 0

:header
echo.
echo ============================================================
echo  Шаг %~1. %~2
echo ============================================================
exit /b 0

:fail
echo   [ОШИБКА] %~1
set "FAILED=!FAILED! [%~1]"
exit /b 0

rem Вопрос да/нет. Аргументы: текст вопроса и ответ по умолчанию, 1 да или 2 нет.
rem Возвращает errorlevel 0 для «да» и 1 для «нет». Цифры работают
rem при любой раскладке клавиатуры; без ответа за 30 с берётся умолчание.
:ask
if "%ASK%"=="0" (
    if "%~2"=="1" exit /b 0
    exit /b 1
)
choice /C 12 /N /T 30 /D %~2 /M "  %~1? 1 - да, 2 - нет [по умолчанию %~2]: "
if errorlevel 2 exit /b 1
exit /b 0

rem Версии установленного PyTorch: TORCH_VER, TORCH_BASE, TORCH_CU, TORCH_GPU, TORCH_TAG.
:torch_info
set "TORCH_VER="
set "TORCH_BASE="
set "TORCH_CU="
set "TORCH_GPU="
set "TORCH_TAG="
for /f "tokens=1-5" %%a in ('%PY% -c "import torch; v = torch.__version__; c = torch.version.cuda; print(v, v.split('+')[0], c or 'cpu', torch.cuda.is_available(), ('cu' + c.replace('.', '')) if c else 'cpu')" 2^>nul') do (
    set "TORCH_VER=%%a"
    set "TORCH_BASE=%%b"
    set "TORCH_CU=%%c"
    set "TORCH_GPU=%%d"
    set "TORCH_TAG=%%e"
)
exit /b 0

rem Закрепить установленные torch и torchaudio, чтобы pip их не заменил.
:write_constraints
type nul > "%CONSTRAINTS%"
if defined TORCH_VER >> "%CONSTRAINTS%" echo torch==!TORCH_VER!
for /f "delims=" %%v in ('%PY% -c "import torchaudio; print(torchaudio.__version__)" 2^>nul') do >> "%CONSTRAINTS%" echo torchaudio==%%v
exit /b 0

rem torchaudio той же версии и CUDA-сборки, что и установленный torch.
:install_torchaudio
if not defined TORCH_BASE (
    call :fail "torchaudio: сначала нужен PyTorch"
    exit /b 0
)
echo   Ставлю torchaudio !TORCH_BASE! под PyTorch !TORCH_VER!
if "!TORCH_TAG!"=="cpu" (
    %PY% -m pip install torchaudio==!TORCH_BASE!
) else (
    %PY% -m pip install torchaudio==!TORCH_BASE! --index-url https://download.pytorch.org/whl/!TORCH_TAG!
)
if errorlevel 1 call :fail "установка torchaudio"
call :write_constraints
exit /b 0
