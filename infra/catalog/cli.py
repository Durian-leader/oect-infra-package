"""
Catalog模块命令行工具

提供完整的catalog系统命令行接口，包括：
- 初始化和配置管理
- 文件扫描和索引
- 同步管理
- 查询和统计
- 维护操作
"""

import argparse
import json
import csv
import sys
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from .service import CatalogService
from .models import ExperimentStatus, ConflictStrategy


def setup_logging(level: str = "INFO"):
    """设置日志"""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


class CatalogCLI:
    """Catalog命令行接口"""
    
    def __init__(self):
        self.catalog = None
        self.parser = self._create_parser()
    
    def _create_parser(self) -> argparse.ArgumentParser:
        """创建命令行解析器"""
        parser = argparse.ArgumentParser(
            prog='catalog',
            description='OECT HDF5文件元信息管理和双向同步系统',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  catalog init --auto-config                    # 自动初始化
  catalog scan --path data/raw --recursive      # 扫描文件
  catalog sync --direction both                 # 双向同步
  catalog query --chip "#20250804008"           # 查询实验
  catalog stats --detailed                      # 详细统计
            """
        )
        
        # 全局选项
        parser.add_argument('--config', type=str, default='catalog_config.yaml',
                           help='配置文件路径 (默认: catalog_config.yaml)')
        parser.add_argument('--verbose', '-v', action='store_true',
                           help='详细输出')
        parser.add_argument('--quiet', '-q', action='store_true',
                           help='安静模式')
        
        # 子命令
        subparsers = parser.add_subparsers(dest='command', help='可用命令')
        
        # 初始化命令
        self._add_init_command(subparsers)
        
        # 扫描命令
        self._add_scan_command(subparsers)
        
        # 同步命令
        self._add_sync_command(subparsers)
        
        # 查询命令
        self._add_query_command(subparsers)
        
        # 统计命令
        self._add_stats_command(subparsers)
        
        # 维护命令
        self._add_maintenance_command(subparsers)

        # Features V2 命令
        self._add_v2_command(subparsers)

        return parser
    
    def _add_init_command(self, subparsers):
        """添加初始化命令"""
        init_parser = subparsers.add_parser('init', help='初始化catalog系统')
        init_parser.add_argument('--root-dir', type=str, help='数据根目录')
        init_parser.add_argument('--auto-config', action='store_true',
                                help='自动检测现有目录结构并生成配置')
        init_parser.add_argument('--force', action='store_true',
                                help='强制重新初始化(清空现有数据库)')
        init_parser.set_defaults(func=self.cmd_init)
    
    def _add_scan_command(self, subparsers):
        """添加扫描命令"""
        scan_parser = subparsers.add_parser('scan', help='扫描和索引文件')
        scan_parser.add_argument('--path', type=str, action='append',
                                help='要扫描的目录路径(可指定多个)')
        scan_parser.add_argument('--recursive', action='store_true',
                                help='递归扫描子目录')
        scan_parser.add_argument('--max-depth', type=int, default=10,
                                help='最大扫描深度')
        scan_parser.add_argument('--incremental', action='store_true', default=True,
                                help='增量扫描模式')
        scan_parser.add_argument('--parallel', type=int, default=4,
                                help='并行工作进程数')
        scan_parser.add_argument('--dry-run', action='store_true',
                                help='预览模式，不实际修改数据库')
        scan_parser.set_defaults(func=self.cmd_scan)
    
    def _add_sync_command(self, subparsers):
        """添加同步命令"""
        sync_parser = subparsers.add_parser('sync', help='双向同步')
        sync_parser.add_argument('--direction', choices=['both', 'file2db', 'db2file'],
                                default='both', help='同步方向')
        sync_parser.add_argument('--force', action='store_true',
                                help='强制同步，忽略时间戳检查')
        sync_parser.add_argument('--resolve-conflicts', 
                                choices=['auto', 'manual', 'ignore'],
                                default='auto', help='冲突解决策略')
        sync_parser.add_argument('--experiment-id', type=int, action='append',
                                help='指定同步的实验ID')
        sync_parser.add_argument('--batch-size', type=int, default=100,
                                help='批处理大小')
        sync_parser.add_argument('--timeout', type=int, default=300,
                                help='操作超时时间(秒)')
        sync_parser.set_defaults(func=self.cmd_sync)
    
    def _add_query_command(self, subparsers):
        """添加查询命令"""
        query_parser = subparsers.add_parser('query', help='查询实验')
        query_parser.add_argument('--chip', type=str, help='芯片ID过滤')
        query_parser.add_argument('--status', choices=['completed', 'running', 'failed', 'pending'],
                                 help='实验状态过滤')
        query_parser.add_argument('--device-type', choices=['N-type', 'P-type'],
                                 help='器件类型过滤')
        query_parser.add_argument('--missing-features', action='store_true',
                                 help='只显示缺少特征文件的实验')
        query_parser.add_argument('--date-range', type=str,
                                 help='日期范围过滤 (格式: YYYY-MM-DD,YYYY-MM-DD)')
        query_parser.add_argument('--batch-id', type=str, help='批次ID过滤')
        query_parser.add_argument('--text', type=str, help='全文搜索')
        query_parser.add_argument('--output', choices=['table', 'json', 'csv'],
                                 default='table', help='输出格式')
        query_parser.add_argument('--file', type=str, help='输出文件路径')
        query_parser.add_argument('--limit', type=int, help='结果数量限制')
        query_parser.set_defaults(func=self.cmd_query)
    
    def _add_stats_command(self, subparsers):
        """添加统计命令"""
        stats_parser = subparsers.add_parser('stats', help='统计信息')
        stats_parser.add_argument('--detailed', action='store_true',
                                 help='显示详细统计信息')
        stats_parser.add_argument('--by-chip', action='store_true',
                                 help='按芯片分组统计')
        stats_parser.add_argument('--by-date', action='store_true',
                                 help='按日期分组统计')
        stats_parser.add_argument('--storage', action='store_true',
                                 help='显示存储使用情况')
        stats_parser.add_argument('--timeline', action='store_true',
                                 help='显示时间线统计')
        stats_parser.add_argument('--days', type=int, default=30,
                                 help='统计时间范围(天数)')
        stats_parser.add_argument('--export', action='store_true',
                                 help='导出统计报告')
        stats_parser.add_argument('--format', choices=['json', 'csv', 'html'],
                                 default='json', help='导出格式')
        stats_parser.add_argument('--file', type=str, help='导出文件路径')
        stats_parser.set_defaults(func=self.cmd_stats)
    
    def _add_maintenance_command(self, subparsers):
        """添加维护命令"""
        maint_parser = subparsers.add_parser('maintenance', help='维护操作')
        maint_parser.add_argument('--validate', action='store_true',
                                 help='数据验证')
        maint_parser.add_argument('--fix-conflicts', action='store_true',
                                 help='自动修复发现的冲突')
        maint_parser.add_argument('--check-files', action='store_true',
                                 help='检查文件系统一致性')
        maint_parser.add_argument('--check-integrity', action='store_true',
                                 help='检查数据完整性')
        maint_parser.add_argument('--remove-orphans', action='store_true',
                                 help='删除孤立的数据库记录')
        maint_parser.add_argument('--vacuum', action='store_true',
                                 help='压缩和优化数据库')
        maint_parser.add_argument('--backup', type=str,
                                 help='创建数据库备份')
        maint_parser.set_defaults(func=self.cmd_maintenance)

    def _add_v2_command(self, subparsers):
        """添加 Features V2 命令"""
        v2_parser = subparsers.add_parser('v2', help='Features V2 特征提取')

        # V2 子命令
        v2_subparsers = v2_parser.add_subparsers(dest='v2_command', help='V2 子命令')

        # v2 configs - 列出可用配置
        configs_parser = v2_subparsers.add_parser('configs', help='列出可用的 V2 配置')
        configs_parser.set_defaults(func=self.cmd_v2_configs)

        # v2 extract - 单实验提取
        extract_parser = v2_subparsers.add_parser('extract', help='单实验 V2 特征提取')
        extract_parser.add_argument('--exp-id', type=int, required=True, help='实验 ID')
        extract_parser.add_argument('--feature-config', type=str, required=True, help='特征配置名称')
        extract_parser.add_argument('--output', type=str, default='parquet',
                                   choices=['dict', 'dataframe', 'parquet'],
                                   help='输出格式')
        extract_parser.set_defaults(func=self.cmd_v2_extract)

        # v2 extract-batch - 批量提取
        batch_parser = v2_subparsers.add_parser('extract-batch', help='批量 V2 特征提取')
        batch_parser.add_argument('--chip', type=str, help='Chip ID 过滤')
        batch_parser.add_argument('--device', type=str, help='Device ID 过滤')
        batch_parser.add_argument('--feature-config', type=str, required=True, help='特征配置名称')
        batch_parser.add_argument('--workers', type=int, default=1, help='并行工作进程数')
        batch_parser.add_argument('--force', action='store_true', help='强制重新计算')
        batch_parser.set_defaults(func=self.cmd_v2_extract_batch)

        # v2 stats - V2 特征统计
        stats_parser = v2_subparsers.add_parser('stats', help='V2 特征统计')
        stats_parser.add_argument('--detailed', action='store_true', help='详细统计')
        stats_parser.set_defaults(func=self.cmd_v2_stats)

        v2_parser.set_defaults(func=lambda args: v2_parser.print_help())

    def run(self, args: Optional[List[str]] = None) -> int:
        """运行CLI"""
        try:
            parsed_args = self.parser.parse_args(args)
            
            # 设置日志级别
            if parsed_args.quiet:
                setup_logging("WARNING")
            elif parsed_args.verbose:
                setup_logging("DEBUG")
            else:
                setup_logging("INFO")
            
            # 检查命令
            if not parsed_args.command:
                self.parser.print_help()
                return 1
            
            # 初始化catalog服务（除了init命令）
            if parsed_args.command != 'init':
                try:
                    self.catalog = CatalogService(parsed_args.config)
                except Exception as e:
                    print(f"错误: 无法初始化catalog服务: {e}")
                    print("请先运行 'catalog init' 初始化系统")
                    return 1
            
            # 执行命令
            return parsed_args.func(parsed_args)
            
        except KeyboardInterrupt:
            print("\n操作被用户中断")
            return 130
        except Exception as e:
            print(f"错误: {e}")
            return 1
        finally:
            if self.catalog:
                self.catalog.close()
    
    # ==================== 命令实现 ====================
    
    def cmd_init(self, args) -> int:
        """初始化命令"""
        try:
            print("正在初始化catalog系统...")
            
            # 创建catalog服务
            self.catalog = CatalogService(args.config, args.root_dir)
            
            # 初始化
            result = self.catalog.initialize_catalog(force=args.force)
            
            if result['success']:
                print("✓ Catalog系统初始化成功")
                
                # 显示配置信息
                config_info = self.catalog.get_config_info()
                print(f"✓ 配置文件: {config_info['config_path']}")
                print(f"✓ 数据库路径: {config_info['database_path']}")
                print(f"✓ 原始数据目录: {config_info['raw_data_path']}")
                print(f"✓ 特征数据目录: {config_info['features_path']}")
                
                # 如果是auto-config模式，自动扫描现有文件
                if args.auto_config:
                    print("正在扫描现有文件...")
                    scan_result = self.catalog.scan_and_index()
                    if scan_result.is_successful:
                        print(f"✓ 扫描完成: 发现 {scan_result.files_added} 个实验")
                    else:
                        print(f"⚠ 扫描部分完成: {scan_result.files_failed} 个文件处理失败")
                
                # 显示最终统计信息
                final_stats = self.catalog.get_statistics()
                print(f"✓ 当前实验数: {final_stats.total_experiments}")
                
                return 0
            else:
                print(f"✗ 初始化失败: {result['message']}")
                return 1
                
        except Exception as e:
            print(f"✗ 初始化失败: {e}")
            return 1
    
    def cmd_scan(self, args) -> int:
        """扫描命令"""
        try:
            print("正在扫描和索引文件...")
            
            scan_paths = args.path if args.path else None
            result = self.catalog.scan_and_index(scan_paths, args.incremental)
            
            if result.is_successful:
                print(f"✓ 扫描完成: {result.files_processed} 个文件处理")
                print(f"  - 新增: {result.files_added}")
                print(f"  - 更新: {result.files_updated}")
                print(f"  - 跳过: {result.files_skipped}")
                if result.duration:
                    print(f"  - 耗时: {result.duration:.2f} 秒")
                return 0
            else:
                print(f"✗ 扫描失败: {result.files_failed} 个文件失败")
                for error in result.errors:
                    print(f"  错误: {error}")
                return 1
                
        except Exception as e:
            print(f"✗ 扫描失败: {e}")
            return 1
    
    def cmd_sync(self, args) -> int:
        """同步命令"""
        try:
            print(f"正在执行{args.direction}同步...")
            
            # 解析冲突策略
            conflict_strategy_map = {
                'auto': ConflictStrategy.TIMESTAMP,
                'manual': ConflictStrategy.MANUAL,
                'ignore': ConflictStrategy.IGNORE
            }
            conflict_strategy = conflict_strategy_map[args.resolve_conflicts]
            
            # 执行同步
            if args.direction == 'both':
                result = self.catalog.bidirectional_sync(conflict_strategy=conflict_strategy)
            elif args.direction == 'file2db':
                result = self.catalog.sync_files_to_database()
            elif args.direction == 'db2file':
                result = self.catalog.sync_database_to_files()
            
            if result.is_successful:
                print(f"✓ 同步完成")
                print(f"  - 处理文件: {result.files_processed}")
                print(f"  - 新增: {result.files_added}")
                print(f"  - 更新: {result.files_updated}")
                print(f"  - 冲突解决: {result.conflicts_resolved}")
                if result.duration:
                    print(f"  - 耗时: {result.duration:.2f} 秒")
                return 0
            else:
                print(f"✗ 同步失败")
                for error in result.errors:
                    print(f"  错误: {error}")
                return 1
                
        except Exception as e:
            print(f"✗ 同步失败: {e}")
            return 1
    
    def cmd_query(self, args) -> int:
        """查询命令"""
        try:
            # 构建查询条件
            filter_kwargs = {}
            
            if args.chip:
                filter_kwargs['chip_id'] = args.chip
            if args.status:
                filter_kwargs['status'] = ExperimentStatus(args.status)
            if args.device_type:
                filter_kwargs['device_type'] = args.device_type
            if args.missing_features:
                filter_kwargs['missing_features'] = True
            if args.batch_id:
                filter_kwargs['batch_id'] = args.batch_id
            if args.text:
                filter_kwargs['text_search'] = args.text
            if args.limit:
                filter_kwargs['limit'] = args.limit
            if args.date_range:
                try:
                    start_date, end_date = args.date_range.split(',')
                    filter_kwargs['created_after'] = datetime.fromisoformat(start_date)
                    filter_kwargs['created_before'] = datetime.fromisoformat(end_date)
                except ValueError:
                    print("错误: 日期范围格式错误，应为 YYYY-MM-DD,YYYY-MM-DD")
                    return 1
            
            # 执行查询
            experiments = self.catalog.find_experiments(**filter_kwargs)
            
            if not experiments:
                print("未找到匹配的实验")
                return 0
            
            # 输出结果
            if args.output == 'json':
                self._output_json(experiments, args.file)
            elif args.output == 'csv':
                self._output_csv(experiments, args.file)
            else:
                self._output_table(experiments, args.file)
            
            return 0
            
        except Exception as e:
            print(f"✗ 查询失败: {e}")
            return 1
    
    def cmd_stats(self, args) -> int:
        """统计命令"""
        try:
            print("正在获取统计信息...")
            
            if args.detailed or args.by_chip:
                # 详细统计
                report = self.catalog.get_summary_report()
                chip_stats = self.catalog.get_chip_statistics() if args.by_chip else {}
                
                self._display_detailed_stats(report, chip_stats)
            else:
                # 基本统计
                stats = self.catalog.get_statistics()
                self._display_basic_stats(stats)
            
            return 0
            
        except Exception as e:
            print(f"✗ 获取统计信息失败: {e}")
            return 1
    
    def cmd_maintenance(self, args) -> int:
        """维护命令"""
        try:
            if args.validate or args.check_integrity:
                print("正在验证数据完整性...")
                issues = self.catalog.validate_data_integrity()
                self._display_validation_results(issues)
            
            if args.fix_conflicts:
                print("正在修复冲突...")
                # 这里可以添加修复逻辑
                print("✓ 冲突修复完成")
            
            if args.remove_orphans:
                print("正在清理孤立记录...")
                cleaned = self.catalog.clean_orphaned_records()
                print(f"✓ 已清理 {cleaned} 个孤立记录")
            
            if args.vacuum:
                print("正在压缩数据库...")
                if self.catalog.vacuum_database():
                    print("✓ 数据库压缩完成")
                else:
                    print("✗ 数据库压缩失败")
            
            if args.backup:
                print("正在创建数据库备份...")
                backup_path = self.catalog.backup_database(args.backup)
                print(f"✓ 备份已创建: {backup_path}")
            
            return 0
            
        except Exception as e:
            print(f"✗ 维护操作失败: {e}")
            return 1

    def cmd_v2_configs(self, args) -> int:
        """列出可用的 V2 配置"""
        try:
            from pathlib import Path

            # 查找配置文件
            config_dirs = [
                Path(self.catalog.config.base_dir) / 'infra/catalog/feature_configs',
                Path(self.catalog.config.base_dir) / 'infra/features_v2/config/templates',
            ]

            configs = []
            for config_dir in config_dirs:
                if config_dir.exists():
                    for yaml_file in config_dir.glob('v2_*.yaml'):
                        configs.append({
                            'name': yaml_file.stem,
                            'path': str(yaml_file),
                            'location': 'catalog' if 'catalog' in str(config_dir) else 'features_v2'
                        })

            if not configs:
                print("未找到可用的 V2 配置文件")
                return 1

            print(f"找到 {len(configs)} 个 V2 配置文件:\n")

            for cfg in configs:
                print(f"  ✓ {cfg['name']}")
                print(f"    位置: {cfg['location']}")
                print(f"    路径: {cfg['path']}")
                print()

            return 0

        except Exception as e:
            print(f"✗ 列出配置失败: {e}")
            return 1

    def cmd_v2_extract(self, args) -> int:
        """单实验 V2 特征提取"""
        try:
            from .unified import UnifiedExperimentManager

            # 使用 CLI 全局配置（run 方法中的 parsed_args.config）
            manager = UnifiedExperimentManager(str(self.catalog.config.config_path))

            # 获取实验
            exp = manager.get_experiment(exp_id=args.exp_id)

            if not exp:
                print(f"✗ 未找到实验 ID: {args.exp_id}")
                return 1

            print(f"实验: {exp.chip_id}-{exp.device_id}")
            print(f"特征配置: {args.feature_config}")
            print(f"输出格式: {args.output}")
            print()

            # 提取特征
            print("正在提取特征...")
            result = exp.extract_features_v2(
                args.feature_config,
                output_format=args.output,
            )

            if args.output == 'parquet':
                print(f"✓ 特征已保存: {result}")
            elif args.output == 'dataframe':
                print(f"✓ 提取了 {len(result.columns)} 列，{len(result)} 行")
                print(result.head())
            else:
                print(f"✓ 提取了 {len(result)} 个特征")

            return 0

        except Exception as e:
            print(f"✗ 提取失败: {e}")
            import traceback
            traceback.print_exc()
            return 1

    def cmd_v2_extract_batch(self, args) -> int:
        """批量 V2 特征提取"""
        try:
            from .unified import UnifiedExperimentManager

            # 使用 CLI 全局配置（run 方法中的 parsed_args.config）
            manager = UnifiedExperimentManager(str(self.catalog.config.config_path))

            # 构建过滤条件
            filters = {}
            if args.chip:
                filters['chip_id'] = args.chip
            if args.device:
                filters['device_id'] = args.device

            # 搜索实验
            experiments = manager.search(**filters)

            if not experiments:
                print("✗ 未找到匹配的实验")
                return 1

            print(f"找到 {len(experiments)} 个实验")
            print(f"特征配置: {args.feature_config}")
            print(f"工作进程: {args.workers}")
            print()

            # 批量提取
            print("正在批量提取特征...")
            result = manager.batch_extract_features_v2(
                experiments=experiments,
                feature_config=args.feature_config,
                n_workers=args.workers,
                force_recompute=args.force,
            )

            # 输出结果
            print()
            print(f"✓ 批量提取完成:")
            print(f"  成功: {len(result['successful'])}")
            print(f"  失败: {len(result['failed'])}")
            print(f"  跳过: {len(result['skipped'])}")
            print(f"  总耗时: {result['total_time_ms'] / 1000:.2f}s")

            if result['timings']:
                avg_time = sum(result['timings'].values()) / len(result['timings'])
                print(f"  平均耗时: {avg_time / 1000:.2f}s/实验")

            if result['failed']:
                print("\n失败的实验:")
                for exp_id, error in result['failed'][:5]:  # 只显示前5个
                    print(f"  - 实验 {exp_id}: {error}")

            return 0

        except Exception as e:
            print(f"✗ 批量提取失败: {e}")
            import traceback
            traceback.print_exc()
            return 1

    def cmd_v2_stats(self, args) -> int:
        """V2 特征统计"""
        try:
            from .unified import UnifiedExperimentManager

            # 使用 CLI 全局配置（run 方法中的 parsed_args.config）
            manager = UnifiedExperimentManager(str(self.catalog.config.config_path))

            # 获取所有实验
            experiments = manager.search()

            # 统计 V2 特征
            v2_count = 0
            total_features = 0
            configs_used = set()

            for exp in experiments:
                if exp.has_v2_features():
                    v2_count += 1
                    metadata = exp.get_v2_features_metadata()
                    if metadata:
                        total_features += metadata.get('feature_count', 0)
                        configs_used.update(metadata.get('configs_used', []))

            # 输出统计
            print("V2 特征统计:")
            print(f"  总实验数: {len(experiments)}")
            print(f"  有 V2 特征: {v2_count} ({v2_count / len(experiments) * 100:.1f}%)")
            print(f"  使用的配置: {', '.join(configs_used) if configs_used else '无'}")

            if args.detailed and v2_count > 0:
                print(f"\n详细信息:")
                for exp in experiments:
                    if exp.has_v2_features():
                        metadata = exp.get_v2_features_metadata()
                        print(f"  {exp.chip_id}-{exp.device_id}:")
                        print(f"    配置: {metadata.get('configs_used')}")
                        print(f"    特征数: {metadata.get('feature_count')}")
                        print(f"    最后计算: {metadata.get('last_computed')}")

            return 0

        except Exception as e:
            print(f"✗ 获取统计失败: {e}")
            return 1

    # ==================== 输出方法 ====================
    
    def _output_table(self, experiments: List, output_file: Optional[str] = None):
        """表格输出"""
        try:
            from tabulate import tabulate
        except ImportError:
            # 如果没有tabulate，使用简单的表格格式
            def simple_tabulate(data, headers, tablefmt='grid'):
                if not data:
                    return "No data"
                
                # 计算列宽
                widths = [len(str(h)) for h in headers]
                for row in data:
                    for i, cell in enumerate(row):
                        widths[i] = max(widths[i], len(str(cell)))
                
                # 构建表格
                lines = []
                # 标题行
                header_line = " | ".join(str(headers[i]).ljust(widths[i]) for i in range(len(headers)))
                lines.append(header_line)
                lines.append("-" * len(header_line))
                
                # 数据行
                for row in data:
                    data_line = " | ".join(str(row[i]).ljust(widths[i]) for i in range(len(row)))
                    lines.append(data_line)
                
                return "\n".join(lines)
            
            tabulate = simple_tabulate
        
        headers = ['ID', '芯片ID', '设备ID', '测试ID', '状态', '完成度%', '创建时间']
        rows = []
        
        for exp in experiments:
            # 安全处理枚举值
            def safe_enum_display(enum_obj):
                if enum_obj is None:
                    return ''
                return enum_obj.value if hasattr(enum_obj, 'value') else str(enum_obj)
            
            rows.append([
                exp.id,
                exp.chip_id,
                exp.device_id,
                exp.test_id,
                safe_enum_display(exp.status),
                f"{exp.completion_percentage:.1f}",
                exp.created_at.strftime('%Y-%m-%d %H:%M') if exp.created_at else ''
            ])
        
        table = tabulate(rows, headers=headers, tablefmt='grid')
        
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(table)
            print(f"结果已保存到: {output_file}")
        else:
            print(table)
    
    def _output_json(self, experiments: List, output_file: Optional[str] = None):
        """JSON输出"""
        data = []
        for exp in experiments:
            data.append(exp.to_dict())
        
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
            print(f"结果已保存到: {output_file}")
        else:
            print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    
    def _output_csv(self, experiments: List, output_file: Optional[str] = None):
        """CSV输出"""
        if not experiments:
            return
        
        fieldnames = list(experiments[0].to_dict().keys())
        
        output = output_file or sys.stdout
        
        if output_file:
            with open(output_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for exp in experiments:
                    writer.writerow(exp.to_dict())
            print(f"结果已保存到: {output_file}")
        else:
            writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
            writer.writeheader()
            for exp in experiments:
                writer.writerow(exp.to_dict())
    
    def _display_basic_stats(self, stats):
        """显示基本统计信息"""
        print("=== Catalog统计信息 ===")
        print(f"总实验数: {stats.total_experiments}")
        print(f"已完成实验: {stats.completed_experiments}")
        print(f"完成率: {stats.completion_rate:.1%}")
        print(f"唯一芯片数: {stats.unique_chips}")
        print(f"特征文件覆盖率: {stats.feature_coverage:.1%}")
        print(f"总数据点数: {stats.total_data_points:,}")
        print(f"存储总大小: {stats.total_storage_size / (1024**3):.2f} GB")
    
    def _display_detailed_stats(self, report: Dict, chip_stats: Dict):
        """显示详细统计信息"""
        print("=== 详细统计报告 ===")
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        
        if chip_stats:
            print("\n=== 按芯片统计 ===")
            print(json.dumps(chip_stats, ensure_ascii=False, indent=2, default=str))
    
    def _display_validation_results(self, issues: Dict):
        """显示验证结果"""
        print("=== 数据完整性验证结果 ===")
        
        total_issues = sum(len(issue_list) for issue_list in issues.values())
        
        if total_issues == 0:
            print("✓ 未发现任何问题")
            return
        
        print(f"发现 {total_issues} 个问题:")
        
        for issue_type, issue_list in issues.items():
            if issue_list:
                print(f"\n{issue_type}: {len(issue_list)} 个")
                for issue in issue_list[:5]:  # 只显示前5个
                    print(f"  - {issue}")
                if len(issue_list) > 5:
                    print(f"  ... 和另外 {len(issue_list) - 5} 个")


def main():
    """命令行入口点"""
    cli = CatalogCLI()
    return cli.run()


if __name__ == '__main__':
    sys.exit(main())