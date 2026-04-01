from __future__ import annotations

import logging
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .config import PipelineConfig


logger = logging.getLogger(__name__)


CMS_ARCHIVES = {
    "plan_information": "plan information  PPUF_2025Q3.zip",
    "basic_formulary": "basic drugs formulary file  PPUF_2025Q3.zip",
    "beneficiary_cost": "beneficiary cost file  PPUF_2025Q3.zip",
    "insulin_beneficiary_cost": "insulin beneficiary cost file  PPUF_2025Q3.zip",
    "pricing": "pricing file PPUF_2025Q3.zip",
    "geographic_locator": "geographic locator file  PPUF_2025Q3.zip",
    "excluded_drugs": "excluded drugs formulary file  PPUF_2025Q3.zip",
    "indication_coverage": "indication based coverage formulary file  PPUF_2025Q3.zip",
}

PHARMACY_NETWORK_ARCHIVES = [
    f"pharmacy networks file  PPUF_2025Q3 part {part}.zip" for part in range(1, 7)
]


@dataclass(slots=True)
class SourcePaths:
    cms_files: dict[str, Path]
    pharmacy_network_parts: list[Path]
    reference_files: dict[str, Path]
    rxcui_files: list[Path]


def _extract_single_file(archive_path: Path, output_path: Path) -> Path:
    if output_path.exists():
        logger.info("reuse extracted file %s", output_path)
        return output_path

    logger.info("extract archive %s -> %s", archive_path.name, output_path.name)
    with zipfile.ZipFile(archive_path) as archive:
        members = archive.namelist()
        if len(members) != 1:
            raise ValueError(f"Expected exactly one file in {archive_path}, found {members}")
        member_name = members[0]
        with archive.open(member_name) as source, output_path.open("wb") as target:
            shutil.copyfileobj(source, target)
    return output_path


def extract_sources(config: PipelineConfig) -> SourcePaths:
    config.ensure_directories()
    raw_dir = config.staging_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    logger.info("extract sources snapshot=%s profile=%s", config.snapshot_quarter, config.build_profile)

    cms_files: dict[str, Path] = {}
    for logical_name, archive_name in CMS_ARCHIVES.items():
        archive_path = config.cms_root / archive_name
        output_name = f"{logical_name}.txt"
        cms_files[logical_name] = _extract_single_file(archive_path, raw_dir / output_name)

    pharmacy_paths: list[Path] = []
    for part, archive_name in enumerate(PHARMACY_NETWORK_ARCHIVES, start=1):
        archive_path = config.cms_root / archive_name
        output_name = f"pharmacy_network_part_{part}.txt"
        pharmacy_paths.append(_extract_single_file(archive_path, raw_dir / output_name))

    reference_files = {
        "insulin_reference": config.reference_dir / "insulin_ref.csv",
        "us_zipcode_geo": config.reference_dir / "us_zipcode_geo.csv",
        "pde_sample": config.reference_dir / "pde.csv",
    }
    rxcui_files = sorted(config.rxcui_dir.glob("rxcui_properties_*.csv"))
    if not rxcui_files:
        raise FileNotFoundError(f"No RXCUI files found in {config.rxcui_dir}")

    return SourcePaths(
        cms_files=cms_files,
        pharmacy_network_parts=pharmacy_paths,
        reference_files=reference_files,
        rxcui_files=rxcui_files,
    )
