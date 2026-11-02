"""Approved CPU telemetry P2/P3: one bounded run, no automatic resume."""
import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ENTRY_STARTED = time.monotonic()
for variable in ['OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS']:
    os.environ[variable]='2'
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ml.experiments import comparator_common as common
from ml.experiments import hpo_protocol as protocol

MODELS = ['xgboost', 'random_forest', 'logistic_regression']


def final_status(outer_status, inner_status):
    if 'TIME_BUDGET_EXCEEDED' in [outer_status, inner_status]:
        return 'TIME_BUDGET_EXCEEDED'
    return inner_status if outer_status == 'COMPLETED' else outer_status


def save(path, value):
    common.write_json(path, value, replace=Path(path).exists())


def build_schedule(cfg):
    result=[]
    for model in MODELS:
        configs=protocol.search_configs(model,cfg)
        for i,config in enumerate(configs,1):
            result.append({'trial_id':f'{model}_{i:02d}','model':model,'phase':'P2' if i==1 else 'P3',
                           'role':'SEARCH','seed':42,'config':config})
        for i,seed in enumerate([43,44],len(configs)+1):
            result.append({'trial_id':f'{model}_{i:02d}','model':model,'phase':'P3',
                           'role':'CONFIRMATION','seed':seed,'config':None})
    return result


def _stop(process):
    if process.poll() is not None:return
    try:os.killpg(process.pid,signal.SIGTERM)
    except ProcessLookupError:return
    try:process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid,signal.SIGKILL)
        process.wait()


def supervise_command(command, log_path, deadline, env=None):
    start=time.monotonic()
    if start>=deadline:return {'status':'NOT_RUN_BUDGET','command_started':False,'wall_seconds':0.,'returncode':None}
    with Path(log_path).open('x') as log:
        process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,env=env)
        status='COMPLETED'
        try:process.wait(timeout=max(0.,deadline-time.monotonic()))
        except subprocess.TimeoutExpired:
            status='TIME_BUDGET_EXCEEDED';_stop(process)
        except BaseException:
            _stop(process);raise
    elapsed=time.monotonic()-start
    if elapsed>=deadline-start:status='TIME_BUDGET_EXCEEDED'
    elif process.returncode:status='IMPLEMENTATION_FAILED'
    return {'status':status,'command_started':True,'wall_seconds':elapsed,'returncode':process.returncode,'command':command}


def write_unrun_artifacts(directory,row):
    import pandas as pd
    directory.mkdir(parents=True,exist_ok=True)
    for name,value in {'config.json':row,'validation_metrics.json':{'status':row['status']},
                       'class_report.json':{'status':'NOT_EVALUATED'},
                       'selection_log.json':{'status':'NOT_SELECTED','test_used':False}}.items():
        if not (directory/name).exists():save(directory/name,value)
    if not (directory/'trials.csv').exists():pd.DataFrame([{k:row.get(k) for k in ['trial_id','model','role','seed','status']}]).to_csv(directory/'trials.csv',index=False)
    if not (directory/'timing_samples.csv').exists():pd.DataFrame(columns=['phase','seconds','warmup','device','threads']).to_csv(directory/'timing_samples.csv',index=False)
    if not (directory/'artifact_manifest.json').exists():save(directory/'artifact_manifest.json',{
        'status':row['status'],'artifacts':{'predictions_test.csv':{'status':'NOT_YET_DUE'},
        'checkpoint':{'status':'NOT_CREATED_BUDGET' if row['status']=='NOT_RUN_BUDGET' else 'NOT_CREATED_FAILURE'}}})


def run_one_trial(row,directory,cfg,context,data_root,global_deadline):
    directory.mkdir(parents=True,exist_ok=False)
    deadline=min(global_deadline,time.monotonic()+300)
    request={**row,'threads':2,'train_rows':21000,'validation_rows':4500,'data_root':str(data_root),'context':context}
    save(directory/'config.json',request)
    environment=dict(os.environ,FYP_TELEMETRY_DEADLINE=str(deadline))
    command=[str(common.ROOT/'.venv/bin/python'),'-B',str(common.ROOT/'ml/telemetry/train_hpo.py'),'--run-dir',str(directory)]
    execution=supervise_command(command,directory/'execution.log',deadline,environment)
    metrics=json.loads((directory/'validation_metrics.json').read_text()) if (directory/'validation_metrics.json').exists() else {}
    status=execution['status']
    if status=='COMPLETED' and metrics.get('status')!='COMPLETED':status='IMPLEMENTATION_FAILED'
    result={**row,'status':status,'directory':str(directory),'metrics':metrics,'execution':execution,
            'checkpoint':str(directory/'checkpoint.joblib'),'trees_used':metrics.get('trees_used',400)}
    if status!='COMPLETED':write_unrun_artifacts(directory,result)
    return result


def execute_schedule(directory,cfg,context,data_root,deadline):
    import numpy as np
    import pandas as pd
    plans=build_schedule(cfg)
    result={'status':'RUNNING','trials':[],'selection':{m:{'status':'INCOMPLETE_SEARCH'} for m in MODELS}}
    start=time.monotonic()
    stopped=False
    for row in plans:
        model=row['model'];selected=result['selection'][model]
        if stopped or time.monotonic()>=deadline:
            stopped=True
            item={**row,'status':'NOT_RUN_BUDGET' if result['status']!='IMPLEMENTATION_FAILED' else 'NOT_RUN_IMPLEMENTATION_FAILURE'}
            write_unrun_artifacts(directory/model/row['trial_id'],item)
        elif model=='logistic_regression' and row['seed']==44 and selected.get('deterministic_duplicate'):
            item={**row,'config':selected['config'],'status':'SKIPPED_DETERMINISTIC_DUPLICATE','independent_evidence':False}
        else:
            if row['role']=='CONFIRMATION':row={**row,'config':selected['config']}
            print('START',row['trial_id'],row['phase'],row['seed'],row['config'],flush=True)
            item=run_one_trial(row,directory/model/row['trial_id'],cfg,context,data_root,deadline)
            print('END',row['trial_id'],item['status'],flush=True)
            if item['status']!='COMPLETED':
                result['status']=item['status'];stopped=True
            elif row['role']=='CONFIRMATION' and model=='logistic_regression' and row['seed']==43:
                base=next(r for r in result['trials'] if r['trial_id']==selected['selected_trial_id'])
                a=np.load(Path(base['directory'])/'probabilities_validation.npy',allow_pickle=False)
                b=np.load(Path(item['directory'])/'probabilities_validation.npy',allow_pickle=False)
                if np.array_equal(a,b):
                    item.update(status='DETERMINISTIC_DUPLICATE',independent_evidence=False)
                    selected['deterministic_duplicate']=True
        result['trials'].append(item)
        searches=[r for r in result['trials'] if r['model']==model and r['role']=='SEARCH' and r['status']=='COMPLETED']
        if row['role']=='SEARCH' and len(searches)==cfg['models'][model]['search_trials']:
            frozen=protocol.select_trial(searches,model,cfg)
            result['selection'][model]={'status':'FROZEN_VALIDATION_SELECTION','selected_trial_id':frozen['trial_id'],
                'config':frozen['config'],'checkpoint':frozen['checkpoint'],'frozen_seed':42,
                'validation_macro_f1':frozen['metrics']['macro_f1'],'validation_log_loss':frozen['metrics']['log_loss'],
                'confirmation_seeds_completed':[],'test_used':False}
            selected=result['selection'][model]
        if row['role']=='CONFIRMATION' and item['status'] in ['COMPLETED','DETERMINISTIC_DUPLICATE']:
            selected['confirmation_seeds_completed'].append(row['seed'])
            base=next(r for r in result['trials'] if r['trial_id']==selected['selected_trial_id'])
            confirmations=[r for r in result['trials'] if r['model']==model and r['role']=='CONFIRMATION' and r['status'] in ['COMPLETED','DETERMINISTIC_DUPLICATE']]
            values=[base['metrics']['macro_f1'],*[r['metrics']['macro_f1'] for r in confirmations]]
            selected.update(confirmation_macro_f1_mean=float(np.mean(values)),confirmation_macro_f1_std=float(np.std(values,ddof=0)),
                            confirmation_std_ddof=0,confirmation_seed_values=[42,*selected['confirmation_seeds_completed']])
        result['used_wall_seconds']=time.monotonic()-start
        save(directory/'selection_log.json',result['selection'])
        save(directory/'artifact_manifest.json',result)
        pd.DataFrame([{k:(json.dumps(r.get(k)) if isinstance(r.get(k),dict) else r.get(k)) for k in ['trial_id','model','phase','role','seed','status','config']} for r in result['trials']]).to_csv(directory/'trials.csv',index=False)
    if result['status']=='RUNNING':result['status']='COMPLETED'
    save(directory/'artifact_manifest.json',result)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id',required=True)
    parser.add_argument('--data-root',type=Path,default=common.DEFAULT_DATA)
    parser.add_argument('--coordinate',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args()
    cfg=protocol.load_protocol()
    if args.coordinate:
        if 'FYP_TELEMETRY_GLOBAL_DEADLINE' not in os.environ:parser.error('Outer supervisor required')
        def interrupt(signum,frame):raise KeyboardInterrupt
        signal.signal(signal.SIGTERM,interrupt)
        directory=protocol.safe_run(args.run_id)
        context=json.loads((directory/'config.json').read_text())
        result=execute_schedule(directory,cfg,context,args.data_root,float(os.environ['FYP_TELEMETRY_GLOBAL_DEADLINE']))
        print(json.dumps({'run_id':args.run_id,'status':result['status'],'used_wall_seconds':result['used_wall_seconds']}),flush=True)
        return 0 if result['status']=='COMPLETED' else 1
    if not __import__('re').fullmatch(r'p3_telemetry_\d{8}',args.run_id):parser.error('Use a new p3_telemetry_<YYYYMMDD> run_id')
    environment=protocol.guard_environment()
    directory=protocol.safe_run(args.run_id,create=True)
    source_names=['ml/experiments/run_telemetry_hpo.py','ml/telemetry/train_hpo.py','ml/experiments/hpo_protocol.py','ml/experiments/comparator_common.py','ml/configs/bounded_hpo.json']
    context={'run_id':args.run_id,'phase':'P2_P3','environment':environment,'source_hashes':{n:common.sha256(common.ROOT/n) for n in source_names},
             'data_root':str(args.data_root),'budget':cfg['wall_time_limits_seconds'],'test_csv_opened':False,'test_hash_startup_only':True}
    save(directory/'config.json',context)
    deadline=ENTRY_STARTED+2700
    command=[str(common.ROOT/'.venv/bin/python'),'-B',str(Path(__file__).resolve()),'--run-id',args.run_id,'--data-root',str(args.data_root),'--coordinate']
    execution=supervise_command(command,directory/'execution.log',deadline,dict(os.environ,FYP_TELEMETRY_GLOBAL_DEADLINE=str(deadline)))
    ledger_path=directory/'artifact_manifest.json'
    ledger=json.loads(ledger_path.read_text()) if ledger_path.exists() else {'trials':[],'selection':{}}
    status=final_status(execution['status'],ledger.get('status','IMPLEMENTATION_FAILED'))
    if status!='COMPLETED':
        ledger['status']=status
        known={r['trial_id'] for r in ledger['trials']}
        for row in build_schedule(cfg):
            if row['trial_id'] not in known:
                item={**row,'status':'NOT_RUN_BUDGET' if status=='TIME_BUDGET_EXCEEDED' else 'NOT_RUN_IMPLEMENTATION_FAILURE'}
                write_unrun_artifacts(directory/row['model']/row['trial_id'],item);ledger['trials'].append(item)
    ledger.update(execution=execution,combined_wall_seconds=time.monotonic()-ENTRY_STARTED,protected_hashes_after=common.protected_snapshot())
    save(ledger_path,ledger)
    print(json.dumps({'run_id':args.run_id,'status':ledger.get('status'),'combined_wall_seconds':ledger['combined_wall_seconds']}),flush=True)
    return 0 if ledger.get('status')=='COMPLETED' else 1


if __name__=='__main__':sys.exit(main())
