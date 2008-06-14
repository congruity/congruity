#!/bin/sh

# This code NOT copyright Stephen Warren <s-t-concordance@wwwdotorg.org>
# This code is released into the public domain.

cd `dirname $0`

version=`./congruity --version`

name_ver=congruity-${version}
tar_name=${name_ver}.tar.bz2
tar_path=releases/${tar_name}

echo Releasing version ${name_ver}

rm -rf ${name_ver}
mkdir ${name_ver}
cp -rp \
  congruity \
  *.png \
  Changelog \
  congruity.1 \
  COPYING \
  LICENSE.txt \
  Makefile \
  README.txt \
  ${name_ver}

rm -rf ${tar_path}
tar jcvf ${tar_path} ${name_ver}
rm -rf ${name_ver}

