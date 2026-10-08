"""使用隔离存储验证凭据恢复与退出/删除的区别。"""
import json
from pathlib import Path

import pytest

from tools.infra.liepin_readonly import LiepinReadOnlySession


class Store:
    path = Path('/isolated-test/liepin-token')

    def __init__(self):
        self.token = None
        self.loads = 0
        self.fail = ''

    def load(self):
        self.loads += 1
        if self.fail == 'load':
            raise OSError('private-storage-error')
        return self.token

    def save(self, token):
        if self.fail == 'save':
            raise OSError('private-storage-error')
        self.token = token

    def delete(self):
        if self.fail == 'delete':
            raise OSError('private-storage-error')
        self.token = None


def test_constructor_does_not_read_and_restart_restores_unverified():
    store = Store()
    first = LiepinReadOnlySession(store=store)
    assert store.loads == 0
    saved = first.configure('synthetic-token')
    assert saved['storage'] == 'local_file'
    assert saved['saved'] is True
    first.unload()
    assert store.token == 'synthetic-token'
    second = LiepinReadOnlySession(store=store)
    restored = second.snapshot()
    assert restored['configured'] is True
    assert restored['state'] == 'unverified'
    assert restored['last_checked_at'] == ''
    assert 'synthetic-token' not in json.dumps(restored)


def test_explicit_delete_is_the_only_action_that_removes_saved_token():
    store = Store()
    session = LiepinReadOnlySession(store=store)
    session.configure('synthetic-token')
    cleared = session.clear()
    assert store.token is None
    assert cleared['configured'] is False
    assert cleared['saved'] is False
    assert LiepinReadOnlySession(store=store).snapshot()['configured'] is False


@pytest.mark.parametrize('invalid', ['', '  ', 'bad\nheader', None, 42])
def test_invalid_replacement_preserves_saved_token(invalid):
    store = Store()
    session = LiepinReadOnlySession(store=store)
    session.configure('original-token')
    auth = session.configure(invalid)
    assert auth['code'] == 'INVALID_INPUT'
    assert store.token == 'original-token'
    assert auth['configured'] and auth['saved']


@pytest.mark.parametrize('operation', ['load', 'save', 'delete'])
def test_storage_failure_is_visible_and_never_leaks_details(operation):
    store = Store()
    session = LiepinReadOnlySession(store=store)
    if operation != 'load':
        session.configure('original-token')
    store.fail = operation
    auth = (session.snapshot() if operation == 'load' else
            session.configure('replacement-token') if operation == 'save' else session.clear())
    assert auth['code'] == 'CREDENTIAL_STORAGE_ERROR'
    assert auth['state'] == 'error'
    if operation != 'load':
        assert store.token == 'original-token'
        assert auth['saved'] is True
    assert not any(secret in json.dumps(auth) for secret in
                   ['private-storage-error', 'original-token', 'replacement-token'])


def test_corrupt_saved_value_blocks_requests_without_echo():
    store = Store()
    store.token = 'bad\nsecret-header'
    session = LiepinReadOnlySession(store=store)
    result = session.read_resume()
    assert result['code'] == 'CREDENTIAL_STORAGE_ERROR'
    assert not result['auth']['configured']
    assert 'secret-header' not in json.dumps(result)


def test_load_failure_can_be_retried_after_permissions_are_fixed():
    store = Store()
    store.token = 'synthetic-token'
    store.fail = 'load'
    session = LiepinReadOnlySession(store=store)
    assert session.snapshot()['code'] == 'CREDENTIAL_STORAGE_ERROR'
    store.fail = ''
    assert session.snapshot()['state'] == 'unverified'


def test_real_stdio_shutdown_eof_and_new_process_preserve_until_explicit_delete(tmp_path):
    import subprocess
    import sys

    path = tmp_path.resolve() / 'credentials' / 'liepin-token'
    root = Path(__file__).resolve().parents[3]
    bootstrap = '''
import runpy, sys
from pathlib import Path
from tools.infra.liepin_readonly import liepin_readonly
from tools.infra.liepin_token_file import LiepinTokenFile
liepin_readonly._store = LiepinTokenFile(Path(sys.argv[1]))
liepin_readonly.unload()
runpy.run_module('tools.sidecar.server', run_name='__main__')
'''

    def run(*requests):
        data = '\n'.join(json.dumps({
            'jsonrpc': '2.0', 'id': index, 'method': method,
            'params': {'meta': {'correlation_id': 'isolated-restart'}, **params},
        }) for index, (method, params) in enumerate(requests)) + '\n'
        result = subprocess.run([sys.executable, '-c', bootstrap, str(path)],
                                input=data, text=True, capture_output=True,
                                cwd=root, timeout=15, check=True)
        assert 'synthetic-stdio-token' not in result.stdout + result.stderr
        responses = [json.loads(line)['result'] for line in result.stdout.splitlines()]
        return responses

    saved, shutdown = run(
        ('settings.liepinCredential', {'action': 'set', 'token': 'synthetic-stdio-token'}),
        ('system.shutdown', {}),
    )
    assert saved['auth']['saved'] and shutdown['accepted']
    # 第二进程由 EOF 正常退出；该路径也必须保留本地保存项。
    restored, = run(('settings.get', {}))
    assert restored['liepin_api']['state'] == 'unverified'
    assert restored['liepin_api']['configured']
    assert path.read_text() == 'synthetic-stdio-token'
    cleared, = run(('settings.liepinCredential', {'action': 'clear'}))
    assert not cleared['auth']['saved']
    missing, = run(('settings.get', {}))
    assert not missing['liepin_api']['configured']
    assert not path.exists()
