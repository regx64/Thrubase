import click


@click.group()
def cli() -> None:
    pass


@cli.command()
def build() -> None:
    compile_all()


@click.command()
def standalone() -> None:
    pass


def compile_all() -> None:
    pass
