PREFIX ?= /usr

BINDIR   := $(PREFIX)/bin
SHAREDIR := $(PREFIX)/share
MAN1DIR  := $(SHAREDIR)/man/man1

INSTALL ?= /usr/bin/install

all:
	@echo "Nothing to build, run 'make install' as root"

install:
	$(INSTALL) -D --mode=755 congruity $(BINDIR)/congruity
	mkdir -p --mode=755 $(SHAREDIR)/congruity
	$(INSTALL) -D --mode=644 *.png $(SHAREDIR)/congruity
	$(INSTALL) -D --mode=644 congruity.1 $(MAN1DIR)

uninstall:
	/bin/rm -f $(BINDIR)/congruity
	/bin/rm -rf $(SHAREDIR)/congruity
	/bin/rm -f $(MAN1DIR)/congruity.1

