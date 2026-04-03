from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


ENV_PREFIX = "CMS_MPD"
BENEFIT_DESIGN_MODES = ("auto", "2025_redesign", "2024_standard")


def _env_value(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _env_path(name: str) -> Path | None:
    raw = _env_value(name)
    return Path(raw) if raw else None


def _default_build_profile() -> str:
    profile = _env_value(f"{ENV_PREFIX}_BUILD_PROFILE", "full").lower()
    return profile if profile in {"full", "demo"} else "full"


def _default_benefit_design_mode() -> str:
    mode = _env_value(f"{ENV_PREFIX}_BENEFIT_DESIGN_MODE", "auto").lower()
    return mode if mode in BENEFIT_DESIGN_MODES else "auto"


def _default_demo_zipcodes() -> tuple[str, ...]:
    raw = _env_value(f"{ENV_PREFIX}_DEMO_ZIPCODES", "43004")
    values = tuple(part.strip().zfill(5) for part in raw.split(",") if part.strip())
    return values or ("43004",)


def _default_data_dir(project_root: Path) -> Path:
    return _env_path(f"{ENV_PREFIX}_DATA_DIR") or (project_root / "data")


def _looks_like_source_data_dir(candidate: Path, cms_folder_name: str) -> bool:
    return (
        (candidate / cms_folder_name).exists()
        or (candidate / "references_data").exists()
        or (candidate / "rxcui_info").exists()
    )


def _default_source_data_dir(project_root: Path, data_dir: Path, cms_folder_name: str) -> Path:
    explicit = _env_path(f"{ENV_PREFIX}_SOURCE_DATA_DIR")
    if explicit is not None:
        return explicit

    candidates = [
        data_dir,
        project_root.parent / "Medicare-PartD-Recommendation" / "data",
        project_root.parent / "CMS-Medicare-PartD-Recommendation" / "data",
    ]
    for candidate in candidates:
        if _looks_like_source_data_dir(candidate, cms_folder_name):
            return candidate
    return data_dir


@dataclass(slots=True)
class PipelineConfig:
    project_root: Path = field(default_factory=lambda: Path(__file__).resolve().parents[2])
    snapshot_quarter: str = "2025-Q3"
    cms_folder_name: str = (
        "Quarterly Prescription Drug Plan Formulary, Pharmacy Network, and Pricing Information"
    )
    db_filename: str = "cms_mpd.duckdb"
    build_profile: str = field(default_factory=_default_build_profile)
    benefit_design_mode: str = field(default_factory=_default_benefit_design_mode)
    demo_zipcodes: tuple[str, ...] = field(default_factory=_default_demo_zipcodes)
    data_dir: Path | None = None
    source_data_dir: Path | None = None

    def __post_init__(self) -> None:
        self.project_root = Path(self.project_root)
        self.benefit_design_mode = (
            self.benefit_design_mode.lower()
            if self.benefit_design_mode.lower() in BENEFIT_DESIGN_MODES
            else "auto"
        )
        self.data_dir = Path(self.data_dir) if self.data_dir is not None else _default_data_dir(self.project_root)
        self.source_data_dir = (
            Path(self.source_data_dir)
            if self.source_data_dir is not None
            else _default_source_data_dir(self.project_root, self.data_dir, self.cms_folder_name)
        )

    @property
    def source_cms_root(self) -> Path:
        return self.source_data_dir / self.cms_folder_name / self.snapshot_quarter

    @property
    def source_reference_dir(self) -> Path:
        return self.source_data_dir / "references_data"

    @property
    def source_rxcui_dir(self) -> Path:
        return self.source_data_dir / "rxcui_info"

    @property
    def cms_root(self) -> Path:
        return self.source_cms_root

    @property
    def reference_dir(self) -> Path:
        return self.source_reference_dir

    @property
    def rxcui_dir(self) -> Path:
        return self.source_rxcui_dir

    @property
    def staging_dir(self) -> Path:
        return self.data_dir / "staging" / self.snapshot_quarter

    @property
    def db_path(self) -> Path:
        if self.build_profile == "demo":
            return self.data_dir / self.db_filename.replace(".duckdb", "_demo.duckdb")
        return self.data_dir / self.db_filename

    @property
    def model_dir(self) -> Path:
        return self.data_dir / "models" / self.snapshot_quarter / self.build_profile

    @property
    def training_dir(self) -> Path:
        return self.data_dir / "training" / self.snapshot_quarter / self.build_profile

    @property
    def model_artifact_path(self) -> Path:
        return self.model_artifact_path_for("tree")

    def model_artifact_path_for(self, model_type: str) -> Path:
        return self.model_dir / f"hybrid_reranker_{model_type}.json"

    @property
    def training_dataset_path(self) -> Path:
        return self.training_dir / "hybrid_reranker_dataset.csv"

    @property
    def training_dataset_metadata_path(self) -> Path:
        return self.training_dir / "hybrid_reranker_dataset.metadata.json"

    @property
    def evaluation_report_path(self) -> Path:
        return self.evaluation_report_path_for("tree")

    def evaluation_report_path_for(self, model_type: str) -> Path:
        return self.training_dir / f"hybrid_reranker_evaluation_{model_type}.json"

    @property
    def research_dir(self) -> Path:
        return self.training_dir / "research"

    @property
    def is_demo_profile(self) -> bool:
        return self.build_profile == "demo"

    @property
    def normalized_demo_zipcodes(self) -> tuple[str, ...]:
        return tuple(zipcode.strip().zfill(5) for zipcode in self.demo_zipcodes if zipcode.strip())

    def ensure_directories(self) -> None:
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.training_dir.mkdir(parents=True, exist_ok=True)
