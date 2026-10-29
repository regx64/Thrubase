from ..models.task import Task


def sort_by_priority(tasks: list[Task]) -> list[Task]:
    return sorted(tasks, key=priority_key)


def priority_key(task: Task) -> tuple[int, int, str]:
    return (int(task.done), task.priority, task.due or "9999")
