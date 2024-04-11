from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml
from django.utils.functional import cached_property

from sentry import eventstore
from sentry.event_manager import EventManager
from sentry.eventtypes.base import format_title_from_tree_label
from sentry.grouping.api import (
    detect_synthetic_exception,
    get_default_grouping_config_dict,
    load_grouping_config,
)
from sentry.grouping.component import GroupingComponent
from sentry.grouping.enhancer import Enhancements
from sentry.grouping.strategies.configurations import CONFIGURATIONS
from sentry.stacktraces.processing import normalize_stacktraces_for_grouping
from sentry.utils import json

"""
This test is a special case meant to be run only through tools/test_grouping.py,
rather that the usual pytest command. tools/test_grouping.py is used to generate
the expected output from current and master branches to compare the grouping
variants output.
"""

if os.environ.get("GROUPING_TEST_INPUT_PATH") is None:
    pytest.skip("only run through tools/test_grouping.py", allow_module_level=True)


class GroupingInput:
    def __init__(self, filename):
        self.filename = filename

    @cached_property
    def data(self):
        with open(self.filename) as f:
            return json.load(f)

    def create_event(self, grouping_config):
        grouping_input = dict(self.data)
        # Customize grouping config from the _grouping config
        grouping_info = grouping_input.pop("_grouping", None) or {}
        enhancements = grouping_info.get("enhancements")
        if enhancements:
            enhancement_bases = Enhancements.loads(grouping_config["enhancements"]).bases
            e = Enhancements.from_config_string(enhancements or "", bases=enhancement_bases)
            grouping_config["enhancements"] = e.dumps()

        # Normalize the event
        mgr = EventManager(data=grouping_input, grouping_config=grouping_config)
        mgr.normalize()
        data = mgr.get_data()

        # Normalize the stacktrace for grouping.  This normally happens in
        # save()
        normalize_stacktraces_for_grouping(data, load_grouping_config(grouping_config))
        evt = eventstore.backend.create_event(data=data, event_id=data["event_id"])

        return evt


def grouping_input(data_path):
    return [GroupingInput(filename) for filename in Path(data_path).glob("**/*.json")]


def with_grouping_input(name, data_path):
    return pytest.mark.parametrize(name, grouping_input(data_path), ids=lambda x: x.filename.stem)


class ReadableYamlDumper(yaml.dumper.SafeDumper):
    """Disable pyyaml aliases for identical object references"""

    def ignore_aliases(self, data):
        return True


def dump_variant(variant, lines=None, indent=0):
    if lines is None:
        lines = []

    def _dump_component(component, indent):
        if not component.hint and not component.values:
            return
        lines.append(
            "%s%s%s%s"
            % (
                "  " * indent,
                component.id,
                component.contributes and "*" or "",
                component.hint and " (%s)" % component.hint or "",
            )
        )
        for value in component.values:
            if isinstance(value, GroupingComponent):
                _dump_component(value, indent + 1)
            else:
                lines.append("{}{}".format("  " * (indent + 1), json.dumps(value)))

    lines.append("{}hash: {}".format("  " * indent, json.dumps(variant.get_hash())))

    for key, value in sorted(variant.__dict__.items()):
        if isinstance(value, GroupingComponent):
            if value.tree_label:
                lines.append(
                    '{}tree_label: "{}"'.format(
                        "  " * indent, format_title_from_tree_label(value.tree_label)
                    )
                )
            lines.append("{}{}:".format("  " * indent, key))
            _dump_component(value, indent + 1)
        elif key == "config":
            # We do not want to dump the config
            continue
        else:
            lines.append("{}{}: {}".format("  " * indent, key, json.dumps(value)))

    return lines


@with_grouping_input("grouping_input", os.environ["GROUPING_TEST_INPUT_PATH"])
@pytest.mark.parametrize("config_name", CONFIGURATIONS.keys(), ids=lambda x: x.replace("-", "_"))
def test_event_hash_variant(config_name, grouping_input, log):
    grouping_config = get_default_grouping_config_dict(config_name)
    loaded_config = load_grouping_config(grouping_config)
    evt = grouping_input.create_event(grouping_config)

    # Make sure we don't need to touch the DB here because this would
    # break stuff later on.
    evt.project = None

    # Set the synthetic marker if detected
    detect_synthetic_exception(evt.data, loaded_config)

    rv: list[str] = []
    for key, value in sorted(evt.get_grouping_variants().items()):
        if rv:
            rv.append("-" * 74)
        rv.append("%s:" % key)
        dump_variant(value, rv, 1)
    output = "\n".join(rv)

    hashes = evt.get_hashes()
    log(repr(hashes))

    assert evt.get_grouping_config() == grouping_config

    output_path = Path(os.environ["GROUPING_TEST_OUTPUT_PATH"], config_name)
    output_path.mkdir(parents=True, exist_ok=True)

    with open(output_path / f"{evt.event_id}.txt", "w") as f:
        f.write(output)
