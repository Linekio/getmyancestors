# coding: utf-8

# global imports
from __future__ import print_function
import re
import sys
import time
from urllib.parse import unquote
import getpass
import argparse
from concurrent.futures import ThreadPoolExecutor

# local imports
from getmyancestors.classes.tree import Tree
from getmyancestors.classes.session import Session



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
        "-m",
        "--marriage",
        action="store_true",
        default=False,
        help="Add spouses and couples information [False]",
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
        "--rate-limit",
        metavar="<INT>",
        type=int,
        help="Max # requests per second",
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
        "-o",
        "--outfile",
        metavar="<FILE>",
        type=argparse.FileType("w", encoding="UTF-8"),
        default=sys.stdout,
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
    parser.add_argument(
        "--client_id", metavar="<STR>", type=str, help="Use Specific Client ID"
    )
    parser.add_argument(
        "--redirect_uri", metavar="<STR>", type=str, help="Use Specific Redirect Uri"
    )
    parser.add_argument(
        "--no-sources",
        action="store_true",
        default=False,
        help="Skip downloading sources [False]",
    )
    parser.add_argument(
        "--no-notes",
        action="store_true",
        default=False,
        help="Skip downloading notes [False]",
    )
    parser.add_argument(
        "--no-memories",
        action="store_true",
        default=False,
        help="Skip downloading memories [False]",
    )
    parser.add_argument(
        "--concurrency",
        metavar="<INT>",
        type=int,
        default=10,
        help="Number of concurrent download threads [10]",
    )
    parser.add_argument(
        "--delay",
        metavar="<FLOAT>",
        type=float,
        default=0.1,
        help="Delay between requests in seconds [0.1]",
    )

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
    fs = Session(
        args.username,
        args.password,
        args.client_id,
        args.redirect_uri,
        args.verbose,
        args.logfile,
        args.timeout,
        args.rate_limit,
        args.delay,
    )
    if not fs.logged:
        sys.exit(2)
    _ = fs._
    tree = Tree(fs, no_sources=args.no_sources, no_memories=args.no_memories)

    # check LDS account
    if args.get_ordinances:
        test = fs.get_url(
            "/service/tree/tree-data/reservations/person/%s/ordinances" % fs.fid, {}, no_api=True
        )
        if not test or test["status"] != "OK":
            print("Need an LDS account")
            sys.exit(2)

    try:
        # add list of starting individuals to the family tree
        todo = args.individuals if args.individuals else [fs.fid]
        print(_("Downloading starting individuals..."), file=sys.stderr)
        tree.add_indis(todo)

        # download ancestors
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

        # download ordinances, notes and contributors
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
        with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
            futures = []
            for fid, indi in tree.indi.items():
                if not args.no_notes:
                    futures.append(executor.submit(indi.get_notes))
                if args.get_ordinances:
                    futures.append(executor.submit(tree.add_ordinances, fid))
                if args.get_contributors:
                    futures.append(executor.submit(indi.get_contributors))
            for fam in tree.fam.values():
                if not args.no_notes:
                    futures.append(executor.submit(fam.get_notes))
                if args.get_contributors:
                    futures.append(executor.submit(fam.get_contributors))
            for future in futures:
                future.result()

    finally:
        # compute number for family relationships and print GEDCOM file
        tree.reset_num()
        tree.print(args.outfile)
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
