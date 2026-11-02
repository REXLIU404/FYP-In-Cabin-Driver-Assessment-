"""User-operated MPS weight fetch, bounded probe/search, and read-only status."""
import argparse
import copy
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

ENTRY_STARTED=time.monotonic()
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ml.experiments import comparator_common as common
from ml.experiments import hpo_protocol as protocol

MODELS = ['mobilenet_v3_large', 'resnet18']
WEIGHTS = {'mobilenet_v3_large': ('mobilenet_v3_large-5c1a4163.pth', '5c1a4163'),
           'resnet18': ('resnet18-f37072fd.pth', 'f37072fd')}


def atomic_json(path, value):
    path=Path(path)
    common.reject_symlink_path(path)
    temporary=path.with_name(f'.{path.name}.{uuid.uuid4().hex}.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    os.replace(temporary,path)


def require_mps():
    import torch
    if not torch.backends.mps.is_available():raise ValueError('MPS required; CPU fallback is not authorized')


def weights_cache():
    import torch
    return Path(torch.hub.get_dir())/'checkpoints'


def cached_weight_records(require_resnet=True):
    result={}
    for model,(filename,prefix) in WEIGHTS.items():
        path=weights_cache()/filename
        if not path.is_file():
            if model=='resnet18' and not require_resnet:continue
            raise ValueError(f'Missing local pretrained weights: {path}; use fetch-weights in your terminal')
        record=common.file_record(path)
        if not record['sha256'].startswith(prefix):raise ValueError(f'Pretrained SHA-256 checksum mismatch: {path}')
        result[model]={**record,'recipe':'IMAGENET1K_V2' if model=='mobilenet_v3_large' else 'IMAGENET1K_V1'}
    return result


def load_approved_budget(path=None):
    path=Path(path or common.ROOT/'ml/configs/approved_vision_budget.json')
    if not path.is_file():raise ValueError('Missing approved vision budget; explicit numeric approval required')
    return protocol.validate_vision_budget(json.loads(path.read_text()))


def _stop(process):
    if process.poll() is not None:return
    try:os.killpg(process.pid,signal.SIGTERM)
    except ProcessLookupError:return
    try:process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid,signal.SIGKILL);process.wait()


def supervise(command,log_path,timeout):
    if timeout<=0:return {'status':'TIME_BUDGET_EXCEEDED','returncode':None,'wall_seconds':0.}
    start=time.monotonic();deadline=start+timeout
    env=dict(os.environ,FYP_VISION_DEADLINE=str(deadline),FYP_VISION_PARENT=str(os.getpid()))
    with Path(log_path).open('x') as log:
        process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,env=env,start_new_session=True)
        if '--attempt-dir' in command:
            directory=Path(command[command.index('--attempt-dir')+1])
            atomic_json(directory/'process.json',{'pid':process.pid,'command':command})
        status='COMPLETED'
        try:process.wait(timeout=max(0.,deadline-time.monotonic()))
        except subprocess.TimeoutExpired:status='TIME_BUDGET_EXCEEDED';_stop(process)
        except BaseException:_stop(process);raise
    elapsed=time.monotonic()-start
    if elapsed>=timeout:status='TIME_BUDGET_EXCEEDED'
    elif process.returncode:status='IMPLEMENTATION_FAILED'
    return {'status':status,'returncode':process.returncode,'wall_seconds':elapsed,'timeout_seconds':timeout}


def _under(root,name):
    path=root/name
    common.reject_symlink_path(path)
    if not path.resolve().is_relative_to(root.resolve()):raise ValueError('Attempt path escapes run directory')
    return path


def _recover_running(directory,state):
    for attempt in state['attempts']:
        if attempt['status']!='RUNNING':continue
        target=_under(directory,attempt['directory'])
        process_file=target/'process.json'
        if process_file.exists():
            old=json.loads(process_file.read_text())
            # Kill only an orphan whose live command still identifies this exact
            # worker attempt; never signal an unrelated reused PID.
            actual=subprocess.run(['ps','-p',str(old['pid']),'-o','command='],capture_output=True,text=True).stdout
            if str(target) in actual and 'ml/vision/train_hpo.py' in actual:
                try:os.killpg(old['pid'],signal.SIGTERM)
                except ProcessLookupError:pass
                raise ValueError('Interrupted worker was stopped; retry the same command after it exits')
        charged=min(attempt['timeout_seconds'],max(.000001,time.time()-attempt['started_wall_time']))
        attempt.update(status='INTERRUPTED',wall_seconds=charged,recovery='Recovered after parent exit')
        state['used_wall_seconds']+=charged


def verify_completed(directory,attempt):
    target=_under(directory,attempt['directory'])
    manifest_file=target/'artifact_manifest.json'
    if not manifest_file.is_file():raise ValueError('Completed artifact manifest is missing')
    manifest=json.loads(manifest_file.read_text())
    records=manifest.get('artifacts',{})
    required={'checkpoint.pt','config.json','validation_metrics.json','class_report.json',
              'selection_log.json','predictions_validation.csv','trials.csv','timing_samples.csv'}
    if not required.issubset(records):raise ValueError('Completed artifact manifest lacks required files')
    for name,record in records.items():
        if name=='predictions_test.csv':continue  # Explicitly deferred to P4.
        path=_under(target,name)
        if not path.is_file() or path.stat().st_size!=record['bytes'] or common.sha256(path)!=record['sha256']:
            raise ValueError(f'Completed artifact integrity mismatch: {name}')
    metrics=json.loads((target/'validation_metrics.json').read_text())
    if metrics!=attempt.get('metrics'):raise ValueError('Completed artifact metrics differ from resume ledger')


def run_plan(directory,phase,plans,budget,context,runner=supervise,entry_started=None):
    invocation_started=time.monotonic() if entry_started is None else entry_started
    directory=Path(directory)
    common.reject_symlink_path(directory)
    signature=hashlib.sha256(json.dumps({'plans':plans,'budget':budget,'context':context},sort_keys=True).encode()).hexdigest()
    state_path=directory/f'{phase}_state.json'
    if state_path.exists():
        state=json.loads(state_path.read_text())
        if state['signature']!=signature:raise ValueError('Resume config/source/budget changed; refuse to mix evidence')
        _recover_running(directory,state)
    else:state={'signature':signature,'phase':phase,'status':'RUNNING','attempts':[], 'trials':{},'selection':{},'used_wall_seconds':0.}
    if state['status']=='NOT_RUN_BUDGET':return state
    prior_usage=state['used_wall_seconds'];prior_attempt_count=len(state['attempts'])
    def account():
        charged=sum(a['wall_seconds'] for a in state['attempts'][prior_attempt_count:])
        state['used_wall_seconds']=prior_usage+max(time.monotonic()-invocation_started,charged)
    plans=copy.deepcopy(plans)
    for row in plans:
        key=f'{row["model"]}/{row["trial_id"]}'
        completed=next((a for a in state['attempts'] if a['key']==key and a['status']=='COMPLETED'),None)
        if completed:
            verify_completed(directory,completed)
            continue
        if state['status']=='IMPLEMENTATION_FAILED':break
        if row['role']=='CONFIRMATION':
            candidates=[{**a['plan'],'status':'COMPLETED','metrics':a['metrics']} for a in state['attempts']
                        if a['status']=='COMPLETED' and a['plan']['model']==row['model'] and a['plan']['role']=='SEARCH']
            selected=protocol.select_trial(candidates,row['model'],protocol.load_protocol())
            row['config']=selected['config']
            state['selection'][row['model']]={'selected_trial_id':selected['trial_id'],'frozen_seed':42,
                'config':selected['config'],'confirmation_cannot_reselect':True}
        account()
        model_used=sum(a['wall_seconds'] for a in state['attempts'] if a['plan']['model']==row['model'])
        trial_used=sum(a['wall_seconds'] for a in state['attempts'] if a['key']==key)
        model_limit=budget['per_model'][row['model']] if isinstance(budget['per_model'],dict) else budget['per_model']
        timeout=min(budget['per_trial']-trial_used,model_limit-model_used,budget['total']-state['used_wall_seconds'])
        if timeout<=0:
            state['status']='NOT_RUN_BUDGET';break
        number=1+sum(a['key']==key for a in state['attempts'])
        attempt_started=time.monotonic()
        relative=f'{phase}/{row["model"]}/{row["trial_id"]}/attempt_{number:02d}'
        target=_under(directory,relative);target.mkdir(parents=True,exist_ok=False)
        attempt={'key':key,'plan':row,'directory':relative,'status':'RUNNING','wall_seconds':0.,
                 'timeout_seconds':timeout,'started_wall_time':time.time()}
        state['attempts'].append(attempt)
        atomic_json(target/'config.json',{'plan':row,'phase':phase,'context':context,'timeout_seconds':timeout})
        atomic_json(state_path,state)
        command=[str(common.ROOT/'.venv/bin/python'),'-B',str(common.ROOT/'ml/vision/train_hpo.py'),'--attempt-dir',str(target)]
        started=attempt_started
        try:
            remaining=timeout-(time.monotonic()-attempt_started)
            execution=runner(command,target/'execution.log',remaining) if remaining>0 else {
                'status':'TIME_BUDGET_EXCEEDED','returncode':None,'wall_seconds':0.,'timeout_seconds':timeout}
        except KeyboardInterrupt:
            attempt.update(status='INTERRUPTED',wall_seconds=max(.000001,time.monotonic()-started))
            account();atomic_json(state_path,state);raise
        elapsed=max(execution['wall_seconds'],time.monotonic()-started)
        attempt.update(status=execution['status'],wall_seconds=elapsed,execution=execution)
        account()
        if elapsed>=timeout:attempt['status']='TIME_BUDGET_EXCEEDED'
        if attempt['status']=='COMPLETED':
            metrics=json.loads((target/'validation_metrics.json').read_text())
            if metrics.get('status')!='COMPLETED':attempt['status']='IMPLEMENTATION_FAILED'
            else:attempt['metrics']=metrics
        if attempt['status']=='TIME_BUDGET_EXCEEDED':state['status']='NOT_RUN_BUDGET'
        elif attempt['status']!='COMPLETED':state['status']='IMPLEMENTATION_FAILED'
        state['trials'][key]={'status':'COMPLETED' if attempt['status']=='COMPLETED' else state['status'],'attempt':relative}
        atomic_json(state_path,state)
        if state['status']!='RUNNING':break
    if state['status']=='NOT_RUN_BUDGET':
        for row in plans:
            key=f'{row["model"]}/{row["trial_id"]}'
            if state['trials'].get(key,{}).get('status')!='COMPLETED':state['trials'][key]={'status':'NOT_RUN_BUDGET'}
    elif state['status']=='RUNNING':state['status']='COMPLETED'
    account();atomic_json(state_path,state)
    return state


def budget_proposal(metrics):
    models={}
    for name,result in metrics.items():
        epoch=result['epochs'][0]
        measured=epoch['train_seconds']+epoch['validation_seconds']
        models[name]={'measured_epoch_seconds':measured,'estimated_seconds':measured*8*8*1.15}
    return {'models':models,'estimated_total_seconds':sum(m['estimated_seconds'] for m in models.values()),
            'formula':'(train + full val seconds) * 8 epochs * 8 logical trials * 1.15',
            'launch_authorized':False,'probe_used_for_selection':False,'probe_counts_toward_hpo':False,
            'interpretation':'Time estimate, not a guarantee or approved budget; startup/reload/resource variation remain'}


def _search_plans(cfg):
    plans=[]
    for model in MODELS:
        configs=protocol.search_configs(model,cfg)
        for i,config in enumerate(configs,1):
            plans.append({'trial_id':f'search_{i:03d}','model':model,'role':'SEARCH','seed':42,
                          'config':config,'max_epochs':8,'is_p2':i==1})
        for seed in [43,44]:plans.append({'trial_id':f'confirm_{seed}','model':model,'role':'CONFIRMATION',
            'seed':seed,'config':None,'max_epochs':8,'is_p2':False})
    return plans


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['fetch-weights','probe','search','status'])
    parser.add_argument('--run-id',required=True)
    parser.add_argument('--data-root',type=Path,default=common.DEFAULT_DATA)
    args=parser.parse_args()
    directory=protocol.safe_run(args.run_id)
    if args.command=='status':
        for name in ['probe_state.json','search_state.json','budget_proposal.json']:
            if (directory/name).is_file():print(name,(directory/name).read_text())
        if not directory.exists():print('NOT_STARTED',args.run_id)
        return 0
    require_mps();environment=protocol.guard_environment(require_mps=True);cfg=protocol.load_protocol()
    budget=load_approved_budget() if args.command=='search' else None
    if args.command=='fetch-weights':
        cached_weight_records(require_resnet=False)
        import torch
        from torchvision.models import ResNet18_Weights
        torch.hub.load_state_dict_from_url(ResNet18_Weights.IMAGENET1K_V1.url,check_hash=True,weights_only=True)
    weights=cached_weight_records()
    if directory.exists():common.reject_symlink_path(directory)
    else:directory=protocol.safe_run(args.run_id,create=True)
    manifest=directory/'weights_manifest.json'
    if manifest.exists():
        if json.loads(manifest.read_text())['models']!=weights:raise ValueError('Weight manifest changed')
    else:atomic_json(manifest,{'models':weights,'recipe_difference':'MobileNetV3 V2 versus ResNet18 V1'})
    if args.command=='fetch-weights':
        print('WEIGHTS_READY',json.dumps(weights));return 0
    source_names=['ml/experiments/run_vision_hpo.py','ml/vision/train_hpo.py','ml/experiments/hpo_protocol.py','ml/experiments/comparator_common.py']
    context={'environment':environment,'weights_manifest':weights,'source_hashes':{n:common.sha256(common.ROOT/n) for n in source_names},
             'protocol_sha256':common.sha256(protocol.CONFIG),'data_root':str(args.data_root)}
    # Dirty-state changes from this run's own outputs must not change resume identity.
    context['environment']['git']['dirty_state_at_first_start']=context['environment']['git'].pop('dirty_state')
    context_file=directory/f'{args.command}_config.json'
    if context_file.exists():
        original=json.loads(context_file.read_text())
        context['environment']['git']['dirty_state_at_first_start']=original['environment']['git']['dirty_state_at_first_start']
        if context!=original:raise ValueError('Resume environment, weights, source, or protocol changed')
    else:atomic_json(context_file,context)
    if args.command=='probe':
        plans=[{'trial_id':'probe_001','model':m,'role':'PROBE','seed':42,'config':{'learning_rate':.0008,'weight_decay':.0001},'max_epochs':1,'is_p2':False} for m in MODELS]
        budget={'per_trial':1200,'per_model':1200,'total':2400}
    else:plans=_search_plans(cfg)
    try:state=run_plan(directory,args.command,plans,budget,context,entry_started=ENTRY_STARTED)
    except KeyboardInterrupt:
        print('INTERRUPTED: rerun the identical command to resume');return 130
    if args.command=='probe' and state['status']=='COMPLETED':
        proposal=budget_proposal({a['plan']['model']:a['metrics'] for a in state['attempts'] if a['status']=='COMPLETED'})
        atomic_json(directory/'budget_proposal.json',proposal)
        print('PROBE_COMPLETE',json.dumps(proposal))
    if args.command=='search' and state['status']=='COMPLETED':
        import numpy as np
        for model in MODELS:
            selected=state['selection'][model]
            seed42=next(a for a in state['attempts'] if a['plan']['model']==model and a['plan']['trial_id']==selected['selected_trial_id'] and a['status']=='COMPLETED')
            confirmations=[a for a in state['attempts'] if a['plan']['model']==model and a['plan']['role']=='CONFIRMATION' and a['status']=='COMPLETED']
            values=[seed42['metrics']['macro_f1'],*[a['metrics']['macro_f1'] for a in confirmations]]
            selected.update(validation_seed_values=values,macro_f1_mean=float(np.mean(values)),macro_f1_std=float(np.std(values)),std_ddof=0,
                            checkpoint=f'{seed42["directory"]}/checkpoint.pt',mps_bitwise_reproducibility_guaranteed=False)
        atomic_json(directory/'selection_log.json',state['selection'])
        print('SEARCH_COMPLETE',json.dumps(state['selection']))
    print('VISION_STATUS',args.command,state['status'],'used_seconds',state['used_wall_seconds'])
    return 0 if state['status']=='COMPLETED' else 1


if __name__=='__main__':sys.exit(main())
