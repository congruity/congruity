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
import random
import datetime
from HTMLParser import HTMLParser
from suds.cache import ObjectCache
from suds.client import Client
from suds.plugin import MessagePlugin

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

TYPES_FOR_WHICH_TO_INCLUDE_TYPE_ENCODING = [
    (XSI_NS, "long"),
    (MS_NS, "guid"),
    (BUTTON_MAPPING_NS, "HardButton"),
    (BUTTON_MAPPING_NS, "CommandButtonAssignment"),
    (BUTTON_MAPPING_NS, "ChannelButtonAssignment"),
    (OPERATION_NS, "OperationBag"),
    (DM_OPERATION_NS, "Operation"),
    (DM_OPERATION_NS, "AddDeviceBySearchResultOperation"),
    (DM_OPERATION_NS, "UpdateDeviceNameOperation"),
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
    (USER_FEATURE_NS, "IRPressAction"),
    (USER_FEATURE_NS, "InputFeature"),
    (USER_FEATURE_NS, "PowerFeature"),
    (USER_FEATURE_NS, "ChannelTuningFeature"),
]

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
    def __init__(self, use_local_wsdl=False):
        if use_local_wsdl:
            # Find the harmony.wsdl file.
            appdir = os.path.abspath(os.path.dirname(sys.argv[0]))
            dirs = ['/usr/share/congruity', appdir, '.']
            for dir in dirs:
                fpath = os.path.join(dir, "harmony.wsdl")
                if os.path.isfile(fpath):
                    self.wsdl_path = fpath
                    break

            url = 'file://' + self.wsdl_path
            cache = None
        else:
            url = 'http://congruity.sourceforge.net/congruity/harmony.wsdl'
            cache = ObjectCache(hours=4)
        self.client = Client(url, cache=cache, plugins=[MHPlugin()])
        self.logged_in = False

    # Log in to web service - Returns True if login succeeded, False otherwise.
    def Login(self, email, password):
        self.logged_in = self.client.service['Security'].LoginUser(
            email=email, password=password, customCredential='',
            isPresistent=False)
        self.password = password
        return self.logged_in is not None

    # Gets the household info.
    def GetHousehold(self):
        self.household = self.client.service['AccountManager'].GetMyHousehold()

    # Gets the remote(s) for a given account.
    def GetRemotes(self):
        self.GetHousehold()
        remotes = []
        for account in self.household.Accounts.Account:
            if account.Remotes != "":
                for remote in account.Remotes.Remote:
                    remotes.append(remote)
        return remotes

    # Gets the product info for a given Skin Id.
    def GetProduct(self, skinId):
        return self.client.service['ProductsManager'].GetProduct(skinId)

    def GetProductButtonList(self, skinId):
        return self.client.service['ProductsManager'].GetProductButtonList(skinId).Buttons.ButtonDefinition

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

    # Get remote config file for the specified remote and write it to the
    # specified filename.
    def GetConfig(self, remote, filename):
        remoteId = self.client.factory.create('{' + DATA_NS + '}Id')
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

    # Returns an instance of MHAccountDetails with the existing account's
    # details filled in.
    def GetAccountDetails(self):
        details = MHAccountDetails()
        self.GetHousehold()
        properties = self.household.Accounts.Account[0].Properties
        passwordQuestion = self.client.service['AccountManager']. \
            GetPasswordQuestion(properties.Email)
        details.firstName = properties.FirstName
        details.lastName = properties.LastName
        details.country = properties.CountryType
        details.email = properties.Email
        details.password = self.password
        details.securityQuestion = passwordQuestion.PasswordQuestion
        details.securityAnswer = None
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
            print "SecureControllerHandshake failed."
            return False

        accountId = self.household.Accounts.Account[0].Id
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
            SecureUpdateAccountProperties(accountId, properties,
                                          handshakeResult.Challenge)
        if result is not None:
            print "SecureUpdateAccountProperties failed: " + str(result)
            return False

        if details.securityAnswer != "":
            result = self.client.service['AccountManager']. \
                UpdatePasswordQuestionAndAnswer(self.password,
                                                details.securityQuestion,
                                                details.securityAnswer)
            if result != "true":
                print "UpdatePasswordQuestionAndAnswer failed: " + str(result)
                return False

        if details.password != self.password:
            result = self.client.service['AccountManager']. \
                UpdatePasswordByOldPassword(details.email, self.password,
                                            details.password)
            if result != "true":
                print "UpdatePasswordByOldPassword failed: " + str(result)
                return False
            self.password = details.password

        return True

    def GetCountryLists(self):
        conn = httplib.HTTPConnection("www.myharmony.com")
        conn.request("GET", "http://www.myharmony.com/Account/Register")
        response = conn.getresponse()
        data = unicode(response.read(), 'utf-8')
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

    def GetActivityTypesAndRoles(self, accountId):
        print self.client.service['ActivityManager'].\
            GetActivityTypesAndRoles(accountId)

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

    # Creates a WatchTV activity for 200/300 remotes
    # deviceInfo is a list of (deviceId, selectedInputName)
    def SaveWatchTVActivity(self, remoteId, deviceInfo, activity=None):
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
            activity.IsTuningDefault = False
            activity.Name = "WatchTV"
            activity.State = "Setup"
            activity.Type = "WatchTV"
        activity.Roles = self.CreateRoles(deviceInfo)
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

    def GetDeviceInputNames(self, deviceId):
        features = self.GetUserFeatures(deviceId)
        if features:
            for feature in features.DeviceFeature:
                try:
                    if feature.InputType == "Discrete":
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
