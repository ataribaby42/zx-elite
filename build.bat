REM make.bat ship=krait laser=original font=128 scannerpixelfix=no stationrandomlaunchfix=no stationslotfix=no fuelfix=no hyperspacedockingfix=no aicouragefix=no scannerblipfix=no stardustfix=no missiletargetfix=no textfullstopfix=no iffunit=no randomizedspawn=no competitionremove=no rotationdriftfix=no dockingrotation=no trafficcontrol=no verify=yes tapfile=elite-128k.tap trafficcontrol=no 

call make.bat verify=yes tapfile=elite-128k.tap
if errorlevel 1 exit /b %errorlevel%

call make.bat ship=krait laser=original font=128fix scannerpixelfix=yes stationrandomlaunchfix=yes stationslotfix=yes fuelfix=yes hyperspacedockingfix=yes aicouragefix=yes scannerblipfix=yes stardustfix=yes missiletargetfix=yes textfullstopfix=yes iffunit=no randomizedspawn=yes rotationdriftfix=yes dockingrotation=yes trafficcontrol=yes verify=no tapfile=elite-128k-A-side-Krait.tap
if errorlevel 1 exit /b %errorlevel%
call make.bat ship=adder laser=original font=128fix scannerpixelfix=yes stationrandomlaunchfix=yes stationslotfix=yes fuelfix=yes hyperspacedockingfix=yes aicouragefix=yes scannerblipfix=yes stardustfix=yes missiletargetfix=yes textfullstopfix=yes iffunit=no randomizedspawn=yes rotationdriftfix=yes dockingrotation=yes trafficcontrol=yes verify=no tapfile=elite-128k-B-side-Adder.tap
if errorlevel 1 exit /b %errorlevel%

call make.bat ship=krait laser=original font=128fix scannerpixelfix=yes stationrandomlaunchfix=yes stationslotfix=yes fuelfix=yes hyperspacedockingfix=yes aicouragefix=yes scannerblipfix=yes stardustfix=yes missiletargetfix=yes textfullstopfix=yes iffunit=no randomizedspawn=yes rotationdriftfix=yes dockingrotation=yes trafficcontrol=yes verify=no tapfile=elite-128k-A-side-Krait.tap
if errorlevel 1 exit /b %errorlevel%
call make.bat ship=adder laser=original font=128fix scannerpixelfix=yes stationrandomlaunchfix=yes stationslotfix=yes fuelfix=yes hyperspacedockingfix=yes aicouragefix=yes scannerblipfix=yes stardustfix=yes missiletargetfix=yes textfullstopfix=yes iffunit=no randomizedspawn=yes rotationdriftfix=yes dockingrotation=yes trafficcontrol=yes verify=no tapfile=elite-128k-B-side-Adder.tap
if errorlevel 1 exit /b %errorlevel%

call make.bat ship=krait laser=original font=48 scannerpixelfix=yes stationrandomlaunchfix=yes stationslotfix=yes fuelfix=yes hyperspacedockingfix=yes aicouragefix=yes scannerblipfix=yes stardustfix=yes missiletargetfix=yes textfullstopfix=yes iffunit=no randomizedspawn=yes rotationdriftfix=yes dockingrotation=yes trafficcontrol=yes verify=no tapfile=elite-128k-font48k-A-side-Krait.tap
if errorlevel 1 exit /b %errorlevel%
call make.bat ship=adder laser=original font=48 scannerpixelfix=yes stationrandomlaunchfix=yes stationslotfix=yes fuelfix=yes hyperspacedockingfix=yes aicouragefix=yes scannerblipfix=yes stardustfix=yes missiletargetfix=yes textfullstopfix=yes iffunit=no randomizedspawn=yes rotationdriftfix=yes dockingrotation=yes trafficcontrol=yes verify=no tapfile=elite-128k-font48k-B-side-Adder.tap
if errorlevel 1 exit /b %errorlevel%

call make.bat ship=krait laser=original font=128fix_ecm_s scannerpixelfix=yes stationrandomlaunchfix=yes stationslotfix=yes fuelfix=yes hyperspacedockingfix=yes aicouragefix=yes scannerblipfix=yes stardustfix=yes missiletargetfix=yes textfullstopfix=yes iffunit=no randomizedspawn=yes rotationdriftfix=yes dockingrotation=yes trafficcontrol=yes verify=no tapfile=elite-128k-fontECM_S-A-side-Krait.tap
if errorlevel 1 exit /b %errorlevel%
call make.bat ship=adder laser=original font=128fix_ecm_s scannerpixelfix=yes stationrandomlaunchfix=yes stationslotfix=yes fuelfix=yes hyperspacedockingfix=yes aicouragefix=yes scannerblipfix=yes stardustfix=yes missiletargetfix=yes textfullstopfix=yes iffunit=no randomizedspawn=yes rotationdriftfix=yes dockingrotation=yes trafficcontrol=yes verify=no tapfile=elite-128k-fontECM_S-B-side-Adder.tap
if errorlevel 1 exit /b %errorlevel%

call make.bat ship=krait laser=single font=128fix scannerpixelfix=yes stationrandomlaunchfix=yes stationslotfix=yes fuelfix=yes hyperspacedockingfix=yes aicouragefix=yes scannerblipfix=yes stardustfix=yes missiletargetfix=yes textfullstopfix=yes iffunit=no randomizedspawn=yes rotationdriftfix=yes dockingrotation=yes trafficcontrol=yes verify=no tapfile=elite-128k-single-laser-A-side-Krait.tap
if errorlevel 1 exit /b %errorlevel%
call make.bat ship=adder laser=single font=128fix scannerpixelfix=yes stationrandomlaunchfix=yes stationslotfix=yes fuelfix=yes hyperspacedockingfix=yes aicouragefix=yes scannerblipfix=yes stardustfix=yes missiletargetfix=yes textfullstopfix=yes iffunit=no randomizedspawn=yes rotationdriftfix=yes dockingrotation=yes trafficcontrol=yes verify=no tapfile=elite-128k-single-laser-B-side-Adder.tap
if errorlevel 1 exit /b %errorlevel%

call make.bat ship=krait laser=single font=48 scannerpixelfix=yes stationrandomlaunchfix=yes stationslotfix=yes fuelfix=yes hyperspacedockingfix=yes aicouragefix=yes scannerblipfix=yes stardustfix=yes missiletargetfix=yes textfullstopfix=yes iffunit=no randomizedspawn=yes rotationdriftfix=yes dockingrotation=yes trafficcontrol=yes verify=no tapfile=elite-128k-font48k-single-laser-A-side-Krait.tap
if errorlevel 1 exit /b %errorlevel%
call make.bat ship=adder laser=single font=48 scannerpixelfix=yes stationrandomlaunchfix=yes stationslotfix=yes fuelfix=yes hyperspacedockingfix=yes aicouragefix=yes scannerblipfix=yes stardustfix=yes missiletargetfix=yes textfullstopfix=yes iffunit=no randomizedspawn=yes rotationdriftfix=yes dockingrotation=yes trafficcontrol=yes verify=no tapfile=elite-128k-font48k-single-laser-B-side-Adder.tap
if errorlevel 1 exit /b %errorlevel%

call make.bat ship=krait laser=single font=128fix_ecm_s scannerpixelfix=yes stationrandomlaunchfix=yes stationslotfix=yes fuelfix=yes hyperspacedockingfix=yes aicouragefix=yes scannerblipfix=yes stardustfix=yes missiletargetfix=yes textfullstopfix=yes iffunit=no randomizedspawn=yes rotationdriftfix=yes dockingrotation=yes trafficcontrol=yes verify=no tapfile=elite-128k-fontECM_S-single-laser-A-side-Krait.tap
if errorlevel 1 exit /b %errorlevel%
call make.bat ship=adder laser=single font=128fix_ecm_s scannerpixelfix=yes stationrandomlaunchfix=yes stationslotfix=yes fuelfix=yes hyperspacedockingfix=yes aicouragefix=yes scannerblipfix=yes stardustfix=yes missiletargetfix=yes textfullstopfix=yes iffunit=no randomizedspawn=yes rotationdriftfix=yes dockingrotation=yes trafficcontrol=yes verify=no tapfile=elite-128k-fontECM_S-single-laser-B-side-Adder.tap
if errorlevel 1 exit /b %errorlevel%

call make.bat ship=krait laser=original font=128fix scannerpixelfix=yes stationrandomlaunchfix=yes stationslotfix=yes fuelfix=yes hyperspacedockingfix=yes aicouragefix=yes scannerblipfix=yes stardustfix=yes missiletargetfix=yes textfullstopfix=yes iffunit=yes randomizedspawn=yes rotationdriftfix=yes dockingrotation=yes trafficcontrol=yes verify=no tapfile=elite-128k-A-side-Krait-IFF.tap
if errorlevel 1 exit /b %errorlevel%
call make.bat ship=adder laser=original font=128fix scannerpixelfix=yes stationrandomlaunchfix=yes stationslotfix=yes fuelfix=yes hyperspacedockingfix=yes aicouragefix=yes scannerblipfix=yes stardustfix=yes missiletargetfix=yes textfullstopfix=yes iffunit=yes randomizedspawn=yes rotationdriftfix=yes dockingrotation=yes trafficcontrol=yes verify=no tapfile=elite-128k-B-side-Adder-IFF.tap
if errorlevel 1 exit /b %errorlevel%

call make.bat ship=krait laser=original font=128fix scannerpixelfix=yes stationrandomlaunchfix=yes stationslotfix=yes fuelfix=yes hyperspacedockingfix=yes aicouragefix=yes scannerblipfix=yes stardustfix=yes missiletargetfix=yes textfullstopfix=yes iffunit=yes randomizedspawn=yes rotationdriftfix=yes dockingrotation=yes trafficcontrol=yes verify=no tapfile=elite-128k-A-side-Krait-IFF.tap
if errorlevel 1 exit /b %errorlevel%
call make.bat ship=adder laser=original font=128fix scannerpixelfix=yes stationrandomlaunchfix=yes stationslotfix=yes fuelfix=yes hyperspacedockingfix=yes aicouragefix=yes scannerblipfix=yes stardustfix=yes missiletargetfix=yes textfullstopfix=yes iffunit=yes randomizedspawn=yes rotationdriftfix=yes dockingrotation=yes trafficcontrol=yes verify=no tapfile=elite-128k-B-side-Adder-IFF.tap
if errorlevel 1 exit /b %errorlevel%

call make.bat ship=krait laser=original font=48 scannerpixelfix=yes stationrandomlaunchfix=yes stationslotfix=yes fuelfix=yes hyperspacedockingfix=yes aicouragefix=yes scannerblipfix=yes stardustfix=yes missiletargetfix=yes textfullstopfix=yes iffunit=yes randomizedspawn=yes rotationdriftfix=yes dockingrotation=yes trafficcontrol=yes verify=no tapfile=elite-128k-font48k-A-side-Krait-IFF.tap
if errorlevel 1 exit /b %errorlevel%
call make.bat ship=adder laser=original font=48 scannerpixelfix=yes stationrandomlaunchfix=yes stationslotfix=yes fuelfix=yes hyperspacedockingfix=yes aicouragefix=yes scannerblipfix=yes stardustfix=yes missiletargetfix=yes textfullstopfix=yes iffunit=yes randomizedspawn=yes rotationdriftfix=yes dockingrotation=yes trafficcontrol=yes verify=no tapfile=elite-128k-font48k-B-side-Adder-IFF.tap
if errorlevel 1 exit /b %errorlevel%

call make.bat ship=krait laser=original font=128fix_ecm_s scannerpixelfix=yes stationrandomlaunchfix=yes stationslotfix=yes fuelfix=yes hyperspacedockingfix=yes aicouragefix=yes scannerblipfix=yes stardustfix=yes missiletargetfix=yes textfullstopfix=yes iffunit=yes randomizedspawn=yes rotationdriftfix=yes dockingrotation=yes trafficcontrol=yes verify=no tapfile=elite-128k-fontECM_S-A-side-Krait-IFF.tap
if errorlevel 1 exit /b %errorlevel%
call make.bat ship=adder laser=original font=128fix_ecm_s scannerpixelfix=yes stationrandomlaunchfix=yes stationslotfix=yes fuelfix=yes hyperspacedockingfix=yes aicouragefix=yes scannerblipfix=yes stardustfix=yes missiletargetfix=yes textfullstopfix=yes iffunit=yes randomizedspawn=yes rotationdriftfix=yes dockingrotation=yes trafficcontrol=yes verify=no tapfile=elite-128k-fontECM_S-B-side-Adder-IFF.tap
if errorlevel 1 exit /b %errorlevel%

call make.bat ship=krait laser=single font=128fix scannerpixelfix=yes stationrandomlaunchfix=yes stationslotfix=yes fuelfix=yes hyperspacedockingfix=yes aicouragefix=yes scannerblipfix=yes stardustfix=yes missiletargetfix=yes textfullstopfix=yes iffunit=yes randomizedspawn=yes rotationdriftfix=yes dockingrotation=yes trafficcontrol=yes verify=no tapfile=elite-128k-single-laser-A-side-Krait-IFF.tap
if errorlevel 1 exit /b %errorlevel%
call make.bat ship=adder laser=single font=128fix scannerpixelfix=yes stationrandomlaunchfix=yes stationslotfix=yes fuelfix=yes hyperspacedockingfix=yes aicouragefix=yes scannerblipfix=yes stardustfix=yes missiletargetfix=yes textfullstopfix=yes iffunit=yes randomizedspawn=yes rotationdriftfix=yes dockingrotation=yes trafficcontrol=yes verify=no tapfile=elite-128k-single-laser-B-side-Adder-IFF.tap
if errorlevel 1 exit /b %errorlevel%

call make.bat ship=krait laser=single font=48 scannerpixelfix=yes stationrandomlaunchfix=yes stationslotfix=yes fuelfix=yes hyperspacedockingfix=yes aicouragefix=yes scannerblipfix=yes stardustfix=yes missiletargetfix=yes textfullstopfix=yes iffunit=yes randomizedspawn=yes rotationdriftfix=yes dockingrotation=yes trafficcontrol=yes verify=no tapfile=elite-128k-font48k-single-laser-A-side-Krait-IFF.tap
if errorlevel 1 exit /b %errorlevel%
call make.bat ship=adder laser=single font=48 scannerpixelfix=yes stationrandomlaunchfix=yes stationslotfix=yes fuelfix=yes hyperspacedockingfix=yes aicouragefix=yes scannerblipfix=yes stardustfix=yes missiletargetfix=yes textfullstopfix=yes iffunit=yes randomizedspawn=yes rotationdriftfix=yes dockingrotation=yes trafficcontrol=yes verify=no tapfile=elite-128k-font48k-single-laser-B-side-Adder-IFF.tap
if errorlevel 1 exit /b %errorlevel%

call make.bat ship=krait laser=single font=128fix_ecm_s scannerpixelfix=yes stationrandomlaunchfix=yes stationslotfix=yes fuelfix=yes hyperspacedockingfix=yes aicouragefix=yes scannerblipfix=yes stardustfix=yes missiletargetfix=yes textfullstopfix=yes iffunit=yes randomizedspawn=yes rotationdriftfix=yes dockingrotation=yes trafficcontrol=yes verify=no tapfile=elite-128k-fontECM_S-single-laser-A-side-Krait-IFF.tap
if errorlevel 1 exit /b %errorlevel%
call make.bat ship=adder laser=single font=128fix_ecm_s scannerpixelfix=yes stationrandomlaunchfix=yes stationslotfix=yes fuelfix=yes hyperspacedockingfix=yes aicouragefix=yes scannerblipfix=yes stardustfix=yes missiletargetfix=yes textfullstopfix=yes iffunit=yes randomizedspawn=yes rotationdriftfix=yes dockingrotation=yes trafficcontrol=yes verify=no tapfile=elite-128k-fontECM_S-single-laser-B-side-Adder-IFF.tap
if errorlevel 1 exit /b %errorlevel%
