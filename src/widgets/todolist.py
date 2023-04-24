from gi.repository import Adw
from ..globals import data
from ..data import ReadData
from .todo import Todo


class TodoList(Adw.PreferencesPage):
    def __init__(self):
        super().__init__()
        data["todo_list"] = self
        self.load_todos()

    def load_todos(self):
        data = ReadData()
        if data["todos"] != {}:
            for todo in data["todos"]:
                self.add(Todo(todo, data["todos"][todo]["sub"]))