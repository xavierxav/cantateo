import time
from datetime import date
from unittest.mock import Mock, patch

import pytest
from django.core.cache import cache

from psaumes.services.aelf import AELF_CACHE_TTL_SECONDS, get_aelf_data


@pytest.mark.django_db
class TestAelfCache:
    def setup_method(self, method=None):
        cache.clear()

    def test_get_aelf_data_uses_fresh_cache(self):
        target_date = date(2025, 6, 15)
        info_response = Mock(status_code=200)
        info_response.json.return_value = {"informations": {"ligne1": "Sainte Trinité"}}
        messes_response = Mock(status_code=200)
        messes_response.json.return_value = {
            "messes": [
                {
                    "lectures": [
                        {
                            "type": "Lecture du psaume",
                            "titre": "Psaume 8",
                            "texte": "Seigneur, notre Dieu, qu'il est grand !",
                        }
                    ]
                }
            ]
        }

        with patch("psaumes.services.aelf.requests.get", side_effect=[info_response, messes_response]) as mocked_get:
            first = get_aelf_data(target_date)
            second = get_aelf_data(target_date)

        assert first["info"] == {"ligne1": "Sainte Trinité"}
        assert first["psalm"]["kind"] == "psaume"
        assert second["info"] == {"ligne1": "Sainte Trinité"}
        assert mocked_get.call_count == 2

    def test_get_aelf_data_returns_stale_cache_on_failure(self):
        target_date = date(2025, 6, 15)
        stale_entry = {
            "data": {"ligne1": "Sainte Trinité"},
            "cached_at": time.time() - (AELF_CACHE_TTL_SECONDS + 60),
        }
        stale_messes = {
            "data": {
                "messes": [
                    {
                        "lectures": [
                            {
                                "type": "Lecture du psaume",
                                "titre": "Psaume 8",
                                "texte": "Seigneur, notre Dieu, qu'il est grand !",
                            }
                        ]
                    }
                ]
            },
            "cached_at": time.time() - (AELF_CACHE_TTL_SECONDS + 60),
        }

        cache.set(f"aelf_infos_{target_date.isoformat()}", stale_entry, timeout=60)
        cache.set(f"aelf_messes_{target_date.isoformat()}", stale_messes, timeout=60)

        with patch("psaumes.services.aelf.requests.get", side_effect=RuntimeError("boom")):
            data = get_aelf_data(target_date)

        assert data["info"] == {"ligne1": "Sainte Trinité"}
        assert data["psalm"]["kind"] == "psaume"
