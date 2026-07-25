from core.database import Database
from query.dispatch import execute_statement

db = Database()


def _cli_confirm(title, text, informative) -> bool:
    print(f"\n{title}")
    print(informative)
    answer = input(f"{text} Type YES to confirm: ").strip()
    return answer == "YES"


def _cli_on_result(col_names, rows, message):
    print(message)
    if col_names:
        print(col_names)
    for row in rows:
        print(row)


def main():
    print("Welcome to PyBase CLI! Type 'exit' to quit.")
    while True:
        command = input("PyBase> ").strip()
        if command.lower() == "exit":
            if db.in_transaction():
                print("Warning: exiting with an active transaction - changes are lost.")
            break
        if not command:
            continue

        execute_statement(command, db, on_result=_cli_on_result, confirm=_cli_confirm)


if __name__ == "__main__":
    main()