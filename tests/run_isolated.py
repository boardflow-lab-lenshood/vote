"""Run interface tests with Redis network connections disabled, including health checks."""
import argparse
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from redis.connection import Connection
from redis.exceptions import ConnectionError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pattern", default="test_*.py")
    args = parser.parse_args()
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern=args.pattern)
    with patch.object(Connection, "connect", side_effect=ConnectionError("Redis disabled in isolated tests")):
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
