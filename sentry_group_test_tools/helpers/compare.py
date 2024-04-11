import difflib
import hashlib
from collections import defaultdict

import click

from .storage import Storage


class CompareConfigOutputs:
    def __init__(self, storage: Storage, config_path: str) -> None:
        self.storage = storage
        self.diffs = {}
        self.config_path = config_path
        self.new_hashes = defaultdict(list)  # maps hash to event_id
        self.old_hashes = defaultdict(list)  # maps hash to event_id
        self.hash_map_new_old = defaultdict(set)  # maps new hash to set of baseline hashes
        self.hash_map_old_new = defaultdict(set)  # maps baseline hash to set of new hashes

    def compare(self) -> None:
        with click.progressbar(
            list(self.config_path.glob("**/*.txt")),
            label=f"Comparing outputs for '{self.config_path.stem}'",
        ) as bar:
            for old_output in bar:
                new_output = self.storage.new_outputs_dir / old_output.relative_to(
                    self.storage.baseline_outputs_dir
                )
                if not new_output.exists():
                    click.secho(f"Missing new output file {new_output}", fg="red")
                    continue

                with open(old_output) as old_file, open(new_output) as new_file:
                    old_data = list(old_file.readlines())
                    new_data = list(new_file.readlines())

                diff = difflib.unified_diff(old_data, new_data, fromfile="old", tofile="new")
                diff = list(diff)
                if diff:
                    diff_md5 = hashlib.md5("".join(diff).encode()).hexdigest()
                    if hashlib.md5("".join(diff).encode()).hexdigest() not in self.diffs:
                        annotated_diff = difflib.unified_diff(
                            old_data, new_data, fromfile=str(old_output), tofile=str(new_output)
                        )

                    self.diffs[diff_md5] = list(annotated_diff)

                old_hash = self.find_hash(old_data)
                new_hash = self.find_hash(new_data)
                self.old_hashes[old_hash].append(old_output.stem)
                self.new_hashes[new_hash].append(new_output.stem)
                self.hash_map_new_old[new_hash].add(old_hash)
                self.hash_map_old_new[old_hash].add(new_hash)

    @staticmethod
    def find_hash(lines: list[str]) -> str:
        for line in lines:
            if line.strip().startswith("hash: "):
                hash_str = line.split("hash: ")[1].strip()
                if hash_str != "null":
                    return hash_str
        raise Exception("Could not find hash in lines")

    @staticmethod
    def diff_is_hash_only(lines: list[str]) -> bool:

        for line in list(lines):
            if not (line.startswith("-") or line.startswith("+")):
                continue
            if line.startswith("---") or line.startswith("+++"):
                continue

            if not line[1:].strip().startswith("hash: "):
                return False
        return True

    def print_summary(self) -> None:
        # click.secho(f"Summary for {self.config_path.stem}:", bold=True)
        if not self.diffs:
            click.secho("No differences found!", fg="green", bold=True)
            return

        click.secho(f"Total diffs: {len(self.diffs)}", fg="yellow")

        non_hash_diffs = [diff for diff in self.diffs.values() if not self.diff_is_hash_only(diff)]
        if non_hash_diffs:
            click.secho(f"Total non-hash diffs: {len(non_hash_diffs)}", fg="red")

        hashes_one_to_one_diff = {}
        for old_hash, new_hashes in self.hash_map_old_new.items():
            if len(new_hashes) != 1:
                click.secho(
                    f"Old hash {old_hash} maps to multiple new hashes: {new_hashes}", fg="red"
                )
            elif old_hash not in self.new_hashes:
                hashes_one_to_one_diff[old_hash] = new_hashes.copy().pop()

        for new_hash, old_hashes in self.hash_map_new_old.items():
            if len(new_hashes) != 1:
                click.secho(
                    f"New hash {new_hash} maps to multiple old hashes: {old_hashes}", fg="red"
                )

        if hashes_one_to_one_diff:
            click.secho(
                f"Old hashes that map to exactly one new hash: {len(hashes_one_to_one_diff)}",
                fg="yellow",
            )
            for old_hash, new_hash in hashes_one_to_one_diff.items():
                click.secho(f" - {old_hash} -> {new_hash}", fg="yellow")

    def save_diffs(self) -> None:
        filename = self.storage.base_data_dir / f"variants.{self.config_path.stem}.diff"
        if not self.diffs:
            filename.unlink(missing_ok=True)
            return

        with open(filename, "w") as f:
            for diff in self.diffs.values():
                f.writelines(diff)
                f.write("\n\n")

        click.secho(f"Differences saved to {filename}", fg="cyan")


def compare_all(storage: Storage) -> None:
    for config_path in storage.baseline_outputs_dir.glob("*"):
        if not config_path.is_dir():
            continue
        comp = CompareConfigOutputs(storage, config_path)
        comp.compare()
        comp.print_summary()
        comp.save_diffs()
