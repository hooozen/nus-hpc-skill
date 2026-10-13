#!/usr/bin/env python3
"""macOS/Linux local diagnostics, read-only SSH probe and PBS renderer. No credentials or submission."""
import argparse
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import sys


def positive(value):
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError('must be positive')
    return n


def walltime(value):
    if not re.fullmatch(r'[0-9]{1,5}:[0-5][0-9]:[0-5][0-9]', value):
        raise argparse.ArgumentTypeError('use HHH:MM:SS')
    h, m, s = map(int, value.split(':'))
    if h * 3600 + m * 60 + s == 0:
        raise argparse.ArgumentTypeError('walltime must be positive')
    return value


def token(value):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', value):
        raise argparse.ArgumentTypeError('use an alphanumeric name, dot, underscore or hyphen')
    return value


def absolute_path(value):
    if not value.startswith('/') or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise argparse.ArgumentTypeError('use an absolute path without control characters')
    return value


PROBE = r'''
set +e
ready=1
if ! command -v qstat >/dev/null 2>&1 || ! command -v qsub >/dev/null 2>&1; then
    if type module >/dev/null 2>&1; then module load pbs; fi
fi
for label in identity commands queues; do
    printf '\n[%s]\n' "$label"
    case "$label" in
        identity) hostname -f && id -un ;;
        commands) command -v qsub && command -v qstat && command -v qdel ;;
        queues) if command -v qstat >/dev/null 2>&1; then qstat -Qf; else printf 'qstat unavailable\n'; false; fi ;;
    esac
    result=$?
    printf 'section_exit=%s\n' "$result"
    if [ "$result" -ne 0 ]; then ready=0; fi
done
printf '\n[quota tool: availability only]\n'
if command -v hpc >/dev/null 2>&1; then
    printf 'Run hpc space separately to inspect quota.\n'
else
    printf 'hpc unavailable\n'
fi
printf 'PROBE_SCHEDULER_READY=%s\n' "$ready"
if [ "$ready" -eq 1 ]; then exit 0; else exit 3; fi
'''


def doctor(args):
    """Only inspect local capabilities; do not read credential values or open a connection."""
    report = {
        'platform': platform.system(),
        'python': platform.python_version(),
        'ssh_available': shutil.which('ssh') is not None,
        'stdin_is_tty': sys.stdin.isatty(),
        'agent_socket_configured': bool(os.environ.get('SSH_AUTH_SOCK')),
        'desktop_session_present': bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')),
        'dbus_session_configured': bool(os.environ.get('DBUS_SESSION_BUS_ADDRESS')),
        'credentials_inspected': False,
        'network_or_auth_verified': False,
    }
    print(json.dumps(report, indent=2))
    return 0 if report['ssh_available'] else 2


def probe(args):
    cmd = ['ssh', '-T', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
           '-o', 'ForwardAgent=no', '-o', 'ConnectTimeout=15']
    if args.ssh_config:
        cmd += ['-F', args.ssh_config]
    if args.user:
        cmd += ['-l', args.user]
    if args.control_path:
        cmd += ['-S', args.control_path]
    # Noninteractive SSH does not necessarily load the site's PBS module.
    cmd += [args.host, 'bash -l -s']
    try:
        result = subprocess.run(cmd, input=PROBE, text=True, capture_output=True, timeout=60)
    except subprocess.TimeoutExpired:
        print('PROBE_TIMEOUT: no mutation performed; check network/session.', file=sys.stderr)
        return 2
    print(result.stdout, end='')
    print(result.stderr, end='', file=sys.stderr)
    if result.returncode == 255:
        print('SSH_UNAVAILABLE: inspect network, host trust or authentication; no automatic auth retries.', file=sys.stderr)
        return 2
    if result.returncode or 'PROBE_SCHEDULER_READY=1' not in result.stdout.splitlines():
        print('PBS_NOT_READY: inspect login environment, module and queue errors.', file=sys.stderr)
        return 3
    print('PBS_PROBE_READY: project eligibility and compute execution are not verified.')
    return 0


def render(args):
    if args.profile == 'hopper':
        if not args.project or not args.ngpus:
            raise ValueError('hopper requires --project and --ngpus')
        if args.ncpus is not None or args.mem_gb is not None:
            raise ValueError('hopper lets the site allocate CPU/memory per GPU; omit --ncpus and --mem-gb')
        resources = f'select=1:ngpus={args.ngpus}'
        queue = args.queue or 'auto'
    else:
        if not args.queue or not args.ncpus or not args.mem_gb:
            raise ValueError('generic requires --queue, --ncpus and --mem-gb')
        resources = f'select=1:ncpus={args.ncpus}:mem={args.mem_gb}gb'
        if args.ngpus:
            resources += f':ngpus={args.ngpus}'
        queue = args.queue
    source = Path(args.command_file)
    command = source.read_text(encoding='utf-8')
    if not command.strip() or '\x00' in command:
        raise ValueError('command file must contain a reviewed, nonempty shell program')
    # Embedded directives anywhere near a header can alter PBS requests; disallow them.
    if re.search(r'^\s*#PBS\b', command, re.MULTILINE):
        raise ValueError('command file must not contain PBS directives')
    header = ['#!/bin/bash', f'#PBS -N {args.name}', f'#PBS -q {queue}']
    if args.project:
        header += [f'#PBS -P {args.project}']
    if args.profile == 'hopper':
        header += ['#PBS -k oed']
    body = ['', 'set -euo pipefail', f'cd -- {shlex.quote(args.workdir)}']
    if args.ncpus:
        body += [f'export OMP_NUM_THREADS={args.ncpus}']
    content = '\n'.join(header + [
        f'#PBS -l {resources}', f'#PBS -l walltime={args.walltime}', '#PBS -j oe',
    ] + body + [
        '# Application/environment commands reviewed for this task:', command.rstrip(), ''
    ])
    # Exclusive creation avoids accidentally replacing an existing job script or symlink.
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as out:
        out.write(content)
    print(f'Prepared {args.output}; review site resource syntax before submission.')
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser('doctor', help='inspect local tools/session flags only; no network or credentials')
    p.set_defaults(func=doctor)
    p = sub.add_parser('probe', help='read-only SSH preflight using an existing trusted alias')
    p.add_argument('--host', required=True, type=token)
    p.add_argument('--user', type=token)
    p.add_argument('--control-path', type=absolute_path, help='absolute path to an existing private SSH control socket')
    p.add_argument('--ssh-config', type=absolute_path, help='absolute path to a trusted OpenSSH config')
    p.set_defaults(func=probe)
    p = sub.add_parser('render', help='prepare one PBS script locally; never submit')
    p.add_argument('--profile', choices=['generic', 'hopper'], default='generic')
    p.add_argument('--project', type=token)
    p.add_argument('--name', required=True, type=token)
    p.add_argument('--queue', type=token)
    p.add_argument('--workdir', required=True, type=absolute_path)
    p.add_argument('--ncpus', type=positive)
    p.add_argument('--mem-gb', type=positive)
    p.add_argument('--ngpus', type=positive)
    p.add_argument('--walltime', required=True, type=walltime)
    p.add_argument('--command-file', required=True)
    p.add_argument('--output', required=True)
    p.set_defaults(func=render)
    args = parser.parse_args()
    try:
        return args.func(args)
    except (OSError, ValueError) as exc:
        parser.exit(2, f'{exc}\n')


if __name__ == '__main__':
    sys.exit(main())
