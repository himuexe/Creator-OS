"""Fetch the two pinned CPU models into private workspace storage and verify their content."""
import argparse
import hashlib
import os
from pathlib import Path
import tempfile
from urllib.request import urlopen


MODELS = (
    ("Systran/faster-whisper-base", "ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66", "faster-whisper-base", {
        "config.json": "56a6d8110d311f19c8f0471e562832c7527f146b567275bfca59fcf7c184da9a",
        "tokenizer.json": "fb7b63191e9bb045082c79fd742a3106a12c99513ab30df4a0d47fa6cb6fd0ab",
        "vocabulary.txt": "34ce3fe1c5041027b3f8d42912270993f986dbc4bb34cf27f951e34a1e453913",
        "model.bin": "d01c3014881c9c6f3133c182f3d2887eb6ca1c789a7538c5c007196857a0a6a9",
    }),
    ("Qwen/Qwen2.5-1.5B-Instruct-GGUF", "91cad51170dc346986eccefdc2dd33a9da36ead9", "", {
        "qwen2.5-1.5b-instruct-q4_k_m.gguf": "6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e",
    }),
)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def prepare(directory):
    for repository, revision, subdirectory, files in MODELS:
        folder = directory / subdirectory
        folder.mkdir(parents=True, exist_ok=True)
        for name, expected in files.items():
            target = folder / name
            if target.is_file():
                if digest(target) != expected:
                    raise SystemExit(f"Existing file has an unexpected checksum: {target}. Move it aside and retry.")
            else:
                url = f"https://huggingface.co/{repository}/resolve/{revision}/{name}?download=true"
                print(f"Downloading {name} from {repository} ...", flush=True)
                with tempfile.NamedTemporaryFile(dir=folder, delete=False) as stream:
                    partial = Path(stream.name)
                try:
                    with urlopen(url, timeout=240) as source, partial.open("wb") as output:
                        while chunk := source.read(1024 * 1024):
                            output.write(chunk)
                    if digest(partial) != expected:
                        raise SystemExit(f"Download failed integrity check for {name}.")
                    os.replace(partial, target)
                finally:
                    partial.unlink(missing_ok=True)
            print(f"Verified {target}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path(__file__).resolve().parents[1] / ".local" / "models")
    prepare(parser.parse_args().directory)
