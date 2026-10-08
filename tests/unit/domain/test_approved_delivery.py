from dataclasses import replace

from tools.channels.base import DeliveryRequest
from tools.domain.result import Err, Ok
from tools.domain.value_objects import DeliveryResult
from tools.orchestration.approved_delivery import deliver_once


class Channel:
    channel_id = 'liepin'

    def __init__(self, *, crash=False, receipt='receipt-1'):
        self.calls = 0
        self.crash = crash
        self.receipt = receipt

    def deliver(self, request):
        self.calls += 1
        if self.crash:
            raise TimeoutError('unknown remote outcome')
        return Ok(DeliveryResult('liepin', True, self.receipt, 'confirmed'))


def request():
    return DeliveryRequest('run-a', 'candidate-a', 'liepin', '/test-only.pdf',
        'https://www.liepin.com/job/123.shtml?mscid=a', False,
        {'platform_job_id':'123','platform_job_type':'2','resume_pdf_sha256':'test-digest'})


def test_duplicate_approval_different_run_and_resume_never_resends(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    channel = Channel()
    first = deliver_once(request(), [channel], source='legacy')
    assert isinstance(first, Ok) and first.value.success
    second = replace(request(), run_id='run-b', candidate_id='candidate-b',
                     metadata={**request().metadata, 'resume_pdf_sha256':'new-version'})
    result = deliver_once(second, [channel], source='legacy')
    assert isinstance(result, Err) and result.error.reason == 'delivery_already_attempted'
    assert channel.calls == 1


def test_unknown_result_is_reserved_and_missing_receipt_is_not_success(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    channel = Channel(crash=True)
    assert isinstance(deliver_once(request(), [channel], source='legacy'), Err)
    channel.crash = False
    assert isinstance(deliver_once(request(), [channel], source='legacy'), Err)
    assert channel.calls == 1
    missing = Channel(receipt='')
    other = replace(request(), metadata={**request().metadata,'platform_job_id':'456'})
    result = deliver_once(other, [missing], source='legacy')
    assert isinstance(result, Err) and result.error.reason == 'delivery_receipt_missing'


def test_official_contract_and_dry_run_do_not_reserve_or_call_channel(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    channel = Channel()
    assert isinstance(deliver_once(request(), [channel], source='liepin_official'), Err)
    assert isinstance(deliver_once(replace(request(), dry_run=True), [channel], source='legacy'), Err)
    assert channel.calls == 0
    assert not (tmp_path/'outputs/submissions/delivery_attempts.sqlite3').exists()


def test_confirmed_check_mode_does_not_block_later_authorized_attempt(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    channel = Channel()
    monkeypatch.setattr(channel, 'deliver', lambda _: Ok(DeliveryResult(
        'liepin', False, '', 'check only', outcome='not_submitted')))
    result = deliver_once(request(), [channel], source='legacy')
    assert isinstance(result, Ok) and not result.value.success
    actual = Channel()
    assert isinstance(deliver_once(request(), [actual], source='legacy'), Ok)
    assert actual.calls == 1
