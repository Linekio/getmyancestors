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
from getmyancestors.classes.gedcom import Gedcom

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
        help="Number of generations to ascend [4] or end level for resume relative to start level",
    )
    parser.add_argument(
        "-d",
        "--descend",
        metavar="<INT>",
        type=int,
        default=0,
        help="Number of generations to descend [0] or start level for resume (-N means N generations above -i)",
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
        "--client_id", metavar="<STR>", type=str, help="Use Specific Client ID"
    )
    parser.add_argument(
        "--redirect_uri", metavar="<STR>", type=str, help="Use Specific Redirect Uri"
    )
    # === MODIFICAÇÃO: Adicionar opção --resume-from ===
    parser.add_argument(
        "--resume-from",
        metavar="<FILE>",
        type=argparse.FileType("r", encoding="UTF-8"),
        help="Resume download from existing GEDCOM file (requires -i as reference point)",
    )
    # ================================================

    # extract arguments from the command line
    try:
        parser.error = parser.exit
        args = parser.parse_args()
    except SystemExit:
        parser.print_help(file=sys.stderr)
        sys.exit(2)
        
    # Verificação de argumentos para --resume-from
    if args.resume_from and not args.individuals:
        print("Error: -i/--individuals is required when using --resume-from as reference point.", file=sys.stderr)
        sys.exit(2)
        
    if args.individuals:
        for fid in args.individuals:
            if not re.match(r"[A-Z0-9]{4}-[A-Z0-9]{3}", fid):
                sys.exit("Invalid FamilySearch ID: " + fid)
                
    # Solicitar credenciais
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
        args.timeout
    )
    if not fs.logged:
        sys.exit(2)
    _ = fs._

    # === MODIFICAÇÃO: Lógica para --resume-from ===
    tree = Tree(fs) # Criar a árvore associada à sessão
    
    if args.resume_from:
        print(_("Resuming from existing GEDCOM file with reference point..."), file=sys.stderr)
        print(_("Reference individual(s): %s") % ", ".join(args.individuals), file=sys.stderr)
        print(_("Resume start offset (descend): %s, Resume generations (ascend): %s") % (args.descend, args.ascend), file=sys.stderr)
        
        # 1. Carregar o arquivo GEDCOM existente
        ged = Gedcom(args.resume_from, tree)
        
        # 2. Coletar os FIDs dos indivíduos carregados
        fids_from_ged = set()
        for num in ged.indi:
            if ged.indi[num].fid:
                fids_from_ged.add(ged.indi[num].fid)
                
        print(_("Loaded %s individuals from GEDCOM file.") % len(fids_from_ged), file=sys.stderr)
        
        if not fids_from_ged:
            print(_("Error: No individuals with FamilySearch IDs found in GEDCOM file."), file=sys.stderr)
            sys.exit(1)
            
        # 3. Buscar dados completos desses indivíduos no FamilySearch
        print(_("Fetching complete data for individuals from FamilySearch..."), file=sys.stderr)
        tree.add_indis(fids_from_ged)
        
        # 4. Identificar os verdadeiros pontos de partida para continuar a busca
        # Estratégia: Encontrar indivíduos que têm pais conhecidos no FamilySearch,
        # mas que esses pais não estão no arquivo GEDCOM carregado.
        start_points = set()
        
        # Para cada indivíduo no arquivo GEDCOM carregado
        for fid in fids_from_ged:
            # Verificar se este indivíduo tem pais conhecidos no FamilySearch
            if fid in tree.indi:
                indi = tree.indi[fid]
                # Se este indivíduo tem pais conhecidos (famc_fid não vazio)
                if indi.famc_fid:
                    # Verificar se todos os pais estão no arquivo GEDCOM carregado
                    all_parents_loaded = True
                    for parent_pair in indi.famc_fid:
                        husb_fid, wife_fid = parent_pair
                        if (husb_fid and husb_fid not in fids_from_ged) or (wife_fid and wife_fid not in fids_from_ged):
                            all_parents_loaded = False
                            break
                    
                    # Se nem todos os pais estão carregados, este indivíduo é um ponto de partida
                    if not all_parents_loaded:
                        start_points.add(fid)
        
        # 5. Calcular o conjunto inicial (todo) com base no offset
        todo = set()
        
        if args.descend == 0:
            # -d 0: Começar a busca a partir dos pontos de partida identificados
            todo = start_points
            if todo:
                print(_("Starting resume from %s individuals that have missing parents.") % len(todo), file=sys.stderr)
            else:
                # Se não encontramos pontos de partida específicos, usar todos os indivíduos carregados
                # como fallback (isso pode acontecer se todos os pais já estiverem no arquivo)
                print(_("No specific starting points found. Using all individuals as starting points."), file=sys.stderr)
                todo = fids_from_ged
        
        elif args.descend < 0:
            # -d < 0: Subir N gerações a partir dos indivíduos de referência
            steps_up = -args.descend
            current_level_fids = set(args.individuals)
            
            # Buscar dados dos indivíduos de referência
            tree.add_indis(args.individuals)
            
            # Subir o número necessário de gerações usando dados já carregados
            for step in range(steps_up):
                next_level_fids = set()
                for fid in current_level_fids:
                    if fid in tree.indi:
                        for parent_pair in tree.indi[fid].famc_fid:
                            husb_fid, wife_fid = parent_pair
                            if husb_fid:
                                next_level_fids.add(husb_fid)
                            if wife_fid:
                                next_level_fids.add(wife_fid)
                
                if not next_level_fids:
                    print(_("No more ancestors found at step %s. Stopping climb.") % (step + 1), file=sys.stderr)
                    break
                current_level_fids = next_level_fids
                
            todo = current_level_fids
            print(_("Starting resume from %s individuals %s generations above reference point.") % (len(todo), steps_up), file=sys.stderr)
        
        else:
            # args.descend > 0: Descida não é aplicável para busca ancestral
            print(_("Descend value > 0 is not applicable for ancestral search. Starting from reference individuals."), file=sys.stderr)
            # Buscar dados dos indivíduos de referência
            tree.add_indis(args.individuals)
            todo = set(args.individuals)
        
        # Se não encontramos ninguém para começar, usar os indivíduos de referência
        if not todo:
            print(_("No starting individuals found. Using reference individuals."), file=sys.stderr)
            todo = set(args.individuals)
            
        print(_("Resumed with %s individuals to start from.") % len(todo), file=sys.stderr)
        
        # 6. Baixar as gerações solicitadas
        done = set()
        for i in range(args.ascend):
            if not todo:
                break
            done |= todo
            print(
                _("Downloading %s. of generations of ancestors (from resume point)...") % (i + 1),
                file=sys.stderr,
            )
            todo = tree.add_parents(todo) - done
            
    else:
        # Comportamento original para download inicial
        initial_fids = args.individuals if args.individuals else [fs.fid]
        print(_("Downloading starting individuals..."), file=sys.stderr)
        tree.add_indis(initial_fids)
        todo = set(tree.indi.keys())
        
        # download ancestors (comportamento original)
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
    # ================================================

    # download descendants (comum a ambos os modos)
    # Nota: Esta parte pode precisar de ajuste se for para suportar descendência na retomada
    # Por enquanto, mantém o comportamento original somente no modo normal
    if not args.resume_from: # Só baixar descendentes no modo normal
        todo_desc = set(tree.indi.keys())
        done_desc = set()
        for i in range(args.descend):
            if not todo_desc:
                break
            done_desc |= todo_desc
            print(
                _("Downloading %s. of generations of descendants...") % (i + 1),
                file=sys.stderr,
            )
            todo_desc = tree.add_children(todo_desc) - done_desc
    else:
        # No modo de retomada, não baixamos descendentes automaticamente
        # a menos que seja especificado de outra forma
        pass
        
    # download spouses
    if args.marriage:
        print(_("Downloading spouses and marriage information..."), file=sys.stderr)
        todo_spouses = set(tree.indi.keys())
        tree.add_spouses(todo_spouses)
        
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