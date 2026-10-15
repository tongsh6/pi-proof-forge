import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def test_pdf_names_are_readable_stable_and_sequenced_across_runs(tmp_path, monkeypatch):
    from tools.infra.export import resume_filename as names
    monkeypatch.setattr(names, '_today', lambda: '20261008')
    paths=[]
    for i in range(5):
        p=tmp_path/f'run{i}'/'resume.md';p.parent.mkdir()
        p.write_text('# 张三\n求职意向：测试公司 · 开发工程师\n正文'+str(i))
        paths.append(p)
    with ThreadPoolExecutor(max_workers=5) as pool:
        results=list(pool.map(lambda p:names.pdf_filename_for_resume(p,tmp_path/'outputs'),paths))
    assert set(results)=={f'张三-测试-开发-20261008.{i}.PDF' for i in range(1,6)}
    monkeypatch.setattr(names, '_today', lambda: '20261009')
    assert names.pdf_filename_for_resume(paths[0],tmp_path/'outputs')==results[0]
    paths[0].write_text(paths[0].read_text()+'新版本')
    assert names.pdf_filename_for_resume(paths[0],tmp_path/'outputs').endswith('-20261009.1.PDF')


def test_filename_uses_version_target_and_cleans_unsafe_components(tmp_path, monkeypatch):
    import hashlib
    from tools.infra.export import resume_filename as names
    monkeypatch.setattr(names, '_today', lambda: '20261008')
    p=tmp_path/'resume.md';p.write_text('# 张/三\n求职意向：旧公司 · 定位文案\n')
    p.with_suffix('.trace.json').write_text(json.dumps({'resume_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'target':{'company':'甲/乙:公司','target_role':'工程师'*100}}))
    name=names.pdf_filename_for_resume(p,tmp_path/'outputs')
    assert name.startswith('张_三-甲_-工程')
    assert name.endswith('-20261008.1.PDF') and len(name.encode())<255
    assert '/' not in name and ':' not in name
    p.write_text('# 李四\n')
    assert names.pdf_filename_for_resume(p,tmp_path/'outputs')=='李四-未指定公司-未指定岗位-20261008.1.PDF'


def test_company_role_abbreviations_fit_platform_and_sequence_collisions(tmp_path,monkeypatch):
    from tools.infra.export import resume_filename as names
    monkeypatch.setattr(names,'_today',lambda:'20261008')
    source=tmp_path/'resume.md';results=[]
    for i in range(12):
        source.write_text('# 林小明\n求职意向：上海示例电子有限公司 · 高级模拟芯片设计工程师\n'+str(i))
        filename=names.pdf_filename_for_resume(source,tmp_path/'outputs');results.append(filename)
        assert len(filename.encode('utf-16-le'))//2<=24
        assert filename.endswith(f'-20261008.{i+1}.PDF')
        assert '上海示例电子有限公司' in source.read_text()
    assert results[0]=='林小明-示例-模拟-20261008.1.PDF'
    assert len(set(results))==12


def test_quick_run_export_uses_shared_name(tmp_path,monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from tools.sidecar.handlers import agent
    monkeypatch.setattr(agent,'_PROJECT_ROOT',tmp_path)
    source=tmp_path/'outputs/r1/resume_mr-r1_A.md';source.parent.mkdir(parents=True)
    source.write_text('# 张三\n求职意向：某上海专业技术服务公司 · 高级全栈工程师\n')
    def render(src,dst):dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(b'%PDF-test')
    monkeypatch.setattr(agent,'markdown_to_pdf',render)
    result=agent._export_resume_pdf('r1',{'resume_dir':'outputs/r1'})
    day=datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d')
    assert Path(result).name==f'张三-某上海专业技术服务公司-高级全栈工程师-{day}.1.PDF'


def test_resume_center_directory_export_uses_readable_name(tmp_path,monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from tools.sidecar.handlers import resume
    root=tmp_path/'outputs';root.mkdir();src=root/'resume_mr-test_A.md'
    src.write_text('# 张三\n求职意向：某上海专业技术服务公司 · 高级全栈工程师\n')
    monkeypatch.setattr(resume,'_OUTPUTS_DIR',root)
    monkeypatch.setattr(resume,'markdown_to_pdf',lambda src,dst:dst.write_bytes(b'%PDF-test'))
    day=datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d')
    result=resume.handle_resume_export_pdf({'meta':{'correlation_id':'t'},'resume_id':'gen_resume_mr-test_A','destination':str(tmp_path/'export')+'/'})
    assert Path(result['path']).name==f'张三-某上海专业技术服务公司-高级全栈工程师-{day}.1.PDF'


def test_local_full_name_is_stable_without_changing_platform_filename(tmp_path, monkeypatch):
    from tools.infra.export import resume_filename as names
    monkeypatch.setattr(names,'_today',lambda:'20261014')
    src=tmp_path/'resume.md';src.write_text('# 童双龙\n求职意向：某上海专业技术服务公司 · 高级全栈工程师\n')
    outputs=tmp_path/'outputs'
    platform=names.pdf_filename_for_resume(src,outputs)
    local=names.pdf_filename_for_resume(src,outputs,readable=True)
    assert local=='童双龙-某上海专业技术服务公司-高级全栈工程师-20261014.1.PDF'
    names.check_platform_pdf_filename(platform)
    monkeypatch.setattr(names,'_today',lambda:'20261015')
    assert names.pdf_filename_for_resume(src,outputs)==platform
    assert names.pdf_filename_for_resume(src,outputs,readable=True)==local


def test_invalid_persisted_filename_cannot_escape_export_directory(tmp_path):
    import pytest
    from tools.infra.export import resume_filename as names
    src=tmp_path/'resume.md';src.write_text('# 张三\n')
    names.pdf_filename_for_resume(src,tmp_path/'outputs')
    registry=tmp_path/'outputs/.resume_pdf_names.json'
    value=json.loads(registry.read_text());value[next(iter(value))]='../escape.PDF'
    registry.write_text(json.dumps(value))
    with pytest.raises(ValueError,match='命名记录无效'):
        names.pdf_filename_for_resume(src,tmp_path/'outputs')


def test_case_only_company_names_do_not_overwrite_in_one_directory(tmp_path,monkeypatch):
    from tools.infra.export import resume_filename as names
    monkeypatch.setattr(names,'_today',lambda:'20261008')
    exports=tmp_path/'export';exports.mkdir();filenames=[]
    for i,company in enumerate(['Acme','acme']):
        source=tmp_path/f'resume{i}.md';source.write_text(f'# 张三\n求职意向：{company} · QA\n')
        filename=names.pdf_filename_for_resume(source,tmp_path/'outputs');filenames.append(filename)
        path=exports/filename
        assert not path.exists(), '自动命名不能覆盖既有版本'
        path.write_bytes(str(i).encode())
    assert filenames[1].endswith('.2.PDF')
    assert (exports/filenames[0]).read_bytes()==b'0'
