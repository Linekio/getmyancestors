# coding: utf-8

# global imports
from __future__ import print_function
import re
import sys
import time
import logging
from urllib.parse import unquote
import getpass
import asyncio
import argparse

# local imports
from getmyancestors.classes.tree import Tree
from getmyancestors.classes.session import Session, logger



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
        "--concurrency",
        metavar="<INT>",
        type=int,
        default=20,
        help="number of concurrent worker threads [20]",
    )
    parser.add_argument(
        "--max-attempts",
        metavar="<INT>",
        type=int,
        default=10,
        help="max retry attempts per failed request [10]",
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
        "--client_id", metavar="<STR>", type=str, help="Use Specific Client ID"
    )
    parser.add_argument(
        "--redirect_uri", metavar="<STR>", type=str, help="Use Specific Redirect Uri"
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

    # configure logging
    log_format = "%(asctime)s %(levelname)-8s %(message)s"
    log_datefmt = "%Y-%m-%d %H:%M:%S"
    handlers = []
    handlers.append(logging.StreamHandler(sys.stderr))
    if args.logfile:
        handlers.append(logging.FileHandler(args.logfile, encoding="UTF-8"))
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format=log_format,
        datefmt=log_datefmt,
        handlers=handlers,
    )
    for name in ("urllib3",):
        logging.getLogger(name).setLevel(logging.WARNING)

    # initialize a FamilySearch session and a family tree object
    logger.info("Login to FamilySearch...")
    fs = Session(
        args.username,
        args.password,
        args.client_id,
        args.redirect_uri,
        args.verbose,
        None,  # logfile handled by logging config
        args.timeout,
        concurrency=args.concurrency,
        max_attempts=args.max_attempts,
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
            logger.warning("Need an LDS account")
            sys.exit(2)

    try:
        # add list of starting individuals to the family tree
        todo = args.individuals if args.individuals else [fs.fid]
        logger.info(_("Downloading starting individuals..."))
        tree.add_indis(todo)

        # download ancestors
        todo = set(tree.indi.keys())
        done = set()
        for i in range(args.ascend):
            if not todo:
                break
            done |= todo
            logger.info(
                _("Downloading generation %s of ancestors...") % (i + 1)
            )
            todo = tree.add_parents(todo) - done

        # download descendants
        todo = set(tree.indi.keys())
        done = set()
        for i in range(args.descend):
            if not todo:
                break
            done |= todo
            logger.info(
                _("Downloading generation %s of descendants...") % (i + 1)
            )
            todo = tree.add_children(todo) - done

        # download spouses
        if args.marriage:
            logger.info(_("Downloading spouses and marriage information..."))
            todo = set(tree.indi.keys())
            tree.add_spouses(todo)

        # download ordinances, notes and contributors
        async def download_stuff(loop):
            futures = set()
            for fid, indi in tree.indi.items():
                if not args.no_notes:
                    futures.add(loop.run_in_executor(None, indi.get_notes))
                if args.get_ordinances:
                    futures.add(loop.run_in_executor(None, tree.add_ordinances, fid))
                if args.get_contributors:
                    futures.add(loop.run_in_executor(None, indi.get_contributors))
            for fam in tree.fam.values():
                if not args.no_notes:
                    futures.add(loop.run_in_executor(None, fam.get_notes))
                if args.get_contributors:
                    futures.add(loop.run_in_executor(None, fam.get_contributors))
            for future in futures:
                await future

        loop = asyncio.get_event_loop()
        logger.info(
            _("Downloading notes")
            + (
                (("," if args.get_contributors else _(" and")) + _(" ordinances"))
                if args.get_ordinances
                else ""
            )
            + (_(" and contributors") if args.get_contributors else "")
            + "..."
        )
        loop.run_until_complete(download_stuff(loop))

    finally:
        # Wait for all workers to drain the request queue
        queued = fs.pending
        if queued:
            logger.info("Waiting for %d pending requests...", queued)
        fs.stop_workers()

        # compute number for family relationships and print GEDCOM file
        tree.reset_num()
        tree.print(args.outfile)
        elapsed = round(time.time() - time_count)
        logger.info(
            _(
                "Downloaded %s individuals, %s families, %s sources and %s notes "
                "in %s seconds with %s HTTP requests."
            )
            % (
                str(len(tree.indi)),
                str(len(tree.fam)),
                str(len(tree.sources)),
                str(len(tree.notes)),
                str(elapsed),
                str(fs.counter),
            ),
        )
        logger.info("Statistics: retries=%d, max_attempts_reached=%d, backoff_time=%.1fs, status_codes=%s",
                     fs.stats.retry_count, fs.stats.max_retries_reached,
                     fs.stats.backoff_time / fs.concurrency, dict(fs.stats.status_codes))


if __name__ == "__main__":
    main()
