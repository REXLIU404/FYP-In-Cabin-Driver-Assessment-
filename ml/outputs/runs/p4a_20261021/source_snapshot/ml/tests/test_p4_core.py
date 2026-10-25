"""Synthetic-only P4 enforcement tests; never read observations or model files."""
import importlib
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def core():
    try:
        return importlib.import_module('ml.experiments.p4_core')
    except ModuleNotFoundError as error:
        if error.name != 'ml.experiments.p4_core':
            raise
        class Missing:
            def __getattr__(self, name):
                pytest.fail('Missing P4 core implementation')
        return Missing()


def approval():
    return dict(phase='P4-B', authorized=True, human_approval='explicit-user-approval-reference',
                protocol_sha256='a'*64, source_sha256='b'*64, run_id='p4_formal_unique')


def binding():
    return {'protocol_sha256':'a'*64,'source_sha256':'b'*64,'run_id':'p4_formal_unique'}


def test_authorization_is_required_before_reader_side_effect(core):
    touched=[]
    with pytest.raises(ValueError,match='P4-B'):
        core.authorized_read(None, lambda: touched.append('read'), **binding())
    assert touched == []
    assert core.authorized_read(approval(), lambda:'synthetic-read', **binding()) == 'synthetic-read'


@pytest.mark.parametrize('field,value', [('phase','P4-A'),('authorized',False),('human_approval',''),
    ('protocol_sha256','c'*64),('source_sha256','c'*64),('run_id','other')])
def test_approval_cannot_be_rebound_or_inferred(core,field,value):
    token=approval();token[field]=value
    with pytest.raises(ValueError):
        core.authorize_p4b(token,**binding())


def test_cache_reuses_clean_without_forward_and_detects_tamper(core,tmp_path):
    cache=core.PredictionCache.create(tmp_path/'cache', binding(), {'toy':'1'*64})
    row=dict(source_id='synthetic:0',condition='clean',input_sha256='2'*64,label=0)
    result=cache.predict_once('toy',[row],lambda: np.array([[2.,-1.]],dtype=np.float32))
    assert result.tolist()==[[2.,-1.]]
    again=cache.predict_once('toy',[row],lambda: pytest.fail('clean forwarded twice'))
    assert np.array_equal(result,again)
    with pytest.raises(ValueError,match='input'):
        cache.predict_once('toy',[dict(row,input_sha256='3'*64)],lambda:None)
    cache.connection.execute("UPDATE predictions SET payload = ?", (b'broken',))
    cache.connection.commit()
    with pytest.raises(ValueError,match='tamper'):
        cache.predict_once('toy',[row],lambda:None)
    cache.close()


def test_cache_restart_and_interrupted_claim_never_recompute(core,tmp_path):
    directory=tmp_path/'cache'
    cache=core.PredictionCache.create(directory,binding(),{'toy':'1'*64})
    row=dict(source_id='s',condition='clean',input_sha256='2'*64,label=0)
    with pytest.raises(RuntimeError,match='synthetic failure'):
        cache.predict_once('toy',[row],lambda: (_ for _ in ()).throw(RuntimeError('synthetic failure')))
    with pytest.raises(ValueError,match='incomplete|failed'):
        cache.predict_once('toy',[row],lambda:pytest.fail('interrupted ID reran'))
    cache.close()
    with pytest.raises(FileExistsError):
        core.PredictionCache.create(directory,binding(),{'toy':'1'*64})


def test_shared_batch32_keeps_per_condition_tail9_and_detects_mutation(core,tmp_path):
    cache=core.PredictionCache.create(tmp_path/'cache',binding(),{'a':'1'*64,'b':'2'*64})
    seen=[]
    def model(x):
        seen.append((len(x),x.tobytes()))
        return np.column_stack((x[:,0],-x[:,0])).astype(np.float32)
    conditions=[('clean',np.arange(41,dtype=np.float32).reshape(41,1)),
                ('stress',np.arange(41,dtype=np.float32).reshape(41,1)+1)]
    result=core.evaluate_shared_conditions(cache,conditions,source_ids=[f's{i}' for i in range(41)],
        labels=[0]*41,models={'a':model,'b':model},batch_size=32)
    assert len(result)==164
    assert [x[0] for x in seen]==[32,32,9,9,32,32,9,9]
    assert all(seen[i][1]==seen[i+1][1] for i in (0,2,4,6))
    assert len(cache.records())==164
    cache.close()


def test_mutating_model_stops_shared_input_corruption(core,tmp_path):
    cache=core.PredictionCache.create(tmp_path/'cache',binding(),{'a':'1'*64})
    def bad(x):
        x.flags.writeable=True;x[0,0]=55
        return np.ones((len(x),2),dtype=np.float32)
    with pytest.raises(ValueError,match='mutat'):
        core.evaluate_shared_conditions(cache,[('clean',np.zeros((2,1),dtype=np.float32))],
            source_ids=['s0','s1'],labels=[0,1],models={'a':bad})
    cache.close()


def test_metrics_fixed_classes_logloss_and_unverified_no_f1(core):
    report=core.classification_metrics([0,1],np.array([[2.,0.],[0.,2.]],dtype=np.float32),2,logits=True)
    assert report['accuracy']==1.0 and report['macro_f1']==1.0
    assert report['confusion']==[[1,0],[0,1]]
    assert report['log_loss']==pytest.approx(0.12692801104297263)
    stress=core.stability_metrics([[.8,.2],[.1,.9]],[[.4,.6],[.1,.9]])
    assert stress['flip_rate']==.5 and stress['mean_l1']==pytest.approx(.4)
    assert stress['label_validity']=='LABEL_VALIDITY_UNVERIFIED' and 'macro_f1' not in stress
    empty=core.conditioned_metrics([0],[[1.,0.]],2)
    assert empty['status']=='NOT_ESTIMABLE' and 'macro_f1' not in empty


def test_probabilities_reject_nan_wrong_row_sum_and_class_count(core):
    for outputs in ([[float('nan'),0]], [[.3,.3]], [[1.,0.,0.]]):
        with pytest.raises(ValueError):
            core.classification_metrics([0],outputs,2,logits=False)


def test_budget_kills_timed_out_process_group_and_forbids_resume(core,tmp_path):
    supervisor=core.BudgetSupervisor(tmp_path/'run', total_seconds=2, stage_caps={'toy':.15},
        min_free_bytes=0,min_available_ram=0, disk_cap_bytes=1024**2)
    started=time.monotonic()
    with pytest.raises(core.BudgetExceeded,match='TIME_BUDGET_EXCEEDED'):
        supervisor.run([sys.executable,'-c','import time;time.sleep(10)'],stage='toy',model='toy',
            model_cap_seconds=1, worker_cap_seconds=1, rss_cap_bytes=1024**3)
    assert time.monotonic()-started<2
    status=json.loads((tmp_path/'run'/'budget_state.json').read_text())
    assert status['status']=='PARTIAL' and status['reason']=='TIME_BUDGET_EXCEEDED'
    with pytest.raises(ValueError,match='stopped'):
        supervisor.run([sys.executable,'-c','pass'],stage='toy',model='toy',model_cap_seconds=1,
            worker_cap_seconds=1,rss_cap_bytes=1024**3)


def test_budget_observed_disk_and_rss_guards(core,tmp_path):
    supervisor=core.BudgetSupervisor(tmp_path/'run',total_seconds=5,stage_caps={'toy':5},
        min_free_bytes=0,min_available_ram=0,disk_cap_bytes=100)
    with pytest.raises(core.BudgetExceeded,match='DISK'):
        supervisor.run([sys.executable,'-c',"from pathlib import Path;import time;Path('large').write_bytes(b'x'*1000);time.sleep(5)"],
            stage='toy',model='toy',model_cap_seconds=5,worker_cap_seconds=5,rss_cap_bytes=1024**3)
    second=core.BudgetSupervisor(tmp_path/'rss',total_seconds=5,stage_caps={'toy':5},
        min_free_bytes=0,min_available_ram=0,disk_cap_bytes=1024**2)
    with pytest.raises(core.BudgetExceeded,match='RSS'):
        second.run([sys.executable,'-c','import time;time.sleep(5)'],stage='toy',model='toy',
            model_cap_seconds=5,worker_cap_seconds=5,rss_cap_bytes=1)


def test_worker_failure_is_final_and_raw_logs_saved(core,tmp_path):
    supervisor=core.BudgetSupervisor(tmp_path/'run',total_seconds=5,stage_caps={'toy':5},
        min_free_bytes=0,min_available_ram=0,disk_cap_bytes=1024**2)
    with pytest.raises(RuntimeError,match='worker'):
        supervisor.run([sys.executable,'-c',"print('raw failure');raise SystemExit(3)"],stage='toy',model='toy',
            model_cap_seconds=5,worker_cap_seconds=5,rss_cap_bytes=1024**3)
    assert 'raw failure' in next((tmp_path/'run').glob('*.stdout.log')).read_text()
    assert json.loads((tmp_path/'run'/'budget_state.json').read_text())['status']=='FAILED'


def test_cli_refuses_disabled_protocol_without_touching_data(core,tmp_path):
    from ml.experiments import run_p4
    protocol=tmp_path/'protocol.json';protocol.write_text(json.dumps({'protocol':'P4-PROTOCOL-v1',
        'phase':'P4-A','formal_execution_authorized':False}))
    with pytest.raises(ValueError,match='P4-B'):
        run_p4.main(['formal','--protocol',str(protocol),'--run-id','never-open-heldout'])
    assert not (tmp_path/'never-open-heldout').exists()


def test_readonly_cache_rebind_refusal_and_actual_source_hash(core,tmp_path):
    cache=core.PredictionCache.create(tmp_path/'cache',binding(),{'toy':'1'*64});cache.close()
    with pytest.raises(ValueError,match='binding'):
        core.PredictionCache.open_readonly(tmp_path/'cache',dict(binding(),source_sha256='c'*64),{'toy':'1'*64})
    source=tmp_path/'source.py';source.write_text('x=1\n')
    first=core.source_manifest([source]);source.write_text('x=2\n')
    second=core.source_manifest([source])
    assert first['source_sha256']!=second['source_sha256']


def test_driver_and_leave_one_out_metrics_keep_fixed_classes(core):
    result=core.driver_metrics([0,1,0,1],[[.9,.1],[.8,.2],[.7,.3],[.1,.9]],
        ['p1','p1','p2','p2'],2)
    assert result['drivers']['p1']['accuracy']==.5
    assert result['drivers']['p2']['accuracy']==1.
    assert result['leave_one_driver_out_macro_f1_range']==[1/3,1.]
    assert result['independent_driver_count']==2


def test_budget_model_and_total_time_are_cumulative(core,tmp_path):
    supervisor=core.BudgetSupervisor(tmp_path/'run',total_seconds=.25,stage_caps={'a':2,'b':2},
        min_free_bytes=0,min_available_ram=0,disk_cap_bytes=1024**2)
    supervisor.run([sys.executable,'-c','import time;time.sleep(.1)'],stage='a',model='m',
        model_cap_seconds=2,worker_cap_seconds=2,rss_cap_bytes=1024**3)
    with pytest.raises(core.BudgetExceeded,match='TIME_BUDGET_EXCEEDED'):
        supervisor.run([sys.executable,'-c','import time;time.sleep(.2)'],stage='b',model='m',
            model_cap_seconds=2,worker_cap_seconds=2,rss_cap_bytes=1024**3)
    assert json.loads((tmp_path/'run'/'budget_state.json').read_text())['total_used_seconds']>=.25


def test_supervisor_monitors_entire_output_root(core,tmp_path):
    root=tmp_path/'all';root.mkdir();(root/'existing-output').write_bytes(b'x'*500)
    supervisor=core.BudgetSupervisor(root/'budget',output_root=root,total_seconds=2,stage_caps={'toy':2},
        min_free_bytes=0,min_available_ram=0,disk_cap_bytes=100)
    with pytest.raises(core.BudgetExceeded,match='DISK'):
        supervisor.run([sys.executable,'-c','import time;time.sleep(1)'],stage='toy',model='toy',
            model_cap_seconds=2,worker_cap_seconds=2,rss_cap_bytes=1024**3)


def test_qc_common_subset_missing_classes_is_not_estimable(core):
    from ml.experiments import run_p4
    predictions=[]
    qc=[]
    for source,label in [('s0',0),('s1',1)]:
        for condition,severity in [('clean',0),('occlusion',0),('occlusion',1),('occlusion',2)]:
            output=[0.]*10;output[label]=1.
            predictions.append(dict(identity='toy',source_id=source,label=label,
                condition='clean' if condition=='clean' else f'occlusion:{severity}',output=output))
            qc.append(dict(source_id=source,class_id=f'c{label}',driver_id='p1',condition=condition,
                severity=severity,status='VALID'))
    result=run_p4.qc_conditioned_report(predictions,qc,identities=['toy'])
    assert result['families']['occlusion']['models']['toy']['clean']['status']=='NOT_ESTIMABLE'
    assert result['families']['occlusion']['common_source_count']==2
    assert result['reviewer_count']==1 and result['inter_rater_agreement'] is None
    qc[-1]['status']='UNCERTAIN'
    other=run_p4.qc_conditioned_report(predictions,qc,identities=['toy'])
    assert other['families']['occlusion']['common_source_count']==1


def test_qc_common_report_retains_driver_support_even_without_ten_classes(core):
    from ml.experiments import run_p4
    predictions=[];qc=[]
    for source,driver,label in [('s0','p1',0),('s1','p2',1)]:
        for family,severity in [('clean',0),('occlusion',0),('occlusion',1),('occlusion',2)]:
            output=[0.]*10;output[label]=2.
            predictions.append(dict(identity='toy',source_id=source,label=label,
                condition='clean' if family=='clean' else f'occlusion:{severity}',output=output))
            qc.append(dict(source_id=source,class_id=f'c{label}',driver_id=driver,condition=family,severity=severity,status='VALID'))
    report=run_p4.qc_conditioned_report(predictions,qc,identities=['toy'])
    family=report['families']['occlusion']
    assert family['driver_class_support']=={'p1':{'c0':1},'p2':{'c1':1}}
    assert family['models']['toy']['clean']['supported_class_diagnostics'][0]['recall']==1.


@pytest.mark.parametrize('column,value',[('label',1),('input_sha','changed'),('source_id','changed')])
def test_cache_aggregation_detects_metadata_tamper(core,tmp_path,column,value):
    cache=core.PredictionCache.create(tmp_path/'cache',binding(),{'toy':'1'*64})
    cache.predict_once('toy',[dict(source_id='s',condition='clean',input_sha256='2'*64,label=0)],
        lambda:np.array([[1.,0.]],dtype=np.float32))
    cache.connection.execute(f'UPDATE predictions SET {column}=?',(value,));cache.connection.commit()
    with pytest.raises(ValueError,match='tamper'):cache.records()
    cache.close()


def test_streaming_bank_writer_preserves_npy_without_resident_maps(core,tmp_path):
    from ml.experiments import run_p4
    path=tmp_path/'bank.npy'
    writer=run_p4.StreamingNpyWriter(path,(3,2,2,3),np.uint8)
    for row in (2,0,1):writer.write_row(row,np.full((2,2,3),row,dtype=np.uint8))
    writer.finish()
    result=np.load(path,allow_pickle=False)
    assert result.shape==(3,2,2,3)
    assert result[:,0,0,0].tolist()==[0,1,2]
    with pytest.raises(ValueError,match='duplicate'):writer.write_row(0,np.zeros((2,2,3),dtype=np.uint8))


def test_total_budget_includes_parent_work_between_workers(core,tmp_path):
    supervisor=core.BudgetSupervisor(tmp_path/'run',total_seconds=.08,stage_caps={'toy':2},
        min_free_bytes=0,min_available_ram=0,disk_cap_bytes=1024**2)
    time.sleep(.1)
    with pytest.raises(core.BudgetExceeded,match='TIME_BUDGET_EXCEEDED'):
        supervisor.run([sys.executable,'-c','pass'],stage='toy',model='toy',
            model_cap_seconds=1,worker_cap_seconds=1,rss_cap_bytes=1024**3)
    assert len(supervisor.workers)==0


def test_private_worker_requires_supervisor_before_spec_read(core,tmp_path,monkeypatch):
    from ml.experiments import run_p4
    monkeypatch.delenv('P4_BUDGET_WORKER',raising=False)
    with pytest.raises(PermissionError,match='supervisor'):
        run_p4.worker(tmp_path/'nonexistent.json','shared_inputs')


def test_protocol_change_cannot_silently_change_runtime(core):
    from ml.experiments import run_p4
    protocol=json.loads((Path(run_p4.ROOT)/'ml/configs/p4_protocol.json').read_text())
    protocol['runtime']['intra_op_threads']=3
    with pytest.raises(ValueError,match='protocol'):
        run_p4.validate_protocol(protocol)


def test_runtime_summary_preserves_rounds_and_sampled_rss(core):
    from ml.experiments import run_p4
    rounds=[{'round':i,'latency_nanoseconds':[1000000,3000000], 'throughput_calls':100,
        'throughput_loop_nanoseconds':1000000000,'rss_before_session_bytes':100,'rss_after_session_bytes':150,
        'lifecycle_ru_maxrss':999} for i in range(6)]
    workers=[{'stage':'runtime','model':'toy','samples':[{'elapsed_seconds':0.,'rss_bytes':100},
        {'elapsed_seconds':.03,'rss_bytes':300}], 'sampled_peak_rss_bytes':300} for i in range(6)]
    report=run_p4.runtime_summary(rounds,workers,'toy')
    assert report['p50_ms']==2. and report['p95_ms']==3.
    assert report['rounds'][0]['p50_ms']==2.
    assert report['rounds'][0]['sampled_peak_minus_baseline_bytes']==200
    assert report['rounds'][0]['maximum_sampling_gap_seconds']==.03
    assert report['pooled_throughput_per_second']==100.


def test_synthetic_disk_bank_three_models_cache_and_partial_guard(core,tmp_path,monkeypatch):
    from ml.experiments import run_p4
    shared=tmp_path/'shared_inputs';shared.mkdir()
    sources=[{'source_id':f's{i:02}','class_id':'c0','driver_id':'p1'} for i in range(41)]
    variants=[];banks={}
    for family,severity,offset in [('clean',0,0),('brightness_up',0,1)]:
        name=family if family=='clean' else family+':0'
        pixels=np.full((41,224,224,3),offset,dtype=np.uint8)
        filename='vision_'+name.replace(':','_')+'.npy';np.save(shared/filename,pixels)
        banks[filename]=core.sha256_file(shared/filename)
        for index,source in enumerate(sources):
            variants.append(dict(source_id=source['source_id'],condition=family,severity=severity,
                input_sha256=core.array_sha256(run_p4.normalize_rgb(pixels[index:index+1])[0])))
    for filename,value in [('vision_sources.json',sources),('vision_variants.json',variants)]:
        (shared/filename).write_text(json.dumps(value))
    (shared/'bank_manifest.json').write_text(json.dumps({'banks':banks,
        'metadata':{p.name:core.sha256_file(p) for p in shared.glob('*.json')}}))
    identities={k:v['sha256'] for k,v in core.FROZEN_IDENTITIES.items()}
    cache=core.PredictionCache.create(tmp_path/'cache',binding(),identities);cache.close()
    seen=[]
    class Session:
        def run(self,names,request):
            x=request['input'];seen.append((len(x),core.array_sha256(x)))
            output=np.zeros((len(x),10),dtype=np.float32);output[:,0]=2
            return [output]
    monkeypatch.setattr(run_p4,'create_ort',lambda path:Session())
    monkeypatch.setattr(run_p4,'verify_identity',lambda *args:tmp_path)
    monkeypatch.setattr(run_p4,'verify_preflight',lambda spec:{'models':{k:{'onnx_path':'toy'} for k in ('MN-HPO42','RN-HPO42','MN-STABLE')}})
    spec={'run_dir':str(tmp_path),'binding':binding()}
    for stage in ('vision_clean','vision_stress'):
        for identity in ('MN-HPO42','RN-HPO42','MN-STABLE'):run_p4.evaluate_model(spec,identity,stage)
    assert [s[0] for s in seen]==[32,9]*6
    assert seen[0:2]==seen[2:4]==seen[4:6]
    before=len(seen);run_p4.evaluate_model(spec,'MN-HPO42','vision_clean');assert len(seen)==before
    cache=core.PredictionCache.open_readonly(tmp_path/'cache',binding(),identities)
    records=cache.records();cache.close();assert len(records)==246
    assert core.classification_metrics([r['label'] for r in records],[r['output'] for r in records],10,logits=True)['accuracy']==1.
    with pytest.raises(ValueError,match='Incomplete full paired'):
        run_p4.aggregate(spec)


def test_formal_provenance_wrong_branch_stops_before_protected_reads(core,monkeypatch):
    from ml.experiments import run_p4,comparator_common,p4_preflight
    monkeypatch.setattr(comparator_common,'git_snapshot',lambda:{'branch':'wrong','staged_paths':''})
    monkeypatch.setattr(p4_preflight,'protected_snapshot',lambda:pytest.fail('protected/data reads after wrong branch'))
    with pytest.raises(ValueError,match='branch'):
        run_p4.formal_provenance()


def test_human_wait_explicitly_pauses_machine_budget(core,tmp_path):
    supervisor=core.BudgetSupervisor(tmp_path/'run',total_seconds=.1,stage_caps={'toy':2},
        min_free_bytes=0,min_available_ram=0,disk_cap_bytes=1024**2)
    with supervisor.human_wait():time.sleep(.12)
    supervisor.run([sys.executable,'-c','pass'],stage='toy',model='toy',model_cap_seconds=1,
        worker_cap_seconds=1,rss_cap_bytes=1024**3)
    assert supervisor.total_used<.1
