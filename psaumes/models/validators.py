import os
import zipfile

from django.core.exceptions import ValidationError


def _read_start(value, size=4096):
    position = None
    try:
        position = value.tell()
    except (AttributeError, OSError):
        position = None

    try:
        value.seek(0)
        return value.read(size)
    finally:
        if position is not None:
            try:
                value.seek(position)
            except (AttributeError, OSError):
                pass


def _validate_extension(value, allowed_extensions):
    ext = os.path.splitext(value.name or '')[1].lower()
    if ext not in allowed_extensions:
        allowed = ', '.join(sorted(allowed_extensions))
        raise ValidationError(f'Extension non autorisée. Extensions acceptées : {allowed}.')
    return ext


def validate_pdf_upload(value):
    _validate_extension(value, {'.pdf'})
    header = _read_start(value, 5)
    if header != b'%PDF-':
        raise ValidationError('Le fichier doit être un PDF valide.')


def validate_mxl_upload(value):
    _validate_extension(value, {'.mxl', '.musicxml', '.xml'})
    if value.name.lower().endswith('.mxl'):
        position = None
        try:
            position = value.tell()
            value.seek(0)
            with zipfile.ZipFile(value) as archive:
                names = {name.lower() for name in archive.namelist()}
                has_musicxml = any(name.endswith(('.xml', '.musicxml')) for name in names)
                has_container = 'meta-inf/container.xml' in names
                if not has_musicxml and not has_container:
                    raise ValidationError('Le fichier MXL ne contient pas de partition MusicXML.')
        except zipfile.BadZipFile as exc:
            raise ValidationError('Le fichier MXL doit être une archive ZIP valide.') from exc
        finally:
            if position is not None:
                try:
                    value.seek(position)
                except (AttributeError, OSError):
                    pass
        return

    header = _read_start(value, 256).lstrip()
    if not header.startswith((b'<?xml', b'<score-partwise', b'<score-timewise')):
        raise ValidationError('Le fichier doit être un MusicXML valide.')


def validate_mp3_upload(value):
    _validate_extension(value, {'.mp3'})
    header = _read_start(value, 4096)
    if header.startswith(b'ID3'):
        return
    if b'\xff\xfb' not in header and b'\xff\xfa' not in header and b'\xff\xf3' not in header:
        raise ValidationError('Le fichier doit être un MP3 valide.')
