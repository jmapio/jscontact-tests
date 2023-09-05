from backends import CNRBackend, CyrusBackend, BackendError
from report import HtmlReport
from tests import Outcome, jscontact_tests


import argparse
from operator import attrgetter
import os
import sys


def make_backend(confstr: str):
    try:
        (name, confstr) = confstr.split(sep=":", maxsplit=1)
        if name == "cyrus":
            (user, pwd, host) = confstr.split(sep=":", maxsplit=2)
            return CyrusBackend(user, pwd, host)
        elif name == "cnr":
            return CNRBackend(confstr)
        else:
            raise BackendError(f"Unknown backend {name}")
    except ValueError:
        raise BackendError("Invalid backend config")


parser = argparse.ArgumentParser(
    description="Test JSContact to vCard conversion.",
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
)
arg_run = parser.add_argument_group("Run")
arg_run.add_argument(
    "-b",
    "--backend",
    help="Either 'cyrus:<username>:<password>:<host[:port]>' or 'cnr:<url>'. Overrides JSCONTACT_TESTS_BACKEND environment variable.",
)
arg_run.add_argument(
    "-o",
    "--outfile",
    help="The file name where to write the test report to",
    default="report.html",
)
arg_run.add_argument(
    "-s",
    "--summary",
    choices=["full", "noheader", "none"],
    help="Print console summary completely (with color), without header (and no color) or not at all",
    default="full",
)
arg_run.add_argument("tests", nargs="*")
parser.add_argument(
    "-l",
    "--list",
    action="store_true",
    help="List tests instead of running",
)

args = parser.parse_args()

if args.list:
    for tc in sorted(jscontact_tests, key=attrgetter("id")):
        print(tc.id)
    sys.exit(os.EX_OK)

backend_config = args.backend or os.getenv("JSCONTACT_TESTS_BACKEND")
if not backend_config:
    print(
        "No backend configured. Either run with -b or set JSCONTACT_TESTS_BACKEND environment variable.",
        file=sys.stderr,
    )
    sys.exit(os.EX_USAGE)

backend = make_backend(backend_config)
report = HtmlReport(backend.__class__.__name__)
want_subset = set(args.tests)

def format_outcome(o: Outcome, color=True) -> str:
    if not color:
        return str(o)
    match o:
        case Outcome.error:
            color = "\033[91m"
        case Outcome.invalid:
            color = "\033[93m"
        case Outcome.success:
            color = "\033[92m"
        case _:
            color = "\033[96m"
    return color + o + "\033[0m"

if args.summary == "full":
    print("{:<30} {:<10} {:<10}".format("Test name", "From vCard", "To vCard"))
    print("{:<30} {:<10} {:<10}".format("---------", "----------", "--------"))

exitcode = os.EX_OK

for tc in sorted(jscontact_tests, key=attrgetter("id")):
    if not want_subset or tc.id in want_subset:
        result = tc.run(backend)
        if not result.is_success():
            exitcode = -1
        report.add(result)
        if args.summary != "none":
            print(
                "{:<30s} {:<10s}    {:<10s}".format(
                    result.test_name,
                    format_outcome(result.to_vcard, color=args.summary == "full"),
                    format_outcome(result.from_vcard, color=args.summary == "full"),
                )
            )
with open(args.outfile, "w", encoding="utf-8") as f:
    report.write(f)
