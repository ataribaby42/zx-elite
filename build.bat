REM make.bat ship=krait laser=original font=128 scannerpixelfix=no stationrandomlaunchfix=no verify=yes tapfile=elite-128k.tap 

call make.bat verify=yes tapfile=elite-128k.tap

call make.bat ship=krait laser=original font=128fix scannerpixelfix=yes stationrandomlaunchfix=yes verify=no tapfile=elite-128k-A-side-Krait.tap
call make.bat ship=adder laser=original font=128fix scannerpixelfix=yes stationrandomlaunchfix=yes verify=no tapfile=elite-128k-B-side-Adder.tap

call make.bat ship=krait laser=original font=128fix scannerpixelfix=yes stationrandomlaunchfix=yes verify=no tapfile=elite-128k-A-side-Krait.tap
call make.bat ship=adder laser=original font=128fix scannerpixelfix=yes stationrandomlaunchfix=yes verify=no tapfile=elite-128k-B-side-Adder.tap

call make.bat ship=krait laser=original font=48 scannerpixelfix=yes stationrandomlaunchfix=yes verify=no tapfile=elite-128k-font48k-A-side-Krait.tap
call make.bat ship=adder laser=original font=48 scannerpixelfix=yes stationrandomlaunchfix=yes verify=no tapfile=elite-128k-font48k-B-side-Adder.tap

call make.bat ship=krait laser=original font=128fix_ecm_s scannerpixelfix=yes stationrandomlaunchfix=yes verify=no tapfile=elite-128k-fontECM_S-A-side-Krait.tap
call make.bat ship=adder laser=original font=128fix_ecm_s scannerpixelfix=yes stationrandomlaunchfix=yes verify=no tapfile=elite-128k-fontECM_S-B-side-Adder.tap

call make.bat ship=krait laser=single font=128fix scannerpixelfix=yes stationrandomlaunchfix=yes verify=no tapfile=elite-128k-single-laser-A-side-Krait.tap
call make.bat ship=adder laser=single font=128fix scannerpixelfix=yes stationrandomlaunchfix=yes verify=no tapfile=elite-128k-single-laser-B-side-Adder.tap

call make.bat ship=krait laser=single font=48 scannerpixelfix=yes stationrandomlaunchfix=yes verify=no tapfile=elite-128k-font48k-single-laser-A-side-Krait.tap
call make.bat ship=adder laser=single font=48 scannerpixelfix=yes stationrandomlaunchfix=yes verify=no tapfile=elite-128k-font48k-single-laser-B-side-Adder.tap

call make.bat ship=krait laser=single font=128fix_ecm_s scannerpixelfix=yes stationrandomlaunchfix=yes verify=no tapfile=elite-128k-fontECM_S-single-laser-A-side-Krait.tap
call make.bat ship=adder laser=single font=128fix_ecm_s scannerpixelfix=yes stationrandomlaunchfix=yes verify=no tapfile=elite-128k-fontECM_S-single-laser-B-side-Adder.tap