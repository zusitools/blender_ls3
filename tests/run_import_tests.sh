#!/bin/sh
mv ../zusiconfig.py ../zusiconfig.py.backup
blender -P ./ls3_import_test.py
mv ../zusiconfig.py.backup ../zusiconfig.py
