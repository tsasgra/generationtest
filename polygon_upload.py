#!/usr/bin/env python3
"""Standalone single/batch Polygon CLI retained from copy_info_on_polygon."""
import sys

from polygon_tool.cli import (indices, main, nonnegative_int, parser, positive,
                              problem_count, validate_options)


if __name__ == '__main__':
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    raise SystemExit(main())
