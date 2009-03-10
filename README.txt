Requirements
==============================================================================

Python (tested with 2.5.1 on Fedora 9)
  See http://www.python.org/

Python ctypes library (included with Python 2.5, separate earlier)
  See http://sourceforge.net/projects/ctypes/

wxPython (tested with wxGTK-2.8.7 on Fedora 9)
  See http://www.wxpython.org/

libconcord (tested with post-0.20 CVS snapshot on Fedora 9)
  See http://www.phildev.net/concordance/
  Note that the python bindings are also required; see
  libconcord/bindings/python

Python, ctypes, and wxPython are typically installed using your distribution's
package management system. If this is not the case, installation instructions
should be located in the documentation accompanying those packages.

libconcord may be available via your distribution's package management
system. If so, please ensure that you install any sub-packages required to
provide the libconcord Python bindings, e.g. both libconcord and
libconcord-python.

If installing libconcord from source, please follow the instructions
accompanying the source. Note that the Python bindings must be installed
separately; the bindings are found within the following sub-directory of the
libconcord source package:

    libconcord/bindings/python

Some versions of libconcord provide a README.txt detailing the installation
process. Otherwise, the basic instructions are to run the following command as
root:

    python setup.py install

Installation
==============================================================================

congruity may be installed by running the following command:

    make install

This command typically requires root access, since the default installation
location is /usr/local.

Please read Makefile for details of variables that may be set to configure the
installation process, e.g.:

    make install DESTDIR=/tmp/pkgtmp PREFIX=/usr

Device Node Access Setup
==============================================================================

You may need to set up udev/similar rules so that the USB device nodes used
by the application are accessible without running congruity as root. Note that
distribution packages of libconcord typically provide these rules, so they may
already be set up for you.

If you need to manually set up udev rules, the following file should work:

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
peripherals you may have! Note that not all Harmony-compatible remotes are
Logitech-branded in the USB listing.

Usage Model
==============================================================================

congruity aims to fit into the usage model implemented by the official
Logitech software. The primary differentiation is that congruity is both
open-source and more cross-platform than the official software.

Harmony remotes are configured using the Logitech website, based at the
following URL:

    http://members.harmonyremote.com/

Note that other URLs may be used for remotes that are not branded as
"Harmony". However, the overall process is identical.

The website provides a database of devices, and a set of wizards to select
which of those are present in your setup. All decisions regarding how the
remote will be configured are made through this website. 

Please note that more recent versions of the Logitech software appear to be
an application that executes locally on the user's computer. However, they are
in fact a simple wrapping of a web-browser, simply hiding the web-based nature
of the configuration process.

Once the configuration is complete, the website will push various file
downloads to the web browser. These files contain the information required to
program the user's configuration into the remote. For each file downloaded,
the congruity application should be executed to process the instructions in
that file.

Web Browser Setup
==============================================================================

Configure your web browser to open files of type *.EZHex, *.EZUp, and *.EZTut
with the congruity application.

This is typically set up using the dialog box that appears when a file is
about to be downloaded. congruity should be executed once for each file
downloaded, and should be passed the name of the saved download as a command-
line parameter, for example:

    congruity /tmp/Connectivity.EZHex

If you're confused, the above behavior is most likely what your web browser
will do automatically when configured to open files using congruity.

Firefox Specific Notes
==============================================================================

You'll need to change a setting to see the download action prompt; Otherwise,
files will simply be saved to disk without you being asked. On Linux, this may
be achieved from the Edit menu -> Preferences menu item -> Main tab -> Select
"Always ask me where to save files". The exact menu location may vary slightly
on other operating systems.

When a file download commences, a dialog will appear with the option to "Open
With", or "Save" the file. Select "Open With", and browse for the congruity
executable as the application. You may also want to select "Do this
automatically for files like this from now on". You will need to select the
path to the congruity application once for each file type (*.EZHex, *.EZUp,
*.EZTut).

If the automatic option is not selected, the dialog will appear for every file
downloaded. Note that Firefox does remember the path to congruity for future
downloads, even though it is not displayed.

