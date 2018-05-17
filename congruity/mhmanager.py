# Copyright 2012-2018 Scott Talbert
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

from __future__ import print_function
import logging
import six.moves.http_client as http_client
import six.moves.urllib as urllib
import uuid
import re
import time
import os
import sys
import random
import datetime
import json
from six.moves.html_parser import HTMLParser
from suds.cache import ObjectCache
from suds.client import Client
from suds.plugin import MessagePlugin

try:
    import gi
    gi.require_version("Secret", "1")
    from gi.repository import Secret
except:
    HAVE_SECRET = False
else:
    HAVE_SECRET = True

XSI_NS = "http://www.w3.org/2001/XMLSchema"
MS_NS = "http://schemas.microsoft.com/2003/10/Serialization/"
DATA_NS = "http://schemas.datacontract.org/2004/07/Logitech.Harmony.Services.Common.Contracts.Data"
OPERATION_NS = "http://schemas.datacontract.org/2004/07/Logitech.Harmony.Services.Common.Contracts.Data.Operation"
DM_OPERATION_NS = "http://schemas.datacontract.org/2004/07/Logitech.Harmony.Services.Manager.DeviceManager.Contracts.Data.Operation"
ACCOUNT_NS = "http://schemas.datacontract.org/2004/07/Logitech.Harmony.Services.DataContract.Account"
BUTTON_MAPPING_NS = "http://schemas.datacontract.org/2004/07/Logitech.Harmony.Services.DataContract.ButtonMapping"
ACTIVITY_NS = "http://schemas.datacontract.org/2004/07/Logitech.Harmony.Services.DataContract.Activity"
ARRAYS_NS = "http://schemas.microsoft.com/2003/10/Serialization/Arrays"
USER_FEATURE_NS = "http://schemas.datacontract.org/2004/07/Logitech.Harmony.Services.DataContract.UserFeature"
USER_BUTTON_MAPPING_NS = "http://schemas.datacontract.org/2004/07/Logitech.Harmony.Services.DataContract.UserButtonMapping"

TYPES_FOR_WHICH_TO_INCLUDE_TYPE_ENCODING = [
    (XSI_NS, "long"),
    (MS_NS, "guid"),
    (DATA_NS, "ActivityId"),
    (DATA_NS, "DeviceId"),
    (BUTTON_MAPPING_NS, "HardButton"),
    (BUTTON_MAPPING_NS, "CommandButtonAssignment"),
    (BUTTON_MAPPING_NS, "ChannelButtonAssignment"),
    (OPERATION_NS, "OperationBag"),
    (DM_OPERATION_NS, "Operation"),
    (DM_OPERATION_NS, "AddDeviceBySearchResultOperation"),
    (DM_OPERATION_NS, "UpdateDeviceNameOperation"),
    (DM_OPERATION_NS, "UpdateUserDeviceOperation"),
    (DM_OPERATION_NS, "AddCommandOperation"),
    (DM_OPERATION_NS, "DeleteCommandOperation"),
    (ACTIVITY_NS, "AccessInternetActivityRole"),
    (ACTIVITY_NS, "ChannelChangingActivityRole"),
    (ACTIVITY_NS, "ControlsNetflixActivityRole"),
    (ACTIVITY_NS, "ControlsVideoCallActivityRole"),
    (ACTIVITY_NS, "DisplayActivityRole"),
    (ACTIVITY_NS, "PassThroughActivityRole"),
    (ACTIVITY_NS, "PlayGameActivityRole"),
    (ACTIVITY_NS, "PlayMediaActivityRole"),
    (ACTIVITY_NS, "PlayMovieActivityRole"),
    (ACTIVITY_NS, "RunLogitechGoogleTVActivityRole"),
    (ACTIVITY_NS, "VolumeActivityRole"),
    (USER_FEATURE_NS, "IRDelayAction"),
    (USER_FEATURE_NS, "IRDevAction"),
    (USER_FEATURE_NS, "IRPressAction"),
    (USER_FEATURE_NS, "InputFeature"),
    (USER_FEATURE_NS, "PowerFeature"),
    (USER_FEATURE_NS, "ChannelTuningFeature"),
    (USER_FEATURE_NS, "InternalStateFeature"),
    (USER_BUTTON_MAPPING_NS, "ButtonChannelAction"),
    (USER_BUTTON_MAPPING_NS, "ButtonCommandAction"),
    (USER_BUTTON_MAPPING_NS, "HardRemoteButton"),
    (USER_BUTTON_MAPPING_NS, "SoftRemoteButton"),
    (USER_BUTTON_MAPPING_NS, "ActivityButtonMap"),
    (USER_BUTTON_MAPPING_NS, "DeviceButtonMap"),
]

# This is a mapping between ActivityTypes and a friendly string
ACTIVITY_TYPE_STRINGS = {
    "Custom"        : "Custom",
    "ListenToMusic" : "Listen to Music",
    "MakeVideoCall" : "Make a Video Call",
    "PlayGame"      : "Play a Game",
    "SurfWeb"       : "Surf the Web",
    "WatchDvd"      : "Watch a Movie",
    "WatchNetflix"  : "Watch Netflix",
    "WatchTV"       : "Watch TV",
}

# This is a mapping between Roles and a friendly string
ROLE_STRINGS = {
    "AccessInternetActivityRole"      : "access the Internet",
    "ChannelChangingActivityRole"     : "change channels",
    "ControlsNetflixActivityRole"     : "watch Netflix",
    "ControlsVideoCallActivityRole"   : "make a video call",
    "PlayGameActivityRole"            : "play video games",
    "PlayMediaActivityRole"           : "play music",
    "PlayMovieActivityRole"           : "watch a movie",
    "RunLogitechGoogleTVActivityRole" : "watch Google TV",
    "VolumeActivityRole"              : "control volume",
}

class MHPlugin(MessagePlugin):
    def fix_elements(self, prefix, elements):
        for element in elements:
            # This is a bit odd, but the MH parser expects type="xxx" attributes
            # only for a few certain types.
            if (element.get('type') is not None) and (element.name is not None):
                ns = element.resolvePrefix(element.get('type').split(':')[0])[1]
                type = element.get('type').split(':')[1]
                if (ns, type) not in TYPES_FOR_WHICH_TO_INCLUDE_TYPE_ENCODING:
                    element.unset('type')
            # Set the namespace prefix where it is set on the parent but not
            # on the children.
            if (element.prefix is None) and (prefix is not None):
                element.setPrefix(prefix)
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

class MHManager():
    def __init__(self, use_local_wsdl=False, suds_debug=False):
        if use_local_wsdl:
            wsdl = os.path.join(os.path.dirname(__file__), 'harmony.wsdl')
            url = 'file://' + wsdl
            cache = None
        else:
            url = 'http://congruity.sourceforge.net/congruity/harmony.wsdl'
            cache = ObjectCache(hours=4)
        if suds_debug:
            logging.basicConfig(level=logging.INFO)
            logging.getLogger('suds.transport').setLevel(logging.DEBUG)
        self.client = Client(url, cache=cache, plugins=[MHPlugin()])

    # Log in to web service - returns True if login succeeded, False if login
    # failed, and None if the account appears to be a members.harmonyremote.com
    # account.
    def Login(self, email, password):
        baseUrl = "https://setup.myharmony.com"
        url = baseUrl + "/MartiniWeb/Account/TestLoginAndMW?provider=hp&&verify=true&toucheck=true"
        data = json.dumps({'email': email, 'password': password}).encode('utf-8')
        headers = {'Content-Type': 'application/json'}
        request = urllib.request.Request(url, data, headers)
        response = urllib.request.urlopen(request)
        # For some reason the response to this is double-encoded
        jsonResponse = json.loads(json.loads(response.read().decode('utf-8')))
        if "mwResult" in jsonResponse:
            if jsonResponse["mwResult"]: # members.harmonyremote.com acct
                return None
            else:
                return False

        url = baseUrl + "/MartiniWeb/Home/Login?i=" + jsonResponse["id_token"]
        url += "&a=" + jsonResponse["access_token"] + "&cl=en-US"
        request = urllib.request.Request(url)
        response = urllib.request.urlopen(request)
        parser = LoginResponseHTMLParser()
        parser.feed(response.read().decode('utf-8'))
        initparams = dict(u.split("=", 1) for u in parser.initparams.split(","))
        self.contentServiceAuthKey = initparams['ContentServiceAuthKey']

        url = "https://svcs.myharmony.com/CompositeSecurityServices/Security.svc/json2/signin"
        data = json.dumps({'id_token': jsonResponse['id_token'],
                           'access_token': jsonResponse['access_token']}).encode('utf-8')
        headers = {'Content-Type': 'application/json'}
        request = urllib.request.Request(url, data, headers)
        response = urllib.request.urlopen(request)
        jsonResponse = json.loads(response.read().decode('utf-8'))
        self.client.options.transport.cookiejar.extract_cookies(response,
                                                                request)

        self.email = email
        self.password = password
        return True

    # Gets the household info.
    def GetHousehold(self):
        self.household = self.client.service['AccountManager'].GetMyHousehold()

    # Gets the remote(s) for a given account.
    def GetRemotes(self):
        self.GetHousehold()
        remotes = []
        try:
            for account in self.household.Accounts.Account:
                if account.Remotes != "":
                    for remote in account.Remotes.Remote:
                        remotes.append(remote)
        except AttributeError:
            pass
        return remotes

    def GetRemoteForAccountId(self, accountId):
        foundAccount = None
        for account in self.household.Accounts.Account:
            if account.Id.Value == accountId.Value:
                foundAccount = account
        try:
            return foundAccount.Remotes.Remote[0]
        except:
            return None

    # Gets the product info for a given Skin Id.
    def GetProduct(self, skinId):
        return self.client.service['ProductsManager'].GetProduct(skinId)

    def GetProductButtonList(self, skinId):
        return self.client.service['ProductsManager'].GetProductButtonList(skinId).Buttons.ButtonDefinition

    def GetRemoteCanvas(self, skinId):
        return self.client.service['UserButtonMappingManager']. \
            GetRemoteCanvas(skinId).AbstractRemoteButton

    def GetCapabilityNames(self, product):
        capabilityNames = []
        for capability in product.SupportedCapabilities.ProductCapability:
            capabilityNames.append(capability.Name)
        return capabilityNames

    def GetCommands(self, deviceId):
        deviceIds = self.client.factory.create('{' + DATA_NS + '}deviceIds')
        deviceIds.DeviceId.append(deviceId)
        result = self.client.service['DeviceManager'].GetCommands(deviceIds)
        if result is not None:
            return result[0].Value[0]
        else:
            return None

    def GetButtonMap(self, deviceId):
        deviceIds = self.client.factory.create('{' + DATA_NS + '}deviceIds')
        deviceIds.DeviceId.append(deviceId)
        result = self.client.service['UserButtonMappingManager'] \
            .GetDeviceModeButtonMaps(deviceIds)
        if result is not None:
            return result[0].Value
        else:
            return None

    def UpdateButtonMap(self, existingButtonMap, button, command,
                        isChannelButton = False):
        buttonMaps = self.client.factory.create('{' + BUTTON_MAPPING_NS
                                                + '}buttonMaps')
        buttonMap = self.client.factory.create('{' + BUTTON_MAPPING_NS
                                               + '}ButtonMap')
        # Have to do this because existingButtonMap doesn't have the correct
        # namespaces.  Same with the others below.
        buttonMap.ButtonMapId.IsPersisted = \
            existingButtonMap.ButtonMapId.IsPersisted
        buttonMap.ButtonMapId.Value = existingButtonMap.ButtonMapId.Value
        buttonMap.ButtonMapType = existingButtonMap.ButtonMapType
        newButton = self.client.factory.create('{' + BUTTON_MAPPING_NS
                                               + '}HardButton')
        if isChannelButton is False:
            newButton.ButtonAssignment = self.client.factory.create(
                '{' + BUTTON_MAPPING_NS + '}CommandButtonAssignment')
            newButton.ButtonAssignment.CommandId.IsPersisted = \
                command.Id.IsPersisted
            newButton.ButtonAssignment.CommandId.Value = command.Id.Value
            newButton.ButtonAssignment.OverriddenDeviceId = None
            newButton.ButtonAssignment.OverriddenButtonMapType = "NoSetting"
        else:
            newButton.ButtonAssignment = self.client.factory.create(
                '{' + BUTTON_MAPPING_NS + '}ChannelButtonAssignment')
            newButton.ButtonAssignment.Channel = command
            newButton.ButtonAssignment.DeviceId.IsPersisted = \
                existingButtonMap.PrimaryDeviceReferenceId.IsPersisted
            newButton.ButtonAssignment.DeviceId.Value = \
                existingButtonMap.PrimaryDeviceReferenceId.Value
        newButton.ButtonKey = button.ButtonKey
        buttonMap.Buttons.AbstractButton = newButton
        buttonMap.PrimaryDeviceReferenceId.IsPersisted = \
            existingButtonMap.PrimaryDeviceReferenceId.IsPersisted
        buttonMap.PrimaryDeviceReferenceId.Value = \
            existingButtonMap.PrimaryDeviceReferenceId.Value
        buttonMap.SurfaceId = "0"
        buttonMaps.ButtonMap = buttonMap
        self.client.service['UserButtonMappingManager'] \
            .UpdateDeviceModeButtonMaps(buttonMaps)

    def GetUserButtonMap(self, deviceId):
        DeviceId = self.client.factory.create('{' + DATA_NS + '}DeviceId')
        DeviceId.IsPersisted = deviceId.IsPersisted
        DeviceId.Value = deviceId.Value
        deviceIds = self.client.factory.create('{' + DATA_NS + '}abstractIds')
        deviceIds.AbstractId.append(DeviceId)
        accountId = self.GetAccountIdForDevice(deviceId)
        remote = self.GetRemoteForAccountId(accountId)
        surfaceId = remote.Surfaces.Surface[0].Id.Value
        return self.client.service['UserButtonMappingManager'] \
            .GetButtonMaps(deviceIds, "", remote.SkinId, accountId,
                           surfaceId).AbstractButtonMap[0]

    def UpdateUserButtonMap(self, userButtonMap, button, command):
        accountId = self.GetAccountIdForDevice(userButtonMap.DeviceId)
        remote = self.GetRemoteForAccountId(accountId)
        surfaceId = remote.Surfaces.Surface[0].Id
        userButtonMap.ButtonMapSurfaceId = surfaceId
        userButtonMap.SurfaceId = surfaceId

        # Check to see if there is an existing entry for this button
        bmIndex = -1
        for i in range(len(userButtonMap.Buttons.AbstractRemoteButton)):
            try:
                if userButtonMap.Buttons.AbstractRemoteButton[i].ButtonKey == \
                   button.ButtonKey:
                    bmIndex = i
                    break
            except AttributeError:
                pass
        if bmIndex != -1:
            bmEntry = userButtonMap.Buttons.AbstractRemoteButton[i]
        else:
            bmEntry = self.client.factory.create('{' + USER_BUTTON_MAPPING_NS
                                                + '}HardRemoteButton')
            bmEntry.ButtonAction = self.client.factory.create('{' +
                                                USER_BUTTON_MAPPING_NS
                                                + '}ButtonCommandAction')
        bmEntry.ButtonAction.EventType = 0
        bmEntry.ButtonAction.Id = 0
        bmEntry.ButtonAction.Order = 0
        bmEntry.ButtonAction.CommandName = command.Name
        bmEntry.ButtonAction.DeviceId = userButtonMap.DeviceId
        bmEntry.ButtonAction.FunctionId = command.FunctionId
        bmEntry.ButtonDoublePressAction = None
        bmEntry.ButtonId = 0
        bmEntry.ButtonLongPressAction = None
        bmEntry.ButtonState = button.ButtonState
        bmEntry.FunctionGroupType = button.FunctionGroupType
        bmEntry.ButtonKey = button.ButtonKey

        if bmIndex != -1:
            userButtonMap.Buttons.AbstractRemoteButton[bmIndex] = bmEntry
        else:
            userButtonMap.Buttons.AbstractRemoteButton.append(bmEntry)
        buttonMaps = self.client.factory.create('{' + USER_BUTTON_MAPPING_NS
                                                + '}ButtonMaps')
        buttonMaps.AbstractButtonMap = userButtonMap
        self.client.service['UserButtonMappingManager'] \
            .SaveButtonMaps(buttonMaps)

    # Get remote config file for the specified remote and write it to the
    # specified filename.
    def GetConfig(self, remote, filename):
        remoteId = self.client.factory.create('{' + DATA_NS + '}Id')
        remoteId.IsPersisted = remote.Id.IsPersisted
        remoteId.Value = remote.Id.Value

        compile = self.client.service['CompileManager'].StartCompileWithLocale(
            remoteId, "Not Implemented")
        url = urllib.parse.urlparse(compile.DownloadUrl)
        match = re.search('CompilationId=(.+)', compile.DownloadUrl)
        compilationId = match.group(1)
        compilationIdString = ('<string xmlns="http://schemas.microsoft.com/2003/10/Serialization/">' + compilationId + '</string>').encode('utf-8')
        maxAttempts = 15
        count = 0
        while (count < maxAttempts):
            newUrl = "http://" + url.netloc + url.path + "?" + str(uuid.uuid4())
            httpRequest = urllib.request.Request(newUrl, compilationIdString,
                                                 {"Content-Type": "text/xml"})
            self.client.options.transport.cookiejar.add_cookie_header(
                httpRequest)
            fp = urllib.request.urlopen(httpRequest)
            rawfile = fp.read()
            response = rawfile.decode('ascii', 'ignore')
            status = re.search(
                '<RemoteConfiguration status=\'Successful\' length=\'.+\'/>',
                response)
            if status is not None:
                file = rawfile[status.end():]
                outputFile = open(filename, 'wb')
                outputFile.write(file)
                outputFile.close()
                break
            else:
                # Give server time to respond.
                time.sleep(4)
                count += 1
        if count == maxAttempts:
            raise Exception("Failed to download config file")

    def GetAccountForRemote(self, remoteId):
        for account in self.household.Accounts.Account:
            if account.Remotes != "":
                for remote in account.Remotes.Remote:
                    if (remote.Id.IsPersisted == remoteId.IsPersisted) and \
                            (remote.Id.Value == remoteId.Value):
                        return account
        return None

    def GetAccountIdForDevice(self, deviceId):
        for account in self.household.Accounts.Account:
            if account.Devices != "":
                for device in account.Devices.Device:
                    if (device.Id.IsPersisted == deviceId.IsPersisted) and \
                            (device.Id.Value == deviceId.Value):
                        return account.Id
        return None

    def GetDevice(self, deviceId):
        return self.client.service['DeviceManager'].GetDevice(deviceId)

    def GetDevices(self, remoteId):
        self.GetHousehold()
        account = self.GetAccountForRemote(remoteId)
        if account.Devices != "":
            deviceIds = self.client.factory.create('{' + DATA_NS + '}deviceIds')
            for device in account.Devices.Device:
                deviceIds.DeviceId.append(device.Id)
            return self.client.service['DeviceManager'].GetDevices(
                deviceIds).Device
        else:
            return None

    def DeleteDevice(self, deviceId):
        self.GetHousehold()
        accountId = self.GetAccountIdForDevice(deviceId)
        deviceIds = self.client.factory.create('{' + DATA_NS + '}deviceIds')
        deviceIds.DeviceId.append(deviceId)
        return self.client.service['DeletionManager'].DeleteDevices(accountId,
                                                                    deviceIds)

    def SearchDevices(self, manufacturer, modelNumber, maxResults):
        return self.client.service['DeviceManager'].SearchGlobalDevices(
            manufacturer, modelNumber, "Unknown", "DidYouMeanMatch", maxResults)

    def AddDevice(self, device, remoteId):
        self.GetHousehold()
        operation = self.client.factory.create(
            '{' + DM_OPERATION_NS + '}AddDeviceBySearchResultOperation'
        )
        operation.ParentAccount = self.GetAccountForRemote(remoteId).Id
        operation.ReturnIdAsKey = str(uuid.uuid4())
        operation.DeviceClassification = "Any"
        operation.DeviceName = device.Manufacturer + " " + device.DeviceModel
        operation.IsScartCableSupported = "false"
        operation.Match = device
        operation.PrivateAddTypeUsed = "NotApplicable"
        return self.client.service['DeviceManager'].UpdateMyData(operation)

    def RenameDevice(self, deviceId, newName):
        self.GetHousehold()
        operation = self.client.factory.create(
            '{' + DM_OPERATION_NS + '}UpdateDeviceNameOperation'
        )
        id = self.client.factory.create('{' + DATA_NS + '}Id')
        id.IsPersisted = deviceId.IsPersisted
        id.Value = deviceId.Value
        operation.ParentAccount = self.GetAccountIdForDevice(deviceId)
        operation.DeviceId = id
        operation.DeviceName = newName
        return self.client.service['DeviceManager'].UpdateMyData(operation)

    def UpdateDevice(self, device, remoteId):
        operation = self.client.factory.create(
            '{' + DM_OPERATION_NS + '}UpdateUserDeviceOperation'
        )
        operation.ParentAccount = self.GetAccountForRemote(remoteId).Id
        operation.Device = device
        return self.client.service['DeviceManager'].UpdateMyData(operation)

    # Returns 'None' on success.  Otherwise returns a string with an error msg.
    # Parameter is an instance of MHAccountDetails.
    def CreateAccount(self, details):
        host = "setup.myharmony.com"
        url = "https://setup.myharmony.com/MartiniWeb/Account/Register"
        params = urllib.parse.urlencode(
            {'FirstName': details.firstName, 'LastName': details.lastName,
             'ctl00$MainContent$selectCountry': '- Select Country -',
             'region': details.country, 'Emailaddress': details.email,
             'Password': details.password, 'RetypePassword': details.password,
             'IsPolicyAccepted': 'true',
             'Keepmeinformed': details.keepMeInformed})
        headers = {"Content-type": "application/x-www-form-urlencoded"}
        conn = http_client.HTTPSConnection(host)
        conn.request("POST", url, params, headers)
        response = conn.getresponse()
        data = response.read().decode('utf-8')
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

    # Returns an instance of MHAccountDetails with the existing account's
    # details filled in.
    def GetAccountDetails(self):
        details = MHAccountDetails()
        self.GetHousehold()
        properties = self.household.Accounts.Account[0].Properties
        details.firstName = properties.FirstName
        details.lastName = properties.LastName
        details.country = properties.CountryType
        details.email = properties.Email
        details.password = self.password
        details.keepMeInformed = properties.ContactMe
        return details

    # Updates an account with the provided details, which should be an instance
    # of MHAccountDetails.
    def UpdateAccountDetails(self, details):
        randGen = random.SystemRandom()
        nonce = randGen.randint(100000000,2000000000)
        handshakeResult = self.client.service['AccountManager']. \
            SecureControllerHandshake(nonce)
        if handshakeResult is None:
            print("SecureControllerHandshake failed.")
            return False

        properties = self.client.factory.create('{' + ACCOUNT_NS
                                                + '}Properties')
        properties.ContactMe = details.keepMeInformed
        properties.CountryType = details.country
        properties.Email = details.email
        properties.FirstName = details.firstName
        properties.IsPolicyAccepted = "true"
        properties.LastName = details.lastName
        properties.UserKey = \
            self.household.Accounts.Account[0].Properties.UserKey
        result = self.client.service['AccountManager']. \
            UpdateMyAccountProperties(properties)
        if result is not None:
            print("UpdateMyAccountProperties failed: " + str(result))
            return False

        if details.password != self.password:
            result = self.client.service['AccountManager']. \
                UpdatePasswordByOldPassword(details.email, self.password,
                                            details.password)
            if result != "true":
                print("UpdatePasswordByOldPassword failed: " + str(result))
                return False
            self.password = details.password

        return True

    def GetCountryLists(self):
        conn = http_client.HTTPSConnection("setup.myharmony.com")
        conn.request("GET",
                     "https://setup.myharmony.com/MartiniWeb/Account/Register")
        response = conn.getresponse()
        data = response.read().decode('utf-8')
        parser = CountryListHTMLParser()
        parser.feed(parser.unescape(data))
        return [parser.country_codes, parser.countries]

    def AddRemote(self, serialNumber, skinId, usbPid, usbVid):
        self.GetHousehold()
        accountId = None
        for account in self.household.Accounts.Account:
            if account.Remotes is None or account.Remotes == "":
                accountId = account.Id
                break
        if accountId is None:
            result = self.client.service['AccountManager']. \
                CreateNewAccountInMyHousehold()
            accountId = result.Id

        remoteInfo = self.client.factory.create(
            '{' + ACCOUNT_NS + '}remoteInfo')
        remoteInfo.AccountId = accountId
        remoteInfo.KeyPadLayout = "Undefined"
        remoteInfo.SerialNumber = serialNumber
        remoteInfo.SkinId = skinId
        remoteInfo.UsbPid = usbPid
        remoteInfo.UsbVid = usbVid
        return self.client.service['UserAccountDirector'].AddRemoteToAccount(
            remoteInfo)

    # Removes a remote from an account.
    def DeleteRemote(self, remoteId):
        account = self.GetAccountForRemote(remoteId)
        self.client.service['AccountManager'].RemoveAccountFromHousehold(
            account.Id)

    # Returns a set of the remote skins supported by this web interface.
    def GetSupportedRemoteSkinIds(self):
        products = self.client.service['ProductsManager'].GetHarmonyProducts()
        skinIds = set()
        for product in products.HarmonyProduct:
            skinIds.add(int(product.SkinId))
        return skinIds

    # Returns a list of the remote names supported by this web interface.
    def GetSupportedRemoteNames(self):
        products = self.client.service['ProductsManager'].GetHarmonyProducts()
        remoteNames = set()
        for product in products.HarmonyProduct:
            remoteNames.add(product.DisplayName)
        remoteNames = list(remoteNames)
        remoteNames.sort()
        return remoteNames

    def GetGlobalRemote(self, serialNumber):
        return self.client.service['RemoteManager'].GetGlobalRemote(
            serialNumber)

    # Gets the "Remote Name" for a given remoteId - used mainly for Harmony
    # Link to identity the room.
    def GetRemoteName(self, remoteId):
        remotes = self.GetRemotes()
        for remote in remotes:
            if remote.Id.Value == remoteId.Value:
                return remote.RemoteProperties.RemoteName
        return None

    # Sets the "Remote Name" - used for Harmony Link to identify the room where
    # the link is located
    def SetRemoteName(self, remoteId, remoteName):
        remoteProperties = self.client.factory.create('{' + ACCOUNT_NS
                                                      + '}RemoteProperties')
        remoteProperties.IsActiveRemote = True
        remoteProperties.IsLocked = False
        remoteProperties.RemoteName = remoteName
        result = self.client.service['RemoteManager'].SaveRemoteProperties(
            remoteId, remoteProperties)
        if result == "Successful":
            return True
        else:
            return False

    # Returns the recommended activities for a given remoteId.
    def GetRecommendedActivities(self, remoteId):
        account = self.GetAccountForRemote(remoteId)
        devices = self.GetDevices(remoteId)
        devicesWithCapabilities = \
            self.client.factory.create('{' + ACTIVITY_NS
                                       + '}DevicesWithCapabilities')
        for device in devices:
            deviceWithCapabilities = \
                self.client.factory.create('{' + ACTIVITY_NS +
                                           '}DeviceWithCapabilities')
            deviceWithCapabilities.DeviceId = device.Id
            deviceWithCapabilities.DeviceType = "Unknown"
            deviceWithCapabilities.PrioritizedCapabilities = \
                device.DeviceCapabilitiesWithPriority
            devicesWithCapabilities.DeviceWithCapabilities.append(
                deviceWithCapabilities)
        return self.client.service['ActivityManager'].\
            GetRecommendedActivitiesFromDevices(account.Id,
                                                devicesWithCapabilities)[0]

    def GetActivityTypeString(self, activityType):
        try:
            return ACTIVITY_TYPE_STRINGS[activityType]
        except:
            return activityType

    def GetRoleString(self, role):
        try:
            return ROLE_STRINGS[role]
        except:
            return role

    def GetActivityTypesAndRoles(self, accountId):
        print(self.client.service['ActivityManager'].\
            GetActivityTypesAndRoles(accountId))

    def GetActivityRolesAndDevices(self, remoteId, activityType):
        account = self.GetAccountForRemote(remoteId)
        activityTypes = \
            self.client.factory.create('{' + ACTIVITY_NS + '}ActivityTypes')
        activityTypes.ActivityType.append(activityType)
        devices = self.GetDevices(remoteId)
        devicesWithCapabilities = \
            self.client.factory.create('{' + ACTIVITY_NS
                                       + '}DevicesWithCapabilities')
        for device in devices:
            deviceWithCapabilities = \
                self.client.factory.create('{' + ACTIVITY_NS +
                                           '}DeviceWithCapabilities')
            deviceWithCapabilities.DeviceId = device.Id
            deviceWithCapabilities.DeviceType = "Unknown"
            deviceWithCapabilities.PrioritizedCapabilities = \
                device.DeviceCapabilitiesWithPriority
            devicesWithCapabilities.DeviceWithCapabilities.append(
                deviceWithCapabilities)        
        return (self.client.service['ActivityManager'].GetActivityRoles(
            account.Id, activityTypes, devicesWithCapabilities).\
                KeyValueOfActivityTypeRoleToDeviceMapping_SFvkcgrh[0].Value.\
                Mapping.KeyValueOfAbstractActivityRoleArrayOfDeviceIdGQ_S527jd,
                devices)

    def GetActivityTemplate(self, remoteId, activityType):
        roles, devices = self.GetActivityRolesAndDevices(remoteId, activityType)
        activityTemplate = ActivityTemplate()
        deviceNames = {}
        activityTemplate.devices = []
        activityTemplate.devicesWithInputs = []
        activityTemplate.roles = []
        for device in devices:
            deviceNames[device.Id.Value] = device.Name
            activityTemplate.devices.append((device.Name, device.Id))
            inputNames = self.GetDeviceInputNames(device.Id)
            if inputNames:
                activityTemplate.devicesWithInputs.append(
                    (device.Name, device.Id, inputNames))
        for role in roles:
            roleType = role.Key.__class__.__name__
            roleDevices = []
            try:
                for deviceId in role.Value.DeviceId:
                    roleDevices.append((deviceNames[deviceId.Value], deviceId))
            except AttributeError:
                pass
            activityTemplate.roles.append((roleType, roleDevices))
        return activityTemplate

    # Returns the configured activities (if any) for a given remoteId
    def GetActivities(self, remoteId):
        accountId = self.GetAccountForRemote(remoteId).Id
        result = self.client.service['UserAccountDirector'].SimpleGetActivities(
            accountId)
        if result:
            return result.Activity
        return None

    # Returns the activity with the supplied name if it exists, None otherwise
    def GetActivity(self, remoteId, activityName):
        activities = self.GetActivities(remoteId)
        if activities is not None:
            for activity in activities:
                if activity.Name == activityName:
                    return activity
        return None

    # Returns the special WatchTV activity for 200/300
    def GetWatchTVActivity(self, remoteId):
        account = self.GetAccountForRemote(remoteId)
        return self.GetActivity(remoteId, "WatchTV")

    # Creates a 'Roles' structure and returns it
    # deviceInfo is a list of (deviceId, selectedInputName)
    def CreateRoles(self, deviceInfo):
        roles = self.client.factory.create('{' + ACTIVITY_NS + '}Roles')
        deviceNum = 1
        for device in deviceInfo:
            deviceId, inputName = device
            role = self.client.factory.create(
                '{' + ACTIVITY_NS + '}PassThroughActivityRole')
            role.DeviceId = deviceId
            role.Id = None
            role.PowerOffOrder = deviceNum
            role.PowerOnOrder = deviceNum
            if inputName:
                role.SelectedInput = self.client.factory.create(
                    '{' + ACTIVITY_NS + '}SelectedInput')
                role.SelectedInput.Id = None
                role.SelectedInput.Name = inputName
            else:
                role.SelectedInput = None
            roles.AbstractActivityRole.append(role)
            deviceNum = deviceNum + 1
        return roles

    def CreateRolesByTemplate(self, saveActivityTemplate):
        roles = self.client.factory.create('{' + ACTIVITY_NS + '}Roles')
        for roleType, deviceId, inputName in saveActivityTemplate.roles:
            role = self.client.factory.create('{' + ACTIVITY_NS + '}' +
                                              roleType)
            role.DeviceId = deviceId
            role.Id = None
            if inputName or inputName == '':
                role.SelectedInput.Id = None
                role.SelectedInput.Name = inputName
            else:
                role.SelectedInput = None
            roles.AbstractActivityRole.append(role)
        return roles

    # Creates a WatchTV activity for 200/300 remotes
    # deviceInfo is a list of (deviceId, selectedInputName)
    def SaveWatchTVActivity(self, remoteId, deviceInfo, activity=None):
        account = self.GetAccountForRemote(remoteId)
        if not activity:
            activity = self.client.factory.create(
                '{' + ACTIVITY_NS + '}Activity')
            activity.AccountId = account.Id
            activity.ActivityGroup = "VirtualGeneric"
            activity.ActivityOrder = "0"
            activity.DateCreated = datetime.datetime.min
            activity.DateModified = datetime.datetime.min
            activity.Id = None
            activity.IsDefault = False
            activity.IsMultiZone = False
            activity.IsTuningDefault = False
            activity.Name = "WatchTV"
            activity.State = "Setup"
            activity.Type = "WatchTV"
        activity.Roles = self.CreateRoles(deviceInfo)
        return self.SaveActivity(remoteId, activity)

    def SaveActivityByTemplate(self, remoteId, saveActivityTemplate, activity):
        accountId = self.GetAccountForRemote(remoteId).Id
        if not activity:
            activity = self.client.factory.create(
                '{' + ACTIVITY_NS + '}Activity')
            activity.AccountId = accountId
            activity.ActivityGroup = "VirtualGeneric"
            activity.ActivityOrder = "0"
            activity.DateCreated = datetime.datetime.min
            activity.DateModified = datetime.datetime.min
            activity.Id = None
            activity.IsDefault = False
            activity.IsMultiZone = False
            activity.IsTuningDefault = False
            activity.State = "Setup"
            activity.Type = saveActivityTemplate.activityType
        activity.Name = saveActivityTemplate.activityName
        activity.Roles = self.CreateRolesByTemplate(saveActivityTemplate)
        return self.SaveActivity(remoteId, activity)        

    # Saves the specified activity
    def SaveActivity(self, remoteId, activity):
        accountId = self.GetAccountForRemote(remoteId).Id
        activities = self.client.factory.create('{' + ACTIVITY_NS
                                                + '}Activities')
        activities.Activity.append(activity)
        return self.client.service['ActivityManager'].SaveActivities(
            accountId, activities)

    # Deletes the specified activity
    def DeleteActivity(self, activity):
        activityIds = self.client.factory.create('{' + DATA_NS + '}activityIds')
        activityIds.ActivityId.append(activity.Id)
        return self.client.service['ActivityManager'].DeleteActivities(
            activity.AccountId, activityIds)

    def GetRoleDeviceId(self, activity, roleType):
        for role in activity.Roles.AbstractActivityRole:
            if role.__class__.__name__ == roleType:
                return role.DeviceId
        return None

    def GetDeviceInput(self, activity, deviceId):
        for role in activity.Roles.AbstractActivityRole:
            if role.DeviceId.Value == deviceId.Value:
                return role.SelectedInput.Name
        return None

    def GetDeviceInputNames(self, deviceId):
        features = self.GetUserFeatures(deviceId)
        if features:
            for feature in features.DeviceFeature:
                try:
                    if feature.InputType == "Discrete" or \
                       feature.InputType == "MultiMethod":
                        inputNames = []
                        for input in feature.Inputs.Input:
                            inputNames.append(input.InputName)
                        return inputNames
                except:
                    continue
        return None

    def GetUserFeatures(self, deviceId):
        deviceIds = self.client.factory.create('{' + DATA_NS + '}deviceIds')
        deviceIds.DeviceId.append(deviceId)
        result = self.client.service['UserFeatureManager'].GetUserFeatures(
            deviceIds)
        if result:
            return result.KeyValueOfDeviceIdArrayOfDeviceFeatureeiEyJu8p[0].\
                Value
        return None

    def SaveUserFeatures(self, userFeatures):
        return self.client.service['UserFeatureManager'].SaveUserFeatures(
            userFeatures)

    def GetPowerFeature(self, deviceId):
        features = self.GetUserFeatures(deviceId)
        if features:
            for feature in features.DeviceFeature:
                if feature.__class__.__name__ == "PowerFeature":
                    return feature
        return None

    # This returns an array of tuples of (IRPressAction/IRDelayAction, Command,
    # Duration) for the given Power Feature Type (ie, pass in
    # powerFeature.PowerToggleActions)
    def GetPowerFeatureActions(self, powerFeatureType):
        if powerFeatureType and powerFeatureType.AbstractIRAction:
            actions = []
            for action in powerFeatureType.AbstractIRAction:
                if action.__class__.__name__ == "IRPressAction":
                    if action.Duration is None:
                        duration = "0"
                    else:
                        duration = action.Duration
                    actions.append(("IRPressAction", action.IRCommandName, 
                                    duration))
                elif action.__class__.__name__ == "IRDelayAction":
                    actions.append(("IRDelayAction", None, action.Delay))
            return actions
        else:
            return None

    # powerFeatureActions is an array of (IRPressAction/IRDelayAction, Command,
    # Duration); actionType is "PowerToggle", "PowerOn", etc.
    def SavePowerFeature(self, powerFeature, powerFeatureActions, actionType):
        ufActions = self.client.factory.create('{' + USER_FEATURE_NS +
                                             '}Actions')
        actionNum = 1
        for pfAction in powerFeatureActions:
            ufAction = None
            if pfAction[0] == "IRPressAction":
                ufAction = self.client.factory.create('{' + USER_FEATURE_NS +
                                                      '}IRPressAction')
                ufAction.ActionId = 0
                ufAction.Order = actionNum
                ufAction.Duration = pfAction[2]
                ufAction.IRCommandName = pfAction[1]
            elif pfAction[0] == "IRDelayAction":
                ufAction = self.client.factory.create('{' + USER_FEATURE_NS +
                                                      '}IRDelayAction')
                ufAction.ActionId = 3
                ufAction.Order = actionNum
                ufAction.Delay = pfAction[2]
            if ufAction is not None:
                ufActions.AbstractIRAction.append(ufAction)
                actionNum += 1

        if actionType == "PowerToggle":
            powerFeature.PowerToggleActions = ufActions
        elif actionType == "PowerOn":
            powerFeature.PowerOnActions = ufActions
        deviceFeatures = self.client.factory.create('{' + USER_FEATURE_NS
                                                    + '}DeviceFeatures')
        deviceFeatures.DeviceFeature.append(powerFeature)
        return self.client.service['UserFeatureManager'].SaveUserFeatures(
            deviceFeatures)

    # Adds a learned IR command (if the command name does not already exist) or
    # updates the IR command for the specified command name and device.
    def UpdateIRCommand(self, commandName, rawSequence, deviceId):
        result = self.client.service['InfraredAnalysisManager'].AnalyzeInfrared(
            None, rawSequence)
        try:
            result.KeyCode
        except:
            return "AnalyzeInfrared failed:" + str(result)

        operation = self.client.factory.create('{' + OPERATION_NS
                                               + '}OperationBag')
        operation.ParentAccount = self.GetAccountIdForDevice(deviceId)
        operation.Items.Operation = self.client.factory.create(
            '{' + DM_OPERATION_NS + '}AddCommandOperation'
        )
        operation.Items.Operation.ParentAccount = operation.ParentAccount
        operation.Items.Operation.DeviceId = deviceId
        operation.Items.Operation.KeyCode = result.KeyCode
        operation.Items.Operation.Name = commandName
        operation.Items.Operation.RawInfrared = rawSequence
        result = self.client.service['DeviceManager'].UpdateMultiple(operation)
        if result is None:
            return "UpdateMultiple failed"
        return None

    # Deletes an IR command (if it is a user-added one) or removes the override
    # if the command is an officially provided one.
    def DeleteIRCommand(self, commandId, deviceId):
        deviceIds = self.client.factory.create('{' + DATA_NS + '}deviceIds')
        deviceIds.DeviceId.append(deviceId)
        taughtCommandIds = self.client.factory.create('{' + ARRAYS_NS
                                                      + '}taughtCommandIds')
        taughtCommandIds.long = commandId.Value
        result = self.client.service['UserButtonMappingManager']. \
            DeleteTaughtDeviceModeCommandButtonMaps(deviceIds, taughtCommandIds)
        if result is not None:
            return "DeleteTaughtDeviceModeCommandButtonMaps:" + str(result)

        operation = self.client.factory.create('{' + OPERATION_NS
                                               + '}OperationBag')
        operation.ParentAccount = self.GetAccountIdForDevice(deviceId)
        operation.Items.Operation = self.client.factory.create(
            '{' + DM_OPERATION_NS + '}DeleteCommandOperation'
        )
        operation.Items.Operation.ParentAccount = operation.ParentAccount
        operation.Items.Operation.DeviceId = deviceId
        operation.Items.Operation.LanguageElementIds.long = commandId.Value
        result = self.client.service['DeviceManager'].UpdateMultiple(operation)
        if result is None:
            return "UpdateMultiple failed"
        return None

class ActivityTemplate:
    def __init__(self):
        self.devices = None # List of (Device Name, DeviceId)
        self.roles = None # List of (Role Name, [(Device Name, DeviceId), .. ]
        self.devicesWithInputs = None # [(Device Name, DeviceId, [Inputs])]

class SaveActivityTemplate:
    def __init__(self):
        self.activityName = None               # Activity Name (String)
        self.activityType = None               # ActivityType
        self.roles = None                      # [(Role Name, DeviceId, Input)]

class Secrets:
    def __init__(self):
        self.HAVE_SECRET = HAVE_SECRET
        self.SCHEMA = None if not HAVE_SECRET else \
            Secret.Schema.new("net.sourceforge.congruity",
                Secret.SchemaFlags.NONE,
                {"application": Secret.SchemaAttributeType.STRING})
        self.KEY = {"application": "mhgui"}

    def _finishLookup(self, source, result, callback):
        secret = Secret.password_lookup_finish(result)
        if secret: callback(*json.loads(secret))

    def _finishStore(self, source, result, callback):
        if not Secret.password_store_finish(result):
            print("Failed to store password")
        elif callback:
            callback()

    def fetchUser(self, callback):
        Secret.password_lookup(self.SCHEMA, self.KEY, None,
            self._finishLookup, callback)

    def storeUser(self, username, password, callback=None):
        Secret.password_store(self.SCHEMA, self.KEY, Secret.COLLECTION_DEFAULT,
            "MHGUI", json.dumps([username, password]), None,
            self._finishStore, callback)

    def clearUser(self):
        Secret.password_clear(self.SCHEMA, self.KEY, None, None)

class MHAccountDetails:
    def __init__(self):
        firstName = ""
        lastName = ""
        country = ""
        email = ""
        password = ""
        keepMeInformed = ""

class LoginResponseHTMLParser(HTMLParser):
    def handle_starttag(self, tag, attrs):
        if tag == 'param' and ('name', 'initparams') in attrs:
            for key, value in attrs:
                if key == 'value':
                    self.initparams = value

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
