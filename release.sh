#!/bin/bash

branch=`git rev-parse --abbrev-ref HEAD`
if [ "$branch" != "blender-2.8" ]; then
  echo "Not on blender-2.8 branch, exiting"
  exit
fi

rm release/blender_ls3.zip
mkdir io_scene_ls3
cp -r README.md batchexport_settings.xml __init__.py lsb.py ls3_export.py ls3_import.py ls_import.py zusiconfig.py.default zusiprops.py i18n.py l10n io_scene_ls3
mkdir  -p io_scene_ls3/zusicommon/zusicommon
cp zusicommon/zusicommon/__init__.py io_scene_ls3/zusicommon/zusicommon
7z a -r -tzip release/blender_ls3.zip io_scene_ls3
rm -rf io_scene_ls3

if [ "$1" != "upload" ]; then
  echo "Not uploading, call with 'upload' parameter to upload"
  exit
fi

if [ `git rev-parse blender-2.8` != `git rev-parse origin/blender-2.8` ]; then
  echo "Branch blender-2.8 is behind origin/blender-2.8, please push first. Exiting"
  exit
fi

echo -n "Tag name (v140423): "
read tag_name

echo -n "Version name (Version 2014-04-23): "
read version_name

echo -n "Description (in German?): "
read descr

echo -n "GitHub personal access token: "
read token

curl -H "Authorization: token $token" https://api.github.com/repos/zusitools/blender_ls3/releases -d "{\"target_commitish\":\"blender-2.8\",\"tag_name\":\"$tag_name\",\"name\":\"$version_name\",\"body\":\"$descr\"}"

echo -n "Release ID: "
read release_id

curl -H "Content-Type:application/octet-stream" -H "Authorization: token $token" "https://uploads.github.com/repos/zusitools/blender_ls3/releases/$release_id/assets?name=blender_ls3.zip" --data-binary @release/blender_ls3.zip
