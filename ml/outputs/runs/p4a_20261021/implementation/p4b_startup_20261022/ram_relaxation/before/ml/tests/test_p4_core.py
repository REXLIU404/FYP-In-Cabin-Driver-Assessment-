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


def telemetry_metadata_fixture():
    """Hand-checked metadata: one injected cell and one source-missing cell."""
    from copy import deepcopy
    from ml.experiments.comparator_common import FEATURES
    unknown={'status':'UNKNOWN','lower_excess':None,'upper_excess':None}
    within={'status':'WITHIN_BOUNDS','lower_excess':0.,'upper_excess':0.}
    speed={'status':'WITHIN_KNOWN_BOUNDS_UPPER_UNKNOWN','lower_excess':0.,'upper_excess':None}
    missing={'status':'MISSING','lower_excess':None,'upper_excess':None}
    rows=[]
    for index in range(2):
        source_mask=[False]*8;injected_mask=[False]*8
        if index==0:injected_mask[0]=True
        else:source_mask[1]=True
        bounds={stage:[{'feature':feature,'domain':deepcopy(speed if i==0 else unknown),
            'empirical':deepcopy(within)} for i,feature in enumerate(FEATURES)]
            for stage in ('source','pre_mask','observed','imputed')}
        if index==0:
            bounds['pre_mask'][0]['domain']={'status':'OUT_OF_BOUNDS','lower_excess':2.,'upper_excess':None}
            bounds['pre_mask'][0]['empirical']={'status':'OUT_OF_BOUNDS','lower_excess':3.,'upper_excess':0.}
            bounds['observed'][0].update(domain=deepcopy(missing),empirical=deepcopy(missing))
        else:
            for stage in ('source','pre_mask','observed'):
                bounds[stage][1].update(domain=deepcopy(missing),empirical=deepcopy(missing))
        rows.append(dict(source_id=f's{index}',domain='D3',severity=0,feature_order=FEATURES,
            source_missing_mask=source_mask,injected_missing_mask=injected_mask,
            missing_mask=[a or b for a,b in zip(source_mask,injected_mask)],
            record_affected=index==0,requested_record_missing_rate=.5,bounds=bounds,
            label_validity='LABEL_VALIDITY_UNVERIFIED',f1_eligible=False))
    return rows


def test_telemetry_metadata_summary_preserves_masks_and_pre_imputation_bounds(core):
    from ml.experiments import run_p4
    report=run_p4.telemetry_metadata_summary(telemetry_metadata_fixture())
    condition=report['conditions']['D3:0']
    assert condition['source_count']==2 and condition['record_count']==2
    assert condition['record_affected']=={'count':1,'rate':.5}
    missing=condition['missingness']
    assert missing['source']['cell_count']==1 and missing['source']['cell_rate']==.0625
    assert missing['injected']['record_count']==1 and missing['injected']['record_rate']==.5
    assert missing['combined']['cell_count']==2 and missing['combined']['cell_rate']==.125
    assert missing['combined']['record_count']==2 and missing['combined']['record_rate']==1.
    assert missing['source']['features']['accel_x']=={'count':1,'rate':.5}
    assert missing['injected']['features']['speed_kmph']=={'count':1,'rate':.5}
    bounds=condition['bounds']
    before=bounds['pre_mask']['speed_kmph']['domain']
    assert before['status_counts']=={'OUT_OF_BOUNDS':1,'WITHIN_KNOWN_BOUNDS_UPPER_UNKNOWN':1}
    assert before['lower_excess']=={'count':1,'sum':2.,'max':2.,'known_count':2,'unknown_or_missing_count':0}
    assert before['upper_excess']=={'count':0,'sum':None,'max':None,'known_count':0,'unknown_or_missing_count':2}
    assert bounds['pre_mask']['speed_kmph']['empirical']['lower_excess']['sum']==3.
    assert bounds['observed']['speed_kmph']['domain']['status_counts']['MISSING']==1
    assert bounds['imputed']['speed_kmph']['domain']['lower_excess']['count']==0
    assert bounds['source']['accel_x']['domain']['status_counts']=={'UNKNOWN':1,'MISSING':1}
    assert condition['label_validity']=='LABEL_VALIDITY_UNVERIFIED'
    assert condition['f1_eligible'] is False and 'macro_f1' not in condition


def test_telemetry_metadata_file_report_rejects_tamper_and_keeps_condition_denominators(core,tmp_path):
    from ml.experiments import run_p4
    from copy import deepcopy
    rows=telemetry_metadata_fixture()
    clean=deepcopy(rows[1]);clean.update(domain='D0',severity=0,record_affected=False,
        label_validity='SOURCE_SYNTHETIC_LABEL',f1_eligible=True)
    rows.append(clean)
    path=tmp_path/'telemetry_variants.json';path.write_text(json.dumps(rows))
    (tmp_path/'bank_manifest.json').write_text(json.dumps({'metadata':{path.name:core.sha256_file(path)}}))
    report=run_p4.load_telemetry_metadata_summary(tmp_path)
    assert report['conditions']['D0']['record_count']==1
    assert report['conditions']['D3:0']['record_count']==2
    assert report['conditions']['D0']['label_validity']=='SOURCE_SYNTHETIC_LABEL'
    path.write_text('[]')
    with pytest.raises(ValueError,match='metadata'):
        run_p4.load_telemetry_metadata_summary(tmp_path)


@pytest.mark.parametrize('field,value',[('authorized',False),('phase','P4-A'),
    ('human_approval',''),('protocol_sha256','0'*64),('source_sha256','0'*64)])
def test_formal_malformed_external_approval_stops_before_data_or_worker(core,tmp_path,monkeypatch,field,value):
    from ml.experiments import run_p4
    protocol=Path(run_p4.ROOT)/'ml/configs/p4_protocol.json'
    frozen=run_p4.binding_for(protocol,'synthetic_boolean_gate')
    approval_path=tmp_path/'synthetic_approval.json'
    approved=dict(frozen,phase='P4-B',authorized=True,human_approval='SYNTHETIC_TEST_FIXTURE_ONLY')
    approved[field]=value;approval_path.write_text(json.dumps(approved))
    execution=tmp_path/'must_not_open.json'
    monkeypatch.setattr(run_p4,'formal_provenance',lambda:{})
    monkeypatch.setattr(run_p4,'BudgetSupervisor',lambda *args,**kwargs:pytest.fail('resource/worker started without literal approval'))
    with pytest.raises(ValueError):
        run_p4.main(['formal','--protocol',str(protocol),'--run-id',frozen['run_id'],
            '--approval',str(approval_path),'--execution-spec',str(execution)])


def test_v2_removes_manual_qc_preserving_full_frozen_scope_and_rejects_v1(core):
    from ml.experiments import run_p4
    protocol=json.loads((run_p4.ROOT/'ml/configs/p4_protocol.json').read_text())
    assert protocol['protocol']=='P4-PROTOCOL-v2'
    assert protocol['amendment']=='USER_APPROVED_MANUAL_QC_REMOVAL'
    assert protocol['formal_execution_authorized'] is False
    for key in ('pilot','formal','conditioned_f1','human_label_validity','inter_rater_agreement'):
        assert protocol['qc'][key]=='REMOVED_FROM_SCOPE'
    assert protocol['qc']['automatic_human_validation'] is False
    assert protocol['scope']=={'vision_sources':3657,'vision_conditions':19,'vision_shared_inputs':69483,
        'vision_identities':3,'vision_predictions':208449,'telemetry_sources':4500,'telemetry_conditions':10,
        'telemetry_shared_inputs':45000,'telemetry_identities':4,'telemetry_predictions':180000,'total_predictions':388449}
    assert 'p4_qc.py' not in {path.name for path in run_p4.SOURCES}
    assert run_p4.validate_protocol(protocol)==protocol
    old=dict(protocol,protocol='P4-PROTOCOL-v1')
    with pytest.raises(ValueError,match='protocol'):run_p4.validate_protocol(old)


def test_stability_distribution_changes_are_paired_descriptive_not_label_f1(core):
    report=core.stability_metrics([[.8,.1,.1],[.7,.2,.1],[.2,.7,.1],[.1,.2,.7]],
        [[.1,.8,.1],[.7,.2,.1],[.1,.2,.7],[.1,.2,.7]])
    assert report['clean_prediction_distribution']==[2,1,1]
    assert report['stress_prediction_distribution']==[1,1,2]
    assert report['prediction_distribution_delta_count']==[-1,0,1]
    assert report['prediction_distribution_delta_rate']==[-.25,0.,.25]
    assert sum(report['prediction_distribution_delta_count'])==0
    assert sum(report['prediction_distribution_delta_rate'])==0.
    assert report['clean_prediction_distribution_rate']==[.5,.25,.25]
    assert report['stress_prediction_distribution_rate']==[.25,.25,.5]
    assert report['flip_rate']==.5 and report['mean_l1']==pytest.approx(.65)
    assert report['human_validated'] is False and report['f1_eligible'] is False
    assert report['label_validity']=='LABEL_VALIDITY_UNVERIFIED' and 'macro_f1' not in report


def test_v2_formal_dispatch_has_no_reviewers_or_manual_wait(core,tmp_path,monkeypatch):
    from ml.experiments import run_p4
    protocol=run_p4.ROOT/'ml/configs/p4_protocol.json';frozen=run_p4.binding_for(protocol,'synthetic_v2_dispatch')
    approval_path=tmp_path/'synthetic_approval.json'
    approval_path.write_text(json.dumps(dict(frozen,phase='P4-B',authorized=True,human_approval='SYNTHETIC_ONLY')))
    spec=tmp_path/'execution_spec.json';spec.write_text('{}')
    calls=[]
    class Supervisor:
        def __init__(self,path,**kwargs):Path(path).mkdir(parents=True);self.path=path
        def run(self,command,**limits):calls.append((command,limits));return {'returncode':0}
    monkeypatch.setattr(run_p4,'ROOT',tmp_path)
    monkeypatch.setattr(run_p4,'formal_provenance',lambda:{'protected_hashes':{'synthetic':'stable'}})
    monkeypatch.setattr(run_p4,'BudgetSupervisor',Supervisor)
    assert run_p4.main(['formal','--protocol',str(protocol),'--run-id',frozen['run_id'],
        '--approval',str(approval_path),'--execution-spec',str(spec)])==0
    from collections import Counter
    assert Counter(limits['stage'] for _,limits in calls)=={'preflight':1,'shared_inputs':1,
        'vision_clean':3,'vision_stress':3,'telemetry':4,'runtime':12,'aggregation':1}
    out=tmp_path/'ml/outputs/runs'/frozen['run_id']
    completion=json.loads((out/'completion.json').read_text())
    assert completion['status']=='MACHINE_EVALUATION_COMPLETED'
    assert completion['qc_status']=='REMOVED_FROM_SCOPE'
    assert completion['formal_prediction_count']==388449
    assert 'reviewers' not in json.loads((out/'execution_spec.json').read_text())


def test_v2_prepare_inputs_writes_only_shared_banks_without_qc_subset(core,tmp_path,monkeypatch):
    from ml.experiments import run_p4,p4_data,p4_qc,e1_generators,comparator_common as common
    from PIL import Image
    run=tmp_path/'run';run.mkdir()
    vision=[]
    for i in range(2):
        source=tmp_path/f'synthetic_{i}.png';Image.new('RGB',(16,16),(i,2,3)).save(source)
        vision.append(dict(source_id=f'synthetic:c{i}',class_id=f'c{i}',driver_id=f'p{i}',
            image_path=str(source),source_split='synthetic'))
    sets={split:[dict(source_id=f'synthetic:{split}:{i}',source_label=label,
        features=[float(i+j) for j in range(8)]) for i,label in enumerate(common.LABELS)]
        for split in ('train','val','test')}
    statistics=e1_generators.fit_train_statistics([r['features'] for r in sets['train']],common.LABELS,
        split='train',source_sha256=run_p4.DATA_HASHES['telemetry_train'])
    monkeypatch.setattr(p4_data,'read_vision_metadata',lambda *args,**kwargs:vision)
    monkeypatch.setattr(p4_data,'read_telemetry_csv',lambda *args,**kwargs:sets[kwargs['split']])
    monkeypatch.setattr(run_p4,'validate_vision_sources',lambda records:None,raising=False)
    monkeypatch.setattr(run_p4,'validate_telemetry_sources',lambda *args:None,raising=False)
    saved={'feature_order':common.FEATURES,'train_csv_sha256':run_p4.DATA_HASHES['telemetry_train'],'median':statistics['median']}
    monkeypatch.setattr(run_p4,'read_json',lambda path:{'train_only_statistics':statistics}
        if Path(path).name=='preparation_evidence.json' else saved)
    monkeypatch.setattr(p4_qc,'select_sources',lambda *args,**kwargs:pytest.fail('manual QC selection called'))
    monkeypatch.setattr(p4_qc,'build_review_kit',lambda *args,**kwargs:pytest.fail('manual QC kit copied'))
    token=core.authorize_p4b(approval(),**binding())
    run_p4.prepare_inputs({'run_dir':str(run),'data_root':str(tmp_path/'synthetic'),'binding':binding()},token)
    shared=run/'shared_inputs'
    manifest=json.loads((shared/'bank_manifest.json').read_text())
    assert len(manifest['banks'])==29
    assert manifest['vision_sources']==2 and manifest['vision_inputs']==38
    assert manifest['telemetry_sources']==3 and manifest['telemetry_inputs']==30
    rows=json.loads((shared/'vision_variants.json').read_text())
    assert len(rows)==38 and all(row['qc_status']=='REMOVED_FROM_SCOPE' for row in rows)
    assert all(row['label_validity']=='LABEL_VALIDITY_UNVERIFIED' and row['f1_eligible'] is False
        for row in rows if row['condition']!='clean')
    telemetry=json.loads((shared/'telemetry_variants.json').read_text())
    assert all(row['qc_status']=='REMOVED_FROM_SCOPE' and row['human_validated'] is False for row in telemetry)
    assert not (run/'qc_review_kit').exists() and not (run/'qc_images').exists()


def test_v2_aggregate_keeps_clean_metrics_without_manual_qc_or_corrupt_f1(core,tmp_path,monkeypatch):
    from ml.experiments import run_p4
    shared=tmp_path/'shared_inputs';shared.mkdir()
    ids=['s0','s1'];identity_hashes={k:v['sha256'] for k,v in core.FROZEN_IDENTITIES.items()}
    cache=core.PredictionCache.create(tmp_path/'cache',binding(),identity_hashes)
    for identity,spec in core.FROZEN_IDENTITIES.items():
        vision=spec['modality']=='vision';n=10 if vision else 3
        for condition,flip in [(('clean' if vision else 'D0'),False),(('brightness_up:0' if vision else 'D3:0'),True)]:
            output=np.zeros((2,n),dtype=np.float32);output[0,int(flip)]=1.;output[1,int(not flip)]=1.
            cache.predict_once(identity,[dict(source_id=s,condition=condition,label=i,input_sha256='2'*64)
                for i,s in enumerate(ids)],lambda output=output:output)
    cache.close()
    monkeypatch.setattr(run_p4,'require_complete_predictions',lambda records:None,raising=False)
    monkeypatch.setattr(run_p4,'qc_conditioned_report',lambda *args,**kwargs:pytest.fail('inactive manual helper called'))
    metadata=telemetry_metadata_fixture()
    (shared/'telemetry_variants.json').write_text(json.dumps(metadata))
    (shared/'bank_manifest.json').write_text(json.dumps({'metadata':{'telemetry_variants.json':core.sha256_file(shared/'telemetry_variants.json')}}))
    (shared/'vision_sources.json').write_text(json.dumps([dict(source_id=s,driver_id=f'p{i}') for i,s in enumerate(ids)]))
    runtime=tmp_path/'runtime_benchmark';runtime.mkdir();workers=[]
    for identity in ('MN-HPO42','RN-HPO42'):
        checkpoint=tmp_path/core.FROZEN_IDENTITIES[identity]['path'];checkpoint.parent.mkdir(parents=True,exist_ok=True);checkpoint.write_bytes(b'synthetic')
        for i in range(6):
            (runtime/f'{identity}_round{i}.json').write_text(json.dumps(dict(round=i,
                latency_nanoseconds=[1,2],throughput_calls=100,throughput_loop_nanoseconds=1000000,
                rss_before_session_bytes=10,rss_after_session_bytes=20,lifecycle_ru_maxrss=30)))
            workers.append(dict(stage='runtime',model=identity,sampled_peak_rss_bytes=30,samples=[]))
    (tmp_path/'budget_state.json').write_text(json.dumps({'workers':workers}))
    monkeypatch.setattr(run_p4,'ROOT',tmp_path)
    monkeypatch.setattr(run_p4,'verify_preflight',lambda spec:{'models':{identity:{'onnx_path':str(tmp_path/core.FROZEN_IDENTITIES[identity]['path'])}
        for identity in ('MN-HPO42','RN-HPO42')}})
    run_p4.aggregate(dict(run_dir=str(tmp_path),binding=binding(),qc_lock='must_not_open',qc_cue_checks='must_not_open'))
    report=json.loads((tmp_path/'evaluation_metrics.json').read_text())
    assert report['qc']['status']=='REMOVED_FROM_SCOPE' and report['qc']['automatic_human_validation'] is False
    assert len(report['models'])==7
    for model in report['models'].values():
        assert model['clean']['accuracy']==1. and model['clean']['macro_f1']>0
        assert model['clean']['classes'] and model['clean']['confusion']
        assert all('macro_f1' not in stress and stress['f1_eligible'] is False
            and stress['label_validity']=='LABEL_VALIDITY_UNVERIFIED' for stress in model['stress'].values())
    assert 'human_review_evidence' not in report['qc'] and 'valid_retention' not in report['qc']


def test_v2_cached_aggregation_cli_needs_only_external_approval_and_remaining_budget(core,tmp_path,monkeypatch):
    from ml.experiments import run_p4
    protocol=run_p4.ROOT/'ml/configs/p4_protocol.json';frozen=run_p4.binding_for(protocol,'synthetic_cached_v2')
    run=tmp_path/frozen['run_id'];run.mkdir()
    approval_path=tmp_path/'synthetic_approval.json'
    approval_path.write_text(json.dumps(dict(frozen,phase='P4-B',authorized=True,human_approval='SYNTHETIC_ONLY')))
    spec=run/'execution_spec.json'
    spec.write_text(json.dumps(dict(binding=frozen,protocol_path=str(protocol),run_dir=str(run),approval_path=str(approval_path))))
    (run/'completion.json').write_text(json.dumps({'status':'MACHINE_EVALUATION_COMPLETED'}))
    (run/'budget_state.json').write_text(json.dumps({'total_used_seconds':100.,'stage_used_seconds':{'aggregation':20.}}))
    calls=[]
    class Supervisor:
        def __init__(self,path,**settings):
            Path(path).mkdir();self.total_used=1.;self.stage_used={'aggregation':1.}
            assert settings['total_seconds']==14300.
            assert settings['stage_caps']=={'aggregation':1180.}
        def run(self,command,**limits):calls.append((command,limits))
    monkeypatch.setattr(run_p4,'BudgetSupervisor',Supervisor)
    monkeypatch.setattr(run_p4,'formal_provenance',lambda:{'protected_hashes':{}})
    assert run_p4.main(['aggregate-cached','--execution-spec',str(spec),'--approval',str(approval_path)])==0
    assert len(calls)==1 and calls[0][1]['stage']=='aggregation'
    saved=json.loads((run/'cached_aggregation/execution_spec.json').read_text())
    assert 'qc_lock' not in saved and 'qc_cue_checks' not in saved and 'reviewers' not in saved
    cumulative=json.loads((run/'cached_aggregation/cumulative_budget.json').read_text())
    assert cumulative['combined_machine_seconds']==101. and cumulative['prediction_forward_count']==0


def test_v2_private_preflight_rejects_old_protocol_before_any_evidence_read(core,tmp_path,monkeypatch):
    from ml.experiments import run_p4
    protocol=json.loads((run_p4.ROOT/'ml/configs/p4_protocol.json').read_text());protocol['protocol']='P4-PROTOCOL-v1'
    old=tmp_path/'old_protocol.json';old.write_text(json.dumps(protocol))
    frozen=run_p4.binding_for(old,'synthetic_old_protocol')
    approval_path=tmp_path/'synthetic_approval.json'
    approval_path.write_text(json.dumps(dict(frozen,phase='P4-B',authorized=True,human_approval='SYNTHETIC_ONLY')))
    spec=tmp_path/'spec.json';spec.write_text(json.dumps(dict(binding=frozen,protocol_path=str(old),approval_path=str(approval_path))))
    monkeypatch.setenv('P4_BUDGET_WORKER','1')
    monkeypatch.setattr(run_p4,'verify_preflight',lambda *args:pytest.fail('old protocol accessed evidence'))
    with pytest.raises(ValueError,match='protocol'):
        run_p4.main(['_verify-preflight','--execution-spec',str(spec)])
