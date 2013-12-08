RUN_UPDATE_DESKTOP_DB ?= 1

DESTDIR ?=
PREFIX  ?= /usr/local

BINDIR      ?= $(PREFIX)/bin
SHAREDIR    ?= $(PREFIX)/share
APPSHAREDIR ?= $(SHAREDIR)/congruity
DESKTOPDIR  ?= $(SHAREDIR)/applications
MANDIR      ?= $(SHAREDIR)/man
MAN1DIR     ?= $(MANDIR)/man1

INSTALL ?= install
UPDATE_DESKTOP_DB ?= update-desktop-database

all:
	@echo "Nothing to build, run 'make install' as root"

install:
	mkdir -p --mode=755 $(DESTDIR)$(BINDIR)
	sed -e "s:/usr/share/congruity:${APPSHAREDIR}:" < congruity > congruity.patched
	$(INSTALL) --mode=755 congruity.patched $(DESTDIR)$(BINDIR)/congruity
	rm -f congruity.patched
	sed -e "s:/usr/share/congruity:${APPSHAREDIR}:" < mhgui > mhgui.patched
	$(INSTALL) --mode=755 mhgui.patched $(DESTDIR)$(BINDIR)/mhgui
	rm -f mhgui.patched
	mkdir -p --mode=755 $(DESTDIR)$(APPSHAREDIR)
	$(INSTALL) --mode=644 *.gif $(DESTDIR)$(APPSHAREDIR)
	$(INSTALL) --mode=644 *.png $(DESTDIR)$(APPSHAREDIR)
	$(INSTALL) --mode=644 harmony.wsdl $(DESTDIR)$(APPSHAREDIR)
	$(INSTALL) --mode=644 *.xsd $(DESTDIR)$(APPSHAREDIR)
	sed -e "s:/usr/share/congruity:${APPSHAREDIR}:" < mhmanager.py > mhmanager.py.patched
	$(INSTALL) --mode=644 mhmanager.py.patched $(DESTDIR)$(APPSHAREDIR)/mhmanager.py
	rm -f mhmanager.py.patched
	mkdir -p --mode=755 $(DESTDIR)$(MAN1DIR)
	$(INSTALL) --mode=644 congruity.1 $(DESTDIR)$(MAN1DIR)
	$(INSTALL) --mode=644 mhgui.1 $(DESTDIR)$(MAN1DIR)
	mkdir -p --mode=755 $(DESTDIR)$(DESKTOPDIR)
	$(INSTALL) --mode=644 congruity.desktop $(DESTDIR)$(DESKTOPDIR)
	$(INSTALL) --mode=644 mhgui.desktop $(DESTDIR)$(DESKTOPDIR)
ifeq ($(RUN_UPDATE_DESKTOP_DB),1)
	$(UPDATE_DESKTOP_DB) > /dev/null 2>&1 || :
endif

uninstall:
	/bin/rm -f $(DESTDIR)$(BINDIR)/congruity
	/bin/rm -f $(DESTDIR)$(BINDIR)/mhgui
	/bin/rm -rf $(DESTDIR)$(APPSHAREDIR)
	/bin/rm -f $(DESTDIR)$(MAN1DIR)/congruity.1
	/bin/rm -f $(DESTDIR)$(MAN1DIR)/mhgui.1
	/bin/rm -f $(DESTDIR)$(DESKTOPDIR)/congruity.desktop
	/bin/rm -f $(DESTDIR)$(DESKTOPDIR)/mhgui.desktop
ifeq ($(RUN_UPDATE_DESKTOP_DB),1)
	$(UPDATE_DESKTOP_DB) > /dev/null 2>&1 || :
endif

