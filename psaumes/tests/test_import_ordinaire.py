"""Tests unitaires de la fonction pure detect_partie_et_voix.

Aucune base de données n'est nécessaire : on ne teste que l'analyse du nom
de fichier. Le marqueur ``django_db`` est volontairement absent afin que
ces tests soient rapides et isolés.
"""

import pytest

from psaumes.management.commands.import_ordinaire import detect_partie_et_voix, _parse_version


@pytest.mark.parametrize('filename, expected', [
    # Une partie + une voix (noms complets).
    ('Kyrie - Soprano.mp3', ('KYRIE', 'S')),
    ('Gloria - Alto.mp3', ('GLORIA', 'A')),
    ('Sanctus - Tenor.mp3', ('SANCTUS', 'T')),
    ('Agnus - Basse.mp3', ('AGNUS_DEI', 'B')),
    ('Alléluia - Mix.mp3', ('ALLELUIA', 'M')),
    ('Anamnèse - Instrumental.mp3', ('ANAMNESE', 'I')),

    # Insensibilité aux accents (Alléluia/Alleluia, Ténor/Tenor).
    ('Alléluia - Ténor.mp3', ('ALLELUIA', 'T')),
    ('Alleluia - Tenor.mp3', ('ALLELUIA', 'T')),

    # Variantes de l'Anamnèse : mémorial / mystère.
    ('Mémorial - Alto.mp3', ('ANAMNESE', 'A')),
    ('Mystère - Soprano.mp3', ('ANAMNESE', 'S')),

    # Raccourcis de voix.
    ('Kyrie - sop.mp3', ('KYRIE', 'S')),
    ('Instru - Kyrie.mp3', ('KYRIE', 'I')),
    ('Ten - Gloria.mp3', ('GLORIA', 'T')),
    ('Bas - Agnus.mp3', ('AGNUS_DEI', 'B')),

    # Jetons courts S avec séparateurs ('s.', '-s', '_s').
    ('S. - Sanctus.mp3', ('SANCTUS', 'S')),
    ('Gloria-S.mp3', ('GLORIA', 'S')),
    ('Kyrie_S.mp3', ('KYRIE', 'S')),

    # Casse indifférente.
    ('sanctus - soprano.mp3', ('SANCTUS', 'S')),

    # Partie seule, sans voix.
    ('Gloria.mp3', ('GLORIA', None)),
    ('Kyrie.pdf', ('KYRIE', None)),

    # Voix seule, sans partie.
    ('Soprano.mp3', (None, 'S')),

    # Ambiguïté : 'basse' doit donner B avant tout raccourci partiel,
    # sans partie détectée.
    ('Messe de la Basse.mp3', (None, 'B')),

    # Aucune correspondance.
    ('readme.txt', (None, None)),

    # Conventions de nommage réelles des dossiers de l'utilisateur.
    ('Agnus v3 musique.mp3', ('AGNUS_DEI', 'I')),
    ('Kyrie-Inst.mp3', ('KYRIE', 'I')),
    ('Agnus v3 soprane.mp3', ('AGNUS_DEI', 'S')),
    ('Kyrie-Alto.mp3', ('KYRIE', 'A')),
    ('Kyrie-Ténor.mp3', ('KYRIE', 'T')),
    ('Kyrie-Basse.mp3', ('KYRIE', 'B')),
    ('Anamnèse v2-2.mp3', ('ANAMNESE', None)),
    ('Prière universelle.mp3', ('PRIERE_UNIVERSELLE', None)),
    ('Prière Universelle - Alto.mp3', ('PRIERE_UNIVERSELLE', 'A')),
    ('PRIERE UNIVERSELLE - Basse.mp3', ('PRIERE_UNIVERSELLE', 'B')),
])
def test_detect_partie_et_voix(filename, expected):
    assert detect_partie_et_voix(filename) == expected


@pytest.mark.parametrize('filename, expected', [
    ('Gloria v3 alto.mp3', 3),
    ('Sanctus.mp3', 0),
    ('Alleluia v2n soprano.mp3', 2),
    ('Kyrie v2-2.mp3', 2),
])
def test_parse_version(filename, expected):
    assert _parse_version(filename) == expected
