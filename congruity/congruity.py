# Copyright 2008-2010 Stephen Warren
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
from __future__ import absolute_import
import ctypes
import os
import os.path
import sys
import threading
import time
import traceback

import wx
import wx.lib.dialogs

version = "21"

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

# Test to determine if we have the new zwave API available.
try:
    libconcord.update_configuration
except:
    str = traceback.format_exc()
    app = wx.App(False)
    dlg = wx.MessageDialog(
        None,
        "Could not load the correct version of libconcord; please ensure "
        "that the latest version is installed.\n\n" + str,
        "congruity: Dependency Error",
        wx.OK | wx.ICON_ERROR
    )
    dlg.ShowModal()
    os._exit(1)

def fsencode(filename):
    try:
        return os.fsencode(filename)
    except AttributeError:
        return filename

def counter():
    i=0
    while True:
        yield i
        i += 1

def program_callback_imp(stage_id, count, current, total, type, context, stages):
    if not context:
        return

    try:
        (f, fcontext) = context
        percent = (current * 100) / total
        f(False, percent, fcontext)
    except:
        print()
        traceback.print_exc()

def program_callback_imp_multi(stage_id, count, current, total, type, context, stages):
    if not context:
        return

    if stage_id == libconcord.LC_CB_STAGE_NUM_STAGES:
        for i in range(count):
            wx.CallAfter(context._AddDg, stages[i])
        # Wait until we're sure all the widgets have been added.  Lock will be
        # released by _FinishWidgets().
        context.dg_widget_lock = threading.Lock()
        context.dg_widget_lock.acquire()
        wx.CallAfter(context._FinishWidgets)
        context.dg_widget_lock.acquire()
        return

    try:
        # dg_widgets is a list where each element in the list is a 3-item list:
        # [stage_id, DecoratedGauge, stage_finished (True/False)]
        # This allows us to support multiple instances of the same stage_id.
        widget_num = -1
        for index, item in enumerate(context.dg_widgets):
            if item[0] == stage_id and item[2] == False:
                widget_num = index
                break
        if widget_num == -1:
            return
        percent = (current * 100) / total
        context._DgUpdate(False, percent, context.dg_widgets[widget_num][1])
        if current == total:
            context._DgUpdate(True, percent, context.dg_widgets[widget_num][1])
            context.dg_widgets[widget_num][2] = True
    except:
        print()
        traceback.print_exc()

class CmdLineException(Exception):
    pass

def exception_message():
    msg = ''
    if type(sys.exc_info()[1]) == libconcord.LibConcordException:
        try:
            msg += '%s\n    (libconcord function %s error %d)\n\n' % (
                sys.exc_info()[1].result_str,
                sys.exc_info()[1].func,
                sys.exc_info()[1].result
            )
        except:
            pass
    if type(sys.exc_info()[1]) == CmdLineException:
        try:
            msg += '%s\n\n' % (
                str(sys.exc_info()[1])
            )
        except:
            pass
    msg += traceback.format_exc()
    return msg

def worker_body_connect(
    resources,
    on_progress,
    cb_context,
    cancel_check,
    after_reset
):
    program_callback = libconcord.callback_type(program_callback_imp)

    max_attempts = after_reset and 180 or 60
    for attempt in range(max_attempts):
        on_progress(
            False,
            (attempt * 100) / max_attempts,
            cb_context
        )
        try:
            if resources.connected:
                libconcord.deinit_concord()
                resources.SetConnected(False)
            libconcord.init_concord()
            resources.SetConnected(True)
            try:
                libconcord.get_identity(
                    program_callback,
                    None
                )
            except:
                ignore = False
                if type(sys.exc_info()[1]) == libconcord.LibConcordException:
                    ignore = sys.exc_info()[1].result == libconcord.LC_ERROR_INVALID_CONFIG
                if not ignore:
                    raise
            break
        except:
            if cancel_check() or (attempt == max_attempts - 1):
                raise
        time.sleep(1)
    on_progress(
        True,
        100,
        cb_context
    )

def show_modal_scrolled_msgbox(parent, title, text):
    size = parent.GetClientSizeTuple()
    size = (size[0] * 90 / 100, size[1] * 90 / 100)
    wx.lib.dialogs.ScrolledMessageDialog(
        parent,
        text,
        title,
        (-1, -1),
        size
    ).ShowModal()

ALIGN_LTA = wx.ALIGN_LEFT  | wx.ALIGN_TOP             | wx.ALL
ALIGN_XTA = wx.EXPAND      | wx.ALIGN_TOP             | wx.ALL
ALIGN_LCA = wx.ALIGN_LEFT  | wx.ALIGN_CENTER_VERTICAL | wx.ALL
ALIGN_RA = wx.ALIGN_RIGHT | wx.ALL
ALIGN_CA = wx.ALIGN_CENTER_VERTICAL | wx.ALL
ALIGN_XCA = wx.EXPAND      | wx.ALIGN_CENTER_VERTICAL | wx.ALL
ALIGN_LBA = wx.ALIGN_LEFT  | wx.ALIGN_BOTTOM          | wx.ALL
ALIGN_XBA = wx.EXPAND      | wx.ALIGN_BOTTOM          | wx.ALL

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

class DecoratedContainer(wx.Panel):
    def __init__(self, parent, resources):
        self.parent = parent
        self.resources = resources

        wx.Panel.__init__(self, parent)

        self.sizer = wx.GridBagSizer(5, 5)
        self.sizer.SetCols(3)
        self.sizer.AddGrowableCol(2)
        self.SetSizer(self.sizer)

        self.last_updated_dg = None

    def _DgStart(self, dg):
        self._OnProgressGauge(False, 0, dg)

    def _DgUpdate(self, is_done, percent, dg):
        self._OnProgressGauge(is_done, percent, dg)

    def _DgEnd(self, dg):
        self._OnProgressGauge(True, 100, dg)

    def _DgFailure(self):
        if self.last_updated_dg:
            self.last_updated_dg.SetBitmap(self.resources.icon_failed)

    def _OnProgressGauge(self, is_done, percent, dg):
        if is_done:
            new_bitmap = self.resources.icon_complete
        else:
            new_bitmap = self.resources.icon_in_progress
        dg.SetBitmap(new_bitmap)
        dg.gauge.SetValue(int(percent))
        self.last_updated_dg = dg

class DecoratedContainerThreadMixin(object):
    def __init__(self, dc):
        self.dc = dc

    def _DgStart(self, dg):
        wx.CallAfter(self.dc._DgStart, dg)

    def _DgUpdate(self, is_done, percent, dg):
        wx.CallAfter(self.dc._DgUpdate, is_done, percent, dg)

    def _DgEnd(self, dg):
        wx.CallAfter(self.dc._DgEnd, dg)

    def _DgFailure(self):
        wx.CallAfter(self.dc._DgFailure)

class DecoratedGauge(object):
    def __init__(self, parent, caption, vpos):
        self.current_bitmap = parent.resources.icon_unstarted
        self.bitmap = wx.StaticBitmap(
            parent,
            -1,
            self.current_bitmap,
            wx.DefaultPosition,
            parent.resources.iwh
        )
        self.text = wx.StaticText(parent, -1, caption)
        self.gauge = wx.Gauge(
            parent,
            -1,
            100,
            wx.DefaultPosition,
            (250, parent.resources.iwh[1])
        )
        parent.sizer.Add(self.bitmap, (vpos, 0), (1, 1), ALIGN_LBA, 5)
        parent.sizer.Add(self.text,   (vpos, 1), (1, 1), ALIGN_LCA, 5)
        parent.sizer.Add(self.gauge,  (vpos, 2), (1, 1), ALIGN_XBA, 5)

    def SetBitmap(self, new_bitmap):
        if self.current_bitmap == new_bitmap:
            return
        self.current_bitmap = new_bitmap
        self.bitmap.SetBitmap(self.current_bitmap)

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

class MessagePanelBase(WizardPanelBase):
    def __init__(self, parent, resources):
        WizardPanelBase.__init__(self, parent, resources)

        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.text_message = WrappedStaticText(self)
        self.sizer.Add(self.text_message, 0, ALIGN_XTA, 5)
        self.SetSizerAndFit(self.sizer)

class WelcomePanel(MessagePanelBase):
    _msg_welcome = (
        "Welcome to congruity; a programming application " +
        "for Logitech Harmony remote controls.\n\n"
    )

    _msg_progress_parsing = (
        "Please wait while the configuration file is parsed."
    )

    _msg_status_ok = (
        "Please ensure the remote control is connected " +
        "before proceeding.\n\n" +
        "Click 'forward' to begin operation."
    )

    _msg_status_failure = (
        "A problem occurred. Click 'forward' for details."
    )

    _msg_failure_explanation = (
        "The configuration file cannot be read, or parsing failed.\n\n" +
        "Operation cannot continue."
    )

    _msg_failure_details_unknown_op = (
        "Unrecognized file type '%d' returned by libconcord"
    )

    def __init__(self, parent, resources):
        self.parent = parent
        self.resources = resources

        MessagePanelBase.__init__(self, parent, resources)

        self.next = None
        self.initial_exception = None

    def _WorkerFunction(self):
        try:
            wx.CallAfter(
                self.text_message.UpdateText,
                self._msg_welcome + self._msg_progress_parsing
            )

            if self.initial_exception:
                wx.CallAfter(
                    self._OnStatusFailure,
                    *self.initial_exception
                )
                return

            self.next = self.resources.page_connect

            type = ctypes.c_int()
            libconcord.read_and_parse_file(
                fsencode(self.resources.ezhex_filename),
                ctypes.byref(type)
            )

            next_map = {
                libconcord.LC_FILE_TYPE_CONNECTIVITY:
                    (
                        self.resources.page_check_connectivity,
                        "Connectivity Check"
                    ),
                libconcord.LC_FILE_TYPE_CONFIGURATION:
                    (
                        self.resources.page_write_configuration,
                        "Update Configuration"
                    ),
                libconcord.LC_FILE_TYPE_FIRMWARE:
                    (
                        self.resources.page_update_firmware,
                        "Update Firmware"
                    ),
                libconcord.LC_FILE_TYPE_LEARN_IR:
                    (
                        self.resources.page_learn_ir_prep,
                        "Learn IR Codes"
                    )
            }

            (next_page, type_text) = next_map.get(type.value, (None, None))

            if not next_page:
                wx.CallAfter(
                    self._OnStatusFailure,
                    self._msg_failure_explanation,
                    self._msg_failure_details_unknown_op % type.value
                )
                return

            next_page.DoParsing()

            wx.CallAfter(self._OnStatusOk, next_page, type_text)
        except:
            wx.CallAfter(
                self._OnStatusFailure,
                self._msg_failure_explanation,
                exception_message()
            )

    def _OnStatusOk(self, next_page, type_text):
        self.resources.page_connect.SetNext(next_page)
        self._OnStatusCommon(self._msg_status_ok)

    def _OnStatusFailure(self, failure_msg, details):
        self.resources.page_failure.SetMessages(
            failure_msg,
            details
        )
        self.next = self.resources.page_failure
        self._OnStatusCommon(self._msg_status_failure)

    def _OnStatusCommon(self, message):
        self.text_message.UpdateText(self._msg_welcome + message)
        self.parent.ReenableCancel()
        self.parent.ReenableNext()

    def SetInitialException(self, initial_exception):
        self.initial_exception = initial_exception

    def OnActivated(self, prev_page, data):
        threading.Thread(target=self._WorkerFunction).start()
        return (None, None)

    def GetTitle(self):
        return "Welcome"

    def IsCancelInitiallyDisabled(self):
        return False

    def GetNext(self):
        return (self.next, None)

class ConnectPanel(WizardPanelBase, DecoratedContainerThreadMixin):
    _msg_ensure_connected = (
        "Please ensure your remote is correctly connected to your computer."
    )

    _msg_status_ok = (
        "Successfully connected to a remote:\n%s"
    )

    _msg_status_failure = (
        "A problem occurred. Click 'forward' for details."
    )

    _msg_failure_explanation = (
        "No remote could be found."
    )

    def __init__(self, parent, resources):
        WizardPanelBase.__init__(self, parent, resources)

        self.sizer = wx.BoxSizer(wx.VERTICAL)

        self.text_help = WrappedStaticText(self)
        self.sizer.Add(self.text_help, 0, wx.EXPAND | wx.ALL, 5)

        self.dc = DecoratedContainer(self, self.resources)
        DecoratedContainerThreadMixin.__init__(self, self.dc)
        self.dg_connect = DecoratedGauge(self.dc, "Detect Remote", 0)
        self.sizer.Add(self.dc, 0, wx.EXPAND | wx.ALL, 5)

        self.text_info = WrappedStaticText(self)
        self.sizer.Add(self.text_info, 0, wx.EXPAND | wx.ALL, 5)

        self.btn_details = wx.Button(self, -1, "&Details...")
        self.sizer.Add(self.btn_details, 0, ALIGN_LTA, 5)
        self.Bind(wx.EVT_BUTTON, self._OnDetails, self.btn_details)

        self.text_full_details = wx.TextCtrl(
            self,
            -1,
            style = wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL
        )
        self.sizer.Add(self.text_full_details, 1, ALIGN_XTA, 5)

        self.SetSizerAndFit(self.sizer)

        self.next = None
        self.finished = False
        self.cancelled = False

        self.lock = threading.Lock()

    def _WorkerFunction(self):
        try:
            wx.CallAfter(
                self.text_help.UpdateText,
                self._msg_ensure_connected
            )

            self._DgStart(self.dg_connect)
            worker_body_connect(
                self.resources,
                self._DgUpdate,
                self.dg_connect,
                lambda: self.cancelled,
                False
            )
            self._DgEnd(self.dg_connect)

            mfg = libconcord.get_mfg().decode('utf-8')
            model = libconcord.get_model().decode('utf-8')

            mfg_model = mfg + " " + model
            wx.CallAfter(self._OnStatusOk, mfg_model)
        except:
            wx.CallAfter(
                self._OnStatusFailure,
                self._msg_failure_explanation,
                exception_message()
            )

        self.lock.acquire()
        self.finished = True
        if self.cancelled:
            wx.CallAfter(self.OnCancel)
        self.lock.release()

    def _OnStatusOk(self, mfg_model):
        self.btn_details.Show()
        self._OnStatusCommon(self._msg_status_ok % mfg_model)

    def _OnStatusFailure(self, failure_msg, details):
        self.dc._DgFailure()
        self.resources.page_failure.SetMessages(
            failure_msg,
            details
        )
        self.SetNext(self.resources.page_failure)
        self._OnStatusCommon(self._msg_status_failure)

    def _OnStatusCommon(self, message):
        self.text_info.UpdateText(message)
        self.parent.ReenableNext()

    def _OnDetails(self, event):
        try:
            msg = ""

            mfg = libconcord.get_mfg().decode('utf-8')
            model = libconcord.get_model().decode('utf-8')
            codename = libconcord.get_codename().decode('utf-8')
            msg += "Model: %s %s (%s)\n" % (msg, model, codename)

            hid_mfg = libconcord.get_hid_mfg_str().decode('utf-8')
            hid_prod = libconcord.get_hid_prod_str().decode('utf-8')
            msg += "USB HID Model: %s %s\n" % (hid_mfg, hid_prod)

            ser_1 = libconcord.get_serial(libconcord.SERIAL_COMPONENT_1).decode('utf-8')
            ser_2 = libconcord.get_serial(libconcord.SERIAL_COMPONENT_2).decode('utf-8')
            ser_3 = libconcord.get_serial(libconcord.SERIAL_COMPONENT_3).decode('utf-8')
            msg += "Serial:\n    %s\n    %s\n    %s\n" % (ser_1, ser_2, ser_3)

            arch = libconcord.get_arch()
            proto = libconcord.get_proto()
            skin = libconcord.get_skin()
            msg += "Arch:%d Proto:%d Skin:%d\n" % (arch, proto, skin)

            fw_type = libconcord.get_fw_type()
            fw_ver_maj = libconcord.get_fw_ver_maj()
            fw_ver_min = libconcord.get_fw_ver_min()
            msg += "Firmware type:%d, version %d.%d\n" % (
                fw_type, fw_ver_maj, fw_ver_min
            )

            hw_ver_maj = libconcord.get_hw_ver_maj()
            hw_ver_min = libconcord.get_hw_ver_min()
            msg += "HW version %d.%d\n" % (hw_ver_maj, hw_ver_min)

            flash_mfg = libconcord.get_flash_mfg()
            flash_id = libconcord.get_flash_id()
            flash_part_num = libconcord.get_flash_part_num().decode('utf-8')
            flash_size = libconcord.get_flash_size()
            msg += "Flash Manufacturer:%d ID:%d Part:%s Size:%dK\n" % (
                flash_mfg, flash_id, flash_part_num, flash_size
            )

            hid_irl = libconcord.get_hid_irl()
            hid_orl = libconcord.get_hid_orl()
            hid_frl = libconcord.get_hid_frl()
            msg += "USB HID Irl:%d Orl:%d Frl:%d\n" % (hid_irl, hid_orl, hid_frl)

            usb_vid = libconcord.get_usb_vid()
            usb_pid = libconcord.get_usb_pid()
            usb_bcd = libconcord.get_usb_bcd()
            msg += "USB VID:%04x PID:%04x BCD:%04x\n" % (usb_vid, usb_pid, usb_bcd)

            config_bytes_used = libconcord.get_config_bytes_used()
            config_bytes_total = libconcord.get_config_bytes_total()
            config_pct_used = (config_bytes_used * 100) / config_bytes_total
            msg += "Config used %d / total %d = %d%%\n" % (
                config_bytes_used, config_bytes_total, config_pct_used
            )

            fw_nondirect = libconcord.is_fw_update_supported(0) == 0
            fw_direct = libconcord.is_fw_update_supported(1) == 0
            if fw_nondirect or fw_direct:
                config_safe = libconcord.is_config_safe_after_fw() == 0
                msg += "Firmware updates: Supported (%s), config%ssafe\n" % (
                    fw_direct and "Direct" or "Not direct",
                    config_safe and " " or " NOT "
                )
            else:
                msg += "Firmware updates: NOT supported\n"
        except:
            msg = (
                "Error retrieving remote information:\n" +
                exception_message()
            )

        self.text_info.Hide()
        self.btn_details.Hide()
        self.text_full_details.Show()
        self.text_full_details.SetValue(msg)
        self.Layout()

    def SetNext(self, next):
        self.next = next

    def OnActivated(self, prev_page, data):
        self.btn_details.Hide()
        self.text_full_details.Hide()
        threading.Thread(target=self._WorkerFunction).start()
        return (None, None)

    def OnCancel(self):
        self.lock.acquire()
        if self.finished:
            self.lock.release()
            self.parent.OnExit(1)
        else:
            self.cancelled = True
        self.lock.release()

    def GetTitle(self):
        return "Connecting"

    def IsCancelInitiallyDisabled(self):
        return False

    def GetNext(self):
        return (self.next, None)

class ProgramRemotePanelBase(WizardPanelBase, DecoratedContainerThreadMixin):
    def __init__(self, parent, resources, file_type):
        WizardPanelBase.__init__(self, parent, resources)
        self.file_type = file_type

        self.sizer = wx.BoxSizer(wx.VERTICAL)

        self.dc = DecoratedContainer(self, self.resources)
        DecoratedContainerThreadMixin.__init__(self, self.dc)
        self._AddWidgets()
        self.sizer.Add(self.dc, 0, wx.EXPAND | wx.ALL, 5)

        self.SetSizerAndFit(self.sizer)

        self.next = None
        self.finished = False

    def _WorkerFunction(self):
        try:
            try:
                self._WorkerFunctionBody()
                wx.CallAfter(self._OnStatusOk)
                return
            except:
                wx.CallAfter(
                    self._OnStatusFailure,
                    "Operation Failed",
                    exception_message()
                )
        finally:
            try:
                if self.resources.connected:
                    self.resources.SetConnected(False)
                    libconcord.deinit_concord()
            except:
                pass

    def _OnStatusOk(self):
        self.next = self.resources.page_success
        self._OnStatusCommon()

    def _OnStatusFailure(self, failure_msg, details):
        self.dc._DgFailure()
        self.next = self.resources.page_failure
        self.resources.page_failure.SetMessages(
            failure_msg,
            details
        )
        self._OnStatusCommon()

    def _OnStatusCommon(self):
        self.finished = True
        self.parent.ReenableCancel()
        self.parent.ReenableNext()

    def OnActivated(self, prev_page, data):
        threading.Thread(target=self._WorkerFunction).start()
        return (None, None)

    def OnCancel(self):
        if self.finished:
            self.parent.OnExit(1)
        show_modal_scrolled_msgbox(
            self.parent,
            "Cannot Cancel",
            "Cancel is disabled during programming operations, " +
            "to prevent placing the remote into a state that will " +
            "potentially be difficult to recover from."
        )

    def GetNext(self):
        return (self.next, None)

    def _AddDg(self, stage_id):
        self.dg_widgets.append([stage_id, DecoratedGauge(self.dc, libconcord.lc_cb_stage_str(stage_id), next(self.vpos)), False])

class CheckConnectivityPanel(ProgramRemotePanelBase):
    def __init__(self, parent, resources):
        ProgramRemotePanelBase.__init__(
            self,
            parent,
            resources,
            libconcord.LC_FILE_TYPE_CONNECTIVITY
        )

    def _AddWidgets(self):
        vpos = counter()
        self.dg_notify_website = DecoratedGauge(self.dc, "Notify Website", next(vpos))

    def DoParsing(self):
        pass

    def _WorkerFunctionBody(self):
        self._DgUpdate(
            False,
            0,
            self.dg_notify_website
        )
        if not self.resources.no_web:
            program_callback = libconcord.callback_type(program_callback_imp)
            libconcord.post_connect_test_success(
                program_callback,
                None
            )
        self._DgUpdate(
            True,
            100,
            self.dg_notify_website
        )

    def GetTitle(self):
        return "Checking Connectivity"

class WriteConfigurationPanel(ProgramRemotePanelBase):
    def __init__(self, parent, resources):
        ProgramRemotePanelBase.__init__(
            self,
            parent,
            resources,
            libconcord.LC_FILE_TYPE_CONFIGURATION
        )

    def _AddWidgets(self):
        self.vpos = counter()
        if not self.resources.no_web:
            self.dg_check_website = DecoratedGauge(self.dc, "Contacting website", next(self.vpos))
        self.dg_widgets = []

    def _FinishWidgets(self):
        if not self.resources.no_web:
            self.dg_notify_website = DecoratedGauge(self.dc, "Contacting website", next(self.vpos))
        self.Layout()
        self.dg_widget_lock.release()

    def DoParsing(self):
        pass

    def _WorkerFunctionBody(self):
        program_callback = libconcord.callback_type(program_callback_imp)

        if not self.resources.no_web:
            self._DgStart(self.dg_check_website)
            libconcord.post_preconfig(program_callback, None)
            self._DgEnd(self.dg_check_website)

        program_callback = libconcord.callback_type(program_callback_imp_multi)
        libconcord.update_configuration(
            program_callback,
            self,
            0
        )

        if not self.resources.no_web:
            self._DgStart(self.dg_notify_website)
            libconcord.post_postconfig(program_callback, None)
            self._DgEnd(self.dg_notify_website)

    def GetTitle(self):
        return "Updating Configuration"

class UpdateFirmwarePanel(ProgramRemotePanelBase):
    def __init__(self, parent, resources):
        ProgramRemotePanelBase.__init__(
            self,
            parent,
            resources,
            libconcord.LC_FILE_TYPE_FIRMWARE
        )

    def _AddWidgets(self):
        self.vpos = counter()
        self.dg_widgets = []

    def _FinishWidgets(self):
        if not self.resources.no_web:
            self.dg_notify_website = DecoratedGauge(self.dc, "Contacting website", next(self.vpos))
        self.Layout()
        self.dg_widget_lock.release()

    def DoParsing(self):
        pass

    def _WorkerFunctionBody(self):
        program_callback = libconcord.callback_type(program_callback_imp)

        # is_fw_update_supported returns error code; 0 OK, otherwise failure
        if libconcord.is_fw_update_supported(0) == 0:
            is_direct = False
        elif libconcord.is_fw_update_supported(1) == 0:
            is_direct = True
        else:
            raise Exception(
                "Sorry, congruity doesn't yet support firmware update " +
                "on this remote model."
            )

        program_callback = libconcord.callback_type(program_callback_imp_multi)
        libconcord.update_firmware(
            program_callback,
            self,
            0,
            ctypes.c_int(is_direct and 1 or 0)
        )

        if not self.resources.no_web:
            self._DgStart(self.dg_notify_website)
            libconcord.post_postfirmware(program_callback, None)
            self._DgEnd(self.dg_notify_website)

    def GetTitle(self):
        return "Updating Firmware"

class LearnIrPrepPanel(WizardPanelBase):
    def __init__(self, parent, resources):
        WizardPanelBase.__init__(self, parent, resources)

        self.sizer = wx.BoxSizer(wx.VERTICAL)

        self.text_top_message = WrappedStaticText(self)
        self.sizer.Add(self.text_top_message, 0, ALIGN_XTA, 5)

        self.source_radio = wx.RadioBox(
            self,
            -1,
            "Select Learning Source",
            wx.DefaultPosition,
            wx.DefaultSize,
            [
                "Learn from original remote   ",
                "Enter Pronto Hex   ",
                "Skip learning key   "
            ],
            1,
            wx.RA_SPECIFY_COLS
        )
        self.Bind(wx.EVT_RADIOBOX, self.OnSourceSelect, self.source_radio)
        self.sizer.Add(self.source_radio, 0, ALIGN_LTA, 20)

        self.text_bottom_message = WrappedStaticText(self)
        self.sizer.Add(self.text_bottom_message, 0, ALIGN_XTA, 5)

        self.SetSizerAndFit(self.sizer)

        self.sel = 0

    def DoParsing(self):
        key_names = ctypes.POINTER(ctypes.c_char_p)()
        key_names_length = ctypes.c_uint()
        libconcord.get_key_names(
            ctypes.byref(key_names),
            ctypes.byref(key_names_length)
        )
        try:
            self.resources.key_names = []
            self.resources.key_names_index = -1
            for i in range(key_names_length.value):
                self.resources.key_names.append(key_names[i].decode('utf-8') + '')
        finally:
            libconcord.delete_key_names(key_names, key_names_length)

    def OnActivated(self, prev_page, is_back):
        if not is_back:
            self.resources.key_names_index += 1
        if self.resources.key_names_index == len(self.resources.key_names):
            return (self.resources.page_success, None)
        self.text_top_message.UpdateText(
            "About to learn key '%s' (%d of %d)." % (
                self.resources.key_names[self.resources.key_names_index],
                self.resources.key_names_index + 1,
                len(self.resources.key_names)
            )
        )
        self._SetSelect(self.sel)
        return (None, None)

    def OnSourceSelect(self, event):
        self._SetSelect(event.GetInt())

    def GetTitle(self):
        return "IR Learning"

    def IsNextInitiallyDisabled(self):
        return False

    def IsCancelInitiallyDisabled(self):
        return False

    def GetNext(self):
        if self.sel == 0:
            return (self.resources.page_learn_ir_learn, None)
        if self.sel == 1:
            return (self.resources.page_learn_ir_enter_pronto_hex, None)
        if self.sel == 2:
            return (self, False)
        return (None, None)

    def _SetSelect(self, sel):
        self.sel = sel
        if self.sel == 0:
            self.text_bottom_message.UpdateText(
                (
                    "INSTRUCTIONS:\n\n" +
                    "Please point your original remote at the IR receiver of " +
                    "your Harmony remote. The IR receiver is typically at the " +
                    "end of the Harmony that you hold closest to you.\n\n" +
                    "The remotes should be placed approximately 2-5 inches " +
                    "(5-10 cm) apart.\n\n" +
                    "Please locate the '%s' button on your original remote, " +
                    "and be prepared to press and hold that button after " +
                    "you have clicked 'forward'."
                ) % self.resources.key_names[self.resources.key_names_index]
            )
        if self.sel == 1:
            self.text_bottom_message.UpdateText(
                "INSTRUCTIONS:\n\n" +
                "Click 'forward' to type/paste in the Pronto hex codes."
            )
        if self.sel == 2:
            self.text_bottom_message.UpdateText(
                "INSTRUCTIONS:\n\n" +
                "This will skip learning this key."
            )

class IRSignalCanvas(wx.ScrolledWindow):
    def __init__(self, parent, id = -1, size = wx.DefaultSize):
        wx.ScrolledWindow.__init__(
            self,
            parent,
            -1,
            size=(300, 100),
            style=wx.SUNKEN_BORDER
        )
        self.SetBackgroundColour("BLACK")
        self.SetScrollbars(10, 0, 32767, 0)
        self.Bind(wx.EVT_PAINT, self.OnPaint)

        self.pulses = []
        self.scale = 20000

    def OnPaint(self, event):
        if not len(self.pulses):
            return

        ytotal = self.GetClientSize()[1]
        ytop = ytotal / 4
        ybottom = ytotal - ytop
        yoffsetmax = ytotal - (ybottom - ytop)

        dc = wx.PaintDC(self)
        self.PrepareDC(dc)
        dc.SetBackground(wx.Brush("black"))
        dc.SetPen(wx.Pen("GREEN"))
        dc.Clear()

        x = 16
        yoffset = 0

        for pulse in self.pulses:
            y = ytop + yoffset
            xe = x + (pulse / self.scale)

            dc.DrawLine(x, ytop, x,  ybottom - 1)
            dc.DrawLine(x, y,    xe, y)

            x = xe
            yoffset = yoffsetmax - yoffset

    def SetSignal(self, pulses, pulse_count):
        if pulse_count == 0:
            return
        self.pulses = []
        self.pulses_sum = 0
        for i in range(pulse_count.value):
            pulse = pulses[i]
            self.pulses_sum = self.pulses_sum + pulse
            self.pulses.append(pulse)
        self.min_scale = (self.pulses_sum / (32767 - 32)) + 1
        self.max_scale = (self.pulses_sum / (self.GetClientSize()[0] - 32)) - 1
        self.max_scale = max(self.max_scale, 1)

        self.scale = self.max_scale
        self._OnSetScale()

    def OnZoomIn(self):
        if not self.pulses:
            return
        self.scale = max(self.scale / 2, self.min_scale)
        self._OnSetScale()

    def OnZoomOut(self):
        if not self.pulses:
            return
        self.scale = min(self.scale * 2, self.max_scale)
        self._OnSetScale()

    def _OnSetScale(self):
        pix_per_unit = 10
        units = (32 + (self.pulses_sum / self.scale)) / pix_per_unit
        pix_to_scroll = pix_per_unit * units
        if pix_to_scroll <= self.GetClientSize()[0]:
            units += 1
        self.SetScrollbars(pix_per_unit, 0, units, 0)

class IRSignalPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)

        sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.canvas = IRSignalCanvas(self)
        sizer.Add(self.canvas, 1, wx.EXPAND | wx.ALL, 0)

        sizer_buttons = wx.BoxSizer(wx.VERTICAL)

        btn_zi = wx.Button(self, -1, "+")
        sizer_buttons.Add(btn_zi, 0, ALIGN_RA, 5)
        self.Bind(wx.EVT_BUTTON, self.OnZoomIn, btn_zi)

        btn_zo = wx.Button(self, -1, "-")
        sizer_buttons.Add(btn_zo, 0, ALIGN_RA, 5)
        self.Bind(wx.EVT_BUTTON, self.OnZoomOut, btn_zo)

        sizer.Add(sizer_buttons, 0, ALIGN_CA, 0)

        self.SetSizer(sizer)

    def OnZoomIn(self, event):
        self.canvas.OnZoomIn()

    def OnZoomOut(self, event):
        self.canvas.OnZoomOut()

class LearnIrLearnPanel(WizardPanelBase, DecoratedContainerThreadMixin):
    def __init__(self, parent, resources):
        WizardPanelBase.__init__(self, parent, resources)

        self.sizer = wx.BoxSizer(wx.VERTICAL)

        self.text_top_message = WrappedStaticText(self)
        self.sizer.Add(self.text_top_message, 0, ALIGN_XTA, 5)

        self.dc = DecoratedContainer(self, self.resources)
        DecoratedContainerThreadMixin.__init__(self, self.dc)

        vpos = counter()
        self.dg_learn = DecoratedGauge(self.dc, "Learn IR", next(vpos))

        self.sizer.Add(self.dc, 0, wx.EXPAND | wx.ALL, 5)

        self.btn_details = wx.Button(self, -1, "&Details...")
        self.sizer.Add(self.btn_details, 0, wx.ALIGN_LEFT | wx.ALL, 5)
        self.Bind(wx.EVT_BUTTON, self._OnDetails, self.btn_details)

        self.divider = wx.StaticLine(self)
        self.sizer.Add(self.divider, 0, wx.EXPAND)

        self.text_results = WrappedStaticText(self)
        self.sizer.Add(self.text_results, 0, ALIGN_XTA, 5)

        self.signal = IRSignalPanel(self)
        self.sizer.Add(self.signal, 0, wx.EXPAND | wx.ALL, 5)

        self.SetSizerAndFit(self.sizer)

    def _WorkerFunction(self):
        try:
            program_callback = libconcord.callback_type(program_callback_imp)

            self._DgStart(self.dg_learn)

            self.resources.cur_ir_allocated_by_libconcord = True
            self.resources.cur_ir_carrier_clock = ctypes.c_uint()
            self.resources.cur_ir_signal = ctypes.POINTER(ctypes.c_uint)()
            self.resources.cur_ir_signal_length = ctypes.c_uint()
            libconcord.learn_from_remote(
                ctypes.byref(self.resources.cur_ir_carrier_clock),
                ctypes.byref(self.resources.cur_ir_signal),
                ctypes.byref(self.resources.cur_ir_signal_length),
                program_callback,
                ctypes.py_object((self._DgUpdate, self.dg_learn))
            )
            if self.resources.cur_ir_carrier_clock.value < 1000:
                raise Exception('Carrier frequency too low')

            self._DgEnd(self.dg_learn)

            wx.CallAfter(self._OnStatusOk)
            return
        except:
            wx.CallAfter(
                self._OnStatusFailure,
                "IR learning failure",
                exception_message()
            )

    def _OnStatusOk(self):
        self.btn_details.Show()
        self.parent.ReenableBack()
        self.next = self.resources.page_learn_ir_upload
        self._OnStatusCommon()

    def _OnStatusFailure(self, failure_msg, details):
        self.dc._DgFailure()
        self.next = self.resources.page_failure
        self.resources.page_failure.SetMessages(
            failure_msg,
            details
        )
        self._OnStatusCommon()
        self.text_results.Show()
        self.text_results.UpdateText(
            "\nRESULTS:\n\n" +
            "Learning failed; perhaps you did not press a key on the original " +
            "remote, or you held the key for too long."
        )
        self.parent.ReenableBack()

    def _OnStatusCommon(self):
        self.parent.ReenableCancel()
        self.parent.ReenableNext()

    def _OnDetails(self, event):
        self.btn_details.Hide()
        self.divider.Show()
        self.text_results.Show()
        self.signal.Show()
        self.text_results.UpdateText(
            "\nRESULTS:\n\n" +
            "Carrier Frequency: %d" % self.resources.cur_ir_carrier_clock.value
        )
        self.signal.canvas.SetSignal(
            self.resources.cur_ir_signal,
            self.resources.cur_ir_signal_length
        )

    def OnActivated(self, prev_page, data):
        self.btn_details.Hide()
        self.divider.Hide()
        self.text_results.Hide()
        self.signal.Hide()
        self.text_top_message.UpdateText(
            "Please press and hold the button on your original remote now."
        )
        threading.Thread(target=self._WorkerFunction).start()
        return (None, None)

    def GetTitle(self):
        return "IR Learning"

    def GetBack(self):
        return (self.resources.page_learn_ir_prep, True)

    def GetNext(self):
        return (self.next, None)

class LearnIrEnterProntoHexPanel(WizardPanelBase):
    def __init__(self, parent, resources):
        WizardPanelBase.__init__(self, parent, resources)

        self.sizer = wx.BoxSizer(wx.VERTICAL)

        self.text_top_message = WrappedStaticText(self)
        self.sizer.Add(self.text_top_message, 0, ALIGN_XTA, 5)

        self.edit_hex = wx.TextCtrl(
            self,
            -1,
            style = wx.TE_MULTILINE | wx.HSCROLL
        )
        self.sizer.Add(self.edit_hex, 1, ALIGN_XTA, 5)

        self.btn_validate = wx.Button(self, -1, "&Validate...")
        self.sizer.Add(self.btn_validate, 0, wx.ALIGN_LEFT | wx.ALL, 5)
        self.Bind(wx.EVT_BUTTON, self._OnValidate, self.btn_validate)

        self.text_results = WrappedStaticText(self)
        self.sizer.Add(self.text_results, 0, ALIGN_XTA, 5)

        self.signal = IRSignalPanel(self)
        self.sizer.Add(self.signal, 0, wx.EXPAND | wx.ALL, 5)

        self.SetSizerAndFit(self.sizer)

    def _OnValidate(self, event):
        try:
            bin = []
            str = ""
            str_idx = 0

            hex = self.edit_hex.GetValue().strip().split(' ')
            for h in hex:
                b = int(h, 16)
                bin.append(b)

                str += "%04x " % b
                str_idx += 1
                if str_idx == 12:
                    str += "\n"
                    str_idx = 0

            self.edit_hex.SetValue(str)

            if len(bin) < 4:
                raise Exception('Pronto code too short (missing header)')

            if bin[0] != 0:
                raise Exception('Not RAW')

            pronto_clock = 4145146
            # IR carrier frequency is given as number of Pronto clock cycles
            frequency = int(pronto_clock / bin[1])
            # Mark/space durations are given as a count of IR carrier cycles,
            # but we need them in microseconds
            carrier_cycle_us = 1000000.0 / frequency

            count_1 = 2 * bin[2]
            count_2 = 2 * bin[3]

            if len(bin) < 4 + count_1 + count_2:
                raise Exception('Pronto code too short (missing pulsetrain)')

            start_1 = 4
            start_2 = 4 + count_1

            repeats = 4
            count = count_1 + (repeats * count_2)

            self.resources.cur_ir_allocated_by_libconcord = False
            self.resources.cur_ir_carrier_clock = ctypes.c_uint(frequency)
            cur_ir_signal_type = ctypes.c_uint * count
            self.resources.cur_ir_signal = cur_ir_signal_type()
            self.resources.cur_ir_signal_length = ctypes.c_uint(count)

            idx = 0

            for i in range(count_1):
                self.resources.cur_ir_signal[idx] = int(bin[start_1 + i] * carrier_cycle_us)
                idx += 1

            for j in range(repeats):
                for i in range(count_2):
                    self.resources.cur_ir_signal[idx] = int(bin[start_2 + i] * carrier_cycle_us)
                    idx += 1

            self._OnStatusOk()

            return
        except:
            self._OnStatusFailure(exception_message())

    def _OnStatusOk(self):
        self.edit_hex.SetEditable(False)

        self.btn_validate.Hide()
        self.text_results.Show()
        self.text_results.UpdateText(
            "\nRESULTS:\n\n" +
            "Carrier Frequency: %d" % self.resources.cur_ir_carrier_clock.value
        )
        self.signal.Show()
        self.signal.canvas.SetSignal(
            self.resources.cur_ir_signal,
            self.resources.cur_ir_signal_length
        )
        self.Layout()
        self.parent.ReenableNext()

    def _OnStatusFailure(self, details):
        self.text_results.Show()
        self.text_results.UpdateText(
            "\nValidation failed:\n\n" + details
        )
        self.signal.Hide()

    def OnActivated(self, prev_page, data):
        self.edit_hex.SetValue("")
        self.edit_hex.SetEditable(True)
        self.btn_validate.Show()
        self.text_results.Hide()
        self.signal.Hide()
        self.text_top_message.UpdateText(
            "Type or paste Pronto HEX code below:"
        )
        self.edit_hex.SetFocus()
        return (None, None)

    def GetTitle(self):
        return "IR Learning"

    def IsBackInitiallyDisabled(self):
        return False

    def IsCancelInitiallyDisabled(self):
        return False

    def GetBack(self):
        return (self.resources.page_learn_ir_prep, True)

    def GetNext(self):
        return (self.resources.page_learn_ir_upload, None)

class LearnIrUploadPanel(WizardPanelBase, DecoratedContainerThreadMixin):
    def __init__(self, parent, resources):
        WizardPanelBase.__init__(self, parent, resources)

        self.sizer = wx.BoxSizer(wx.VERTICAL)

        self.dc = DecoratedContainer(self, self.resources)
        DecoratedContainerThreadMixin.__init__(self, self.dc)

        vpos = counter()
        self.dg_upload = DecoratedGauge(self.dc, "Upload Signal", next(vpos))

        self.sizer.Add(self.dc, 0, wx.EXPAND | wx.ALL, 5)

        self.SetSizerAndFit(self.sizer)

    def _WorkerFunction(self):
        try:
            program_callback = libconcord.callback_type(program_callback_imp)

            self._DgStart(self.dg_upload)

            post_string = ctypes.c_char_p()
            libconcord.encode_for_posting(
                self.resources.cur_ir_carrier_clock,
                self.resources.cur_ir_signal,
                self.resources.cur_ir_signal_length,
                post_string
            )

            try:
                if self.resources.cur_ir_allocated_by_libconcord:
                    libconcord.delete_ir_signal(self.resources.cur_ir_signal);
                self.resources.cur_ir_carrier_clock = None
                self.resources.cur_ir_signal = None
                self.resources.cur_ir_signal_length = None

                self._DgUpdate(False, 10, self.dg_upload)

                if not self.resources.no_web:
                    libconcord.post_new_code(
                        self.resources.key_names[self.resources.key_names_index].encode('utf-8'),
                        post_string,
                        program_callback,
                        None
                    )
            finally:
                libconcord.delete_encoded_signal(post_string)

            self._DgEnd(self.dg_upload)

            wx.CallAfter(self._OnStatusOk)
            return
        except:
            wx.CallAfter(
                self._OnStatusFailure,
                "Signal upload failure",
                exception_message()
            )

    def _OnStatusOk(self):
        self.next = self.resources.page_learn_ir_prep
        self._OnStatusCommon()

    def _OnStatusFailure(self, failure_msg, details):
        self.dc._DgFailure()
        self.next = self.resources.page_failure
        self.resources.page_failure.SetMessages(
            failure_msg,
            details
        )
        self._OnStatusCommon()

    def _OnStatusCommon(self):
        self.parent.ReenableCancel()
        self.parent.ReenableNext()

    def OnActivated(self, prev_page, data):
        threading.Thread(target=self._WorkerFunction).start()
        return (None, None)

    def GetTitle(self):
        return "IR Signal Upload"

    def GetNext(self):
        return (self.next, None)

class SuccessPanel(MessagePanelBase):
    def __init__(self, parent, resources):
        MessagePanelBase.__init__(
            self,
            parent,
            resources
        )

    def OnActivated(self, prev_page, data):
        self.text_message.UpdateText("Operation has completed successfully.")
        return (None, None)

    def OnCancel(self):
        self.parent.OnExit(0)

    def GetTitle(self):
        return "Success"

    def IsTerminal(self):
        return True

    def GetExitCode(self):
        return 0

    def IsCloseInitiallyDisabled(self):
        return False

class FailurePanel(WizardPanelBase):
    def __init__(self, parent, resources):
        WizardPanelBase.__init__(self, parent, resources)

        self.sizer = wx.BoxSizer(wx.VERTICAL)

        self.text_message = WrappedStaticText(self)
        self.sizer.Add(self.text_message, 0, ALIGN_LTA, 5)

        self.btn_details = wx.Button(self, -1, "&Details...")
        self.Bind(wx.EVT_BUTTON, self._OnDetails, self.btn_details)
        self.sizer.Add(self.btn_details, 0, ALIGN_LTA, 5)

        self.text_full_details = wx.TextCtrl(
            self,
            -1,
            style = wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL
        )
        self.sizer.Add(self.text_full_details, 1, ALIGN_XTA, 5)

        self.SetSizerAndFit(self.sizer)

        self.message = ""
        self.log_text = ""

    def _OnDetails(self, event):
        self.btn_details.Hide()
        self.text_full_details.Show()
        self.text_full_details.SetValue(self.log_text)
        self.parent.ReenableClose()

    def SetMessages(self, message, traceback):
        self.message = message
        if traceback:
            self.message += "\n\nSee below for details."
        self.log_text = traceback

    def OnActivated(self, prev_page, data):
        self.text_full_details.Hide()
        if self.log_text:
            self.btn_details.SetFocus()
        else:
            self.btn_details.Hide()
        self.text_message.UpdateText(self.message)
        return (None, None)

    def GetTitle(self):
        return "Failure"

    def IsTerminal(self):
        return True

    def GetExitCode(self):
        return 1

    def IsCloseInitiallyDisabled(self):
        return False

class Wizard(wx.Dialog):
    def __init__(
        self,
        resources,
        app_finalizer,
        min_page_width = 658,
        min_page_height = 560
    ):
        self.app_finalizer = app_finalizer

        self.min_page_width = min_page_width
        self.min_page_height = min_page_height

        wx.Dialog.__init__(self, None, -1, 'Congruity version ' + version)

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

        self.btn_cancel = wx.Button(self, wx.ID_CANCEL)
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
        (page, data) = self.cur_page.GetBack()
        self._SetPage(page, data)

    def _OnNext(self, event):
        if self.cur_page.IsTerminal():
            self.OnExit(self.cur_page.GetExitCode())
        (page, data) = self.cur_page.GetNext()
        self._SetPage(page, data)

    def _OnCancel(self, event):
        self.cur_page.OnCancel()

    def _SetPage(self, page, data):
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
    def __init__(self, no_web):
        self.no_web = no_web

        self.ezhex_filename = None
        self.xml = None
        self.xml_size = None
        self.learn_key_list = None
        self.learn_key_index = 0
        self.connected = False

    def LoadImages(self):
        def load(filename):
            fpath = os.path.join(os.path.dirname(__file__), filename)
            return wx.Image(fpath, wx.BITMAP_TYPE_PNG).ConvertToBitmap()

        self.img_remote       = load("remote.png")
        self.icon_unstarted   = load("icon-unstarted.png")
        self.icon_in_progress = load("icon-in-progress.png")
        self.icon_complete    = load("icon-complete.png")
        self.icon_failed      = load("icon-failed.png")

        iw = max(
            self.icon_in_progress.GetWidth(),
            self.icon_complete.GetWidth(),
            self.icon_failed.GetWidth()
        )
        ih = max(
            self.icon_in_progress.GetHeight(),
            self.icon_complete.GetHeight(),
            self.icon_failed.GetHeight()
        )
        self.iwh = (iw, ih)

    def CreatePages(self, wizard):
        self.page_welcome = WelcomePanel(wizard, self)
        self.page_connect = ConnectPanel(wizard, self)
        self.page_check_connectivity = CheckConnectivityPanel(wizard, self)
        self.page_write_configuration = WriteConfigurationPanel(wizard, self)
        self.page_update_firmware = UpdateFirmwarePanel(wizard, self)
        self.page_success = SuccessPanel(wizard, self)
        self.page_failure = FailurePanel(wizard, self)
        self.page_learn_ir_prep = LearnIrPrepPanel(wizard, self)
        self.page_learn_ir_learn = LearnIrLearnPanel(wizard, self)
        self.page_learn_ir_enter_pronto_hex = LearnIrEnterProntoHexPanel(wizard, self)
        self.page_learn_ir_upload = LearnIrUploadPanel(wizard, self)
        self.pages = [
            self.page_welcome,
            self.page_connect,
            self.page_check_connectivity,
            self.page_write_configuration,
            self.page_update_firmware,
            self.page_success,
            self.page_failure,
            self.page_learn_ir_prep,
            self.page_learn_ir_learn,
            self.page_learn_ir_enter_pronto_hex,
            self.page_learn_ir_upload,
        ]

    def SetEzHexFilename(self, ezhex_filename):
        self.ezhex_filename = ezhex_filename

    def SetXmlData(self, xml, xml_size):
        self.xml = xml
        self.xml_size = xml_size

    def SetConnected(self, connected):
        self.connected = connected

class Finalizer(object):
    def __init__(self, resources):
        self.resources = resources

    def __call__(self):
        try:
            if self.resources.xml:
                libconcord.delete_blob(self.resources.xml)
        except:
            pass
        self.resources.xml = None
        self.resources.xml_size = None

        try:
            if self.resources.cur_ir_allocated_by_libconcord and self.resources.cur_ir_signal:
                libconcord.delete_ir_signal(self.resources.cur_ir_signal);
        except:
            pass
        self.resources.cur_ir_carrier_clock = None
        self.resources.cur_ir_signal = None
        self.resources.cur_ir_signal_length = None

        try:
            if self.resources.connected:
                self.resources.SetConnected(False)
                libconcord.deinit_concord()
        except:
            pass

def main():
    argv = sys.argv
    app = wx.App(False)

    appdir = os.path.dirname(argv.pop(0))

    no_web = False
    try:
        while len(argv) and argv[0].startswith('-'):
            arg = argv.pop(0)
            if arg == '--version':
                print(version)
                return
            elif arg == '--no-web':
                no_web = True
            else:
                raise CmdLineException("ERROR: Option '%s' not recognized" % arg)
        if len(argv) != 1:
            # We did not get a file name on the command line, prompt the user for one.
            with wx.FileDialog(None, "Congruity - Open a file", 
                               wildcard="EZHex files (*.EZHex;*.EZUp;*.EZTut)|*.EZHex;*.EZUp;*.EZTut",
                               style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as fileDialog:
                if fileDialog.ShowModal() == wx.ID_CANCEL:
                    os._exit(1)
                ezhex_filename = fileDialog.GetPath()
        else:
            ezhex_filename = argv.pop(0)
        initial_exception = None
    except:
        ezhex_filename = None
        initial_exception = ("Command-line error", exception_message())

    resources = Resources(no_web)
    resources.LoadImages()
    resources.SetEzHexFilename(ezhex_filename)

    wizard = Wizard(resources, Finalizer(resources))

    resources.CreatePages(wizard)
    if initial_exception:
        resources.page_welcome.SetInitialException(initial_exception)
    wizard.SetPages(resources.pages)
    wizard.SetInitialPage(resources.page_welcome)

    wizard.Show()

    app.MainLoop()

if __name__ == "__main__":
    main()
