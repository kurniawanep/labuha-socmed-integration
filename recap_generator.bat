@echo off
title Generator Rekapitulasi Penyebaran Informasi
color 0B

:: Pastikan berjalan di direktori file batch ini berada
cd /d "%~dp0"

:menu
cls
echo ===================================================
echo             MENU REKAPITULASI PENYEBARAN
echo ===================================================
echo.
echo  [1] Buat Rekap Ringkasan (Rentang Tanggal)
echo  [2] Buat Rekap Detail (Rentang Tanggal)
echo  [3] Buat Rekap Ringkasan (Semua Waktu)
echo  [4] Buat Rekap Detail (Semua Waktu)
echo  [5] Tampilkan Daftar Pegawai (staff.json)
echo  [6] Cek Penggunaan Penyimpanan Supabase
echo  [7] Bersihkan Penyimpanan Supabase
echo  [8] Keluar
echo.
echo ===================================================
set "choice="
set /p choice="Pilih opsi (1-8): "

if "%choice%"=="1" goto date_summary
if "%choice%"=="2" goto date_detail
if "%choice%"=="3" goto all_summary
if "%choice%"=="4" goto all_detail
if "%choice%"=="5" goto list_staff
if "%choice%"=="6" goto list_storage
if "%choice%"=="7" goto cleanup_storage
if "%choice%"=="8" exit /b
goto menu

:date_summary
echo.
echo --- Masukkan Rentang Tanggal (Format: YYYY-MM-DD) ---
set /p start_date="Masukkan tanggal MULAI (inklusif): "
set /p end_date="Masukkan tanggal SELESAI (inklusif): "
echo.
echo Menjalankan rekap ringkasan dari %start_date% sampai %end_date%...
".venv\Scripts\python.exe" report_generator.py --from %start_date% --to %end_date%
echo.
pause
goto menu

:date_detail
echo.
echo --- Masukkan Rentang Tanggal (Format: YYYY-MM-DD) ---
set /p start_date="Masukkan tanggal MULAI (inklusif): "
set /p end_date="Masukkan tanggal SELESAI (inklusif): "
echo.
echo Menjalankan rekap detail dari %start_date% sampai %end_date%...
".venv\Scripts\python.exe" report_generator.py --from %start_date% --to %end_date% --detail
echo.
pause
goto menu

:all_summary
echo.
echo Menjalankan rekap ringkasan semua waktu...
".venv\Scripts\python.exe" report_generator.py
echo.
pause
goto menu

:all_detail
echo.
echo Menjalankan rekap detail semua waktu...
".venv\Scripts\python.exe" report_generator.py --detail
echo.
pause
goto menu

:list_staff
echo.
".venv\Scripts\python.exe" report_generator.py --list-staff
echo.
pause
goto menu

:list_storage
echo.
".venv\Scripts\python.exe" report_generator.py --list-storage
echo.
pause
goto menu

:cleanup_storage
echo.
set /p days="Hapus file yang lebih lama dari berapa hari? (default: 7): "
if "%days%"=="" set days=7
echo.
".venv\Scripts\python.exe" report_generator.py --cleanup-storage %days%
echo.
pause
goto menu
