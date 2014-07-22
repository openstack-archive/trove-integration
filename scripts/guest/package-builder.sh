#!/usr/bin/env bash

set -x

PACKAGE=trove
GIT_URL=http://github.com/openstack/trove.git
GIT_BRANCH=master
GUEST_REQUIREMENTS=~/trove-integration/scripts/guest/guest-requirements.txt

export DEBIAN_FRONTEND=noninteractive

# install dependencies
sudo apt-get -y install python-dev python-pip git-core libxml2-dev libxslt1-dev libmysqlclient-dev
sudo pip install virtualenv

echo "Building $PACKAGE using $GIT_URL"

BUILDDIR=$PACKAGE
echo "cloning ${GIT_URL}"
rm -rf /tmp/$BUILDDIR
mkdir -p /tmp/$BUILDDIR

cd /tmp/$BUILDDIR
git clone ${GIT_URL} $PACKAGE

cd $PACKAGE
git checkout -B guestgent-build ${GIT_BRANCH}
python setup.py build sdist
VERSION=`ls dist | sed -e "s/$PACKAGE-\(.*\).tar.gz/\1/"`
echo "version $VERSION"
mkdir -p $PACKAGE

cd $PACKAGE
VENV="$VERSION"
virtualenv --no-site-packages $VENV

cd $VENV
chmod +x ./bin/activate
. ./bin/activate
pip install -U "pip==1.4.1"
pip install -U distribute
pip install -r $GUEST_REQUIREMENTS
pip install /tmp/$BUILDDIR/$PACKAGE/dist/$PACKAGE-$VERSION.tar.gz

cd ..
deactivate
virtualenv --relocatable $VENV

cd ..
PKG_TAR="$PACKAGE-$VENV.tar.gz"
tar cfz $PKG_TAR $PACKAGE/$VENV

#sudo cp /tmp/$BUILDDIR/$PACKAGE/$PKG_TAR ~


# upload to swift
. ~/devstack/openrc
swift post -r '.r:*' guest-packages
swift upload guest-packages $PKG_TAR