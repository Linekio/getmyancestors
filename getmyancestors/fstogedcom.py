#!/usr/bin/env python3
# coding: utf-8

# global imports
import os
import sys

try:
    from tkinter import PhotoImage, Tk
except ImportError:
    print("\n" + "=" * 60)
    print("ERROR: Tkinter is not available.")
    print("=" * 60)
    print("The graphical interface requires Tkinter.")
    print("\nInstallation instructions:")
    print("- Ubuntu/Debian: sudo apt install python3-tk")
    print("- Fedora/RHEL: sudo dnf install python3-tkinter")
    print("- macOS: brew install python-tk")
    print("- Windows: Usually included with Python installation")
    print("\n" + "=" * 60)
    sys.exit(1)

# local imports
from getmyancestors.classes.gui import FStoGEDCOM


def main():
    root = Tk()
    root.title("FamilySearch to GEDCOM")
    if sys.platform != "darwin":
        root.iconphoto(
            True,
            PhotoImage(file=os.path.join(os.path.dirname(__file__), "fstogedcom.png")),
        )
    fstogedcom = FStoGEDCOM(root)
    fstogedcom.mainloop()


if __name__ == "__main__":
    main()
