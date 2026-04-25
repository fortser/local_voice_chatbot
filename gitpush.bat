@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ========================================
echo        Git Quick Commit ^& Push
echo ========================================
echo.

set /p "commit_message=Введите сообщение коммита: "

if "%commit_message%"=="" (
    echo ОШИБКА: сообщение коммита не может быть пустым!
    pause
    exit /b 1
)

echo.

echo [1/3] git add .
git add .
if %errorlevel% neq 0 (
    echo ОШИБКА на этапе git add!
    pause
    exit /b 1
)
echo OK - Файлы добавлены
echo.

echo [2/3] git commit -m "%commit_message%"
git commit -m "%commit_message%"
if %errorlevel% neq 0 (
    echo ОШИБКА на этапе git commit!
    pause
    exit /b 1
)
echo OK - Коммит создан
echo.

echo [3/3] git push -u origin HEAD
git push -u origin HEAD
if %errorlevel% neq 0 (
    echo ОШИБКА на этапе git push!
    pause
    exit /b 1
)
echo OK - Изменения отправлены

echo.
echo ========================================
echo        Всё выполнено успешно!
echo ========================================
echo.
pause
