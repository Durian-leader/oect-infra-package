from catalog import UnifiedExperimentManager
import pandas as pd
import json


def normalize_value(value):
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return json.dumps(value)


def flatten_workflow(exp):
    workflow = exp.get_workflow()
    if not workflow:
        return {}

    flattened = {}

    def walk(steps, path):
        for idx, step in enumerate(steps, start=1):
            step_path = path + [str(idx)]
            base = f"workflow_step_{'_'.join(step_path)}"

            flattened[f"{base}_type"] = getattr(step, "type", None)

            if hasattr(step, "id"):
                flattened[f"{base}_id"] = step.id

            if hasattr(step, "command_id"):
                flattened[f"{base}_command_id"] = step.command_id

            if hasattr(step, "iterations"):
                flattened[f"{base}_iterations"] = step.iterations

            params = getattr(step, "params", None)
            if params:
                for key, value in params.items():
                    flattened[f"{base}_param_{key}"] = normalize_value(value)

            child_steps = getattr(step, "steps", None)
            if child_steps:
                walk(child_steps, step_path)

    walk(workflow, [])
    return flattened


def build_row(exp):
    info = exp.get_info()
    row = {}
    for section in info.values():
        row.update(section)
    row.update(flatten_workflow(exp))
    return row


manager = UnifiedExperimentManager("catalog_config.yaml")
experiments = manager.search()
if not experiments:
    raise SystemExit("No experiments found.")

rows = [build_row(exp) for exp in experiments]

pd.DataFrame(rows).to_excel("experiments_metadata.xlsx", index=False)
