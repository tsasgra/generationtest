#!/usr/bin/env python3
"""Standalone Gemini entry point retained from upload_img_to_gemini."""
import sys

from gemini_tool.cli import main, numbered_folders, positive_number


if __name__ == '__main__':
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    raise SystemExit(main())
