#!/bin/bash

set -e

INSTALL_PREFIX=$(readlink -f "$1")
if [ ! -d "$INSTALL_PREFIX" ]; then
    echo Installation prefix is not a directory: $INSTALL_PREFIX
    exit 1
fi

SOURCE_DIR=$(dirname $0)
cd $SOURCE_DIR

# Bazel makes it's output artifacts read-only, but we'd like our
# installed versions to be overwritten if this script is run again.
chmod -R u+w bazel-bin/src
chmod -R u+w bazel-bin/lcmtypes
chmod -R u+w bazel-genfiles/lcmtypes

cp -a bazel-bin/src/optitrack_client* $INSTALL_PREFIX/bin
cp bazel-bin/lcmtypes/liblcmtypes_optitrack.jar $INSTALL_PREFIX/share/java/lcmtypes_optitrack.jar

# TODO(sam.creasey) The hardcoded python2.7 here isn't great.
PYTHON_TARGET=$INSTALL_PREFIX/lib/python2.7/dist-packages/optitrack
if [ ! -d "$PYTHON_TARGET" ]; then
    mkdir $PYTHON_TARGET
fi
cp bazel-genfiles/lcmtypes/optitrack/*.py $PYTHON_TARGET
