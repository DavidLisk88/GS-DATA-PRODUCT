"""LSEG Data Copilot prototype package."""

__version__ = "0.1.0"

from .catalog import Catalog, TableSpec, ColumnSpec  # noqa: F401
from .pipeline import CopilotPipeline, bootstrap  # noqa: F401
from .reasoner import create_reasoner  # noqa: F401
from .sql_executor import SQLExecutionResult, execute_validated_sql  # noqa: F401
