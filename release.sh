#!/bin/bash
mkdir io_scene_ls3
cp batchexport_settings.py.default __init__.py ls3_export.py ls3_import.py ls_import.py zusicommon.py zusiconfig.py.default zusiprops.py io_scene_ls3
zip -r release.zip io_scene_ls3
mv release.zip release
rm -rf io_scene_ls3