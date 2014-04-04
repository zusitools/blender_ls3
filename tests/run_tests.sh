#!/bin/sh
mv ../zusiconfig.py ../zusiconfig.py.backup
blender -P ./test.py
mv ../zusiconfig.py.backup ../zusiconfig.py
