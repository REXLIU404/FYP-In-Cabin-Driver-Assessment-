"""Read-only S3 audit: saved JSON/CSV/logs and Git blobs; no ML imports."""
import csv
import hashlib
import itertools
import json
import math
import statistics
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
RUN = ROOT / 'ml/outputs/runs/p3_vision_20261018'
HERE = Path(__file__).resolve().parent
checks = []
inputs = {}


def load(path):
    path = Path(path)
    data = path.read_bytes()
    inputs[str(path.relative_to(ROOT))] = hashlib.sha256(data).hexdigest()
    return json.loads(data)


def check(name, passed, detail=None):
    checks.append({'name': name, 'passed': bool(passed), 'detail': detail})
    if not passed:
        print('FAIL', name, detail)


def close(a, b):
    return math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12)


def blob(head, path):
    return subprocess.check_output(['git', 'show', f'{head}:{path}'], cwd=ROOT)


def checksum(value):
    return hashlib.sha256(value).hexdigest()


state = load(RUN / 'search_state.json')
context = load(RUN / 'search_config.json')
selection = load(RUN / 'selection_log.json')
cfg = load(ROOT / 'ml/configs/bounded_hpo.json')
budget = load(ROOT / 'ml/configs/approved_vision_budget.json')
models = ['mobilenet_v3_large', 'resnet18']
head = context['environment']['git']['execution_commit']
check('execution commit matches 335da4e', head == '335da4e3de203836c045452f84cc291bcd352a26')
check('HEAD matches executed commit', subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() == head)
check('branch identity', context['environment']['git']['branch'] == 'fyp2/ml-training')
check('tracked clean recorded', context['environment']['git']['tracked_worktree_clean'] is True)
check('staging empty recorded', context['environment']['git']['staged_paths'] == '')
check('only protected audit untracked at first start', context['environment']['git']['dirty_state_at_first_start'] == '?? docs/fyp2/09_INDEPENDENT_AUDIT_REVIEW.md')
check('budget explicit exact limits', budget['launch_authorized'] is True and budget['per_trial'] == 2400 and budget['per_model'] == {'mobilenet_v3_large': 17100, 'resnet18': 15300} and budget['total'] == 32400)
check('budget no automatic extension', budget['automatic_budget_extension'] is False and budget['grid_changes_authorized'] is False)
check('budget resources unchanged', budget['resource_constraints'] == {'device':'mps', 'batch_size':64, 'cpu_threads':2, 'workers':0})
for path in [*context['source_hashes'], 'ml/configs/bounded_hpo.json', 'ml/configs/approved_vision_budget.json']:
    saved = blob(head, path)
    current = (ROOT / path).read_bytes()
    check(f'current bytes equal executed commit: {path}', current == saved)
    if path in context['source_hashes']:
        check(f'recorded source SHA matches executed blob: {path}', checksum(saved) == context['source_hashes'][path])
check('protocol hash matches execution commit', checksum(blob(head, 'ml/configs/bounded_hpo.json')) == context['protocol_sha256'])
check('phase COMPLETED', state['phase'] == 'search' and state['status'] == 'COMPLETED')
check('root selection equals ledger', selection == state['selection'])
check('no excluded or budget stopped trials', state['excluded_trials'] == [] and state['model_budget_stops'] == {})
check('exactly 16 attempts and logical trials', len(state['attempts']) == len(state['trials']) == 16)
check('logical keys unique', len({a['key'] for a in state['attempts']}) == 16)
plans = []
summary = {}
previous_finished = 0.0
previous_started = 0.0
mixed_clock_gaps = []
for model in models:
    specification = cfg['models'][model]
    grid = specification['grid']
    combinations = [dict(zip(grid, values)) for values in itertools.product(*grid.values())]
    check(f'{model} exact grid', combinations == [dict(learning_rate=lr, weight_decay=wd) for lr in [.0001,.0003,.0008] for wd in [.0001,.001]])
    expected = []
    for i, combination in enumerate(combinations, 1):
        expected.append({'trial_id':f'search_{i:03d}', 'model':model, 'role':'SEARCH', 'seed':42, 'config':combination, 'max_epochs':8, 'is_p2':i==1})
    expected += [{'trial_id':f'confirm_{seed}', 'model':model, 'role':'CONFIRMATION', 'seed':seed, 'config':None, 'max_epochs':8, 'is_p2':False} for seed in [43,44]]
    plans.extend(expected)
    attempts = [a for a in state['attempts'] if a['plan']['model'] == model]
    search = [a for a in attempts if a['plan']['role'] == 'SEARCH']
    confirmations = [a for a in attempts if a['plan']['role'] == 'CONFIRMATION']
    check(f'{model} 6 searches and 2 confirmations', len(attempts) == 8 and len(search) == 6 and len(confirmations) == 2)
    check(f'{model} search plans match exact registered grid', [a['plan'] for a in search] == expected[:6])
    check(f'{model} P2 first search counted once', sum(a['plan']['is_p2'] for a in attempts) == 1 and search[0]['plan']['is_p2'] is True)
    check(f'{model} search seed42 only', {a['plan']['seed'] for a in search} == {42})
    check(f'{model} confirmations 43 and 44', [a['plan']['seed'] for a in confirmations] == [43,44])
    model_time = sum(a['wall_seconds'] for a in attempts)
    check(f'{model} budget cap respected', model_time <= budget['per_model'][model])
    highest = max(a['metrics']['macro_f1'] for a in search)
    tied = [a for a in search if highest-a['metrics']['macro_f1'] < cfg['selection']['tie_macro_f1_absolute_tolerance']]
    best = min(tied, key=lambda a:(a['metrics']['log_loss'], a['metrics']['best_epoch'], int(a['plan']['trial_id'].split('_')[-1])))
    chosen = selection[model]
    check(f'{model} independent tolerance/loss/epoch/id selection', chosen['selected_trial_id'] == best['plan']['trial_id'] and chosen['config'] == best['plan']['config'])
    check(f'{model} frozen seed42 checkpoint, no confirmation reselection', chosen['frozen_seed'] == 42 and chosen['confirmation_cannot_reselect'] is True and chosen['checkpoint'] == best['directory']+'/checkpoint.pt')
    check(f'{model} confirmation configs frozen to selected search', all(a['plan']['config'] == best['plan']['config'] for a in confirmations))
    check(f'{model} confirmations completed after all search', all(a['started_wall_time'] >= search[-1]['started_wall_time']+search[-1]['wall_seconds']-0.01 for a in confirmations))
    values = [best['metrics']['macro_f1'], *[a['metrics']['macro_f1'] for a in confirmations]]
    mean = statistics.mean(values)
    std = statistics.pstdev(values)
    check(f'{model} seed IDs and values', chosen['validation_seed_ids'] == [42,43,44] and chosen['validation_seed_values'] == values)
    check(f'{model} mean independently recomputed', close(chosen['macro_f1_mean'], mean))
    check(f'{model} std ddof0 independently recomputed', chosen['std_ddof'] == 0 and close(chosen['macro_f1_std'], std))
    check(f'{model} all searches and confirmations covered', chosen['missing_confirmation_seeds'] == [] and chosen['search_trials_completed'] == chosen['search_trials_planned'] == 6)
    for a in attempts:
        label = a['key']
        directory = RUN/a['directory']
        request = load(directory/'config.json')
        metrics = load(directory/'validation_metrics.json')
        local_selection = load(directory/'selection_log.json')
        check(f'{label} one completed attempt returncode0', a['status'] == a['execution']['status'] == 'COMPLETED' and a['execution']['returncode'] == 0 and a['directory'].endswith('/attempt_01'))
        check(f'{label} trial ledger points completed attempt', state['trials'][label] == {'status':'COMPLETED', 'attempt':a['directory']})
        check(f'{label} trial wall within cap and timeout', 0 < a['execution']['wall_seconds'] <= a['wall_seconds'] <= a['timeout_seconds'] <= budget['per_trial'] and a['execution']['wall_seconds'] <= a['execution']['timeout_seconds'] <= a['timeout_seconds'])
        check(f'{label} saved request exact', request == {'plan':a['plan'],'phase':'search','context':context,'timeout_seconds':a['timeout_seconds']})
        check(f'{label} metrics match ledger', metrics == a['metrics'])
        check(f'{label} fixed train/val batch/resources/scheduler', all(metrics[k] == v for k,v in {'train_samples':15899,'validation_samples':2868,'batch_size':64,'device':'mps','threads':2,'workers':0,'cosine_T_max':8,'early_stopping_patience':2}.items()))
        check(f'{label} formal validation not test', metrics['interpretation'] == 'FORMAL_VALIDATION_ONLY' and metrics['counts_toward_hpo'] is True and metrics['test_predictions'] == metrics['test_images_opened'] == 0)
        check(f'{label} selection split only val and deferred test', local_selection['selection_split'] == 'val' and local_selection['probe_used_for_model_selection'] is False and local_selection['test_predictions'] == 'NOT_YET_DUE')
        epochs = metrics['epochs']
        check(f'{label} <=8 completed epochs', 1 <= len(epochs) == metrics['epochs_completed'] <= 8 and [e['epoch'] for e in epochs] == list(range(1,len(epochs)+1)))
        best_score, bad, best_epoch, stopped = -1., 0, None, False
        for e in epochs:
            check(f'{label} epoch{e["epoch"]} finite metrics/time', all(isinstance(v,(int,float)) and math.isfinite(v) for v in e.values()) and e['train_seconds'] > 0 and e['validation_seconds'] > 0)
            predicted_lr = a['plan']['config']['learning_rate'] * (1+math.cos(math.pi*(e['epoch']-1)/8))/2
            check(f'{label} epoch{e["epoch"]} cosine Tmax8 rate', close(e['learning_rate'],predicted_lr))
            check(f'{label} epoch{e["epoch"]} was not run after patience reached', not stopped)
            if e['macro_f1'] > best_score:
                best_score,bad,best_epoch=e['macro_f1'],0,e['epoch']
            else:
                bad += 1
            stopped = bad >= 2
        check(f'{label} stop only at epoch8 or patience2', len(epochs)==8 or stopped)
        check(f'{label} best epoch and metric recomputed', best_epoch == metrics['best_epoch'] and close(best_score,metrics['macro_f1']))
        check(f'{label} best logloss matches selected epoch', close(metrics['log_loss'], epochs[best_epoch-1]['log_loss']))
        execution = (directory/'execution.log').read_bytes()
        inputs[str((directory/'execution.log').relative_to(ROOT))] = checksum(execution)
        loglines = execution.decode().splitlines()
        logged_epochs = [json.loads(line) for line in loglines if line.startswith('{')]
        check(f'{label} actual stdout epoch records match saved metrics', logged_epochs == epochs)
        check(f'{label} stdout TRIAL_COMPLETE matches checkpoint epoch/score', loglines[-1] == f'TRIAL_COMPLETE {model} {a["plan"]["trial_id"]} {best_epoch} {metrics["macro_f1"]}')
        with (directory/'trials.csv').open(newline='') as handle:
            trial_rows = list(csv.DictReader(handle))
        check(f'{label} trials.csv exactly one formal row', len(trial_rows)==1 and trial_rows[0]['status']=='COMPLETED' and trial_rows[0]['counts_toward_hpo']=='True' and int(trial_rows[0]['seed'])==a['plan']['seed'] and json.loads(trial_rows[0]['config'])==a['plan']['config'] and close(float(trial_rows[0]['macro_f1']),metrics['macro_f1']))
        check(f'{label} strictly increasing recorded start order', a['started_wall_time'] > previous_started)
        if previous_started:
            mixed_clock_gaps.append({'trial':label,'unix_start_minus_previous_unix_plus_monotonic_elapsed':a['started_wall_time']-previous_finished})
        previous_started = a['started_wall_time']
        previous_finished = a['started_wall_time']+a['wall_seconds']
    summary[model] = {'selected_trial':chosen['selected_trial_id'],'config':chosen['config'],'best_seed42_macro_f1':values[0],'seed_macro_f1':values,'macro_f1_mean':mean,'macro_f1_std_ddof0':std,'seed_range':max(values)-min(values),'wall_seconds':model_time,'wall_budget_seconds':budget['per_model'][model],'epochs_completed':sum(a['metrics']['epochs_completed'] for a in attempts),'trials':[{'trial_id':a['plan']['trial_id'],'seed':a['plan']['seed'],'macro_f1':a['metrics']['macro_f1'],'log_loss':a['metrics']['log_loss'],'best_epoch':a['metrics']['best_epoch'],'epochs_completed':a['metrics']['epochs_completed'],'wall_seconds':a['wall_seconds']} for a in attempts]}
signature = hashlib.sha256(json.dumps({'plans':plans, 'budget':budget, 'context':context},sort_keys=True).encode()).hexdigest()
check('canonical plan/budget/context signature', signature == state['signature'])
attempt_seconds = sum(a['wall_seconds'] for a in state['attempts'])
check('total wall ledger includes attempt time and within cap', attempt_seconds <= state['used_wall_seconds'] <= budget['total'])
check('total elapsed independently consistent with first/last worker times', state['used_wall_seconds'] >= previous_finished-state['attempts'][0]['started_wall_time']-0.01)
summary['total'] = {'attempt_seconds':attempt_seconds,'used_wall_seconds':state['used_wall_seconds'],'controller_overhead_seconds':state['used_wall_seconds']-attempt_seconds,'approved_total_seconds':budget['total'],'budget_excluded_trials':state['excluded_trials'],'epochs_completed':sum(a['metrics']['epochs_completed'] for a in state['attempts']),'mixed_clock_gaps':mixed_clock_gaps}
result = {'status':'VERIFIED_PASS' if all(c['passed'] for c in checks) else 'FAILED','scope':'Saved protocol, selection, budgets, epoch logs, executed Git commit; no training, model load, forward, raw test data, or original artifact edits','checks_passed':sum(c['passed'] for c in checks),'checks_total':len(checks),'summary':summary,'checks':checks,'input_sha256':inputs,'limitations':['Evidence-only verification cannot prove absence of unlogged raw-data access; source and logs record zero test images/predictions.','Only one fixed validation split; seed42 is selected among 6 configurations, so its peak score is selected and optimistic.','Confirmation seeds validate variation without reselecting; n=3 mean/std is descriptive, not a confidence interval or significance claim.','MobileNet V2 versus ResNet18 V1 ImageNet pretraining recipes differ; report comparison as complete specified pipelines.','MPS bitwise determinism is not guaranteed.','Unix start times and monotonic elapsed durations cannot be strictly concatenated: one mixed-clock derived gap is -0.0411s. The controller synchronously waits for each worker; source and increasing starts support sequential execution, but no single-clock per-worker end timestamps were captured. This is an audit limitation, not evidence of overlapping fits.','Held-out test and E1 remain deferred to new P4 authorization; no safety or real-world generalization claim.','Bounded HPO config retains prior S1 pending-decision text; explicit committed S2 approved_vision_budget.json is the newer applicable budget authorization.']}
(HERE/'config.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
print(json.dumps({k:result[k] for k in ['status','checks_passed','checks_total','summary','limitations']},indent=2))
raise SystemExit(0 if result['status']=='VERIFIED_PASS' else 1)
