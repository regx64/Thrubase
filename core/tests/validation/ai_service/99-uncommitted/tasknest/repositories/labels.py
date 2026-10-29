from ..models.label import Label
from .base import BaseRepository


class LabelRepository(BaseRepository):
    table = "labels"

    def for_task(self, task_id: int) -> list[Label]:
        return [Label.from_row(r) for r in self.fetch_all("SELECT * FROM labels WHERE task_id = ?", task_id)]

    def add(self, task_id: int, name: str) -> Label:
        label_id = self.db.execute("INSERT INTO labels (task_id, name) VALUES (?, ?)", task_id, name)
        return Label(id=label_id, task_id=task_id, name=name)
