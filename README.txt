Requirements:

Python (tested with 2.5.1 on Fedora 8)
  See http://www.python.org/
Python ctypes library (included with Python 2.5, separate earlier)
  See http://sourceforge.net/projects/ctypes/
wxPython (tested with wxGTK-2.8.4 on Fedora 8)
  See http://www.wxpython.org/
libconcord (tested with pre-0.20 CVS snapshot on Fedora 8)
  See http: http://www.phildev.net/concordance/

Installation/Usage:

You may need to set up udev/similar rules so that the USB device nodes
used by the application are accessible without using root. I use
the following file:

----- /etc/udev/rules.d/custom-concordance.rules:
SYSFS{idVendor}=="046d", SYSFS{idProduct}=="c110", MODE="666"
-----

Note that your vendor and product ID may be different. Use lsusb to verify:

-----
[swarren@esk ~]$ lsusb
...
Bus 005 Device 011: ID 046d:c110 Logitech, Inc. 
...
-----

Remember to differentiate between the Harmony remote and any other Logitech
peripherals you may have!

Congruity relies on the libconcord library, which must be obtained and
installed separately. Note that you will need to install the Python bindings
for libconcord too; see libconcord/bindings/python/.

Configure your web browser to open files of type *.EZHex and *.EZUp with the
congruity application. This is typically performed using the dialog box
that appears when a file is about to be downloaded.

Note that in Firefox, you'll need to change a setting to see the download
action prompt; Otherwise, files will simply be saved to disk without you
being asked. Edit menu -> Preferences menu item -> Main tab -> Select
"Always ask me where to save files."

