#!/usr/bin/python

# Copyright 2012-2013 Scott Talbert
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
import httplib
import urlparse
import urllib
import urllib2
import uuid
import re
import time
import os
import sys
from HTMLParser import HTMLParser
from suds.client import Client
from suds.plugin import MessagePlugin

XSI_NS = "http://www.w3.org/2001/XMLSchema"
MS_NS = "http://schemas.microsoft.com/2003/10/Serialization/"
DATA_NS = "http://schemas.datacontract.org/2004/07/Logitech.Harmony.Services.Common.Contracts.Data"
OPERATION_NS = "http://schemas.datacontract.org/2004/07/Logitech.Harmony.Services.Common.Contracts.Data.Operation"
DM_OPERATION_NS = "http://schemas.datacontract.org/2004/07/Logitech.Harmony.Services.Manager.DeviceManager.Contracts.Data.Operation"

class MHPlugin(MessagePlugin):
    def fix_elements(self, prefix, elements):
        for element in elements:
            # This is a bit odd, but the MH parser expects type="xxx" attributes
            # only for a few certain types.  Currently type attributes are
            # expected only for xsi:long, guid, and those in the DM_OPERATION_NS
            if (element.get('type') is not None) and (element.name is not None):
                ns = element.resolvePrefix(element.get('type').split(':')[0])
                if (ns[1] != XSI_NS) and (ns[1] != MS_NS) and (ns[1] != DM_OPERATION_NS):
                    #print "PLUGIN: removing {0} from {1}".format(element.get('type'), element.name)
                    element.unset('type')
                elif (ns[1] == XSI_NS):
                    if (element.get('type').split(':')[1] != "long"):
                        element.unset('type')
            # Set the namespace prefix where it is set on the parent but not
            # on the children.
            if (element.prefix is None) and (prefix is not None):
                element.setPrefix(prefix)
                #print "PLUGIN: set prefix for {0}".format(element)
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
    def Login(self, email, password):
        self.logged_in = self.client.service['Security'].LoginUser(
            email=email, password=password, customCredential='',
            isPresistent=False)
        return self.logged_in is not None

    # Gets the household info.
    def GetHousehold(self):
        self.household = self.client.service['AccountManager'].GetMyHousehold()

    # Gets the remote(s) for a given account.
    def GetRemotes(self):
        self.GetHousehold()
        remotes = []
        if self.household.Remotes != "":
            for remote in self.household.Remotes.Remote:
                remotes.append(remote)
        return remotes

    # Gets the product info for a given Skin Id.
    def GetProduct(self, skinId):
        return self.client.service['ProductsManager'].GetProduct(skinId)

    # Get remote config file for the specified remote and write it to the
    # specified filename.
    def GetConfig(self, remote, filename):
        remoteId = self.client.factory.create('{' + DATA_NS + '}remoteId')
        remoteId.IsPersisted = remote.Id.IsPersisted
        remoteId.Value = remote.Id.Value

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

    def GetDevices(self):
        self.GetHousehold()
        deviceIds = self.client.factory.create('{' + DATA_NS + '}deviceIds')
        for device in self.household.Accounts.Account[0].Devices.Device:
            deviceIds.DeviceId.append(device.Id)
        return self.client.service['DeviceManager'].GetDevices(deviceIds).Device

    def DeleteDevice(self, deviceId):
        self.GetHousehold()
        accountId = self.client.factory.create('{' + DATA_NS + '}accountId')
        deviceIds = self.client.factory.create('{' + DATA_NS + '}deviceIds')
        accountId.IsPersisted = self.household.Accounts.Account[0].Id.IsPersisted
        accountId.Value = self.household.Accounts.Account[0].Id.Value
        deviceIds.DeviceId.append(deviceId)
        return self.client.service['DeletionManager'].DeleteDevices(accountId,
                                                                    deviceIds)

    def SearchDevices(self, manufacturer, modelNumber, maxResults):
        return self.client.service['DeviceManager'].SearchGlobalDevices(
            manufacturer, modelNumber, "Unknown", "DidYouMeanMatch", maxResults)

    def AddDevice(self, device):
        self.GetHousehold()
        operation = self.client.factory.create('{' + DM_OPERATION_NS + '}AddDeviceBySearchResultOperation')
        operation.ParentAccount = self.household.Accounts.Account[0].Id
        operation.ReturnIdAsKey = str(uuid.uuid4())
        operation.DeviceClassification = "Any"
        operation.DeviceName = device.Manufacturer + " " + device.DeviceModel
        operation.IsScartCableSupported = "false"
        operation.Match = device
        operation.PrivateAddTypeUsed = "NotApplicable"
        return self.client.service['DeviceManager'].UpdateMyData(operation)

    def RenameDevice(self, deviceId, newName):
        self.GetHousehold()
        operation = self.client.factory.create('{' + DM_OPERATION_NS + '}UpdateDeviceNameOperation')
        id = self.client.factory.create('{' + DATA_NS + '}Id')
        id.IsPersisted = deviceId.IsPersisted
        id.Value = deviceId.Value
        operation.ParentAccount = self.household.Accounts.Account[0].Id
        operation.DeviceId = id
        operation.DeviceName = newName
        return self.client.service['DeviceManager'].UpdateMyData(operation)

    # Returns 'None' on success.  Otherwise returns a string with an error msg.
    # Parameter is an instance of MHAccountDetails.
    def CreateAccount(self, details):
        host = "www.myharmony.com"
        url = "http://www.myharmony.com/MartiniWeb/Account/Register"
        params = urllib.urlencode(
            {'FirstName': details.firstName, 'LastName': details.lastName,
             'ctl00$MainContent$selectCountry': '- Select Country -',
             'region': details.country, 'Emailaddress': details.email,
             'Password': details.password, 'RetypePassword': details.password,
             'securityquestion': details.securityQuestion,
             'Securityanswer': details.securityAnswer,
             'IsPolicyAccepted': 'true',
             'Keepmeinformed': details.keepMeInformed})
        headers = {"Content-type": "application/x-www-form-urlencoded"}
        conn = httplib.HTTPConnection(host)
        conn.request("POST", url, params, headers)
        response = conn.getresponse()
        data = response.read()
        conn.close()
        # We get a redirect response (code 302) on success.  Return.
        if response.status == 302:
            return None
        # Check for field validation errors.
        parser = CreateAccountResponseHTMLParser()
        parser.feed(data)
        if parser.error != "":
            return parser.error
        else:
            return "Unknown Error"

    def GetCountryLists(self):
        conn = httplib.HTTPConnection("www.myharmony.com")
        conn.request("GET", "http://www.myharmony.com/Account/Register")
        response = conn.getresponse()
        data = unicode(response.read(), 'utf-8')
        parser = CountryListHTMLParser()
        parser.feed(parser.unescape(data))
        return [parser.country_codes, parser.countries]

class MHAccountDetails:
    def __init__(self):
        firstName = ""
        lastName = ""
        country = ""
        email = ""
        password = ""
        securityQuestion = ""
        securityAnswer = ""
        keepMeInformed = ""

class CreateAccountResponseHTMLParser(HTMLParser):
    def __init__(self):
        HTMLParser.__init__(self)
        self.save_data = False
        self.error = ""
    def handle_starttag(self, tag, attrs):
        for attr in attrs:
            if attr == ('class', 'field-validation-error'):
                self.save_data = True
    def handle_data(self, data):
        if self.save_data:
            self.error += data
            self.save_data = False

class CountryListHTMLParser(HTMLParser):
    def __init__(self):
        HTMLParser.__init__(self)
        self.in_country_section = False
        self.country_codes = []
        self.countries = []
        self.country_code = None
    def handle_starttag(self, tag, attrs):
        if tag == 'select' and ('id', 'region') in attrs and \
                ('name', 'region') in attrs:
            self.in_country_section = True
            return
        if self.in_country_section:
            if tag == 'option':
                for attr in attrs:
                    if attr[0] == 'value':
                        self.country_code = attr[1]
    def handle_data(self, data):
        if self.country_code is not None:
            self.country_codes.append(self.country_code)
            self.countries.append(data)
            self.country_code = None
    def handle_endtag(self, tag):
        if self.in_country_section and tag == 'select':
            self.in_country_section = False
