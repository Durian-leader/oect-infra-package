from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Iterable, List, Optional

from catalog import UnifiedExperimentManager

from .assets import AssetGenerator
from .reports import ReportComposer
from .slides import SlideEngine

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--verbose", action="store_true", help="Enable debug logging")
    common.add_argument("--assets-dir", default="build/assets", help="Directory to store generated assets")
    common.add_argument("--slides-config", default="configs/slides.yaml", help="Slide definition YAML")
    common.add_argument("--assets-config", default="configs/assets.yaml", help="Asset profile YAML")
    common.add_argument("--reports-config", default="configs/reports.yaml", help="Report definition YAML")
    common.add_argument("--catalog-config", help="Catalog configuration for experiment manager")

    parser = argparse.ArgumentParser(
        description="Composable stability report pipeline",
        parents=[common],
    )
    subparsers = parser.add_subparsers(dest="command")

    assets_parser = subparsers.add_parser("assets", help="Asset management commands", parents=[common])
    assets_sub = assets_parser.add_subparsers(dest="action")
    assets_gen = assets_sub.add_parser("generate", help="Generate assets for chips", parents=[common])
    assets_gen.add_argument("--chips", nargs="*", help="Target chip IDs or '*' for all")
    assets_gen.add_argument("--overwrite", action="store_true", help="Overwrite existing files")
    assets_gen.add_argument("--sha1", action="store_true", help="Compute SHA1 checksum for records")

    slides_parser = subparsers.add_parser("slides", help="Slide generation commands", parents=[common])
    slides_build = slides_parser.add_subparsers(dest="action")
    slides_build_cmd = slides_build.add_parser("build", help="Build slides from assets", parents=[common])
    slides_build_cmd.add_argument("--slide-ids", nargs="*", help="Limit to specific slide IDs")
    slides_build_cmd.add_argument("--chips", nargs="*", help="Limit to specific chips")
    slides_build_cmd.add_argument("--slides-dir", default="build/slides", help="Output directory for single slides")

    reports_parser = subparsers.add_parser("reports", help="Compose final reports", parents=[common])
    reports_sub = reports_parser.add_subparsers(dest="action")
    reports_compose = reports_sub.add_parser("compose", help="Compose a report", parents=[common])
    reports_compose.add_argument("report_id", help="Report identifier from config")
    reports_compose.add_argument("--output", help="Optional output path")
    reports_compose.add_argument("--output-dir", default="build/reports", help="Directory for final reports")

    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    if args.command == "assets" and args.action == "generate":
        return _cmd_assets_generate(args)
    if args.command == "slides" and args.action == "build":
        return _cmd_slides_build(args)
    if args.command == "reports" and args.action == "compose":
        return _cmd_reports_compose(args)

    parser.print_help()
    return 1


def _cmd_assets_generate(args) -> int:
    assets_dir = Path(args.assets_dir)
    generator = AssetGenerator(
        assets_dir=assets_dir,
        config_path=Path(args.assets_config),
        compute_sha1=args.sha1,
        overwrite=args.overwrite,
        catalog_config=Path(args.catalog_config) if args.catalog_config else None,
    )
    target_chips = _resolve_chips(args.chips, generator.experiment_manager)
    for chip_id in target_chips:
        generator.generate_for_chip(chip_id)
    return 0


def _cmd_slides_build(args) -> int:
    assets_dir = Path(args.assets_dir)
    slides_dir = Path(args.slides_dir)
    engine = SlideEngine(
        assets_dir=assets_dir,
        slides_dir=slides_dir,
        config_path=Path(args.slides_config),
    )
    engine.build(
        slide_ids=args.slide_ids,
        chips=args.chips,
    )
    return 0


def _cmd_reports_compose(args) -> int:
    assets_dir = Path(args.assets_dir)
    output_dir = Path(args.output_dir)
    composer = ReportComposer(
        assets_dir=assets_dir,
        slides_config_path=Path(args.slides_config),
        reports_config_path=Path(args.reports_config),
        output_dir=output_dir,
    )
    output_path = Path(args.output) if args.output else None
    composer.compose(args.report_id, output_path=output_path)
    return 0


def _resolve_chips(spec: Optional[List[str]], manager: UnifiedExperimentManager) -> List[str]:
    experiments = manager.search()
    chips = sorted({exp.chip_id for exp in experiments})
    if not spec:
        return chips
    if "*" in spec:
        return chips
    filtered = [chip for chip in chips if chip in spec]
    missing = [chip for chip in spec if chip not in chips and chip != "*"]
    for item in missing:
        logger.warning("Chip %s not found in catalog", item)
    filtered.extend(missing)
    return filtered


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
