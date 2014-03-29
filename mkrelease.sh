#!/bin/sh

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <git tag, e.g. congruity-18>"
    exit 1
fi
VERSION=$1

git archive --format=tar --prefix=${VERSION}/ ${VERSION} | bzip2 > ${VERSION}.tar.bz2

