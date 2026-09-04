REM make.bat ship=krait laser=original font=128 scannerpixelfix=no stationrandomlaunchfix=no verify=yes tapfile=elite-128k.tap 

call make.bat verify=yes tapfile=elite-128k.tap

call make.bat ship=krait laser=original font=128fix scannerpixelfix=yes stationrandomlaunchfix=yes verify=no tapfile=elite-128k-A-side-Krait.tap
call make.bat ship=adder laser=original font=128fix scannerpixelfix=yes stationrandomlaunchfix=yes verify=no tapfile=elite-128k-B-side-Adder.tap

call make.bat ship=krait laser=single font=128fix scannerpixelfix=yes stationrandomlaunchfix=yes verify=no tapfile=elite-128k-single-laser-A-side-Krait.tap
call make.bat ship=adder laser=single font=128fix scannerpixelfix=yes stationrandomlaunchfix=yes verify=no tapfile=elite-128k-single-laser-B-side-Adder.tap