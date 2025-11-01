"""
配置文件 Schema（Pydantic 模型）

定义配置文件的结构和验证规则
"""

from typing import Any, Dict, List, Optional, Literal, Union
from pydantic import BaseModel, Field, validator
from pathlib import Path


class DataSourceConfig(BaseModel):
    """数据源配置"""

    experiment_type: Literal['transfer', 'transient', 'both'] = 'transfer'
    load_mode: Literal['batch', 'step_by_step'] = 'batch'

    class Config:
        extra = 'forbid'  # 不允许额外字段


class FeatureSpec(BaseModel):
    """单个特征的配置"""

    name: str = Field(..., description="特征名称")
    extractor: Optional[str] = Field(None, description="提取器名称（如 'transfer.gm_max'）")
    func: Optional[str] = Field(None, description="自定义函数（Python 表达式）")
    input: Union[str, List[str]] = Field(..., description="输入依赖")
    params: Dict[str, Any] = Field(default_factory=dict, description="参数字典")
    output_shape: Optional[List[Union[str, int]]] = Field(None, description="输出形状")
    description: Optional[str] = Field(None, description="特征描述")
    unit: Optional[str] = Field(None, description="单位")

    @validator('extractor', 'func')
    def check_extractor_or_func(cls, v, values):
        """确保 extractor 和 func 至少有一个"""
        if 'extractor' in values and 'func' in values:
            if values.get('extractor') is None and v is None:
                raise ValueError("必须提供 extractor 或 func 之一")
        return v

    class Config:
        extra = 'allow'  # 允许额外字段（用于扩展）


class PostProcessStep(BaseModel):
    """后处理步骤配置"""

    type: str = Field(..., description="处理类型（normalize, filter, aggregate）")
    target: Union[str, List[str]] = Field(..., description="目标特征")
    params: Dict[str, Any] = Field(default_factory=dict, description="参数")

    class Config:
        extra = 'forbid'


class VersioningConfig(BaseModel):
    """版本化配置"""

    auto_create: bool = Field(True, description="是否自动创建版本")
    expand_multidim: bool = Field(True, description="是否展开多维特征")
    selected_features: Optional[List[str]] = Field(None, description="选择的特征（None=全部）")
    version_name: Optional[str] = Field(None, description="版本名称")

    class Config:
        extra = 'forbid'


class CachingConfig(BaseModel):
    """缓存配置"""

    enabled: bool = Field(True, description="是否启用缓存")
    backend: Literal['memory', 'disk', 'both'] = Field('memory', description="缓存后端")
    memory_size_mb: int = Field(512, description="内存缓存大小（MB）")
    disk_cache_dir: Optional[str] = Field('.cache', description="磁盘缓存目录")

    class Config:
        extra = 'forbid'


class ParallelConfig(BaseModel):
    """并行配置"""

    enabled: bool = Field(False, description="是否启用并行")
    n_workers: int = Field(4, description="工作进程数")
    backend: Literal['threading', 'multiprocessing'] = Field('multiprocessing')

    class Config:
        extra = 'forbid'


class AdvancedConfig(BaseModel):
    """高级配置"""

    transforms: List[PostProcessStep] = Field(default_factory=list)
    caching: CachingConfig = Field(default_factory=CachingConfig)
    parallel: ParallelConfig = Field(default_factory=ParallelConfig)

    class Config:
        extra = 'allow'


class FeatureConfig(BaseModel):
    """特征提取配置（根模型）"""

    version: str = Field('v2', description="配置文件版本")
    name: Optional[str] = Field(None, description="配置名称")
    config_version: str = Field('1.0', description="配置内容版本号")
    data_type: Literal['transfer', 'transient', 'both'] = Field('transfer')
    description: Optional[str] = Field(None, description="配置描述")

    # 数据源配置
    data_source: DataSourceConfig = Field(default_factory=DataSourceConfig)

    # 特征列表
    features: List[FeatureSpec] = Field(..., description="特征定义列表")

    # 后处理（可选）
    postprocessing: List[PostProcessStep] = Field(default_factory=list)

    # 版本化配置（可选）
    versioning: VersioningConfig = Field(default_factory=VersioningConfig)

    # 高级配置（可选）
    advanced: Optional[AdvancedConfig] = None

    @validator('features')
    def check_features_not_empty(cls, v):
        if not v:
            raise ValueError("features 列表不能为空")
        return v

    @classmethod
    def from_yaml(cls, yaml_path: str) -> 'FeatureConfig':
        """从 YAML 文件加载配置"""
        import yaml

        path = Path(yaml_path)
        if not path.exists():
            raise FileNotFoundError(f"配置文件不存在: {yaml_path}")

        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        return cls(**data)

    @classmethod
    def from_json(cls, json_path: str) -> 'FeatureConfig':
        """从 JSON 文件加载配置"""
        import json

        path = Path(json_path)
        if not path.exists():
            raise FileNotFoundError(f"配置文件不存在: {json_path}")

        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        return cls(**data)

    @classmethod
    def load(cls, config_path: str) -> 'FeatureConfig':
        """自动识别文件类型并加载"""
        path = Path(config_path)
        suffix = path.suffix.lower()

        if suffix in ['.yaml', '.yml']:
            return cls.from_yaml(config_path)
        elif suffix == '.json':
            return cls.from_json(config_path)
        else:
            raise ValueError(f"不支持的配置文件格式: {suffix}")

    def save_yaml(self, output_path: str):
        """保存为 YAML 文件"""
        import yaml

        with open(output_path, 'w', encoding='utf-8') as f:
            yaml.dump(self.dict(), f, allow_unicode=True, default_flow_style=False)

    def save_json(self, output_path: str):
        """保存为 JSON 文件"""
        import json

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(self.dict(), f, ensure_ascii=False, indent=2)

    class Config:
        extra = 'allow'  # 允许额外字段（向后兼容）
