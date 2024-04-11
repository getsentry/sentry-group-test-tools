# Grouping Testing Tools (WIP)


## Install

### Install Edmgutil
This tool uses `edmgutil` to create encrypted, ephemeral volumes.
```shell
cargo install --git https://github.com/getsentry/edmgutil --branch main edmgutil
```
See: https://github.com/getsentry/edmgutil

### Install
```shell
cd {your sentry dir}
direnv allow
pip install git+https://github.com/getsentry/sentry-group-test-tools.git#egg=sentry_group_test_tools
```


### Install for Development
Checkout the this repo and install it as an editable package. All changes will
be immediatelly reflected.
```shell
git clone git@github.com:getsentry/sentry-group-test-tools.git
cd {your sentry dir}
direnv allow
pip install -e {this package dir}
```

## Usage

```shell
cd {your sentry dir}
direnv allow
test-grouping
```
### Options
```
Usage: test-grouping [OPTIONS]

Options:
  -o, --org TEXT          Organization name
  -p, --project TEXT      Project name
  -i, --issue TEXT        Issue number
  -l, --limit INTEGER     Limit
  -t, --token TEXT        API token
  -f, --force-refetch     force refetching data
  --force-baseline        force rerunning of baseline tests
  --use-edmg / --no-edmg  use edmgutil as storage
  --help                  Show this message and exit.
```

For most up to data available options
```test-grouping --help```