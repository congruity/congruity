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

import ctypes
import os
import os.path
import sys
import threading
import time
import traceback
from six.moves.urllib.error import URLError

import wx
try: # Phoenix
    import wx.adv
    AnimationCtrl = wx.adv.AnimationCtrl
    ANIMATION_TYPE_GIF = wx.adv.ANIMATION_TYPE_GIF
    HyperlinkCtrl = wx.adv.HyperlinkCtrl
except: # Classic
    import wx.animate
    AnimationCtrl = wx.animate.AnimationCtrl
    ANIMATION_TYPE_GIF = wx.animate.ANIMATION_TYPE_GIF
    HyperlinkCtrl = wx.HyperlinkCtrl
import wx.grid
from tempfile import NamedTemporaryFile
try:
    from .mhmanager import MHManager
    from .mhmanager import MHAccountDetails
    from .mhmanager import SaveActivityTemplate
    from .mhmanager import Secrets
except ModuleNotFoundError:
    from mhmanager import MHManager
    from mhmanager import MHAccountDetails
    from mhmanager import SaveActivityTemplate
    from mhmanager import Secrets

version = "19"

HARMONY_350_SKIN_ID = "104"
HARMONY_LINK_SKIN_ID = 82
WATCH_TV_BUTTON_SKIN_IDS = [78, 79, 80, 81, 104]

try:
    import argparse
except:
    use_local_wsdl = False
    if '--use-local-wsdl' in sys.argv:
        use_local_wsdl = True
    suds_debug = False
    if '--suds-debug' in sys.argv:
        suds_debug = True
else:
    parser = argparse.ArgumentParser(description='Manage Logitech Harmony Remotes.')
    parser.add_argument('-d', '--suds-debug', help='output SOAP messages',
        action='store_true')
    parser.add_argument('-l', '--use-local-wsdl', help='use local wsdl file',
        action='store_true')
    args = parser.parse_args()
    suds_debug = args.suds_debug
    use_local_wsdl = args.use_local_wsdl
mhMgr = MHManager(use_local_wsdl, suds_debug)

secrets = Secrets()

try:
    import libconcord
except:
    str = traceback.format_exc()
    app = wx.App(False)
    dlg = wx.MessageDialog(
        None,
        "Could not load libconcord; please ensure it, and the Python "
        "bindings, are installed and in the relevant search paths.\n\n" + str,
        "congruity: Dependency Error",
        wx.OK | wx.ICON_ERROR
    )
    dlg.ShowModal()
    os._exit(1)

ALIGN_LTA = wx.ALIGN_LEFT  | wx.ALIGN_TOP             | wx.ALL
ALIGN_XTA = wx.EXPAND      | wx.ALIGN_TOP             | wx.ALL
ALIGN_LCA = wx.ALIGN_LEFT  | wx.ALIGN_CENTER_VERTICAL | wx.ALL
ALIGN_RCA = wx.ALIGN_RIGHT | wx.ALIGN_CENTER_VERTICAL | wx.ALL
ALIGN_XCA = wx.EXPAND      | wx.ALIGN_CENTER_VERTICAL | wx.ALL
ALIGN_LBA = wx.ALIGN_LEFT  | wx.ALIGN_BOTTOM          | wx.ALL
ALIGN_XBA = wx.EXPAND      | wx.ALIGN_BOTTOM          | wx.ALL

def dummy_callback_imp(stage_id, count, current, total, type, context, stages):
    pass
dummy_cb = libconcord.callback_type(dummy_callback_imp)

class ThrobberDialog(wx.Dialog):
    TITLE_REMOTE = "Please wait, contacting remote..."
    TITLE_WEBSITE = "Please wait, contacting website..."
    def __init__(self, title):
        if title is None:
            self.title = self.TITLE_WEBSITE
        else:
            self.title = title
        wx.Dialog.__init__(self, None, -1, title=self.title)
        self.SetClientSize((256, 256))
        self.SetBackgroundColour("white")
        self.gif = AnimationCtrl(self, -1)
        self.gif.LoadFile(self.FindGif("throbber.gif"),
                          ANIMATION_TYPE_GIF)
        self.gif.Play()
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.sizer.Add(self.gif, 1, wx.EXPAND|wx.ALL, 64)
        self.SetSizer(self.sizer)
    def FindGif(self, filename):
        return os.path.join(os.path.dirname(__file__), filename)

class BackgroundTask:
    def __init__(self, backgroundFunctionSpec, onDoneFunctionSpec,
                 modalThrobber = True, throbberTitle = None):
        self.backgroundFunction = backgroundFunctionSpec[0]
        self.backgroundFunctionArgs = backgroundFunctionSpec[1:]
        self.onDoneFunction = onDoneFunctionSpec[0]
        self.onDoneFunctionArgs = onDoneFunctionSpec[1:]
        threading.Thread(target=self.ThreadFunction).start()
        self.throbber = None
        if modalThrobber is not None:
            self.throbber = ThrobberDialog(throbberTitle)
            if modalThrobber is True:
                self.throbber.ShowModal()
                self.throbber.Destroy()
            else:
                self.throbber.Show()
    def ThreadFunction(self):
        result = self.backgroundFunction(*self.backgroundFunctionArgs)
        wx.CallAfter(self.ThreadDoneFunction, result)
    def ThreadDoneFunction(self, bgFuncResult):
        if self.throbber is not None:
            if self.throbber.IsModal():
                self.throbber.EndModal(0)
            else:
                self.throbber.Destroy()
        self.onDoneFunction(bgFuncResult, *self.onDoneFunctionArgs)

class WrappedStaticText(wx.StaticText):
    def __init__(self, parent):
        self.parent = parent
        wx.StaticText.__init__(self, parent, -1, "")

    def UpdateText(self, new_label):
        cur_width = self.parent.GetSize().GetWidth()
        self.SetLabel(new_label)
        self.Wrap(cur_width)
        self.Layout()
        self.parent.Layout()

def wxListStringItem(id, text):
    item = wx.ListItem()
    item.SetId(id)
    item.SetText(text)
    item.SetMask(wx.LIST_MASK_TEXT)
    return item

class WizardPanelBase(wx.Panel):
    def __init__(self, parent, resources):
        self.parent = parent
        self.resources = resources

        wx.Panel.__init__(self, parent)

    def OnActivated(self, prev_page, data):
        return (None, None)

    def OnCancel(self):
        self.parent.OnExit(1)

    def GetTitle(self):
        return "Base"

    def IsTerminal(self):
        return False

    def IsBackInitiallyDisabled(self):
        return True

    def IsNextInitiallyDisabled(self):
        return True

    def IsCloseInitiallyDisabled(self):
        return True

    def IsCancelInitiallyDisabled(self):
        return True

    def GetExitCode(self):
        return 0

    def GetBack(self):
        return (None, None)

    def GetNext(self):
        return (None, None)

class DevicePanelTemplate(WizardPanelBase):
    def __init__(self, parent, resources):
        WizardPanelBase.__init__(self, parent, resources)

        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.deviceTitle = wx.StaticText(self)
        font = wx.Font(14, wx.SWISS, wx.NORMAL, wx.BOLD)
        self.deviceTitle.SetFont(font)
        self.sizer.Add(self.deviceTitle, 0, ALIGN_XCA, 5)
        self.textMessage = WrappedStaticText(self)
        self.sizer.Add(self.textMessage, 0, ALIGN_XTA, 5)

class WelcomePanel(WizardPanelBase):
    _msg_welcome = (
        "Welcome to MHGUI: an application for accessing " +
        "Logitech's MyHarmony website.\n\n" +
        "Please enter your MyHarmony.com username and " +
        "password below.\n"
    )

    def __init__(self, parent, resources):
        WizardPanelBase.__init__(self, parent, resources)

        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.textMessage = WrappedStaticText(self)
        self.sizer.Add(self.textMessage, 0, ALIGN_XTA, 5)
        self.userSizer = wx.BoxSizer(wx.VERTICAL)
        self.usernameLabel = wx.StaticText(self, -1, "Username:")
        self.usernameCtrl = wx.TextCtrl(self, -1, "")
        self.usernameCtrl.SetMinSize((200, 31))
        self.usernameSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.usernameSizer.Add(self.usernameLabel, 0, ALIGN_LCA, 0)
        self.usernameSizer.AddStretchSpacer()
        self.usernameSizer.Add(self.usernameCtrl, 0, ALIGN_RCA, 0)
        self.userSizer.Add(self.usernameSizer, 0, wx.EXPAND, 0)
        self.passwordText = wx.StaticText(self, -1, "Password:")
        self.passwordCtrl = wx.TextCtrl(self, -1, "", style=wx.TE_PASSWORD)
        self.passwordCtrl.SetMinSize((200, 31))
        self.passwordSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.passwordSizer.Add(self.passwordText, 0, ALIGN_LCA, 0)
        self.passwordSizer.AddStretchSpacer()
        self.passwordSizer.Add(self.passwordCtrl, 0, ALIGN_RCA, 0)
        self.userSizer.Add(self.passwordSizer, 0, wx.EXPAND, 0)
        self.sizer.Add(self.userSizer)
        self.sizer.AddSpacer(25)
        if secrets.HAVE_SECRET:
            self.storeUserCtrl = wx.CheckBox(self, 0,
                "Store username and password")
            self.storeUserCtrl.Bind(wx.EVT_CHECKBOX, self.OnStoreUserChecked)
            self.sizer.Add(self.storeUserCtrl)
            self.sizer.AddSpacer(25)
        self.createAccountButton = wx.Button(self, label="Create Account")
        self.createAccountButton.Bind(wx.EVT_BUTTON, self.OnCreateAccount)
        self.sizer.Add(self.createAccountButton)

        self.SetSizerAndFit(self.sizer)

        self.next = None

        self.fetchedUsername = None
        self.fetchedPassword = None
        if secrets.HAVE_SECRET: self.FetchUser()

    def OnActivated(self, prev_page, data):
        self.textMessage.UpdateText(self._msg_welcome)
        self.next = self.resources.page_remote_select
        self.parent.ReenableNext()
        return (None, None)

    def GetTitle(self):
        return "Welcome"

    def IsCancelInitiallyDisabled(self):
        return False

    def OnUserFetched(self, username, password):
        self.usernameCtrl.ChangeValue(username)
        self.passwordCtrl.ChangeValue(password)
        self.fetchedUsername = username
        self.fetchedPassword = password
        self.storeUserCtrl.SetValue(True)

    def OnNext(self):
        username = self.usernameCtrl.GetValue()
        password = self.passwordCtrl.GetValue()
        if not (username and password):
            wx.MessageBox('Please enter a username and password',
                'Missing Login Details', wx.OK | wx.ICON_WARNING)
        else:
            BackgroundTask((self.DoLogin, username, password),
                           (self.FinishLogin,))
        return False

    def DoLogin(self, username, password):
        try:
            result = mhMgr.Login(username, password)
        except URLError as e:
            result = e.reason
        return result

    def FinishLogin(self, loginResult):
        if loginResult is True:
            if secrets.HAVE_SECRET and self.storeUserCtrl.IsChecked():
                if self.fetchedUsername != mhMgr.email or \
                   self.fetchedPassword != mhMgr.password:
                    secrets.storeUser(mhMgr.email, mhMgr.password)
            self.parent._SetPage(self.next, True, True)
        else:
            if loginResult is None:
                msg = 'You appear to have used a members.harmonyremote.com ' \
                      'account.  Please create a myharmony.com account or ' \
                      'login with an existing one.'
            elif loginResult is False:
                msg = 'Login failed.  Username or password incorrect.'
            else:
                msg = 'Login failed.  %s' % loginResult
            wx.MessageBox(msg, 'Login Failed', wx.OK | wx.ICON_WARNING)
            self.usernameCtrl.Clear()
            self.passwordCtrl.Clear()

    def GetNext(self):
        return (self.next, True, True)

    def OnCreateAccount(self, event):
        self.parent._SetPage(self.resources.page_create_account, None, True)

    def FetchUser(self):
        secrets.fetchUser(self.OnUserFetched)

    def OnStoreUserChecked(self, event):
        if not event.IsChecked():
            secrets.clearUser()

class RemoteSelectPanel(WizardPanelBase):
    _msg_welcome = (
        "Please select a remote control below.\n\n" +
        "Remotes (maximum of 6 per account):"
    )

    def __init__(self, parent, resources):
        WizardPanelBase.__init__(self, parent, resources)

        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.textMessage = WrappedStaticText(self)
        self.sizer.Add(self.textMessage, 0, ALIGN_XTA, 5)
        self.remotesListBox = wx.ListBox(self, style=wx.LB_SINGLE,
                                         size=(134, 75))
        self.sizer.Add(self.remotesListBox)
        self.sizer.AddSpacer(20)
        self.addButton = wx.Button(self, label="Add New Remote",
                                   size=(127, 33))
        self.addButton.Bind(wx.EVT_BUTTON, self.OnAddRemote)
        self.sizer.Add(self.addButton)
        self.sizer.AddSpacer(10)
        self.deleteButton = wx.Button(self, label="Delete Remote",
                                      size=(127, 33))
        self.deleteButton.Bind(wx.EVT_BUTTON, self.OnDeleteRemote)
        self.deleteButton.SetToolTip(wx.ToolTip(
                "Remove a Remote from your Account"
        ))
        self.sizer.Add(self.deleteButton)
        self.sizer.AddSpacer(10)
        self.updateAccountButton = wx.Button(self, label="Update Account",
                                             size=(127,33))
        self.updateAccountButton.Bind(wx.EVT_BUTTON, self.OnUpdateAccount)
        self.updateAccountButton.SetToolTip(wx.ToolTip(
                "Update User Account Details (password, etc.)"
        ))
        self.sizer.Add(self.updateAccountButton)
        self.SetSizerAndFit(self.sizer)

        self.next = None

    def LoadData(self):
        self.remotes = mhMgr.GetRemotes()
        self.remoteDisplayNames = []
        for remote in self.remotes:
            product = mhMgr.GetProduct(remote.SkinId)
            self.remoteDisplayNames.append(product.DisplayName)

    def AddRemote(self, serialNumber, skinId, usbPid, usbVid):
        result = mhMgr.AddRemote(serialNumber, skinId, usbPid, usbVid)
        if result is not None:
            self.LoadData()
        return result

    def DeleteRemote(self, remoteId):
        mhMgr.DeleteRemote(remoteId)
        self.LoadData()

    def LoadAddRemoteData(self):
        self.supportedRemotes = mhMgr.GetSupportedRemoteNames()
        self.supportedSkins = mhMgr.GetSupportedRemoteSkinIds()

    def LoadDataUI(self, loadDataResult):
        self.remotesListBox.Clear()
        self.remotesListBox.Set(self.remoteDisplayNames)
        if len(self.remoteDisplayNames) == 1:
            self.remotesListBox.SetSelection(0)
        self.Layout()
        self.parent.Show()

    def OnActivated(self, prev_page, loadData):
        self.textMessage.UpdateText(self._msg_welcome)
        self.parent.ReenableNext()
        if loadData:
            BackgroundTask((self.LoadData,), (self.LoadDataUI,), False)
        return (None, None)

    def GetTitle(self):
        return "Remote Selection"

    def IsCancelInitiallyDisabled(self):
        return False

    def OnAddRemote(self, event):
        BackgroundTask((self.LoadAddRemoteData,), (self.DoAddRemote,))

    def DoAddRemote(self, loadResult):
        if len(self.remotes) >= 6:
            wx.MessageBox('Each account can support up to 6 remotes.',
                          'Maximum Number of Remotes Reached',
                          wx.OK | wx.ICON_WARNING)
            return            
        msg = 'Please ensure your remote control is connected.'
        msg += '\n\nThe web service advertises support for these models:'
        for name in self.supportedRemotes:
            msg += '\n' + name
        msg += "\n\nNOTE: MHGUI has only been tested with Harmony 200, 300,"
        msg += "\n650, and Link."
        wx.MessageBox(msg, 'Connect Remote', wx.OK)

        try:
            libconcord.init_concord()
        except:
            msg = '%s\n    (libconcord function %s error %d)\n\n' % (
                sys.exc_info()[1].result_str,
                sys.exc_info()[1].func,
                sys.exc_info()[1].result
            )
            wx.MessageBox('Could not detect remote: ' + msg, 'Error',
                          wx.OK | wx.ICON_WARNING)
            return

        cb = libconcord.callback_type(dummy_callback_imp)
        try:
            libconcord.get_identity(cb, None)
        except:
            msg = '%s\n    (libconcord function %s error %d)\n\n' % (
                sys.exc_info()[1].result_str,
                sys.exc_info()[1].func,
                sys.exc_info()[1].result
            )
            wx.MessageBox('Could not identify remote: ' + msg, 'Error',
                          wx.OK | wx.ICON_WARNING)
            libconcord.deinit_concord()
            return

        ser_1 = libconcord.get_serial(libconcord.SERIAL_COMPONENT_1)
        ser_2 = libconcord.get_serial(libconcord.SERIAL_COMPONENT_2)
        ser_3 = libconcord.get_serial(libconcord.SERIAL_COMPONENT_3)
        serialNumber = (ser_1 + ser_2 + ser_3).decode('utf-8')
        skinId = libconcord.get_skin()
        usbPid = hex(libconcord.get_usb_pid())
        usbVid = hex(libconcord.get_usb_vid())
        mfg = libconcord.get_mfg().decode('utf-8')
        model = libconcord.get_model().decode('utf-8')
        mfg_model = mfg + ' ' + model
        libconcord.deinit_concord()
        # Check whether this is a supported remote.
        if skinId not in self.supportedSkins:
            wx.MessageBox('Sorry, this remote model (' + mfg_model + ') is '
                          + 'not supported by this software.  Please '
                          + 'use members.harmonyremote.com.',
                          'Unsupported Remote', wx.OK | wx.ICON_WARNING)
            return
        # Check whether this remote is already on this account.
        for remote in self.remotes:
            if remote.SerialNumber == serialNumber:
                wx.MessageBox('Sorry, this remote already exists in '
                              + 'your account.', 'Existing Remote',
                              wx.OK | wx.ICON_WARNING)
                return
        # Actually add the remote!
        BackgroundTask((self.AddRemote, serialNumber, skinId, usbPid, usbVid),
                       (self.FinishAddRemote, skinId))

    def FinishAddRemote(self, result, skinId):
        if result is not None:
            if skinId == HARMONY_LINK_SKIN_ID:
                wx.MessageBox('Remote successfully added.  Make sure to select'
                              + ' your Harmony Link, select "Forward", and'
                              + ' then select "Configure Harmony Link" to'
                              + ' complete setup.', 'Success', wx.OK)
            else:
                wx.MessageBox('Remote successfully added.', 'Success',
                              wx.OK)
            self.LoadDataUI(None)
            return
        else:
            wx.MessageBox('Remote addition failed.', 'Failure',
                          wx.OK, wx.ICON_WARNING)
            return

    def OnDeleteRemote(self, event):
        if self.remotesListBox.GetSelection() != -1:
            dlg = wx.MessageDialog(self.parent,
                                   'Are you sure you want to delete '
                                   + self.remotesListBox.GetStringSelection()
                                   + ' from your account?',
                                   'Delete Confirmation',
                                   wx.YES_NO | wx.ICON_QUESTION)
            result = dlg.ShowModal() == wx.ID_YES
            dlg.Destroy()
            if result:
                remoteId = self.remotes[self.remotesListBox.GetSelection()].Id
                BackgroundTask((self.DeleteRemote, remoteId),
                               (self.LoadDataUI,))
        else:
            wx.MessageBox('Please make a selection.', 'No selection made.',
                          wx.OK | wx.ICON_WARNING)

    def OnUpdateAccount(self, event):
        self.parent._SetPage(self.resources.page_create_account, True, True)

    def OnNext(self):
        if self.remotesListBox.GetSelection() != -1:
            self.next = self.resources.page_remote_configuration
            return True
        else:
            wx.MessageBox('Please make a selection.', 'No selection made.',
                          wx.OK | wx.ICON_WARNING)
            return False

    def GetNext(self):
        return (self.next, self.remotes[self.remotesListBox.GetSelection()],
                True)

class RemoteConfigurationPanel(WizardPanelBase):
    _msg_welcome = (
        "Please make a selection below.\n"
    )

    def __init__(self, parent, resources):
        WizardPanelBase.__init__(self, parent, resources)

        self.buttonSize = (170, 33) # Size of largest button
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.textMessage = wx.StaticText(self)
        self.sizer.Add(self.textMessage, 0, ALIGN_XTA, 5)
        self.devicesListBox = wx.ListBox(self, style=wx.LB_SINGLE)
        self.sizer.Add(self.devicesListBox, 0, 0, 0)
        self.sizer.AddSpacer(20)
        self.buttonSizer = wx.BoxSizer(wx.HORIZONTAL)

        self.leftButtonSizer = wx.BoxSizer(wx.VERTICAL)
        self.addButton = wx.Button(self, label="Add Device",
                                   size=self.buttonSize)
        self.addButton.Bind(wx.EVT_BUTTON, self.OnAdd)
        self.addButton.SetToolTip(wx.ToolTip(
                "Add a device (TV, cable box, etc) to this remote"
        ))
        self.leftButtonSizer.Add(self.addButton, 0, 0, 0)
        self.deleteButton = wx.Button(self, label="Delete Device",
                                      size=self.buttonSize)
        self.deleteButton.Bind(wx.EVT_BUTTON, self.OnDelete)
        self.leftButtonSizer.Add(self.deleteButton, 0, 0, 0)
        self.renameButton = wx.Button(self, label="Rename Device",
                                      size=self.buttonSize)
        self.renameButton.Bind(wx.EVT_BUTTON, self.OnRename)
        self.leftButtonSizer.Add(self.renameButton, 0, 0, 0)
        self.configureButton = wx.Button(self, label="Configure Device",
                                         size=self.buttonSize)
        self.configureButton.Bind(wx.EVT_BUTTON, self.OnConfigure)
        self.configureButton.SetToolTip(wx.ToolTip(
                "Adjust/fix button functionality for a device"
        ))
        self.leftButtonSizer.Add(self.configureButton, 0, 0, 0)
        self.adjustPowerSettingsButton = wx.Button(
            self, label="Adjust Power Settings", size=self.buttonSize)
        self.adjustPowerSettingsButton.Bind(wx.EVT_BUTTON,
                                            self.OnAdjustPowerSettings)
        self.adjustPowerSettingsButton.SetToolTip(wx.ToolTip(
                "Adjust power on/off settings for a device"
        ))
        self.leftButtonSizer.Add(self.adjustPowerSettingsButton)
        self.adjustDeviceDelaysButton = wx.Button(
            self, label="Adjust Device Delays", size=self.buttonSize)
        self.adjustDeviceDelaysButton.Bind(wx.EVT_BUTTON,
                                           self.OnAdjustDeviceDelays)
        self.adjustDeviceDelaysButton.SetToolTip(wx.ToolTip(
                "Adjust speed of commands sent to a device"
        ))
        self.leftButtonSizer.Add(self.adjustDeviceDelaysButton)
        self.buttonSizer.Add(self.leftButtonSizer, 0, 0, 0)

        self.rightButtonSizer = wx.BoxSizer(wx.VERTICAL)
        self.buttonSizer.Add(self.rightButtonSizer, 0, 0, 0)

        self.sizer.Add(self.buttonSizer, 0, 0, 0)
        self.SetSizerAndFit(self.sizer)

        self.next = None

    def AddFavoriteChannelsButton(self):
        self.favoriteChannelsButton = wx.Button(self,
                                                label="Edit Favorite Channels",
                                                size=self.buttonSize)
        self.favoriteChannelsButton.Bind(wx.EVT_BUTTON, self.OnFavoriteChannels)
        self.rightButtonSizer.Add(self.favoriteChannelsButton, 0, 0, 0)

    def AddConfigButtons(self):
        self.syncButton = wx.Button(self, label="Sync Remote",
                                    size=self.buttonSize)
        self.syncButton.Bind(wx.EVT_BUTTON, self.OnSync)
        self.syncButton.SetToolTip(wx.ToolTip(
                "Update the configuration on your remote"
        ))
        self.rightButtonSizer.Add(self.syncButton, 0, 0, 0)
        self.downloadConfigButton = wx.Button(self, label="Download Config",
                                              size=self.buttonSize)
        self.downloadConfigButton.Bind(wx.EVT_BUTTON, self.OnDownloadConfig)
        self.downloadConfigButton.SetToolTip(wx.ToolTip(
                "Download the config for your remote and save it to a file"
        ))
        self.rightButtonSizer.Add(self.downloadConfigButton, 0, 0, 0)

    def AddSetupWatchTVButton(self):
        self.setupWatchTVButton = wx.Button(self, label="Setup Watch TV Button",
                                            size=self.buttonSize)
        self.setupWatchTVButton.Bind(wx.EVT_BUTTON, self.OnSetupWatchTV)
        self.setupWatchTVButton.SetToolTip(wx.ToolTip(
                "Configure what happens when you press your Watch TV button"
        ))
        self.rightButtonSizer.Add(self.setupWatchTVButton, 0, 0, 0)

    def AddConfigureHarmonyLinkButton(self):
        self.configureHarmonyLinkButton = wx.Button(
            self, label="Configure Harmony Link", size=self.buttonSize)
        self.configureHarmonyLinkButton.Bind(wx.EVT_BUTTON,
                                             self.OnConfigureHarmonyLink)
        self.configureHarmonyLinkButton.SetToolTip(wx.ToolTip(
                "Configure Harmony Link Settings (Room Name, Wifi, etc.)"
        ))
        self.rightButtonSizer.Add(self.configureHarmonyLinkButton, 0, 0, 0)

    def AddSetupActivitiesButton(self):
        self.setupActivitiesButton = wx.Button(self, label="Setup Activities",
                                               size=self.buttonSize)
        self.setupActivitiesButton.Bind(wx.EVT_BUTTON, self.OnSetupActivities)
        self.setupActivitiesButton.SetToolTip(wx.ToolTip(
                "Configure one-button activities (e.g., Watch TV)"
        ))
        self.rightButtonSizer.Add(self.setupActivitiesButton, 0, 0, 0)

    def LoadData(self):
        self.product = mhMgr.GetProduct(self.remote.SkinId)
        self.devices = mhMgr.GetDevices(self.remote.Id)
        if self.remote.SkinId == HARMONY_350_SKIN_ID:
            self.watchTVActivity = mhMgr.GetActivity(self.remote.Id, "Watch TV")

    def LoadDataUI(self, loadDataResult):
        self._msg_welcome = "Remote Configuration for " \
            + self.product.DisplayName + "\n\nDevices (maximum of " \
            + str(self.product.MaxDevicesPerAccount) + "):"
        self.textMessage.SetLabel(self._msg_welcome)
        self.PopulateDevicesList()

        # Populate remote-specific buttons in rightButtonSizer
        self.rightButtonSizer.Clear(True)
        capabilities = mhMgr.GetCapabilityNames(self.product)
        if "FavoriteChannels" in capabilities:
            self.AddFavoriteChannelsButton()
        if "CompiledRemoteButtonMapping" in capabilities or \
                "ActivityCompiledRemoteButtonMapping" in capabilities:
            self.AddConfigButtons()
        if int(self.remote.SkinId) in WATCH_TV_BUTTON_SKIN_IDS:
            self.AddSetupWatchTVButton()
        if "Wifi" in capabilities:
            self.AddConfigureHarmonyLinkButton()
        if "Activities" in capabilities and \
                int(self.remote.SkinId) not in WATCH_TV_BUTTON_SKIN_IDS:
            self.AddSetupActivitiesButton()

        self.Layout()
        self.parent.Show()

    def PopulateDevicesList(self):
        self.devicesList = []
        if self.devices is not None:
            for device in self.devices:
                self.devicesList.append(device.Name)
            self.devicesListBox.Set(self.devicesList)
        else:
            self.devicesListBox.Clear()

    def OnAdd(self, event):
        if len(self.devicesList) < self.product.MaxDevicesPerAccount:
            self.parent._SetPage(self.resources.page_add_device, self.remote)
        else:
            wx.MessageBox('Remote cannot support additional devices.',
                          'Cannot Add Device.', wx.OK | wx.ICON_WARNING)

    def OnDelete(self, event):
        deviceToDelete = self.devicesListBox.GetSelections()
        if deviceToDelete:
            dlg = wx.MessageDialog(self.parent,
                                   'Are you sure you want to delete '
                                   + self.devicesListBox.GetStringSelection()
                                   + '?', 'Delete Confirmation',
                                   wx.YES_NO | wx.ICON_QUESTION)
            result = dlg.ShowModal() == wx.ID_YES
            dlg.Destroy()
            if result:
                BackgroundTask((self.DoDelete, deviceToDelete),
                               (self.FinishDelete,))
        else:
            wx.MessageBox('Please select a device to delete.',
                          'No selection made.', wx.OK | wx.ICON_WARNING)

    def DoDelete(self, deviceToDelete):
        mhMgr.DeleteDevice(self.devices[deviceToDelete[0]].Id)
        self.devices = mhMgr.GetDevices(self.remote.Id)

    def FinishDelete(self, result):
        self.PopulateDevicesList()
        self.Layout()

    def OnRename(self, event):
        deviceToRename = self.devicesListBox.GetSelections()
        if deviceToRename:
            dlg = wx.TextEntryDialog(self.parent,
                                     'Enter new name for device "'
                                     + self.devicesListBox.GetStringSelection()
                                     + '":', 'Rename Device')
            result = dlg.ShowModal() == wx.ID_OK
            newName = dlg.GetValue()
            dlg.Destroy()
            if result:
                BackgroundTask((self.DoRename, deviceToRename, newName),
                               (self.FinishRename,))
        else:
            wx.MessageBox('Please select a device to rename.',
                          'No selection made.', wx.OK | wx.ICON_WARNING)

    def DoRename(self, deviceToRename, newName):
        mhMgr.RenameDevice(self.devices[deviceToRename[0]].Id, newName)
        self.devices = mhMgr.GetDevices(self.remote.Id)

    def FinishRename(self, result):
        self.PopulateDevicesList()
        self.Layout()

    def OnConfigure(self, event):
        deviceToConfigure = self.devicesListBox.GetSelections()
        if deviceToConfigure:
            params = (
                self.remote.SkinId,
                self.product,
                self.devices[deviceToConfigure[0]].Id,
                self.devices[deviceToConfigure[0]].Name
            )
            self.parent._SetPage(self.resources.page_configure_device, params,
                                 True)
        else:
            wx.MessageBox('Please select a device to configure.',
                          'No selection made.', wx.OK | wx.ICON_WARNING)

    def OnFavoriteChannels(self, event):
        deviceToConfigure = self.devicesListBox.GetSelections()
        if deviceToConfigure:
            params = (
                self.remote.SkinId,
                self.devices[deviceToConfigure[0]].Id,
                self.devices[deviceToConfigure[0]].Name
            )
            self.parent._SetPage(self.resources.page_favorite_channels, params,
                                 True)
        else:
            wx.MessageBox('Please select a device for which to configure the '
                          + "favorite channels.", 'No selection made.',
                          wx.OK | wx.ICON_WARNING)

    def OnSync(self, event):
        tempFile = NamedTemporaryFile(delete=False)
        tempFile.close()
        BackgroundTask((mhMgr.GetConfig, self.remote, tempFile.name),
                       (self.FinishSync, tempFile.name))

    def FinishSync(self, getConfigResult, tempFileName):
        self.parent.Hide()
        BackgroundTask((self.DoCongruity, tempFileName),
                       (self.FinishCongruity,), None)

    def DoCongruity(self, tempFileName):
        congruityPath = os.path.join(os.path.dirname(__file__), "congruity.py")
        os.system(sys.executable + " " + congruityPath + " --no-web " + tempFileName)
        os.unlink(tempFileName)

    def FinishCongruity(self, result):
        self.parent.Show()

    def OnDownloadConfig(self, event):
        dialog = wx.FileDialog(
            self,
            message = "Save configuration as...", 
            defaultFile = "config.zip",
            style = wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT
        )
        if dialog.ShowModal() == wx.ID_OK:
            filename = dialog.GetPath()
            dialog.Destroy()
            BackgroundTask((mhMgr.GetConfig, self.remote, filename),
                           (self.FinishDownloadConfig, filename))
        else:
            dialog.Destroy()

    def FinishDownloadConfig(self, getConfigResult, filename):
        wx.MessageBox('Config file saved to ' + filename,
                      'Download complete.', wx.OK)

    def OnSetupWatchTV(self, event):
        if self.remote.SkinId == HARMONY_350_SKIN_ID:
            params = (self.remote, "WatchTV", self.watchTVActivity)
            self.parent._SetPage(self.resources.page_edit_activity, params,
                                 True)
        else:
            self.parent._SetPage(self.resources.page_setup_watch_tv,
                                 self.remote, True)

    def OnConfigureHarmonyLink(self, event):
        self.parent._SetPage(self.resources.page_harmony_link, self.remote)

    def OnSetupActivities(self, event):
        self.parent._SetPage(self.resources.page_setup_activities, self.remote,
                             True)

    def OnAdjustPowerSettings(self, event):
        deviceToConfigure = self.devicesListBox.GetSelections()
        if deviceToConfigure:
            self.parent._SetPage(self.resources.page_adjust_power_settings,
                                 self.devices[deviceToConfigure[0]], True)
        else:
            wx.MessageBox('Please select a device to adjust.',
                          'No selection made.', wx.OK | wx.ICON_WARNING)

    def OnAdjustDeviceDelays(self, event):
        deviceToConfigure = self.devicesListBox.GetSelections()
        if deviceToConfigure:
            self.parent._SetPage(self.resources.page_adjust_device_delays,
                                 (self.remote.Id,
                                  self.devices[deviceToConfigure[0]].Id,
                                  self.devices[deviceToConfigure[0]].Name),
                                  True)
        else:
            wx.MessageBox('Please select a device to adjust.',
                          'No selection made.', wx.OK | wx.ICON_WARNING)

    def OnActivated(self, prev_page, remote):
        self.parent.ReenableBack()
        if remote is not None:
            self.remote = remote
            BackgroundTask((self.LoadData,), (self.LoadDataUI,), False)
        return (None, None)

    def GetTitle(self):
        return "Remote Configuration"

    def IsCancelInitiallyDisabled(self):
        return False

    def OnNext(self):
        pass

    def GetNext(self):
        return (self.next, None)

    def GetBack(self):
        return (self.resources.page_remote_select, False)

class AddDevicePanel(WizardPanelBase):
    _msg_welcome = (
        "Please enter the manufacturer and model number of your device below.\n"
    )

    def __init__(self, parent, resources):
        WizardPanelBase.__init__(self, parent, resources)

        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.textMessage = WrappedStaticText(self)
        self.sizer.Add(self.textMessage, 0, ALIGN_XTA, 5)
        self.typeSizer = wx.BoxSizer(wx.VERTICAL)
        self.manufacturerLabel = wx.StaticText(self, -1, "Manufacturer:")
        self.manufacturerCtrl = wx.TextCtrl(self, -1, "")
        self.manufacturerCtrl.SetMinSize((200, 31))
        self.manufacturerSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.manufacturerSizer.Add(self.manufacturerLabel, 0, ALIGN_LCA, 0)
        self.manufacturerSizer.AddStretchSpacer()
        self.manufacturerSizer.Add(self.manufacturerCtrl, 0, ALIGN_RCA, 0)
        self.typeSizer.Add(self.manufacturerSizer, 0, wx.EXPAND, 0)
        self.modelNumberText = wx.StaticText(self, -1, "Model Number:")
        self.modelNumberCtrl = wx.TextCtrl(self, -1, "")
        self.modelNumberCtrl.SetMinSize((200, 31))
        self.modelNumberSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.modelNumberSizer.Add(self.modelNumberText, 0, ALIGN_LCA, 0)
        self.modelNumberSizer.AddStretchSpacer()
        self.modelNumberSizer.Add(self.modelNumberCtrl, 0, ALIGN_RCA, 0)
        self.typeSizer.Add(self.modelNumberSizer, 0, wx.EXPAND, 0)
        self.sizer.Add(self.typeSizer)
        self.searchButton = wx.Button(self, label="Search")
        self.searchButton.Bind(wx.EVT_BUTTON, self.OnSearch)
        self.sizer.Add(self.searchButton, 0, 0, 0)

        self.divider = wx.StaticLine(self)
        self.sizer.Add(self.divider, 0, wx.EXPAND | wx.ALL, 5)

        self.searchResultsText = wx.StaticText(self, -1, "Search Results:")
        self.sizer.Add(self.searchResultsText, 0, 0, 0)
        self.searchResultsListBox = wx.ListBox(self, style=wx.LB_SINGLE, 
                                               size=(300, 150))
        self.sizer.Add(self.searchResultsListBox, 0, 0, 0)
        self.addButton = wx.Button(self, label="Add Device")
        self.addButton.Bind(wx.EVT_BUTTON, self.OnAdd)
        self.sizer.Add(self.addButton, 0, 0, 0)

        self.SetSizerAndFit(self.sizer)

        self.next = None

    def OnActivated(self, prev_page, data):
        self.textMessage.UpdateText(self._msg_welcome)
        self.parent.ReenableBack()
        self.remote = data
        self.ClearPage()
        return (None, None)

    def OnSearch(self, event):
        self.searchResultsList = []
        self.searchResultsListBox.Set(self.searchResultsList)
        if self.manufacturerCtrl.IsEmpty():
            wx.MessageBox('Please enter a manufacturer.',
                          'No manufacturer entered.', wx.OK | wx.ICON_WARNING)
        elif self.modelNumberCtrl.IsEmpty():
            wx.MessageBox('Please enter a model number.',
                          'No model number entered.', wx.OK | wx.ICON_WARNING)
        else:
            manufacturer = self.manufacturerCtrl.GetValue()
            modelNumber = self.modelNumberCtrl.GetValue()
            BackgroundTask((self.DoSearch, manufacturer, modelNumber),
                           (self.FinishSearch,))

    def DoSearch(self, manufacturer, modelNumber):
        return mhMgr.SearchDevices(manufacturer, modelNumber, 5)

    def FinishSearch(self, searchResults):
        if searchResults.Status == "NoMatchFound":
            wx.MessageBox('Sorry, no devices were found.',
                          'No devices found.', wx.OK | wx.ICON_WARNING)
        else:
            self.matches = searchResults.Matches.PublicDeviceSearchMatch
            for match in self.matches:
                self.searchResultsList.append(match.Manufacturer + " "
                                              + match.DeviceModel)
            self.searchResultsListBox.Set(self.searchResultsList)

    def OnAdd(self, event):
        deviceToAdd = self.searchResultsListBox.GetSelections()
        if deviceToAdd:
            BackgroundTask((self.DoAdd, deviceToAdd), (self.FinishAdd,))
        else:
            wx.MessageBox('Please select a device to add.',
                          'No selection made.', wx.OK | wx.ICON_WARNING)

    def DoAdd(self, deviceToAdd):
        return mhMgr.AddDevice(self.matches[deviceToAdd[0]], self.remote.Id)

    def FinishAdd(self, result):
        if result is None:
            wx.MessageBox('Device addition failed!',
                          'Failure', wx.OK | wx.ICON_WARNING)
        else:
            self.parent._SetPage(self.resources.page_remote_configuration,
                                 self.remote, True)

    def ClearPage(self):
        self.manufacturerCtrl.Clear()
        self.modelNumberCtrl.Clear()
        self.searchResultsListBox.Clear()

    def GetTitle(self):
        return "Device Addition"

    def IsCancelInitiallyDisabled(self):
        return False

    def OnNext(self):
        pass

    def GetNext(self):
        return (self.next, None)

    def GetBack(self):
        return (self.resources.page_remote_configuration, None)

class CreateAccountPanel(WizardPanelBase):
    _msg_welcome_create = (
        "Please enter the information below in order to create an account.\n"
    )
    _msg_welcome_update = (
        "Please update the information below.\n"
    )

    def __init__(self, parent, resources):
        WizardPanelBase.__init__(self, parent, resources)

        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.textMessage = WrappedStaticText(self)
        self.sizer.Add(self.textMessage, 0, ALIGN_XTA, 5)
    
        self.lineOneSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.firstNameLabel = wx.StaticText(self, -1, "First Name:")
        self.lineOneSizer.Add(self.firstNameLabel, 0, ALIGN_LCA)
        self.firstNameCtrl = wx.TextCtrl(self, size=(120,31))
        self.firstNameCtrl.SetMaxLength(30)
        self.lineOneSizer.Add(self.firstNameCtrl)
        self.lineOneSizer.AddSpacer(25)
        self.lastNameLabel = wx.StaticText(self, -1, "Last Name:")
        self.lineOneSizer.Add(self.lastNameLabel, 0, ALIGN_LCA)
        self.lastNameCtrl = wx.TextCtrl(self, size=(120,31))
        self.lastNameCtrl.SetMaxLength(30)
        self.lineOneSizer.Add(self.lastNameCtrl)
        self.sizer.Add(self.lineOneSizer)
        self.sizer.AddSpacer(12)

        self.lineTwoSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.countryLabel = wx.StaticText(self, -1, "Country:")
        self.lineTwoSizer.Add(self.countryLabel, 0, ALIGN_LCA)
        self.countryChoice = wx.Choice(self, -1)
        self.lineTwoSizer.Add(self.countryChoice)
        self.sizer.Add(self.lineTwoSizer)
        self.sizer.AddSpacer(12)

        self.lineThreeSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.emailAddressLabel = wx.StaticText(self, -1, "Email Address:")
        self.lineThreeSizer.Add(self.emailAddressLabel, 0, ALIGN_LCA)
        self.emailAddressCtrl = wx.TextCtrl(self, size=(170,31))
        self.emailAddressCtrl.SetMaxLength(50)
        self.lineThreeSizer.Add(self.emailAddressCtrl)
        self.sizer.Add(self.lineThreeSizer)
        self.sizer.AddSpacer(12)

        self.lineFourSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.passwordLabel = wx.StaticText(self, -1, "Password:")
        self.lineFourSizer.Add(self.passwordLabel, 0, ALIGN_LCA)
        self.passwordCtrl = wx.TextCtrl(self, -1, "", style=wx.TE_PASSWORD, 
                                        size=(120, 31))
        self.passwordCtrl.SetMaxLength(30)
        self.lineFourSizer.Add(self.passwordCtrl)
        self.lineFourSizer.AddSpacer(25)
        self.retypePasswordLabel = wx.StaticText(self, -1, "Confirm Password:")
        self.lineFourSizer.Add(self.retypePasswordLabel, 0, ALIGN_LCA)
        self.retypePasswordCtrl = wx.TextCtrl(self, -1, "",
                                              style=wx.TE_PASSWORD,
                                              size=(120, 31))
        self.retypePasswordCtrl.SetMaxLength(30)
        self.lineFourSizer.Add(self.retypePasswordCtrl)
        self.sizer.Add(self.lineFourSizer)
        self.sizer.AddSpacer(12)

        self.lineSevenSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.termsCheckBox = wx.CheckBox(self,
            label="I agree to the Logitech Terms of Use and Privacy Policy")
        self.sizer.Add(self.termsCheckBox)
        self.contactCheckBox = wx.CheckBox(self,
            label="Keep me informed about Logitech offers and products.")
        self.sizer.Add(self.contactCheckBox)

        self.lineEightSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.termsOfUseLink = HyperlinkCtrl(self, -1, "Terms of Use",
            "https://files.myharmony.com/Assets/legal/en/termsofuse.html")
        self.lineEightSizer.Add(self.termsOfUseLink)
        self.lineEightSizer.AddSpacer(10)
        self.privacyPolicyLink = HyperlinkCtrl(self, -1, "Privacy Policy",
            "https://files.myharmony.com/Assets/legal/en/privacypolicy.html")
        self.lineEightSizer.Add(self.privacyPolicyLink)
        self.sizer.Add(self.lineEightSizer)

        self.SetSizerAndFit(self.sizer)

        self.next = None

    def OnActivated(self, prev_page, data):
        self.parent.ReenableNext()
        self.parent.ReenableBack()
        if data is not None:
            self.isUpdate = True
            self.parent.title.SetLabel("Account Update")
            self._msg_welcome = self._msg_welcome_update
        else:
            self.isUpdate = False
            self._msg_welcome = self._msg_welcome_create
            self.ClearData()
        self.textMessage.UpdateText(self._msg_welcome)
        BackgroundTask((self.LoadData,), (self.LoadDataUI,), False)
        return (None, None)

    def LoadData(self):
        self.countryLists = mhMgr.GetCountryLists()
        self.countryCodes = self.countryLists[0]
        self.countries = self.countryLists[1]
        if self.isUpdate:
            self.details = mhMgr.GetAccountDetails()

    def LoadDataUI(self, loadDataResult):
        self.countryChoice.SetItems(self.countries)
        if self.isUpdate:
            self.PopulateData()
        self.Layout()
        self.parent.Show()

    def PopulateData(self):
        details = self.details
        self.firstNameCtrl.SetValue(details.firstName)
        self.lastNameCtrl.SetValue(details.lastName)
        self.countryChoice.SetSelection(
            self.countryCodes.index(details.country)
        )
        self.emailAddressCtrl.SetValue(details.email)
        self.passwordCtrl.SetValue(details.password) 
        self.retypePasswordCtrl.SetValue(details.password)
        self.termsCheckBox.SetValue(True)
        if str(details.keepMeInformed).lower() == "true":
            self.contactCheckBox.SetValue(True)
        else:
            self.contactCheckBox.SetValue(False)

    def ClearData(self):
        self.firstNameCtrl.Clear()
        self.lastNameCtrl.Clear()
        self.countryChoice.SetSelection(0)
        self.emailAddressCtrl.Clear()
        self.passwordCtrl.Clear()
        self.retypePasswordCtrl.Clear()
        self.termsCheckBox.SetValue(False)
        self.contactCheckBox.SetValue(False)

    def GetTitle(self):
        return "Account Creation"

    def IsCancelInitiallyDisabled(self):
        return False

    def OnNext(self):
        if self.firstNameCtrl.IsEmpty():
            wx.MessageBox('First Name Required.',
                          'Error', wx.OK | wx.ICON_WARNING)
            return
        if self.lastNameCtrl.IsEmpty():
            wx.MessageBox('Last Name Required.',
                          'Error', wx.OK | wx.ICON_WARNING)
            return
        if self.countryChoice.GetSelection() == 0:
            wx.MessageBox('Country Selection Required.',
                          'Error', wx.OK | wx.ICON_WARNING)
            return
        if self.emailAddressCtrl.IsEmpty():
            wx.MessageBox('Email Address Required.',
                          'Error', wx.OK | wx.ICON_WARNING)
            return
        if len(self.passwordCtrl.GetValue()) < 4:
            wx.MessageBox('Passwords must be at least 4 characters.',
                          'Error', wx.OK | wx.ICON_WARNING)
            return
        if self.passwordCtrl.GetValue() != self.retypePasswordCtrl.GetValue():
            wx.MessageBox('Passwords do not match.',
                          'Error', wx.OK | wx.ICON_WARNING)
            return
        if self.termsCheckBox.GetValue() is False:
            wx.MessageBox('Must accept terms and conditions.',
                          'Error', wx.OK | wx.ICON_WARNING)
            return

        mhAccount = MHAccountDetails()
        mhAccount.firstName = self.firstNameCtrl.GetValue()
        mhAccount.lastName = self.lastNameCtrl.GetValue()
        mhAccount.country = self.countryCodes[self.countryChoice.GetSelection()]
        mhAccount.email = self.emailAddressCtrl.GetValue()
        mhAccount.password = self.passwordCtrl.GetValue()
        if self.contactCheckBox.GetValue() is True:
            mhAccount.keepMeInformed = "true"
        else:
            mhAccount.keepMeInformed = "false"

        if not self.isUpdate:
            BackgroundTask((self.DoCreateAccount, mhAccount),
                           (self.FinishCreateAccount,))
        else:
            BackgroundTask((self.DoUpdateAccount, mhAccount),
                           (self.FinishUpdateAccount,))

    def DoCreateAccount(self, mhAccount):
        return mhMgr.CreateAccount(mhAccount)

    def FinishCreateAccount(self, result):
        if result is None:
            wx.MessageBox('Account created successfully.', 'Success', wx.OK)
            self.parent._SetPage(self.resources.page_welcome, None)
        else:
            wx.MessageBox(result, 'Error', wx.OK | wx.ICON_WARNING)

    def DoUpdateAccount(self, mhAccount):
        return mhMgr.UpdateAccountDetails(mhAccount)

    def FinishUpdateAccount(self, result):
        if result:
            wx.MessageBox('Account updated successfully.', 'Success', wx.OK)
            self.parent._SetPage(self.resources.page_remote_select, False)
        else:
            wx.MessageBox('Account update failed.', 'Failure',
                          wx.OK | wx.ICON_WARNING)

    def GetNext(self):
        return (self.next, None)

    def GetBack(self):
        if self.isUpdate:
            return (self.resources.page_remote_select, False)
        else:
            return (self.resources.page_welcome, None)

class ConfigureDevicePanel(WizardPanelBase):
    _msg_welcome = (
        "Please select a remote control button to modify on the left.\n" +
        "Then, select a device command to assign to that button on the right.\n"
        + "If there is an existing device command assigned to a button, it\n"
        + "will be selected when you select the remote control button."
    )

    def __init__(self, parent, resources):
        WizardPanelBase.__init__(self, parent, resources)

        self.LC_WIDTH = 225
        self.LC_HEIGHT = 225
        self.LC_SIZE = (self.LC_WIDTH, self.LC_HEIGHT)

        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.textMessage = WrappedStaticText(self)
        self.sizer.Add(self.textMessage, 0, ALIGN_XTA, 5)

        self.sizer.AddSpacer(10)
        self.hSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.leftSizer = wx.BoxSizer(wx.VERTICAL)
        self.remoteButtonsLabel = wx.StaticText(self, -1, "Remote Buttons:")
        self.leftSizer.Add(self.remoteButtonsLabel, 0, 0, 0)
        self.remoteButtonsListCtrl = wx.ListCtrl(self, size=self.LC_SIZE,
            style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_NO_HEADER)
        self.remoteButtonsListCtrl.InsertColumn(0, "")
        self.remoteButtonsListCtrl.SetColumnWidth(0, self.LC_WIDTH - 1)
        self.remoteButtonsListCtrl.Bind(wx.EVT_LIST_ITEM_SELECTED,
                                        self.OnRemoteButtonSelection)
        self.leftSizer.Add(self.remoteButtonsListCtrl)
        self.hSizer.Add(self.leftSizer, 0, 0, 0)
        self.hSizer.AddSpacer(20)
        self.rightSizer = wx.BoxSizer(wx.VERTICAL)
        self.deviceCommandsLabel = wx.StaticText(self, -1, "Device Commands:")
        self.rightSizer.Add(self.deviceCommandsLabel, 0, 0, 0)
        self.deviceCommandsListCtrl = wx.ListCtrl(self, size=self.LC_SIZE,
            style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_NO_HEADER)
        self.deviceCommandsListCtrl.InsertColumn(0, "")
        self.deviceCommandsListCtrl.SetColumnWidth(0, self.LC_WIDTH - 1)
        self.rightSizer.Add(self.deviceCommandsListCtrl)
        self.hSizer.Add(self.rightSizer, 0, 0, 0)
        self.sizer.Add(self.hSizer, 0, 0, 0)
        self.sizer.AddSpacer(10)

        self.bottomSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.updateButton = wx.Button(self, label="Update Button")
        self.updateButton.Bind(wx.EVT_BUTTON, self.OnUpdate)
        self.updateButton.SetToolTip(wx.ToolTip(
                "Update selected button with the selected device command"
        ))
        self.bottomSizer.Add(self.updateButton, 0, 0, 0)
        self.overrideButton = wx.Button(self, label="Override Command")
        self.overrideButton.Bind(wx.EVT_BUTTON, self.OnOverride)
        self.overrideButton.SetToolTip(wx.ToolTip(
                "Learn IR command from existing remote to replace a command"
        ))
        self.bottomSizer.Add(self.overrideButton, 0, 0, 0)
        self.addButton = wx.Button(self, label="Add Command")
        self.addButton.Bind(wx.EVT_BUTTON, self.OnAdd)
        self.addButton.SetToolTip(wx.ToolTip(
                "Learn IR command from existing remote as a new command"
        ))
        self.bottomSizer.Add(self.addButton, 0, 0, 0)
        self.restoreButton = wx.Button(self, label="Restore Command")
        self.restoreButton.Bind(wx.EVT_BUTTON, self.OnRestore)
        self.restoreButton.SetToolTip(wx.ToolTip(
                "Remove overriden IR command/restore to official command"
        ))
        self.bottomSizer.Add(self.restoreButton, 0, 0, 0)
        self.sizer.Add(self.bottomSizer, 0, 0, 0)

        self.SetSizerAndFit(self.sizer)

        self.next = None

    def OnActivated(self, prev_page, data):
        self.textMessage.UpdateText(self._msg_welcome)
        self.parent.ReenableBack()
        self.skinId, self.product, self.deviceId, self.deviceName = data
        self.parent.title.SetLabel(self.deviceName)
        BackgroundTask((self.LoadData,), (self.LoadDataUI,), False)
        return (None, None)

    def LoadData(self):
        # Only populate the buttons list if this remote has buttons; if the
        # 'remote' is a Harmony Link, it has no ProductButtonList.
        self.remoteButtons = None
        capabilities = mhMgr.GetCapabilityNames(self.product)
        if "CompiledRemoteButtonMapping" in capabilities:
            self.buttonMapType = "Compiled"
            self.remoteButtons = mhMgr.GetProductButtonList(self.skinId)
            self.buttonMap = mhMgr.GetButtonMap(self.deviceId)
        elif "ActivityCompiledRemoteButtonMapping" in capabilities:
            self.buttonMapType = "ActivityCompiled"
            self.remoteButtons = mhMgr.GetRemoteCanvas(self.skinId)
            self.buttonMap = mhMgr.GetUserButtonMap(self.deviceId)
        self.deviceCommands = mhMgr.GetCommands(self.deviceId)

    def LoadDataUI(self, loadDataResult):
        self.remoteButtonsListCtrl.DeleteAllItems()
        if self.remoteButtons is not None:
            for i in range(len(self.remoteButtons)):
                buttonKey = self.remoteButtons[i].ButtonKey
                self.remoteButtonsListCtrl.InsertItem(wxListStringItem(i, buttonKey))

        self.deviceCommandsListCtrl.DeleteAllItems()
        if self.deviceCommands is not None:
            for i in range(len(self.deviceCommands)):
                command = self.deviceCommands[i]
                name = command.Name
                if command.IsLearned == "true":
                    name += "*"
                self.deviceCommandsListCtrl.InsertItem(wxListStringItem(i, name))
                if self.IsCommandMapped(command):
                    color = wx.LIGHT_GREY
                    self.deviceCommandsListCtrl.SetItemTextColour(i, color)

        self.parent.Show()

    def OnRemoteButtonSelection(self, event):
        buttonSelection = self.remoteButtonsListCtrl.GetFirstSelected()
        key = self.remoteButtons[buttonSelection].ButtonKey
        foundCommand = self.FindCommand(key)
        if foundCommand is not None:
            for i in range(len(self.deviceCommands)):
                if self.buttonMapType == "Compiled":
                    # ButtonAssignment might not be a CommandButtonAssignment,
                    # but ignore the error if it isn't.
                    try:
                        if foundCommand.ButtonAssignment.CommandId.Value == \
                                self.deviceCommands[i].Id.Value:
                            self.deviceCommandsListCtrl.Select(i)
                            self.deviceCommandsListCtrl.EnsureVisible(i)
                            return
                    except AttributeError:
                        pass
                elif self.buttonMapType == "ActivityCompiled":
                    # ButtonAction might not be a CommandButtonAction,
                    # but ignore the error if it isn't.
                    try:
                        if foundCommand.ButtonAction.CommandName == \
                                self.deviceCommands[i].Name:
                            self.deviceCommandsListCtrl.Select(i)
                            self.deviceCommandsListCtrl.EnsureVisible(i)
                            return
                    except AttributeError:
                        pass

        commandSelection = self.deviceCommandsListCtrl.GetFirstSelected()
        if commandSelection != -1:
            self.deviceCommandsListCtrl.Select(commandSelection, 0)

    def FindCommand(self, buttonKey):
        if self.buttonMapType == "Compiled":
            for button in self.buttonMap.Buttons.AbstractButton:
                if buttonKey == button.ButtonKey:
                    return button
        elif self.buttonMapType == "ActivityCompiled":
            for button in self.buttonMap.Buttons.AbstractRemoteButton:
                try:
                    if buttonKey == button.ButtonKey:
                        return button
                except AttributeError:
                    pass
        return None

    def IsCommandMapped(self, command):
        if self.buttonMapType == "Compiled":
            for button in self.buttonMap.Buttons.AbstractButton:
                # ButtonAssignment might not be a CommandButtonAssignment, but
                # ignore the error if it isn't.
                try:
                    if button.ButtonAssignment.CommandId.Value == \
                       command.Id.Value:
                        return True
                except AttributeError:
                    pass
            return False
        elif self.buttonMapType == "ActivityCompiled":
            for button in self.buttonMap.Buttons.AbstractRemoteButton:
                # ButtonAction might not be a CommandButtonAction, but
                # ignore the error if it isn't.
                try:
                    if button.ButtonAction.CommandName == command.Name:
                        return True
                except AttributeError:
                    pass
            return False

    def OnUpdate(self, event):
        buttonSelection = self.remoteButtonsListCtrl.GetFirstSelected()
        commandSelection = self.deviceCommandsListCtrl.GetFirstSelected()
        if (buttonSelection == -1) or (commandSelection == -1):
            wx.MessageBox('Please select a button and command to assign.',
                          'No selection(s) made.', wx.OK | wx.ICON_WARNING)
            return
        button = self.remoteButtons[buttonSelection]
        command = self.deviceCommands[commandSelection]
        BackgroundTask((self.DoUpdate, button, command), (self.LoadDataUI,))

    def DoUpdate(self, button, command):
        if self.buttonMapType == "Compiled":
            mhMgr.UpdateButtonMap(self.buttonMap, button, command)
        elif self.buttonMapType == "ActivityCompiled":
            mhMgr.UpdateUserButtonMap(self.buttonMap, button, command)
        self.LoadData()

    def OnOverride(self, event):
        commandSelection = self.deviceCommandsListCtrl.GetFirstSelected()
        if commandSelection == -1:
            wx.MessageBox('Please select a command to override.',
                          'No command selected.', wx.OK | wx.ICON_WARNING)
            return
        command = self.deviceCommands[commandSelection].Name
        self.UpdateIR(command)

    def OnAdd(self, event):
        dlg = wx.TextEntryDialog(None, "Enter the name of the new command:",
                                 "Add Command")
        if dlg.ShowModal() != wx.ID_OK:
            return
        command = dlg.GetValue()
        self.UpdateIR(command)

    def OnRestore(self, event):
        commandSelection = self.deviceCommandsListCtrl.GetFirstSelected()
        if commandSelection == -1:
            wx.MessageBox('Please select a command to restore.',
                          'No command selected.', wx.OK | wx.ICON_WARNING)
            return
        command = self.deviceCommands[commandSelection]
        if command.IsLearned != "true":
            wx.MessageBox('Selected command is not a learned command.',
                          'Error', wx.OK | wx.ICON_WARNING)
            return
        BackgroundTask((self.DoRestore, command), (self.FinishRestore,))

    def DoRestore(self, command):
        result = mhMgr.DeleteIRCommand(command.Id, self.deviceId)
        self.LoadData()
        return result

    def FinishRestore(self, result):
        if result is not None:
            wx.MessageBox('IR command deletion failed: ' + result, 'Error',
                          wx.OK | wx.ICON_WARNING)
        self.LoadDataUI(None)

    def UpdateIR(self, commandName):
        msg = 'Please ensure your remote control is connected.'
        wx.MessageBox(msg, 'Connect Remote', wx.OK)
        try:
            libconcord.init_concord()
        except:
            msg = '%s\n    (libconcord function %s error %d)\n\n' % (
                sys.exc_info()[1].result_str,
                sys.exc_info()[1].func,
                sys.exc_info()[1].result
            )
            wx.MessageBox('Could not detect remote: ' + msg, 'Error',
                          wx.OK | wx.ICON_WARNING)
            return

        msg = 'Please place your two remotes 3 inches (8 cm) apart.  After ' \
            + 'pressing OK, press the button on your non-Harmony remote that ' \
            + 'you wish to be learned.'
        wx.MessageBox(msg, 'Position Remotes', wx.OK)
        self.commandName = commandName
        self.carrierClock = ctypes.c_uint()
        self.signal = ctypes.POINTER(ctypes.c_uint)()
        self.signalLength = ctypes.c_uint()
        BackgroundTask((self.DoLearnIR,), (self.FinishLearnIR,), 
                       throbberTitle=ThrobberDialog.TITLE_REMOTE)

    def DoLearnIR(self):
        msg = None
        try:
            libconcord.learn_from_remote(
                ctypes.byref(self.carrierClock),
                ctypes.byref(self.signal),
                ctypes.byref(self.signalLength),
                libconcord.callback_type(dummy_callback_imp),
                None
            )
        except:
            msg = '%s\n    (libconcord function %s error %d)\n\n' % (
                sys.exc_info()[1].result_str,
                sys.exc_info()[1].func,
                sys.exc_info()[1].result
            )
            libconcord.deinit_concord()

    def FinishLearnIR(self, msg):
        if msg is not None:
            wx.MessageBox('IR learning failed: ' + msg + '\nPerhaps you did '
                          + 'not press a key?', 'Error',
                          wx.OK | wx.ICON_WARNING)
            return

        self.rawSequence = ctypes.c_char_p()
        libconcord.encode_for_posting(self.carrierClock, self.signal,
                                      self.signalLength, self.rawSequence)
        BackgroundTask((self.DoUpdateIR,), (self.FinishUpdateIR,))

    def DoUpdateIR(self):
        result = mhMgr.UpdateIRCommand(self.commandName,
                                       self.rawSequence.value.decode('utf-8'),
                                       self.deviceId)
        self.LoadData()
        return result

    def FinishUpdateIR(self, result):
        if result is not None:
            wx.MessageBox('IR learning update failed: ' + result, 'Error',
                          wx.OK | wx.ICON_WARNING)
        self.LoadDataUI(None)
        libconcord.delete_ir_signal(self.signal)
        libconcord.delete_encoded_signal(self.rawSequence)
        libconcord.deinit_concord()

    def GetTitle(self):
        return "Device Configuration"

    def IsCancelInitiallyDisabled(self):
        return False

    def OnNext(self):
        pass

    def GetNext(self):
        return (self.next, None)

    def GetBack(self):
        return (self.resources.page_remote_configuration, None)

class FavoriteChannelsPanel(WizardPanelBase):
    _msg_welcome = (
        "Please select a favorite channel button to modify on the left.\n" +
        "Then, type the channel on the right as you would enter it on your " +
        "remote.\n"
        + "If there is an existing channel assigned to a button, it\n"
        + "will be displayed when you select the favorite control button."
    )

    def __init__(self, parent, resources):
        WizardPanelBase.__init__(self, parent, resources)

        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.textMessage = WrappedStaticText(self)
        self.sizer.Add(self.textMessage, 0, ALIGN_XTA, 5)

        self.hSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.leftSizer = wx.BoxSizer(wx.VERTICAL)
        self.remoteButtonsLabel = wx.StaticText(self, -1, "Buttons:")
        self.leftSizer.Add(self.remoteButtonsLabel, 0, 0, 0)
        self.remoteButtonsListBox = wx.ListBox(self, style=wx.LB_SINGLE)
        self.remoteButtonsListBox.Bind(wx.EVT_LISTBOX,
                                       self.OnRemoteButtonSelection)
        self.leftSizer.Add(self.remoteButtonsListBox, 0, 0, 0)
        self.hSizer.Add(self.leftSizer, 0, 0, 0)
        self.hSizer.AddSpacer(20)
        self.rightSizer = wx.BoxSizer(wx.VERTICAL)
        self.channelLabel = wx.StaticText(self, -1, "Channel:")
        self.rightSizer.Add(self.channelLabel, 0, 0, 0)
        self.channelCtrl = wx.TextCtrl(self, -1, "")
        self.channelCtrl.SetMinSize((70, 31))
        self.rightSizer.Add(self.channelCtrl, 0, 0, 0)
        self.hSizer.Add(self.rightSizer, 0, 0, 0)
        self.sizer.Add(self.hSizer, 0, 0, 0)
        self.sizer.AddSpacer(20)

        self.updateButton = wx.Button(self, label="Update Button")
        self.updateButton.Bind(wx.EVT_BUTTON, self.OnUpdate)
        self.updateButton.SetToolTip(wx.ToolTip(
                "Save selected button assignment"
        ))
        self.sizer.Add(self.updateButton, 0, 0, 0)

        self.SetSizerAndFit(self.sizer)

        self.next = None

    def OnActivated(self, prev_page, data):
        self.textMessage.UpdateText(self._msg_welcome)
        self.parent.ReenableBack()
        self.skinId, self.deviceId, self.deviceName = data
        self.parent.title.SetLabel(self.deviceName)
        BackgroundTask((self.LoadData,), (self.LoadDataUI,), False)
        return (None, None)

    def LoadData(self):
        self.remoteButtons = mhMgr.GetProductButtonList(self.skinId)
        self.buttonMap = mhMgr.GetButtonMap(self.deviceId)

    def LoadDataUI(self, loadDataResult):
        self.remoteButtonsList = []
        if self.remoteButtons is not None:
            for button in self.remoteButtons:
                if button.ButtonType == "FavoriteChannelButton":
                    self.remoteButtonsList.append(button.ButtonKey)
            self.remoteButtonsListBox.Set(self.remoteButtonsList)
        self.Fit()
        self.parent.Show()

    def OnRemoteButtonSelection(self, event):
        key = self.remoteButtons[self.remoteButtonsListBox.GetSelection()] \
            .ButtonKey
        foundCommand = self.FindCommand(key)
        if foundCommand is not None:
            # ButtonAssignment might not be a ChannelButtonAssignment, but
            # ignore the error if it isn't.
            try:
                self.channelCtrl.SetValue(foundCommand.ButtonAssignment.Channel)
                return
            except AttributeError:
                pass
        self.channelCtrl.Clear()

    def FindCommand(self, buttonKey):
        for button in self.buttonMap.Buttons.AbstractButton:
            if buttonKey == button.ButtonKey:
                return button
        return None

    def OnUpdate(self, event):
        buttonSelection = self.remoteButtonsListBox.GetSelection()
        channel = self.channelCtrl.GetValue()
        if (buttonSelection == -1) or (not channel.isdigit()):
            wx.MessageBox('Please select a button and channel to assign.',
                          'No selection(s) made.', wx.OK | wx.ICON_WARNING)
            return
        button = self.remoteButtons[buttonSelection]
        BackgroundTask((self.DoUpdate, button, channel), (self.LoadDataUI,))

    def DoUpdate(self, button, channel):
        mhMgr.UpdateButtonMap(self.buttonMap, button, channel,
                              isChannelButton = True)
        self.LoadData()

    def GetTitle(self):
        return "Favorite Channels"

    def IsCancelInitiallyDisabled(self):
        return False

    def OnNext(self):
        pass

    def GetNext(self):
        return (self.next, None)

    def GetBack(self):
        return (self.resources.page_remote_configuration, None)

class SetupWatchTVPanel(WizardPanelBase):
    _msg_welcome = (
        "Please select the devices to be turned on when you press the\n" +
        "Watch TV button.  Then, select the proper input for each device, if " +
        "applicable.  Re-order the devices to change the power-on order.\n"
    )

    def __init__(self, parent, resources):
        WizardPanelBase.__init__(self, parent, resources)

        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.textMessage = WrappedStaticText(self)
        self.sizer.Add(self.textMessage, 0, ALIGN_XTA, 5)

        self.listBoxLabel = wx.StaticText(self, -1, "Selected Devices:" +
                                          "\t\t\t  Unselected Devices:")
        self.sizer.Add(self.listBoxLabel)

        self.buttonSize = (40, 40)
        self.listBoxSize = (160, 160)
        self.deviceSelectionSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.selectedDevicesListBox = wx.ListBox(self, style=wx.LB_SINGLE,
                                                 size=self.listBoxSize)
        self.deviceSelectionSizer.Add(self.selectedDevicesListBox)
        self.deviceSelectionButtonSizer = wx.BoxSizer(wx.VERTICAL)
        self.selectDeviceButton = wx.Button(self, label=u'\u2190',
                                            size=self.buttonSize)
        self.selectDeviceButton.SetToolTip(wx.ToolTip(
                "Add device to Watch TV configuration"
        ))
        self.selectDeviceButton.Bind(wx.EVT_BUTTON, self.OnSelect)
        self.deviceSelectionButtonSizer.Add(self.selectDeviceButton)
        self.removeDeviceButton = wx.Button(self, label=u'\u2192',
                                            size=self.buttonSize)
        self.removeDeviceButton.SetToolTip(wx.ToolTip(
                "Remove device from Watch TV configuration"
        ))
        self.removeDeviceButton.Bind(wx.EVT_BUTTON, self.OnRemove)
        self.deviceSelectionButtonSizer.Add(self.removeDeviceButton)
        self.raiseDeviceButton = wx.Button(self, label=u'\u2191',
                                           size=self.buttonSize)
        self.raiseDeviceButton.SetToolTip(wx.ToolTip(
                "Move device earlier in power-on order"
        ))
        self.raiseDeviceButton.Bind(wx.EVT_BUTTON, self.OnRaise)
        self.deviceSelectionButtonSizer.Add(self.raiseDeviceButton)
        self.lowerDeviceButton = wx.Button(self, label=u'\u2193',
                                           size=self.buttonSize)
        self.lowerDeviceButton.SetToolTip(wx.ToolTip(
                "Move device later in power-on order"
        ))
        self.lowerDeviceButton.Bind(wx.EVT_BUTTON, self.OnLower)
        self.deviceSelectionButtonSizer.Add(self.lowerDeviceButton)
        self.deviceSelectionSizer.Add(self.deviceSelectionButtonSizer)
        self.unselectedDevicesListBox = wx.ListBox(self, style=wx.LB_SINGLE,
                                                   size=self.listBoxSize)
        self.deviceSelectionSizer.Add(self.unselectedDevicesListBox)
        self.sizer.Add(self.deviceSelectionSizer)

        # Placeholder sizer for input selection widgets
        self.inputSelectionSizer = wx.BoxSizer(wx.VERTICAL)
        self.sizer.Add(self.inputSelectionSizer)

        self.saveChangesButton = wx.Button(self, label="Save Changes")
        self.saveChangesButton.Bind(wx.EVT_BUTTON, self.OnSave)
        self.sizer.Add(self.saveChangesButton)

        self.SetSizerAndFit(self.sizer)

        self.next = None

    def FindRole(self, device, activity):
        if activity:
            for role in activity.Roles.AbstractActivityRole:
                if role.DeviceId.Value == device.Id.Value and \
                        role.DeviceId.IsPersisted == device.Id.IsPersisted:
                    return role
        return None

    def GetDevice(self, role):
        for device in self.devices:
            if device.Id.Value == role.DeviceId.Value:
                return (device.Name, device.Id)

    def LoadData(self):
        self.devices = mhMgr.GetDevices(self.remote.Id)
        self.activity = mhMgr.GetWatchTVActivity(self.remote.Id)
        self.inputNames = {}
        for device in self.devices:
            self.inputNames[device.Id] = mhMgr.GetDeviceInputNames(device.Id)

    def LoadDataUI(self, loadDataResult):
        self.selectedDevicesListBox.Clear()
        self.unselectedDevicesListBox.Clear()
        self.inputSelectionSizer.Clear(True)
        self.inputSelectionWidgets = {}

        # Add devices from the roles first since they need to be added in role
        # order
        if self.activity:
            for role in self.activity.Roles.AbstractActivityRole:
                deviceName, deviceId = self.GetDevice(role)
                self.selectedDevicesListBox.Append(deviceName, deviceId)

        # Now add the other devices.
        for device in self.devices:
            role = self.FindRole(device, self.activity)
            if not role:
                self.unselectedDevicesListBox.Append(device.Name, device.Id)
            inputNames = self.inputNames[device.Id]
            if inputNames:
                # Allow input to be set to 'None'
                inputNames.append('None')
                label = wx.StaticText(self, -1, "Input for " + device.Name
                                      + ":")
                choice = wx.Choice(self, -1, choices=inputNames)
                try:
                    choice.SetSelection(choice.FindString(
                            role.SelectedInput.Name))
                except:
                    choice.SetSelection(choice.FindString('None'))
                sizer = wx.BoxSizer(wx.HORIZONTAL)
                sizer.Add(label, flag=wx.ALIGN_CENTER_VERTICAL)
                sizer.Add(choice)
                self.inputSelectionSizer.Add(sizer)
                self.inputSelectionWidgets[device.Id] = choice
        self.Layout()
        self.parent.Show()

    def OnActivated(self, prev_page, remote):
        self.textMessage.UpdateText(self._msg_welcome)
        self.parent.ReenableBack()
        self.remote = remote
        BackgroundTask((self.LoadData,), (self.LoadDataUI,), False)
        return (None, None)

    def OnSelect(self, event):
        selection = self.unselectedDevicesListBox.GetSelection()
        if selection != wx.NOT_FOUND:
            self.selectedDevicesListBox.Append(
                self.unselectedDevicesListBox.GetStringSelection(),
                self.unselectedDevicesListBox.GetClientData(selection))
            self.unselectedDevicesListBox.Delete(selection)

    def OnRemove(self, event):
        selection = self.selectedDevicesListBox.GetSelection()
        if selection != wx.NOT_FOUND:
            self.unselectedDevicesListBox.Append(
                self.selectedDevicesListBox.GetStringSelection(),
                self.selectedDevicesListBox.GetClientData(selection))
            self.selectedDevicesListBox.Delete(selection)

    def OnRaise(self, event):
        selection = self.selectedDevicesListBox.GetSelection()
        if selection != wx.NOT_FOUND and selection != 0:
            selectionString = self.selectedDevicesListBox.GetStringSelection()
            clientData = self.selectedDevicesListBox.GetClientData(selection)
            self.selectedDevicesListBox.Delete(selection)
            self.selectedDevicesListBox.Insert(selectionString, selection - 1,
                                               clientData)
            self.selectedDevicesListBox.SetSelection(selection - 1)

    def OnLower(self, event):
        selection = self.selectedDevicesListBox.GetSelection()
        lastItem = self.selectedDevicesListBox.GetCount() - 1
        if selection != wx.NOT_FOUND and selection != lastItem:
            selectionString = self.selectedDevicesListBox.GetStringSelection()
            clientData = self.selectedDevicesListBox.GetClientData(selection)
            self.selectedDevicesListBox.Delete(selection)
            self.selectedDevicesListBox.Insert(selectionString, selection + 1,
                                               clientData)
            self.selectedDevicesListBox.SetSelection(selection + 1)

    def OnSave(self, event):
        if self.selectedDevicesListBox.GetCount() == 0:
            if self.activity is not None:
                BackgroundTask((self.DoDelete,), (self.LoadDataUI,))
        else:
            deviceInfo = []
            for index in range(self.selectedDevicesListBox.GetCount()):
                deviceId = self.selectedDevicesListBox.GetClientData(index)
                try:
                    inputName = self.inputSelectionWidgets[deviceId].\
                        GetStringSelection()
                    if inputName == 'None':
                        inputName = None
                except KeyError:
                    inputName = None
                deviceInfo.append((deviceId, inputName))
            BackgroundTask((self.DoSave, deviceInfo), (self.LoadDataUI,))

    def DoDelete(self):
        mhMgr.DeleteActivity(self.activity)
        self.LoadData()

    def DoSave(self, deviceInfo):
        mhMgr.SaveWatchTVActivity(self.remote.Id, deviceInfo, self.activity)
        self.LoadData()

    def GetTitle(self):
        return "Setup Watch TV Button"

    def IsCancelInitiallyDisabled(self):
        return False

    def OnNext(self):
        pass

    def GetNext(self):
        return (self.next, None)

    def GetBack(self):
        return (self.resources.page_remote_configuration, None)

class ConfigureHarmonyLinkSettingsPanel(WizardPanelBase):
    _msg_welcome = (
        "On this page, you can configure the Room and WiFi settings for\n" +
        "your Harmony Link.\n"
    )

    def __init__(self, parent, resources):
        self.roomNames = [ "", "Basement", "Bedroom", "Den", "Dorm",
                           "Family Room", "Hallway", "Kitchen", "Living Room",
                           "Media Room", "Office", "Rec Room" ]
        self.serviceLink = "https://svcs.myharmony.com/Discovery"
        self.encryptionTypes = [ "OPEN", "WEP", "WPA-PSK", "WPA2-PSK" ]
        self.labelSize = (133, 21)

        WizardPanelBase.__init__(self, parent, resources)

        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.textMessage = WrappedStaticText(self)
        self.sizer.Add(self.textMessage, 0, ALIGN_XTA, 5)

        self.roomNameSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.roomNameLabel = wx.StaticText(self, -1, "Room Name:")
        self.roomNameLabel.SetMinSize(self.labelSize)
        self.roomNameSizer.Add(self.roomNameLabel,
                               flag=wx.ALIGN_CENTER_VERTICAL)
        self.roomNameChoice = wx.Choice(self, -1, choices=self.roomNames)
        self.roomNameSizer.Add(self.roomNameChoice)
        self.sizer.Add(self.roomNameSizer)

        self.sizer.AddSpacer(25)

        self.wifiNetworksSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.wifiNetworksLabel = wx.StaticText(self, -1, "Available Networks:")
        self.wifiNetworksSizer.Add(self.wifiNetworksLabel,
                                   flag=wx.ALIGN_CENTER_VERTICAL)
        self.wifiNetworksListBox = wx.ListBox(self, style=wx.LB_SINGLE,
                                         size=(200, 62))
        self.wifiNetworksListBox.Bind(wx.EVT_LISTBOX, self.OnSelectNetwork)
        self.wifiNetworksSizer.Add(self.wifiNetworksListBox)
        self.sizer.Add(self.wifiNetworksSizer)

        self.ssidSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.ssidLabel = wx.StaticText(self, -1, "SSID:")
        self.ssidLabel.SetMinSize(self.labelSize)
        self.ssidSizer.Add(self.ssidLabel, flag=wx.ALIGN_CENTER_VERTICAL)
        self.ssidCtrl = wx.TextCtrl(self, -1, "")
        self.ssidCtrl.SetMinSize((200, 31))
        self.ssidSizer.Add(self.ssidCtrl)
        self.sizer.Add(self.ssidSizer)

        self.passwordSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.passwordLabel = wx.StaticText(self, -1, "Password:")
        self.passwordLabel.SetMinSize(self.labelSize)
        self.passwordSizer.Add(self.passwordLabel,
                               flag=wx.ALIGN_CENTER_VERTICAL)
        self.passwordCtrl = wx.TextCtrl(self, -1, "")
        self.passwordCtrl.SetMinSize((200, 31))
        self.passwordSizer.Add(self.passwordCtrl)
        self.sizer.Add(self.passwordSizer)

        self.encryptionSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.encryptionLabel = wx.StaticText(self, -1, "Encryption:")
        self.encryptionLabel.SetMinSize(self.labelSize)
        self.encryptionSizer.Add(self.encryptionLabel,
                                 flag=wx.ALIGN_CENTER_VERTICAL)
        self.encryptionChoice = wx.Choice(self, -1,
                                          choices=self.encryptionTypes)
        self.encryptionSizer.Add(self.encryptionChoice)
        self.sizer.Add(self.encryptionSizer)

        self.wifiStatusSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.wifiStatusLabel = wx.StaticText(self, -1, "WiFi Status:")
        self.wifiStatusLabel.SetMinSize(self.labelSize)
        self.wifiStatusSizer.Add(self.wifiStatusLabel,
                                 flag = wx.ALIGN_CENTER_VERTICAL)
        self.wifiStatusCtrl = wx.TextCtrl(self, -1, "")
        self.wifiStatusCtrl.SetEditable(False)
        self.wifiStatusCtrl.SetMinSize((300, 31))
        self.wifiStatusSizer.Add(self.wifiStatusCtrl)
        self.sizer.Add(self.wifiStatusSizer)

        self.sizer.AddSpacer(25)

        self.saveChangesButton = wx.Button(self, label="Save Changes")
        self.saveChangesButton.Bind(wx.EVT_BUTTON, self.OnSaveChanges)
        self.sizer.Add(self.saveChangesButton)

        self.SetSizerAndFit(self.sizer)

        self.next = None

    def OnActivated(self, prev_page, data):
        self.textMessage.UpdateText(self._msg_welcome)
        self.parent.ReenableBack()
        self.remote = data
        BackgroundTask((self.LoadData,), (self.LoadDataUI,), 
                       throbberTitle=ThrobberDialog.TITLE_REMOTE)
        return (None, None)

    def LoadData(self):
        try:
            libconcord.init_concord()
        except:
            msg = '%s\n    (libconcord function %s error %d)\n\n' % (
                sys.exc_info()[1].result_str,
                sys.exc_info()[1].func,
                sys.exc_info()[1].result
            )
            return msg

        # We don't really care about the identity, but for the Harmony Link,
        # this seems to be the more reliable way of starting off a conversation
        # with it.
        try:
            libconcord.get_identity(dummy_cb, None)
        except:
            # If get_identity fails, try again.  The Harmony Link seems to have
            # a weird bug where it will fail once, but if you try again, it
            # will succeed.
            libconcord.get_identity(dummy_cb, None)

        self.LoadConfigProperties()
        self.LoadWifiConfig()
        self.LoadWifiNetworks()
        return None

    def LoadDataUI(self, msg):
        if msg is not None:
            wx.MessageBox('Could not detect Harmony Link: ' + msg, 'Error',
                          wx.OK | wx.ICON_WARNING)
            self.parent._SetPage(self.resources.page_remote_configuration, None)
            return
        self.LoadConfigPropertiesUI(None)
        self.LoadWifiConfigUI(None)
        self.LoadWifiNetworksUI(None)

    def LoadConfigProperties(self):
        self.remoteName = mhMgr.GetRemoteName(self.remote.Id)
        cfg_prop = libconcord.mh_cfg_properties()
        libconcord.mh_get_cfg_properties(ctypes.byref(cfg_prop))
        self.cfg_prop = self.DecodeMHStruct(cfg_prop)

    def LoadConfigPropertiesUI(self, result):
        if self.remoteName is None:
            choiceItem = wx.NOT_FOUND
        else:
            choiceItem = self.roomNameChoice.FindString(self.remoteName)
        if choiceItem != wx.NOT_FOUND:
            self.roomNameChoice.SetSelection(choiceItem)
        else:
            self.roomNameChoice.SetSelection(0)

    def LoadWifiConfig(self):
        wifi_cfg = libconcord.mh_wifi_config()
        libconcord.mh_get_wifi_config(ctypes.byref(wifi_cfg))
        self.wifi_cfg = self.DecodeMHStruct(wifi_cfg)

    def LoadWifiConfigUI(self, result):
        self.ssidCtrl.SetValue(self.wifi_cfg.ssid)
        self.passwordCtrl.SetValue(self.wifi_cfg.password)
        encNum = self.encryptionChoice.FindString(self.wifi_cfg.encryption)
        if encNum != wx.NOT_FOUND:
            self.encryptionChoice.SetSelection(encNum)
        else:
            self.encryptionChoice.SetSelection(0)
        if self.wifi_cfg.connect_status == "connected":
            self.wifiStatusCtrl.SetValue("connected")
        else:
            self.wifiStatusCtrl.SetValue(self.wifi_cfg.connect_status + ": " +
                                         self.wifi_cfg.error_code)

    def LoadWifiNetworks(self):
        self.wifi_networks = libconcord.mh_wifi_networks()
        libconcord.mh_get_wifi_networks(ctypes.byref(self.wifi_networks))

    def LoadWifiNetworksUI(self, result):
        self.wifiNetworksListBox.DeselectAll()
        self.wifiNetworksListBox.Clear()
        for network in self.wifi_networks.network:
            network = self.DecodeMHStruct(network)
            if network.ssid == "":
                break
            self.wifiNetworksListBox.Append(network.ssid, network.encryption)

    def OnSelectNetwork(self, event):
        self.ssidCtrl.SetValue(self.wifiNetworksListBox.GetStringSelection())
        self.passwordCtrl.Clear()
        self.encryptionChoice.SetSelection(
            self.encryptionChoice.FindString(
                self.wifiNetworksListBox.GetClientData(
                    self.wifiNetworksListBox.GetSelection()
                    )
                )
            )

    def OnSaveChanges(self, event):
        # Validate Selections
        if self.roomNameChoice.GetSelection() == 0:
            wx.MessageBox('Please select a room name', 'Error',
                          wx.OK | wx.ICON_WARNING)
            return
        if self.ssidCtrl.IsEmpty():
            wx.MessageBox('Please enter an SSID', 'Error',
                          wx.OK | wx.ICON_WARNING)
            return

        # Determine which item(s) needs to be saved
        self.saveCfgProp = False
        roomName = self.roomNameChoice.GetStringSelection()
        if self.cfg_prop.host_name != roomName or self.cfg_prop.email != \
                mhMgr.email or self.remoteName != roomName:
            self.saveCfgProp = True
        self.saveWifi = False
        ssid = self.ssidCtrl.GetValue()
        password = self.passwordCtrl.GetValue()
        encryption = self.encryptionChoice.GetStringSelection()
        if encryption == "OPEN":
            encryption = ""
        if self.wifi_cfg.ssid != ssid or self.wifi_cfg.password != password or \
                self.wifi_cfg.encryption != encryption:
            self.saveWifi = True

        # Save what needs to be saved
        if self.saveWifi:
            self.wifi_cfg.ssid = ssid
            self.wifi_cfg.encryption = encryption
            self.wifi_cfg.password = password
        if self.saveCfgProp:
            self.cfg_prop.host_name = roomName
            self.cfg_prop.email = mhMgr.email
            self.cfg_prop.service_link = self.serviceLink
        if self.saveWifi or self.saveCfgProp:
            BackgroundTask((self.DoSaveChanges,), (self.FinishSaveChanges,), 
                           throbberTitle=ThrobberDialog.TITLE_REMOTE)

    def DoSaveChanges(self):
        if self.saveWifi:
            wifi_cfg = self.EncodeMHStruct(self.wifi_cfg,
                                           libconcord.mh_wifi_config())
            libconcord.mh_set_wifi_config(ctypes.byref(wifi_cfg))
            self.LoadWifiConfig()
        if self.saveCfgProp:
            mhMgr.SetRemoteName(self.remote.Id, self.cfg_prop.host_name)
            cfg_prop = self.EncodeMHStruct(self.cfg_prop,
                                           libconcord.mh_cfg_properties())
            libconcord.mh_set_cfg_properties(ctypes.byref(cfg_prop))
            time.sleep(10)
            # Do not self.LoadConfigProperties() here.  The Link doesn't
            # respond very well if you do.  Just assume everything worked.

    def FinishSaveChanges(self, result):
        if self.saveWifi:
            self.LoadWifiConfigUI(None)

    def DecodeMHStruct(self, encoded):
        class Object: pass
        decoded = Object()
        for field in encoded._fields_:
            setattr(decoded, field[0],
                    getattr(encoded, field[0]).decode('utf-8'))
        return decoded

    def EncodeMHStruct(self, decoded, encoded):
        for prop, val in vars(decoded).items():
            setattr(encoded, prop, val.encode('utf-8'))
        return encoded

    def GetTitle(self):
        return "Configure Harmony Link Settings"

    def IsCancelInitiallyDisabled(self):
        return False

    def OnNext(self):
        pass

    def GetNext(self):
        return (self.next, None)

    def GetBack(self):
        libconcord.deinit_concord()
        return (self.resources.page_remote_configuration, None)

    def OnCancel(self):
        libconcord.deinit_concord()
        self.parent.OnExit(0)

class SetupActivitiesPanel(WizardPanelBase):
    _msg_welcome = (
        "Existing Activities:"
    )

    def __init__(self, parent, resources):
        WizardPanelBase.__init__(self, parent, resources)

        self.buttonSize = (127, 33)

        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.textMessage = WrappedStaticText(self)
        self.sizer.Add(self.textMessage, 0, ALIGN_XTA, 5)
        self.activitiesListBox = wx.ListBox(self, style=wx.LB_SINGLE,
                                            size=(200, 100))
        self.sizer.Add(self.activitiesListBox)
        self.sizer.AddSpacer(20)
        self.addButton = wx.Button(self, label="Add Activity",
                                   size=self.buttonSize)
        self.addButton.Bind(wx.EVT_BUTTON, self.OnAddActivity)
        self.sizer.Add(self.addButton)
        self.sizer.AddSpacer(10)
        self.editButton = wx.Button(self, label="Edit Activity",
                                    size=self.buttonSize)
        self.editButton.Bind(wx.EVT_BUTTON, self.OnEditActivity)
        self.sizer.Add(self.editButton)
        self.sizer.AddSpacer(10)
        self.deleteButton = wx.Button(self, label="Delete Activity",
                                      size=self.buttonSize)
        self.deleteButton.Bind(wx.EVT_BUTTON, self.OnDeleteActivity)
        self.sizer.Add(self.deleteButton)
        self.SetSizerAndFit(self.sizer)

        self.next = None

    def OnActivated(self, prev_page, data):
        self.textMessage.UpdateText(self._msg_welcome)
        self.parent.ReenableBack()
        if data is not None:
            self.remote = data
            BackgroundTask((self.LoadData,), (self.LoadDataUI,), False)
        return (None, None)

    def LoadData(self):
        self.activities = mhMgr.GetActivities(self.remote.Id)
        self.recommendedActivities = mhMgr.GetRecommendedActivities(
            self.remote.Id)

    def LoadDataUI(self, loadDataResult):
        self.activitiesListBox.Clear()
        if self.activities:
            for activity in self.activities:
                self.activitiesListBox.Append(activity.Name, activity)
        self.parent.Show()

    def OnAddActivity(self, event):
        activityTypeStrings = []
        for activity in self.recommendedActivities:
            activityTypeStrings.append(mhMgr.GetActivityTypeString(activity))
        dlg = wx.SingleChoiceDialog(
            self.parent,
            "Please select an activity type to add:",
            "Activity Selection",
            activityTypeStrings
        )
        if dlg.ShowModal() != wx.ID_OK:
            return
        activityType = self.recommendedActivities[dlg.GetSelection()]
        params = (self.remote, activityType, None)
        self.parent._SetPage(self.resources.page_edit_activity, params, True)

    def OnEditActivity(self, event):
        activity = self.GetSelectedActivity()
        if not activity:
            return
        params = (self.remote, activity.Type, activity)
        self.parent._SetPage(self.resources.page_edit_activity, params, True)

    def OnDeleteActivity(self, event):
        activity = self.GetSelectedActivity()
        if not activity:
            return
        BackgroundTask((self.DoDelete, activity), (self.LoadDataUI,))

    def GetSelectedActivity(self):
        activityNum = self.activitiesListBox.GetSelection()
        if activityNum == wx.NOT_FOUND:
            wx.MessageBox('Please select an activity', 'Error',
                          wx.OK | wx.ICON_WARNING)
            return None
        return self.activitiesListBox.GetClientData(activityNum)

    def DoDelete(self, activity):
        mhMgr.DeleteActivity(activity)
        self.activities = mhMgr.GetActivities(self.remote.Id)

    def GetTitle(self):
        return "Activity Setup"

    def IsCancelInitiallyDisabled(self):
        return False

    def GetNext(self):
        return (self.next, None)

    def GetBack(self):
        return (self.resources.page_remote_configuration, None)

class EditActivityPanel(WizardPanelBase):
    def __init__(self, parent, resources):
        WizardPanelBase.__init__(self, parent, resources)

        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizerAndFit(self.sizer)

        self.next = None

    def OnActivated(self, prev_page, data):
        self.parent.ReenableBack()
        self.remote, self.activityType, self.activity = data
        BackgroundTask((self.LoadData,), (self.LoadDataUI,), False)
        return (None, None)

    def LoadData(self):
        if self.activity:
            self.activityNameDefault = self.activity.Name
        else:
            self.activityNameDefault = mhMgr.GetActivityTypeString(
                self.activityType)
        self.activityTemplate = mhMgr.GetActivityTemplate(self.remote.Id,
                                                          self.activityType)

    def LoadDataUI(self, loadDataResult):
        self.sizer.Clear(True)

        self.activityNameSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.activityNameLabel = wx.StaticText(self, -1, "Activity Name:")
        self.activityNameSizer.Add(self.activityNameLabel,
                                   flag=wx.ALIGN_CENTER_VERTICAL)
        self.activityNameCtrl = wx.TextCtrl(self, -1, self.activityNameDefault)
        self.activityNameCtrl.SetMinSize((150, 31))
        if self.remote.SkinId == HARMONY_350_SKIN_ID:
            self.activityNameCtrl.Disable()
        self.activityNameSizer.Add(self.activityNameCtrl)
        self.sizer.Add(self.activityNameSizer)
        self.sizer.AddSpacer(10)

        self.roles = []
        self.roleChoices = {}
        for role in self.activityTemplate.roles:
            roleType, devices = role
            self.roles.append(roleType)
            if roleType == "DisplayActivityRole": # Don't add widget for Display
                self.displayDeviceId = devices[0][1]
                continue
            if roleType == "PassThroughActivityRole":
                continue
            roleString = mhMgr.GetRoleString(roleType)
            label = "What device do you use to " + roleString + "?"
            labelText = wx.StaticText(self, -1, label)
            self.sizer.Add(labelText)
            choice = wx.Choice(self, -1)
            self.sizer.Add(choice)
            self.sizer.AddSpacer(10)
            self.roleChoices[roleType] = choice
            for deviceName, deviceId in devices:
                choice.Append(deviceName, deviceId)
            choice.SetSelection(0)
            if self.activity:
                device = mhMgr.GetRoleDeviceId(self.activity, roleType)
                for i in range(choice.GetCount()):
                    if choice.GetClientData(i).Value == device.Value:
                        choice.SetSelection(i)

        self.inputSelectionChoices = {}
        self.deviceIdsWithInputs = []
        for deviceName, deviceId, inputs in \
            self.activityTemplate.devicesWithInputs:
            self.deviceIdsWithInputs.append(deviceId)
            # Allow input to be set to 'None'
            inputs.append('None')
            label = "What input should " + deviceName + " be set to?"
            inputSelectionLabel = wx.StaticText(self, -1, label)
            self.sizer.Add(inputSelectionLabel)
            inputSelectionChoice = wx.Choice(self, -1, choices=inputs)
            self.sizer.Add(inputSelectionChoice)
            self.inputSelectionChoices[deviceId.Value] = inputSelectionChoice
            self.sizer.AddSpacer(10)
            if self.activity:
                input = mhMgr.GetDeviceInput(self.activity, deviceId)
                if input:
                    inputNum = inputSelectionChoice.FindString(input)
                else:
                    inputNum = inputSelectionChoice.FindString('None')
                inputSelectionChoice.SetSelection(inputNum)

        self.sizer.AddSpacer(20)
        self.saveChangesButton = wx.Button(self, label="Save Changes")
        self.saveChangesButton.Bind(wx.EVT_BUTTON, self.OnSaveChanges)
        self.sizer.Add(self.saveChangesButton)
        self.Layout()
        self.parent.Show()

    def OnSaveChanges(self, event):
        if self.activityNameCtrl.IsEmpty():
            wx.MessageBox('Please enter an activity name', 'Error',
                          wx.OK | wx.ICON_WARNING)
            return

        template = SaveActivityTemplate()
        template.activityName = self.activityNameCtrl.GetValue()
        template.activityType = self.activityType
        template.roles = []

        hasPassThroughRole = False
        assignedDeviceIds = []

        for role in self.roles:
            if role == "PassThroughActivityRole":
                hasPassThroughRole = True
                continue
            if role == "DisplayActivityRole":
                deviceId = self.displayDeviceId
            else:
                deviceNum = self.roleChoices[role].GetSelection()
                deviceId = self.roleChoices[role].GetClientData(deviceNum)
            try:
                inputChoice = self.inputSelectionChoices[deviceId.Value]
                inputName = inputChoice.GetStringSelection()
                if inputName == 'None':
                    inputName = ''
            except KeyError:
                inputName = None
            template.roles.append((role, deviceId, inputName))
            assignedDeviceIds.append(deviceId.Value)

        # PassThroughActivityRole handling: if there's a device with an input
        # assigned, but is not in a role, assign it a PassThrough role.
        if hasPassThroughRole:
            for deviceId in self.deviceIdsWithInputs:
                if deviceId.Value not in assignedDeviceIds:
                    inputChoice = self.inputSelectionChoices[deviceId.Value]
                    inputName = inputChoice.GetStringSelection()
                    if inputName != 'None':
                        template.roles.append(("PassThroughActivityRole",
                                               deviceId, inputName))

        self.parent.Hide()
        BackgroundTask((self.DoSave, template), (self.FinishSave,), False)

    def DoSave(self, template):
        mhMgr.SaveActivityByTemplate(self.remote.Id, template, self.activity)

    def FinishSave(self, saveResult):
        if self.remote.SkinId == HARMONY_350_SKIN_ID:
            self.parent._SetPage(self.resources.page_remote_configuration, None)
            self.parent.Show()
        else:
            self.parent._SetPage(self.resources.page_setup_activities,
                                 self.remote, True)

    def GetTitle(self):
        return "Edit Activity"

    def IsCancelInitiallyDisabled(self):
        return False

    def GetNext(self):
        return (self.next, None)

    def GetBack(self):
        if self.remote.SkinId == HARMONY_350_SKIN_ID:
            return (self.resources.page_remote_configuration, None)
        return (self.resources.page_setup_activities, None)

class AdjustPowerSettingsPanel(DevicePanelTemplate):
    _msg_welcome = (
        "On this page, you can adjust the commands that are sent when your " +
        "device\nis powered on and off."
    )

    def __init__(self, parent, resources):
        DevicePanelTemplate.__init__(self, parent, resources)

        self.buttonSize = (127, 33)

        self.buttonSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.addCommandButton = wx.Button(self, label="Add Command",
                                          size=self.buttonSize)
        self.addCommandButton.Bind(wx.EVT_BUTTON, self.OnAddCommand)
        self.buttonSizer.Add(self.addCommandButton)
        self.addDelayButton = wx.Button(self, label="Add Delay",
                                        size=self.buttonSize)
        self.addDelayButton.Bind(wx.EVT_BUTTON, self.OnAddDelay)
        self.buttonSizer.Add(self.addDelayButton)
        self.editCommandButton = wx.Button(self, label="Edit Command",
                                           size=self.buttonSize)
        self.editCommandButton.Bind(wx.EVT_BUTTON, self.OnEditCommand)
        self.buttonSizer.Add(self.editCommandButton)
        self.deleteCommandButton = wx.Button(self, label="Delete Command",
                                             size=self.buttonSize)
        self.deleteCommandButton.Bind(wx.EVT_BUTTON, self.OnDeleteCommand)
        self.buttonSizer.Add(self.deleteCommandButton)
        self.sizer.Add(self.buttonSizer)
        self.sizer.AddSpacer(10)

        self.commandGrid = wx.grid.Grid(self)
        self.commandGrid.CreateGrid(1, 2)
        self.commandGrid.EnableEditing(False)
        self.commandGrid.SetColLabelValue(0, "Command")
        self.commandGrid.SetColLabelValue(1, "Duration")
        self.commandGrid.SetSelectionMode(wx.grid.Grid.wxGridSelectRows)
        self.commandGrid.Bind(wx.grid.EVT_GRID_SELECT_CELL, self.OnSelectCell)
        self.sizer.Add(self.commandGrid)

        self.sizer.AddSpacer(10)
        self.saveButton = wx.Button(self, label="Save Changes",
                                    size=self.buttonSize)
        self.saveButton.Bind(wx.EVT_BUTTON, self.OnSaveChanges)
        self.sizer.Add(self.saveButton)

        self.SetSizerAndFit(self.sizer)

        self.next = None

    def OnActivated(self, prev_page, data):
        self.textMessage.UpdateText(self._msg_welcome)
        self.parent.ReenableBack()
        self.device = data
        self.deviceTitle.SetLabel(self.device.Name)
        BackgroundTask((self.LoadData,), (self.LoadDataUI,), False)
        return (None, None)

    def LoadData(self):
        self.powerFeature = mhMgr.GetPowerFeature(self.device.Id)
        self.deviceCommands = mhMgr.GetCommands(self.device.Id)

    def LoadDataUI(self, loadDataResult):
        self.deviceCommandsList = []
        if self.deviceCommands:
            for command in self.deviceCommands:
                self.deviceCommandsList.append(command.Name)
        if self.commandGrid.GetNumberRows() > 0:
            self.commandGrid.DeleteRows(0, self.commandGrid.GetNumberRows())

        self.actions = mhMgr.GetPowerFeatureActions(
            self.powerFeature.PowerToggleActions)
        if self.actions is None:
            self.actions = mhMgr.GetPowerFeatureActions(
                self.powerFeature.PowerOnActions)
            if self.actions is not None:
                self.actionType = "PowerOn"
        else:
            self.actionType = "PowerToggle"

        if self.actions:
            for action in self.actions:
                if action[0] == "IRPressAction":
                    rowNum = self.AddRow()
                    self.commandGrid.SetCellValue(rowNum, 0, action[1])
                    self.commandGrid.SetCellValue(rowNum, 1, action[2])
                elif action[0] == "IRDelayAction":
                    rowNum = self.AddRow()
                    self.commandGrid.SetCellValue(rowNum, 0, "Delay")
                    self.commandGrid.SetCellValue(rowNum, 1, action[2])
            self.commandGrid.AutoSize()
            self.commandGrid.ClearSelection()
        else:
            self.actions = []

        self.parent.Show()

    def AddRow(self):
        self.commandGrid.AppendRows(1)
        return self.commandGrid.GetNumberRows() - 1

    def EditCommandRow(self, commandName, duration, rowNum=None):
        if rowNum is None:
            rowNum = self.AddRow()
            self.actions.append(("IRPressAction", commandName, duration))
        else:
            self.actions[rowNum] = ("IRPressAction", commandName, duration)
        self.commandGrid.SetCellValue(rowNum, 0, commandName)
        self.commandGrid.SetCellValue(rowNum, 1, duration)

    def EditDelayRow(self, delayAmount, rowNum=None):
        if rowNum is None:
            rowNum = self.AddRow()
            self.actions.append(("IRDelayAction", None, delayAmount))
        else:
            self.actions[rowNum] = ("IRDelayAction", None, delayAmount)
        self.commandGrid.SetCellValue(rowNum, 0, "Delay")
        self.commandGrid.SetCellValue(rowNum, 1, delayAmount)

    def ResizeGrid(self):
        self.commandGrid.AutoSize()
        self.Layout()

    def GetSelectedRow(self):
        try:
            return self.commandGrid.GetSelectedRows()[0]
        except:
            return None

    def DoEditCommand(self, rowNum=None):
        if rowNum is not None:
            commandName = self.commandGrid.GetCellValue(rowNum, 0)
            duration = int(self.commandGrid.GetCellValue(rowNum, 1))
        else:
            commandName = None
            duration = 0
        dlg = wx.SingleChoiceDialog(self.parent,
                                    'Select command:',
                                    'Command Selection',
                                    self.deviceCommandsList)
        if commandName:
            dlg.SetSelection(self.deviceCommandsList.index(commandName))
        if dlg.ShowModal() == wx.ID_OK:
            commandName = dlg.GetStringSelection()
            val = wx.GetNumberFromUser('Enter duration in seconds:',
                                       '(0-60 s)', 'Duration Entry',
                                       value=duration, min=0, max=60)
            if val != -1:
                self.EditCommandRow(commandName, str(val), rowNum)
                self.ResizeGrid()
        dlg.Destroy()

    def DoEditDelay(self, rowNum=None):
        if rowNum is not None:
            delayAmount = int(self.commandGrid.GetCellValue(rowNum, 1))
        else:
            delayAmount = 0
        val = wx.GetNumberFromUser('Enter delay amount in milliseconds:',
                                   '(0-20000 ms)', 'Delay Entry',
                                   value=delayAmount, min=0, max=20000)
        if val != -1:
            self.EditDelayRow(str(val), rowNum)
            self.ResizeGrid()

    def OnSelectCell(self, event):
        self.commandGrid.SelectRow(event.GetRow())
        event.Skip()

    def OnAddCommand(self, event):
        self.DoEditCommand()

    def OnAddDelay(self, event):
        self.DoEditDelay()

    def OnEditCommand(self, event):
        rowNum = self.GetSelectedRow()
        if rowNum is None:
            wx.MessageBox('Please select a command', 'Error',
                          wx.OK | wx.ICON_WARNING)
        else:
            if self.actions[rowNum][0] == "IRDelayAction":
                self.DoEditDelay(rowNum)
            else:
                self.DoEditCommand(rowNum)

    def OnDeleteCommand(self, event):
        rowNum = self.GetSelectedRow()
        if rowNum is None:
            wx.MessageBox('Please select a command', 'Error',
                          wx.OK | wx.ICON_WARNING)
        else:
            self.commandGrid.DeleteRows(rowNum, 1)
            self.ResizeGrid()
            del self.actions[rowNum]

    def OnSaveChanges(self, event):
        BackgroundTask((self.DoSaveChanges,), (self.FinishSaveChanges,))

    def DoSaveChanges(self):
        mhMgr.SavePowerFeature(self.powerFeature, self.actions, self.actionType)

    def FinishSaveChanges(self, saveChangesResult):
        pass

    def GetTitle(self):
        return "Power Setting Adjustment"

    def IsCancelInitiallyDisabled(self):
        return False

    def GetNext(self):
        return (self.next, None)

    def GetBack(self):
        return (self.resources.page_remote_configuration, None)

class AdjustDeviceDelaysPanel(DevicePanelTemplate):
    _msg_welcome = (
        "On this page, you can adjust how quickly commands are sent to your " +
        "device."
    )

    def __init__(self, parent, resources):
        DevicePanelTemplate.__init__(self, parent, resources)

        self.sizer.AddSpacer(10)

        self.controlsSizer = wx.BoxSizer(wx.VERTICAL)
        self.sizer.Add(self.controlsSizer)

        self.SetSizerAndFit(self.sizer)

        self.next = None

    def OnActivated(self, prev_page, data):
        self.textMessage.UpdateText(self._msg_welcome)
        self.parent.ReenableBack()
        self.remoteId, self.deviceId, deviceName = data
        self.deviceTitle.SetLabel(deviceName)
        BackgroundTask((self.LoadData,), (self.LoadDataUI,), False)
        return (None, None)

    def LoadData(self):
        self.device = mhMgr.GetDevice(self.deviceId)
        self.userFeatures = mhMgr.GetUserFeatures(self.deviceId)

    def LoadDataUI(self, loadDataResult):
        self.controlsSizer.Clear(True)
        self.controls = {}
        self.featureIdxs = {}
        self.AddControl("interdevice", "Inter-device Delay (ms):", 0, 5000,
                        self.device.InterDeviceDelay,
                        self.device.DefaultInterDeviceDelay)
        self.AddControl("interkey", "Inter-key Delay (ms):", 0, 1000,
                        self.device.InterKeyDelay,
                        self.device.DefaultInterKeyDelay)
        for i in range(len(self.userFeatures.DeviceFeature) - 1, -1, -1):
            deviceFeature = self.userFeatures.DeviceFeature[i]
            if deviceFeature.__class__.__name__ == "InputFeature":
                self.AddControl("input", "Input Delay (ms):", 0, 5000,
                                deviceFeature.InputDelay,
                                deviceFeature.DefaultInputDelay)
                self.featureIdxs["input"] = i
            elif deviceFeature.__class__.__name__ == "PowerFeature":
                self.AddControl("poweron", "Power-on Delay (ms):", 0, 60000,
                                deviceFeature.PowerOnDelay,
                                deviceFeature.DefaultPowerOnDelay)
                self.featureIdxs["poweron"] = i
            else:
                del self.userFeatures.DeviceFeature[i]
        saveButton = wx.Button(self, label="Save Changes")
        saveButton.Bind(wx.EVT_BUTTON, self.OnSaveChanges)
        self.controlsSizer.Add(saveButton)
        self.Layout()
        self.parent.Show()

    def AddControl(self, key, labelText, min, max, value, default):
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        label = wx.StaticText(self, label=labelText, size=(157, 21))
        sizer.Add(label, flag=wx.ALIGN_CENTER_VERTICAL)
        sizer.AddSpacer(10)
        ctrl = wx.SpinCtrl(self, min=min, max=max, value=value)
        self.controls[key] = ctrl
        sizer.Add(ctrl)
        sizer.AddSpacer(10)
        button = wx.Button(self, label="Restore Default")
        def OnRestoreDefault(event, ctrl=ctrl, default=default):
            ctrl.SetValue(int(default))
        button.Bind(wx.EVT_BUTTON, OnRestoreDefault)
        sizer.Add(button)
        self.controlsSizer.Add(sizer)
        self.controlsSizer.AddSpacer(10)

    def OnSaveChanges(self, event):
        self.device.InterDeviceDelay = self.controls["interdevice"].GetValue()
        self.device.InterKeyDelay = self.controls["interkey"].GetValue()
        if "input" in self.controls:
            idx = self.featureIdxs["input"]
            self.userFeatures.DeviceFeature[idx].InputDelay = \
                self.controls["input"].GetValue()
        if "poweron" in self.controls:
            idx = self.featureIdxs["poweron"]
            self.userFeatures.DeviceFeature[idx].PowerOnDelay = \
                self.controls["poweron"].GetValue()
        BackgroundTask((self.DoSaveChanges,), (self.FinishSaveChanges,))

    def DoSaveChanges(self):
        mhMgr.UpdateDevice(self.device, self.remoteId)
        mhMgr.SaveUserFeatures(self.userFeatures)

    def FinishSaveChanges(self, saveChangesResult):
        pass

    def GetTitle(self):
        return "Device Delay Adjustment"

    def IsCancelInitiallyDisabled(self):
        return False

    def GetNext(self):
        return (self.next, None)

    def GetBack(self):
        return (self.resources.page_remote_configuration, None)

class Wizard(wx.Dialog):
    def __init__(
        self,
        resources,
        app_finalizer,
        min_page_width = 658,
        min_page_height = None
    ):
        self.app_finalizer = app_finalizer

        self.min_page_width = min_page_width
        self.min_page_height = min_page_height

        wx.Dialog.__init__(self, None, -1, 'MHGUI version ' + version)

        sizer_main = wx.BoxSizer(wx.VERTICAL)

        sizer_top = wx.BoxSizer(wx.HORIZONTAL)
        bitmap = wx.StaticBitmap(self, -1, resources.img_remote)
        sizer_top.Add(bitmap, 0, wx.EXPAND | wx.ALL, 5)

        self.sizer_top_right = wx.BoxSizer(wx.VERTICAL)
        self.title = wx.StaticText(self, -1, "Title")
        font = wx.Font(18, wx.SWISS, wx.NORMAL, wx.BOLD)
        self.title.SetFont(font)
        self.sizer_top_right.Add(self.title, 0, wx.EXPAND)
        divider_top_right = wx.StaticLine(self)
        self.sizer_top_right.Add(divider_top_right, 0, wx.EXPAND)
        spacer = wx.StaticText(self, -1, "")
        self.sizer_top_right.Add(spacer, 0, wx.EXPAND)

        sizer_top.Add(self.sizer_top_right, 1, wx.EXPAND | wx.ALL, 5)
        sizer_main.Add(sizer_top, 1, wx.EXPAND | wx.ALL, 5)

        divider_main = wx.StaticLine(self)
        sizer_main.Add(divider_main, 0, wx.EXPAND | wx.ALL, 5)

        sizer_buttons = wx.BoxSizer(wx.HORIZONTAL)

        sizer_buttons.AddStretchSpacer()

        self.btn_back = wx.Button(self, wx.ID_BACKWARD)
        self.Bind(wx.EVT_BUTTON, self._OnBack, self.btn_back)
        sizer_buttons.Add(self.btn_back, 0, wx.EXPAND | wx.ALL, 5)

        self.btn_next = wx.Button(self, wx.ID_FORWARD)
        self.Bind(wx.EVT_BUTTON, self._OnNext, self.btn_next)
        sizer_buttons.Add(self.btn_next, 0, wx.EXPAND | wx.ALL, 5)

        self.btn_close = wx.Button(self, wx.ID_CLOSE)
        self.Bind(wx.EVT_BUTTON, self._OnNext, self.btn_close)
        sizer_buttons.Add(self.btn_close, 0, wx.EXPAND | wx.ALL, 5)

        self.btn_cancel = wx.Button(self, wx.ID_CLOSE)
        self.Bind(wx.EVT_BUTTON, self._OnCancel, self.btn_cancel)
        self.Bind(wx.EVT_CLOSE, self._OnCancel)
        sizer_buttons.Add(self.btn_cancel, 0, wx.EXPAND | wx.ALL, 5)

        sizer_main.Add(sizer_buttons, 0, wx.EXPAND | wx.ALL, 5)

        self.SetSizerAndFit(sizer_main)

        self.cur_page = None

    def SetPages(self, pages):
        def tuple_max(a, b):
            return (max(a[0], b[0]), max(a[1], b[1]))

        self.pages = pages

        for page in self.pages:
            page.Hide()

        size_wiz = self.GetSize()
        for page in self.pages:
            page.Show()
            self.sizer_top_right.Add(page, 1, wx.EXPAND)
            self.Fit()
            size_page = self.GetSize()
            size_wiz = tuple_max(size_wiz, size_page)
            page.Hide()
            self.sizer_top_right.Detach(page)

        if self.min_page_width and (size_wiz[0] < self.min_page_width):
            size_wiz = (self.min_page_width, size_wiz[1])

        if self.min_page_height and (size_wiz[1] < self.min_page_height):
            size_wiz = (size_wiz[0], self.min_page_height )

        self.SetClientSize(size_wiz)

    def SetInitialPage(self, page):
        if self.cur_page:
            raise Exception("Current page already set")
        self._SetPage(page, None)

    def OnExit(self, retcode):
        if self.app_finalizer:
            self.app_finalizer()
        os._exit(retcode)

    def _ReenableButton(self, button):
        button.Enable(True)
        button.Hide()
        button.Show()
        button.SetFocus()

    def ReenableBack(self):
        self._ReenableButton(self.btn_back)

    def ReenableNext(self):
        self._ReenableButton(self.btn_next)

    def ReenableClose(self):
        self._ReenableButton(self.btn_close)

    def ReenableCancel(self):
        self._ReenableButton(self.btn_cancel)

    def _OnBack(self, event):
        try:
            (page, data, hide) = self.cur_page.GetBack()
        except:
            (page, data) = self.cur_page.GetBack()
            hide = False
        self._SetPage(page, data, hide)

    def _OnNext(self, event):
        if self.cur_page.IsTerminal():
            self.OnExit(self.cur_page.GetExitCode())
        if self.cur_page.OnNext():
            try:
                (page, data, hide) = self.cur_page.GetNext()
            except:
                (page, data) = self.cur_page.GetNext()
                hide = False
            self._SetPage(page, data, hide)

    def _OnCancel(self, event):
        self.cur_page.OnCancel()

    def _SetPage(self, page, data, hide=False):
        if hide:
            self.Hide()
        while page:
            if not page in self.pages:
                raise Exception("Invalid page")

            prev_page = self.cur_page
            if prev_page:
                prev_page.Hide()
                self.sizer_top_right.Detach(prev_page)

            self.cur_page = page

            self.cur_page.Show()
            self.sizer_top_right.Add(self.cur_page, 1, wx.EXPAND)

            self.title.SetLabel(self.cur_page.GetTitle())

            self.Layout()

            is_terminal = self.cur_page.IsTerminal()
            if is_terminal:
                self.btn_next.Hide()
                self.btn_close.Show()
            else:
                self.btn_next.Show()
                self.btn_close.Hide()

            self.btn_back.Enable(not self.cur_page.IsBackInitiallyDisabled())
            self.btn_next.Enable(not self.cur_page.IsNextInitiallyDisabled())
            self.btn_close.Enable(not self.cur_page.IsCloseInitiallyDisabled())
            self.btn_cancel.Enable(
                (not is_terminal)
                and
                (not self.cur_page.IsCancelInitiallyDisabled())
            )

            if self.btn_next.IsEnabled():
                self.btn_next.SetFocus()
            elif self.btn_close.IsEnabled():
                self.btn_close.SetFocus()

            (page, data) = self.cur_page.OnActivated(prev_page, data)

class Resources(object):
    def LoadImages(self):
        def load(filename):
            fpath = os.path.join(os.path.dirname(__file__), filename)
            return wx.Image(fpath, wx.BITMAP_TYPE_PNG).ConvertToBitmap()

        self.img_remote       = load("remote.png")

    def CreatePages(self, wizard):
        self.page_welcome = WelcomePanel(wizard, self)
        self.page_remote_select = RemoteSelectPanel(wizard, self)
        self.page_remote_configuration = RemoteConfigurationPanel(wizard, self)
        self.page_add_device = AddDevicePanel(wizard, self)
        self.page_create_account = CreateAccountPanel(wizard, self)
        self.page_configure_device = ConfigureDevicePanel(wizard, self)
        self.page_favorite_channels = FavoriteChannelsPanel(wizard, self)
        self.page_setup_watch_tv = SetupWatchTVPanel(wizard, self)
        self.page_harmony_link = ConfigureHarmonyLinkSettingsPanel(wizard, self)
        self.page_setup_activities = SetupActivitiesPanel(wizard, self)
        self.page_edit_activity = EditActivityPanel(wizard, self)
        self.page_adjust_power_settings = AdjustPowerSettingsPanel(wizard, self)
        self.page_adjust_device_delays = AdjustDeviceDelaysPanel(wizard, self)
        self.pages = [
            self.page_welcome,
            self.page_remote_select,
            self.page_remote_configuration,
            self.page_add_device,
            self.page_create_account,
            self.page_configure_device,
            self.page_favorite_channels,
            self.page_setup_watch_tv,
            self.page_harmony_link,
            self.page_setup_activities,
            self.page_edit_activity,
            self.page_adjust_power_settings,
            self.page_adjust_device_delays,
        ]

class Finalizer(object):
    def __init__(self, resources):
        self.resources = resources

    def __call__(self):
        pass


def main():
    app = wx.App(False)

    resources = Resources()
    resources.LoadImages()

    wizard = Wizard(resources, Finalizer(resources))

    resources.CreatePages(wizard)
    wizard.SetPages(resources.pages)
    wizard.SetInitialPage(resources.page_welcome)

    wizard.Show()

    app.MainLoop()

if __name__ == "__main__":
    main()
