"""
工作流业务逻辑服务

处理工作流配置的解析、分析和导出功能
"""
import json
from typing import Dict, Any, Optional
from ..models import Workflow, WorkflowStep
from ..repositories import BaseRepository

########################### 日志设置 ################################
from ...logger_config import get_module_logger
logger = get_module_logger()
#####################################################################


class WorkflowService:
    """工作流服务类"""
    
    def __init__(self, repository: BaseRepository):
        self.repository = repository
    
    def get_workflow(self) -> Optional[Workflow]:
        """获取工作流配置"""
        return self.repository.load_workflow()
    
    def has_workflow(self) -> bool:
        """检查是否有工作流配置"""
        return self.repository.has_workflow()
    
    def get_workflow_summary(self) -> Dict[str, Any]:
        """获取工作流摘要信息"""
        workflow = self.get_workflow()
        if not workflow:
            return {"has_workflow": False}
        
        summary = {
            "has_workflow": True,
            "total_steps": len(workflow),
            "step_types": {},
            "total_loops": 0,
            "max_loop_iterations": 0,
            "nested_step_count": 0
        }
        
        def analyze_steps(steps_list):
            for step in steps_list:
                step_type = step.type
                summary["step_types"][step_type] = summary["step_types"].get(step_type, 0) + 1
                
                if step.type == 'loop':
                    summary["total_loops"] += 1
                    summary["max_loop_iterations"] = max(summary["max_loop_iterations"], step.iterations)
                    summary["nested_step_count"] += len(step.steps)
                    # 递归分析嵌套步骤
                    analyze_steps(step.steps)
        
        analyze_steps(workflow)
        return summary
    
    def print_workflow(self, indent: int = 0, show_all_params: bool = False):
        """以人类可读格式打印工作流"""
        workflow = self.get_workflow()
        if not workflow:
            print("  " * indent + "无工作流配置")
            return
        
        print("  " * indent + f"工作流配置 (共 {len(workflow)} 个步骤):")
        print("  " * indent + "=" * 50)
        
        for i, step in enumerate(workflow, 1):
            self._print_workflow_step(step, i, indent + 1, show_all_params)
            if i < len(workflow):
                print("  " * indent + "-" * 30)
    
    def _print_workflow_step(self, step: WorkflowStep, step_num: int, indent: int = 0, show_all_params: bool = False):
        """打印单个工作流步骤"""
        prefix = "  " * indent
        
        if step.type == 'loop':
            print(f"{prefix}步骤 {step_num}: 循环 ({step.iterations} 次)")
            print(f"{prefix}  ID: {step.id}")
            print(f"{prefix}  子步骤 ({len(step.steps)} 个):")
            
            for j, sub_step in enumerate(step.steps, 1):
                self._print_workflow_step(sub_step, j, indent + 1, show_all_params)
                if j < len(step.steps):
                    print(f"{prefix}  " + "·" * 20)
        else:
            # 常规步骤 (transfer, transient, output)
            step_type_name = {
                'transfer': '转移特性测试',
                'transient': '瞬态特性测试',
                'output': '输出特性测试'
            }.get(step.type, step.type)
            
            print(f"{prefix}步骤 {step_num}: {step_type_name}")
            print(f"{prefix}  ID: {step.id}")
            print(f"{prefix}  Command ID: {step.command_id}")
            
            if hasattr(step, 'params') and step.params:
                self._print_step_params(step.params, step.type, indent + 1, show_all_params)
    
    def _print_step_params(self, params: Dict[str, Any], step_type: str, indent: int = 0, show_all_params: bool = False):
        """打印步骤参数"""
        prefix = "  " * indent
        print(f"{prefix}参数:")
        
        # 定义每种步骤类型的关键参数
        key_params = {
            'transfer': ['isSweep', 'timeStep', 'sourceVoltage', 'drainVoltage',
                        'gateVoltageStart', 'gateVoltageEnd', 'gateVoltageStep'],
            'transient': ['timeStep', 'sourceVoltage', 'drainVoltage', 'bottomTime',
                         'topTime', 'gateVoltageBottom', 'gateVoltageTop', 'cycles'],
            'output': ['isSweep', 'timeStep', 'sourceVoltage', 'gateVoltage',
                      'drainVoltageStart', 'drainVoltageEnd', 'drainVoltageStep']
        }
        
        params_to_show = key_params.get(step_type, list(params.keys())) if not show_all_params else list(params.keys())
        
        # 按类别分组参数
        voltage_params = []
        timing_params = []
        sweep_params = []
        other_params = []
        
        for param_name in params_to_show:
            if param_name not in params:
                continue
            
            value = params[param_name]
            param_display = f"{param_name}: {value}"
            
            if 'voltage' in param_name.lower():
                voltage_params.append(param_display)
            elif 'time' in param_name.lower() or param_name == 'cycles':
                timing_params.append(param_display)
            elif 'sweep' in param_name.lower() or 'step' in param_name.lower():
                sweep_params.append(param_display)
            else:
                other_params.append(param_display)
        
        # 打印分组参数
        if voltage_params:
            print(f"{prefix}  电压参数:")
            for param in voltage_params:
                print(f"{prefix}    {param}")
        
        if timing_params:
            print(f"{prefix}  时间参数:")
            for param in timing_params:
                print(f"{prefix}    {param}")
        
        if sweep_params:
            print(f"{prefix}  扫描参数:")
            for param in sweep_params:
                print(f"{prefix}    {param}")
        
        if other_params:
            print(f"{prefix}  其他参数:")
            for param in other_params:
                print(f"{prefix}    {param}")
    
    def export_workflow_json(self, output_path: str, indent: int = 2) -> bool:
        """导出工作流配置到JSON文件"""
        workflow = self.get_workflow()
        if not workflow:
            logger.warning("无工作流配置可导出")
            return False
        
        try:
            # 将Pydantic模型转换为字典
            workflow_dict = [step.model_dump() for step in workflow]
            
            # 写入JSON文件
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(workflow_dict, f, ensure_ascii=False, indent=indent)
            
            logger.info(f"工作流已导出到: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"导出工作流失败: {e}")
            return False