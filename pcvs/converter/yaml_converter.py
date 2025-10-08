import json
import os
import pprint
import re
import sys

import click
from ruamel.yaml import YAML

import pcvs
from pcvs import io
from pcvs.helpers.exceptions import CommonException

desc_dict = dict()


def separate_key_and_value(s: str, c: str) -> tuple:
    """helper to split the key and value from a string"""
    array = s.split(c)
    if len(array) > 1:
        k = array[0]
        v = "".join(array[1:])

        if v.lower() == "true":
            v = True
        elif v.lower() == "false":
            v = False

        return (k, v)
    else:
        return (s, None)


def set_with(data, klist, val, append=False):
    """Add a value to a n-depth dict where the depth is declared as
    a list of intermediate keys. the 'append' flag indicates if the given
    'value' should be appended or replace the original content
    """
    # Just in case intermediate keys do not exist
    for key in klist[:-1]:
        data = data.setdefault(key, {})

    # if the value should be appended
    if append:
        # if the key doe not exist, create the list
        if klist[-1] not in data:
            data[klist[-1]] = list()
        # if it exists and is not a list ==> complain!
        elif not isinstance(data[klist[-1]], list):
            raise TypeError("fail")
        # append the value
        data[klist[-1]].append(val)
    else:
        # replace the value
        data[klist[-1]] = val


def flatten(dd, prefix="") -> dict:
    """make the n-depth dict 'dd' a "flat" version, where the successive keys
    are chained in a tuple. for instance:
    {'a': {'b': {'c': value}}} --> {('a', 'b', 'c'): value}
    """
    return (
        {
            prefix + "||" + k if prefix else k: v
            for kk, vv in dd.items()
            for k, v in flatten(vv, kk).items()
        }
        if isinstance(dd, dict)
        else {prefix: dd}
    )


def compute_new_key(k, m) -> str:
    """replace in 'k' any pattern found in 'm'.
    'k' is a string with placeholders, while 'm' is a match result with groups
    named after placeholders.
    This function will also expand the placeholder if 'call:' token is used to
    execute python code on the fly (complex transformation)
    """

    # basic replace the whole string with any placeholder
    for elt in m.groupdict().keys():
        k = k.replace(".", "||").replace("<" + elt + ">", m.group(elt))

    return k


def check_if_key_matches(key, ref_array) -> tuple:
    """list all matches for the current key in the new YAML description."""
    # for each key to be replaced.
    # WARNING: no order!
    for old_k, new_k in ref_array.items():
        # compile the regex (useful ?)
        r = re.compile(old_k)
        if re.fullmatch(r, key) is not None:  # if the key exist
            # CAUTION: we only parse the first match_obj iteration:
            # we do not consider a token to match multiple times in
            # the source key!
            res = next(r.finditer(key))
            # if there is a associated key in the new tree
            if new_k is not None:
                if isinstance(new_k, list):
                    dest_k = [compute_new_key(i, res) for i in new_k]
                else:
                    dest_k = [compute_new_key(new_k, res)]
            else:
                dest_k = []
            return (True, dest_k)
        else:  # the key does not exist
            pass
    return (False, [])


def process(data, ref_array=None, warn_if_missing=True) -> dict:
    """Process YAML dict 'data' and return a transformed dict"""
    output = dict()

    # desc_dict['second'] is set to contain all keys
    # by opposition to desc_dict['first'] containing modifiers
    if not ref_array:
        ref_array = desc_dict["second"]

    # browse original data
    for k, v in data.items():
        # if the node changed and should be moved, the tuple contains:
        # - valid = node changed = key has been found in the desc.
        # - dest_k = an array where each elt can be:
        #    * the new key value
        #    * the new key alongside with the transformed value as well
        # in the latter case, a split is required to identify key & value
        # an array is returned as a single node can produe multiple new nodes
        (valid, dest_k) = check_if_key_matches(k, ref_array)
        if valid:
            io.console.info("Processing {}".format(k))
            # An empty array means the key does not exist in the new tree.
            # => discard
            if len(dest_k) <= 0:
                continue

            # Process each of the new keys
            for elt_dest_k in dest_k:
                (final_k, final_v, token) = (elt_dest_k, None, "")
                # src key won't be kept
                if final_k is None:
                    continue
                # if a split is required
                for token in ["|+|", "|=|"]:
                    (final_k, final_v) = separate_key_and_value(elt_dest_k, token)
                    # the split() succeeded ? stop
                    if final_v:
                        break

                # special case to handle the "+" operator to append a value
                should_append = token == "+"
                # if none of the split() succeeded, just keep the old value
                final_v = v if not final_v else final_v
                # set the new key with the new value
                set_with(output, final_k.split("||"), final_v, should_append)
        else:
            # warn when an old_key hasn't be declared in spec.
            io.console.info("DISCARDING {}".format(k))
            if warn_if_missing:
                io.console.warn("Key {} undeclared in spec.".format(k))
                set_with(output, ["pcvs_missing"] + k.split("||"), v)
            else:
                set_with(output, k.split("||"), v)
    return output


def process_modifiers(data):
    """applies rules in-place for the data dict.
    Rules are present in the desc_dict['first'] sub-dict."""
    if "first" in desc_dict.keys():
        # do not warn for missing keys in that case (incomplete)
        return process(data, desc_dict["first"], warn_if_missing=False)
    else:
        return data


def replace_placeholder(tmp, refs) -> dict:
    """
    The given TMP should be a dict, where keys contain placeholders, wrapped
    with "<>". Each placeholder will be replaced (i.e. key will be changed) by
    the associated value in refs."""

    final = dict()
    for old, new in tmp.items():
        if old.startswith("__"):
            continue

        replacement = []
        for elt in old.split("."):
            insert = False
            for valid_k in refs.keys():
                if valid_k in elt:
                    insert = True
                    replacement.append(elt.replace(valid_k, refs[valid_k]))
            if not insert:
                replacement.append(re.escape(elt))
        # this backslash are needed, do not ask WHY.
        final[r"\|\|".join(replacement)] = new
    return final


def convert(input_file, kind, template, scheme, out, stdout, skip_unknown, in_place) -> None:
    """
    Process the conversion from one YAML format to another.
    Conversion specifications are described by the SCHEME file.
    """
    kind = kind.lower()
    io.console.print_header("YAML Conversion")

    if in_place and (stdout or out is not None):
        raise click.BadOptionUsage(
            "--stdout/--in-place",
            "Cannot use --in-place option with any other output options (--output/--stdout)",
        )
    elif in_place:
        out = input_file

    if template is None and kind == "te":
        io.console.warn(
            "\n".join(
                [
                    "If the TE file contains YAML aliases, the conversion may",
                    "fail. Use the '--template' option to provide the YAML file",
                    "containing these aliases",
                ]
            )
        )
    if kind == "profile":
        kind = ""
    # load the input file
    f = sys.stdin if input_file == "-" else open(input_file, "r")
    try:
        io.console.print_item("Load data file: {}".format(f.name))
        stream = f.read()
        if template:
            io.console.print_item("Load template file: {}".format(template))
            stream = open(template, "r").read() + stream
        data_to_convert = YAML(typ="safe").load(stream)
    except YAML.composer.ComposerError as e:
        raise CommonException.IOError(e, template) from e

    # load the scheme
    if not scheme:
        scheme = open(os.path.join(pcvs.PATH_INSTDIR, "converter/convert.json"))
    io.console.print_item("Load scheme file: {}".format(scheme.name))
    tmp = json.load(scheme)

    # if modifiers are declared, replace token with regexes
    if "__modifiers" in tmp.keys():
        desc_dict["first"] = replace_placeholder(tmp["__modifiers"], tmp["__tokens"])
    desc_dict["second"] = replace_placeholder(tmp, tmp["__tokens"])

    io.console.info(["Conversion list {old_key -> new_key):", f"{tmp}"])

    # first, "flattening" the original array: {(1, 2, 3): "val"}
    data_to_convert = flatten(data_to_convert, kind)

    # then, process modifiers, altering original data before processing
    io.console.print_item("Process alterations to the original data")
    data_to_convert = process_modifiers(data_to_convert)
    # as modifiers may have created nested dictionaries:
    # => "flattening" again, but with no prefix (persistent from first)
    data_to_convert = flatten(data_to_convert, "")

    # Finally, convert the original data to the final yaml dict
    io.console.print_item("Process the data")
    final_data = process(data_to_convert, warn_if_missing=not skip_unknown)

    # remove appended kind (if any)
    final_data = final_data.get(kind, final_data)
    # remove template key from the output to avoid polluting the caller
    io.console.print_item("Pruning templates from the final data")
    invalid_nodes = [k for k in final_data.keys() if k.startswith("pcvst_")]
    io.console.info(["Prune the following:", "{}".format(pprint.pformat(invalid_nodes))])

    for x in invalid_nodes + ["pcvs_missing"]:
        final_data.pop(x, None)

    io.console.info(["Final layout:", "{}".format(pprint.pformat(final_data))])

    if stdout:
        f = sys.stdout
    else:
        if out is None:
            prefix, base = os.path.split("./file.yml" if input_file == "-" else input_file)
            out = os.path.join(prefix, "convert-" + base)
        f = open(out, "w")

    io.console.print_section("Converted data written into {}".format(f.name))
    YAML(typ="safe").dump(final_data, f)

    f.flush()
    if not stdout:
        f.close()


# FIXME:
# MISSING:
# - compiler.package_manager
# - runtime.package_manager
# - te.package_manager
# """
