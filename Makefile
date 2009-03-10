DESTDIR ?=
PREFIX  ?= /usr/local

BINDIR      ?= $(PREFIX)/bin
SHAREDIR    ?= $(PREFIX)/share
APPSHAREDIR ?= $(SHAREDIR)/congruity
MANDIR      ?= $(SHAREDIR)/man
MAN1DIR     ?= $(MANDIR)/man1

INSTALL ?= install

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

uninstall:
	/bin/rm -f $(DESTDIR)$(BINDIR)/congruity
	/bin/rm -rf $(DESTDIR)$(APPSHAREDIR)
	/bin/rm -f $(DESTDIR)$(MAN1DIR)/congruity.1

