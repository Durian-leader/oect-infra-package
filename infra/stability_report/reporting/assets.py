from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence


try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PyYAML is required for the reporting pipeline") from exc

from ...catalog import UnifiedExperimentManager
from ...visualization import OECTPlotter, ChipFeaturePlotter

logger = logging.getLogger(__name__)


@dataclass
class AssetDefinition:
    """Declarative definition of a single asset type."""

    id: str
    generator: str
    scope: str  # e.g. per_chip, per_device, feature_variants
    output: str
    params: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AssetDefinition":
        return cls(
            id=data["id"],
            generator=data["generator"],
            scope=data.get("scope", "per_chip"),
            output=data["output"],
            params=data.get("params", {}),
            enabled=data.get("enabled", True),
        )


@dataclass
class AssetRecord:
    asset_id: str
    path: str
    scope: str
    chip_id: str
    device_id: Optional[str] = None
    variant: Optional[str] = None
    generator: Optional[str] = None
    status: str = "generated"
    size_bytes: Optional[int] = None
    mtime: Optional[float] = None
    sha1: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "path": self.path,
            "scope": self.scope,
            "chip_id": self.chip_id,
            "device_id": self.device_id,
            "variant": self.variant,
            "generator": self.generator,
            "status": self.status,
            "size_bytes": self.size_bytes,
            "mtime": self.mtime,
            "sha1": self.sha1,
        }


@dataclass
class AssetManifest:
    """Snapshot of assets for a single chip."""

    chip_id: str
    records: List[AssetRecord] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    profile_name: Optional[str] = None

    def add(self, record: AssetRecord) -> None:
        self.records.append(record)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chip_id": self.chip_id,
            "generated_at": self.generated_at,
            "profile_name": self.profile_name,
            "records": [r.to_dict() for r in self.records],
        }

    def find(self, asset_id: str, *, device_id: Optional[str] = None, variant: Optional[str] = None) -> List[AssetRecord]:
        results = [r for r in self.records if r.asset_id == asset_id]
        if device_id is not None:
            results = [r for r in results if r.device_id == device_id]
        if variant is not None:
            results = [r for r in results if r.variant == variant]
        return results


class ManifestStore:
    """Persist manifests to disk."""

    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def manifest_path(self, chip_id: str) -> Path:
        safe_chip = chip_id.replace("#", "chip").replace("/", "_")
        return self.base_dir / f"manifest_{safe_chip}.json"

    def save(self, manifest: AssetManifest) -> None:
        path = self.manifest_path(manifest.chip_id)
        path.write_text(json.dumps(manifest.to_dict(), indent=2, ensure_ascii=True))
        logger.info("Saved manifest %s", path)

    def load(self, chip_id: str) -> Optional[AssetManifest]:
        path = self.manifest_path(chip_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        manifest = AssetManifest(chip_id=data["chip_id"], generated_at=data.get("generated_at", ""))
        manifest.profile_name = data.get("profile_name")
        for rec in data.get("records", []):
            manifest.add(AssetRecord(**rec))
        return manifest

    def list_chips(self) -> List[str]:
        chips = []
        for path in self.base_dir.glob("manifest_*.json"):
            name = path.stem.replace("manifest_", "")
            if name.startswith("chip"):
                chips.append("#" + name[len("chip") :])
            else:
                chips.append(name)
        return sorted(chips)


class AssetRegistry:
    """Registry of generator callables."""

    def __init__(self) -> None:
        self._registry: Dict[str, Callable[["GenerationContext", Dict[str, Any]], Sequence[Path]]] = {}

    def register(self, name: str, func: Callable[["GenerationContext", Dict[str, Any]], Sequence[Path]]) -> None:
        self._registry[name] = func

    def get(self, name: str) -> Callable[["GenerationContext", Dict[str, Any]], Sequence[Path]]:
        if name not in self._registry:
            raise KeyError(f"No asset generator registered for '{name}'")
        return self._registry[name]


@dataclass
class GenerationContext:
    chip_id: str
    base_dir: Path
    asset_definition: AssetDefinition
    experiment_manager: UnifiedExperimentManager
    experiment: Optional[Any] = None
    device_id: Optional[str] = None
    feature_plotter: Optional[ChipFeaturePlotter] = None
    overwrite: bool = False

    def resolve_path(self, pattern: str, **extra: Any) -> Path:
        values = {
            "chip_id": self.chip_id,
            "chip_safe": self.chip_id.replace("#", "chip").replace("/", "_"),
            "device_id": self.device_id,
        }
        values.update(extra)
        path = (self.base_dir / pattern.format(**values)).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


class AssetGenerator:
    def __init__(
        self,
        assets_dir: Path,
        config_path: Path,
        *,
        config_profile: Optional[str] = None,
        registry: Optional[AssetRegistry] = None,
        compute_sha1: bool = False,
        overwrite: bool = False,
        catalog_config: Optional[Path] = None,
    ) -> None:
        self.assets_dir = Path(assets_dir)
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = Path(config_path)
        self.profile_name = config_profile or self.config_path.stem
        self.registry = registry or default_asset_registry()
        self.compute_sha1 = compute_sha1
        self.overwrite = overwrite
        self.manifest_store = ManifestStore(self.assets_dir / "manifests")
        self.catalog_config = Path(catalog_config) if catalog_config else None
        if self.catalog_config:
            self.experiment_manager = UnifiedExperimentManager(str(self.catalog_config))
        else:
            self.experiment_manager = UnifiedExperimentManager()
        self.feature_plotter: Optional[ChipFeaturePlotter] = None
        self.asset_definitions = self._load_config()

    def _load_config(self) -> List[AssetDefinition]:
        config = yaml.safe_load(self.config_path.read_text())
        if not config or "assets" not in config:
            raise ValueError(f"Asset configuration '{self.config_path}' missing 'assets' list")
        return [AssetDefinition.from_dict(item) for item in config["assets"] if item.get("enabled", True)]

    def _ensure_feature_plotter(self, params: Dict[str, Any]) -> None:
        if self.feature_plotter is not None:
            return
        features_dir = params.get("features_dir")
        if not features_dir:
            candidates = [
                Path("/mnt/d/UserData/lidonghaowsl/data/Stability_PS/features/"),
                Path("data/features"),
            ]
            for candidate in candidates:
                if candidate.exists():
                    features_dir = candidate
                    break
        if not features_dir:
            raise RuntimeError("Feature directory not found for ChipFeaturePlotter")
        self.feature_plotter = ChipFeaturePlotter(features_dir)

    def _has_up_to_date_asset(self, path: Path, source_files: Iterable[Path]) -> bool:
        if not path.exists() or not source_files:
            return False
        target_mtime = path.stat().st_mtime
        for src in source_files:
            try:
                if Path(src).stat().st_mtime > target_mtime:
                    return False
            except FileNotFoundError:
                return False
        return True

    def generate_for_chip(self, chip_id: str) -> AssetManifest:
        logger.info("Generating assets for chip %s", chip_id)
        manifest = AssetManifest(chip_id=chip_id)
        manifest.profile_name = self.profile_name
        experiments = self.experiment_manager.search(chip_id=chip_id)
        device_map = {exp.device_id: exp for exp in experiments}

        for asset_def in self.asset_definitions:
            context = GenerationContext(
                chip_id=chip_id,
                base_dir=self.assets_dir,
                asset_definition=asset_def,
                experiment_manager=self.experiment_manager,
                overwrite=self.overwrite,
            )
            if asset_def.scope == "per_chip":
                self._generate_per_chip(asset_def, context, manifest)
            elif asset_def.scope == "per_device":
                for device_id, experiment in device_map.items():
                    ctx = GenerationContext(
                        chip_id=chip_id,
                        base_dir=self.assets_dir,
                        asset_definition=asset_def,
                        experiment_manager=self.experiment_manager,
                        experiment=experiment,
                        device_id=device_id,
                        overwrite=self.overwrite,
                    )
                    self._generate_asset(asset_def, ctx, manifest)
            elif asset_def.scope == "feature_variants":
                self._ensure_feature_plotter(asset_def.params)
                for variant in asset_def.params.get("variants", []):
                    ctx = GenerationContext(
                        chip_id=chip_id,
                        base_dir=self.assets_dir,
                        asset_definition=asset_def,
                        experiment_manager=self.experiment_manager,
                        overwrite=self.overwrite,
                    )
                    self._generate_feature_variant(asset_def, ctx, manifest, variant)
            else:
                logger.warning("Unknown asset scope '%s'", asset_def.scope)

        self.manifest_store.save(manifest)
        return manifest

    def _generate_per_chip(self, asset_def: AssetDefinition, context: GenerationContext, manifest: AssetManifest) -> None:
        self._generate_asset(asset_def, context, manifest)

    def _generate_asset(self, asset_def: AssetDefinition, context: GenerationContext, manifest: AssetManifest) -> None:
        generator = self.registry.get(asset_def.generator)
        output_paths = generator(context, asset_def.params)
        for path in output_paths:
            record = self._build_record(asset_def, context, Path(path))
            manifest.add(record)

    def _generate_feature_variant(
        self,
        asset_def: AssetDefinition,
        context: GenerationContext,
        manifest: AssetManifest,
        variant: Dict[str, Any],
    ) -> None:
        generator = self.registry.get(asset_def.generator)
        params = {**asset_def.params, **variant}
        params.setdefault("variant", variant.get("variant"))
        context.feature_plotter = self.feature_plotter
        output_paths = generator(context, params)
        for path in output_paths:
            record = self._build_record(
                asset_def,
                context,
                Path(path),
                variant=params.get("variant"),
            )
            manifest.add(record)

    def _build_record(
        self,
        asset_def: AssetDefinition,
        context: GenerationContext,
        path: Path,
        *,
        variant: Optional[str] = None,
    ) -> AssetRecord:
        if not path.exists():
            return AssetRecord(
                asset_id=asset_def.id,
                path=str(path),
                scope=asset_def.scope,
                chip_id=context.chip_id,
                device_id=context.device_id,
                variant=variant,
                generator=asset_def.generator,
                status="missing",
            )
        stat = path.stat()
        sha1 = None
        if self.compute_sha1:
            sha1 = _sha1_file(path)
        return AssetRecord(
            asset_id=asset_def.id,
            path=str(path),
            scope=asset_def.scope,
            chip_id=context.chip_id,
            device_id=context.device_id,
            variant=variant,
            generator=asset_def.generator,
            status="generated",
            size_bytes=stat.st_size,
            mtime=stat.st_mtime,
            sha1=sha1,
        )


def _sha1_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha1()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


# --- default generators ----------------------------------------------------

def default_asset_registry() -> AssetRegistry:
    registry = AssetRegistry()
    registry.register("plotter_image", plotter_image_generator)
    registry.register("plotter_video", plotter_video_generator)
    registry.register("feature_plot", feature_plot_generator)
    return registry


def plotter_image_generator(context: GenerationContext, params: Dict[str, Any]) -> Sequence[Path]:
    if context.experiment is None:
        raise ValueError("plotter_image requires experiment in context")

    method_name = params.get("method")
    if not method_name:
        raise ValueError("plotter_image requires 'method' param")

    output_pattern = params.get("filename") or context.asset_definition.output
    plotter = OECTPlotter(context.experiment.file_path)
    method = getattr(plotter, method_name)
    kwargs = params.get("method_params", {})
    fig = method(**kwargs)
    if fig is None:
        return []
    path = context.resolve_path(output_pattern)
    if path.exists() and not context.overwrite:
        logger.debug('Skipping existing image %s', path)
        fig.clf()
        return [path]
    fig.savefig(path, dpi=params.get('dpi', 300), bbox_inches=params.get('bbox_inches', 'tight'))
    fig.clf()
    return [path]


def plotter_video_generator(context: GenerationContext, params: Dict[str, Any]) -> Sequence[Path]:
    if context.experiment is None:
        raise ValueError("plotter_video requires experiment in context")
    method_name = params.get("method", "create_transfer_video_parallel")
    output_pattern = params.get("filename") or context.asset_definition.output
    plotter = OECTPlotter(context.experiment.file_path)
    method = getattr(plotter, method_name)
    video_path = context.resolve_path(output_pattern)
    if video_path.exists() and not context.overwrite:
        logger.debug('Skipping existing video %s', video_path)
        return [video_path]
    method_kwargs = {k: v for k, v in params.items() if k not in {'method', 'filename'}}
    final_path = method(save_path=str(video_path), **method_kwargs)
    if not final_path:
        return []
    return [Path(final_path)]


def feature_plot_generator(context: GenerationContext, params: Dict[str, Any]) -> Sequence[Path]:
    if context.feature_plotter is None:
        raise ValueError("feature_plot requires ChipFeaturePlotter")
    feature_name = params.get("feature")
    variant = params.get("variant")
    if not feature_name or not variant:
        raise ValueError("feature_plot requires 'feature' and 'variant'")
    output_pattern = params.get("filename") or context.asset_definition.output
    fig = context.feature_plotter.plot_chip_feature(
        chip_id=context.chip_id,
        feature_name=feature_name,
        skip_points=params.get("skip_points", 0),
        normalize_to_first=params.get("normalize_to_first", False),
        figsize=tuple(params.get("figsize", (12, 8))),
    )
    if fig is None:
        return []
    path = context.resolve_path(output_pattern, variant=variant)
    if path.exists() and not context.overwrite:
        logger.debug('Skipping existing feature image %s', path)
        fig.clf()
        return [path]
    fig.savefig(path, dpi=params.get('dpi', 300), bbox_inches=params.get('bbox_inches', 'tight'))
    fig.clf()
    return [path]
