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
	mkdir -p --mode=755 $(DESTDIR)$(APPSHAREDIR)
	$(INSTALL) --mode=644 *.png $(DESTDIR)$(APPSHAREDIR)
	mkdir -p --mode=755 $(DESTDIR)$(MAN1DIR)
	$(INSTALL) --mode=644 congruity.1 $(DESTDIR)$(MAN1DIR)
	mkdir -p --mode=755 $(DESTDIR)$(DESKTOPDIR)
	$(INSTALL) --mode=644 congruity.desktop $(DESTDIR)$(DESKTOPDIR)
ifeq ($(RUN_UPDATE_DESKTOP_DB),1)
	$(UPDATE_DESKTOP_DB) > /dev/null 2>&1 || :
endif

uninstall:
	/bin/rm -f $(DESTDIR)$(BINDIR)/congruity
	/bin/rm -rf $(DESTDIR)$(APPSHAREDIR)
	/bin/rm -f $(DESTDIR)$(MAN1DIR)/congruity.1
	/bin/rm -f $(DESTDIR)$(DESKTOPDIR)/congruity.desktop
ifeq ($(RUN_UPDATE_DESKTOP_DB),1)
	$(UPDATE_DESKTOP_DB) > /dev/null 2>&1 || :
endif

