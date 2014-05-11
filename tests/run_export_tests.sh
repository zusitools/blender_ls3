#!/bin/sh
mv ../zusiconfig.py ../zusiconfig.py.backup
blender -P ./ls3_export_test.py
mv ../zusiconfig.py.backup ../zusiconfig.py
