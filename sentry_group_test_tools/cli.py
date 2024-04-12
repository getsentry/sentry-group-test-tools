import os
import subprocess
from pathlib import Path
from subprocess import check_output
import contextlib

import click
from sentry_group_test_tools.helpers import Data, Storage, compare_all

os.environ["SENTRY_IN_TEST_ENVIRONMENT"] = "1"

TOKEN = os.getenv("SENTRY_API_TOKEN")
MASTER = "master"


@click.command()
@click.option("--org", "-o", default="sentry", help="Organization name")
@click.option("--project", "-p", default="sentry", help="Project name")
@click.option("--issue", "-i", help="Issue number", multiple=True)
@click.option("--limit", "-l", default=100, help="Limit", type=int)
@click.option("--token", "-t", help="API token", default=TOKEN)
@click.option("--force-refetch", "-f", help="force refetching data", type=bool, is_flag=True)
@click.option("--force-baseline", help="force rerunning of baseline tests", type=bool, is_flag=True)
@click.option(
    "--use-edmg/--no-edmg", help="use edmgutil as storage", type=bool, is_flag=True, default=True
)
@click.option("--grouping-config", help="grouping config IDs (eg. newstyle:2023_01_11)")
def main(
    org: str,
    project: str,
    issue: str | list[str],
    limit: int,
    token: str,
    force_refetch: bool,
    force_baseline: bool,
    use_edmg: bool,
    grouping_config: str,
):
    storage = Storage(limit=limit, use_edmg=use_edmg)

    if force_refetch:
        # this will wipe all data
        storage.wipe_data()

    data = Data(storage, org, project, issue, limit, token)

    if storage.empty(storage.raw_data_dir):
        data.fetch_data()
        data.write_raw_data()
    else:
        click.secho("Found cached data, resusing", fg="green", nl=False)
        click.secho(" [use -f to force refresh]", fg="yellow")
        data.read_raw_data()

    data.transform_data()
    run_baseline_tests(storage, force_baseline, grouping_config)
    run_new_tests(storage, grouping_config)
    compare_all(storage)

def sentry_root() -> Path:
    try:
        sentry = __import__("sentry")
    except ImportError:
        click.secho("This script must be executed in Sentry venv", fg="red")
        raise
    else:
        # /.../sentry/src/sentry/__init__.py -> /.../sentry
        return Path(sentry.__file__).parent.parent.parent

def git(command: str, splitlines: bool=False) -> str | list[str]:
    command_args = [s.strip() for s in command.split()]
    if command_args[0] != "git":
        command_args.insert(0, "git")
    output = check_output(command_args, cwd=sentry_root()).decode()
    if splitlines:
        return [l.strip() for l in output.splitlines()]
    else:
        return output.strip()

def run_baseline_tests(storage: Storage, force_baseline: bool, grouping_config: str| None = None) -> None:
    if not force_baseline and not storage.empty(storage.baseline_outputs_dir, glob="**/*.txt"):
        click.secho("Baseline tests already ran, skipping", fg="green", nl=False)
        click.secho(" [use --force-baseline to force refresh]", fg="yellow")
        return

    STASH_MARKER = "__grouping_test_run__"
    BRANCH = git("branch --show-current")

    stash_out = git(f"stash -u -m {STASH_MARKER}")
    stash_id = None
    if stash_out != "No local changes to save":
        stashes =git("stash list", splitlines=True)
        stash_id = None
        for stash in stashes:
            if stash.strip().endswith(STASH_MARKER):
                stash_id = stash.split(":")[0]
                break
        if not stash_id:
            raise Exception("Stashed changes, but could not find the stash")

    try:
        git(f"switch {MASTER}")
        run_tests(storage.inputs_dir, storage.baseline_outputs_dir, grouping_config)
    finally:
        git(f"switch {BRANCH}")
        if stash_id:
            git(f"stash pop {stash_id}")


def run_new_tests(storage: Storage, grouping_config: str| None = None) -> None:
    run_tests(storage.inputs_dir, storage.new_outputs_dir, grouping_config)

@contextlib.contextmanager
def symlinked_test_dir():
    test_dir = Path(__file__).parent / "_test"
    test_link = sentry_root() / "tests/sentry/grouping/_test"

    try:
        test_link.symlink_to(test_dir)
        yield
    finally:
        test_link.unlink()

@symlinked_test_dir()
def run_tests(input_dir, ouput_dir, grouping_config: str| None = None):
    # calling via subprocess to avoid pytest's internal caching, which gets confused
    # by the code changing between runs

    pytest_cwd = sentry_root()

    pytest_command = [
        "pytest",
        # TODO: figure out how to have test itself oustide of the tests directory
        "tests/sentry/grouping/_test/",
    ]

    if grouping_config:
        pytest_command += ["-k", f"{grouping_config}"]


    pytest_extra_parallel = [
        "-v",  # verbose, so for each passed test we have a line with "PASSED"
        "-p",
        "no:rerunfailures",  # doesn't work well with parallel, but we don't need it
        "--no-cov",
        "--dist=load",  # run tests in parallel using all available cores
        "-n",
        "auto",
    ]

    pytest_env = {
        **os.environ,
        "GROUPING_TEST_INPUT_PATH": str(input_dir),
        "GROUPING_TEST_OUTPUT_PATH": str(ouput_dir),
    }

    try:
        pytest_collect = check_output(
            pytest_command + ["-qq", "--collect-only"],
            env=pytest_env,
            cwd=pytest_cwd,
        ).decode()
    except subprocess.CalledProcessError as e:
        click.secho("Failed to collect tests", fg="red")
        click.echo(e.output)
        raise

    n_tests = int(pytest_collect.split(":")[1].strip())
    process = subprocess.Popen(
        pytest_command + pytest_extra_parallel,
        env=pytest_env,
        cwd=pytest_cwd,
        stdout=subprocess.PIPE,
    )

    with click.progressbar(
        length=n_tests,
        label=f"Running {n_tests} tests",
    ) as bar:
        for line in process.stdout:
            if b"PASSED" in line:
                bar.update(1)


if __name__ == "__main__":
    main()
