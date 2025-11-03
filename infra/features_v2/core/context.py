"""
Extraction Context - Transparent context access for feature extractors

This module provides a thread-safe mechanism for feature extractors to access
experiment metadata and workflow parameters without explicit parameter passing.

Usage in extractors:
    from infra.features_v2.core.context import get_current_context

    @register('my_feature')
    class MyExtractor(BaseExtractor):
        def extract(self, data, params):
            ctx = get_current_context()
            if ctx:
                sampling_rate = ctx.get_workflow_param('transient_sampling_rate', 1000)
                chip_id = ctx.chip_id
            # ... use context information
"""

from contextvars import ContextVar
from typing import Optional, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from infra.catalog.unified_experiment import UnifiedExperiment

# Thread-safe context variable (Python 3.7+)
_current_context: ContextVar[Optional['ExtractionContext']] = ContextVar(
    'extraction_context',
    default=None
)


class ExtractionContext:
    """
    Ambient context accessible to all extractors during execution.

    Provides transparent access to experiment metadata and workflow parameters
    without requiring explicit parameter passing.

    Attributes:
        unified_experiment: The UnifiedExperiment being processed
        config_name: Feature configuration name
        config_version: Feature configuration version

    Example:
        ctx = get_current_context()
        if ctx:
            sampling_rate = ctx.get_workflow_param('workflow_step_1_1_param_sampling_rate')
            chip_id = ctx.chip_id
    """

    def __init__(
        self,
        unified_experiment: 'UnifiedExperiment',
        config_name: Optional[str] = None,
        config_version: Optional[str] = None
    ):
        """
        Initialize extraction context.

        Args:
            unified_experiment: The UnifiedExperiment instance
            config_name: Optional feature configuration name
            config_version: Optional feature configuration version
        """
        self._unified_experiment = unified_experiment
        self._config_name = config_name
        self._config_version = config_version
        self._workflow_cache: Optional[Dict[str, Any]] = None

    @property
    def unified_experiment(self) -> 'UnifiedExperiment':
        """Get the unified experiment instance"""
        return self._unified_experiment

    @property
    def chip_id(self) -> str:
        """Get chip ID (e.g., '#20250804008')"""
        return self._unified_experiment.chip_id

    @property
    def device_id(self) -> str:
        """Get device ID (e.g., '3')"""
        return self._unified_experiment.device_id

    @property
    def config_name(self) -> Optional[str]:
        """Get feature configuration name"""
        return self._config_name

    @property
    def config_version(self) -> Optional[str]:
        """Get feature configuration version"""
        return self._config_version

    @property
    def workflow(self) -> Dict[str, Any]:
        """
        Get flattened workflow metadata (cached).

        Returns a dictionary with workflow parameters like:
        - 'workflow_vg_gate_voltage': 0.6
        - 'workflow_step_1_1_param_Vd': -0.6
        - 'workflow_step_1_1_param_sampling_rate': 1000

        Returns:
            Dictionary of workflow metadata (empty dict if unavailable)
        """
        if self._workflow_cache is None:
            try:
                self._workflow_cache = self._unified_experiment.get_workflow_metadata()
            except Exception:
                # Fallback: return empty dict if workflow metadata unavailable
                self._workflow_cache = {}

        return self._workflow_cache

    def get_workflow_param(self, param_path: str, default: Any = None) -> Any:
        """
        Get specific workflow parameter by path.

        This method provides safe access to workflow parameters with a default
        fallback value if the parameter doesn't exist.

        Args:
            param_path: Parameter path (e.g., 'workflow_step_1_1_param_Vd')
            default: Default value if parameter not found

        Returns:
            Parameter value or default

        Example:
            # Get transient sampling rate with default 1000
            sampling_rate = ctx.get_workflow_param('workflow_step_1_1_param_sampling_rate', 1000)

            # Get gate voltage
            vg = ctx.get_workflow_param('workflow_vg_gate_voltage', 0.6)
        """
        return self.workflow.get(param_path, default)

    def has_workflow_param(self, param_path: str) -> bool:
        """
        Check if a workflow parameter exists.

        Args:
            param_path: Parameter path to check

        Returns:
            True if parameter exists, False otherwise
        """
        return param_path in self.workflow

    def get_all_workflow_params(self) -> Dict[str, Any]:
        """
        Get all workflow parameters.

        Returns:
            Complete workflow metadata dictionary
        """
        return self.workflow.copy()

    def __repr__(self) -> str:
        return (
            f"ExtractionContext(chip_id={self.chip_id!r}, "
            f"device_id={self.device_id!r}, "
            f"config_name={self.config_name!r})"
        )


class execution_context:
    """
    Context manager for setting execution context.

    This is typically used internally by the Executor to inject context
    during feature extraction. Users should use get_current_context() instead.

    Example (internal use):
        with execution_context(unified_experiment, 'my_config'):
            result = extractor.extract(data, params)
            # extractor can now call get_current_context()
    """

    def __init__(
        self,
        unified_experiment: 'UnifiedExperiment',
        config_name: Optional[str] = None,
        config_version: Optional[str] = None
    ):
        """
        Initialize context manager.

        Args:
            unified_experiment: The UnifiedExperiment instance
            config_name: Optional feature configuration name
            config_version: Optional feature configuration version
        """
        self.context = ExtractionContext(
            unified_experiment=unified_experiment,
            config_name=config_name,
            config_version=config_version
        )
        self.token = None

    def __enter__(self) -> ExtractionContext:
        """Enter context: set current context"""
        self.token = _current_context.set(self.context)
        return self.context

    def __exit__(self, *args) -> None:
        """Exit context: restore previous context"""
        if self.token is not None:
            _current_context.reset(self.token)


def get_current_context() -> Optional[ExtractionContext]:
    """
    Get current execution context (if available).

    This function should be called within feature extractor's extract() method
    to access experiment metadata and workflow parameters.

    Returns:
        ExtractionContext if called during feature extraction, None otherwise

    Example:
        @register('my_feature')
        class MyExtractor(BaseExtractor):
            def extract(self, data, params):
                ctx = get_current_context()
                if ctx:
                    sampling_rate = ctx.get_workflow_param('transient_sampling_rate', 1000)
                    print(f"Processing {ctx.chip_id} device {ctx.device_id}")

                # ... compute features

    Thread Safety:
        This function is thread-safe and async-safe. Each thread/async task
        has its own isolated context, making it safe for parallel execution.
    """
    return _current_context.get()


def require_context() -> ExtractionContext:
    """
    Get current context or raise error if not available.

    Use this when your extractor absolutely requires context to function.

    Returns:
        ExtractionContext instance

    Raises:
        RuntimeError: If no execution context is available

    Example:
        @register('context_required_feature')
        class ContextRequiredExtractor(BaseExtractor):
            def extract(self, data, params):
                ctx = require_context()  # Will raise if no context
                sampling_rate = ctx.get_workflow_param('transient_sampling_rate')
                # ...
    """
    ctx = get_current_context()
    if ctx is None:
        raise RuntimeError(
            "No execution context available. "
            "This extractor must be called through FeatureSet.compute() "
            "with a UnifiedExperiment instance."
        )
    return ctx


# Convenience function for checking if context is available
def has_context() -> bool:
    """
    Check if execution context is currently available.

    Returns:
        True if context is available, False otherwise

    Example:
        if has_context():
            ctx = get_current_context()
            # ... use context
        else:
            # ... fallback logic
    """
    return get_current_context() is not None
