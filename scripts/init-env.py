"""Create the local Compose environment without overwriting existing credentials."""
from pathlib import Path
import os
import secrets


def main():
    root = Path(__file__).resolve().parents[1]
    template = (root / ".env.example").read_text(encoding="utf-8")
    lines = []
    for line in template.splitlines():
        if line in {"APP_DB_PASSWORD=", "POSTGRES_ADMIN_PASSWORD="}:
            line += secrets.token_urlsafe(36)
        lines.append(line)
    try:
        descriptor = os.open(root / ".env", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as target:
            target.write("\n".join(lines) + "\n")
    except FileExistsError:
        raise SystemExit("An .env already exists. Use its settings or edit it directly.")
    print("Created .env for Docker Compose.")


if __name__ == "__main__":
    main()
