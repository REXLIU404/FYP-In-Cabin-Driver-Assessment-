"""Vision orchestration boundaries: fake MPS, synthetic artifacts, no training/data."""
import importlib
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def vision():
    try:
        return importlib.import_module('ml.experiments.run_vision_hpo')
    except ModuleNotFoundError as error:
        if error.name != 'ml.experiments.run_vision_hpo':
            raise
        class MissingVision:
            def __getattr__(self, name):
                pytest.fail('Missing bounded vision HPO orchestration implementation')
        return MissingVision()


@pytest.fixture
def context():
    return {'environment': {'git': {'head': 'synthetic', 'dirty_state': ''}},
            'weights_manifest': {}, 'source_hashes': {}, 'protocol_sha256': 'synthetic',
            'data_root': '/synthetic/not-opened'}


def plan(trial_id='search_001'):
    return {'trial_id': trial_id, 'model': 'resnet18', 'role': 'SEARCH', 'seed': 42,
            'config': {'learning_rate': 0.0001, 'weight_decay': 0.0001},
            'max_epochs': 8, 'is_p2': trial_id == 'search_001'}


def synthetic_worker(command, log_path, timeout):
    """Only filesystem contract outputs; never import a trainer or load data."""
    attempt = Path(command[command.index('--attempt-dir') + 1])
    metrics = {'status': 'COMPLETED', 'macro_f1': 0.75, 'log_loss': 0.5,
               'best_epoch': 1, 'all_losses_and_probabilities_finite': True,
               'reload_verified': True, 'test_predictions': 0,
               'epochs': [{'epoch': 1, 'train_seconds': 2.0, 'validation_seconds': 1.0}]}
    (attempt / 'validation_metrics.json').write_text(json.dumps(metrics))
    (attempt/'checkpoint.pt').write_bytes(b'synthetic artifact, no model')
    for name in ['class_report.json','selection_log.json','predictions_validation.csv','timing_samples.csv','trials.csv']:
        (attempt/name).write_text('{}\n' if name.endswith('.json') else 'synthetic\n')
    records={p.name:{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
             for p in attempt.iterdir() if p.is_file()}
    (attempt / 'artifact_manifest.json').write_text(json.dumps({'status': 'COMPLETED', 'test_images_opened': 0,'artifacts':records}))
    Path(log_path).write_text('synthetic worker only\n')
    return {'status': 'COMPLETED', 'returncode': 0, 'wall_seconds': 0.02,
            'timeout_seconds': timeout}


def test_missing_numeric_budget_refuses_without_creating_approval(vision, tmp_path):
    path = tmp_path / 'approved_vision_budget.json'
    with pytest.raises((ValueError, FileNotFoundError), match='budget|预算|approved'):
        vision.load_approved_budget(path)
    assert not path.exists()


@pytest.mark.parametrize('payload', [
    {'launch_authorized': False, 'per_trial': 1, 'per_model': 2, 'total': 3},
    {'launch_authorized': True, 'per_trial': None, 'per_model': 2, 'total': 3},
    {'launch_authorized': True, 'per_trial': True, 'per_model': 2, 'total': 3},
    {'launch_authorized': True, 'per_trial': 1, 'per_model': 2, 'total': float('inf')},
])
def test_incomplete_or_nonfinite_budget_is_not_authorization(vision, tmp_path, payload):
    path = tmp_path / 'approval.json'
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        vision.load_approved_budget(path)


def test_no_mps_refuses_even_when_cpu_is_available(vision, monkeypatch):
    fake = SimpleNamespace(backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: False)))
    monkeypatch.setitem(sys.modules, 'torch', fake)
    with pytest.raises(ValueError, match='MPS'):
        vision.require_mps()


def test_resume_skips_completed_attempt_and_preserves_directory(vision, tmp_path, context):
    budget = {'per_trial': 10.0, 'per_model': 20.0, 'total': 30.0}
    first = vision.run_plan(tmp_path, 'search', [plan()], budget, context, runner=synthetic_worker)
    assert first['attempts'][0]['status'] == 'COMPLETED'
    attempt = tmp_path / first['attempts'][0]['directory']
    before = {str(p.relative_to(attempt)): (p.read_bytes(), p.stat().st_mtime_ns)
              for p in attempt.rglob('*') if p.is_file()}

    def forbidden(*args, **kwargs):
        pytest.fail('A completed trial must not launch another worker')

    again = vision.run_plan(tmp_path, 'search', [plan()], budget, context, runner=forbidden)
    after = {str(p.relative_to(attempt)): (p.read_bytes(), p.stat().st_mtime_ns)
             for p in attempt.rglob('*') if p.is_file()}
    assert len(again['attempts']) == 1
    assert before == after


def test_ctrl_c_is_retained_as_interrupted_then_new_attempt(vision, tmp_path, context):
    budget = {'per_trial': 5.0, 'per_model': 20.0, 'total': 30.0}

    def interrupt(*args, **kwargs):
        time.sleep(0.02)
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        vision.run_plan(tmp_path, 'search', [plan()], budget, context, runner=interrupt)
    state = json.loads((tmp_path / 'search_state.json').read_text())
    assert state['attempts'][0]['status'] == 'INTERRUPTED'
    assert state['attempts'][0]['wall_seconds'] > 0
    previous_usage = state['used_wall_seconds']
    seen_timeout = []

    def rerun(command, log_path, timeout):
        seen_timeout.append(timeout)
        return synthetic_worker(command, log_path, timeout)

    again = vision.run_plan(tmp_path, 'search', [plan()], budget, context, runner=rerun)
    assert [row['status'] for row in again['attempts']] == ['INTERRUPTED', 'COMPLETED']
    assert again['attempts'][0]['directory'] != again['attempts'][1]['directory']
    assert seen_timeout[0] < 5.0
    assert again['used_wall_seconds'] >= previous_usage


def test_hard_wall_kills_blocked_child_including_pre_training_load(vision, tmp_path):
    started = time.monotonic()
    result = vision.supervise([sys.executable, '-c', 'import time; time.sleep(30)'],
                              tmp_path / 'child.log', 0.08)
    assert result['status'] == 'TIME_BUDGET_EXCEEDED'
    assert time.monotonic() - started < 2.0
    assert result['wall_seconds'] >= 0.08


def test_wall_limit_stops_and_marks_remaining_without_reset(vision, tmp_path, context):
    budget = {'per_trial': 0.1, 'per_model': 1.0, 'total': 2.0}

    def timeout(command, log_path, seconds):
        return {'status': 'TIME_BUDGET_EXCEEDED', 'returncode': -9,
                'wall_seconds': 0.1, 'timeout_seconds': seconds}

    state = vision.run_plan(tmp_path, 'search', [plan(), plan('search_002')],
                            budget, context, runner=timeout)
    assert state['status'] == 'PARTIAL'
    assert state['attempts'][0]['status'] == 'TIME_BUDGET_EXCEEDED'
    assert state['trials']['resnet18/search_001']['status'] == 'NOT_RUN_BUDGET'
    assert state['trials']['resnet18/search_002']['status'] == 'NOT_RUN_BUDGET'
    assert len(state['attempts']) == 1
    state = vision.run_plan(tmp_path, 'search', [plan(), plan('search_002')],
                            budget, context, runner=lambda *a: pytest.fail('budget must not reset'))
    assert len(state['attempts']) == 1


def test_running_attempt_after_parent_crash_becomes_interrupted(vision, tmp_path, context):
    budget = {'per_trial': 10.0, 'per_model': 20.0, 'total': 30.0}
    # Simulate a parent dying between launching the worker and saving its result.
    def crash(command, log_path, timeout):
        raise SystemExit(9)

    with pytest.raises(SystemExit):
        vision.run_plan(tmp_path, 'search', [plan()], budget, context, runner=crash)
    state = vision.run_plan(tmp_path, 'search', [plan()], budget, context, runner=synthetic_worker)
    assert [a['status'] for a in state['attempts']] == ['INTERRUPTED', 'COMPLETED']


def test_changed_resume_config_refuses_instead_of_mixing_evidence(vision, tmp_path, context):
    budget = {'per_trial': 10.0, 'per_model': 20.0, 'total': 30.0}
    vision.run_plan(tmp_path, 'search', [plan()], budget, context, runner=synthetic_worker)
    changed = plan()
    changed['config']['learning_rate'] = 0.9
    with pytest.raises(ValueError, match='changed|mismatch|改变'):
        vision.run_plan(tmp_path, 'search', [changed], budget, context, runner=synthetic_worker)


def test_probe_estimate_is_time_only_and_eight_by_eight(vision):
    proposal = vision.budget_proposal({'mobilenet_v3_large': {'epochs': [
        {'epoch': 1, 'train_seconds': 10.0, 'validation_seconds': 2.0}]},
        'resnet18': {'epochs': [{'epoch': 1, 'train_seconds': 20.0, 'validation_seconds': 4.0}]}})
    assert proposal['models']['mobilenet_v3_large']['estimated_seconds'] == pytest.approx(883.2)
    assert proposal['models']['resnet18']['estimated_seconds'] == pytest.approx(1766.4)
    assert proposal['estimated_total_seconds'] == pytest.approx(2649.6)
    assert proposal['launch_authorized'] is False
    assert proposal['probe_used_for_selection'] is False


def test_weight_integrity_failure_never_rewrites_manifest(vision, tmp_path, monkeypatch):
    cache = tmp_path / 'cache'
    cache.mkdir()
    (cache / 'mobilenet_v3_large-5c1a4163.pth').write_bytes(b'corrupt')
    monkeypatch.setattr(vision, 'weights_cache', lambda: cache)
    with pytest.raises(ValueError, match='hash|checksum|SHA'):
        vision.cached_weight_records(require_resnet=False)
    assert not (tmp_path / 'weights_manifest.json').exists()


def test_attempt_preparation_cannot_add_time_outside_trial_budget(vision,tmp_path,context,monkeypatch):
    original=vision.atomic_json
    def slow(path,value):
        time.sleep(.02)
        return original(path,value)
    monkeypatch.setattr(vision,'atomic_json',slow)
    state=vision.run_plan(tmp_path,'probe',[plan()],{'per_trial':.01,'per_model':1.,'total':2.},context,
                          runner=lambda *a:pytest.fail('Expired preparation budget must not start a worker'))
    assert state['status']=='PARTIAL'


@pytest.mark.parametrize('damage',['delete','change'])
def test_completed_checkpoint_damage_refuses_resume_without_retraining(vision,tmp_path,context,damage):
    budget={'per_trial':10.,'per_model':20.,'total':30.}
    state=vision.run_plan(tmp_path,'search',[plan()],budget,context,runner=synthetic_worker)
    checkpoint=tmp_path/state['attempts'][0]['directory']/'checkpoint.pt'
    if damage=='delete':checkpoint.unlink()
    else:checkpoint.write_bytes(b'changed')
    with pytest.raises(ValueError,match='artifact|checkpoint|integrity'):
        vision.run_plan(tmp_path,'search',[plan()],budget,context,
                        runner=lambda *a:pytest.fail('Damaged completed artifact cannot trigger automatic retraining'))


def test_second_launcher_cannot_mutate_or_kill_active_run(vision,tmp_path,context):
    budget={'per_trial':10.,'per_model':20.,'total':30.}
    def active_worker(command,log_path,timeout):
        before=(tmp_path/'search_state.json').read_bytes()
        with pytest.raises(ValueError,match='ALREADY_RUNNING'):
            vision.run_plan(tmp_path,'search',[plan()],budget,context,
                            runner=lambda *a:pytest.fail('Second launcher started a worker'))
        assert (tmp_path/'search_state.json').read_bytes()==before
        return synthetic_worker(command,log_path,timeout)
    result=vision.run_plan(tmp_path,'search',[plan()],budget,context,runner=active_worker)
    assert len(result['attempts'])==1 and result['status']=='COMPLETED'


def test_external_sigterm_is_an_interruption_not_an_implementation_failure(vision,tmp_path):
    import os
    import signal
    result=vision.supervise([sys.executable,'-c','import os,signal;os.kill(os.getpid(),signal.SIGTERM)'],
                            tmp_path/'signal.log',5.)
    assert result['returncode']==-signal.SIGTERM
    assert result['status']=='INTERRUPTED'


def test_signal_interruption_can_resume_without_discarding_attempt_or_budget(vision,tmp_path,context):
    budget={'per_trial':10.,'per_model':20.,'total':30.}
    first=vision.run_plan(tmp_path,'probe',[plan()],budget,context,
        runner=lambda *a:{'status':'INTERRUPTED','returncode':-15,'wall_seconds':.03,'timeout_seconds':10.})
    assert first['status']=='INTERRUPTED'
    result=vision.run_plan(tmp_path,'probe',[plan()],budget,context,runner=synthetic_worker)
    assert [a['status'] for a in result['attempts']]==['INTERRUPTED','COMPLETED']
    assert result['used_wall_seconds']>=first['used_wall_seconds']
    assert result['attempts'][1]['timeout_seconds']<10.


def test_recovery_refuses_to_signal_worker_with_live_controller(vision,tmp_path,monkeypatch):
    import os
    import signal
    target=tmp_path/'attempt';target.mkdir()
    (target/'process.json').write_text(json.dumps({'pid':12345,'command':[]}))
    state={'used_wall_seconds':2.,'attempts':[{'status':'RUNNING','directory':'attempt',
           'timeout_seconds':10.,'started_wall_time':time.time(),'wall_seconds':0.}]}
    def inspect(command,*args,**kwargs):
        fields=command[command.index('-o')+1]
        text=' 42 /repo/ml/vision/train_hpo.py --attempt-dir '+str(target) if fields=='ppid=,command=' else 'python /repo/ml/experiments/run_vision_hpo.py probe --run-id '+tmp_path.name
        return SimpleNamespace(stdout=text,returncode=0)
    monkeypatch.setattr(vision.subprocess,'run',inspect)
    monkeypatch.setattr(vision.os,'killpg',lambda *a:pytest.fail('Live worker was signalled'))
    with pytest.raises(ValueError,match='ALREADY_RUNNING'):
        vision._recover_running(tmp_path,state)
    assert state['attempts'][0]['status']=='RUNNING'


def test_failed_run_retry_does_not_consume_budget_without_starting_a_worker(vision,tmp_path,context):
    budget={'per_trial':10.,'per_model':20.,'total':30.}
    first=vision.run_plan(tmp_path,'probe',[plan()],budget,context,
        runner=lambda *a:{'status':'IMPLEMENTATION_FAILED','returncode':1,'wall_seconds':.03})
    original=(tmp_path/'probe_state.json').read_bytes()
    again=vision.run_plan(tmp_path,'probe',[plan()],budget,context,
        runner=lambda *a:pytest.fail('An implementation failure cannot automatically rerun'))
    assert again['used_wall_seconds']==first['used_wall_seconds']
    assert (tmp_path/'probe_state.json').read_bytes()==original


def legacy_probe_fixture(vision,directory,context):
    import copy
    from ml.experiments import comparator_common as common
    old=copy.deepcopy(context)
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=common.ROOT,text=True).strip()
    old['environment']['git']['head']=head
    source_names=['ml/experiments/run_vision_hpo.py','ml/vision/train_hpo.py',
                  'ml/experiments/hpo_protocol.py','ml/experiments/comparator_common.py']
    old_controller=subprocess.check_output(['git','show',f'{head}:{source_names[0]}'],cwd=common.ROOT)
    old['source_hashes']={n:hashlib.sha256((common.ROOT/n).read_bytes()).hexdigest() for n in source_names}
    old['source_hashes'][source_names[0]]=hashlib.sha256(old_controller).hexdigest()
    current=copy.deepcopy(old)
    current['source_hashes'][source_names[0]]=hashlib.sha256((common.ROOT/source_names[0]).read_bytes()).hexdigest()
    plans=[{'trial_id':'probe_001','model':m,'role':'PROBE','seed':42,
            'config':{'learning_rate':.0008,'weight_decay':.0001},'max_epochs':1,'is_p2':False}
           for m in ['mobilenet_v3_large','resnet18']]
    budget={'per_trial':1200,'per_model':1200,'total':2400}
    signature=hashlib.sha256(json.dumps({'plans':plans,'budget':budget,'context':old},sort_keys=True).encode()).hexdigest()
    attempts=[]
    for number,status,wall in [(1,'INTERRUPTED',30.797756583080627),(2,'IMPLEMENTATION_FAILED',27.519550209050067)]:
        relative=f'probe/mobilenet_v3_large/probe_001/attempt_{number:02d}'
        target=directory/relative;target.mkdir(parents=True)
        (target/'execution.log').write_text('original captured log\n')
        row={'key':'mobilenet_v3_large/probe_001','plan':plans[0],'directory':relative,
             'status':status,'wall_seconds':wall,'timeout_seconds':1200}
        if number==2:row['execution']={'status':'IMPLEMENTATION_FAILED','returncode':-15,'wall_seconds':wall}
        attempts.append(row)
    state={'signature':signature,'phase':'probe','status':'IMPLEMENTATION_FAILED','attempts':attempts,
           'trials':{'mobilenet_v3_large/probe_001':{'status':'IMPLEMENTATION_FAILED','attempt':attempts[-1]['directory']}},
           'selection':{},'used_wall_seconds':78.09884787490591}
    (directory/'probe_config.json').write_text(json.dumps(old))
    (directory/'probe_state.json').write_text(json.dumps(state))
    return old,current,state


def test_legacy_sigterm_recovery_preserves_evidence_budget_and_source_versions(vision,tmp_path,context):
    old,current,state=legacy_probe_fixture(vision,tmp_path,context)
    old_state=(tmp_path/'probe_state.json').read_bytes()
    old_context=(tmp_path/'probe_config.json').read_bytes()
    logs={str(p):p.read_bytes() for p in tmp_path.rglob('execution.log')}
    recovered=vision.recover_probe_interruption(tmp_path,old,current)
    assert recovered['status']=='INTERRUPTED'
    assert recovered['used_wall_seconds']==state['used_wall_seconds']
    assert len(recovered['attempts'])==2
    assert recovered['attempts'][-1]['status']=='INTERRUPTED'
    assert recovered['attempts'][-1]['original_status']=='IMPLEMENTATION_FAILED'
    assert recovered['attempts'][-1]['execution']['returncode']==-15
    assert (tmp_path/'probe_config.json').read_bytes()==old_context
    audit_dir=(tmp_path/recovered['context_file']).parent
    assert (audit_dir/'probe_state.json').read_bytes()==old_state
    assert json.loads((tmp_path/recovered['context_file']).read_text())==current
    for p,wanted in logs.items():assert Path(p).read_bytes()==wanted
    assert not (tmp_path/'probe/mobilenet_v3_large/probe_001/attempt_03').exists()


@pytest.mark.parametrize('change',['trainer','weights','data_root','protocol','ordinary_failure','budget'])
def test_legacy_recovery_refuses_recipe_drift_or_genuine_failure(vision,tmp_path,context,change):
    old,current,state=legacy_probe_fixture(vision,tmp_path,context)
    if change=='trainer':current['source_hashes']['ml/vision/train_hpo.py']='changed'
    elif change=='weights':current['weights_manifest']={'changed':True}
    elif change=='data_root':current['data_root']='/changed'
    elif change=='protocol':current['protocol_sha256']='changed'
    elif change=='ordinary_failure':state['attempts'][-1]['execution']['returncode']=1
    elif change=='budget':state['used_wall_seconds']=2400
    (tmp_path/'probe_state.json').write_text(json.dumps(state))
    before=(tmp_path/'probe_state.json').read_bytes()
    with pytest.raises(ValueError):vision.recover_probe_interruption(tmp_path,old,current)
    assert (tmp_path/'probe_state.json').read_bytes()==before
    assert list(tmp_path.glob('recovery_*'))==[]


def test_recovery_cli_context_can_resume_the_identical_probe(vision,tmp_path,context,monkeypatch):
    import copy
    from ml.experiments import comparator_common as common
    configured=copy.deepcopy(context)
    configured['environment']['git']={'head':'synthetic','dirty_state_at_first_start':''}
    configured['protocol_sha256']=common.sha256(vision.protocol.CONFIG)
    configured['data_root']=str(common.DEFAULT_DATA)
    old,current,before=legacy_probe_fixture(vision,tmp_path,configured)
    environment=copy.deepcopy(old['environment'])
    environment['git']['dirty_state']=environment['git'].pop('dirty_state_at_first_start')
    monkeypatch.setattr(vision,'cached_weight_records',lambda:{})
    args=SimpleNamespace(command='recover-interrupted',data_root=common.DEFAULT_DATA)
    with vision.run_lock(tmp_path):
        assert vision._execute_command(args,tmp_path,copy.deepcopy(environment),{},None)==0
    recovered=json.loads((tmp_path/'probe_state.json').read_text())
    assert len(recovered['attempts'])==2
    assert recovered['used_wall_seconds']==before['used_wall_seconds']
    run_plan=vision._run_plan
    def run_synthetic(directory,phase,plans,budget,context,entry_started=None):
        return run_plan(directory,phase,plans,budget,context,runner=synthetic_worker)
    monkeypatch.setattr(vision,'_run_plan',run_synthetic)
    args.command='probe'
    with vision.run_lock(tmp_path):
        assert vision._execute_command(args,tmp_path,copy.deepcopy(environment),{},None)==0
    state=json.loads((tmp_path/'probe_state.json').read_text())
    assert [a['status'] for a in state['attempts']]==['INTERRUPTED','INTERRUPTED','COMPLETED','COMPLETED']
    assert state['used_wall_seconds']>=before['used_wall_seconds']
    assert state['attempts'][2]['timeout_seconds']<1200
    assert state['status']=='COMPLETED'


def model_plans(model):
    return [{**plan(f'search_{number:03d}'),'model':model} for number in [1,2]]


@pytest.mark.parametrize('scope',['per_trial','per_model'])
def test_mobilenet_budget_stop_does_not_cancel_resnet(vision,tmp_path,context,monkeypatch,scope):
    clock=[0.]
    monkeypatch.setattr(vision.time,'monotonic',lambda:clock[0])
    plans=model_plans('mobilenet_v3_large')+model_plans('resnet18')
    budget={'per_trial':.5 if scope=='per_trial' else 10.,
            'per_model':{'mobilenet_v3_large':.5 if scope=='per_model' else 10.,'resnet18':10.},'total':20.}
    called=[]
    def worker(command,log_path,timeout):
        row=json.loads((Path(log_path).parent/'config.json').read_text())['plan'];called.append(row['model'])
        if row['model']=='mobilenet_v3_large':
            clock[0]+=timeout
            return {'status':'TIME_BUDGET_EXCEEDED','returncode':-15,'wall_seconds':timeout}
        result=synthetic_worker(command,log_path,timeout);clock[0]+=.1;result['wall_seconds']=.1
        return result
    state=vision.run_plan(tmp_path,'search',plans,budget,context,runner=worker)
    assert called==['mobilenet_v3_large','resnet18','resnet18']
    assert state['status']=='PARTIAL'
    assert state['model_budget_stops']['mobilenet_v3_large']['scope']==scope
    assert state['trials']['mobilenet_v3_large/search_001']['status']=='NOT_RUN_BUDGET'
    assert state['trials']['mobilenet_v3_large/search_002']['status']=='NOT_RUN_BUDGET'
    assert state['trials']['resnet18/search_002']['status']=='COMPLETED'
    original=(tmp_path/'search_state.json').read_bytes()
    vision.run_plan(tmp_path,'search',plans,budget,context,runner=lambda *a:pytest.fail('Terminal model budgets must not reset'))
    assert (tmp_path/'search_state.json').read_bytes()==original


def test_total_budget_stops_both_models_and_cannot_reset(vision,tmp_path,context,monkeypatch):
    clock=[0.];monkeypatch.setattr(vision.time,'monotonic',lambda:clock[0])
    plans=model_plans('mobilenet_v3_large')+model_plans('resnet18')
    budget={'per_trial':10.,'per_model':10.,'total':.5};called=[]
    def worker(command,log_path,timeout):
        called.append(str(log_path));clock[0]+=timeout
        return {'status':'TIME_BUDGET_EXCEEDED','returncode':-15,'wall_seconds':timeout}
    state=vision.run_plan(tmp_path,'search',plans,budget,context,runner=worker)
    assert len(called)==1 and state['status']=='NOT_RUN_BUDGET' and state['budget_stop_scope']=='total'
    assert all(row['status']=='NOT_RUN_BUDGET' for row in state['trials'].values())
    before=(tmp_path/'search_state.json').read_bytes()
    vision.run_plan(tmp_path,'search',plans,budget,context,runner=lambda *a:pytest.fail('Global cap must not reset'))
    assert (tmp_path/'search_state.json').read_bytes()==before


def test_other_model_resumes_after_interrupt_without_reopening_stopped_model(vision,tmp_path,context,monkeypatch):
    clock=[0.];monkeypatch.setattr(vision.time,'monotonic',lambda:clock[0])
    plans=model_plans('mobilenet_v3_large')+model_plans('resnet18')
    budget={'per_trial':.5,'per_model':10.,'total':20.}
    def worker(command,log_path,timeout):
        row=json.loads((Path(log_path).parent/'config.json').read_text())['plan']
        clock[0]+=.1
        if row['model']=='mobilenet_v3_large':
            return {'status':'TIME_BUDGET_EXCEEDED','returncode':-15,'wall_seconds':timeout}
        raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):vision.run_plan(tmp_path,'search',plans,budget,context,runner=worker)
    interrupted=json.loads((tmp_path/'search_state.json').read_text())
    def resume(command,log_path,timeout):
        row=json.loads((Path(log_path).parent/'config.json').read_text())['plan']
        assert row['model']=='resnet18'
        return synthetic_worker(command,log_path,timeout)
    state=vision.run_plan(tmp_path,'search',plans,budget,context,runner=resume)
    assert state['status']=='PARTIAL' and state['used_wall_seconds']>=interrupted['used_wall_seconds']
    assert len([a for a in state['attempts'] if a['plan']['model']=='mobilenet_v3_large'])==1
    assert state['trials']['resnet18/search_002']['status']=='COMPLETED'


def test_model_cap_preflight_skips_only_that_model(vision,tmp_path,context,monkeypatch):
    clock=[0.];monkeypatch.setattr(vision.time,'monotonic',lambda:clock[0])
    plans=model_plans('mobilenet_v3_large')+model_plans('resnet18')
    budget={'per_trial':10.,'per_model':{'mobilenet_v3_large':.5,'resnet18':10.},'total':20.}
    state={'signature':vision.plan_signature(plans,budget,context),'phase':'search','status':'INTERRUPTED',
           'attempts':[{'key':'mobilenet_v3_large/search_001','plan':plans[0],
                        'directory':'unused','status':'INTERRUPTED','wall_seconds':.5}],
           'trials':{},'selection':{},'used_wall_seconds':.5}
    (tmp_path/'search_state.json').write_text(json.dumps(state))
    called=[]
    def worker(command,log_path,timeout):
        row=json.loads((Path(log_path).parent/'config.json').read_text())['plan'];called.append(row['model'])
        return synthetic_worker(command,log_path,timeout)
    state=vision.run_plan(tmp_path,'search',plans,budget,context,runner=worker)
    assert called==['resnet18','resnet18'] and state['status']=='PARTIAL'
    assert state['model_budget_stops']['mobilenet_v3_large']['scope']=='per_model'


def test_partial_selection_excludes_timeout_even_with_high_saved_score(vision,tmp_path,context,monkeypatch):
    clock=[0.];monkeypatch.setattr(vision.time,'monotonic',lambda:clock[0])
    plans=model_plans('mobilenet_v3_large')+model_plans('resnet18')
    budget={'per_trial':1.,'per_model':10.,'total':20.}
    def worker(command,log_path,timeout):
        row=json.loads((Path(log_path).parent/'config.json').read_text())['plan']
        result=synthetic_worker(command,log_path,timeout)
        if row['model']=='mobilenet_v3_large' and row['trial_id']=='search_002':
            metrics=Path(log_path).parent/'validation_metrics.json'
            saved=json.loads(metrics.read_text());saved['macro_f1']=.999;metrics.write_text(json.dumps(saved))
            clock[0]+=timeout
            result.update(status='TIME_BUDGET_EXCEEDED',returncode=-15,wall_seconds=timeout)
        else:clock[0]+=.02
        return result
    state=vision.run_plan(tmp_path,'search',plans,budget,context,runner=worker)
    vision.finalize_search(state,plans,{'selection':{'tie_macro_f1_absolute_tolerance':1e-4}})
    assert state['selection']['mobilenet_v3_large']['selected_trial_id']=='search_001'
    assert state['selection']['mobilenet_v3_large']['missing_confirmation_seeds']==[43,44]
    excluded=state['excluded_trials']
    assert any(r['model']=='mobilenet_v3_large' and r['trial_id']=='search_002' and r['attempt_status']=='TIME_BUDGET_EXCEEDED' for r in excluded)


def test_partial_cli_writes_missing_model_and_budget_report(vision,tmp_path,context,monkeypatch,capsys):
    import copy
    from ml.experiments import comparator_common as common
    plans=vision._search_plans(vision.protocol.load_protocol())
    budget={'per_trial':10.,'per_model':100.,'total':200.}
    def stop(command,log_path,timeout):
        return {'status':'TIME_BUDGET_EXCEEDED','returncode':-15,'wall_seconds':timeout}
    state=vision.run_plan(tmp_path,'search',plans,budget,context,runner=stop)
    monkeypatch.setattr(vision,'cached_weight_records',lambda:{})
    monkeypatch.setattr(vision,'_run_plan',lambda *a,**kw:state)
    args=SimpleNamespace(command='search',data_root=common.DEFAULT_DATA)
    environment={'git':{'dirty_state':''}}
    assert vision._execute_command(args,tmp_path,environment,vision.protocol.load_protocol(),budget)==1
    output=capsys.readouterr().out
    assert 'SEARCH_PARTIAL' in output and 'SEARCH_COMPLETE' not in output
    assert 'BUDGET_EXCLUDED_TRIALS' in output
    selected=json.loads((tmp_path/'selection_log.json').read_text())
    assert all(r['status']=='NOT_SELECTED' and r['reason']=='NO_COMPLETED_SEARCH' for r in selected.values())


@pytest.mark.parametrize('dirty',[" M ml/vision/train_hpo.py\0", "A  ml/configs/approved_vision_budget.json\0", "?? unexpected.txt\0"])
def test_search_refuses_uncommitted_execution_state(vision,tmp_path,monkeypatch,dirty):
    from ml.experiments import comparator_common as common
    monkeypatch.setattr(common,'ROOT',tmp_path)
    def read(command,**kwargs):
        if 'status' in command:return dirty
        return b'committed'
    monkeypatch.setattr(vision.subprocess,'check_output',read)
    with pytest.raises(ValueError,match='clean|committed|dirty|staged'):
        vision.require_clean_search_commit(tmp_path,{'head':'a'*40,'staged_paths':''})


def test_search_continues_other_model_confirmations_after_first_model_timeout(vision,tmp_path,context,monkeypatch):
    clock=[0.];monkeypatch.setattr(vision.time,'monotonic',lambda:clock[0])
    cfg=vision.protocol.load_protocol();plans=vision._search_plans(cfg)
    budget={'per_trial':1.,'per_model':100.,'total':200.}
    def worker(command,log_path,timeout):
        row=json.loads((Path(log_path).parent/'config.json').read_text())['plan']
        if row['model']=='mobilenet_v3_large':
            clock[0]+=timeout
            return {'status':'TIME_BUDGET_EXCEEDED','returncode':-15,'wall_seconds':timeout}
        result=synthetic_worker(command,log_path,timeout);clock[0]+=.02;return result
    state=vision.run_plan(tmp_path,'search',plans,budget,context,runner=worker)
    vision.finalize_search(state,plans,cfg)
    assert state['status']=='PARTIAL'
    assert state['selection']['mobilenet_v3_large']['status']=='NOT_SELECTED'
    assert state['selection']['resnet18']['validation_seed_ids']==[42,43,44]
    assert state['selection']['resnet18']['missing_confirmation_seeds']==[]
    assert len([a for a in state['attempts'] if a['plan']['model']=='resnet18'])==8


def test_legacy_global_budget_status_can_continue_unattempted_model(vision,tmp_path,context,monkeypatch):
    clock=[0.];monkeypatch.setattr(vision.time,'monotonic',lambda:clock[0])
    plans=model_plans('mobilenet_v3_large')+model_plans('resnet18')
    budget={'per_trial':.5,'per_model':10.,'total':20.}
    state={'signature':vision.plan_signature(plans,budget,context),'phase':'search','status':'NOT_RUN_BUDGET',
           'attempts':[{'key':'mobilenet_v3_large/search_001','plan':plans[0],
                        'directory':'unused','status':'TIME_BUDGET_EXCEEDED','wall_seconds':.5}],
           'trials':{f"{r['model']}/{r['trial_id']}":{'status':'NOT_RUN_BUDGET'} for r in plans},
           'selection':{},'used_wall_seconds':.5}
    (tmp_path/'search_state.json').write_text(json.dumps(state))
    called=[]
    def worker(command,log_path,timeout):
        row=json.loads((Path(log_path).parent/'config.json').read_text())['plan'];called.append(row['model'])
        return synthetic_worker(command,log_path,timeout)
    state=vision.run_plan(tmp_path,'search',plans,budget,context,runner=worker)
    assert called==['resnet18','resnet18'] and state['status']=='PARTIAL'
    assert state['used_wall_seconds']>=.5


def test_total_stop_preserves_earlier_per_trial_exclusion_reason(vision,tmp_path,context,monkeypatch):
    clock=[0.];monkeypatch.setattr(vision.time,'monotonic',lambda:clock[0])
    plans=model_plans('mobilenet_v3_large')+model_plans('resnet18')
    def worker(command,log_path,timeout):
        clock[0]+=timeout
        return {'status':'TIME_BUDGET_EXCEEDED','returncode':-15,'wall_seconds':timeout}
    state=vision.run_plan(tmp_path,'search',plans,{'per_trial':.5,'per_model':10.,'total':.8},context,runner=worker)
    assert state['status']=='NOT_RUN_BUDGET'
    assert state['trials']['mobilenet_v3_large/search_001']['budget_scope']=='per_trial'
    assert state['trials']['resnet18/search_001']['budget_scope']=='total'


def test_total_preflight_has_priority_over_negative_model_remaining(vision,tmp_path,context,monkeypatch):
    clock=[0.];monkeypatch.setattr(vision.time,'monotonic',lambda:clock[0])
    plans=model_plans('mobilenet_v3_large')+model_plans('resnet18')
    budget={'per_trial':1.,'per_model':.5,'total':.7}
    state={'signature':vision.plan_signature(plans,budget,context),'phase':'search','status':'INTERRUPTED',
           'attempts':[{'key':'mobilenet_v3_large/search_001','plan':plans[0],
                        'directory':'unused','status':'INTERRUPTED','wall_seconds':.8}],
           'trials':{},'selection':{},'used_wall_seconds':.8}
    (tmp_path/'search_state.json').write_text(json.dumps(state))
    state=vision.run_plan(tmp_path,'search',plans,budget,context,runner=lambda *a:pytest.fail('Total cap exhausted'))
    assert state['budget_stop_scope']=='total' and not state['model_budget_stops']
    assert all(r['budget_scope']=='total' for r in state['trials'].values())


def test_total_terminal_verifies_completed_checkpoint_before_republishing_selection(vision,tmp_path,context,monkeypatch):
    clock=[0.];monkeypatch.setattr(vision.time,'monotonic',lambda:clock[0])
    plans=model_plans('mobilenet_v3_large')+model_plans('resnet18')
    budget={'per_trial':10.,'per_model':10.,'total':.5}
    def worker(command,log_path,timeout):
        if clock[0]==0:
            result=synthetic_worker(command,log_path,timeout);clock[0]=.1;result['wall_seconds']=.1;return result
        clock[0]+=timeout
        return {'status':'TIME_BUDGET_EXCEEDED','returncode':-15,'wall_seconds':timeout}
    state=vision.run_plan(tmp_path,'search',plans,budget,context,runner=worker)
    assert state['status']=='NOT_RUN_BUDGET'
    (tmp_path/state['attempts'][0]['directory']/'checkpoint.pt').write_bytes(b'corrupt')
    before=(tmp_path/'search_state.json').read_bytes()
    with pytest.raises(ValueError,match='artifact|integrity'):
        vision.run_plan(tmp_path,'search',plans,budget,context,runner=lambda *a:pytest.fail('No retraining'))
    assert (tmp_path/'search_state.json').read_bytes()==before


def test_search_clean_commit_preserves_declared_untracked_exceptions(vision,tmp_path,monkeypatch):
    from ml.experiments import comparator_common as common
    monkeypatch.setattr(common,'ROOT',tmp_path)
    directory=tmp_path/'ml/outputs/runs/test_run';directory.mkdir(parents=True)
    source_names=['ml/experiments/run_vision_hpo.py','ml/vision/train_hpo.py',
                  'ml/experiments/hpo_protocol.py','ml/experiments/comparator_common.py',
                  'ml/configs/bounded_hpo.json','ml/configs/approved_vision_budget.json']
    for name in source_names:
        p=tmp_path/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'committed')
    dirty='?? docs/fyp2/09_INDEPENDENT_AUDIT_REVIEW.md\0?? ml/outputs/runs/test_run/search_state.json\0'
    def read(command,**kwargs):
        if 'status' in command:return dirty
        return b'committed'
    monkeypatch.setattr(vision.subprocess,'check_output',read)
    git={'head':'a'*40,'staged_paths':'','dirty_state':'untracked audit and own output'}
    vision.require_clean_search_commit(directory,git)
    assert git['tracked_worktree_clean'] is True and git['execution_commit']=='a'*40
    assert git['dirty_state']=='untracked audit and own output'
    (tmp_path/'ml/configs/approved_vision_budget.json').write_bytes(b'changed')
    with pytest.raises(ValueError,match='committed|HEAD'):
        vision.require_clean_search_commit(directory,git)
