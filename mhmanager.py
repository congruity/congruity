#!/usr/bin/python

# Copyright 2012 Scott Talbert
#
# This file is part of congruity.
#
# congruity is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# congruity is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with congruity.  If not, see <http://www.gnu.org/licenses/>.

import logging
import urlparse
import urllib2
import uuid
import re
import time
import os
import sys
from suds.client import Client
from suds.plugin import MessagePlugin

class MHPlugin(MessagePlugin):
    def fix_elements(self, prefix, elements):
        for element in elements:
            # Remove the type="xxx" attribute for non-built-in types.
            if (element.get('type') is not None) and (element.name is not None):
                if element.get('type').find(element.name) != -1:
                    print "PLUGIN: removing {0} from {1}".format(element.get('type'), element.name)
                    element.set('type', '')
            # Set the namespace prefix where it is set on the parent but not
            # on the children.
            if (element.prefix is None) and (prefix is not None):
                element.setPrefix(prefix)
                print "PLUGIN: set prefix for {0}".format(element)
            # Recursively fix the child elements.
            if element.getChildren() is not None:
                self.fix_elements(element.prefix, element.getChildren())
    def marshalled(self, context):
        body = context.envelope.getChild('Body')
        # Make the namespace explicit in the operation tag vice having it
        # predefined, e.g.:
        # xmlns:ns="namespace"; <ns:operation> ==> <operation xmlns="namespace">
        operation = body[0]
        if operation.prefix is not None:
            ns = operation.resolvePrefix(operation.prefix)
            if ns[1] is not None:
                operation.expns = ns[1]
        operation.prefix = None
        self.fix_elements(None, operation.getChildren())


#logging.basicConfig(level=logging.INFO)
#logging.getLogger('suds.client').setLevel(logging.DEBUG)
#logging.getLogger('suds.transport').setLevel(logging.DEBUG)
#logging.getLogger('suds.xsd.schema').setLevel(logging.DEBUG)
#logging.getLogger('suds.wsdl').setLevel(logging.DEBUG)
#logging.getLogger('suds.xsd.query').setLevel(logging.DEBUG)
#logging.getLogger('suds.xsd.sxbasic').setLevel(logging.DEBUG)
#logging.getLogger('suds.mx.literal').setLevel(logging.DEBUG)

class MHManager():
    def __init__(self):
        # Find the harmony.wsdl file.
        appdir = os.path.abspath(os.path.dirname(sys.argv[0]))
        dirs = ['/usr/share/congruity', appdir, '.']
        for dir in dirs:
            fpath = os.path.join(dir, "harmony.wsdl")
            if os.path.isfile(fpath):
                self.wsdl_path = fpath
                break
        
        url = 'file://' + self.wsdl_path
        # TODO: Cache can probably be re-enabled for release version.
        self.client = Client(url, cache=None, plugins=[MHPlugin()])
        self.logged_in = False

    # Log in to web service - Returns True if login succeeded, False otherwise.
    def Login(self, username, password):
        self.logged_in = self.client.service['AuthenticationService'].Login(
            username=username, password=password, customCredential='',
            isPersistent=False)
        return self.logged_in

    # Gets the account info.
    def GetAccount(self):
        self.account = self.client.service['AccountManager'].GetMyAccount()

    # Gets the remote(s) for a given account.
    def GetRemotes(self):
        self.GetAccount()
        remotes = []
        for remote in self.account.Remotes.Remote:
            remotes.append(remote)
        return remotes

    # Gets the product info for a given Skin Id.
    def GetProduct(self, skinId):
        return self.client.service['ProductsManager'].GetProduct(skinId)

    # Get remote config file and write it to the specified filename.
    def GetConfig(self, filename):
        self.GetAccount()
        # TODO: Do we need to support multiple remotes?
        remoteId = self.client.factory.create('ns10:remoteId')
        remoteId.IsPersisted = self.account.Remotes.Remote[0].Id.IsPersisted
        remoteId.Value = self.account.Remotes.Remote[0].Id.Value

        compile = self.client.service['CompileManager'].StartCompileWithLocale(
            remoteId, "Not Implemented")
        url = urlparse.urlparse(compile.DownloadUrl)
        match = re.search('CompilationId=(.+)', compile.DownloadUrl)
        compilationId = match.group(1)
        compilationIdString = '<string xmlns="http://schemas.microsoft.com/2003/10/Serialization/">' + compilationId + '</string>'
        maxAttempts = 2
        count = 0
        while (count < maxAttempts):
            newUrl = "http://" + url.netloc + url.path + "?" + str(uuid.uuid4())
            httpRequest = urllib2.Request(newUrl, compilationIdString,
                                          {"Content-Type": "text/xml"})
            self.client.options.transport.cookiejar.add_cookie_header(
                httpRequest)
            fp = urllib2.urlopen(httpRequest)
            rawfile = fp.read()
            response = rawfile.decode('ascii', 'ignore')
            status = re.search(
                '<RemoteConfiguration status=\'Successful\' length=\'.+\'/>',
                response)
            if status is not None:
                file = rawfile[status.end():]
                outputFile = open(filename, 'wb')
                outputFile.write(file)
                break
            else:
                # Give server time to respond.
                time.sleep(4)
                count += 1

#print account

#print "device zero:"
#print account.Devices.Device[0].Id
#print
#print "device one:"
#print account.Devices.Device[1].Id

#deviceIds = client.factory.create('ns10:deviceIds')
#print deviceIds
#deviceIds.DeviceId.append(account.Devices.Device[0].Id)
#deviceIds.DeviceId.append(account.Devices.Device[1].Id)
#print deviceIds

#devices = client.service['DeviceManager'].GetDevices(deviceIds)
#print devices

#print account.Remotes.Remote[0].Id
