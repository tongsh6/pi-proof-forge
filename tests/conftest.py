"""测试凭据隔离：所有默认单例只使用临时目录，不碰用户保存项。"""
import pytest


@pytest.fixture(autouse=True)
def isolated_liepin_credentials(tmp_path_factory, monkeypatch):
    from tools.infra.liepin_readonly import liepin_readonly
    from tools.infra.liepin_token_file import LiepinTokenFile

    liepin_readonly.unload()
    root = tmp_path_factory.mktemp('isolated-liepin')
    monkeypatch.setattr(liepin_readonly, '_store',
                        LiepinTokenFile(root / 'credentials' / 'liepin-token'))
    yield
    liepin_readonly.unload()
