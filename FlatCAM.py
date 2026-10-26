############################################################
# FlatCAM: 2D Post-processing for Manufacturing            #
# http://flatcam.org                                       #
# Author: Juan Pablo Caram (c)                             #
# Date: 2/5/2014                                           #
# MIT Licence                                              #
############################################################

import sys
import traceback

from PyQt6 import QtCore, QtWidgets
from FlatCAMApp import App


def debug_trace():
    """
    Set a tracepoint in the Python debugger that works with Qt
    :return: None
    """
    from PyQt6.QtCore import pyqtRemoveInputHook
    #from pdb import set_trace
    pyqtRemoveInputHook()
    #set_trace()


def excepthook(exc_type, exc_value, exc_tb):
    """
    PyQt6 aborts the application on any exception that escapes a Qt
    callback unless sys.excepthook is overridden. Print it instead and
    keep running, as PyQt4 did.
    """
    traceback.print_exception(exc_type, exc_value, exc_tb)


def main():
    debug_trace()
    sys.excepthook = excepthook

    # All X11 calling should be thread safe otherwise we have strange issues
    # QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_X11InitThreads)
    # NOTE: Never talk to the GUI from threads! This is why I commented the above.

    app = QtWidgets.QApplication(sys.argv)
    QtCore.QDir.setSearchPaths("share", ["share", "share/flatcam", "/usr/share/flatcam"])

    fc = App()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
