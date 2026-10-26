#!/bin/sh -e
# "-e" exists on first error.

# System libraries and Tcl/Tk (FlatCAM's shell uses tkinter's Tcl interpreter).
sudo apt-get install python3-dev \
				python3-venv \
				python3-tk \
				libgeos-dev \
				libspatialindex-dev

# Python dependencies, in a virtual environment.
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
