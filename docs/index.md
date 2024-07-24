# Grouping Testing Tool

> **Note**
> Refer to [README](../README.md) for installation instructions and basic usage


## How it Works

### Basic Flow

This tool works by injecting a tests defined in [../sentry_group_test_tools/_test](../sentry_group_test_tools/_test) into
Sentry, then using pytest to run it. The tests are run against `master` branch and the current branch, then the outputs
(in _pysnap_ format) are compared. Data for the tests is fetch from live events (see below).

### Injecting the Test

This tool is installed as a package within Sentry virtual env, where the main script is defined as an entry-point
`test-grouping`. This means that this tool can _only_ be used from withing Sentry checkout and _only_ with venv active.

The tests is injected by symlinking [../sentry_group_test_tools/_test](../sentry_group_test_tools/_test) into
`tests/sentry/grouping/` within Sentry checkout. This symlink is removed when test is done.


#### Fetching the Data

> **Note**
> Fetching data requires a valid API token, you can either pass it as `--token` parameter or set it via
> `SENTRY_API_TOKEN` env var.

This tool uses ProjectEvents endpoint to get a random sample of events from specified project or IssueEvents endpoint
to get random sample of events from specified issues. Note that fetching large amounts of data via these endpoints is
slow. Unless otherwise specified, the default is to use `sentry` project.

You can specify how many events to fetch using `--limit` parameter.

By default, unless overriden with `--force-refetch`, the data is cached and not refetched for subsequent runs.

The data is stored on encrypted volume created using [edmgutil](https://github.com/getsentry/edmgutil).
It's currently hardcoded to use `/Volumes/grouping_data_cache/` as its location. The volume is ephemeral
and set to expire after 7 days.

#### Branch switching

The tool switches the branch to `master` to run test generating the baseline. Unless overriden with `--force-baseline`,
the this will happen only on the first run.

Subsequently the tool switches back to current branch, runs the test generating new pysnaps.

If the current branch is not clean, the tool will stash all changes (including untracked) before switching, and restore
this stash afterwards.


#### Comparison

End result is running comparison on differences. Because the datasets can be huge it's not viable to look at exact detail
difference, therefore the tool summarizes differece types. Hash-only diffs are diffs where only hash changes.

- Total diffs — number of all differences. This includes _hash-only diffs_ as well as all other diffs.
- Total non-hash diffs — number of differences excluding _hash-only diffs_.
- Old hashes that map to exactly one new hash — differences where every event with old hash maps to one and only one new hash.
This indicates that grouping does not change.
- Old hash maps to multiple new hashes — differences where some events which were in same group before now belong in two or more new groups;
- New hash maps to multiple old hashes — differences where some events which were in same group now belonged in two or more old groups before;

If you need to debug exact differences, they are saved to a file using standard diff format.

### Limitations

#### Limited Test Coverage

Currently the only test implemented is the re-used variats test, which covers only part of grouping logic. Ideally we should
have test covering _whole_ grouping logic starting at `process_event` call and ending at `save_event` call.

#### Limited Data Coverage

As of now fetching data relies on passing API key belonging to specific org. We need to implement some kind of
superuser mechanism here that would let authorized Sentry engineers fetch data from orgs we're trying to improve
grouping for, however as of now such a mechanism does not exist.

#### Only on Dev Machines

This tool can only be used on dev machines. This is intentional, we have no plans to run this in CI, as that would
expose the event data.