#!/usr/bin/env python3
"""Offline regression tests; no credentials, network access, or PBS submissions."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).with_name('hpc.py')
SPEC = importlib.util.spec_from_file_location('nus_hpc_helper', SCRIPT)
hpc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hpc)
BASH = shutil.which('bash')


def cli(arguments):
    """Exercise real argparse validation without spawning a process."""
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.object(sys, 'argv', [str(SCRIPT)] + arguments):
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = hpc.main()
            except SystemExit as exc:
                code = exc.code
    return code, out.getvalue(), err.getvalue()


class DoctorTests(unittest.TestCase):
    def test_local_report_does_not_read_secrets_or_call_subprocess(self):
        secret = 'TEST_SECRET_MUST_NOT_BE_EMITTED'
        for platform_name in ('Darwin', 'Linux'):
            with self.subTest(platform=platform_name):
                with mock.patch.dict(os.environ, {
                    'SSH_AUTH_SOCK': '/private/' + secret,
                    'DBUS_SESSION_BUS_ADDRESS': secret,
                    'DISPLAY': secret,
                    'NUS_PASSWORD': secret,
                }, clear=True), mock.patch.object(hpc.platform, 'system', return_value=platform_name), \
                        mock.patch.object(hpc.shutil, 'which', return_value='/usr/bin/ssh'), \
                        mock.patch.object(hpc.subprocess, 'run', side_effect=AssertionError('network/process access')), \
                        mock.patch('builtins.open', side_effect=AssertionError('credential/file access')):
                    code, out, err = cli(['doctor'])
                self.assertEqual(code, 0, err)
                report = json.loads(out)
                self.assertEqual(report['platform'], platform_name)
                self.assertTrue(report['agent_socket_configured'])
                self.assertTrue(report['dbus_session_configured'])
                self.assertFalse(report['credentials_inspected'])
                self.assertFalse(report['network_or_auth_verified'])
                self.assertNotIn(secret, out + err)

    def test_headless_linux_without_ssh_reports_capability_failure(self):
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(hpc.platform, 'system', return_value='Linux'), \
                mock.patch.object(hpc.shutil, 'which', return_value=None):
            code, out, _ = cli(['doctor'])
        report = json.loads(out)
        self.assertEqual(code, 2)
        self.assertFalse(report['ssh_available'])
        self.assertFalse(report['desktop_session_present'])
        self.assertFalse(report['dbus_session_configured'])
        self.assertFalse(report['agent_socket_configured'])


class ProbeTests(unittest.TestCase):
    def probe_result(self, returncode=0, stdout='PROBE_SCHEDULER_READY=1\n', stderr=''):
        with mock.patch.object(hpc.subprocess, 'run', return_value=subprocess.CompletedProcess(
                [], returncode, stdout, stderr)) as run:
            response = cli(['probe', '--host', 'nus-hopper', '--user', 'testuser',
                            '--ssh-config', '/tmp/trusted config', '--control-path', '/tmp/private socket'])
        return response, run.call_args

    def test_ssh_is_noninteractive_and_preserves_explicit_connection_options(self):
        (code, out, err), call = self.probe_result()
        self.assertEqual(code, 0, err)
        command = call.args[0]
        self.assertEqual(command, ['ssh', '-T', '-o', 'BatchMode=yes', '-o',
                                  'StrictHostKeyChecking=yes', '-o', 'ForwardAgent=no',
                                  '-o', 'ConnectTimeout=15', '-F', '/tmp/trusted config',
                                  '-l', 'testuser', '-S', '/tmp/private socket',
                                  'nus-hopper', 'bash -l -s'])
        self.assertEqual(call.kwargs['input'], hpc.PROBE)
        self.assertTrue(call.kwargs['capture_output'])
        self.assertTrue(call.kwargs['text'])
        self.assertEqual(call.kwargs['timeout'], 60)
        self.assertIn('project eligibility and compute execution are not verified', out)

    def test_transport_and_scheduler_failures_have_nonzero_status(self):
        cases = [
            (255, '', 2, 'SSH_UNAVAILABLE'),
            (0, 'PROBE_SCHEDULER_READY=0\n', 3, 'PBS_NOT_READY'),
            (0, 'qstat unavailable\n', 3, 'PBS_NOT_READY'),
            (3, 'PROBE_SCHEDULER_READY=1\n', 3, 'PBS_NOT_READY'),
            (0, 'prefix_PROBE_SCHEDULER_READY=1\n', 3, 'PBS_NOT_READY'),
        ]
        for remote_status, output, expected_status, diagnostic in cases:
            with self.subTest(remote_status=remote_status, output=output):
                (code, out, err), _ = self.probe_result(remote_status, output)
                self.assertEqual(code, expected_status)
                self.assertIn(diagnostic, err)
                self.assertNotIn('PBS_PROBE_READY:', out)

    def test_timeout_does_not_retry(self):
        with mock.patch.object(hpc.subprocess, 'run', side_effect=subprocess.TimeoutExpired('ssh', 60)) as run:
            code, out, err = cli(['probe', '--host', 'nus-hopper'])
        self.assertEqual(code, 2)
        self.assertEqual(run.call_count, 1)
        self.assertIn('PROBE_TIMEOUT', err)
        self.assertNotIn('PBS_PROBE_READY:', out)

    def test_invalid_host_user_and_connection_paths_never_invoke_ssh(self):
        invalid = [('--host', '-oProxyCommand=evil'), ('--host', 'host;evil'),
                   ('--user', 'user\ncommand'), ('--control-path', 'relative'),
                   ('--ssh-config', '/tmp/config\n-oProxyCommand=evil')]
        for option, value in invalid:
            with self.subTest(option=option, value=value):
                args = ['probe', '--host', 'nus-hopper', option + '=' + value]
                with mock.patch.object(hpc.subprocess, 'run') as run:
                    code, _, _ = cli(args)
                self.assertEqual(code, 2)
                run.assert_not_called()


@unittest.skipUnless(BASH, 'bash is needed for offline probe-shell tests')
class ProbeShellTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='nus-hpc-probe-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / 'bin'
        self.pbs = self.root / 'pbs'
        self.bin.mkdir()
        self.pbs.mkdir()
        self.command(self.bin, 'hostname', 'printf "test-hpc.example\\n"')
        self.command(self.bin, 'id', 'printf "testuser\\n"')

    def command(self, directory, name, body):
        script = directory / name
        script.write_text('#!/bin/sh\n' + body + '\n', encoding='utf-8')
        script.chmod(0o700)

    def scheduler(self, directory, qstat_exit=0):
        # qsub/qdel must only be discovered, never executed by the probe.
        self.command(directory, 'qsub', 'exit 99')
        self.command(directory, 'qdel', 'exit 99')
        self.command(directory, 'qstat', 'printf "Queue: testqueue\\n"\nexit ' + str(qstat_exit))

    def run_probe(self, preamble=''):
        # Isolate PATH to stubs: this shell cannot reach any real HPC or auth command.
        env = {'PATH': str(self.bin), 'PBS_STUB_BIN': str(self.pbs), 'LC_ALL': 'C'}
        return subprocess.run([BASH, '--noprofile', '--norc', '-c', preamble + hpc.PROBE],
                              env=env, text=True, capture_output=True, timeout=10)

    def test_module_load_fallback_finds_scheduler(self):
        self.scheduler(self.pbs)
        preamble = '''
module() {
    if [ "$1" != load ] || [ "$2" != pbs ]; then return 17; fi
    printf 'MOCK_MODULE_LOADED\\n'
    PATH="$PBS_STUB_BIN:$PATH"
    export PATH
}
'''
        result = self.run_probe(preamble)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn('MOCK_MODULE_LOADED', result.stdout)
        self.assertIn('PROBE_SCHEDULER_READY=1', result.stdout)

    def test_missing_optional_hpc_does_not_fail_scheduler_readiness(self):
        self.scheduler(self.bin)
        result = self.run_probe()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('hpc unavailable', result.stdout)
        self.assertIn('PROBE_SCHEDULER_READY=1', result.stdout)

    def test_qstat_failure_marks_not_ready(self):
        self.scheduler(self.bin, qstat_exit=7)
        result = self.run_probe()
        self.assertEqual(result.returncode, 3)
        self.assertIn('section_exit=7', result.stdout)
        self.assertIn('PROBE_SCHEDULER_READY=0', result.stdout)

    def test_missing_scheduler_marks_not_ready(self):
        result = self.run_probe()
        self.assertEqual(result.returncode, 3)
        self.assertIn('qstat unavailable', result.stdout)
        self.assertIn('PROBE_SCHEDULER_READY=0', result.stdout)

    def test_identity_failure_marks_not_ready(self):
        self.scheduler(self.bin)
        self.command(self.bin, 'hostname', 'exit 8')
        result = self.run_probe()
        self.assertEqual(result.returncode, 3)
        self.assertIn('section_exit=8', result.stdout)
        self.assertIn('PROBE_SCHEDULER_READY=0', result.stdout)


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='nus-hpc-render-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.command = self.root / 'reviewed.sh'
        self.command.write_text('printf "test complete\\n"\n', encoding='utf-8')
        self.output = self.root / 'job.pbs'

    def arguments(self, profile='generic'):
        result = ['render', '--profile', profile, '--name', 'smoke',
                  '--workdir', str(self.root), '--walltime', '00:01:00',
                  '--command-file', str(self.command), '--output', str(self.output)]
        if profile == 'hopper':
            result += ['--project', 'TEST-PROJECT-001', '--ngpus', '1']
        else:
            result += ['--queue', 'testqueue', '--ncpus', '2', '--mem-gb', '3']
        return result

    def test_generic_resources_and_output_permissions(self):
        code, _, err = cli(self.arguments() + ['--ngpus', '1'])
        self.assertEqual(code, 0, err)
        content = self.output.read_text(encoding='utf-8')
        self.assertIn('#PBS -l select=1:ncpus=2:mem=3gb:ngpus=1\n', content)
        self.assertIn('export OMP_NUM_THREADS=2\n', content)
        self.assertNotIn('#PBS -P ', content)
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o600)

    @unittest.skipUnless(BASH and shutil.which('awk'), 'bash and awk are needed for local smoke execution')
    def test_hopper_smoke_asset_runs_locally_and_writes_verified_results(self):
        smoke = SCRIPT.parent.parent / 'assets' / 'smoke.sh'
        code, _, err = cli(self.arguments('hopper') + ['--command-file', str(smoke)])
        self.assertEqual(code, 0, err)
        env = os.environ.copy()
        env.pop('PBS_JOBID', None)
        # A local Bash check only: PBS headers remain comments and nothing is submitted.
        result = subprocess.run([BASH, str(self.output)], cwd=self.root, env=env,
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('job_id=local-check\n', result.stdout)
        self.assertEqual((self.root / 'result.txt').read_text(), 'sum_1_to_100000=5000050000\n')
        self.assertEqual((self.root / 'status').read_text(), 'COMPLETE\n')
        self.assertFalse((self.root / 'result.txt.tmp').exists())
        self.assertFalse((self.root / 'status.tmp').exists())

    def test_hopper_project_gpu_resources_do_not_override_site_cpu_memory(self):
        code, _, err = cli(self.arguments('hopper'))
        self.assertEqual(code, 0, err)
        content = self.output.read_text(encoding='utf-8')
        self.assertIn('#PBS -P TEST-PROJECT-001\n', content)
        self.assertIn('#PBS -q auto\n', content)
        self.assertIn('#PBS -k oed\n', content)
        self.assertIn('#PBS -l select=1:ngpus=1\n', content)
        self.assertNotIn('ncpus=', content)
        self.assertNotIn('mem=', content)
        self.assertNotIn('OMP_NUM_THREADS=', content)

    def test_required_resource_parameters(self):
        for profile, field in [('hopper', '--project'), ('hopper', '--ngpus'),
                               ('generic', '--queue'), ('generic', '--ncpus'), ('generic', '--mem-gb')]:
            with self.subTest(profile=profile, field=field):
                arguments = self.arguments(profile)
                index = arguments.index(field)
                del arguments[index:index + 2]
                code, _, _ = cli(arguments)
                self.assertEqual(code, 2)
                self.assertFalse(self.output.exists())
        for option in ('--ncpus', '--mem-gb'):
            with self.subTest(hopper_forbidden_override=option):
                code, _, err = cli(self.arguments('hopper') + [option, '2'])
                self.assertEqual(code, 2)
                self.assertIn('omit --ncpus and --mem-gb', err)
                self.assertFalse(self.output.exists())

    def test_invalid_resources_names_paths_and_directives_are_rejected(self):
        cases = [('--name', 'bad\n#PBS -q other'), ('--name', 'bad;command'),
                 ('--queue', '-oProxyCommand'), ('--project', 'proj\ncommand'),
                 ('--ncpus', '1:mem=1gb'), ('--mem-gb', '0'), ('--ngpus', '-1'),
                 ('--walltime', '00:00:00'), ('--walltime', '1:60:00'),
                 ('--walltime', '1:00:00\n#PBS -q other'),
                 ('--workdir', 'relative/path'), ('--workdir', '/tmp/path\ncommand'),
                 ('--workdir', '/tmp/path\x00command')]
        for option, value in cases:
            with self.subTest(option=option, value=value):
                code, _, _ = cli(self.arguments() + [option + '=' + value])
                self.assertEqual(code, 2)
                self.assertFalse(self.output.exists())
        for program in ('', '  \n', 'printf ok\n#PBS -l select=2\n', 'true\x00'):
            with self.subTest(command=program):
                self.command.write_text(program, encoding='utf-8')
                code, _, _ = cli(self.arguments())
                self.assertEqual(code, 2)
                self.assertFalse(self.output.exists())

    @unittest.skipUnless(BASH, 'bash is needed to verify rendered path quoting')
    def test_shell_metacharacters_in_absolute_workdir_remain_literal(self):
        workdir = self.root / "space ' quote $(touch INJECTION_OCCURRED); directory"
        workdir.mkdir()
        self.command.write_text('pwd -P > actual.txt\n', encoding='utf-8')
        code, _, err = cli(self.arguments() + ['--workdir', str(workdir)])
        self.assertEqual(code, 0, err)
        result = subprocess.run([BASH, str(self.output)], cwd=self.root,
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((workdir / 'actual.txt').read_text().strip(), str(workdir.resolve()))
        self.assertFalse((self.root / 'INJECTION_OCCURRED').exists())

    def test_existing_output_is_preserved(self):
        self.output.write_text('existing job\n', encoding='utf-8')
        code, _, _ = cli(self.arguments())
        self.assertEqual(code, 2)
        self.assertEqual(self.output.read_text(), 'existing job\n')

    def test_output_symlink_is_refused_even_if_target_does_not_exist(self):
        for target_exists in (False, True):
            with self.subTest(target_exists=target_exists):
                target = self.root / ('target-' + str(target_exists))
                if target_exists:
                    target.write_text('untouched\n', encoding='utf-8')
                self.output.symlink_to(target)
                code, _, _ = cli(self.arguments())
                self.assertEqual(code, 2)
                self.assertTrue(self.output.is_symlink())
                if target_exists:
                    self.assertEqual(target.read_text(), 'untouched\n')
                else:
                    self.assertFalse(target.exists())
                self.output.unlink()


if __name__ == '__main__':
    unittest.main(verbosity=2)
