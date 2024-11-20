#!/bin/sh

pynsist --no-makensis win32-installer.cfg
pushd build/nsis
#Make changes here to the generated installer.nsi before running makensis
#Here we set the default to normal program files install as opposed to per-user profile install. We fix the prompts to let the user know what "For all users" and "For just me" means
sed -i 's/!define MULTIUSER_INSTALLMODE_DEFAULT_CURRENTUSER/!define MULTIUSER_INSTALLMODEPAGE_TEXT_ALLUSERS "Install for all users (default, in Program Files)"\n!define MULTIUSER_INSTALLMODEPAGE_TEXT_CURRENTUSER "Install in my user profile folder"/g' installer.nsi
makensis installer.nsi
popd
