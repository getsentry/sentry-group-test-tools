from pathlib import Path
from shutil import rmtree, which
from subprocess import check_call

import click


class Storage:
    ROOT_NAME = Path("grouping_data_cache")
    EDMG_BASE = Path("/Volumes")
    EDMG_MIN_SIZE = 100  # 100MB
    EDMG_EXPIRY = 7  # 7 days expiry, max allowed is 14 days

    def __init__(self, limit: int) -> None:
        if not self.ensure_edmg():
            raise Exception("Encrypted storage required for this tool")
        self.base = self.EDMG_BASE
        self._root = self.base / self.ROOT_NAME

        # keeping this small makes it faster to eject and re-create
        self.EDMG_SIZE = max(self.EDMG_MIN_SIZE, int(limit * .3) + 100)  # 300KB per event


    def ensure_edmg(self) -> bool:
        if which("edmgutil"):
            return True

        click.secho("⚠️ edmgutil not found, falling back to non-encrypted storage!", fg="red")
        click.secho("Please install edmutils https://github.com/getsentry/edmgutil", fg="yellow")
        click.secho(
            "Make sure to enable `edmgutil cron --install` to auto-eject expired data", fg="yellow"
        )
        return False

    @property
    def root(self) -> Path:
        if not self._root.exists():
            self._root = self.create_root()
        return self._root

    @property
    def root_path(self) -> Path:
        return self.base / self.ROOT_NAME

    @property
    def _root_exists(self) -> bool:
        return hasattr(self, "_root") and self._root.exists()

    def create_root(self) -> Path:
        click.secho(f"Using encrypted, ephemeral storage", fg="green")
        try:
            check_call(["edmgutil", "eject", "--expired"])
        except Exception as e:
            click.secho(f"⚠️ Failed to eject expired data: {e}", fg="red")
            raise

        if not self._root.exists():
            try:
                check_call(
                    [
                        "edmgutil",
                        "new",
                        f"--size={self.EDMG_SIZE}",
                        f"--name={self.ROOT_NAME}",
                        f"--days={self.EDMG_EXPIRY}",
                    ]
                )
            except Exception as e:
                click.secho(f"⚠️ Failed to create edmgutil storage: {e}", fg="red")
                raise
        return self._root


    def wipe_data(self) -> None:
        if not self._root_exists:
            return
        try:
            check_call(["edmgutil", "eject", str(self.root)])
            # ejecting and re-creating is faster, and refreshes expiry
        except Exception as e:
            click.secho(f"⚠️ Failed to eject edmgutil storage: {e}", fg="red")
            raise

        click.secho("Cache cleared", fg="yellow")

    @property
    def base_data_dir(self) -> Path:
        path = self.root / "data"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def ensure_path(self, path: Path) -> Path:
        path = self.base_data_dir / path
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def raw_data_dir(self) -> Path:
        return self.ensure_path("raw")

    @property
    def inputs_dir(self) -> Path:
        return self.ensure_path("inputs")

    @property
    def baseline_outputs_dir(self) -> Path:
        return self.ensure_path("baseline_outputs")

    @property
    def new_outputs_dir(self) -> Path:
        return self.ensure_path("new_outputs")

    def empty(self, path: Path, glob: str = "*.json") -> bool:
        return not any(path.glob(glob))
