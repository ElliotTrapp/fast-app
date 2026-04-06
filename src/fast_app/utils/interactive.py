"""Interactive prompt utilities."""

import click


def ask_questions_interactive(questions: list[str]) -> list[str]:
    """Ask questions interactively and collect answers."""
    answers = []
    click.echo("\n📝 Please answer these questions to help tailor your resume:\n")

    for i, question in enumerate(questions, 1):
        click.echo(f"{i}. {question}")
        answer = click.prompt("   Your answer", default="", show_default=False)
        answers.append(answer)

    return answers
