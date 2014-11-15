#!/bin/bash

branch=`git rev-parse --abbrev-ref HEAD`
if [ "$branch" != "master" ]; then
  echo "Not on master branch, exiting"
  exit
fi

rm release/release.zip
mkdir io_scene_ls3
cp -r README.md batchexport_settings.py.default __init__.py ls3_export.py ls3_import.py ls_import.py zusicommon.py zusiconfig.py.default zusiprops.py i18n.py l10n io_scene_ls3
7z a -r -tzip release/release.zip io_scene_ls3
rm -rf io_scene_ls3

if [ "$1" != "upload" ]; then
  echo "Not uploading, call with 'upload' parameter to upload"
  exit
fi

if [ `git rev-parse master` != `git rev-parse origin/master` ]; then
  echo "Branch master is behind origin/master, please push first. Exiting"
  exit
fi

echo -n "Tag name (v140423): "
read tag_name

echo -n "Version name (Version 2014-04-23): "
read version_name

echo -n "Description (in German?): "
read descr

curl -u "zusitools" https://api.github.com/repos/zusitools/blender_ls3/releases -d "{\"tag_name\":\"$tag_name\",\"name\":\"$version_name\",\"body\":\"$descr\"}"

echo -n "Release ID: "
read release_id

curl -H "Content-Type:application/octet-stream" -u "zusitools" "https://uploads.github.com/repos/zusitools/blender_ls3/releases/$release_id/assets?name=release.zip" --data-binary @release/release.zip
