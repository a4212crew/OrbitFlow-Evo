"""Application settings for read-only device workflows (Python 3.11+)."""
from dataclasses import dataclass
from pathlib import Path
import tomllib
import math


@dataclass(frozen=True)
class ExecutionConfig:
    max_concurrent_devices: int = 5
    connection_start_interval: float = 1.0
    connection_retry_delay: float = 5.0

    def __post_init__(self):
        if type(self.max_concurrent_devices) is not int or self.max_concurrent_devices < 1:
            raise ValueError("execution.max_concurrent_devices must be a positive integer")
        if (type(self.connection_start_interval) not in (int, float)
                or not math.isfinite(self.connection_start_interval)
                or self.connection_start_interval < 0):
            raise ValueError("execution.connection_start_interval must be finite and non-negative")
        if (type(self.connection_retry_delay) not in (int, float)
                or not math.isfinite(self.connection_retry_delay)
                or self.connection_retry_delay < 0):
            raise ValueError("execution.connection_retry_delay must be finite and non-negative")


def load_execution_config(path="orbitflow.toml"):
    """Read execution settings; the shared profile supersedes the legacy default.

    Explicit alternate configuration files retain their existing semantics.
    Profile pacing never changes the direct CLI concurrency default of five.
    """
    path = Path(path)
    profile = Path('data/sys_config/configuration-profile.toml')
    if path == Path('orbitflow.toml') and profile.exists():
        from orbitflow.environment import load_profile
        return ExecutionConfig(**load_profile(profile)['execution'])
    if not path.exists() and path == Path("orbitflow.toml"):
        return ExecutionConfig()
    with path.open("rb") as source:
        settings = tomllib.load(source)
    return ExecutionConfig(**settings.get("execution", {}))
