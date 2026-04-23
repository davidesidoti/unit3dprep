"""CLI entry point. Interactive prompts wrapping core logic."""
import os
import sys
from pathlib import Path

try:
    import readline
    _HAS_READLINE = True
except ImportError:
    _HAS_READLINE = False

from .core import (
    SEEDINGS_DIR,
    build_name,
    extract_specs,
    format_se,
    hardlink_file,
    hardlink_tree,
    has_italian_audio,
    iter_video_files,
    map_source,
    tmdb_fetch,
    tmdb_year,
)

TMDB_API_KEY = os.environ.get("TMDB_API_KEY")


def prompt_confirm(msg: str) -> bool:
    try:
        answer = input(msg).strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer in {"y", "yes", "s", "si", "sì"}


def prompt_edit(msg: str, default: str) -> str:
    if _HAS_READLINE:
        readline.set_startup_hook(lambda: readline.insert_text(default))
        try:
            return input(msg).strip()
        finally:
            readline.set_startup_hook()
    print(f"Attuale: {default}")
    new = input(f"{msg} (invio = mantieni): ").strip()
    return new or default


def prompt_choice(msg: str, choices: dict[str, str]) -> str:
    options = " / ".join(f"[{k}]{v}" for k, v in choices.items())
    while True:
        try:
            ans = input(f"{msg} {options}: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return ""
        if ans in choices:
            return ans


def ask_tmdb_id(kind_label: str, default_title: str = "") -> tuple[str, dict]:
    kind = "tv" if kind_label == "tv" else "movie"
    hint = f" (guessit: '{default_title}')" if default_title else ""
    while True:
        try:
            raw = input(f"Inserisci TMDB ID per {kind}{hint}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(1)
        if not raw:
            continue
        try:
            data = tmdb_fetch(kind, raw, TMDB_API_KEY or "")
            return kind, data
        except Exception as e:
            print(f"Errore TMDB: {e}. Riprova.")


def resolve_collision(target: Path) -> str:
    if not target.exists():
        return "overwrite"
    print(f"Attenzione: '{target}' esiste già.")
    choice = prompt_choice(
        "Cosa fare?",
        {"o": "sovrascrivi", "s": "salta", "c": "annulla"},
    )
    return {"o": "overwrite", "s": "skip", "c": "cancel"}.get(choice, "cancel")


def run_unit3dup(args: list[str]):
    import subprocess
    try:
        result = subprocess.run(["unit3dup", *args])
        sys.exit(result.returncode)
    except FileNotFoundError:
        print("Errore: 'unit3dup' non trovato nel PATH.")
        sys.exit(127)


def handle_file(path: Path):
    if not path.exists() or not path.is_file():
        print(f"Errore: file non valido: {path}")
        sys.exit(1)

    print(f"Analisi tracce audio: {path.name} ...")
    if not has_italian_audio(path):
        print("Italiano non trovato nelle tracce audio. Uscita.")
        sys.exit(1)

    if not prompt_confirm("Lingua italiana trovata. Proseguo con hardlink e rinomina? [y/n]: "):
        print("Annullato.")
        sys.exit(0)

    from guessit import guessit
    guess = dict(guessit(path.name))
    title_hint = guess.get("title", "")
    kind, tmdb_data = ask_tmdb_id("movie", title_hint)
    title = tmdb_data.get("title") or tmdb_data.get("name") or title_hint
    year = tmdb_year(tmdb_data, kind)

    specs = extract_specs(path)
    source, src_type = map_source(guess)
    tag = guess.get("release_group", "") or ""

    proposed = build_name(
        title=title, year=year, se="",
        specs=specs, source=source, src_type=src_type, tag=tag,
        cut="", repack="REPACK" if guess.get("proper_count") else "",
    )
    final_name = prompt_edit("Nome finale: ", proposed)
    if not final_name:
        print("Nome vuoto, annullato.")
        sys.exit(1)

    SEEDINGS_DIR.mkdir(parents=True, exist_ok=True)
    target = SEEDINGS_DIR / f"{final_name}{path.suffix.lower()}"
    action = resolve_collision(target)
    if action == "cancel":
        print("Annullato.")
        sys.exit(0)
    if action == "skip" and target.exists():
        print(f"File esistente, uso: {target}")
    else:
        hardlink_file(path, target, overwrite=True)
        print(f"Hardlink creato: {target}")

    if not prompt_confirm(f"Uploadare '{target.name}' tramite unit3dup? [y/n]:"):
        print("Annullato (hardlink rimane in ~/seedings).")
        sys.exit(0)

    run_unit3dup(["-b", "-u", str(target.resolve())])


def handle_folder(folder: Path):
    if not folder.exists() or not folder.is_dir():
        print(f"Errore: cartella non valida: {folder}")
        sys.exit(1)

    files = list(iter_video_files(folder))
    if not files:
        print("Nessun file video trovato.")
        sys.exit(1)

    print(f"Trovati {len(files)} file video. Analisi tracce audio ...")
    for f in files:
        print(f"  {f.relative_to(folder)} ... ", end="", flush=True)
        if has_italian_audio(f):
            print("ok")
        else:
            print("NO ITALIANO")
            print(f"\nFile senza traccia italiana: {f}")
            sys.exit(1)

    if not prompt_confirm("\nItaliano trovato in tutti i file. Proseguo con hardlink e rinomina? [y/n]: "):
        print("Annullato.")
        sys.exit(0)

    from guessit import guessit
    folder_guess = dict(guessit(folder.name))
    title_hint = folder_guess.get("title", folder.name)
    kind, tmdb_data = ask_tmdb_id("tv", title_hint)
    series_title = tmdb_data.get("name") or tmdb_data.get("title") or title_hint
    year = tmdb_year(tmdb_data, kind)

    episode_rename: dict[Path, str] = {}
    sample_specs = None
    sample_source = ""
    sample_type = ""
    sample_tag = ""
    for f in files:
        g = dict(guessit(f.name))
        season = g.get("season")
        if isinstance(season, list):
            season = season[0]
        episode = g.get("episode")
        se = format_se(season, episode)
        if not se:
            print(f"Avviso: impossibile ricavare S##E## da '{f.name}'. Lo salto.")
            continue
        specs = extract_specs(f)
        source, src_type = map_source(g)
        tag = g.get("release_group", "") or folder_guess.get("release_group", "") or ""
        if sample_specs is None:
            sample_specs, sample_source, sample_type, sample_tag = specs, source, src_type, tag
        new_name = build_name(
            title=series_title, year="", se=se,
            specs=specs, source=source, src_type=src_type, tag=tag,
        )
        episode_rename[f] = new_name

    folder_name = build_name(
        title=series_title, year="", se="",
        specs=sample_specs or {}, source=sample_source, src_type=sample_type, tag=sample_tag,
    )
    folder_name = prompt_edit("Nome cartella finale: ", folder_name)
    if not folder_name:
        print("Nome vuoto, annullato.")
        sys.exit(1)

    import shutil as _shutil
    SEEDINGS_DIR.mkdir(parents=True, exist_ok=True)
    target_dir = SEEDINGS_DIR / folder_name
    action = resolve_collision(target_dir)
    if action == "cancel":
        print("Annullato.")
        sys.exit(0)
    if action == "overwrite" and target_dir.exists():
        _shutil.rmtree(target_dir)

    if action != "skip" or not target_dir.exists():
        hardlink_tree(folder, target_dir, episode_rename)
        print(f"Hardlink creati in: {target_dir}")
        for orig, new in episode_rename.items():
            print(f"  {orig.name} -> {new}{orig.suffix.lower()}")

    if not prompt_confirm(f"Uploadare '{target_dir.name}' su ItaTorrents? [y/n]: "):
        print("Annullato (hardlink rimane in ~/seedings).")
        sys.exit(0)

    run_unit3dup(["-b", "-f", str(target_dir.resolve())])


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Verifica lingua italiana, rinomina secondo nomenclatura ItaTorrents e carica tramite unit3dup."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-u", "--upload", metavar="FILE", help="Singolo file video (film)")
    group.add_argument("-f", "--folder", metavar="CARTELLA", help="Cartella (serie TV)")
    args = parser.parse_args()

    if args.upload:
        handle_file(Path(args.upload).expanduser().resolve())
    else:
        handle_folder(Path(args.folder).expanduser().resolve())


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrotto. Ciao!")
        sys.exit(130)
