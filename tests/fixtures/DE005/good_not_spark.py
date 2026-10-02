"""Plain Python module: `collect()` here is not a Spark action, so DE005 must stay silent."""

import gc
from dataclasses import dataclass, field


@dataclass
class MetricsBuffer:
    values: list[float] = field(default_factory=list)

    def collect(self) -> list[float]:
        collected, self.values = self.values, []
        return collected


buffer = MetricsBuffer()
buffer.values.append(1.5)
snapshot = buffer.collect()
gc.collect()
