from __future__ import annotations

import logging
from pathlib import Path
from typing import List

from .geometry import default_alps_polygon_with_source
from .io_utils import write_csv


def main() -> None:
    """Generate a CSV describing the Alps perimeter source and any warnings/errors."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    log_records: List[logging.LogRecord] = []

    class Collector(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:  # type: ignore[override]
            if record.levelno >= logging.WARNING:
                log_records.append(record)

    logging.getLogger().addHandler(Collector())

    _, source = default_alps_polygon_with_source()

    errors = [r.getMessage() for r in log_records if r.levelno >= logging.ERROR]
    warnings = [r.getMessage() for r in log_records if r.levelno == logging.WARNING]

    out_dir = Path("outputs")
    out_dir.mkdir(parents=True, exist_ok=True)

    write_csv(out_dir / "perimeter_status.csv", [{
        "perimeter_source": source,
        "errors": "|".join(errors),
        "warnings": "|".join(warnings),
    }])


if __name__ == "__main__":
    main()
