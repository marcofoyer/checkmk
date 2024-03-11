#!/usr/bin/env python3
# Copyright (C) 2019 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from cmk.utils import version as cmk_version
from cmk.utils.hostaddress import HostAddress, HostName
from cmk.utils.labels import HostLabel
from cmk.utils.sectionname import SectionName

from cmk.automations.results import (
    ABCAutomationResult,
    Gateway,
    GatewayResult,
    result_type_registry,
    ScanParentsResult,
    SerializedResult,
    ServiceDiscoveryPreviewResult,
    ServiceDiscoveryResult,
)

from cmk.checkengine.discovery import CheckPreviewEntry
from cmk.checkengine.discovery import DiscoveryResult as SingleHostDiscoveryResult

from cmk.base.automations import automations


def test_result_type_registry_completeness() -> None:
    # ensures that all automation calls registered in cmk.base have a corresponding result type
    # registered in cmk.automations
    automations_missing = (
        {"bake-agents"} if cmk_version.edition() is cmk_version.Edition.CRE else set()
    )
    assert set(result_type_registry) - automations_missing == set(automations._automations)


@dataclass
class AutomationResultTest(ABCAutomationResult):
    a: int
    b: str
    c: bool
    d: Sequence[None]
    e: Mapping[str, str]

    @staticmethod
    def automation_call() -> str:
        return "test"


def test_serialization() -> None:
    automation_res_test = AutomationResultTest(
        a=1,
        b="string",
        c=True,
        d=(
            None,
            None,
        ),
        e={
            "a": "test",
            "123": "456",
        },
    )
    assert automation_res_test == AutomationResultTest.deserialize(
        automation_res_test.serialize(cmk_version.Version.from_str(cmk_version.__version__))
    )


class TestDiscoveryResult:
    HOSTS = {
        HostName("host_1"): SingleHostDiscoveryResult(
            clustered_new=0,
            clustered_old=0,
            clustered_vanished=0,
            diff_text=None,
            error_text="",
            self_kept=0,
            self_new=0,
            self_new_host_labels=0,
            self_removed=0,
            self_total=0,
            self_total_host_labels=0,
        ),
        HostName("host_2"): SingleHostDiscoveryResult(
            clustered_new=1,
            clustered_old=2,
            clustered_vanished=3,
            diff_text="something changed",
            error_text="error",
            self_kept=4,
            self_new=5,
            self_new_host_labels=6,
            self_removed=7,
            self_total=8,
            self_total_host_labels=9,
        ),
    }

    def test_serialization(self) -> None:
        assert ServiceDiscoveryResult.deserialize(
            ServiceDiscoveryResult(self.HOSTS).serialize(
                cmk_version.Version.from_str(cmk_version.__version__)
            )
        ) == ServiceDiscoveryResult(self.HOSTS)


class TestTryDiscoveryResult:
    def test_serialization(self) -> None:
        result = ServiceDiscoveryPreviewResult(
            output="output",
            check_table=[
                CheckPreviewEntry(
                    check_source="my_check_source",
                    check_plugin_name="my_check_plugin_name",
                    ruleset_name=None,
                    discovery_ruleset_name=None,
                    item=None,
                    old_discovered_parameters={},
                    new_discovered_parameters={},
                    effective_parameters=None,
                    description="description",
                    state=0,
                    output="output",
                    metrics=[],
                    old_labels={},
                    new_labels={},
                    found_on_nodes=[],
                )
            ],
            host_labels={},
            new_labels={},
            vanished_labels={},
            changed_labels={},
            source_results={"agent": (0, "Success")},
            labels_by_host={HostName("my_host"): [HostLabel("cmk/foo", "bar", SectionName("baz"))]},
        )
        assert (
            ServiceDiscoveryPreviewResult.deserialize(
                result.serialize(cmk_version.Version.from_str(cmk_version.__version__))
            )
            == result
        )


class TestScanParentsResult:
    SERIALIZED_RESULT = SerializedResult("([((None, '108.170.228.254', None), 'gateway', 0, '')],)")

    DESERIALIZED_RESULT = ScanParentsResult(
        results=[
            GatewayResult(
                gateway=Gateway(None, HostAddress("108.170.228.254"), None),
                state="gateway",
                ping_fails=0,
                message="",
            )
        ]
    )

    def test_serialization_roundtrip(self) -> None:
        assert (
            ScanParentsResult.deserialize(
                self.DESERIALIZED_RESULT.serialize(
                    cmk_version.Version.from_str(cmk_version.__version__)
                )
            )
            == self.DESERIALIZED_RESULT
        )

    def test_deserialization(self) -> None:
        assert ScanParentsResult.deserialize(self.SERIALIZED_RESULT) == self.DESERIALIZED_RESULT
