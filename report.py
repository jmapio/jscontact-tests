from backends import BackendError, InvalidCardError
from jscardutil import MatchJSCardError
from tests import Outcome, Result
from vcardutil import VCardMatchError


import datetime
import io
import json
import pprint


class HtmlReport:
    def __init__(self, backend_name: str):
        self.results: list[Result] = []
        self.backend_name = backend_name
        self.start = datetime.datetime.utcnow()

    def add(self, result: Result):
        self.results.append(result)

    def write_error(self, error: Exception, out: io.TextIOBase):
        if isinstance(error, VCardMatchError):
            print("<h4>Invalid vCard properties</h4>", file=out)
            print("<ul>", file=out)
            for m in error.match_errors:
                print("<li>", file=out)
                if m.prop:
                    print(f"<pre>{m.prop}</pre>", file=out)
                if m.prop and m.candidates:
                    print(
                        f"This property does not match any of its expected variants:",
                        file=out,
                    )
                elif m.prop:
                    print(
                        f"This property does not match any expected property.",
                        file=out,
                    )
                elif m.candidates:
                    print(
                        f"The following required properties were not matched by any property:",
                        file=out,
                    )
                print("</li>", file=out)

                if m.candidates:
                    for c in m.candidates:
                        print("<ul>", file=out)
                        print(
                            f"<li><pre>{pprint.pformat(c, indent=2, width=120)}</pre></li>",
                            file=out,
                        )
                        print("</ul>", file=out)
            print("</ul>", file=out)
        elif isinstance(error, MatchJSCardError):
            print("<h4>Invalid Card properties</h4>", file=out)
            for d in error.diff:
                print("<ul>", file=out)
                print(
                    f"<li><pre>{d.path}</pre></li>",
                    file=out,
                )
                if d.a_val and not d.b_val:
                    print(
                        f"This property is missing.",
                        file=out,
                    )
                elif not d.a_val and d.b_val:
                    print(
                        f"This property is unexpected.",
                        file=out,
                    )
                elif d.a_val and d.b_val:
                    print(
                        f"This property has the wrong value.",
                        file=out,
                    )

                if d.a_val:
                    print(
                        f"Expected value: <pre>{pprint.pformat(d.a_val, indent=2, width=120)}</pre>",
                        file=out,
                    )
                print("</ul>", file=out)
        elif isinstance(error, InvalidCardError):
            print("<h4>Card unexpectedly got rejected:</h4>", file=out)
            if error.json:
                print(
                    f"<pre>{json.dumps(error.json, indent=2, sort_keys=True)}</pre>",
                    file=out,
                )
            else:
                print(f"<pre>{error})</pre>", file=out)
        elif isinstance(error, BackendError):
            print("<h4>Unexpected response</h4>", file=out)
            if error.json:
                print(
                    f"<pre>{json.dumps(error.json, indent=2, sort_keys=True)}</pre>",
                    file=out,
                )
            else:
                print(f"<pre>{error})</pre>", file=out)
        elif error:
            print("<h4>Unknown error</h4>", file=out)
            print(f"<pre>{error}</pre>", file=out)

    def write(self, out: io.TextIOBase):
        print("<html>", file=out)
        print("<head>", file=out)
        print('<meta charset="utf-8">', file=out)
        print(
            f"<title>JSContact Tests ({self.backend_name} {self.start.isoformat})</title>",
            file=out,
        )
        print(
            "<style>.success { background: lightgreen; } .invalid { background: orange; } .error {background: red;}</style>",
            file=out,
        )
        print("</head>", file=out)
        print("<body>", file=out)

        print(f"<h1>JSContact Tests</h1>", file=out)
        print(f"{self.backend_name}, {self.start.ctime()} UTC", file=out)

        print("<h2>Summary</h2>", file=out)
        print("<table>", file=out)
        print("<tr>", file=out)
        print("<th>Test name</th>", file=out)
        print("<th>To vCard</th>", file=out)
        print("<th>From vCard</th>", file=out)
        print("</tr>", file=out)
        for result in self.results:
            print("<tr>", file=out)
            print(
                f'<td><a href="#{result.test_name}">{result.test_name}</a></td>',
                file=out,
            )
            print(
                f'<td><span class="{result.to_vcard}">{result.to_vcard}</span></td>',
                file=out,
            )
            print(
                f'<td><span class="{result.from_vcard}">{result.from_vcard}</span></td>',
                file=out,
            )
            print("</tr>", file=out)
        print("</table>", file=out)

        for result in self.results:
            print("<hr>", file=out)
            print(f"<p>", file=out)
            print(
                f'<h2 id="{result.test_name}">Test <code>{result.test_name}</code></h2>',
                file=out,
            )

            print(f"<h3>Card</h3>", file=out)
            print(
                f"<pre>{json.dumps(result.sent_jscard, indent=2, sort_keys=True)}</pre>",
                file=out,
            )

            print(
                f'<h3 id="{result.test_name}_to_vcard">To vCard: <span class="{result.to_vcard}">{result.to_vcard}</span></h3>',
                file=out,
            )
            if result.to_vcard != Outcome.skipped:
                if result.got_vcard:
                    print(f"<pre>{result.got_vcard}</pre>", file=out)
                if result.want_invalid_props and result.to_vcard != Outcome.success:
                    print(
                        "<h4>The Card is invalid and should have been rejected:</h4>",
                        file=out,
                    )
                    print("The following Card properties are invalid:", file=out)
                    for prop in result.want_invalid_props:
                        print("<ul>", file=out)
                        print(
                            f"<li><pre>{pprint.pformat(prop, indent=2, width=120)}</pre></li>",
                            file=out,
                        )
                        print("</ul>", file=out)
                if result.got_error and result.to_vcard != Outcome.success:
                    self.write_error(result.got_error, out)

            print(
                f'<h3 id="{result.test_name}_from_vcard">From vCard: <span class="{result.from_vcard}">{result.from_vcard}</span></h3>',
                file=out,
            )
            if result.from_vcard != Outcome.skipped:
                if result.got_jscard:
                    print(
                        f"<pre>{json.dumps(result.got_jscard, indent=2, sort_keys=True)}</pre>",
                        file=out,
                    )
                if result.got_error and result.from_vcard != Outcome.success:
                    self.write_error(result.got_error, out)

            print(f"</p>", file=out)

        print("</body>", file=out)
        print("</html>", file=out)
