# coding: utf-8

# global imports
from __future__ import print_function
import re
import sys
import time
from urllib.parse import unquote
import getpass
import asyncio
import argparse

# local imports
from getmyancestors.classes.tree import Tree
from getmyancestors.classes.session import Session
from getmyancestors.classes.session import CachedSession


def main():
    parser = argparse.ArgumentParser(
        description="Retrieve GEDCOM data from FamilySearch Tree (4 Jul 2016)",
        add_help=False,
        usage="getmyancestors -u username -p password [options]",
    )
    parser.add_argument(
        "-u", "--username", metavar="<STR>", type=str, help="FamilySearch username"
    )
    parser.add_argument(
        "-p", "--password", metavar="<STR>", type=str, help="FamilySearch password"
    )
    parser.add_argument(
        "-i",
        "--individuals",
        metavar="<STR>",
        nargs="+",
        type=str,
        help="List of individual FamilySearch IDs for whom to retrieve ancestors",
    )
    parser.add_argument(
        "-e",
        "--exclude",
        metavar="<STR>",
        nargs="+",
        type=str,
        help="List of individual FamilySearch IDs to exclude from the tree",
    )
    parser.add_argument(
        "-a",
        "--ascend",
        metavar="<INT>",
        type=int,
        default=4,
        help="Number of generations to ascend [4]",
    )
    parser.add_argument(
        "-d",
        "--descend",
        metavar="<INT>",
        type=int,
        default=0,
        help="Number of generations to descend [0]",
    )
    parser.add_argument(
        '--distance',
        metavar="<INT>",
        type=int,
        default=0,
        help="The maxium distance from the starting individuals [0]. If distance is set, ascend and descend will be ignored.",
    )
    parser.add_argument(
        '--only-blood-relatives',
        action="store_true",
        default=True,
        help="Only include blood relatives in the tree [False]",
    )
    parser.add_argument(
        "-m",
        "--marriage",
        action="store_true",
        default=False,
        help="Add spouses and couples information [False]",
    )
    parser.add_argument(
        "--cache",
        action="store_true",
        default=False,
        help="Use of http cache to reduce requests during testing [False]",
    )
    parser.add_argument(
        "-r",
        "--get-contributors",
        action="store_true",
        default=False,
        help="Add list of contributors in notes [False]",
    )
    parser.add_argument(
        "-c",
        "--get_ordinances",
        action="store_true",
        default=False,
        help="Add LDS ordinances (need LDS account) [False]",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=False,
        help="Increase output verbosity [False]",
    )
    parser.add_argument(
        "-t",
        "--timeout",
        metavar="<INT>",
        type=int,
        default=60,
        help="Timeout in seconds [60]",
    )

    parser.add_argument(
        "-x",
        "--xml",
        action="store_true",
        default=False,
        help="To print the output in Gramps XML format [False]",
    )
    parser.add_argument(
        "--show-password",
        action="store_true",
        default=False,
        help="Show password in .settings file [False]",
    )
    parser.add_argument(
        "--save-settings",
        action="store_true",
        default=False,
        help="Save settings into file [False]",
    )
    parser.add_argument(
        "-g",
        "--geonames",
        metavar="<STR>",
        type=str,
        help="Geonames.org username in order to download place data",
    )
    try:
        parser.add_argument(
            "-o",
            "--outfile",
            metavar="<FILE>",
            # type=argparse.FileType("w", encoding="UTF-8"),
            # default=sys.stdout,
            help="output GEDCOM file [stdout]",
        )
        parser.add_argument(
            "-l",
            "--logfile",
            metavar="<FILE>",
            type=argparse.FileType("w", encoding="UTF-8"),
            default=False,
            help="output log file [stderr]",
        )
    except TypeError:
        sys.stderr.write("Python >= 3.4 is required to run this script\n")
        sys.stderr.write("(see https://docs.python.org/3/whatsnew/3.4.html#argparse)\n")
        sys.exit(2)

    # extract arguments from the command line
    try:
        parser.error = parser.exit
        args = parser.parse_args()
    except SystemExit:
        parser.print_help(file=sys.stderr)
        sys.exit(2)
    if args.individuals:
        for fid in args.individuals:
            if not re.match(r"[A-Z0-9]{4}-[A-Z0-9]{3}", fid):
                sys.exit("Invalid FamilySearch ID: " + fid)
    if args.exclude:
        for fid in args.exclude:
            if not re.match(r"[A-Z0-9]{4}-[A-Z0-9]{3}", fid):
                sys.exit("Invalid FamilySearch ID: " + fid)

    args.username = (
        args.username if args.username else input("Enter FamilySearch username: ")
    )
    args.password = (
        args.password
        if args.password
        else getpass.getpass("Enter FamilySearch password: ")
    )

    time_count = time.time()

    # Report settings used when getmyancestors is executed
    if args.save_settings and args.outfile.name != "<stdout>":

        def parse_action(act):
            if not args.show_password and act.dest == "password":
                return "******"
            value = getattr(args, act.dest)
            return str(getattr(value, "name", value))

        formatting = "{:74}{:\t>1}\n"
        settings_name = args.outfile.name.split(".")[0] + ".settings"
        try:
            with open(settings_name, "w") as settings_file:
                settings_file.write(
                    formatting.format("time stamp: ", time.strftime("%X %x %Z"))
                )
                for action in parser._actions:
                    settings_file.write(
                        formatting.format(
                            action.option_strings[-1], parse_action(action)
                        )
                    )
        except OSError as exc:
            print(
                "Unable to write %s: %s" % (settings_name, repr(exc)), file=sys.stderr
            )

    # initialize a FamilySearch session and a family tree object
    print("Login to FamilySearch...", file=sys.stderr)
    if args.cache:
        print("Using cache...", file=sys.stderr)
        fs = CachedSession(args.username, args.password, args.verbose, args.logfile, args.timeout)
    else:
        fs = Session(args.username, args.password, args.verbose, args.logfile, args.timeout)
    if not fs.logged:
        sys.exit(2)
    _ = fs._
    tree = Tree(
        fs, 
        exclude=args.exclude,
        geonames_key=args.geonames,
    )

    # check LDS account
    if args.get_ordinances:
        test = fs.get_url(
            "/service/tree/tree-data/reservations/person/%s/ordinances" % fs.fid, {}
        )
        if test["status"] != "OK":
            sys.exit(2)

    try:
        # add list of starting individuals to the family tree
        todo = args.individuals if args.individuals else [fs.fid]
        print(_("Downloading starting individuals..."), file=sys.stderr)
        tree.add_indis(todo)



        # download ancestors
        if args.distance == 0:
            todo = set(tree.indi.keys())
            done = set()
            for i in range(args.ascend):
                if not todo:
                    break
                done |= todo
                print(
                    _("Downloading %s. of generations of ancestors...") % (i + 1),
                    file=sys.stderr,
                )
                todo = tree.add_parents(todo) - done

            # download descendants
            todo = set(tree.indi.keys())
            done = set()
            for i in range(args.descend):
                if not todo:
                    break
                done |= todo
                print(
                    _("Downloading %s. of generations of descendants...") % (i + 1),
                    file=sys.stderr,
                )
                todo = tree.add_children(todo) - done

            # download spouses
            if args.marriage:
                print(_("Downloading spouses and marriage information..."), file=sys.stderr)
                todo = set(tree.indi.keys())
                tree.add_spouses(todo)

        else:
            todo_bloodline = set(tree.indi.keys())
            todo_others = set()
            done = set()
            for distance in range(args.distance):

                if not todo_bloodline and not todo_others:
                    break
                done |= todo_bloodline
                print(
                    _("Downloading individuals at distance %s...") % (distance + 1),
                    file=sys.stderr,
                )
                parents = tree.add_parents(todo_bloodline) - done
                children = tree.add_children(todo_bloodline) - done

                # download spouses
                if args.marriage:
                    print(_("Downloading spouses and marriage information..."), file=sys.stderr)
                    todo = set(tree.indi.keys())
                    tree.add_spouses(todo)

                # spouses = tree.add_spouses(todo_bloodline) - done

                todo_bloodline = parents | children
                # if args.only_blood_relatives:
                #     # Downloading non bloodline parents
                #     tree.add_parents(todo_others)

                #     # TODO what is a non bloodline person becomes bloodline on another branch?
                #     todo_others = spouses
                # else:
                    # todo_bloodline |= spouses

        # download ordinances, notes and contributors
        async def download_stuff(loop):
            futures = set()
            for fid, indi in tree.indi.items():
                futures.add(loop.run_in_executor(None, indi.get_notes))
                if args.get_ordinances:
                    futures.add(loop.run_in_executor(None, tree.add_ordinances, fid))
                if args.get_contributors:
                    futures.add(loop.run_in_executor(None, indi.get_contributors))
            for fam in tree.fam.values():
                futures.add(loop.run_in_executor(None, fam.get_notes))
                if args.get_contributors:
                    futures.add(loop.run_in_executor(None, fam.get_contributors))
            for future in futures:
                await future

        loop = asyncio.get_event_loop()
        print(
            _("Downloading notes")
            + (
                (("," if args.get_contributors else _(" and")) + _(" ordinances"))
                if args.get_ordinances
                else ""
            )
            + (_(" and contributors") if args.get_contributors else "")
            + "...",
            file=sys.stderr,
        )
        loop.run_until_complete(download_stuff(loop))

    finally:
        # compute number for family relationships and print GEDCOM file
        tree.reset_num()
        if args.xml:
            with open(args.outfile, "wb") as f:
                tree.printxml(f)
        else:
            with open(args.outfile, "w", encoding="UTF-8") as f:
                tree.print(f)
        print(
            _(
                "Downloaded %s individuals, %s families, %s sources and %s notes "
                "in %s seconds with %s HTTP requests."
            )
            % (
                str(len(tree.indi)),
                str(len(tree.fam)),
                str(len(tree.sources)),
                str(len(tree.notes)),
                str(round(time.time() - time_count)),
                str(fs.counter),
            ),
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
