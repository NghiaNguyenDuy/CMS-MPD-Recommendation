from __future__ import annotations

from cms_mpd.config import PipelineConfig
from cms_mpd.pipeline import extract_sources


def test_extract_sources_from_local_archives():
    config = PipelineConfig()
    sources = extract_sources(config)

    assert set(sources.cms_files) == {
        "plan_information",
        "basic_formulary",
        "beneficiary_cost",
        "insulin_beneficiary_cost",
        "pricing",
        "geographic_locator",
        "excluded_drugs",
        "indication_coverage",
    }
    assert len(sources.pharmacy_network_parts) == 6
    assert all(path.exists() for path in sources.cms_files.values())
    assert all(path.exists() for path in sources.pharmacy_network_parts)
    assert all(path.exists() for path in sources.reference_files.values())
    assert len(sources.rxcui_files) >= 1

