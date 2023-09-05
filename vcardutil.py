import abc
from collections import defaultdict
import copy
import datetime
import json
import pprint
import re

from operator import attrgetter

from dataclasses import dataclass
from typing import Self, List, Tuple


@dataclass
class Param:
    name: str
    value: str

    def __str__(self):
        return f"{self.name}={self.value}"


@dataclass
class Prop:
    group: str
    name: str
    params: list[Param]
    value: str

    @classmethod
    def fromstr(cls, s: str) -> Self:
        # Parse name and group
        group = None
        m = re.match("[A-Za-z0-9-]+", s)
        if not m:
            raise ParseError(s)
        if s[m.end()] == ".":
            group = s[0 : m.end()]
            s = s[m.end() + 1 :]
            m = re.match("[A-Za-z0-9-]+", s)
            if not m:
                raise ParseError(s)
        name = s[0 : m.end()].upper()
        s = s[m.end() :]

        # Parse parameters
        params = []
        while s[0] == ";":
            m = re.match(r';([A-Za-z0-9-]+)=((".*?(?<!\\)")|[^";:]*)', s)
            if not m:
                raise ParseError(s)
            params.append(Param(m.group(1).upper(), m.group(2)))
            s = s[m.end() :]

        # Parse value
        if s[0] != ":":
            raise ParseError(s)
        value = s[1:]
        return Prop(group, name, params, value)

    def __str__(self):
        params = "".join([f";{p}" for p in self.params])
        group = f"{self.group}." if self.group else ""
        return group + f"{self.name}{params}:{self.value}"


def parse(s: str) -> list[Prop]:
    lines = re.sub(r"\r\n[ \t]", "", s).split("\r\n")
    if len(lines) and not len(lines[-1]):
        del lines[-1]
    return [Prop.fromstr(l) for l in lines]


def normalize_vcard(vprops: list[Prop]) -> list[Prop]:
    # Keep original intact
    vprops = copy.deepcopy(vprops)

    # Splice out BEGIN and END
    if len(vprops) > 2 and vprops[0].name == "BEGIN" and vprops[-1].name == "END":
        head, tail = [vprops[0]], [vprops[-1]]
        vprops = vprops[1:-1]
    else:
        head, tail = [], []

    # Sort parameters by name, value
    for prop in vprops:
        prop.params.sort(key=attrgetter("value"))
        prop.params.sort(key=attrgetter("name"))

    # Sort properties by name, value
    vprops.sort(key=attrgetter("value"))
    vprops.sort(key=attrgetter("name"))

    # Splice in BEGIN and END
    return head + vprops + tail


class Value(abc.ABC):
    @abc.abstractmethod
    def match(self, s: str) -> bool:
        pass


class AnyValue(Value):
    def match(self, s: str) -> bool:
        return True

    def __repr__(self):
        return "AnyValue"


@dataclass
class NoCaseValue(Value):
    val: str

    def match(self, val: str) -> bool:
        return self.val.upper() == val.upper()

    def __str__(self):
        return f"NoCaseValue({self.val})"

    def __repr__(self) -> str:
        return self.__str__()


@dataclass
class OneOfValue(Value):
    vals: list[str | Value]

    def match(self, val: str) -> bool:
        for v in self.vals:
            if isinstance(v, Value):
                if v.match(val):
                    return True
            elif v == val:
                return True
        return False


@dataclass
class MaybeQuoted(Value):
    val: str

    def match(self, val: str) -> bool:
        return val in [self.val, f'"{self.val}"']


@dataclass
class MaybeEscaped(Value):
    val: str

    def match(self, val: str) -> bool:
        if self.val == val:
            return True
        return self.val == re.sub(r"\\,", ",", val)


@dataclass
class ComponentsValue(Value):
    comps: list[str | set[str]]

    def match(self, val: str) -> bool:
        subcomps = re.split(r"(?<!\\);", val)
        if len(self.comps) != len(subcomps):
            return False
        for i, want_subcomp in enumerate(self.comps):
            if type(want_subcomp) == str:
                if want_subcomp != subcomps[i]:
                    return False
            elif set(re.split(r"(?<!\\),", subcomps[i])) != self.comps[i]:
                return False
        return True


class TextJSONValue(Value):
    def __init__(self, jval: dict):
        self.val = json.dumps(json.loads(jval))

    def match(self, textval: str) -> bool:
        try:
            val = textval.replace(r"\,", ",").replace(r"\\", "\\")
            jval = json.loads(val)
            return self.val == json.dumps(jval)
        except json.JSONDecodeError:
            return False


class TimestampValue(Value):
    def parse(self, val: str):
        if len(val) == 18:
            val = val + "00"
        elif len(val) > 20:
            raise ValueError
        return datetime.datetime.strptime(val, "%Y%m%dT%H%M%S%z")

    def __init__(self, val: str):
        self.ts = self.parse(val)

    def match(self, val: str) -> bool:
        try:
            r = self.ts == self.parse(val)
            return r
        except ValueError:
            return False

    def __repr__(self):
        return f"Timestamp({self.ts.isoformat()})"


def match_value(want: str | Value, have: str) -> bool:
    if want is AnyValue:
        return True

    if isinstance(want, Value):
        return want.match(have)
    else:
        return want == have


@dataclass
class ParamMatch:
    name: str
    value: str | NoCaseValue = AnyValue
    mandatory: bool = True


@dataclass
class GroupMatch:
    id: str


@dataclass
class AltIdMatch:
    id: str
    mandatory: bool = True


@dataclass
class PropMatch:
    name: str
    value: str | NoCaseValue = AnyValue
    params: list[ParamMatch] = None
    mandatory: bool = True
    alt_id: AltIdMatch | None = None
    group: str | GroupMatch | None = None

    def match(self, prop: Prop, group_by_id: dict, altid_by_id: dict) -> bool:
        if not match_value(self.value, prop.value):
            return False

        # Match parameters, except ALTID
        param_matches_byname = defaultdict(list[ParamMatch])
        if self.params:
            for param_match in self.params:
                param_matches_byname[param_match.name].append(param_match)
        if len(prop.params):
            for param in prop.params:
                if param.name == "ALTID":
                    continue
                param_matches = param_matches_byname.get(param.name)
                if not param_matches:
                    return False
                pos = -1
                for idx, param_match in enumerate(param_matches):
                    if match_value(param_match.value, param.value):
                        pos = idx
                        break
                if pos == -1:
                    return False
                del param_matches[pos]

                if len(param_matches):
                    param_matches_byname[param_match.name] = param_matches
                else:
                    del param_matches_byname[param_match.name]

        for param_matches in param_matches_byname.values():
            for param_match in param_matches:
                if param_match.mandatory:
                    return False

        # Match ALTID
        altid_params = [param for param in prop.params if param.name == "ALTID"]
        if len(altid_params) > 1:
            return False
        if self.alt_id:
            if self.alt_id.mandatory and not altid_params:
                return False
            elif altid_params:
                try:
                    if altid_params[0].value != altid_by_id[self.alt_id.id]:
                        return False
                except KeyError:
                    if altid_params[0].value in altid_by_id.values():
                        return False
                    altid_by_id[self.alt_id.id] = altid_params[0].value

        # Match group
        if self.group:
            if isinstance(self.group, GroupMatch):
                try:
                    if prop.group != group_by_id[self.group.id]:
                        return False
                except KeyError:
                    if prop.group in group_by_id.values():
                        return False
                    group_by_id[self.group.id] = prop.group
            else:
                if prop.group != self.group:
                    return False

        return True


default_matches = [
    PropMatch("PRODID", AnyValue, mandatory=False),
    PropMatch("REV", AnyValue, mandatory=False),
    PropMatch("UID", AnyValue),
    PropMatch("VERSION", "4.0"),
    PropMatch(
        "FN",
        AnyValue(),
        [ParamMatch("DERIVED", NoCaseValue("TRUE"), mandatory=False)],
    ),
    PropMatch(
        "JSPROP",
        '"1.0"',
        [
            ParamMatch("JSPTR", "version"),
            ParamMatch("VALUE", NoCaseValue("TEXT"), mandatory=False),
        ],
        mandatory=False,
    ),
    PropMatch("CREATED", AnyValue, mandatory=False),
]


@dataclass
class PropMatchError:
    prop: Prop
    candidates: list[PropMatch] = None

    @classmethod
    def mismatched(cls, prop: Prop, candidates: list[PropMatch]):
        return PropMatchError(prop, candidates)

    @classmethod
    def unmatched(cls, candidates: list[PropMatch]):
        return PropMatchError(None, candidates)

    @classmethod
    def unexpected(cls, prop: Prop):
        return PropMatchError(prop, None)


class VCardMatchError(Exception):
    def __init__(self, message, errors: list[PropMatchError]):
        super().__init__(message)
        self.match_errors = errors


class ParseError(Exception):
    pass


def match_vcard(
    vcard: str, want_matches: list[PropMatch], default_matches=default_matches
):
    match_errors = []
    props = parse(vcard)
    if len(props) <= 2 or props[0].name != "BEGIN" or props[-1].name != "END":
        raise ValueError("Missing BEGIN or END")
    props = normalize_vcard(props)
    props = props[1:-1]

    matches_by_name = defaultdict(list[PropMatch])
    group_by_id = dict()
    altid_by_id = dict()
    want_name = set()

    for pm in want_matches:
        matches_by_name[pm.name].append(pm)
        want_name.add(pm.name)

    for pm in default_matches:
        if pm.name not in want_name:
            matches_by_name[pm.name].append(pm)

    seen_name = set()
    for prop in props:
        seen_name.add(prop.name)
        matches = matches_by_name.get(prop.name, None)
        if matches is None:
            match_errors.append(PropMatchError.unexpected(prop))
            continue

        pos = -1
        for idx, pm in enumerate(matches):
            if pm.match(prop, group_by_id, altid_by_id):
                pos = idx
                break
        if pos == -1:
            match_errors.append(PropMatchError.mismatched(prop, copy.deepcopy(matches)))
            continue

        del matches[pos]
        if len(matches):
            matches_by_name[pm.name] = matches
        else:
            del matches_by_name[pm.name]

    unmatched_matches = []
    for matches in matches_by_name.values():
        unmatched_matches.extend([pm for pm in matches if pm.mandatory])
    if unmatched_matches:
        match_errors.append(PropMatchError.unmatched(unmatched_matches))

    if match_errors:
        raise VCardMatchError("invalid properties found", match_errors)
