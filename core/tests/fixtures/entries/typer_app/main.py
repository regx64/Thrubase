import typer

app = typer.Typer()


@app.command()
def hello(name: str) -> None:
    greet(name)


def greet(name: str) -> None:
    pass
