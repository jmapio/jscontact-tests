import copy
from collections.abc import Container, Mapping, Sequence
from dataclasses import dataclass
import json


def remove_defaultval(jsobj: dict, path: tuple[str], defaultval):
    if not path or not jsobj:
        return

    (name, subpath) = (path[0], path[1:])
    if name == "*" and subpath:
        try:
            iter = jsobj.values()
        except:
            iter = jsobj.__iter__()
        for subobj in iter:
            remove_defaultval(subobj, subpath, defaultval)
    elif subpath:
        remove_defaultval(jsobj.get(name), subpath, defaultval)
    elif jsobj.get(name) == defaultval:
        del jsobj[name]


def sort_unordered_components(jsobj: dict):
    try:
        if not jsobj.get("isOrdered", False) and jsobj["components"]:
            comps = jsobj["components"]
            comps.sort(key=lambda v: json.dumps(v, sort_keys=True))
            jsobj["components"] = comps
    except KeyError:
        pass


def apply_patchobject(jscard: dict, pobj: dict):
    for key, val in pobj.items():
        jsobj = jscard
        path = key.split("/")
        if not path:
            raise ValueError(key)
        while path:
            if isinstance(jsobj, Sequence) and not isinstance(jsobj, str):
                try:
                    jsobj = jsobj[int(path[0])]
                except (ValueError, IndexError):
                    raise ValueError(path)
            else:
                try:
                    jsobj = jsobj[path[0]]
                except KeyError:
                    if len(path) != 1:
                        raise ValueError(path)
                    jsobj[path[0]] = val
            path = path[1:]


def normalize_vcardparams(jsobj):
    if isinstance(jsobj, Mapping):
        try:
            del jsobj["vCardParams"]["group"]
            if not jsobj["vCardParams"]:
                del jsobj["vCardParams"]
        except KeyError:
            pass
        for jval in jsobj.values():
            normalize_vcardparams(jval)
    elif isinstance(jsobj, Sequence) and not isinstance(jsobj, str):
        for jval in jsobj:
            normalize_vcardparams(jval)


def normalize_jscard(jscard: dict):
    default_values = {
        ("addresses", "*", "@type"): "Address",
        ("addresses", "*", "isOrdered"): False,
        ("addresses", "*", "components", "*", "@type"): "AddressComponent",
        ("anniversaries", "*", "@type"): "Anniversary",
        ("anniversaries", "*", "date", "@type"): "PartialDate",
        ("anniversaries", "*", "place", "@type"): "Address",
        ("calendars", "*", "@type"): "Calendar",
        ("cryptoKeys", "*", "@type"): "CryptoKey",
        ("directories", "*", "@type"): "Directory",
        ("emails", "*", "@type"): "EmailAddress",
        ("kind",): "individual",
        ("links", "*", "@type"): "Link",
        ("media", "*", "@type"): "Media",
        ("name", "@type"): "Name",
        ("name", "isOrdered"): False,
        ("name", "components", "*", "@type"): "NameComponent",
        ("nicknames", "*", "@type"): "Nickname",
        ("notes", "*", "@type"): "Note",
        ("notes", "*", "author", "@type"): "Author",
        ("onlineServices", "*", "@type"): "OnlineService",
        ("organizations", "*", "@type"): "Organization",
        ("organizations", "*", "units", "*", "@type"): "OrgUnit",
        ("personalInfo", "*", "@type"): "PersonalInfo",
        ("phones", "*", "@type"): "Phone",
        ("preferredLanguages", "*", "@type"): "LanguagePref",
        ("relatedTo", "*", "@type"): "Relation",
        ("schedulingAddresses", "*", "@type"): "SchedulingAddress",
        ("speakToAs", "@type"): "SpeakToAs",
        ("speakToAs", "pronouns", "*", "@type"): "Pronouns",
        ("titles", "*", "@type"): "Title",
        ("titles", "*", "kind"): "title",
    }

    localizations = jscard.pop("localizations", None)

    for path, val in default_values.items():
        remove_defaultval(jscard, path, val)

    if "name" in jscard:
        sort_unordered_components(jscard["name"])
    if "addresses" in jscard:
        for id in jscard["addresses"].keys():
            sort_unordered_components(jscard["addresses"][id])

    # Ignore implementation-specific vCard properties and parameters
    if "vCardProps" in jscard:
        props = [p for p in jscard["vCardProps"] if p[0] != "version"]
        if props:
            jscard["vCardProps"] = props
        else:
            del jscard["vCardProps"]
    normalize_vcardparams(jscard)

    # Replace the patch objects in localizations with
    # the complete, patched Card. Keep invalid patches.
    if localizations:
        for l in list(localizations.keys()):
            patched_jscard = copy.deepcopy(jscard)
            try:
                apply_patchobject(patched_jscard, localizations[l])
                normalize_jscard(patched_jscard)
                localizations[l] = patched_jscard
            except ValueError:
                pass
        jscard["localizations"] = localizations


def encode_path(segs: list[str]) -> str:
    if len(segs) and segs[0] == "localizations":
        return "/".join(segs)
    else:
        return "/".join([p.replace("~", "~0").replace("/", "~1") for p in segs])


@dataclass
class JSPropDiff:
    path: str
    a_val: None = None
    b_val: None = None


def diff_list(a: Sequence, b: Sequence, diffs: list[JSPropDiff], segs: list[str]):
    if len(a) != len(b):
        diffs.append(JSPropDiff(encode_path(segs), a_val=a, b_val=b))
        return

    for i in range(len(a)):
        a_val = a[i]
        b_val = b[i]
        if isinstance(a_val, Mapping) and isinstance(b_val, Mapping):
            diff_objs(a_val, b_val, diffs, segs + [str(i)])
        elif (
            not isinstance(a_val, str)
            and not isinstance(b_val, str)
            and isinstance(a_val, Sequence)
            and isinstance(b_val, Sequence)
        ):
            diff_list(a_val, b_val, diffs, segs + [str(i)])
        elif a_val != b_val:
            diffs.append(
                JSPropDiff(encode_path(segs + [str(i)]), a_val=a_val, b_val=b_val)
            )


def diff_objs(a: Mapping, b: Mapping, diffs: list[JSPropDiff], segs: list[str]):
    a_keys = frozenset(a.keys())
    b_keys = frozenset(b.keys())

    for key in a_keys - b_keys:
        diffs.append(JSPropDiff(encode_path(segs + [key]), a_val=a[key]))

    for key in b_keys - a_keys:
        diffs.append(JSPropDiff(encode_path(segs + [key]), b_val=b[key]))

    for key in a_keys & b_keys:
        a_val = a[key]
        b_val = b[key]
        if isinstance(a_val, Mapping) and isinstance(b_val, Mapping):
            diff_objs(a_val, b_val, diffs, segs + [key])
        elif (
            not isinstance(a_val, str)
            and not isinstance(b_val, str)
            and isinstance(a_val, Sequence)
            and isinstance(b_val, Sequence)
        ):
            diff_list(a_val, b_val, diffs, segs + [key])
        elif a_val != b_val:
            diffs.append(
                JSPropDiff(encode_path(segs + [key]), a_val=a_val, b_val=b_val)
            )


def remove_unknown_vendorprops(want_card: dict, have_card: dict):
    # TODO this currently only deals with top-level properties
    for prop in list(have_card.keys()):
        if prop.find(":") >= 0:
            if not prop in want_card:
                del have_card[prop]


class MatchJSCardError(Exception):
    diff: list[JSPropDiff]

    def __init__(self, diffs):
        super().__init__("Card does not match")
        self.diff = diffs


def match_jscard(want_card: dict, have_card: dict):
    want_card = copy.deepcopy(want_card)
    have_card = copy.deepcopy(have_card)

    # Remove these props, if not explicitly set
    if not "created" in want_card:
        have_card.pop("created", None)
    if not "updated" in want_card:
        have_card.pop("updated", None)
    if not "prodId" in want_card:
        have_card.pop("prodId", None)
    if not "vCardProps" in want_card:
        have_card.pop("vCardProps", None)

    remove_unknown_vendorprops(want_card, have_card)
    normalize_jscard(want_card)
    normalize_jscard(have_card)

    diffs = []
    diff_objs(want_card, have_card, diffs, [])
    if diffs:
        raise MatchJSCardError(diffs)
