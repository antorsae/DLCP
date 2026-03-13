
SUBDIRS=gpsim.html.LyXconv

all: gpsim.ps gpsim.pdf

gpsim.ps: gpsim.lyx
	lyx -e ps gpsim.lyx

gpsim.pdf: gpsim.lyx
	lyx -e pdf gpsim.lyx

EXTRA_DIST = \
	screenshots/breadboard.png \
	screenshots/registerview.png \
	screenshots/scope1.png \
	screenshots/scope2.png  \
	screenshots/source_browser.png \
	screenshots/control_source.png \
	screenshots/breadboard_register.png \
	gpsim.html.LyXconv/Makefile \
	gpsim.html.LyXconv/elyxer_p3.py \
	gpsim.html.LyXconv/elyxer.py \
	gpsim.html.LyXconv/gpsim.html \
	metadata/gpsim.desktop \
	metadata/gpsim.appdata.xml \
	metadata/gpsim.png \
	makefile.mingw \
	gpsim.lyx \
	gpsim.pdf \
	gpsim.ps

MOSTLYCLEANFILES =  *~
CLEANFILES =  *~
DISTCLEANFILES =  *~
MAINTAINERCLEANFILES =  gpsim.ps gpsim.pdf *~ 
