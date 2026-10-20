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


@pytest.fixture(autouse=True)
def isolated_llm_credentials(tmp_path_factory, monkeypatch):
    """LLM 密钥测试只使用临时目录，不读取或写入用户真实凭据。"""
    root = tmp_path_factory.mktemp('isolated-llm-credentials')
    monkeypatch.setenv('PPF_CREDENTIAL_DIR', str(root / 'credentials'))
    for name in ('LLM_API_KEY', 'LLM_THINKING', 'LLM_PROVIDER', 'LLM_MODEL', 'LLM_BASE_URL'):
        monkeypatch.delenv(name, raising=False)
    yield

