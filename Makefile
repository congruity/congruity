DESTDIR ?=
PREFIX  ?= /usr

BINDIR      ?= $(PREFIX)/bin
SHAREDIR    ?= $(PREFIX)/share
APPSHAREDIR ?= $(SHAREDIR)/congruity
MAN1DIR     ?= $(SHAREDIR)/man/man1

INSTALL ?= /usr/bin/install

all:
	@echo "Nothing to build, run 'make install' as root"

install:
	mkdir -p --mode=755 $(DESTDIR)$(BINDIR)
	$(INSTALL) --mode=755 congruity $(DESTDIR)$(BINDIR)/congruity
	mkdir -p --mode=755 $(DESTDIR)$(APPSHAREDIR)
	$(INSTALL) --mode=644 *.png $(DESTDIR)$(APPSHAREDIR)
	mkdir -p --mode=755 $(DESTDIR)$(MAN1DIR)
	$(INSTALL) --mode=644 congruity.1 $(DESTDIR)$(MAN1DIR)

uninstall:
	/bin/rm -f $(DESTDIR)$(BINDIR)/congruity
	/bin/rm -rf $(DESTDIR)$(APPSHAREDIR)
	/bin/rm -f $(DESTDIR)$(MAN1DIR)/congruity.1

