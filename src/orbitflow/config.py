"""Application settings for read-only device workflows (Python 3.11+)."""
from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class ExecutionConfig:
    max_concurrent_devices: int = 10

    def __post_init__(self):
        if type(self.max_concurrent_devices) is not int or self.max_concurrent_devices < 1:
            raise ValueError("execution.max_concurrent_devices must be a positive integer")


def load_execution_config(path="orbitflow.toml"):
    """Read the application execution table; an absent default file uses defaults."""
    path = Path(path)
    if not path.exists() and path == Path("orbitflow.toml"):
        return ExecutionConfig()
    with path.open("rb") as source:
        settings = tomllib.load(source)
    return ExecutionConfig(**settings.get("execution", {}))
