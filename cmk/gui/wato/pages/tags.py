#!/usr/bin/env python
# -*- encoding: utf-8; py-indent-offset: 4 -*-
# +------------------------------------------------------------------+
# |             ____ _               _        __  __ _  __           |
# |            / ___| |__   ___  ___| | __   |  \/  | |/ /           |
# |           | |   | '_ \ / _ \/ __| |/ /   | |\/| | ' /            |
# |           | |___| | | |  __/ (__|   <    | |  | | . \            |
# |            \____|_| |_|\___|\___|_|\_\___|_|  |_|_|\_\           |
# |                                                                  |
# | Copyright Mathias Kettner 2014             mk@mathias-kettner.de |
# +------------------------------------------------------------------+
#
# This file is part of Check_MK.
# The official homepage is at http://mathias-kettner.de/check_mk.
#
# check_mk is free software;  you can redistribute it and/or modify it
# under the  terms of the  GNU General Public License  as published by
# the Free Software Foundation in version 2.  check_mk is  distributed
# in the hope that it will be useful, but WITHOUT ANY WARRANTY;  with-
# out even the implied warranty of  MERCHANTABILITY  or  FITNESS FOR A
# PARTICULAR PURPOSE. See the  GNU General Public License for more de-
# tails. You should have  received  a copy of the  GNU  General Public
# License along with GNU Make; see the file  COPYING.  If  not,  write
# to the Free Software Foundation, Inc., 51 Franklin St,  Fifth Floor,
# Boston, MA 02110-1301 USA.
"""Manage the variable config.wato_host_tags -> The set of tags to be assigned
to hosts and that is the basis of the rules."""

import abc
from enum import Enum

import cmk.gui.config as config
import cmk.gui.watolib as watolib
from cmk.gui.table import table_element
import cmk.gui.forms as forms
from cmk.gui.exceptions import MKUserError, MKAuthException
from cmk.gui.i18n import _, _u
from cmk.gui.globals import html
from cmk.gui.valuespec import (
    ListChoice,
    Foldable,
    Tuple,
    ListOf,
    Dictionary,
    TextAscii,
    TextUnicode,
    OptionalDropdownChoice,
    FixedValue,
    ID,
    Transform,
)

import cmk.utils.tags
from cmk.gui.watolib.tags import TagConfigFile

from cmk.gui.plugins.wato.utils.main_menu import (
    MainMenu,
    MenuItem,
)

from cmk.gui.plugins.wato.utils.html_elements import (
    wato_html_head,)

from cmk.gui.plugins.wato import (
    WatoMode,
    mode_registry,
    wato_confirm,
    global_buttons,
    make_action_link,
    add_change,
)


@mode_registry.register
class ModeTags(WatoMode):
    @classmethod
    def name(cls):
        return "tags"

    @classmethod
    def permissions(cls):
        return ["hosttags"]

    def __init__(self):
        super(ModeTags, self).__init__()
        self._builtin_config = cmk.utils.tags.BuiltinTagConfig()

        self._tag_config_file = TagConfigFile()
        self._tag_config = cmk.utils.tags.TagConfig()
        self._tag_config.parse_config(self._tag_config_file.load_for_reading())

        self._effective_config = cmk.utils.tags.TagConfig()
        self._effective_config.parse_config(self._tag_config.get_dict_format())
        self._effective_config += self._builtin_config

    def title(self):
        return _("Tag groups")

    def buttons(self):
        global_buttons()
        html.context_button(
            _("New tag group"), watolib.folder_preserving_link([("mode", "edit_tag")]), "new")
        html.context_button(
            _("New aux tag"), watolib.folder_preserving_link([("mode", "edit_auxtag")]), "new")

    def action(self):
        if html.request.has_var("_delete"):
            return self._delete_tag_group()

        if html.request.has_var("_del_aux"):
            return self._delete_aux_tag()

        if html.request.var("_move") and html.check_transaction():
            return self._move_tag_group()

    def _delete_tag_group(self):
        del_id = html.get_item_input("_delete", dict(self._tag_config.get_tag_group_choices()))[1]

        tag_group = self._tag_config.get_tag_group(del_id)
        if tag_group:
            operations = list(tag_group.get_tag_ids())
        else:
            operations = None

        message = _rename_tags_after_confirmation(del_id, operations)
        if message is True:  # no confirmation yet
            c = wato_confirm(
                _("Confirm deletion of the tag group '%s'") % del_id,
                _("Do you really want to delete the tag group '%s'?") % del_id)
            if c is False:
                return ""
            elif c is None:
                return None

        if message:
            self._tag_config.remove_tag_group(del_id)
            self._tag_config.validate_config()
            self._tag_config_file.save(self._tag_config.get_dict_format())
            watolib.Folder.invalidate_caches()
            watolib.Folder.root_folder().rewrite_hosts_files()
            add_change("edit-tags", _("Removed tag group %s (%s)") % (message, del_id))
            return "tags", message != True and message or None

    def _delete_aux_tag(self):
        del_id = html.get_item_input("_del_aux",
                                     dict(self._tag_config.aux_tag_list.get_choices()))[1]

        # Make sure that this aux tag is not begin used by any tag group
        for group in self._tag_config.tag_groups:
            for grouped_tag in group.tags:
                if del_id in grouped_tag.aux_tag_ids:
                    raise MKUserError(
                        None,
                        _("You cannot delete this auxiliary tag. "
                          "It is being used in the tag group <b>%s</b>.") % group.title)

        operations = {del_id: False}
        message = _rename_tags_after_confirmation(None, operations)
        if message is True:  # no confirmation yet
            c = wato_confirm(
                _("Confirm deletion of the auxiliary tag '%s'") % del_id,
                _("Do you really want to delete the auxiliary tag '%s'?") % del_id)
            if c is False:
                return ""
            elif c is None:
                return None

        if message:
            self._tag_config.aux_tag_list.remove(del_id)
            self._tag_config.validate_config()
            self._tag_config_file.save(self._tag_config.get_dict_format())
            watolib.Folder.invalidate_caches()
            watolib.Folder.root_folder().rewrite_hosts_files()
            add_change("edit-tags", _("Removed auxiliary tag %s (%s)") % (message, del_id))
            return "tags", message != True and message or None

    def _move_tag_group(self):
        move_nr = html.get_integer_input("_move")
        move_to = html.get_integer_input("_index")

        moved = self._tag_config.tag_groups.pop(move_nr)
        self._tag_config.tag_groups.insert(move_to, moved)

        self._tag_config.validate_config()
        self._tag_config_file.save(self._tag_config.get_dict_format())
        watolib.add_change("edit-tags", _("Changed order of tag groups"))

    def page(self):
        if not self._tag_config.tag_groups + self._tag_config.get_aux_tags():
            MainMenu([
                MenuItem(
                    "edit_ttag", _("Create new tag group"), "new", "hosttags",
                    _("Each tag group will create one dropdown choice in the host configuration.")),
                MenuItem(
                    "edit_auxtag", _("Create new auxiliary tag"), "new", "hosttags",
                    _("You can have these tags automatically added if certain primary tags are set."
                     )),
            ]).show()
            return

        self._render_tag_list()
        self._render_aux_tag_list()

    def _render_tag_list(self):
        with table_element(
                "tags",
                _("Tag groups"),
                help=(_("Tags are the basis of Check_MK's rule based configuration. "
                        "If the first step you define arbitrary tag groups. A host "
                        "has assigned exactly one tag out of each group. These tags can "
                        "later be used for defining parameters for hosts and services, "
                        "such as <i>disable notifications for all hosts with the tags "
                        "<b>Network device</b> and <b>Test</b></i>.")),
                empty_text=_("You haven't defined any tag groups yet."),
                searchable=False,
                sortable=False) as table:

            for nr, tag_group in enumerate(self._effective_config.tag_groups):
                table.row()
                table.cell(_("Actions"), css="buttons")
                self._show_tag_icons(tag_group, nr)

                table.text_cell(_("ID"), tag_group.id)
                table.text_cell(_("Title"), tag_group.title)
                table.text_cell(_("Topic"), tag_group.topic or _("Tags"))
                table.cell(_("Demonstration"), sortable=False)
                html.begin_form("tag_%s" % tag_group.id)
                watolib.host_attribute("tag_%s" % tag_group.id).render_input("", None)
                html.end_form()

    def _show_tag_icons(self, tag_group, nr):
        if self._builtin_config.tag_group_exists(tag_group.id):
            html.i("(%s)" % _("builtin"))
            return

        edit_url = watolib.folder_preserving_link([("mode", "edit_tag"), ("edit", tag_group.id)])
        html.icon_button(edit_url, _("Edit this tag group"), "edit")

        html.element_dragger_url("tr", base_url=make_action_link([("mode", "tags"), ("_move", nr)]))

        delete_url = make_action_link([("mode", "tags"), ("_delete", tag_group.id)])
        html.icon_button(delete_url, _("Delete this tag group"), "delete")

    def _render_aux_tag_list(self):
        with table_element(
                "auxtags",
                _("Auxiliary tags"),
                help=_("Auxiliary tags can be attached to other tags. That way "
                       "you can for example have all hosts with the tag <tt>cmk-agent</tt> "
                       "get also the tag <tt>tcp</tt>. This makes the configuration of "
                       "your hosts easier."),
                empty_text=_("You haven't defined any auxiliary tags."),
                searchable=False) as table:

            for aux_tag in self._effective_config.aux_tag_list.get_tags():
                table.row()
                table.cell(_("Actions"), css="buttons")
                if aux_tag.id in self._builtin_config.aux_tag_list.get_tag_ids():
                    html.i("(%s)" % _("builtin"))
                else:
                    edit_url = watolib.folder_preserving_link([("mode", "edit_auxtag"),
                                                               ("edit", aux_tag.id)])
                    delete_url = make_action_link([("mode", "tags"), ("_del_aux", aux_tag.id)])
                    html.icon_button(edit_url, _("Edit this auxiliary tag"), "edit")
                    html.icon_button(delete_url, _("Delete this auxiliary tag"), "delete")
                table.text_cell(_("ID"), aux_tag.id)

                table.text_cell(_("Title"), _u(aux_tag.title))
                table.text_cell(_("Topic"), _u(aux_tag.topic) or _("Tags"))
                table.text_cell(
                    _("Tags using this auxiliary tag"), ", ".join(
                        self._get_tags_using_aux_tag(aux_tag)))

    def _get_tags_using_aux_tag(self, aux_tag):
        used_tags = set()
        for tag_group in self._effective_config.tag_groups:
            for tag in tag_group.tags:
                if aux_tag in tag.aux_tag_ids:
                    used_tags.add(aux_tag.id)
        return sorted(used_tags)


class ABCEditTagMode(WatoMode):
    __metaclass__ = abc.ABCMeta

    @classmethod
    def permissions(cls):
        return ["hosttags"]

    def __init__(self):
        super(ABCEditTagMode, self).__init__()
        self._tag_config_file = TagConfigFile()
        self._untainted_hosttags_config = cmk.utils.tags.TagConfig()
        self._untainted_hosttags_config.parse_config(self._tag_config_file.load_for_reading())

        self._effective_config = cmk.utils.tags.TagConfig()
        self._effective_config.parse_config(self._untainted_hosttags_config.get_dict_format())
        self._effective_config += cmk.utils.tags.BuiltinTagConfig()

        self._id = self._get_id()
        self._new = self._is_new_tag()

    @abc.abstractmethod
    def _get_id(self):
        raise NotImplementedError()

    def _is_new_tag(self):
        return html.request.var("edit") is None

    def _basic_elements(self):
        if self._new:
            vs_id = ID(
                title=_("Tag ID"),
                size=60,
                allow_empty=False,
                help=_("The internal ID of the tag is used as it's unique identifier "
                       "It cannot be changed later."),
            )
        else:
            vs_id = FixedValue(
                self._id,
                title=_("Tag ID"),
            )

        return [
            ("id", vs_id),
            ("title", TextUnicode(
                title=_("Title"),
                size=60,
                allow_empty=False,
            )),
            ("topic", self._get_topic_valuespec()),
        ]

    def _get_topic_valuespec(self):
        return OptionalDropdownChoice(
            title=_("Topic") + "<sup>*</sup>",
            choices=self._effective_config.get_topic_choices(),
            explicit=TextUnicode(),
            otherlabel=_("Create new topic"),
            default_value=None,
            help=_("Different tags can be grouped in topics to make the visualization and "
                   "selections in the GUI more comfortable."),
        )


@mode_registry.register
class ModeEditAuxtag(ABCEditTagMode):
    @classmethod
    def name(cls):
        return "edit_auxtag"

    def __init__(self):
        super(ModeEditAuxtag, self).__init__()

        if self._new:
            self._aux_tag = cmk.utils.tags.AuxTag()
        else:
            self._aux_tag = self._untainted_hosttags_config.aux_tag_list.get_aux_tag(self._id)

    def _get_id(self):
        if not html.request.has_var("edit"):
            return None

        return html.get_item_input(
            "edit", dict(self._untainted_hosttags_config.aux_tag_list.get_choices()))[1]

    def title(self):
        if self._new:
            return _("Create new auxiliary tag")
        return _("Edit auxiliary tag")

    def buttons(self):
        html.context_button(
            _("All tags"), watolib.folder_preserving_link([("mode", "tags")]), "back")

    def action(self):
        if not html.check_transaction():
            return "tags"

        vs = self._valuespec()
        aux_tag_spec = vs.from_html_vars("aux_tag")
        vs.validate_value(aux_tag_spec, "aux_tag")

        self._aux_tag = cmk.utils.tags.AuxTag(aux_tag_spec)
        self._aux_tag.validate()

        changed_hosttags_config = cmk.utils.tags.TagConfig()
        changed_hosttags_config.parse_config(self._tag_config_file.load_for_reading())

        if self._new:
            changed_hosttags_config.aux_tag_list.append(self._aux_tag)
        else:
            changed_hosttags_config.aux_tag_list.update(self._id, self._aux_tag)
        changed_hosttags_config.validate_config()

        self._tag_config_file.save(changed_hosttags_config.get_dict_format())

        return "tags"

    def page(self):
        html.begin_form("aux_tag")

        self._valuespec().render_input("aux_tag", self._aux_tag.get_dict_format())

        forms.end()
        html.show_localization_hint()
        html.button("save", _("Save"))
        html.hidden_fields()
        html.end_form()

    def _valuespec(self):
        return Dictionary(
            title=_("Basic settings"),
            elements=self._basic_elements(),
            render="form",
            form_narrow=True,
            optional_keys=[],
        )


@mode_registry.register
class ModeEditTagGroup(ABCEditTagMode):
    @classmethod
    def name(cls):
        return "edit_tag"

    def __init__(self):
        super(ModeEditTagGroup, self).__init__()

        self._untainted_tag_group = self._untainted_hosttags_config.get_tag_group(self._id)
        if not self._untainted_tag_group:
            self._untainted_tag_group = cmk.utils.tags.TagGroup()

        self._tag_group = self._untainted_hosttags_config.get_tag_group(
            self._id) or cmk.utils.tags.TagGroup()

    def _get_id(self):
        return html.request.var("edit", html.request.var("tag_id"))

    def title(self):
        if self._new:
            return _("Create new tag group")
        return _("Edit tag group")

    def buttons(self):
        html.context_button(
            _("All tags"), watolib.folder_preserving_link([("mode", "tags")]), "back")

    def action(self):
        if not html.check_transaction():
            return "tags"

        vs = self._valuespec()
        tag_group_spec = vs.from_html_vars("tag_group")
        vs.validate_value(tag_group_spec, "tag_group")

        # Create new object with existing host tags
        changed_hosttags_config = cmk.utils.tags.TagConfig()
        changed_hosttags_config.parse_config(self._tag_config_file.load_for_modification())

        changed_tag_group = cmk.utils.tags.TagGroup(tag_group_spec)
        self._tag_group = changed_tag_group

        if self._new:
            # Inserts and verifies changed tag group
            changed_hosttags_config.insert_tag_group(changed_tag_group)
            changed_hosttags_config.validate_config()
            self._tag_config_file.save(changed_hosttags_config.get_dict_format())

            # Make sure, that all tags are active (also manual ones from main.mk)
            config.load_config()
            add_change("edit-hosttags", _("Created new host tag group '%s'") % changed_tag_group.id)
            return "tags", _("Created new host tag group '%s'") % changed_tag_group.title

        # Updates and verifies changed tag group
        changed_hosttags_config.update_tag_group(changed_tag_group)
        changed_hosttags_config.validate_config()

        # This is the major effort of WATO when it comes to
        # host tags: renaming and deleting of tags that might be
        # in use by folders, hosts and rules. First we create a
        # kind of "patch" from the old to the new tags. The renaming
        # of a tag is detected by comparing the titles. Addition
        # of new tags is not a problem and need not be handled.
        # Result of this is the dict 'operations': it's keys are
        # current tag names, its values the corresponding new names
        # or False in case of tag removals.
        operations = {}

        # Detect renaming
        new_by_title = dict([(tag.title, tag.id) for tag in changed_tag_group.tags])

        for former_tag in self._untainted_tag_group.tags:
            if former_tag.title in new_by_title:
                new_id = new_by_title[former_tag.title]
                if new_id != former_tag.id:
                    operations[former_tag.id] = new_id  # might be None

        # Detect removal
        for former_tag in self._untainted_tag_group.tags:
            if former_tag.id is not None \
                and former_tag.id not in [ tmp_tag.id for tmp_tag in changed_tag_group.tags ] \
                and former_tag.id not in operations:
                # remove explicit tag (hosts/folders) or remove it from tag specs (rules)
                operations[former_tag.id] = False

        # Now check, if any folders, hosts or rules are affected
        message = _rename_tags_after_confirmation(changed_tag_group.id, operations)
        if message:
            self._tag_config_file.save(changed_hosttags_config.get_dict_format())
            config.load_config()
            add_change("edit-hosttags", _("Edited host tag group %s (%s)") % (message, self._id))
            return "tags", message != True and message or None

        return "tags"

    def page(self):
        html.begin_form("tag_group", method='POST')

        self._valuespec().render_input("tag_group", self._tag_group.get_dict_format())

        forms.end()
        html.show_localization_hint()

        html.button("save", _("Save"))
        html.hidden_fields()
        html.end_form()

    def _valuespec(self):
        basic_elements = self._basic_elements()
        tag_choice_elements = self._tag_choices_elements()

        return Dictionary(
            elements=basic_elements + tag_choice_elements,
            headers=[
                (_("Basic settings"), [k for k, _vs in basic_elements]),
                (_("Tag choices"), [k for k, _vs in tag_choice_elements]),
            ],
            render="form",
            form_narrow=True,
            optional_keys=[],
        )

    def _tag_choices_elements(self):
        return [
            ("tags", self._tag_choices_valuespec()),
        ]

    def _tag_choices_valuespec(self):
        # We want the compact tuple style visualization which is not
        # supported by the Dictionary valuespec. Transform!
        return Transform(
            ListOf(
                Tuple(
                    elements=[
                        TextAscii(
                            title=_("Tag ID"),
                            size=16,
                            regex="^[-a-z0-9A-Z_]*$",
                            none_is_empty=True,
                            regex_error=_("Invalid tag ID. Only the characters a-z, A-Z, "
                                          "0-9, _ and - are allowed.")),
                        TextUnicode(title=_("Title") + "*", allow_empty=False, size=40),
                        Foldable(
                            ListChoice(
                                title=_("Auxiliary tags"),
                                choices=self._effective_config.aux_tag_list.get_choices(),
                            )),
                    ],
                    show_titles=True,
                    orientation="horizontal",
                ),
                add_label=_("Add tag choice"),
                row_label="@. Choice",
                sort_by=1,  # sort by description
                help=_("The first choice of a tag group will be its default value. "
                       "If a tag group has only one choice, it will be displayed "
                       "as a checkbox and set or not set the only tag. If it has "
                       "more choices you may leave at most one tag id empty. A host "
                       "with that choice will not get any tag of this group.<br><br>"
                       "The tag ID must contain only of letters, digits and "
                       "underscores.<br><br><b>Renaming tags ID:</b> if you want "
                       "to rename the ID of a tag, then please make sure that you do not "
                       "change its title at the same time! Otherwise WATO will not "
                       "be able to detect the renaming and cannot exchange the tags "
                       "in all folders, hosts and rules accordingly."),
            ),
            forth=lambda x: [(c["id"], c["title"], c["aux_tags"]) for c in x],
            back=lambda x: [dict(zip(["id", "title", "aux_tags"], c)) for c in x],
        )


class TagCleanupMode(Enum):
    ABORT = "abort"  # No further action. Aborting here.
    CHECK = "check"  # only affected rulesets are collected, nothing is modified
    DELETE = "delete"  # Rules using this tag are deleted
    REMOVE = "remove"  # Remove tags from rules
    REPAIR = "repair"  # Remove tags from rules


def _rename_tags_after_confirmation(tag_group_id, operations):
    """Handle renaming and deletion of tags

    Find affected hosts, folders and rules. Remove or fix those rules according
    the the users' wishes. In case auf auxiliary tags the tag_id is None. In
    other cases it is the id of the tag group currently being edited.

    operations is either:
    - a list of tag_ids to be handled (e.g. all tag_ids of a tag group)
    - a dictionary of
      - old_tag_id: new_tag_id pairs to be replaced
      - old_tag_id: None/False to remove old_tag_id
    """

    repair_mode = html.request.var("_repair")
    if repair_mode is not None:
        try:
            mode = TagCleanupMode(repair_mode)
        except ValueError:
            raise MKUserError("_repair", "Invalid mode")

        if mode == TagCleanupMode.ABORT:
            raise MKUserError("id_0", _("Aborting change."))

        # make attribute unknown to system, important for save() operations
        if tag_group_id and isinstance(operations, list):
            watolib.host_attributes.undeclare_host_tag_attribute(tag_group_id)

        affected_folders, affected_hosts, affected_rulesets = \
        _change_host_tags_in_folders(tag_group_id, operations, mode, watolib.Folder.root_folder())

        return _("Modified folders: %d, modified hosts: %d, modified rulesets: %d") % \
            (len(affected_folders), len(affected_hosts), len(affected_rulesets))

    message = ""
    affected_folders, affected_hosts, affected_rulesets = \
        _change_host_tags_in_folders(tag_group_id, operations, TagCleanupMode.CHECK, watolib.Folder.root_folder())

    if affected_folders:
        message += _("Affected folders with an explicit reference to this tag "
                     "group and that are affected by the change") + ":<ul>"
        for folder in affected_folders:
            message += '<li><a href="%s">%s</a></li>' % (folder.edit_url(), folder.alias_path())
        message += "</ul>"

    if affected_hosts:
        message += _("Hosts where this tag group is explicitely set "
                     "and that are effected by the change") + ":<ul><li>"
        for nr, host in enumerate(affected_hosts):
            if nr > 20:
                message += "... (%d more)" % (len(affected_hosts) - 20)
                break
            elif nr > 0:
                message += ", "

            message += '<a href="%s">%s</a>' % (host.edit_url(), host.name())
        message += "</li></ul>"

    if affected_rulesets:
        message += _("Rulesets that contain rules with references to the changed tags") + ":<ul>"
        for ruleset in affected_rulesets:
            message += '<li><a href="%s">%s</a></li>' % (watolib.folder_preserving_link(
                [("mode", "edit_ruleset"), ("varname", ruleset.name)]), ruleset.title())
        message += "</ul>"

    if not message and isinstance(operations, tuple):  # deletion of unused tag group
        html.open_div(class_="really")
        html.begin_form("confirm")
        html.write_text(_("Please confirm the deletion of the tag group."))
        html.button("_abort", _("Abort"))
        html.button("_do_confirm", _("Proceed"))
        html.hidden_fields(add_action_vars=True)
        html.end_form()
        html.close_div()

    elif message:
        if isinstance(operations, list):
            wato_html_head(_("Confirm tag deletion"))
        else:
            wato_html_head(_("Confirm tag modifications"))
        html.open_div(class_="really")
        html.h3(_("Your modifications affect some objects"))
        html.write_text(message)
        html.br()
        html.write_text(
            _("WATO can repair things for you. It can rename tags in folders, host and rules. "
              "Removed tag groups will be removed from hosts and folders, removed tags will be "
              "replaced with the default value for the tag group (for hosts and folders). What "
              "rules concern, you have to decide how to proceed."))
        html.begin_form("confirm")

        # Check if operations contains removal
        if isinstance(operations, list):
            have_removal = True
        else:
            have_removal = False
            for new_val in operations.values():
                if not new_val:
                    have_removal = True
                    break

        if affected_rulesets and have_removal:
            html.br()
            html.b(
                _("Some tags that are used in rules have been removed by you. What "
                  "shall we do with that rules?"))
            html.open_ul()
            html.radiobutton("_repair", "remove", True,
                             _("Just remove the affected tags from the rules."))
            html.br()
            html.radiobutton(
                "_repair", "delete", False,
                _("Delete rules containing tags that have been removed, if tag is used in a positive sense. Just remove that tag if it's used negated."
                 ))
        else:
            html.open_ul()
            html.radiobutton("_repair", "repair", True, _("Fix affected folders, hosts and rules."))

        html.br()
        html.radiobutton("_repair", "abort", False, _("Abort your modifications."))
        html.close_ul()

        html.button("_do_confirm", _("Proceed"), "")
        html.hidden_fields(add_action_vars=True)
        html.end_form()
        html.close_div()
        return False

    return True


def _change_host_tags_in_folders(tag_group_id, operations, mode, folder):
    """Update host tag assignments in hosts/folders

    tag_group_id is None -> Auxiliary tag has been deleted, no tag group affected
    See _rename_tags_after_confirmation() doc string for additional information.
    """
    affected_folders = []
    affected_hosts = []
    affected_rulesets = []
    if tag_group_id:
        aff_folders = _change_host_tags_in_host_or_folder(tag_group_id, operations, mode, folder)
        affected_folders += aff_folders

        if aff_folders and mode != TagCleanupMode.CHECK:
            try:
                folder.save()
            except MKAuthException:
                # Ignore MKAuthExceptions of locked host.mk files
                pass

        for subfolder in folder.all_subfolders().values():
            aff_folders, aff_hosts, aff_rulespecs = _change_host_tags_in_folders(
                tag_group_id, operations, mode, subfolder)
            affected_folders += aff_folders
            affected_hosts += aff_hosts
            affected_rulesets += aff_rulespecs

        affected_hosts += _change_host_tags_in_hosts(tag_group_id, operations, mode, folder)

    affected_rulesets += _change_host_tags_in_rules(tag_group_id, operations, mode, folder)
    return affected_folders, affected_hosts, affected_rulesets


def _change_host_tags_in_hosts(tag_group_id, operations, mode, folder):
    affected_hosts = []
    for host in folder.hosts().itervalues():
        aff_hosts = _change_host_tags_in_host_or_folder(tag_group_id, operations, mode, host)
        affected_hosts += aff_hosts

    if affected_hosts and mode != TagCleanupMode.CHECK:
        try:
            folder.save_hosts()
        except MKAuthException:
            # Ignore MKAuthExceptions of locked host.mk files
            pass
    return affected_hosts


def _change_host_tags_in_host_or_folder(tag_group_id, operations, mode, host_or_folder):
    affected = []

    attrname = "tag_" + tag_group_id
    attributes = host_or_folder.attributes()
    if attrname not in attributes:
        return affected  # The attribute is not set

    # Deletion of a tag group
    if isinstance(operations, list):
        if attrname in attributes:
            affected.append(host_or_folder)
            if mode != TagCleanupMode.CHECK:
                del attributes[attrname]
        return affected

    # Deletion or replacement of a tag choice
    current = attributes[attrname]
    if current in operations:
        affected.append(host_or_folder)
        if mode != TagCleanupMode.CHECK:
            new_tag = operations[current]
            if new_tag is False:  # tag choice has been removed -> fall back to default
                del attributes[attrname]
            else:
                attributes[attrname] = new_tag

    return affected


def _change_host_tags_in_rules(tag_group_id, operations, mode, folder):
    """Update tags in all rules

    The function parses all rules in all rulesets and looks for host tags that
    have been removed or renamed. If tags are removed then the depending on the
    mode affected rules are either deleted ("delete") or the vanished tags are
    removed from the rule ("remove").

    See _rename_tags_after_confirmation() doc string for additional information.
    """
    affected_rulesets = set()

    rulesets = watolib.FolderRulesets(folder)
    rulesets.load()

    for ruleset in rulesets.get_rulesets().itervalues():
        for _folder, _rulenr, rule in ruleset.get_rules():
            affected_rulesets.update(
                _change_host_tags_in_rule(tag_group_id, operations, mode, ruleset, rule))

    if affected_rulesets and mode != TagCleanupMode.CHECK:
        rulesets.save()

    return sorted(affected_rulesets, key=lambda x: x.title())


def _change_host_tags_in_rule(tag_group_id, operations, mode, ruleset, rule):
    affected_rulesets = set()

    # Handle deletion of complete tag group
    if isinstance(operations, list):
        if tag_group_id in rule.conditions.host_tags:
            affected_rulesets.add(ruleset)

            if mode == TagCleanupMode.CHECK:
                pass

            elif mode == TagCleanupMode.DELETE:
                ruleset.delete_rule(rule)
            else:
                del rule.conditions.host_tags[tag_group_id]

        return affected_rulesets

    # Removal or renaming of single tag choices
    for old_tag, new_tag in operations.items():
        # The case that old_tag is None (an empty tag has got a name)
        # cannot be handled when it comes to rules. Rules do not support
        # such None-values.
        if not old_tag:
            continue

        if old_tag not in rule.tag_specs and ("!" + old_tag) not in rule.tag_specs:
            continue  # old tag id is not configured

        affected_rulesets.add(ruleset)

        if mode == TagCleanupMode.CHECK:
            continue  # Skip modification

        if old_tag in rule.tag_specs:
            rule.tag_specs.remove(old_tag)
            if new_tag:
                rule.tag_specs.append(new_tag)
            elif mode == TagCleanupMode.DELETE:
                ruleset.delete_rule(rule)

        # negated tag has been renamed or removed
        if "!" + old_tag in rule.tag_specs:
            rule.tag_specs.remove("!" + old_tag)
            if new_tag:
                rule.tag_specs.append("!" + new_tag)
            # the case "delete" need not be handled here. Negated
            # tags can always be removed without changing the rule's
            # behaviour.

    return affected_rulesets
