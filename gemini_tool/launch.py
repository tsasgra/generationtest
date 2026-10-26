"""Original Gemini launcher, using the shared setup/reset implementation."""
import sys

from pipeline import main as pipeline_main


def main(argv=None):
    return pipeline_main(['gemini', *(sys.argv[1:] if argv is None else argv)])


if __name__ == '__main__':
    raise SystemExit(main())
