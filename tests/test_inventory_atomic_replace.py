"""Atomic inventory persistence under short Windows file locks."""
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from orbitflow.inventory import store


@pytest.mark.parametrize('failures', [1, 3, 4])
def test_windows_replace_permission_retry(tmp_path, monkeypatch, failures):
    path = tmp_path / 'inventory.json'
    path.write_text('{"previous": true}')
    inventory = store.JsonInventoryStore(path)
    original_replace = store.os.replace
    denied = PermissionError(13, 'synthetic access denied')
    calls = []

    def replace(source, destination):
        calls.append(source)
        assert json.loads(source.read_text()) == {'devices': {}}
        if len(calls) <= failures:
            raise denied
        original_replace(source, destination)

    monkeypatch.setattr(store, 'sys', SimpleNamespace(platform='win32'))
    monkeypatch.setattr(store.os, 'replace', replace)
    sleep = Mock()
    monkeypatch.setattr(store.time, 'sleep', sleep)
    if failures == 4:
        with pytest.raises(PermissionError) as caught:
            inventory._write({'devices': {}})
        assert caught.value is denied
        assert json.loads(path.read_text()) == {'previous': True}
    else:
        inventory._write({'devices': {}})
        assert json.loads(path.read_text()) == {'devices': {}}
    assert len(calls) == min(failures + 1, 4)
    assert sleep.call_count == min(failures, 3)
    assert sum(call.args[0] for call in sleep.call_args_list) <= 0.301
    assert not path.with_name('inventory.json.tmp').exists()


@pytest.mark.parametrize('platform,error', [
    ('linux', PermissionError(13, 'denied')),
    ('win32', OSError(28, 'disk full')),
    ('win32', FileNotFoundError(2, 'missing')),
])
def test_unrelated_replace_failure_not_retried(tmp_path, monkeypatch, platform, error):
    inventory = store.JsonInventoryStore(tmp_path / 'inventory.json')
    monkeypatch.setattr(store, 'sys', SimpleNamespace(platform=platform))
    replace = Mock(side_effect=error)
    sleep = Mock()
    monkeypatch.setattr(store.os, 'replace', replace)
    monkeypatch.setattr(store.time, 'sleep', sleep)
    with pytest.raises(type(error)) as caught:
        inventory._write({'devices': {}})
    assert caught.value is error
    replace.assert_called_once()
    sleep.assert_not_called()
    assert list(tmp_path.iterdir()) == []


def test_serialization_failure_cleans_temp_without_replace(tmp_path, monkeypatch):
    replace = Mock()
    monkeypatch.setattr(store.os, 'replace', replace)
    with pytest.raises(TypeError):
        store.JsonInventoryStore(tmp_path / 'inventory.json')._write({'invalid': object()})
    replace.assert_not_called()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('winerror', [5, 32, 33])
def test_equivalent_windows_access_denial(tmp_path, monkeypatch, winerror):
    original_replace = store.os.replace
    error = OSError('Windows file lock')
    error.winerror = winerror
    calls = []

    def replace(source, destination):
        calls.append(1)
        if len(calls) == 1:
            raise error
        original_replace(source, destination)

    monkeypatch.setattr(store, 'sys', SimpleNamespace(platform='win32'))
    monkeypatch.setattr(store.os, 'replace', replace)
    monkeypatch.setattr(store.time, 'sleep', Mock())
    path = tmp_path / 'inventory.json'
    store.JsonInventoryStore(path)._write({'devices': {}})
    assert calls == [1, 1]
    assert json.loads(path.read_text()) == {'devices': {}}
    assert list(tmp_path.iterdir()) == [path]


def test_cleanup_denial_preserves_original_failure(tmp_path, monkeypatch):
    inventory = store.JsonInventoryStore(tmp_path / 'inventory.json')
    error = OSError(28, 'disk full')
    monkeypatch.setattr(store.os, 'replace', Mock(side_effect=error))
    with monkeypatch.context() as cleanup_patch:
        cleanup_patch.setattr(store.Path, 'unlink', Mock(side_effect=PermissionError('locked')))
        with pytest.raises(OSError) as caught:
            inventory._write({'devices': {}})
        assert caught.value is error
    inventory.path.with_name('inventory.json.tmp').unlink()
