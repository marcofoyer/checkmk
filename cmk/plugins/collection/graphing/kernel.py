#!/usr/bin/env python3
# Copyright (C) 2023 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.

from cmk.graphing.v1 import metrics, perfometers, Title, translations

translation_kernel = translations.Translation(
    name="kernel",
    check_commands=[translations.PassiveCheck("kernel")],
    translations={
        "ctxt": translations.RenameTo("context_switches"),
        "pgmajfault": translations.RenameTo("major_page_faults"),
        "processes": translations.RenameTo("process_creations"),
    },
)

UNIT_PER_SECOND = metrics.Unit(metrics.DecimalNotation("/s"))

metric_process_creations = metrics.Metric(
    name="process_creations",
    title=Title("Process creations"),
    unit=UNIT_PER_SECOND,
    color=metrics.Color.ORANGE,
)

metric_context_switches = metrics.Metric(
    name="context_switches",
    title=Title("Context switches"),
    unit=UNIT_PER_SECOND,
    color=metrics.Color.LIGHT_GREEN,
)

metric_major_page_faults = metrics.Metric(
    name="major_page_faults",
    title=Title("Major page faults"),
    unit=UNIT_PER_SECOND,
    color=metrics.Color.GREEN,
)

metric_page_swap_in = metrics.Metric(
    name="page_swap_in",
    title=Title("Page Swap In"),
    unit=UNIT_PER_SECOND,
    color=metrics.Color.CYAN,
)

metric_page_swap_out = metrics.Metric(
    name="page_swap_out",
    title=Title("Page Swap Out"),
    unit=UNIT_PER_SECOND,
    color=metrics.Color.BLUE,
)

perfometer_major_page_faults = perfometers.Perfometer(
    name="major_page_faults",
    focus_range=perfometers.FocusRange(
        perfometers.Closed(0),
        perfometers.Open(11313),
    ),
    segments=["major_page_faults"],
)
