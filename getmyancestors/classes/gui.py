# fstogedcom classes and functions
import asyncio
import os
import re
import tempfile
import time
from threading import Thread
from tkinter import IntVar, Menu, StringVar, TclError, filedialog, messagebox
from tkinter.ttk import Button, Checkbutton, Entry, Frame, Label, Notebook, Treeview

from diskcache import Cache

from getmyancestors.classes.gedcom import Gedcom
from getmyancestors.classes.session import Session
from getmyancestors.classes.translation import translations
from getmyancestors.classes.tree import Fam, Indi, Tree

tmp_dir = os.path.join(tempfile.gettempdir(), "fstogedcom")
cache = Cache(tmp_dir)
lang = cache.get("lang")


def _(string):
    if string in translations and lang in translations[string]:
        return translations[string][lang]
    return string


class EntryWithMenu(Entry):
    """Entry widget with right-clic menu to copy/cut/paste"""

    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self.bind("<Button-3>", self.click_right)

    def click_right(self, event):
        """open menu"""
        menu = Menu(self, tearoff=0)
        try:
            self.selection_get()
            state = "normal"
        except TclError:
            state = "disabled"
        menu.add_command(label=_("Copy"), command=self.copy, state=state)
        menu.add_command(label=_("Cut"), command=self.cut, state=state)
        menu.add_command(label=_("Paste"), command=self.paste)
        menu.post(event.x_root, event.y_root)

    def copy(self):
        """copy in clipboard"""
        self.clipboard_clear()
        text = self.selection_get()
        self.clipboard_append(text)

    def cut(self):
        """move in clipboard"""
        self.copy()
        self.delete("sel.first", "sel.last")

    def paste(self):
        """paste from clipboard"""
        try:
            text = self.selection_get(selection="CLIPBOARD")
            self.insert("insert", text)
        except TclError:
            pass


class FilesToMerge(Treeview):
    """List of GEDCOM files to merge"""

    def __init__(self, master, **kwargs):
        super().__init__(master, selectmode="extended", height=5, **kwargs)
        self.heading("#0", text=_("Files"))
        self.column("#0", width=300)
        self.files = dict()
        self.bind("<Button-3>", self.popup)

    def add_file(self, filename):
        """add a GEDCOM file"""
        if any(f.name == filename for f in self.files.values()):
            messagebox.showinfo(
                _("Error"),
                message=_("File already exist: ") + os.path.basename(filename),
            )
            return
        if not os.path.exists(filename):
            messagebox.showinfo(
                _("Error"), message=_("File not found: ") + os.path.basename(filename)
            )
            return
        file = open(filename, "r", encoding="utf-8")
        new_id = self.insert("", 0, text=os.path.basename(filename))
        self.files[new_id] = file

    def popup(self, event):
        """open menu to remove item"""
        item = self.identify_row(event.y)
        if item:
            menu = Menu(self, tearoff=0)
            menu.add_command(label=_("Remove"), command=self.delete_item(item))
            menu.post(event.x_root, event.y_root)

    def delete_item(self, item):
        """return a function to remove a file"""

        def delete():
            self.files[item].close()
            self.files.pop(item)
            self.delete(item)

        return delete


class Merge(Frame):
    """Merge GEDCOM widget"""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        warning = Label(
            self,
            font=("a", 7),
            wraplength=300,
            justify="center",
            text=_(
                "Warning: This tool should only be used to merge GEDCOM files from this software. "
                "If you use other GEDCOM files, the result is not guaranteed."
            ),
        )
        self.files_to_merge = FilesToMerge(self)
        self.btn_add_file = Button(self, text=_("Add files"), command=self.add_files)
        buttons = Frame(self, borderwidth=20)
        self.btn_quit = Button(buttons, text=_("Quit"), command=self.quit)
        self.btn_save = Button(buttons, text=_("Merge"), command=self.save)
        warning.pack()
        self.files_to_merge.pack()
        self.btn_add_file.pack()
        self.btn_quit.pack(side="left", padx=(0, 40))
        self.btn_save.pack(side="right", padx=(40, 0))
        buttons.pack(side="bottom")

    def add_files(self):
        """open file explorer to pick a file"""
        for filename in filedialog.askopenfilenames(
            title=_("Open"),
            defaultextension=".ged",
            filetypes=(("GEDCOM", ".ged"), (_("All files"), "*.*")),
        ):
            self.files_to_merge.add_file(filename)

    def save(self):
        """merge GEDCOM files"""
        if not self.files_to_merge.files:
            messagebox.showinfo(_("Error"), message=_("Please add GEDCOM files"))
            return

        filename = filedialog.asksaveasfilename(
            title=_("Save as"),
            defaultextension=".ged",
            filetypes=(("GEDCOM", ".ged"), (_("All files"), "*.*")),
        )
        tree = Tree()

        indi_counter = 0
        fam_counter = 0

        # read the GEDCOM data
        for file in self.files_to_merge.files.values():
            ged = Gedcom(file, tree)

            # add informations about individuals
            for num in ged.indi:
                fid = ged.indi[num].fid
                if fid not in tree.indi:
                    indi_counter += 1
                    tree.indi[fid] = Indi(tree=tree, num=indi_counter)
                    tree.indi[fid].tree = tree
                    tree.indi[fid].fid = ged.indi[num].fid
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
                tree.indi[fid].endowment = ged.indi[num].endowment
                if not (
                    tree.indi[fid].sealing_child and tree.indi[fid].sealing_child.famc
                ):
                    tree.indi[fid].sealing_child = ged.indi[num].sealing_child

            # add informations about families
            for num in ged.fam:
                husb, wife = (ged.fam[num].husb_fid, ged.fam[num].wife_fid)
                if (husb, wife) not in tree.fam:
                    fam_counter += 1
                    tree.fam[(husb, wife)] = Fam(husb, wife, tree, fam_counter)
                    tree.fam[(husb, wife)].tree = tree
                tree.fam[(husb, wife)].chil_fid |= ged.fam[num].chil_fid
                tree.fam[(husb, wife)].fid = ged.fam[num].fid
                tree.fam[(husb, wife)].facts = ged.fam[num].facts
                tree.fam[(husb, wife)].notes = ged.fam[num].notes
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
        with open(filename, "w", encoding="utf-8") as file:
            tree.print(file)
        messagebox.showinfo(_("Info"), message=_("Files successfully merged"))

    def quit(self):
        """prevent exception on quit during download"""
        super().quit()
        os._exit(1)


class SignIn(Frame):
    """Sign In widget"""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.username = StringVar()
        self.username.set(cache.get("username") or "")
        self.password = StringVar()
        self.password.set(cache.get("password") or "")
        label_username = Label(self, text=_("Username:"))
        entry_username = EntryWithMenu(self, textvariable=self.username, width=30)
        label_password = Label(self, text=_("Password:"))
        entry_password = EntryWithMenu(
            self, show="●", textvariable=self.password, width=30
        )

        self.save_password = IntVar()
        self.save_password.set(cache.get("save_password") or 0)
        check_save_password = Checkbutton(
            self,
            text=_("Save Password"),
            variable=self.save_password,
            onvalue=1,
            offvalue=0,
        )

        label_username.grid(row=0, column=0, pady=15, padx=(0, 5))
        entry_username.grid(row=0, column=1)
        label_password.grid(row=1, column=0, padx=(0, 5))
        entry_password.grid(row=1, column=1)
        check_save_password.grid(row=2, column=1, pady=5)
        entry_username.focus_set()
        entry_username.bind("<Key>", self.enter)
        entry_password.bind("<Key>", self.enter)

    def enter(self, evt):
        """enter event"""
        if evt.keysym in {"Return", "KP_Enter"}:
            self.master.master.command_in_thread(self.master.master.login)()


class StartIndis(Treeview):
    """List of starting individuals"""

    def __init__(self, master, **kwargs):
        super().__init__(
            master, selectmode="extended", height=5, columns=("fid",), **kwargs
        )
        self.heading("#0", text=_("Name"))
        self.column("#0", width=250)
        self.column("fid", width=80)
        self.indis = dict()
        self.heading("fid", text="Id")
        self.bind("<Button-3>", self.popup)

    def add_indi(self, fid):
        """add an individual fid"""
        if not fid:
            return None
        if fid in self.indis.values():
            messagebox.showinfo(_("Error"), message=_("ID already exist"))
            return None
        if not re.match(r"[A-Z0-9]{4}-[A-Z0-9]{3}", fid):
            messagebox.showinfo(
                _("Error"), message=_("Invalid FamilySearch ID: ") + fid
            )
            return None
        fs = self.master.master.master.fs
        data = fs.get_url("/platform/tree/persons/%s" % fid)
        if data and "persons" in data:
            if "names" in data["persons"][0]:
                for name in data["persons"][0]["names"]:
                    if name["preferred"]:
                        self.indis[
                            self.insert(
                                "", 0, text=name["nameForms"][0]["fullText"], values=fid
                            )
                        ] = fid
                        return True
        messagebox.showinfo(_("Error"), message=_("Individual not found"))
        return None

    def popup(self, event):
        """open menu to remove item"""
        item = self.identify_row(event.y)
        if item:
            menu = Menu(self, tearoff=0)
            menu.add_command(label=_("Remove"), command=self.delete_item(item))
            menu.post(event.x_root, event.y_root)

    def delete_item(self, item):
        """return a function to remove a fid"""

        def delete():
            self.indis.pop(item)
            self.delete(item)

        return delete


class Options(Frame):
    """Options form"""

    def __init__(self, master, ordinances=False, **kwargs):
        super().__init__(master, **kwargs)
        self.ancestors = IntVar()
        self.ancestors.set(4)
        self.descendants = IntVar()
        self.spouses = IntVar()
        self.ordinances = IntVar()
        self.contributors = IntVar()
        self.start_indis = StartIndis(self)
        self.fid = StringVar()
        btn = Frame(self)
        entry_fid = EntryWithMenu(btn, textvariable=self.fid, width=16)
        entry_fid.bind("<Key>", self.enter)
        label_ancestors = Label(self, text=_("Number of generations to ascend"))
        entry_ancestors = EntryWithMenu(self, textvariable=self.ancestors, width=5)
        label_descendants = Label(self, text=_("Number of generations to descend"))
        entry_descendants = EntryWithMenu(self, textvariable=self.descendants, width=5)
        btn_add_indi = Button(
            btn, text=_("Add a FamilySearch ID"), command=self.add_indi
        )
        btn_spouses = Checkbutton(
            self,
            text="\t" + _("Add spouses and couples information"),
            variable=self.spouses,
        )
        btn_ordinances = Checkbutton(
            self, text="\t" + _("Add Temple information"), variable=self.ordinances
        )
        btn_contributors = Checkbutton(
            self,
            text="\t" + _("Add list of contributors in notes"),
            variable=self.contributors,
        )
        self.start_indis.grid(row=0, column=0, columnspan=3)
        entry_fid.grid(row=0, column=0, sticky="w")
        btn_add_indi.grid(row=0, column=1, sticky="w")
        btn.grid(row=1, column=0, columnspan=2, sticky="w")
        entry_ancestors.grid(row=2, column=0, sticky="w")
        label_ancestors.grid(row=2, column=1, sticky="w")
        entry_descendants.grid(row=3, column=0, sticky="w")
        label_descendants.grid(row=3, column=1, sticky="w")
        btn_spouses.grid(row=4, column=0, columnspan=2, sticky="w")
        if ordinances:
            btn_ordinances.grid(row=5, column=0, columnspan=3, sticky="w")
        btn_contributors.grid(row=6, column=0, columnspan=3, sticky="w")
        entry_ancestors.focus_set()

    def add_indi(self):
        """add a fid"""
        if self.start_indis.add_indi(self.fid.get()):
            self.fid.set("")

    def enter(self, evt):
        """enter event"""
        if evt.keysym in {"Return", "KP_Enter"}:
            self.add_indi()


class Download(Frame):
    """Main widget"""

    def __init__(self, master, **kwargs):
        super().__init__(master, borderwidth=20, **kwargs)
        self.fs = None
        self.tree = None
        self.logfile = None

        # User information
        self.info_tree = False
        self.start_time = None
        info = Frame(self, borderwidth=10)
        self.info_label = Label(
            info,
            wraplength=350,
            borderwidth=20,
            justify="center",
            font=("a", 10, "bold"),
        )
        self.info_indis = Label(info)
        self.info_fams = Label(info)
        self.info_sources = Label(info)
        self.info_notes = Label(info)
        self.time = Label(info)
        self.info_label.grid(row=0, column=0, columnspan=2)
        self.info_indis.grid(row=1, column=0)
        self.info_fams.grid(row=1, column=1)
        self.info_sources.grid(row=2, column=0)
        self.info_notes.grid(row=2, column=1)
        self.time.grid(row=3, column=0, columnspan=2)

        self.form = Frame(self)
        self.sign_in = SignIn(self.form)
        self.options = None
        self.title = Label(
            self, text=_("Sign In to FamilySearch"), font=("a", 12, "bold")
        )
        buttons = Frame(self)
        self.btn_quit = Button(
            buttons, text=_("Quit"), command=Thread(target=self.quit).start
        )
        self.btn_valid = Button(
            buttons, text=_("Sign In"), command=self.command_in_thread(self.login)
        )
        self.title.pack()
        self.sign_in.pack()
        self.form.pack()
        self.btn_quit.pack(side="left", padx=(0, 40))
        self.btn_valid.pack(side="right", padx=(40, 0))
        info.pack()
        buttons.pack(side="bottom")
        self.pack()
        self.update_needed = False

    def info(self, text):
        """dislay informations"""
        self.info_label.config(text=text)

    def save(self):
        """save the GEDCOM file"""
        filename = filedialog.asksaveasfilename(
            title=_("Save as"),
            defaultextension=".ged",
            filetypes=(("GEDCOM", ".ged"), (_("All files"), "*.*")),
        )
        if not filename:
            return
        with open(filename, "w", encoding="utf-8") as file:
            self.tree.print(file)

    def login(self):
        """log in FamilySearch"""
        global _
        username = self.sign_in.username.get()
        password = self.sign_in.password.get()
        if not (username and password):
            messagebox.showinfo(
                message=_("Please enter your FamilySearch username and password.")
            )
            return
        self.btn_valid.config(state="disabled")
        self.info(_("Login to FamilySearch..."))
        self.logfile = open("download.log", "w", encoding="utf-8")
        self.fs = Session(
            self.sign_in.username.get(),
            self.sign_in.password.get(),
            verbose=True,
            logfile=self.logfile,
            timeout=1,
        )
        if not self.fs.logged:
            messagebox.showinfo(
                _("Error"), message=_("The username or password was incorrect")
            )
            self.btn_valid.config(state="normal")
            self.info("")
            return
        self.tree = Tree(self.fs)
        _ = self.fs._
        self.title.config(text=_("Options"))
        cache.delete("lang")
        cache.add("lang", self.fs.lang)
        cache.delete("username")
        cache.add("username", username)

        cache.delete("password")
        # cache password  only when checked

        save_pass = self.sign_in.save_password.get()
        if save_pass == 1:
            cache.add("password", password)

        cache.delete("save_password")
        cache.add("save_password", save_pass)

        url = "/service/tree/tree-data/reservations/person/%s/ordinances" % self.fs.fid
        lds_account = self.fs.get_url(url, {}, no_api=True).get("status") == "OK"
        self.options = Options(self.form, lds_account)
        self.info("")
        self.sign_in.destroy()
        self.options.pack()
        self.master.change_lang()
        self.btn_valid.config(
            command=self.command_in_thread(self.download),
            state="normal",
            text=_("Download"),
        )
        self.options.start_indis.add_indi(self.fs.fid)
        self.update_needed = False

    def quit(self):
        """prevent exception during download"""
        self.update_needed = False
        if self.logfile:
            self.logfile.close()
        super().quit()
        os._exit(1)

    def download(self):
        """download family tree"""
        todo = [
            self.options.start_indis.indis[key]
            for key in sorted(self.options.start_indis.indis)
        ]
        for fid in todo:
            if not re.match(r"[A-Z0-9]{4}-[A-Z0-9]{3}", fid):
                messagebox.showinfo(
                    _("Error"), message=_("Invalid FamilySearch ID: ") + fid
                )
                return
        self.start_time = time.time()
        self.options.destroy()
        self.form.destroy()
        self.title.config(text="FamilySearch to GEDCOM")
        self.btn_valid.config(state="disabled")
        self.info(_("Downloading starting individuals..."))
        self.info_tree = True
        self.tree.add_indis(todo)
        todo = set(todo)
        done = set()
        for i in range(self.options.ancestors.get()):
            if not todo:
                break
            done |= todo
            self.info(_("Downloading %s. of generations of ancestors...") % (i + 1))
            todo = self.tree.add_parents(todo) - done

        todo = set(self.tree.indi.keys())
        done = set()
        for i in range(self.options.descendants.get()):
            if not todo:
                break
            done |= todo
            self.info(_("Downloading %s. of generations of descendants...") % (i + 1))
            todo = self.tree.add_children(todo) - done

        if self.options.spouses.get():
            self.info(_("Downloading spouses and marriage information..."))
            todo = set(self.tree.indi.keys())
            self.tree.add_spouses(todo)
        ordi = self.options.ordinances.get()
        cont = self.options.contributors.get()

        async def download_stuff(loop):
            futures = set()
            for fid, indi in self.tree.indi.items():
                futures.add(loop.run_in_executor(None, indi.get_notes))
                if ordi:
                    futures.add(
                        loop.run_in_executor(None, self.tree.add_ordinances, fid)
                    )
                if cont:
                    futures.add(loop.run_in_executor(None, indi.get_contributors))
            for fam in self.tree.fam.values():
                futures.add(loop.run_in_executor(None, fam.get_notes))
                if cont:
                    futures.add(loop.run_in_executor(None, fam.get_contributors))
            for future in futures:
                await future

        loop = asyncio.get_event_loop()
        self.info(
            _("Downloading notes")
            + ((("," if cont else _(" and")) + _(" ordinances")) if ordi else "")
            + (_(" and contributors") if cont else "")
            + "..."
        )
        loop.run_until_complete(download_stuff(loop))

        self.tree.reset_num()
        self.btn_valid.config(command=self.save, state="normal", text=_("Save"))
        self.info(text=_("Success ! Click below to save your GEDCOM file"))
        self.update_info_tree()
        self.update_needed = False

    def command_in_thread(self, func):
        """command to update widget in a new Thread"""

        def res():
            self.update_needed = True
            Thread(target=self.update_gui).start()
            Thread(target=func).start()

        return res

    def update_info_tree(self):
        """update informations"""
        if self.info_tree and self.start_time and self.tree:
            self.info_indis.config(text=_("Individuals: %s") % len(self.tree.indi))
            self.info_fams.config(text=_("Families: %s") % len(self.tree.fam))
            self.info_sources.config(text=_("Sources: %s") % len(self.tree.sources))
            self.info_notes.config(text=_("Notes: %s") % len(self.tree.notes))
            t = round(time.time() - self.start_time)
            minutes = t // 60
            seconds = t % 60
            self.time.config(
                text=_("Elapsed time: %s:%s") % (minutes, str(seconds).zfill(2))
            )

    def update_gui(self):
        """update widget"""
        while self.update_needed:
            self.update_info_tree()
            self.master.update()
            time.sleep(0.1)


class FStoGEDCOM(Notebook):
    """Main notebook"""

    def __init__(self, master, **kwargs):
        super().__init__(master, width=400, **kwargs)
        self.download = Download(self)
        self.merge = Merge(self)
        self.add(self.download, text=_("Download GEDCOM"))
        self.add(self.merge, text=_("Merge GEDCOMs"))
        self.pack()

    def change_lang(self):
        """update text with user's language"""
        self.tab(self.index(self.download), text=_("Download GEDCOM"))
        self.tab(self.index(self.merge), text=_("Merge GEDCOMs"))
        self.download.btn_quit.config(text=_("Quit"))
        self.merge.btn_quit.config(text=_("Quit"))
        self.merge.btn_save.config(text=_("Merge"))
        self.merge.btn_add_file.config(text=_("Add files"))
