#!/usr/bin/env python3
"""Upload up to ten Polygon problems concurrently, each from ten .txt files."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from polygon_tool.api import APIError, PolygonAPI, TransportError
from polygon_tool.credentials import load_credentials
from polygon_tool.input import discover_problems, init_batch, init_directory, parse_batch, parse_problem
from polygon_tool.problem_url import resolve_problem_url
from polygon_tool.workflow import Workflow, WorkflowError, state_lock

DEFAULT_ENV_FILE = Path(__file__).resolve().parent.parent / '.env'


def positive(value):
    number = float(value)
    if not 0 < number < float('inf'):
        raise argparse.ArgumentTypeError('Phải là số dương hữu hạn.')
    return number


def nonnegative_int(value):
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError('Phải là số nguyên không âm.')
    return number


def problem_count(value):
    number = int(value)
    if not 1 <= number <= 10:
        raise argparse.ArgumentTypeError('Phải là số nguyên từ 1 đến 10.')
    return number


def indices(value):
    try:
        result = [int(v.strip()) for v in value.split(',')]
    except ValueError as exc:
        raise argparse.ArgumentTypeError('Dùng danh sách như 1,3,7.') from exc
    if not result or min(result) < 1 or len(set(result)) != len(result):
        raise argparse.ArgumentTypeError('Chỉ số sample phải dương và không trùng.')
    return sorted(result)


def parser():
    cli = argparse.ArgumentParser(description=__doc__)
    sub = cli.add_subparsers(dest='command', required=True)
    init = sub.add_parser('init', help='Tạo thư mục gồm 10 file .txt trống, mỗi file là một phần.')
    init.add_argument('--output', type=Path, default=Path('problem'), help='Thư mục mới để tạo 10 file .txt.')
    init.add_argument('--count', type=problem_count, help='Tạo problem1..problemN, mỗi bài gồm 10 file .txt.')
    run = sub.add_parser('run', help='Kiểm tra và tạo một bài hoặc tối đa 10 bài song song.')
    run.add_argument('--input', type=Path, required=True, help='Một bài hoặc thư mục chứa problem1..problem10.')
    run.add_argument('--dry-run', action='store_true')
    run.add_argument('--time-limit', type=int)
    run.add_argument('--memory-limit', type=int)
    run.add_argument('--input-file')
    run.add_argument('--output-file')
    run.add_argument('--source-type', default='cpp.g++17')
    resume = sub.add_parser('resume', help='Tiếp tục bằng checkpoint, không tạo bài khác.')
    resume.add_argument('--problem-id', type=int, help='Xác nhận ID sau create bị mất phản hồi.')
    resume.add_argument('--package-id', type=int, help='Chọn ID trong các package mới của revision đã commit.')
    correction = resume.add_mutually_exclusive_group()
    correction.add_argument('--update-input', type=Path, help='Thư mục 10 file đã sửa trên cùng problem ID; server phải khớp checkpoint.')
    correction.add_argument('--retry-failed-package', action='store_true', help='Chủ động build lại package FAILED, giữ revision.')
    for command in (run, resume):
        command.add_argument('--state', type=Path, default=Path('run_state.json'))
        command.add_argument('--jobs', type=problem_count, default=None, help='Số bài chạy song song, mặc định 10.')
        command.add_argument('--sample-indices', type=indices)
        command.add_argument('--output-dir', type=Path, default=None)
        command.add_argument('--request-timeout', type=positive, default=None)
        command.add_argument('--retries', type=nonnegative_int, default=None)
        command.add_argument('--request-interval', type=positive, default=None)
        command.add_argument('--poll-interval', type=positive, default=None)
        command.add_argument('--poll-timeout', type=positive, default=None)
        command.add_argument('--browser', action='store_true', default=None)
        command.add_argument('--browser-profile', type=Path, default=None)
        command.add_argument('--browser-timeout', type=positive, default=None)
        command.add_argument('--url-only', action='store_true')
    return cli


def validate_options(options):
    time_limit = options.get('timeLimit')
    if time_limit is not None and (not 250 <= time_limit <= 15000 or time_limit % 50):
        raise ValueError('--time-limit: 250..15000 ms, chia hết cho 50.')
    memory = options.get('memoryLimit')
    if memory is not None and not 4 <= memory <= 1024:
        raise ValueError('--memory-limit: 4..1024 MB.')
    for field in ('inputFile', 'outputFile'):
        value = options.get(field)
        if value is not None and (not 1 <= len(value) <= 64 or '\x00' in value or '\n' in value or '\r' in value):
            raise ValueError(f'{field}: phải có 1..64 ký tự hợp lệ trên một dòng.')
    if (options.get('inputFile') is not None and options.get('outputFile') is not None
            and options['inputFile'].lower() == options['outputFile'].lower()):
        raise ValueError('Tên tệp vào và ra phải khác nhau.')
    if not options.get('source_type', '').strip():
        raise ValueError('--source-type không được rỗng.')


def legacy_launch(argv=None):
    """Keep the source branch's Windows auto/check/resume/stop actions."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    action = arguments.pop(0) if arguments else 'auto'
    if action == 'stop':
        from polygon_tool.stop import main as stop
        if arguments:
            raise ValueError('Polygon Stop không nhận thêm tùy chọn.')
        return stop()
    if action == 'auto':
        action = 'resume' if Path('run_state.json').exists() else 'run'
    commands = {
        'run': ['run', '--input', 'problem', '--state', 'run_state.json'],
        'check': ['run', '--input', 'problem', '--dry-run'],
        'resume': ['resume', '--state', 'run_state.json'],
    }
    if action not in commands:
        raise ValueError('Dùng polygon-legacy [auto|check|resume|stop].')
    return main([*commands[action], *arguments])


def main(argv=None):
    args = parser().parse_args(argv)
    workflow = None
    key = secret = None
    try:
        if args.command == 'init':
            if args.count is not None:
                init_batch(args.output, args.count)
                print(f'Đã tạo {args.count} thư mục bài trong {args.output}, mỗi bài gồm 10 file .txt trống.')
            else:
                init_directory(args.output)
                print(f'Đã tạo 10 file .txt trong {args.output}. Điền nội dung vào từng file trước khi run.')
            return 0
        batch_resume = False
        if args.command == 'run':
            options = {'input_path': str(args.input.resolve()), 'timeLimit': args.time_limit,
                       'memoryLimit': args.memory_limit, 'inputFile': args.input_file,
                       'outputFile': args.output_file, 'source_type': args.source_type}
        else:
            if not args.state.exists():
                raise ValueError(f'Không có checkpoint: {args.state}')
            state = json.loads(args.state.read_text(encoding='utf-8'))
            if state.get('version') != 1:
                raise ValueError('Phiên bản checkpoint không được hỗ trợ.')
            batch_resume = state.get('kind') == 'batch'
            if batch_resume and (args.problem_id is not None or args.package_id is not None
                                 or args.update_input or args.retry_failed_package):
                raise ValueError('Tùy chọn sửa/khôi phục một bài phải dùng --state checkpoint con '
                                 '(ví dụ run_state.problems/problem1.json).')
            options = dict(state['options'])
            options.update(problem_id=args.problem_id, package_id=args.package_id)
            if args.update_input:
                options['input_path'] = str(args.update_input.resolve())
        defaults = {'request_timeout': 60.0, 'retries': 3, 'request_interval': 1.0,
                    'poll_interval': 5.0, 'poll_timeout': 900.0, 'browser_timeout': 300.0,
                    'browser': False, 'browser_profile': str(Path('.polygon-browser').resolve()),
                    'output_dir': str(Path('.').resolve()), 'sample_indices': None, 'jobs': 10}
        for name, default in defaults.items():
            value = getattr(args, name)
            if value is not None:
                options[name] = str(value.resolve()) if isinstance(value, Path) else value
            elif name not in options:
                options[name] = default
        validate_options(options)
        paths = discover_problems(Path(options['input_path']), allow_single=True)
        if paths == []:
            raise ValueError('Chưa có bộ nội dung bài nào được điền trong thư mục đầu vào.')
        if args.command == 'resume' and batch_resume != (paths is not None):
            raise ValueError('Cấu trúc đầu vào khác checkpoint: không đổi giữa một bài và nhiều bài khi resume.')
        problems = parse_batch(paths) if paths is not None else None
        parts = None if paths is not None else parse_problem(Path(options['input_path']))
        if args.command == 'run' and args.dry_run:
            # Offline by design: no credentials, state, API reads, or remote writes.
            if paths is not None:
                print(json.dumps({'valid': True, 'kind': 'batch', 'total': len(paths),
                                  'jobs': min(options['jobs'], len(paths)),
                                  'request_interval': options['request_interval'],
                                  'problems': [{'folder': path.name, 'name': item['name problem'],
                                                'display_name': item['name']}
                                               for path, item in zip(paths, problems)],
                                  'note': 'Mỗi bài có checkpoint/kết quả riêng; chưa gọi Polygon.'},
                                 ensure_ascii=False, indent=2))
                return 0
            print(json.dumps({'valid': True, 'name': parts['name problem'], 'display_name': parts['name'],
                              'statement_language': 'vietnamese', 'sample_indices': options['sample_indices'],
                              'plan': ['create', 'info', 'statement', 'checker.cpp', 'checker', 'gen.cpp',
                                       'solution (MA)', 'script (tests)', 'samples from server indices',
                                       'codeforces access', 'verify', 'commit', 'Standard package', 'official URL'],
                              'defaults': 'Giữ mặc định Polygon cho tùy chọn chưa truyền; in giá trị khi chạy thật.',
                              'note': 'Sample tự động chỉ xác định sau khi Polygon triển khai script.'},
                             ensure_ascii=False, indent=2))
            return 0
        key, secret = load_credentials(DEFAULT_ENV_FILE)
        with state_lock(args.state):
            if args.command == 'run' and args.state.exists():
                raise ValueError('Checkpoint đã tồn tại. Dùng resume --state hoặc đường dẫn --state mới.')
            if args.command == 'resume' and paths is None:
                state = json.loads(args.state.read_text(encoding='utf-8'))
                if state.get('committed') and not args.update_input and options['sample_indices'] != state['options'].get('sample_indices'):
                    raise ValueError('Không đổi sample sau commit. Kiểm tra bài và tạo quy trình mới nếu cần sửa.')
            if paths is not None:
                from polygon_tool.batch import BatchWorkflow
                workflow = BatchWorkflow(args.state, paths, problems, options,
                                         resume=batch_resume, sample_override=args.sample_indices is not None)
                result = workflow.run(key, secret, resolve_problem_url)
            else:
                api = PolygonAPI(key, secret, timeout=options['request_timeout'], retries=options['retries'],
                                 interval=options['request_interval'])
                workflow = Workflow(api, args.state, parts, options)
                if args.command == 'resume' and args.update_input:
                    workflow.accept_updated_input()
                if args.command == 'resume' and args.retry_failed_package:
                    workflow.retry_failed_package()
                if workflow.state:
                    workflow.state['options'] = options
                    workflow.save()
                result = workflow.run(resolve_problem_url)
        if args.url_only:
            if paths is not None:
                for row in result['problems']:
                    if row['status'] == 'completed':
                        print(row['result']['problem_url'])
            else:
                print(result['problem_url'])
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        if paths is not None and result['failed']:
            print(f'Tiếp tục các bài chưa xong: python polygon_upload.py resume --state "{args.state}"',
                  file=sys.stderr)
            return 1
        return 0
    except (APIError, TransportError, WorkflowError, ValueError, OSError) as exc:
        # The transport strips credentials from remote comments; local exceptions
        # never contain request bodies. Keep progress and errors off stdout.
        message = str(exc)
        for value in (key, secret, os.environ.get('POLYGON_API_KEY'), os.environ.get('POLYGON_API_SECRET')):
            if value:
                message = message.replace(value, '[REDACTED]')
        step = workflow.step if workflow else 'preflight'
        print(f'Lỗi tại {step}: {message}', file=sys.stderr)
        if getattr(args, 'state', None) and args.state.exists():
            print(f'Tiếp tục: python polygon_upload.py resume --state "{args.state}"', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('Đã dừng. Dùng resume với checkpoint hiện tại; không chạy run lần nữa.', file=sys.stderr)
        return 130


if __name__ == '__main__':
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    raise SystemExit(main())
