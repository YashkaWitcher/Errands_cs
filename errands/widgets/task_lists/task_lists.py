# Copyright 2023 Vlad Krupinskii <mrvladus@yandex.ru>
# SPDX-License-Identifier: MIT

from uuid import uuid4
from icalendar import Calendar
from errands.utils.data import UserData
from errands.utils.functions import get_children
from errands.lib.gsettings import GSettings
from errands.lib.logging import Log
from errands.lib.sync.sync import Sync
from errands.widgets.components import Box
from errands.widgets.task_lists.task_lists_item import TaskListsItem
from errands.widgets.task import Task
from errands.widgets.task_list.task_list import TaskList
from gi.repository import Adw, Gtk, Gio, GObject, Gdk


class TaskLists(Adw.Bin):
    def __init__(self, window, stack: Gtk.Stack):
        super().__init__()
        self.stack: Gtk.Stack = stack
        self.window = window
        self._build_ui()
        self._add_actions()
        self._load_lists()

    def _add_actions(self) -> None:
        group = Gio.SimpleActionGroup()
        self.insert_action_group(name="lists", group=group)

        def _create_action(name: str, callback: callable) -> None:
            action: Gio.SimpleAction = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            group.add_action(action)

        def _add(*args) -> None:
            pass

        def _backup_create(*args) -> None:
            pass

        def _backup_load(*args) -> None:
            pass

        def _import(*args) -> None:
            def _confirm(dialog: Gtk.FileDialog, res) -> None:
                try:
                    file: Gio.File = dialog.open_finish(res)
                except:
                    Log.debug("Lists: Import cancelled")
                    return
                with open(file.get_path(), "r") as f:
                    calendar: Calendar = Calendar.from_ical(f.read())
                    # List name
                    name = calendar.get(
                        "X-WR-CALNAME", file.get_basename().rstrip(".ics")
                    )
                    if name in [
                        i[0]
                        for i in UserData.run_sql("SELECT name FROM lists", fetch=True)
                    ]:
                        name = f"{name}_{uuid4()}"
                    # Create list
                    uid: str = UserData.add_list(name)
                    # Add tasks
                    for todo in calendar.walk("VTODO"):
                        # Tags
                        if (tags := todo.get("CATEGORIES", "")) != "":
                            tags = ",".join(
                                [
                                    i.to_ical().decode("utf-8")
                                    for i in (
                                        tags if isinstance(tags, list) else tags.cats
                                    )
                                ]
                            )
                        # Start
                        if (start := todo.get("DTSTART", "")) != "":
                            start = (
                                todo.get("DTSTART", "")
                                .to_ical()
                                .decode("utf-8")
                                .strip("Z")
                            )
                        else:
                            start = ""
                        # End
                        if (end := todo.get("DUE", todo.get("DTEND", ""))) != "":
                            end = (
                                todo.get("DUE", todo.get("DTEND", ""))
                                .to_ical()
                                .decode("utf-8")
                                .strip("Z")
                            )
                        else:
                            end = ""
                        UserData.add_task(
                            color=todo.get("X-ERRANDS-COLOR", ""),
                            completed=str(todo.get("STATUS", "")) == "COMPLETED",
                            end_date=end,
                            list_uid=uid,
                            notes=str(todo.get("DESCRIPTION", "")),
                            parent=str(todo.get("RELATED-TO", "")),
                            percent_complete=int(todo.get("PERCENT-COMPLETE", 0)),
                            priority=int(todo.get("PRIORITY", 0)),
                            start_date=start,
                            tags=tags,
                            text=str(todo.get("SUMMARY", "")),
                            uid=todo.get("UID", None),
                        )
                self.update_ui()
                self.window.add_toast(_("Imported"))
                Sync.sync()

            filter = Gtk.FileFilter()
            filter.add_pattern("*.ics")
            dialog = Gtk.FileDialog(default_filter=filter)
            dialog.open(self.window, None, _confirm)

        _create_action("add", _add)
        _create_action("backup_create", _backup_create)
        _create_action("backup_load", _backup_load)
        _create_action("import", _import)

    def _build_ui(self) -> None:
        hb = Adw.HeaderBar(
            title_widget=Gtk.Label(
                label=_("Errands"),
                css_classes=["heading"],
            )
        )
        # Import menu
        import_menu: Gio.Menu = Gio.Menu.new()
        import_menu.append(_("Import List"), "lists.import")
        # Add list button
        self.add_list_btn = Adw.SplitButton(
            icon_name="list-add-symbolic",
            tooltip_text=_("Add List"),
            menu_model=import_menu,
            dropdown_tooltip=_("More Options"),
        )
        self.add_list_btn.connect("clicked", self.on_add_btn_clicked)
        hb.pack_start(self.add_list_btn)

        # Main menu
        menu: Gio.Menu = Gio.Menu.new()
        top_section = Gio.Menu.new()
        top_section.append(_("Sync / Fetch Tasks"), "app.sync")
        backup_submenu = Gio.Menu.new()
        backup_submenu.append(_("Create"), "lists.backup_create")
        backup_submenu.append(_("Load"), "lists.backup_load")
        # top_section.append_submenu(_("Backup"), backup_submenu)
        menu.append_section(None, top_section)
        bottom_section = Gio.Menu.new()
        bottom_section.append(_("Preferences"), "app.preferences")
        bottom_section.append(_("Keyboard Shortcuts"), "win.show-help-overlay")
        bottom_section.append(_("About Errands"), "app.about")
        menu.append_section(None, bottom_section)
        menu_btn = Gtk.MenuButton(
            menu_model=menu,
            primary=True,
            icon_name="open-menu-symbolic",
            tooltip_text=_("Main Menu"),
        )
        hb.pack_end(menu_btn)

        # Sync indicator
        self.sync_indicator = Gtk.Spinner(
            tooltip_text=_("Syncing..."), visible=False, spinning=True
        )
        hb.pack_end(self.sync_indicator)

        # Lists
        self.lists = Gtk.ListBox(css_classes=["navigation-sidebar"])
        self.lists.connect("row-selected", self.on_list_swiched)
        # Status page
        self.status_page = Adw.StatusPage(
            title=_("Add new List"),
            description=_('Click "+" button'),
            icon_name="errands-lists-symbolic",
            css_classes=["compact"],
            vexpand=True,
        )
        # Trash button
        self.trash_btn = Gtk.Button(
            child=Adw.ButtonContent(
                icon_name="errands-trash-symbolic",
                label=_("Trash"),
                halign="center",
            ),
            css_classes=["flat"],
            margin_top=6,
            margin_bottom=6,
            margin_end=6,
            margin_start=6,
        )
        self.trash_btn.connect("clicked", self.on_trash_btn_clicked)
        trash_drop_ctrl = Gtk.DropTarget.new(actions=Gdk.DragAction.MOVE, type=Task)
        trash_drop_ctrl.connect("drop", lambda _d, t, _x, _y: t.delete())
        self.trash_btn.add_controller(trash_drop_ctrl)
        # Toolbar view
        toolbar_view = Adw.ToolbarView(
            content=Gtk.ScrolledWindow(
                child=Box(
                    children=[self.lists, self.status_page], orientation="vertical"
                ),
                propagate_natural_height=True,
            )
        )
        toolbar_view.add_top_bar(hb)
        toolbar_view.add_bottom_bar(self.trash_btn)
        self.set_child(toolbar_view)

    def add_list(self, name, uid) -> Gtk.ListBoxRow:
        task_list = TaskList(self.window, uid, self)
        page: Adw.ViewStackPage = self.stack.add_titled(
            child=task_list, name=name, title=name
        )
        task_list.title.bind_property(
            "title", page, "title", GObject.BindingFlags.SYNC_CREATE
        )
        task_list.title.bind_property(
            "title", page, "name", GObject.BindingFlags.SYNC_CREATE
        )
        row = TaskListsItem(task_list, self.lists, self, self.window)
        self.lists.append(row)
        return row

    def on_add_btn_clicked(self, btn) -> None:
        def _entry_activated(_, dialog):
            if dialog.get_response_enabled("add"):
                dialog.response("add")
                dialog.close()

        def _entry_changed(entry, _, dialog):
            text = entry.props.text.strip(" \n\t")
            names = [i["name"] for i in UserData.get_lists_as_dicts()]
            dialog.set_response_enabled("add", text and text not in names)

        def _confirm(_, res, entry):
            if res == "cancel":
                return

            name = entry.props.text.rstrip().lstrip()
            uid = UserData.add_list(name)
            row = self.add_list(name, uid)
            self.lists.select_row(row)
            Sync.sync()

        entry = Gtk.Entry(placeholder_text=_("New List Name"))
        dialog = Adw.MessageDialog(
            transient_for=self.window,
            hide_on_close=True,
            heading=_("Add List"),
            default_response="add",
            close_response="cancel",
            extra_child=entry,
        )
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("add", _("Add"))
        dialog.set_response_enabled("add", False)
        dialog.set_response_appearance("add", Adw.ResponseAppearance.SUGGESTED)
        dialog.connect("response", _confirm, entry)
        entry.connect("activate", _entry_activated, dialog)
        entry.connect("notify::text", _entry_changed, dialog)
        dialog.present()

    def on_trash_btn_clicked(self, _btn) -> None:
        self.lists.unselect_all()
        self.stack.set_visible_child_name("trash")
        self.window.split_view.set_show_content(True)
        self.window.split_view_inner.set_show_sidebar(False)

    def on_list_swiched(self, _, row: Gtk.ListBoxRow) -> None:
        Log.debug("Lists: Switch list")
        if row:
            name = row.label.get_label()
            self.stack.set_visible_child_name(name)
            self.window.split_view.set_show_content(True)
            GSettings.set("last-open-list", "s", name)
            self.status_page.set_visible(False)

    def get_lists(self) -> list[TaskList]:
        lists: list[TaskList] = []
        pages: Adw.ViewStackPages = self.stack.get_pages()
        for i in range(pages.get_n_items()):
            child = pages.get_item(i).get_child()
            if isinstance(child, TaskList):
                lists.append(child)
        return lists

    def _load_lists(self) -> None:
        # Add lists
        lists = [i for i in UserData.get_lists_as_dicts() if not i["deleted"]]
        for list in lists:
            row = self.add_list(list["name"], list["uid"])
            if GSettings.get("last-open-list") == list["name"]:
                self.lists.select_row(row)
        self.status_page.set_visible(len(lists) == 0)

    def update_ui(self) -> None:
        Log.debug("Lists: Update UI...")

        # Delete lists
        uids = [i["uid"] for i in UserData.get_lists_as_dicts()]
        for row in get_children(self.lists):
            if row.uid not in uids:
                prev_child = row.get_prev_sibling()
                next_child = row.get_next_sibling()
                list = row.task_list
                self.stack.remove(list)
                if prev_child or next_child:
                    self.lists.select_row(prev_child or next_child)
                self.lists.remove(row)

        # Update old lists
        for list in self.get_lists():
            list.update_ui()

        # Create new lists
        old_uids = [row.uid for row in get_children(self.lists)]
        new_lists = UserData.get_lists_as_dicts()
        for list in new_lists:
            if list["uid"] not in old_uids:
                Log.debug(f"Lists: Add list '{list['uid']}'")
                row = self.add_list(list["name"], list["uid"])
                self.lists.select_row(row)
                self.stack.set_visible_child_name(list["name"])
                self.status_page.set_visible(False)

        # Show status
        lists = get_children(self.lists)
        self.status_page.set_visible(len(lists) == 0)
        if len(lists) == 0:
            self.stack.set_visible_child_name("status")
            # self.window.split_view.set_show_sidebar(False)

        # Update details
        # tasks: list[Task] = []
        # for list in self.get_lists():
        #     tasks.extend(list.get_all_tasks())