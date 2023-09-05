# JSContact Tests

This is a test suite for JSContact and vCard conversion as outlined in
[draft-ietf-calext-jscontact-vcard](https://datatracker.ietf.org/doc/draft-ietf-calext-jscontact-vcard/).

## Installation

### Install Python 3 and pip

Install Python 3. Then install [Pip](https://pypi.org/project/pip/). Most likely your
system already has installed both. Otherwise it should provide packages.

The tests run on Python 3.11.4 or later. Maybe they'll run on earlier versions, too.

### Get the test sources

Fetch the latest sources from [https://github.com/rsto/jscontact-tests/](https://github.com/rsto/jscontact-tests/).
Change into the `jscontact-tests` directory.

### Create a Python virtual environment

Rather than installing system-wide Python dependencies, we'll set up a virtual
environment:

    $ python -m venv venv

then activate this environment in your shell

    $ source venv/bin/activate

### Install project dependencies

Now that the virtual environment is set up, install the project dependencies
using `pip`:

    (venv) $ pip install -r requirements.txt

## Running

Call the test runner with `-h` or `--help` for all available
command line options.

    (venv) $ python main.py --help

### Choose and configure a backend

Choose the backend to run tests against using either the '-b'
(or '--backend') argument, or alternatively setting its value
in the `JSCONTACT_TESTS_BACKEND` environment variable.
The backend config value is backend-specific.

The following backend config is using the Cyrus backend, authenticating
JMAP requests as user `cassandane` and password `secret`. The JMAP server
is assumed to listen on host `localhost` and port `9101`:

    cyrus:cassandane:secret:localhost:9101

The following backend config is using the CNR backend that listens
at URL `http://localhost:8080/convert`:

    cnr:http://localhost:8080/convert

### Run tests

Run the test suite (assuming you configured the backend in
the environment variable `JSCONTACT_TESTS_BACKEND`):

    (venv) $ python main.py

This will give a short summary on the command line. The actual test results
are in file `report.html`.

If you only want to run a single or multiple tests, give their
names as arguments on the command line like

    (venv) $ python main.py mytest1 mytest2

The return code either is `EX_OK` (0) if all tests passed,
-1 if any test failed, or `EX_USAGE` for invalid arguments.

## Testing other backends

Testing other backends can be accomplished either by adding a new backend
implementation to `backends.py` or by providing a network service that
implements the API of one of the already implemented APIs.

The simplest is to emulate the CNR backend by meeting the following
requirements:

- Your network service must listen on a HTTP or HTTPS URL and
  accept POST requests at that location
- For JSContact to vCard conversion, the POST request contains
  a `Content-Type` header of value `application/jscontact+json`,
  and the JSContact Card in the body.
- For vCard to JSContact conversion, the POST request contains
  a `Content-Type` header of value `text/vcard;charset=utf8`,
  and the vCard in the body.
- On successful conversion, the HTTP response must have status 200
  and the `Content-Type` header value be set to `application/jscontact+json`
  or `text/vcard;charset=utf8`, respectively.
- For invalid input, such as for invalid properties, the HTTP response
  must have status 422. The body may contain debugging information.
- If the HTTP request `Content-Type` header is missing or does not
  match the expected values, the HTTP response must have status 415.
- Otherwise the HTTP response may have any status and is handled as
  an unexpected error.
