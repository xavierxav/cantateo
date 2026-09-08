from pathlib import Path
from xml.etree import ElementTree


class MusicXmlValidationError(ValueError):
    """Raised when generated MusicXML is missing or structurally invalid."""


def validate_musicxml_file(path: Path) -> None:
    if not path.exists() or path.stat().st_size == 0:
        raise MusicXmlValidationError('Generated MusicXML file is missing or empty.')

    try:
        root = ElementTree.parse(path).getroot()
    except ElementTree.ParseError as exc:
        raise MusicXmlValidationError('Generated MusicXML is not valid XML.') from exc

    tag = _local_name(root.tag)
    if tag not in {'score-partwise', 'score-timewise'}:
        raise MusicXmlValidationError('Generated XML is not a MusicXML score.')


def _local_name(tag):
    if '}' in tag:
        return tag.rsplit('}', 1)[1]
    return tag
