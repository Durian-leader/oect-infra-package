**模块简介**
- 目标：为 OECT（有机电化学晶体管）器件生成科研级稳定性分析报告（PPTX），聚焦不同封装面积的对比分析。
- 组成：提供两类工作流
  - 两阶段管道 v2（单文件脚本）：先生成素材（图片/视频），再装配成完整 PPT。
  - 组合式三阶段子系统 reporting（包）：Assets → Slides → Reports，可通过 YAML 声明式扩展。

**依赖与外部模块**
- 第三方：`python-pptx`（PPT 生成）、`PyYAML`（配置解析）。
- 项目内：`catalog.UnifiedExperimentManager`、`visualization.OECTPlotter`、`visualization.ChipFeaturePlotter`、`features`、`experiment.Experiment`、`logger_config.get_module_logger`。这些模块的细节见各自模块的 CLAUDE.md。

**文件结构（要点）**
- `stability_report_pipeline_v2.py`：两阶段管道实现与 CLI。
- `reporting/`：组合式三阶段实现与 CLI
  - `assets.py`：资产定义/生成与清单管理
  - `slides.py`：单页幻灯片构建器与引擎
  - `reports.py`：整份报告编排器
  - `cli.py`：命令行入口（assets/slides/reports）

**两阶段管道 v2 API**
- 类 `AssetManager(base_dir)`：素材路径与枚举
  - `get_image_path(chip_id, device_id, image_type) -> Path`
  - `get_video_path(chip_id, device_id) -> Path`
  - `get_feature_path(chip_id, feature_name, variant) -> Path`
  - `list_chip_assets(chip_id) -> Dict[str, List[Path]]`
- 类 `AssetGenerator(asset_manager, config_path='catalog_config.yaml', overwrite_mode=False)`：生成素材
  - `generate_chip_assets(chip_id) -> Dict`：为 6 个 device 生成图片与视频，并生成两组特征图：`absI_max_raw`、`absgm_max_forward`（各 6 个变体）。
  - 内部依赖：`UnifiedExperimentManager.search()` 获取实验，`OECTPlotter` 生成图像/视频；`ChipFeaturePlotter.plot_chip_feature()` 生成特征图。
  - 注：特征数据目录自动探测（优先 `/mnt/d/UserData/lidonghaowsl/data/Stability_PS/features/`，否则 `data/features/`）。
- 类 `PPTComposer(asset_manager)`：从本地素材组装 PPT（16:9）
  - `create_presentation(chip_id, output_path) -> str|None`
  - 页面布局：
    - 标题页
    - 2×3 设备网格：`transient_all`、`transfer_evolution_linear`、`transfer_evolution_log`
    - 2×3 视频网格：transfer 演化视频
    - 2×3 设备网格：`transient_early`（Step 1，t=5–6s）、`transient_late`（Step 1000，t=5–6s）
    - 特征矩阵：`absI_max_raw`、`absgm_max_forward`（各 6 变体）
- 类 `StabilityReportPipelineV2(output_dir='reports', assets_dir=None, config_path='catalog_config.yaml', overwrite_mode=False)`
  - `generate_chip_report(chip_id, skip_asset_generation=False) -> str|None`
  - `generate_all_chip_reports(skip_asset_generation=False) -> List[str]`
- CLI（脚本内）：
  - 单芯片：`python stability_report_pipeline_v2.py --chip "#2025..." [--output <path>] [--skip-assets] [--overwrite] [--assets-dir <dir>] [--config <yaml>] [--verbose]`
  - 全芯片：`python stability_report_pipeline_v2.py --all-chips --output-dir <dir> [--overwrite] [--config <yaml>]`

**组合式三阶段 reporting API**
- 资产定义与生成（`reporting/assets.py`）
  - 数据类：`AssetDefinition`、`AssetRecord`、`AssetManifest`；持久化：`ManifestStore`
  - 注册表：`AssetRegistry`（注册生成器）；上下文：`GenerationContext`
  - 类 `AssetGenerator(assets_dir, config_path, config_profile=None, registry=None, compute_sha1=False, overwrite=False, catalog_config=None)`
    - `generate_for_chip(chip_id) -> AssetManifest`：根据 YAML 生成资产并保存 `manifests/manifest_<chip>.json`
    - 支持 scope：`per_chip`、`per_device`、`feature_variants`
    - 默认生成器（已注册）：
      - `plotter_image`：调用 `OECTPlotter.<method>` 返回 `matplotlib` 图并保存
      - `plotter_video`：调用 `OECTPlotter.create_transfer_video_parallel`（或指定 `method`）
      - `feature_plot`：调用 `ChipFeaturePlotter.plot_chip_feature`
- 幻灯片构建（`reporting/slides.py`）
  - 数据类：`SlideDefinition`；注册表：`SlideRegistry`；基类：`SlideBuilder`
  - 预置构建器：
    - `image_grid`：设备图片 2×3 网格（可配置列数/标题/说明文字）
    - `video_grid`：设备视频 2×3 网格（插入 mp4）
    - `feature_matrix`：特征变体矩阵（如 6 种变体）
  - 引擎 `SlideEngine(assets_dir, slides_dir, config_path, registry=None)`
    - `build(slide_ids=None, chips=None) -> List[Path]`；`build_all()`
    - 输出：`<slides_dir>/<slide_id>/<chip>.pptx`，并写入同名 `.json` 元数据
- 报告编排（`reporting/reports.py`）
  - 数据类：`ReportSlide`、`ReportDefinition`
  - 类 `ReportComposer(assets_dir, slides_config_path, reports_config_path, output_dir, registry=None)`
    - `compose(report_id, output_path=None) -> Path`：按报告定义顺序渲染并保存整份 PPTX
    - `list_reports() -> List[str]`
- CLI（`python -m stability_report.reporting.cli`）
  - 资产生成：`assets generate --assets-config <yaml> --catalog-config <yaml> --assets-dir <dir> [--chips <...>] [--overwrite] [--sha1]`
  - 幻灯片生成：`slides build --slides-config <yaml> --assets-dir <dir> --slides-dir <dir> [--slide-ids <...>] [--chips <...>]`
  - 报告编排：`reports compose <report_id> --assets-dir <dir> --slides-config <yaml> --reports-config <yaml> --output-dir <dir> [--output <path>]`

**配置要点（YAML）**
- 资产（`configs/assets.yaml`）
  - 字段：`id`、`scope`、`generator`、`output`、`params`
  - 常用 `generator`：`plotter_image`（需 `method` 与可选 `method_params`）、`plotter_video`、`feature_plot`
  - 变量：`{chip_id}`、`{chip_safe}`、`{device_id}`、`{variant}` 可用于 `output/filename`
- 幻灯片（`configs/slides.yaml`）
  - 字段：`id`、`builder`、`params`、`scope`
  - 预置 `builder`：`image_grid`、`video_grid`、`feature_matrix`
- 报告（`configs/reports.yaml`）
  - `reports[].slides[].chips` 支持 `"*"`、单个 chip、列表（`"*"` 会展开为全部已存在清单的 chip）

**输入/输出约定**
- v2 默认输出目录：`reports/`（文件名 `stability_report_<chip>.pptx`）；素材默认在 `output_dir/assets/`。
- reporting 默认结构（由配置决定）：
  - 图片：`images/{chip_safe}/device_{device_id}/...png`
  - 视频：`videos/{chip_safe}/device_{device_id}/...mp4`
  - 特征：`features/{chip_safe}/<feature>_<variant>.png`
  - 清单：`assets_dir/manifests/manifest_<chip>.json`
  - 单页幻灯片：`slides_dir/<slide_id>/<chip>.pptx`
  - 整体报告：`output_dir/<report_id>.pptx`

**注意**
- 覆盖策略：v2 与 reporting 均支持“跳过已存在”与“覆盖”模式（分别由 `overwrite_mode` 或 `--overwrite` 控制）。
- 尺寸：PPT 为 16:9（13.33" × 7.5"）。
- 依赖模块的实现/数据来源、图表绘制细节均在对应模块中，详见其 CLAUDE.md。

# Stability Reporting Pipeline (Composable)

New three-stage workflow for generating stability reports:

1. **Assets** – render reusable figures, videos, and feature plots to the filesystem.
2. **Slides** – assemble single-slide PPTX pages from manifests.
3. **Reports** – compose full decks by sequencing slide definitions.

## Quick start

```bash
python -m stability_report.reporting.cli assets generate \
  --assets-config configs/assets.yaml \
  --catalog-config catalog_config.yaml \
  --assets-dir /home/lidonghaowsl/develop_win/hdd/data/Stability_PS20250929/build/assets \
  # --chips "#20250804008" "#20250804009"

python -m stability_report.reporting.cli slides build \
  --slides-config configs/slides.yaml \
  --assets-dir /home/lidonghaowsl/develop_win/hdd/data/Stability_PS20250929/build/assets \
  --slides-dir /home/lidonghaowsl/develop_win/hdd/data/Stability_PS20250929/build/slides

python -m stability_report.reporting.cli reports compose chip_overview \
  --assets-dir /home/lidonghaowsl/develop_win/hdd/data/Stability_PS20250929/build/assets \
  --slides-config configs/slides.yaml \
  --reports-config configs/reports.yaml \
  --output-dir /home/lidonghaowsl/develop_win/hdd/data/Stability_PS20250929/build/reports
```

Update the YAML files in `configs/` to add new asset generators, slide layouts, or report playlists. Slides and reports are purely declarative—add new entries without touching code by reusing the registered builders and generators.
