#!/bin/sh

# This code NOT copyright Stephen Warren <s-t-concordance@wwwdotorg.org>
# This code is released into the public domain.

cd `dirname $0`

name=congruity
version=`./congruity --version`

name_ver=${name}-${version}
tar_name=${name_ver}.tar.bz2
rel_path=releases
tar_path=${rel_path}/${tar_name}

echo Releasing version ${name_ver}

rm -rf ${name_ver}
mkdir ${name_ver}
cp -rp \
  congruity \
  harmony.wsdl \
  mhgui \
  mhmanager.py \
  *.png \
  *.xsd \
  Changelog \
  congruity.1 \
  congruity.desktop \
  COPYING \
  LICENSE.txt \
  Makefile \
  README.txt \
  ${name_ver}

rm -rf ${tar_path}
mkdir -p ${rel_path}
tar jcvf ${tar_path} ${name_ver}
rm -rf ${name_ver}

