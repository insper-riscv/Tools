"""Validate an IP-XACT document against IEEE Std 1685-2022.

The schemas are the ones Accellera publishes, packaged unchanged in the
`schemas` folder (see its NOTICE), so the validation needs no network.
"""

from functools import cache
from pathlib import Path

import xmlschema

SCHEMA_DIR = Path(__file__).parent / "schemas" / "1685-2022"


@cache
def load_schema() -> xmlschema.XMLSchema:
    """Load the IP-XACT schema once.

    Returns
    -------
    xmlschema.XMLSchema
        The schema built from `index.xsd` and the files it includes.
    """
    return xmlschema.XMLSchema(str(SCHEMA_DIR / "index.xsd"))


def schema_errors(path: Path) -> list[str]:
    """List what a document breaks in the schema.

    Parameters
    ----------
    path : Path
        The XML file.

    Returns
    -------
    list of str
        One line for each violation; empty when the document is valid.
    """
    schema = load_schema()
    return [
        f"{path.name}: {error.path}: {error.reason}"
        for error in schema.iter_errors(str(path))
    ]
