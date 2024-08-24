# coding: utf-8

from __future__ import print_function

# global imports
import os
import sys
import argparse

# local imports
from getmyancestors.classes.tree import Indi, Fam, Tree
from getmyancestors.classes.gedcom import Gedcom

sys.path.append(os.path.dirname(sys.argv[0]))


def main():
    parser = argparse.ArgumentParser(
        description="Merge GEDCOM data from FamilySearch Tree (4 Jul 2016)",
        add_help=False,
        usage="mergemyancestors -i input1.ged input2.ged ... [options]",
    )
    try:
        parser.add_argument(
            "-i",
            metavar="<FILE>",
            nargs="+",
            type=argparse.FileType("r", encoding="UTF-8"),
            default=[sys.stdin],
            help="input GEDCOM files [stdin]",
        )
        parser.add_argument(
            "-o",
            metavar="<FILE>",
            nargs="?",
            type=argparse.FileType("w", encoding="UTF-8"),
            default=sys.stdout,
            help="output GEDCOM files [stdout]",
        )
    except TypeError:
        sys.stderr.write("Python >= 3.4 is required to run this script\n")
        sys.stderr.write("(see https://docs.python.org/3/whatsnew/3.4.html#argparse)\n")
        exit(2)

    # extract arguments from the command line
    try:
        parser.error = parser.exit
        args = parser.parse_args()
    except SystemExit as e:
        print(e.code)
        parser.print_help()
        exit(2)

    tree = Tree()

    indi_counter = 0
    fam_counter = 0

    # read the GEDCOM data
    for file in args.i:
        ged = Gedcom(file, tree)

        # add information about individuals
        for num in ged.indi:
            fid = ged.indi[num].fid
            if fid not in tree.indi:
                indi_counter += 1
                tree.indi[fid] = Indi(ged.indi[num].fid, tree, num=indi_counter)
            tree.indi[fid].fams_fid |= ged.indi[num].fams_fid
            tree.indi[fid].famc_fid |= ged.indi[num].famc_fid
            tree.indi[fid].name = ged.indi[num].name
            tree.indi[fid].birthnames = ged.indi[num].birthnames
            tree.indi[fid].nicknames = ged.indi[num].nicknames
            tree.indi[fid].aka = ged.indi[num].aka
            tree.indi[fid].married = ged.indi[num].married
            tree.indi[fid].gender = ged.indi[num].gender
            tree.indi[fid].facts = ged.indi[num].facts
            tree.indi[fid].notes = ged.indi[num].notes
            tree.indi[fid].sources = ged.indi[num].sources
            tree.indi[fid].memories = ged.indi[num].memories
            tree.indi[fid].baptism = ged.indi[num].baptism
            tree.indi[fid].confirmation = ged.indi[num].confirmation
            tree.indi[fid].initiatory = ged.indi[num].initiatory
            tree.indi[fid].endowment = ged.indi[num].endowment
            if not (tree.indi[fid].sealing_child and tree.indi[fid].sealing_child.famc):
                tree.indi[fid].sealing_child = ged.indi[num].sealing_child

        # add information about families
        for num in ged.fam:
            husb, wife = (ged.fam[num].husb_fid, ged.fam[num].wife_fid)
            if (husb, wife) not in tree.fam:
                fam_counter += 1
                tree.fam[(husb, wife)] = Fam(husb, wife, tree, fam_counter)
                tree.fam[(husb, wife)].tree = tree
            tree.fam[(husb, wife)].chil_fid |= ged.fam[num].chil_fid
            if ged.fam[num].fid:
                tree.fam[(husb, wife)].fid = ged.fam[num].fid
            if ged.fam[num].facts:
                tree.fam[(husb, wife)].facts = ged.fam[num].facts
            if ged.fam[num].notes:
                tree.fam[(husb, wife)].notes = ged.fam[num].notes
            if ged.fam[num].sources:
                tree.fam[(husb, wife)].sources = ged.fam[num].sources
            tree.fam[(husb, wife)].sealing_spouse = ged.fam[num].sealing_spouse

    # merge notes by text
    tree.notes = sorted(tree.notes, key=lambda x: x.text)
    for i, n in enumerate(tree.notes):
        if i == 0:
            n.num = 1
            continue
        if n.text == tree.notes[i - 1].text:
            n.num = tree.notes[i - 1].num
        else:
            n.num = tree.notes[i - 1].num + 1

    # compute number for family relationships and print GEDCOM file
    tree.reset_num()
    tree.print(args.o)


if __name__ == "__main__":
    main()
