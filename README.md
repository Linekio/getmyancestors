getmyancestors
==============

_getmyancestors_ is a python3 package that downloads family trees in GEDCOM format from FamilySearch.

This program is now in production phase, but bugs might still be present. Features will be added on request. It is provided as is.

The project is maintained at https://github.com/Linekio/getmyancestors. Visit here for the latest version and more information.

This script requires python3 and the modules indicated in the requirements.txt file. To install the modules, run in your terminal:


Installation
============

The easiest way to install _getmyancestors_ is to use pip:

`pip install getmyancestors`

Otherwise, you can download the source package and then execute in the folder:

`pip install .`

How to use
==========

With graphical user interface:

```
fstogedcom
```

Command line examples:

The username and password can also come from the `FS_USERNAME` and `FS_PASS` environment variables. Prefer that, or the prompt, over `-p`: a password on the command line is visible to other users in the process list.

```
FS_USERNAME=username FS_PASS=password getmyancestors -i LF7T-Y4C -o out.ged
```

Download four generations of ancestors for the main individual in your tree and output gedcom on stdout (will prompt for username and password):

```
getmyancestors
```

Download four generations of ancestors and output gedcom to a file while generating a verbode stderr (will prompt for username and password):

```
getmyancestors -o out.ged -v
```

Download four generations of ancestors for individual LF7T-Y4C and generate a verbose log file:

```
getmyancestors -u username -p password -i LF7T-Y4C -o out.ged -l out.log -v
```

Download six generations of ancestors for individual LF7T-Y4C and generate a verbose log file:

```
getmyancestors -a 6 -u username -p password -i LF7T-Y4C -o out.ged -l out.log -v
```

Download four generations of ancestors for individual LF7T-Y4C including all their children and their children spouses:

```
getmyancestors -d 1 -m -u username -p password -i LF7T-Y4C -o out.ged
```

Download six generations of ancestors for individuals L4S5-9X4 and LHWG-18F including all their children, grandchildren and their spouses:

```
getmyancestors -a 6 -d 2 -m -u username -p password -i L4S5-9X4 LHWG-18F -o out.ged
```

Download four generations of ancestors for individual LF7T-Y4C including LDS ordinances (need LDS account)

```
getmyancestors -c -u username -p password -i LF7T-Y4C -o out.ged
```

Merge two Gedcom files

```
mergemyancestors -i file1.ged file2.ged -o out.ged
```


Support
=======

Submit questions or suggestions, or feature requests by opening an Issue at https://github.com/Linekio/getmyancestors/issues

Donation
========

If this project help you, you can give me a tip :)

[![paypal](https://www.paypalobjects.com/en_US/i/btn/btn_donateCC_LG.gif)](https://www.paypal.com/cgi-bin/webscr?cmd=_s-xclick&hosted_button_id=98X3CY93XTAYJ)
