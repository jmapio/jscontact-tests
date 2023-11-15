import copy
from dataclasses import dataclass
from enum import StrEnum, auto
import uuid

import vcardutil
import jscardutil
from backends import InvalidCardError
from jscardutil import *
from vcardutil import *


class Outcome(StrEnum):
    success = auto()
    invalid = auto()
    error = auto()
    skipped = auto()


@dataclass
class Result:
    test_name: str
    sent_jscard: dict
    to_vcard: Outcome = Outcome.skipped
    from_vcard: Outcome = Outcome.skipped
    got_vcard: str = None
    got_error: Exception = None
    got_jscard: dict = None
    want_invalid_props: list[str] = None

    def is_success(self) -> bool:
        return self.to_vcard == Outcome.success and (
            self.from_vcard == Outcome.success or self.from_vcard == Outcome.skipped
        )


@dataclass
class TestCase:
    id: str
    jprops: dict
    matches: list[PropMatch]
    skip_to_vcard: bool = False
    skip_from_vcard: bool = False
    invalid_props: list[str] = None

    def run(self, backend) -> Result:
        jscard = copy.deepcopy(self.jprops)
        if "@type" not in jscard:
            jscard["@type"] = "Card"
        if "uid" not in jscard:
            jscard["uid"] = str(uuid.uuid4())
        if "version" not in jscard:
            jscard["version"] = "1.0"

        result = Result(self.id, jscard)

        if self.skip_to_vcard:
            return result

        try:
            result.got_vcard = backend.to_vcard(jscard)
            if not self.invalid_props:
                vcardutil.match_vcard(result.got_vcard, self.matches)
                result.to_vcard = Outcome.success
            else:
                # We expected an InvalidCardError but got a vCard
                result.to_vcard = Outcome.invalid
                result.want_invalid_props = self.invalid_props
        except VCardMatchError as e:
            result.got_error = e
            result.to_vcard = Outcome.invalid
        except InvalidCardError as e:
            if self.invalid_props:
                result.to_vcard = Outcome.success
            else:
                result.got_error = e
                result.to_vcard = Outcome.error
        except Exception as e:
            result.got_error = e
            result.to_vcard = Outcome.error

        if result.to_vcard != Outcome.success or self.invalid_props:
            return result

        if self.skip_from_vcard:
            result.from_vcard = Outcome.skipped
            return result

        try:
            result.got_jscard = backend.to_jscard(result.got_vcard)
            jscardutil.match_jscard(jscard, result.got_jscard)
            result.from_vcard = Outcome.success
        except MatchJSCardError as e:
            result.got_error = e
            result.from_vcard = Outcome.invalid
        except Exception as e:
            result.got_error = e
            result.from_vcard = Outcome.error

        return result


jscontact_tests: list[TestCase] = [
    TestCase(
        "created",
        {"created": "2022-09-30T14:35:10Z"},
        [
            PropMatch(
                "CREATED",
                "20220930T143510Z",
                [ParamMatch("VALUE", NoCaseValue("timestamp"), mandatory=False)],
            ),
        ],
    ),
    TestCase(
        "kind_group",
        {
            "kind": "group",
            "members": {
                "urn:uuid:03a0e51f-d1aa-4385-8a53-e29025acd8af": True,
            },
        },
        [
            PropMatch("KIND", NoCaseValue("group")),
            PropMatch("MEMBER", "urn:uuid:03a0e51f-d1aa-4385-8a53-e29025acd8af"),
        ],
    ),
    TestCase(
        "language",
        {"language": "de-AT"},
        [
            PropMatch(
                "LANGUAGE",
                "de-AT",
                [ParamMatch("VALUE", NoCaseValue("language-tag"), mandatory=False)],
            ),
        ],
    ),
    TestCase(
        "prodId",
        {"prodId": "ACME Contacts App version 1.23.5"},
        [
            PropMatch("PRODID", "ACME Contacts App version 1.23.5"),
        ],
    ),
    TestCase(
        "relatedTo",
        {
            "relatedTo": {
                "urn:uuid:f81d4fae-7dec-11d0-a765-00a0c91e6bf6": {
                    "relation": {"friend": True}
                },
                "8cacdfb7d1ffdb59@example.com": {"relation": {}},
            }
        },
        [
            PropMatch(
                "RELATED",
                "urn:uuid:f81d4fae-7dec-11d0-a765-00a0c91e6bf6",
                [ParamMatch("TYPE", NoCaseValue("friend"))],
            ),
            PropMatch(
                "RELATED",
                "8cacdfb7d1ffdb59@example.com",
                [ParamMatch("VALUE", NoCaseValue("TEXT"))],
            ),
        ],
    ),
    TestCase(
        "uid_urn",
        {"uid": "urn:uuid:a8325755-a21d-456a-bb8b-8dc75165164c"},
        [
            PropMatch("UID", "urn:uuid:a8325755-a21d-456a-bb8b-8dc75165164c"),
        ],
    ),
    TestCase(
        "uid_uri",
        {"uid": "ldap:///o=University%20of%20Michigan,c=US"},
        [
            PropMatch("UID", MaybeEscaped("ldap:///o=University%20of%20Michigan,c=US")),
        ],
    ),
    TestCase(
        "uid_text",
        {"uid": "hello@example.com"},
        [
            PropMatch(
                "UID",
                "hello@example.com",
                [ParamMatch("VALUE", "TEXT", mandatory=False)],
            ),
        ],
    ),
    TestCase(
        "updated",
        {"updated": "2021-10-31T22:27:10Z"},
        [PropMatch("REV", "20211031T222710Z")],
    ),
    TestCase(
        "name_components",
        {
            "name": {
                "components": [
                    {"kind": "title", "value": "Ms."},
                    {"kind": "given", "value": "Mary Jean"},
                    {"kind": "given2", "value": "Elizabeth"},
                    {"kind": "surname", "value": "van Halen"},
                    {"kind": "surname2", "value": "Barrientos"},
                    {"kind": "generation", "value": "III"},
                    {"kind": "separator", "value": ", "},
                    {"kind": "credential", "value": "PhD"},
                ],
                "isOrdered": True,
            },
        },
        [
            PropMatch(
                "FN",
                OneOfValue(
                    [
                        "Ms. Mary Jean Elizabeth van Halen Barrientos III\\, PhD",
                        "Mary Jean Elizabeth van Halen Barrientos",
                        "Mary Jean Elizabeth van Halen Barrientos III",
                    ]
                ),
                [ParamMatch("DERIVED", NoCaseValue("TRUE"))],
            ),
            PropMatch(
                "N",
                ComponentsValue(
                    [
                        "van Halen,Barrientos",
                        "Mary Jean",
                        "Elizabeth",
                        "Ms.",
                        set(["PhD", "III"]),
                        "Barrientos",
                        "III",
                    ]
                ),
                [
                    ParamMatch(
                        "JSCOMPS",
                        OneOfValue(
                            # TODO that's just stupid having to duplicate JSCOMPS here
                            ['";3;1;2;0;5;6;s,\\, ;4"', '";3;1;2;0;5;6;s,\\, ;4,1"']
                        ),
                    )
                ],
            ),
        ],
    ),
    TestCase(
        "name_localizations",
        {
            "name": {
                "components": [
                    {"kind": "title", "value": "title"},
                    {"kind": "given", "value": "given"},
                    {"kind": "given2", "value": "given2"},
                    {"kind": "surname", "value": "surname"},
                    {"kind": "surname2", "value": "surname2"},
                    {"kind": "credential", "value": "credential"},
                    {"kind": "generation", "value": "generation"},
                ],
            },
            "localizations": {
                "de": {
                    "name/components": [
                        {"kind": "title", "value": "anrede"},
                        {"kind": "given", "value": "vorname"},
                        {"kind": "given2", "value": "vorname2"},
                        {"kind": "surname", "value": "nachname"},
                        {"kind": "surname2", "value": "nachname2"},
                        {"kind": "credential", "value": "titel"},
                        {"kind": "generation", "value": "generation"},
                    ]
                }
            },
        },
        [
            PropMatch(
                "N",
                ComponentsValue(
                    [
                        "surname,surname2",
                        "given",
                        "given2",
                        "title",
                        set(["generation", "credential"]),
                        "surname2",
                        "generation",
                    ]
                ),
                alt_id=AltIdMatch("1"),
            ),
            PropMatch(
                "N",
                ComponentsValue(
                    [
                        "nachname,nachname2",
                        "vorname",
                        "vorname2",
                        "anrede",
                        set(["generation", "titel"]),
                        "nachname2",
                        "generation",
                    ]
                ),
                [ParamMatch("LANGUAGE", "de")],
                alt_id=AltIdMatch("1"),
            ),
            PropMatch(
                "FN",
                AnyValue(),
                [ParamMatch("DERIVED", NoCaseValue("TRUE"), mandatory=False)],
                mandatory=False,
            ),
            PropMatch(
                "FN",
                AnyValue(),
                [
                    ParamMatch("DERIVED", NoCaseValue("TRUE"), mandatory=False),
                    ParamMatch("LANGUAGE", "de"),
                ],
                mandatory=False,
            ),
        ],
    ),
    TestCase(
        "name_fullname_only",
        {
            "name": {"full": "Mr. John Q. Public, Esq."},
        },
        [
            PropMatch("FN", "Mr. John Q. Public\\, Esq."),
        ],
    ),
    TestCase(
        "name_given",
        {
            "name": {
                "components": [
                    {
                        "kind": "given",
                        "value": "Jane",
                    }
                ]
            },
        },
        [
            PropMatch(
                "FN",
                "Jane",
                [ParamMatch("DERIVED", NoCaseValue("TRUE"))],
            ),
            PropMatch("N", OneOfValue([";Jane;;;", ";Jane;;;;;"])),
        ],
    ),
    TestCase(
        "name_surname",
        {
            "name": {
                "components": [
                    {
                        "kind": "given",
                        "value": "Jane",
                    },
                    {"kind": "surname", "value": "Doe"},
                ]
            },
        },
        [
            PropMatch(
                "FN",
                AnyValue(),
                [ParamMatch("DERIVED", NoCaseValue("TRUE"))],
            ),
            PropMatch("N", OneOfValue(["Doe;Jane;;;", "Doe;Jane;;;;;"])),
        ],
    ),
    TestCase(
        "name_surname_whitespace",
        {
            "name": {
                "components": [
                    {
                        "kind": "given",
                        "value": "Vincent",
                    },
                    {"kind": "surname", "value": "van Gogh"},
                ],
                "isOrdered": True,
            },
        },
        [
            PropMatch(
                "N",
                OneOfValue(["van Gogh;Vincent;;;", "van Gogh;Vincent;;;;;"]),
                [ParamMatch("JSCOMPS", '";1;0"')],
            ),
        ],
    ),
    TestCase(
        "name_surname2",
        {
            "name": {
                "components": [
                    {
                        "kind": "given",
                        "value": "Diego",
                    },
                    {"kind": "surname", "value": "Rivera"},
                    {"kind": "surname2", "value": "Barrientos"},
                ],
                "isOrdered": True,
            },
        },
        [
            PropMatch(
                "FN",
                "Diego Rivera Barrientos",
                [ParamMatch("DERIVED", NoCaseValue("TRUE"))],
            ),
            PropMatch(
                "N",
                "Rivera,Barrientos;Diego;;;;Barrientos;",
                [ParamMatch("JSCOMPS", '";1;0;5"')],
            ),
        ],
    ),
    TestCase(
        "name_defaultSeparator",
        {
            "name": {
                "defaultSeparator": "X",
                "components": [
                    {
                        "kind": "given",
                        "value": "Jane",
                    },
                    {
                        "kind": "surname",
                        "value": "Doe",
                    },
                ],
                "isOrdered": True,
            },
        },
        [
            PropMatch(
                "FN",
                "JaneXDoe",
                [ParamMatch("DERIVED", NoCaseValue("TRUE"))],
            ),
            PropMatch(
                "N",
                OneOfValue(["Doe;Jane;;;", "Doe;Jane;;;;;"]),
                [ParamMatch("JSCOMPS", '"s,X;1;0"')],
            ),
        ],
    ),
    TestCase(
        "name_phonetic",
        {
            "name": {
                "components": [
                    {
                        "kind": "given",
                        "value": "John",
                        "phonetic": "/d͡ʒɑn/",
                    },
                    {
                        "kind": "surname",
                        "value": "Smith",
                        "phonetic": "/smɪθ/",
                    },
                ],
                "phoneticSystem": "ipa",
            }
        },
        [
            PropMatch("N", "Smith;John;;;;;", alt_id=AltIdMatch("1")),
            PropMatch(
                "N",
                "/smɪθ/;/d͡ʒɑn/;;;;;",
                [ParamMatch("PHONETIC", NoCaseValue("ipa"))],
                alt_id=AltIdMatch("1"),
            ),
            PropMatch(
                "FN",
                OneOfValue(["John Smith", "Smith John"]),
                [ParamMatch("DERIVED", NoCaseValue("TRUE"), mandatory=False)],
                mandatory=False,
            ),
        ],
    ),
    TestCase(
        "name_phonetic_ordered",
        {
            "name": {
                "components": [
                    {
                        "kind": "given",
                        "value": "John",
                        "phonetic": "/d͡ʒɑn/",
                    },
                    {
                        "kind": "surname",
                        "value": "Smith",
                        "phonetic": "/smɪθ/",
                    },
                ],
                "phoneticSystem": "ipa",
                "isOrdered": True,
            }
        },
        [
            PropMatch(
                "N",
                "Smith;John;;;;;",
                [
                    ParamMatch("JSCOMPS", '";1;0"'),
                ],
                alt_id=AltIdMatch("1"),
            ),
            PropMatch(
                "N",
                "/smɪθ/;/d͡ʒɑn/;;;;;",
                [
                    ParamMatch("PHONETIC", NoCaseValue("ipa")),
                    ParamMatch("JSCOMPS", '";1;0"', mandatory=False),
                ],
                alt_id=AltIdMatch("1"),
            ),
            PropMatch(
                "FN",
                OneOfValue(["John Smith", "Smith John"]),
                [ParamMatch("DERIVED", NoCaseValue("TRUE"), mandatory=False)],
                mandatory=False,
            ),
        ],
    ),
    TestCase(
        "name_sortAs",
        {
            "name": {
                "components": [
                    {"kind": "given", "value": "Robert"},
                    {"kind": "given2", "value": "Pau"},
                    {"kind": "surname", "value": "Shou Chang"},
                ],
                "sortAs": {"surname": "Pau Shou Chang", "given": "Robert"},
            }
        },
        [
            PropMatch(
                "N",
                OneOfValue(["Shou Chang;Robert;Pau;;", "Shou Chang;Robert;Pau;;;;"]),
                [ParamMatch("SORT-AS", MaybeQuoted("Pau Shou Chang,Robert"))],
            ),
        ],
    ),
    TestCase(
        "nicknames",
        {
            "nicknames": {
                "n1": {"name": "Johnny"},
                "n2": {"name": "The John", "contexts": {"work": True}},
            }
        },
        [
            PropMatch("NICKNAME", "Johnny", [ParamMatch("PROP-ID", "n1")]),
            PropMatch(
                "NICKNAME",
                "The John",
                [ParamMatch("PROP-ID", "n2"), ParamMatch("TYPE", NoCaseValue("work"))],
            ),
        ],
    ),
    TestCase(
        "organizations",
        {
            "organizations": {
                "o1": {
                    "name": "ABC, Inc.",
                    "units": [
                        {"name": "North American Division"},
                        {"name": "Marketing"},
                    ],
                    "sortAs": "ABC",
                }
            }
        },
        [
            PropMatch(
                "ORG",
                "ABC\\, Inc.;North American Division;Marketing",
                [
                    ParamMatch("SORT-AS", MaybeQuoted("ABC")),
                    ParamMatch("PROP-ID", "o1"),
                ],
            )
        ],
    ),
    TestCase(
        "speakToAs",
        {
            "speakToAs": {
                "grammaticalGender": "neuter",
                "pronouns": {
                    "k19": {"pronouns": "they/them", "pref": 2},
                    "k32": {"pronouns": "xe/xir", "pref": 1},
                },
            }
        },
        [
            PropMatch(
                "GRAMGENDER",
                NoCaseValue("neuter"),
                [
                    ParamMatch("VALUE", NoCaseValue("TEXT"), mandatory=False),
                ],
            ),
            PropMatch(
                "PRONOUNS",
                "they/them",
                [
                    ParamMatch("PROP-ID", "k19"),
                    ParamMatch("PREF", "2"),
                    ParamMatch("VALUE", NoCaseValue("TEXT"), mandatory=False),
                ],
            ),
            PropMatch(
                "PRONOUNS",
                "xe/xir",
                [
                    ParamMatch("PROP-ID", "k32"),
                    ParamMatch("PREF", "1"),
                    ParamMatch("VALUE", NoCaseValue("TEXT"), mandatory=False),
                ],
            ),
        ],
    ),
    TestCase(
        "titles",
        {
            "titles": {
                "le9": {"kind": "title", "name": "Research Scientist"},
                "k2": {"kind": "role", "name": "Project Leader", "organizationId": "o2"},
            },
            "organizations": {"o2": {"name": "ABC"}},
        },
        [
            PropMatch("TITLE", "Research Scientist", [ParamMatch("PROP-ID", "le9")]),
            PropMatch(
                "ROLE",
                "Project Leader",
                [ParamMatch("PROP-ID", "k2")],
                group=GroupMatch("group1"),
            ),
            PropMatch(
                "ORG", "ABC", [ParamMatch("PROP-ID", "o2")], group=GroupMatch("group1")
            ),
        ],
    ),
    TestCase(
        "emails",
        {
            "emails": {
                "e1": {
                    "contexts": {"work": True},
                    "address": "jqpublic@xyz.example.com",
                },
                "e2": {"address": "jane_doe@example.com", "pref": 1},
            }
        },
        [
            PropMatch(
                "EMAIL",
                "jqpublic@xyz.example.com",
                [ParamMatch("PROP-ID", "e1"), ParamMatch("TYPE", NoCaseValue("work"))],
            ),
            PropMatch(
                "EMAIL",
                "jane_doe@example.com",
                [ParamMatch("PROP-ID", "e2"), ParamMatch("PREF", "1")],
            ),
        ],
    ),
    TestCase(
        "onlineServices",
        {
            "onlineServices": {
                "x1": {"uri": "xmpp:alice@example.com", "vCardName": "impp"},
                "x2": {
                    "service": "Mastodon",
                    "user": "@alice@example2.com",
                    "uri": "https://example2.com/@alice",
                    "label": "foo",
                },
            }
        },
        [
            PropMatch("IMPP", "xmpp:alice@example.com", [ParamMatch("PROP-ID", "x1")]),
            PropMatch(
                "SOCIALPROFILE",
                "https://example2.com/@alice",
                [
                    ParamMatch("PROP-ID", "x2"),
                    ParamMatch("USERNAME", "@alice@example2.com"),
                    ParamMatch("SERVICE-TYPE", "Mastodon"),
                    ParamMatch("VALUE", NoCaseValue("URI"), mandatory=False),
                ],
                group=GroupMatch("group1"),
            ),
            PropMatch(
                "X-ABLABEL",
                "foo",
                [ParamMatch("VALUE", NoCaseValue("TEXT"), mandatory=False)],
                group=GroupMatch("group1"),
            ),
        ],
    ),
    TestCase(
        "phones",
        {
            "phones": {
                "tel0": {
                    "contexts": {"private": True},
                    "features": {"voice": True},
                    "number": "tel:+1-555-555-5555;ext=5555",
                    "pref": 1,
                },
                "tel3": {
                    "contexts": {"work": True},
                    "number": "tel:+1-201-555-0123",
                },
            }
        },
        [
            PropMatch(
                "TEL",
                "tel:+1-555-555-5555;ext=5555",
                [
                    ParamMatch(
                        "TYPE",
                        OneOfValue(
                            [
                                NoCaseValue("HOME,VOICE"),
                                NoCaseValue("VOICE,HOME"),
                            ],
                        ),
                    ),
                    ParamMatch("VALUE", NoCaseValue("URI")),
                    ParamMatch("PREF", "1"),
                    ParamMatch("PROP-ID", "tel0"),
                ],
            ),
            PropMatch(
                "TEL",
                "tel:+1-201-555-0123",
                [
                    ParamMatch("VALUE", NoCaseValue("URI")),
                    ParamMatch("TYPE", NoCaseValue("WORK")),
                    ParamMatch("PROP-ID", "tel3"),
                ],
            ),
        ],
    ),
    TestCase(
        "preferredLanguages",
        {
            "preferredLanguages": {
                "l1": {"language": "en", "contexts": {"work": True}, "pref": 1},
                "l2": {"language": "fr", "contexts": {"work": True}, "pref": 2},
                "l3": {"language": "fr", "contexts": {"private": True}},
            }
        },
        [
            PropMatch(
                "LANG",
                "en",
                [
                    ParamMatch("PROP-ID", "l1"),
                    ParamMatch("TYPE", NoCaseValue("WORK")),
                    ParamMatch("PREF", "1"),
                ],
            ),
            PropMatch(
                "LANG",
                "fr",
                [
                    ParamMatch("PROP-ID", "l2"),
                    ParamMatch("TYPE", NoCaseValue("WORK")),
                    ParamMatch("PREF", "2"),
                ],
            ),
            PropMatch(
                "LANG",
                "fr",
                [
                    ParamMatch("PROP-ID", "l3"),
                    ParamMatch("TYPE", NoCaseValue("HOME")),
                ],
            ),
        ],
    ),
    TestCase(
        "calendars",
        {
            "calendars": {
                "calA": {
                    "kind": "calendar",
                    "uri": "webcal://calendar.example.com/calA.ics",
                },
                "project-a": {
                    "kind": "freeBusy",
                    "uri": "https://calendar.example.com/busy/project-a",
                },
            },
        },
        [
            PropMatch(
                "CALURI",
                "webcal://calendar.example.com/calA.ics",
                [ParamMatch("PROP-ID", "calA")],
            ),
            PropMatch(
                "FBURL",
                "https://calendar.example.com/busy/project-a",
                [ParamMatch("PROP-ID", "project-a")],
            ),
        ],
    ),
    TestCase(
        "schedulingAddresses",
        {"schedulingAddresses": {"sched1": {"uri": "mailto:janedoe@example.com"}}},
        [
            PropMatch(
                "CALADRURI",
                "mailto:janedoe@example.com",
                [
                    ParamMatch("PROP-ID", "sched1"),
                ],
            ),
        ],
    ),
    TestCase(
        "schedulingAddresses_label",
        {
            "schedulingAddresses": {
                "sched1": {
                    "uri": "mailto:janedoe@example.com",
                    "label": "bar",
                    "contexts": {"work": True},
                    "pref": 3,
                }
            }
        },
        [
            PropMatch(
                "CALADRURI",
                "mailto:janedoe@example.com",
                [
                    ParamMatch("PROP-ID", "sched1"),
                    ParamMatch("TYPE", NoCaseValue("WORK")),
                    ParamMatch("PREF", "3"),
                ],
                group=GroupMatch("group1"),
            ),
            PropMatch(
                "X-ABLABEL",
                "bar",
                [ParamMatch("VALUE", NoCaseValue("text"), mandatory=False)],
                group=GroupMatch("group1"),
            ),
        ],
    ),
    TestCase(
        "addresses_components",
        {
            "addresses": {
                "a1": {
                    "components": [
                        {"kind": "apartment", "value": "apartment-val"},
                        {"kind": "block", "value": "block-val"},
                        {"kind": "building", "value": "building-val"},
                        {"kind": "country", "value": "country-val"},
                        {"kind": "direction", "value": "direction-val"},
                        {"kind": "district", "value": "district-val"},
                        {"kind": "floor", "value": "floor-val"},
                        {"kind": "landmark", "value": "landmark-val"},
                        {"kind": "locality", "value": "locality-val"},
                        {"kind": "name", "value": "name-val"},
                        {"kind": "number", "value": "number-val"},
                        {"kind": "postcode", "value": "postcode-val"},
                        {"kind": "postOfficeBox", "value": "postOfficeBox-val"},
                        {"kind": "region", "value": "region-val"},
                        {"kind": "room", "value": "room-val"},
                        {"kind": "subdistrict", "value": "subdistrict-val"},
                    ]
                }
            },
        },
        [
            PropMatch(
                "ADR",
                ComponentsValue(
                    [
                        "postOfficeBox-val",
                        set(
                            [
                                "room-val",
                                "floor-val",
                                "apartment-val",
                                "building-val",
                            ]
                        ),
                        set(
                            [
                                "number-val",
                                "name-val",
                                "block-val",
                                "direction-val",
                                "landmark-val",
                                "subdistrict-val",
                                "district-val",
                            ]
                        ),
                        "locality-val",
                        "region-val",
                        "postcode-val",
                        "country-val",
                        "room-val",
                        "apartment-val",
                        "floor-val",
                        "number-val",
                        "name-val",
                        "building-val",
                        "block-val",
                        "subdistrict-val",
                        "district-val",
                        "landmark-val",
                        "direction-val",
                    ]
                ),
                [
                    ParamMatch("PROP-ID", "a1"),
                    ParamMatch("LABEL", AnyValue(), mandatory=False),
                ],
            )
        ],
    ),
    TestCase(
        "addresses_localizations",
        {
            "addresses": {
                "k26": {
                    "components": [
                        {"kind": "block", "value": "2-7"},
                        {"kind": "separator", "value": "-"},
                        {"kind": "number", "value": "2"},
                        {"kind": "separator", "value": " "},
                        {"kind": "district", "value": "Marunouchi"},
                        {"kind": "locality", "value": "Chiyoda-ku"},
                        {"kind": "region", "value": "Tokyo"},
                        {"kind": "separator", "value": " "},
                        {"kind": "postcode", "value": "100-8994"},
                    ],
                    "defaultSeparator": ", ",
                    "full": "2-7-2 Marunouchi, Chiyoda-ku, Tokyo 100-8994",
                    "isOrdered": True,
                }
            },
            "localizations": {
                "jp": {
                    "addresses/k26": {
                        "components": [
                            {"kind": "region", "value": "東京都"},
                            {"kind": "locality", "value": "千代田区"},
                            {"kind": "district", "value": "丸ノ内"},
                            {"kind": "block", "value": "2-7"},
                            {"kind": "separator", "value": "-"},
                            {"kind": "number", "value": "2"},
                            {"kind": "postcode", "value": "〒100-8994"},
                        ],
                        "defaultSeparator": "",
                        "full": "〒100-8994東京都千代田区丸ノ内2-7-2",
                        "isOrdered": True,
                    }
                }
            },
        },
        [
            PropMatch(
                "ADR",
                ComponentsValue(
                    [
                        "",  # pobox
                        "",  # extadr
                        set(["2-7", "2", "Marunouchi"]),  # street
                        "Chiyoda-ku",  # locality
                        "Tokyo",  # region
                        "100-8994",  # postal code
                        "",  # country
                        "",  # room
                        "",  # apartment
                        "",  # floor
                        "2",  # street number
                        "",  # street name
                        "",  # building
                        "2-7",  # block
                        "",  # subdistrict
                        "Marunouchi",  # distrcit
                        "",  # landmark
                        "",  # cardinal direction
                    ]
                ),
                [
                    ParamMatch(
                        "LABEL",
                        MaybeQuoted("2-7-2 Marunouchi, Chiyoda-ku, Tokyo 100-8994"),
                    ),
                    ParamMatch("JSCOMPS", '"s,\\, ;13;s,-;10;s, ;15;3;4;s, ;5"'),
                    ParamMatch("PROP-ID", "k26"),
                ],
                alt_id=AltIdMatch("1", mandatory=False),
            ),
            PropMatch(
                "ADR",
                ComponentsValue(
                    [
                        "",  # pobox
                        "",  # extadr
                        set(["2-7", "2", "丸ノ内"]),  # street
                        "千代田区",  # locality
                        "東京都",  # region
                        "〒100-8994",  # postal code
                        "",  # country
                        "",  # room
                        "",  # apartment
                        "",  # floor
                        "2",  # street number
                        "",  # street name
                        "",  # building
                        "2-7",  # block
                        "",  # subdistrict
                        "丸ノ内",  # distrcit
                        "",  # landmark
                        "",  # cardinal direction
                    ]
                ),
                [
                    ParamMatch(
                        "LABEL",
                        MaybeQuoted("〒100-8994東京都千代田区丸ノ内2-7-2"),
                    ),
                    ParamMatch("JSCOMPS", '"s,;4;3;15;13;s,-;10;5"'),
                    ParamMatch("LANGUAGE", "jp"),
                    ParamMatch("PROP-ID", "k26"),
                ],
                alt_id=AltIdMatch("1", mandatory=False),
            ),
        ],
    ),
    TestCase(
        "addresses_defaultseparator_rfc6868",
        {
            "addresses": {
                "a1": {
                    "components": [
                        {"kind": "name", "value": "name"},
                        {"kind": "region", "value": "region"},
                    ],
                    "defaultSeparator": "\nx^y\"z",
                    "isOrdered": True,
                }
            },
        },
        [
            PropMatch(
                "ADR",
                ComponentsValue(
                    [
                        "",  # pobox
                        "",  # extadr
                        "name",  # street
                        "",  # locality
                        "region",  # region
                        "",  # postal code
                        "",  # country
                        "",  # room
                        "",  # apartment
                        "",  # floor
                        "",  # street number
                        "name",  # street name
                        "",  # building
                        "",  # block
                        "",  # subdistrict
                        "",  # distrcit
                        "",  # landmark
                        "",  # cardinal direction
                    ]
                ),
                [
                    ParamMatch("JSCOMPS", '"' + "s,^nx^^y^'z;11;4" + '"'),
                    ParamMatch("PROP-ID", "a1"),
                    ParamMatch("LABEL", "name^nx^^y^'zregion", mandatory=False),
                ],
                alt_id=AltIdMatch("1", mandatory=False),
            ),
        ],
    ),
    TestCase(
        "cryptoKeys",
        {
            "cryptoKeys": {
                "mykey1": {"uri": "https://www.example.com/keys/jdoe.cer"},
                "mykey2": {"uri": "https://example.com/bar.key"},
            }
        },
        [
            PropMatch(
                "KEY",
                "https://www.example.com/keys/jdoe.cer",
                [
                    ParamMatch("PROP-ID", "mykey1"),
                    ParamMatch("VALUE", NoCaseValue("URI"), mandatory=False),
                ],
            ),
            PropMatch(
                "KEY",
                "https://example.com/bar.key",
                [
                    ParamMatch("PROP-ID", "mykey2"),
                    ParamMatch("VALUE", NoCaseValue("URI"), mandatory=False),
                ],
            ),
        ],
    ),
    TestCase(
        "cryptoKeys_datauri",
        {
            "cryptoKeys": {
                "mykey2": {
                    "uri": "data:application/pgp-keys;base64,LS0tLS1CRUdJTiBSU0EgUFVCTElDIEtFWS0tLS0tCk"
                    + "1JSUJDZ0tDQVFFQSt4R1ovd2N6OXVnRnBQMDdOc3BvNlUxN2wwWWhGaUZweHhVNHBUazNMaWZ6OVIzen"
                    + "NJc3UKRVJ3dGE3K2ZXSWZ4T28yMDhldHQvamhza2lWb2RTRXQzUUJHaDRYQmlweVdvcEt3WjkzSEhhRF"
                    + "ZaQUFMaS8yQQoreFRCdFdkRW83WEdVdWpLRHZDMi9hWkt1a2ZqcE9pVUk4QWhMQWZqbWxjRC9VWjFRUG"
                    + "gwbUhzZ2xSTkNtcEN3Cm13U1hBOVZObWh6K1BpQitEbWw0V1duS1cvVkhvMnVqVFh4cTcrZWZNVTRIMm"
                    + "ZueTNTZTNLWU9zRlBGR1oxVE4KUVNZbEZ1U2hXckhQdGlMbVVkUG9QNkNWMm1NTDF0aytsN0RJSXFYcl"
                    + "FoTFVLREFDZU01cm9NeDBrTGhVV0I4UAorMHVqMUNObE5ONEpSWmxDN3hGZnFpTWJGUlU5WjRONll3SU"
                    + "RBUUFCCi0tLS0tRU5EIFJTQSBQVUJMSUMgS0VZLS0tLS0K"
                },
            }
        },
        [
            PropMatch(
                "KEY",
                MaybeEscaped(
                    "data:application/pgp-keys;base64,LS0tLS1CRUdJTiBSU0EgUFVCTElDIEtFWS0tLS0tCk"
                    + "1JSUJDZ0tDQVFFQSt4R1ovd2N6OXVnRnBQMDdOc3BvNlUxN2wwWWhGaUZweHhVNHBUazNMaWZ6OVIzen"
                    + "NJc3UKRVJ3dGE3K2ZXSWZ4T28yMDhldHQvamhza2lWb2RTRXQzUUJHaDRYQmlweVdvcEt3WjkzSEhhRF"
                    + "ZaQUFMaS8yQQoreFRCdFdkRW83WEdVdWpLRHZDMi9hWkt1a2ZqcE9pVUk4QWhMQWZqbWxjRC9VWjFRUG"
                    + "gwbUhzZ2xSTkNtcEN3Cm13U1hBOVZObWh6K1BpQitEbWw0V1duS1cvVkhvMnVqVFh4cTcrZWZNVTRIMm"
                    + "ZueTNTZTNLWU9zRlBGR1oxVE4KUVNZbEZ1U2hXckhQdGlMbVVkUG9QNkNWMm1NTDF0aytsN0RJSXFYcl"
                    + "FoTFVLREFDZU01cm9NeDBrTGhVV0I4UAorMHVqMUNObE5ONEpSWmxDN3hGZnFpTWJGUlU5WjRONll3SU"
                    + "RBUUFCCi0tLS0tRU5EIFJTQSBQVUJMSUMgS0VZLS0tLS0K"
                ),
                [
                    ParamMatch("PROP-ID", "mykey2"),
                    ParamMatch("VALUE", NoCaseValue("URI"), mandatory=False),
                ],
            ),
        ],
    ),
    TestCase(
        "directories",
        {
            "directories": {
                "dir1": {
                    "kind": "entry",
                    "uri": "https://dir.example.com/addrbook/jdoe/Jean%20Dupont.vcf",
                },
                "dir2": {
                    "kind": "directory",
                    "uri": "ldap://ldap.example/o=Example%20Tech,ou=Engineering",
                    "pref": 1,
                },
            }
        },
        [
            PropMatch(
                "SOURCE",
                "https://dir.example.com/addrbook/jdoe/Jean%20Dupont.vcf",
                [
                    ParamMatch("PROP-ID", "dir1"),
                    ParamMatch("VALUE", NoCaseValue("URI"), mandatory=False),
                ],
            ),
            PropMatch(
                "ORG-DIRECTORY",
                MaybeEscaped("ldap://ldap.example/o=Example%20Tech,ou=Engineering"),
                [
                    ParamMatch("PROP-ID", "dir2"),
                    ParamMatch("PREF", "1"),
                    ParamMatch("VALUE", NoCaseValue("URI"), mandatory=False),
                ],
            ),
        ],
    ),
    TestCase(
        "links",
        {
            "links": {
                "link1": {
                    "uri": "https://example.com",
                },
                "link3": {
                    "kind": "contact",
                    "uri": "mailto:contact@example.com",
                    "pref": 1,
                },
            }
        },
        [
            PropMatch("URL", "https://example.com", [ParamMatch("PROP-ID", "link1")]),
            PropMatch(
                "CONTACT-URI",
                "mailto:contact@example.com",
                [ParamMatch("PROP-ID", "link3"), ParamMatch("PREF", "1")],
            ),
        ],
    ),
    TestCase(
        "media",
        {
            "media": {
                "res45": {
                    "kind": "sound",
                    "uri": "CID:JOHNQ.part8.19960229T080000.xyzMail@example.com",
                },
                "res47": {
                    "kind": "logo",
                    "uri": "https://www.example.com/pub/logos/abccorp.jpg",
                },
                "res1": {
                    "kind": "photo",
                    "uri": "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAASABIAAD/",
                },
            }
        },
        [
            PropMatch(
                "SOUND",
                "CID:JOHNQ.part8.19960229T080000.xyzMail@example.com",
                [ParamMatch("PROP-ID", "res45")],
            ),
            PropMatch(
                "LOGO",
                "https://www.example.com/pub/logos/abccorp.jpg",
                [ParamMatch("PROP-ID", "res47")],
            ),
            PropMatch(
                "PHOTO",
                MaybeEscaped("data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAASABIAAD/"),
                [ParamMatch("PROP-ID", "res1")],
            ),
        ],
    ),
    TestCase(
        "localizations_overwrite",
        {
            "name": {
                "components": [
                    {"kind": "title", "value": "Mr."},
                    {"kind": "given", "value": "Ivan"},
                    {"kind": "given2", "value": "Petrovich"},
                    {"kind": "surname", "value": "Vasiliev"},
                ]
            },
            "localizations": {
                "uk-Cyrl": {
                    "name": {
                        "components": [
                            {"kind": "title", "value": "г-н"},
                            {"kind": "given", "value": "Иван"},
                            {"kind": "given2", "value": "Петрович"},
                            {"kind": "surname", "value": "Васильев"},
                        ]
                    }
                }
            },
        },
        [
            PropMatch("N", "Vasiliev;Ivan;Petrovich;Mr.;;;", alt_id=AltIdMatch("1")),
            PropMatch(
                "N",
                "Васильев;Иван;Петрович;г-н;;;",
                [ParamMatch("LANGUAGE", "uk-Cyrl")],
                alt_id=AltIdMatch("1"),
            ),
            PropMatch(
                "FN",
                AnyValue(),
                [
                    ParamMatch("DERIVED", NoCaseValue("TRUE")),
                ],
                alt_id=AltIdMatch("1", mandatory=False),
                mandatory=False,
            ),
            PropMatch(
                "FN",
                AnyValue(),
                [
                    ParamMatch("DERIVED", NoCaseValue("TRUE")),
                    ParamMatch("LANGUAGE", MaybeQuoted("uk-Cyrl")),
                ],
                alt_id=AltIdMatch("1", mandatory=False),
                mandatory=False,
            ),
        ],
    ),
    TestCase(
        "localizations_patch",
        {
            "name": {"full": "Gabriel García Márquez"},
            "titles": {"t1": {"kind": "title", "name": "novelist"}},
            "localizations": {"es": {"titles/t1/name": "autor"}},
        },
        [
            PropMatch(
                "FN",
                "Gabriel García Márquez",
                [ParamMatch("VALUE", NoCaseValue("text"), mandatory=False)],
            ),
            PropMatch(
                "TITLE",
                "novelist",
                [
                    ParamMatch("PROP-ID", "t1"),
                    ParamMatch("VALUE", NoCaseValue("text"), mandatory=False),
                ],
                alt_id=AltIdMatch("1"),
            ),
            PropMatch(
                "TITLE",
                "autor",
                [
                    ParamMatch("PROP-ID", "t1"),
                    ParamMatch("LANGUAGE", "es"),
                    ParamMatch("VALUE", NoCaseValue("text"), mandatory=False),
                ],
                alt_id=AltIdMatch("1"),
            ),
        ],
    ),
    TestCase(
        "anniversaries",
        {
            "anniversaries": {
                "k8": {"kind": "birth", "date": {"year": 1953, "month": 4, "day": 15}},
                "k9": {
                    "kind": "death",
                    "date": {"@type": "Timestamp", "utc": "2019-10-15T23:10:00Z"},
                    "place": {"full": "4445 Tree Street\nNew England, ND 58647\nUSA"},
                },
            }
        },
        [
            PropMatch(
                "BDAY",
                "19530415",
                [
                    ParamMatch("PROP-ID", "k8"),
                    ParamMatch("VALUE", NoCaseValue("date"), mandatory=False),
                ],
            ),
            PropMatch(
                "DEATHDATE",
                TimestampValue("20191015T231000Z"),
                [
                    ParamMatch("PROP-ID", "k9"),
                    ParamMatch("VALUE", NoCaseValue("timestamp"), mandatory=False),
                ],
            ),
            PropMatch(
                "DEATHPLACE",
                "4445 Tree Street\\nNew England\\, ND 58647\\nUSA",
                [
                    ParamMatch("PROP-ID", "k9"),
                    ParamMatch("VALUE", NoCaseValue("text"), mandatory=False),
                ],
            ),
        ],
    ),
    TestCase(
        "keywords",
        {"keywords": {"internet": True, "IETF": True}},
        [PropMatch("CATEGORIES", ComponentsValue([set(["internet", "IETF"])]))],
    ),
    TestCase(
        "notes",
        {
            "notes": {
                "n1": {
                    "note": "Open office hours are 1600 to 1715 EST, Mon-Fri",
                    "created": "2022-11-23T15:01:32Z",
                    "author": {"name": "John"},
                }
            }
        },
        [
            PropMatch(
                "NOTE",
                "Open office hours are 1600 to 1715 EST\\, Mon-Fri",
                [
                    ParamMatch("PROP-ID", "n1"),
                    ParamMatch("CREATED", "20221123T150132Z"),
                    ParamMatch("AUTHOR-NAME", "John"),
                    ParamMatch("VALUE", NoCaseValue("text"), mandatory=False),
                ],
            )
        ],
    ),
    TestCase(
        "personalInfo",
        {
            "personalInfo": {
                "pi2": {"kind": "expertise", "value": "chemistry", "level": "high"},
                "pi1": {"kind": "hobby", "value": "reading", "level": "high"},
                "pi6": {"kind": "interest", "value": "r&b music", "level": "medium"},
            }
        },
        [
            PropMatch(
                "EXPERTISE",
                "chemistry",
                [
                    ParamMatch("PROP-ID", NoCaseValue("pi2")),
                    ParamMatch("LEVEL", NoCaseValue("expert")),
                    ParamMatch("VALUE", NoCaseValue("text"), mandatory=False),
                ],
            ),
            PropMatch(
                "HOBBY",
                "reading",
                [
                    ParamMatch("PROP-ID", NoCaseValue("pi1")),
                    ParamMatch("LEVEL", NoCaseValue("high")),
                    ParamMatch("VALUE", NoCaseValue("text"), mandatory=False),
                ],
            ),
            PropMatch(
                "INTEREST",
                "r&b music",
                [
                    ParamMatch("PROP-ID", NoCaseValue("pi6")),
                    ParamMatch("LEVEL", NoCaseValue("medium")),
                    ParamMatch("VALUE", NoCaseValue("text"), mandatory=False),
                ],
            ),
        ],
    ),
    TestCase(
        "vCardProps",
        {"vCardProps": [["x-foo", {"group": "item2", "pref": 1}, "unknown", "bar"]]},
        [
            PropMatch(
                "X-FOO",
                "bar",
                [ParamMatch("PREF", "1")],
                group="item2",
            )
        ],
    ),
    TestCase(
        "vCardParams",
        {
            "emails": {
                "e1": {
                    "address": "jqpublic@xyz.example.com",
                    "vCardParams": {"x-foo": "bar"},
                },
            }
        },
        [
            PropMatch(
                "EMAIL",
                "jqpublic@xyz.example.com",
                [ParamMatch("PROP-ID", "e1"), ParamMatch("X-FOO", "bar")],
            ),
        ],
    ),
    TestCase(
        "vCardProps_iana",
        {
            "name": {"full": "Jane Doe"},
            "vCardProps": [["photo", {}, "uri", "https://example.com/hello.jpg"]],
        },
        [
            PropMatch(
                "FN",
                "Jane Doe",
                [ParamMatch("VALUE", NoCaseValue("text"), mandatory=False)],
            ),
            PropMatch(
                "PHOTO",
                "https://example.com/hello.jpg",
                [ParamMatch("VALUE", NoCaseValue("URI"), mandatory=False)],
            ),
        ],
        skip_from_vcard=True,
    ),
    TestCase(
        "vendorSpecific",
        {
            "example.com:foo": "bar",
            "name": {"full": "Jane Doe", "example.com:foo2": {"bar": "baz"}},
        },
        [
            PropMatch(
                "JSPROP",
                TextJSONValue('"bar"'),
                [
                    ParamMatch("JSPTR", '"example.com:foo"'),
                    ParamMatch("VALUE", NoCaseValue("text"), mandatory=False),
                ],
            ),
            PropMatch(
                "JSPROP",
                TextJSONValue('{"bar": "baz"}'),
                [
                    ParamMatch("JSPTR", '"name/example.com:foo2"'),
                    ParamMatch("VALUE", NoCaseValue("text"), mandatory=False),
                ],
            ),
            PropMatch(
                "FN",
                "Jane Doe",
                [ParamMatch("VALUE", NoCaseValue("text"), mandatory=False)],
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
        ],
    ),
    TestCase(
        "unknownProp",
        {
            "foo": "bar",
        },
        [
            PropMatch(
                "JSPROP",
                TextJSONValue('"bar"'),
                [
                    ParamMatch("JSPTR", MaybeQuoted("foo")),
                    ParamMatch("VALUE", NoCaseValue("text"), mandatory=False),
                ],
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
        ],
    ),
    TestCase(
        "wrongCaseProp",
        {
            "nickNames": {
                "n1": {"name": "Johnny"},
                "n2": {"name": "The John", "contexts": {"work": True}},
            }
        },
        None,
        invalid_props=["nickNames"],
    ),
    TestCase(
        "wrongCaseProp2",
        {
            "name": {"full": "Jane", "Full": "Jane"},
        },
        None,
        invalid_props=["name/Full"],
    ),
    TestCase(
        "extra",
        {"name": {"full": "Jane"}, "extra": "reserved"},
        None,
        invalid_props=["extra"],
    ),
    TestCase(
        "extra_nested",
        {"name": {"full": "Jane", "extra": "reserved"}},
        None,
        invalid_props=["name/extra"],
    ),
    TestCase(
        "extra_patched",
        {"name": {"full": "Jane"}, "localizations": {"de": {"name/extra": "reserved"}}},
        None,
        invalid_props=["localizations/de/name~1extra"],
    ),
]
