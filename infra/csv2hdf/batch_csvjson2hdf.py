# batch_csvjson2hdf.py
from __future__ import annotations
import os, re, json, sys, traceback

########################### 日志设置 ################################
from ..logger_config import get_module_logger
logger = get_module_logger()
#####################################################################
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple, Union
from concurrent.futures import ProcessPoolExecutor, as_completed
from enum import Enum

# 新的直接转换模块
try:
    from .direct_csv2hdf import direct_csv_to_new_hdf5
except ImportError:
    # 当作为独立脚本运行时的备用导入
    from infra.csv2hdf.direct_csv2hdf import direct_csv_to_new_hdf5

# =========================
# 数据结构
# =========================
class ConflictStrategy(Enum):
    """处理文件名冲突的策略"""
    OVERWRITE = "overwrite"    # 覆盖已存在的文件
    SKIP = "skip"             # 跳过已存在的文件
    RENAME = "rename"         # 重命名为唯一文件名 (添加 _2, _3, ...)

@dataclass
class JobResult:
    folder: str
    h5_path: Optional[str]
    ok: bool
    message: str
    steps: Optional[int] = None
    csv_written: Optional[int] = None
    workflow_stored: Optional[bool] = None
    skipped: bool = False  # 新增：标记是否因文件已存在而跳过

# =========================
# 工具函数
# =========================
def _ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)

def _find_json(folder: str, json_name: str = "test_info.json") -> str:
    """
    在 folder 里查找 JSON。优先固定文件名；否则若唯一 *.json 则使用之。
    """
    candidate = os.path.join(folder, json_name)
    if os.path.isfile(candidate):
        return candidate
    jsons = [f for f in os.listdir(folder) if f.lower().endswith(".json")]
    if len(jsons) == 1:
        return os.path.join(folder, jsons[0])
    raise FileNotFoundError(f"No JSON found in {folder} (expected '{json_name}' or unique *.json).")

def _read_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _find_workflow_json(folder: str) -> str:
    """
    在 folder 里查找 workflow.json 文件
    """
    workflow_path = os.path.join(folder, "workflow.json")
    if os.path.isfile(workflow_path):
        return workflow_path
    raise FileNotFoundError(f"No workflow.json found in {folder}")

def _store_workflow_to_h5(h5_path: str, workflow_path: str):
    """
    将 workflow.json 存储到 HDF5 文件的 raw/workflow 中
    """
    import h5py
    try:
        workflow_data = _read_json(workflow_path)
        with h5py.File(h5_path, "a") as h5:
            raw_group = h5.require_group("raw")
            # 存储workflow.json的内容
            def write_json_string_dataset(group, name, data):
                """Simple helper to write JSON data as string dataset"""
                import h5py
                import json
                json_str = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
                dt = h5py.string_dtype(encoding="utf-8", length=None)
                group.create_dataset(name, data=json_str, dtype=dt)
            
            write_json_string_dataset(raw_group, "workflow", workflow_data)
        return True
    except Exception:
        return False

def _sanitize_filename_part(s: str, default: str = "NA", max_len: int = 120) -> str:
    """
    替换非法字符、去首尾空白、裁剪长度，避免生成非法或过长的文件名部件。
    """
    if s is None:
        return default
    s = str(s).strip()
    if not s:
        return default
    s = re.sub(r'[\\/:*?"<>|\r\n\t]', "_", s)
    s = re.sub(r"\s+", " ", s)  # 压缩连续空白
    if len(s) > max_len:
        s = s[:max_len].rstrip()
    return s
def _build_h5_basename_from_json(json_obj: dict) -> Tuple[str, Tuple[str, str, str, str]]:
    """
    从清理后的JSON中读取四个字段构建文件名：
      chip_id-device_number-description-test_id.h5
    字段直接从根级别读取，若字段缺失或为空则用 "NA" 替代。
    """
    def get_field(name: str) -> str:
        # 直接从根级别读取字段（JSON已经扁平化）
        val = json_obj.get(name) or "NA"
        return _sanitize_filename_part(val)

    chip_id       = get_field("chip_id")
    device_number = get_field("device_number")
    description   = get_field("description")
    test_id       = get_field("test_id")

    return f"{chip_id}-{device_number}-{description}-{test_id}.h5", (chip_id, device_number, description, test_id)


def _unique_path(path: str) -> str:
    """
    若 path 已存在，则追加 _2/_3/... 保持唯一。
    """
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    i = 2
    while True:
        cand = f"{stem}_{i}{ext}"
        if not os.path.exists(cand):
            return cand
        i += 1

def _count_steps(json_path: str) -> int:
    try:
        obj = _read_json(json_path)
        steps = obj.get("steps", [])
        return len(steps) if isinstance(steps, list) else 0
    except Exception:
        return 0

def _annotate_provenance(h5_path: str,
                         src_folder: str,
                         json_path: str,
                         fields: Tuple[str, str, str, str],
                         output_filename: str):
    """
    向 HDF5 顶层写入溯源属性 + 四个关键字段 + 输出文件名。
    """
    import h5py
    from datetime import datetime, timezone
    chip_id, device_number, description, test_id = fields
    with h5py.File(h5_path, "a") as h5:
        h5.attrs["source_folder_name"] = os.path.basename(os.path.abspath(src_folder))
        h5.attrs["source_folder_path"] = os.path.abspath(src_folder)
        h5.attrs["source_json_name"]   = os.path.basename(json_path)
        h5.attrs["export_time_utc"]    = datetime.now(timezone.utc).isoformat()

        # 关键字段写入，便于自描述/索引
        h5.attrs["chip_id"]        = chip_id
        h5.attrs["device_number"]  = device_number
        h5.attrs["description"]    = description
        h5.attrs["test_id"]        = test_id

        # 记录最终输出文件名（便于校验）
        h5.attrs["output_filename"] = output_filename

# =========================
# 单目录任务
# =========================
def _process_one_folder(folder: str,
                        out_dir: str,
                        json_name: str = "test_info.json",
                        conflict_strategy: Union[ConflictStrategy, str] = ConflictStrategy.OVERWRITE) -> JobResult:
    try:
        folder = os.path.abspath(folder)
        if not os.path.isdir(folder):
            return JobResult(folder, None, False, "Not a directory")
        
        # 转换字符串为枚举
        if isinstance(conflict_strategy, str):
            try:
                conflict_strategy = ConflictStrategy(conflict_strategy.lower())
            except ValueError:
                return JobResult(folder, None, False, f"Invalid conflict strategy: {conflict_strategy}")

        json_path = _find_json(folder, json_name=json_name)
        meta = _read_json(json_path)
        basename, fields = _build_h5_basename_from_json(meta)

        _ensure_dir(out_dir)
        h5_path = os.path.join(out_dir, basename)
        
        # 处理文件冲突策略
        if os.path.exists(h5_path):
            if conflict_strategy == ConflictStrategy.SKIP:
                return JobResult(
                    folder=folder,
                    h5_path=h5_path,
                    ok=True,
                    message="Skipped (file exists)",
                    skipped=True
                )
            elif conflict_strategy == ConflictStrategy.RENAME:
                h5_path = _unique_path(h5_path)
            # ConflictStrategy.OVERWRITE: 继续执行，覆盖文件

        # 直接从CSV和JSON生成新格式HDF5
        direct_csv_to_new_hdf5(json_path, folder, h5_path)
        step_count = _count_steps(json_path)
        
        # 添加溯源信息
        _annotate_provenance(h5_path, folder, json_path, fields, basename)
        
        # 存储 workflow.json（如果存在）
        workflow_stored = False
        try:
            workflow_path = _find_workflow_json(folder)
            workflow_stored = _store_workflow_to_h5(h5_path, workflow_path)
        except FileNotFoundError:
            # workflow.json 不存在，不是错误
            pass

        return JobResult(
            folder=folder,
            h5_path=h5_path,
            ok=True,
            message="OK (Direct New Format)",
            steps=step_count,
            csv_written=None,  # 不再适用于新格式
            workflow_stored=workflow_stored
        )
    except Exception as e:
        return JobResult(
            folder=folder,
            h5_path=None,
            ok=False,
            message=f"{e.__class__.__name__}: {e}\n{traceback.format_exc()}",
            steps=None,
            csv_written=None,
            workflow_stored=None
        )

# =========================
# 进度显示（tqdm 可选）
# =========================
class _Progress:
    def __init__(self, total: int, enabled: bool = True, desc: str = "Folders"):
        self.total = total
        self.enabled = bool(enabled)
        self._use_tqdm = False
        self._count = 0
        if self.enabled:
            try:
                from tqdm import tqdm  # type: ignore
                self._use_tqdm = True
                self._bar = tqdm(total=total, desc=desc, unit="folder")
            except Exception:
                self._bar = None
                sys.stdout.write("\r[0/%d]   0.00%%" % total)
                sys.stdout.flush()
        else:
            self._bar = None

    def update(self, n: int = 1, info: Optional[str] = None):
        if not self.enabled:
            return
        if self._use_tqdm:
            if info:
                self._bar.set_postfix_str(info[:60], refresh=False)
            self._bar.update(n)
        else:
            self._count += n
            pct = (self._count / self.total * 100) if self.total else 100.0
            msg = f"\r[{self._count}/{self.total}] {pct:6.2f}%"
            if info:
                msg += f" | {info[:60]}"
            sys.stdout.write(msg)
            sys.stdout.flush()

    def close(self):
        if self._use_tqdm and self._bar is not None:
            self._bar.close()
        elif self.enabled:
            sys.stdout.write("\n"); sys.stdout.flush()

# =========================
# 并行主函数
# =========================
def process_folders_parallel(
    folders: Iterable[str],
    out_dir: str,
    num_workers: Optional[int] = None,
    json_name: str = "test_info.json",
    conflict_strategy: Union[ConflictStrategy, str] = ConflictStrategy.OVERWRITE,
    show_progress: bool = True,
) -> List[JobResult]:
    """并行处理多个目录，将JSON+CSV转换为HDF5格式。

    Args:
        folders: 源目录列表，每个目录包含test_info.json和CSV文件
        out_dir: 输出HDF5文件的目录
        num_workers: 工作进程数量，默认为CPU核心数
        json_name: JSON文件名，默认为"test_info.json"  
        conflict_strategy: 处理文件名冲突的策略，支持字符串或枚举：
            - "overwrite" (默认): 覆盖已存在的文件
            - "skip": 跳过已存在的文件
            - "rename": 重命名为唯一文件名(添加_2,_3,...)
        show_progress: 是否显示进度条

    Returns:
        List[JobResult]: 处理结果列表

    Examples:
        >>> # 使用字符串参数 (推荐)
        >>> process_folders_parallel(folders, "output/", conflict_strategy="skip")
        >>> process_folders_parallel(folders, "output/", conflict_strategy="rename")
        
        >>> # 使用枚举
        >>> from csv2hdf.batch_csvjson2hdf import ConflictStrategy  
        >>> process_folders_parallel(folders, "output/", conflict_strategy=ConflictStrategy.SKIP)
    """
    folders = list(dict.fromkeys(map(os.path.abspath, folders)))  # 去重并绝对化
    _ensure_dir(out_dir)
    results: List[JobResult] = []

    prog = _Progress(total=len(folders), enabled=show_progress, desc="Folders")

    with ProcessPoolExecutor(max_workers=num_workers) as ex:
        fut2folder = {
            ex.submit(_process_one_folder, folder, out_dir, json_name, conflict_strategy): folder
            for folder in folders
        }
        for fut in as_completed(fut2folder):
            res = fut.result()
            results.append(res)
            if res.ok and res.skipped:
                info = f"SKIP: {os.path.basename(res.folder)} (file exists)"
            elif res.ok:
                info = f"OK: {os.path.basename(res.folder)} (steps={res.steps}, cols={res.csv_written}, workflow={'Y' if res.workflow_stored else 'N'})"
            else:
                info = f"FAIL: {os.path.basename(res.folder)}"
            prog.update(1, info)

    prog.close()
    return results

# =========================
# CLI
# =========================
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Parallel CSV+JSON -> HDF5 exporter (custom filename & provenance).")
    parser.add_argument("folders", nargs="+", help="Source folders; each contains test_info.json and CSV files.")
    parser.add_argument("--out-dir", required=True, help="Directory to place all generated .h5 files.")
    parser.add_argument("--json-name", default="test_info.json", help="JSON filename to look for (default: test_info.json)")
    parser.add_argument("--workers", type=int, default=None, help="Number of worker processes (default: os.cpu_count())")
    parser.add_argument("--conflict", choices=["overwrite", "skip", "rename"], default="overwrite",
                        help="Strategy for handling existing files: overwrite (default), skip, or rename with suffix")
    parser.add_argument("--no-progress", action="store_true", help="Disable progress display.")
    args = parser.parse_args()

    results = process_folders_parallel(
        folders=args.folders,
        out_dir=args.out_dir,
        num_workers=args.workers,
        json_name=args.json_name,
        conflict_strategy=ConflictStrategy(args.conflict),
        show_progress=not args.no_progress,
    )
    ok_cnt = sum(r.ok for r in results)
    skip_cnt = sum(r.skipped for r in results)
    logger.info(f"\nProcessed {len(results)} folder(s); OK: {ok_cnt}, SKIP: {skip_cnt}, FAIL: {len(results)-ok_cnt}")
    for r in results:
        if r.ok and r.skipped:
            status = "SKIP"
        elif r.ok:
            status = "OK"
        else:
            status = "FAIL"
        logger.info(f"[{status}] {r.folder}")
        if r.ok and not r.skipped:
            logger.info(f"  H5: {r.h5_path}")
            logger.info(f"  steps: {r.steps}, csv_columns_written: {r.csv_written}, workflow_stored: {'Yes' if r.workflow_stored else 'No'}")
        elif r.ok and r.skipped:
            logger.info(f"  H5: {r.h5_path} (skipped, file exists)")
        else:
            logger.error(f"  Error: {r.message}")
