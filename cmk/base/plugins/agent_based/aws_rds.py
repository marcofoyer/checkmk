#!/usr/bin/env python3
# Copyright (C) 2019 tribe29 GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.

import time
from collections.abc import Mapping, MutableMapping
from typing import Any

from cmk.base.plugins.agent_based.utils.cpu_util import check_cpu_util
from cmk.base.plugins.agent_based.utils.diskstat import check_diskstat_dict

from .agent_based_api.v1 import (
    check_levels,
    get_value_store,
    IgnoreResultsError,
    register,
    render,
    Result,
    State,
)
from .agent_based_api.v1.type_defs import CheckResult, DiscoveryResult, StringTable
from .utils import interfaces
from .utils.aws import (
    aws_get_counts_rate_human_readable,
    aws_rds_service_item,
    AWSSectionMetrics,
    discover_aws_generic,
    extract_aws_metrics_by_labels,
    parse_aws,
)


def parse_aws_rds(string_table: StringTable) -> AWSSectionMetrics:
    section: dict[str, Mapping[str, Any]] = {}
    for metrics in extract_aws_metrics_by_labels(
        [
            "CPUUtilization",
            "CPUCreditUsage",
            "CPUCreditBalance",
            "DatabaseConnections",
            "FailedSQLServerAgentJobsCount",
            "BinLogDiskUsage",
            "OldestReplicationSlotLag",
            "ReplicaLag",
            "ReplicationSlotDiskUsage",
            "TransactionLogsDiskUsage",
            "TransactionLogsGeneration",
            "NetworkReceiveThroughput",
            "NetworkTransmitThroughput",
            "DiskQueueDepth",
            "WriteIOPS",
            "WriteLatency",
            "WriteThroughput",
            "ReadIOPS",
            "ReadLatency",
            "ReadThroughput",
            "BurstBalance",
            # "FreeableMemory",
            # "SwapUsage",
            # "FreeStorageSpace",
            # "MaximumUsedTransactionIDs",
        ],
        parse_aws(string_table),
        extra_keys=["DBInstanceIdentifier", "AllocatedStorage", "Region"],
    ).values():

        try:
            metrics["AllocatedStorage"] *= 1.074e9
        except KeyError:
            pass

        section.setdefault(
            aws_rds_service_item(metrics["DBInstanceIdentifier"], metrics["Region"]),
            metrics,
        )
    return section


register.agent_section(
    name="aws_rds",
    parse_function=parse_aws_rds,
)

# .
#   .--network IO----------------------------------------------------------.
#   |                     _                      _      ___ ___            |
#   |          _ __   ___| |___      _____  _ __| | __ |_ _/ _ \           |
#   |         | '_ \ / _ \ __\ \ /\ / / _ \| '__| |/ /  | | | | |          |
#   |         | | | |  __/ |_ \ V  V / (_) | |  |   <   | | |_| |          |
#   |         |_| |_|\___|\__| \_/\_/ \___/|_|  |_|\_\ |___\___/           |
#   |                                                                      |
#   '----------------------------------------------------------------------'


def discover_aws_rds_network_io(section: AWSSectionMetrics) -> DiscoveryResult:
    yield from discover_aws_generic(
        section,
        ["NetworkReceiveThroughput", "NetworkTransmitThroughput"],
    )


def check_aws_rds_network_io(
    item: str,
    params: Mapping[str, Any],
    section: AWSSectionMetrics,
) -> CheckResult:
    metrics = section.get(item)
    if metrics is None:
        return
    try:
        interface = interfaces.InterfaceWithRatesAndAverages.from_interface_with_counters_or_rates(
            interfaces.InterfaceWithRates(
                attributes=interfaces.Attributes(
                    index="0",
                    descr=item,
                    alias=metrics.get("DBInstanceIdentifier", item),
                    type="1",
                    oper_status="1",
                ),
                rates=interfaces.Rates(
                    in_octets=metrics["NetworkReceiveThroughput"],
                    out_octets=metrics["NetworkTransmitThroughput"],
                ),
                get_rate_errors=[],
            ),
            timestamp=time.time(),
            value_store=get_value_store(),
            params=params,
        )
    except KeyError:
        raise IgnoreResultsError("Currently no data from AWS")
    yield from interfaces.check_single_interface(item, params, interface)


register.check_plugin(
    name="aws_rds_network_io",
    sections=["aws_rds"],
    service_name="AWS/RDS %s Network IO",
    discovery_function=discover_aws_rds_network_io,
    check_ruleset_name="if",
    check_default_parameters=interfaces.CHECK_DEFAULT_PARAMETERS,
    check_function=check_aws_rds_network_io,
)

# .
#   .--disk IO-------------------------------------------------------------.
#   |                         _ _     _      ___ ___                       |
#   |                      __| (_)___| | __ |_ _/ _ \                      |
#   |                     / _` | / __| |/ /  | | | | |                     |
#   |                    | (_| | \__ \   <   | | |_| |                     |
#   |                     \__,_|_|___/_|\_\ |___\___/                      |
#   |                                                                      |
#   '----------------------------------------------------------------------'


def discover_aws_rds_disk_io(section: AWSSectionMetrics) -> DiscoveryResult:
    yield from discover_aws_generic(
        section,
        [
            "DiskQueueDepth",
            "ReadIOPS",
            "ReadLatency",
            "ReadThroughput",
            "WriteIOPS",
            "WriteLatency",
            "WriteThroughput",
        ],
    )


def check_aws_rds_disk_io(
    item: str,
    params: Mapping[str, Any],
    section: AWSSectionMetrics,
) -> CheckResult:
    disk_data: MutableMapping[str, float] = {}

    if (metrics := section.get(item)) is None:
        return

    for key, metric_key, scale in [
        ("read_ios", "ReadIOPS", 1.0),
        ("write_ios", "WriteIOPS", 1.0),
        ("read_throughput", "ReadThroughput", 1.0),
        ("write_throughput", "WriteThroughput", 1.0),
        ("read_latency", "ReadLatency", 1000.0),
        ("write_latency", "WriteLatency", 1000.0),
    ]:
        if (metric := metrics.get(metric_key)) is None:
            continue
        disk_data[key] = metric * scale

    yield from check_diskstat_dict(
        params=params,
        disk=disk_data,
        value_store=get_value_store(),
        this_time=time.time(),
    )


register.check_plugin(
    name="aws_rds_disk_io",
    service_name="AWS/RDS %s Disk IO",
    check_function=check_aws_rds_disk_io,
    discovery_function=discover_aws_rds_disk_io,
    check_default_parameters={},
    check_ruleset_name="diskstat",
    sections=["aws_rds"],
)


#   .--CPU utilization-----------------------------------------------------.
#   |    ____ ____  _   _         _   _ _ _          _   _                 |
#   |   / ___|  _ \| | | |  _   _| |_(_) (_)______ _| |_(_) ___  _ __      |
#   |  | |   | |_) | | | | | | | | __| | | |_  / _` | __| |/ _ \| '_ \     |
#   |  | |___|  __/| |_| | | |_| | |_| | | |/ / (_| | |_| | (_) | | | |    |
#   |   \____|_|    \___/   \__,_|\__|_|_|_/___\__,_|\__|_|\___/|_| |_|    |
#   |                                                                      |
#   '----------------------------------------------------------------------'


def discover_aws_rds(section: AWSSectionMetrics) -> DiscoveryResult:
    yield from discover_aws_generic(
        section,
        ["CPUUtilization"],
    )


def check_aws_rds(item: str, params: Mapping[str, Any], section: AWSSectionMetrics) -> CheckResult:
    if (metrics := section.get(item)) is None:
        return

    yield from check_cpu_util(
        util=metrics["CPUUtilization"],
        params=params,
        value_store=get_value_store(),
        this_time=time.time(),
    )


register.check_plugin(
    name="aws_rds",
    service_name="AWS/RDS %s CPU Utilization",
    check_default_parameters={"levels": (80.0, 90.0)},
    check_ruleset_name="cpu_utilization_multiitem",
    check_function=check_aws_rds,
    discovery_function=discover_aws_rds,
)

# .
#   .--agent jobs----------------------------------------------------------.
#   |                                 _       _       _                    |
#   |           __ _  __ _  ___ _ __ | |_    (_) ___ | |__  ___            |
#   |          / _` |/ _` |/ _ \ '_ \| __|   | |/ _ \| '_ \/ __|           |
#   |         | (_| | (_| |  __/ | | | |_    | | (_) | |_) \__ \           |
#   |          \__,_|\__, |\___|_| |_|\__|  _/ |\___/|_.__/|___/           |
#   |                |___/                 |__/                            |
#   '----------------------------------------------------------------------'


def discover_aws_rds_agent_jobs(section: AWSSectionMetrics) -> DiscoveryResult:
    yield from discover_aws_generic(
        section,
        ["FailedSQLServerAgentJobsCount"],
    )


def check_aws_rds_agent_jobs(item: str, section: AWSSectionMetrics) -> CheckResult:
    if (metrics := section.get(item)) is None:
        return

    failed_agent_jobs = metrics["FailedSQLServerAgentJobsCount"]
    if failed_agent_jobs > 0:
        yield Result(
            state=State.WARN,
            summary=f"Rate of failing jobs: {aws_get_counts_rate_human_readable(failed_agent_jobs)}",
        )
        return

    yield Result(
        state=State.OK,
        summary=f"Rate of failing jobs: {aws_get_counts_rate_human_readable(failed_agent_jobs)}",
    )


register.check_plugin(
    name="aws_rds_agent_jobs",
    service_name="AWS/RDS %s SQL Server Agent Jobs",
    check_function=check_aws_rds_agent_jobs,
    discovery_function=discover_aws_rds_agent_jobs,
    sections=["aws_rds"],
)

# .
#   .--CPU credits---------------------------------------------------------.
#   |           ____ ____  _   _                     _ _ _                 |
#   |          / ___|  _ \| | | |   ___ _ __ ___  __| (_) |_ ___           |
#   |         | |   | |_) | | | |  / __| '__/ _ \/ _` | | __/ __|          |
#   |         | |___|  __/| |_| | | (__| | |  __/ (_| | | |_\__ \          |
#   |          \____|_|    \___/   \___|_|  \___|\__,_|_|\__|___/          |
#   |                                                                      |
#   '----------------------------------------------------------------------'

# CPU credit balance:
# For standard T2 instances with bursting, a burst can continue only as long as
# there are available CPU credits, so it’s important to monitor your instance’s
# balance. Credits are earned any time the instance is running below its baseline
# CPU performance level. The initial balance, accrual rate, and maximum possible
# balance are all dependent on the instance level.
#
# CPU credit usage:
# One CPU credit is equivalent to one minute of 100 percent CPU utilization (or
# two minutes at 50 percent, etc.). Whenever an instance requires CPU performance
# above that instance type’s baseline, it will burst, consuming CPU credits until
# the demand lessens or the credit balance runs out. Keeping an eye on your
# instances’ credit usage will help you identify whether you might need to switch
# to an instance type that is optimized for CPU-intensive workloads. Or, you can
# create an alert for when your credit balance drops below a threshold while CPU
# usage remains above baseline.


def discover_aws_rds_cpu_credits(section: AWSSectionMetrics) -> DiscoveryResult:
    yield from discover_aws_generic(
        section,
        [
            "CPUCreditUsage",
            "CPUCreditBalance",
        ],
    )


def check_aws_rds_cpu_credits(
    item: str,
    params: Mapping[str, Any],
    section: AWSSectionMetrics,
) -> CheckResult:
    if (metrics := section.get(item)) is None:
        return

    yield Result(state=State.OK, summary=f"CPU Credit Usage: {metrics['CPUCreditUsage']:.2f}")

    yield from check_levels(
        value=metrics["CPUCreditBalance"],
        metric_name="aws_cpu_credit_balance",
        levels_lower=params.get("balance_levels_lower", (None, None)),
        label="CPU Credit Balance",
    )

    if metrics.get("BurstBalance"):
        yield from check_levels(
            value=metrics["BurstBalance"],
            metric_name="aws_burst_balance",
            levels_lower=params.get("burst_balance_levels_lower", (None, None)),
            render_func=render.percent,
            label="Burst Balance",
        )


register.check_plugin(
    name="aws_rds_cpu_credits",
    service_name="AWS/RDS %s CPU Credits",
    check_function=check_aws_rds_cpu_credits,
    discovery_function=discover_aws_rds_cpu_credits,
    check_default_parameters={},
    check_ruleset_name="aws_rds_cpu_credits",
    sections=["aws_rds"],
)

# .
#   .--bin log usage-------------------------------------------------------.
#   |     _     _         _                                                |
#   |    | |__ (_)_ __   | | ___   __ _   _   _ ___  __ _  __ _  ___       |
#   |    | '_ \| | '_ \  | |/ _ \ / _` | | | | / __|/ _` |/ _` |/ _ \      |
#   |    | |_) | | | | | | | (_) | (_| | | |_| \__ \ (_| | (_| |  __/      |
#   |    |_.__/|_|_| |_| |_|\___/ \__, |  \__,_|___/\__,_|\__, |\___|      |
#   |                             |___/                   |___/            |
#   '----------------------------------------------------------------------'


def discover_aws_rds_bin_log_usage(section: AWSSectionMetrics) -> DiscoveryResult:
    yield from discover_aws_generic(
        section,
        ["BinLogDiskUsage"],
    )


def check_aws_rds_bin_log_usage(
    item: str,
    params: Mapping[str, Any],
    section: AWSSectionMetrics,
) -> CheckResult:
    if (metrics := section.get(item)) is None:
        return

    bin_log_usage = metrics["BinLogDiskUsage"]
    yield Result(state=State.OK, summary=render.bytes(bin_log_usage))

    if (allocated_storage := metrics.get("AllocatedStorage")) is None or allocated_storage == 0.0:
        yield Result(state=State.WARN, summary="Cannot calculate usage")
        return

    usage = 100.0 * bin_log_usage / allocated_storage
    yield from check_levels(
        value=usage,
        metric_name="aws_rds_bin_log_disk_usage",
        levels_upper=params.get("levels"),
        render_func=render.percent,
    )


register.check_plugin(
    name="aws_rds_bin_log_usage",
    check_function=check_aws_rds_bin_log_usage,
    discovery_function=discover_aws_rds_bin_log_usage,
    check_default_parameters={},
    check_ruleset_name="aws_rds_disk_usage",
    service_name="AWS/RDS %s Binary Log Usage",
    sections=["aws_rds"],
)
