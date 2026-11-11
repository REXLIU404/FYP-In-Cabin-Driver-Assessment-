"""P4 protocol enforcement and evaluation. Imports perform no data/model I/O.

Approval artifacts record externally supplied human authorization; their presence
is provenance, not a cryptographic proof of a person's authority. P4-A creates
no approval. All held-out readers must require a P4Authorization before opening.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import signal
import sqlite3
import subprocess
import time
from dataclasses import dataclass
from typing import Callable, Mapping

import numpy as np
import psutil

PROTOCOL = 'P4-PROTOCOL-v2'
GIB = 1024**3
STAGE_CAPS = {'preflight':600, 'shared_inputs':1200, 'vision_clean':1200,
              'vision_stress':7200, 'telemetry':1200, 'runtime':1800, 'aggregation':1200}
FROZEN_IDENTITIES = {
    'MN-HPO42': {'modality':'vision', 'path':'ml/outputs/runs/p3_vision_20261018/search/mobilenet_v3_large/search_006/attempt_01/checkpoint.pt', 'sha256':'bc96e7a230de6391820b1e04e7480087841680ae6cc1b6e73cba42b25eb67295'},
    'RN-HPO42': {'modality':'vision', 'path':'ml/outputs/runs/p3_vision_20261018/search/resnet18/search_004/attempt_01/checkpoint.pt', 'sha256':'008d831c98ea5e4b6c5c821787b3dc9a1dcbc6ca47a74dd1d8f7110eb4ac7d20'},
    'XGB-HPO42': {'modality':'telemetry', 'path':'ml/outputs/runs/p3_telemetry_20261018/xgboost/xgboost_02/checkpoint.joblib', 'sha256':'a464481d25ecb13f7db8392e039ac74855ad22fd80078154c7a4375a81097836'},
    'RF-HPO42': {'modality':'telemetry', 'path':'ml/outputs/runs/p3_telemetry_20261018/random_forest/random_forest_06/checkpoint.joblib', 'sha256':'cca6d8c7a7832b53c7cc0e6d1777e1c9e37b721612bb58e29df26be875c65aba'},
    'LR-HPO42': {'modality':'telemetry', 'path':'ml/outputs/runs/p3_telemetry_20261018/logistic_regression/logistic_regression_06/checkpoint.joblib', 'sha256':'558ac2cbda976822b370f257def52fa1a2dca9bb4cfe0b5e64f29623061c0274'},
    'MN-STABLE': {'modality':'vision', 'path':'ml/outputs/vision/mobilenetv3_large_vision.pt', 'sha256':'196ca7b151d84e0c4a8eac87128da9dd8f22c894984a991ef611536bb523e7c7', 'onnx_path':'ml/outputs/vision/mobilenetv3_large_vision.onnx', 'onnx_sha256':'b3a42e8dd4553355b1fd7d9e7fe3d28e318decb894e76eb029489b7ff2e90bcf'},
    'XGB-STABLE': {'modality':'telemetry', 'path':'ml/outputs/telemetry/xgb_telemetry.json', 'sha256':'9802cb06ca98f0c1befaf851fa7668cfec70e005cf8bb3884e49d7d45d7aec07', 'iteration_range':(0,91)},
}


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def sha256_file(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024**2), b''):
            digest.update(block)
    return digest.hexdigest()


def array_sha256(value):
    array=np.asarray(value)
    return hashlib.sha256(canonical_json({'shape':array.shape,'dtype':str(array.dtype)})+array.tobytes(order='C')).hexdigest()


def atomic_json(path, value):
    path=Path(path); temporary=path.with_name(path.name+'.tmp')
    with temporary.open('xb') as stream:
        stream.write(canonical_json(value));stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,path)


@dataclass(frozen=True)
class P4Authorization:
    protocol_sha256: str
    run_id: str
    source_sha256: str
    human_approval: str
    phase: str = 'P4-B'

    def require_heldout(self):
        # Revalidate even if a caller constructs a dataclass directly.
        authorize_p4b(vars(self) | {'authorized':True}, protocol_sha256=self.protocol_sha256,
                      run_id=self.run_id, source_sha256=self.source_sha256)


def authorize_p4b(approval, *, protocol_sha256, run_id, source_sha256):
    if not isinstance(approval, dict) or approval.get('phase')!='P4-B' or approval.get('authorized') is not True:
        raise ValueError('Separate explicit P4-B approval is required before held-out access')
    if not isinstance(approval.get('human_approval'),str) or not approval['human_approval'].strip():
        raise ValueError('P4-B requires an explicit human approval reference')
    for name,expected in [('protocol_sha256',protocol_sha256),('source_sha256',source_sha256),('run_id',run_id)]:
        if approval.get(name)!=expected:
            raise ValueError(f'P4-B approval {name} binding mismatch')
    if not all(re.fullmatch('[0-9a-f]{64}',h or '') for h in (protocol_sha256,source_sha256)):
        raise ValueError('P4-B requires full protocol/source SHA256')
    if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,99}',run_id or ''):
        raise ValueError('P4-B invalid run ID')
    return P4Authorization(protocol_sha256,run_id,source_sha256,approval['human_approval'])


def authorized_read(approval, reader, **binding):
    authorize_p4b(approval,**binding)
    return reader()


def verify_identity(identity, root):
    spec=FROZEN_IDENTITIES[identity]
    path=Path(root)/spec['path']
    if path.is_symlink() or sha256_file(path)!=spec['sha256']:
        raise ValueError(f'Frozen identity hash mismatch: {identity}')
    return path


class PredictionCache:
    """Transactional once-only row claims. Interrupted claims cannot auto retry.

    A new formal run creates a fresh directory; reopening is read-only for metric
    aggregation. Explicit future continuation requires a separately reviewed tool.
    """
    @classmethod
    def create(cls, path, binding, identities):
        directory=Path(path);directory.mkdir(parents=True,exist_ok=False)
        self=cls(); self.path=directory; self.binding=dict(binding);self.identities=dict(identities)
        self.connection=sqlite3.connect(directory/'predictions.sqlite3')
        self.connection.execute('PRAGMA journal_mode=WAL')
        self.connection.execute('PRAGMA synchronous=FULL')
        self.connection.execute('CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        metadata={'binding':self.binding,'identities':self.identities,'schema':2}
        self.connection.execute('INSERT INTO meta VALUES (?,?)',('manifest',canonical_json(metadata).decode()))
        self.connection.execute('CREATE TABLE predictions (identity TEXT, source_id TEXT, condition TEXT, input_sha TEXT, label INTEGER, status TEXT, payload BLOB, payload_sha TEXT, detail TEXT, PRIMARY KEY(identity,source_id,condition))')
        self.connection.commit();atomic_json(directory/'binding.json',metadata)
        self.read_only=False
        return self

    @classmethod
    def open_readonly(cls,path,binding,identities):
        self=cls();self.path=Path(path);self.binding=dict(binding);self.identities=dict(identities);self.read_only=True
        if self.path.is_symlink():raise ValueError('Cache symlink refused')
        self.connection=sqlite3.connect(f'file:{self.path / "predictions.sqlite3"}?mode=ro',uri=True)
        self._verify_manifest()
        return self

    def _verify_manifest(self):
        expected={'binding':self.binding,'identities':self.identities,'schema':2}
        stored=json.loads(self.connection.execute("SELECT value FROM meta WHERE key='manifest'").fetchone()[0])
        if stored!=expected or json.loads((self.path/'binding.json').read_text())!=expected:
            raise ValueError('Cache identity/binding tamper detected')

    def _row_sha(self,identity,source_id,condition,input_sha,label,payload):
        metadata={'identity':identity,'checkpoint_sha256':self.identities[identity],
            'source_id':source_id,'condition':condition,'input_sha256':input_sha,'label':int(label)}
        return hashlib.sha256(canonical_json(metadata)+payload).hexdigest()

    def predict_once(self,identity,rows,forward):
        self._verify_manifest()
        if self.read_only:raise ValueError('Read-only cache cannot predict')
        if identity not in self.identities:raise ValueError('Unknown model identity')
        if not rows:raise ValueError('Empty prediction batch')
        keys=[(identity,r['source_id'],r['condition']) for r in rows]
        if len(set(keys))!=len(keys):raise ValueError('Duplicate source/condition IDs')
        existing=[self.connection.execute('SELECT input_sha,label,status,payload,payload_sha FROM predictions WHERE identity=? AND source_id=? AND condition=?',k).fetchone() for k in keys]
        if any(existing):
            if not all(existing):raise ValueError('Mixed completed/missing cache batch; no auto resume')
            outputs=[]
            for row,stored in zip(rows,existing):
                input_sha,label,status,payload,digest=stored
                if input_sha!=row['input_sha256'] or label!=row['label']:raise ValueError('Cache input/label hash mismatch')
                if status!='COMPLETED':raise ValueError('Cache incomplete/failed claim; separate continuation approval required')
                if self._row_sha(identity,row['source_id'],row['condition'],input_sha,label,payload)!=digest:raise ValueError('Cache row/payload tamper detected')
                outputs.append(np.load(io.BytesIO(payload),allow_pickle=False))
            return np.stack(outputs)
        with self.connection:
            self.connection.executemany('INSERT INTO predictions VALUES (?,?,?,?,?,?,?,?,?)',
                [(identity,r['source_id'],r['condition'],r['input_sha256'],int(r['label']),'CLAIMED',None,None,None) for r in rows])
        try:
            outputs=np.asarray(forward())
            if outputs.ndim!=2 or len(outputs)!=len(rows) or not np.isfinite(outputs).all():raise ValueError('Invalid nonfinite prediction outputs')
            completed=[]
            for key,row,output in zip(keys,rows,outputs):
                stream=io.BytesIO();np.save(stream,output,allow_pickle=False);payload=stream.getvalue()
                completed.append((payload,self._row_sha(identity,row['source_id'],row['condition'],row['input_sha256'],row['label'],payload),*key))
            with self.connection:
                self.connection.executemany("UPDATE predictions SET status='COMPLETED',payload=?,payload_sha=? WHERE identity=? AND source_id=? AND condition=?",completed)
            return outputs
        except BaseException as error:
            with self.connection:
                self.connection.executemany("UPDATE predictions SET status='FAILED',detail=? WHERE identity=? AND source_id=? AND condition=?",[(repr(error),*key) for key in keys])
            raise

    def records(self):
        self._verify_manifest(); result=[]
        for identity,source_id,condition,input_sha,label,status,payload,digest,detail in self.connection.execute('SELECT * FROM predictions ORDER BY identity,condition,source_id'):
            if status!='COMPLETED':raise ValueError('Incomplete/failed predictions prevent complete aggregation')
            if self._row_sha(identity,source_id,condition,input_sha,label,payload)!=digest:raise ValueError('Cache row/payload tamper detected')
            result.append(dict(identity=identity,source_id=source_id,condition=condition,input_sha256=input_sha,label=label,output=np.load(io.BytesIO(payload),allow_pickle=False)))
        return result

    def close(self):self.connection.close()


def evaluate_shared_conditions(cache,conditions,*,source_ids,labels,models,batch_size=32):
    """Stream one condition at a time; never flatten conditions before batching."""
    if batch_size!=32:raise ValueError('P4 evaluation batch must be 32')
    if len(set(source_ids))!=len(source_ids) or len(labels)!=len(source_ids):raise ValueError('Source IDs must be unique and paired with labels')
    results=[]; seen=set()
    for condition,values in conditions:
        if condition in seen:raise ValueError('Duplicate condition')
        seen.add(condition);values=np.asarray(values)
        if len(values)!=len(source_ids) or not np.isfinite(values).all():raise ValueError('Invalid shared input bank')
        for start in range(0,len(values),32):
            shared=np.ascontiguousarray(values[start:start+32]);before=array_sha256(shared);shared.flags.writeable=False
            rows=[dict(source_id=source_ids[i],condition=condition,label=int(labels[i]),input_sha256=array_sha256(shared[i-start])) for i in range(start,min(start+32,len(values)))]
            for identity,model in models.items():
                def checked_forward(model=model):
                    output=model(shared)
                    if array_sha256(shared)!=before:raise ValueError('Model mutated shared input')
                    return output
                outputs=cache.predict_once(identity,rows,checked_forward)
                if array_sha256(shared)!=before:raise ValueError('Shared input mutation detected')
                results.extend(dict(identity=identity,**row,output=output) for row,output in zip(rows,outputs))
    return results


def probabilities(outputs,n_classes,*,logits):
    outputs=np.asarray(outputs)
    if outputs.ndim!=2 or outputs.shape[1]!=n_classes or not len(outputs) or not np.isfinite(outputs).all():raise ValueError('Invalid class output shape or nonfinite values')
    result=outputs.astype(np.float64)
    if logits:
        result=np.exp(result-result.max(axis=1,keepdims=True));result/=result.sum(axis=1,keepdims=True)
    elif (result<0).any() or (result>1).any() or not np.allclose(result.sum(axis=1),1,rtol=0,atol=1e-6):
        raise ValueError('Invalid probability range or row sums')
    return result


def classification_metrics(labels,outputs,n_classes,*,logits=False):
    labels=np.asarray(labels)
    p=probabilities(outputs,n_classes,logits=logits)
    if labels.shape!=(len(p),) or not np.issubdtype(labels.dtype,np.integer) or (labels<0).any() or (labels>=n_classes).any():raise ValueError('Invalid fixed-class labels')
    predicted=np.asarray(outputs).argmax(axis=1);matrix=np.zeros((n_classes,n_classes),dtype=int)
    np.add.at(matrix,(labels,predicted),1);tp=np.diag(matrix);support=matrix.sum(axis=1);prediction_support=matrix.sum(axis=0)
    precision=np.divide(tp,prediction_support,out=np.zeros(n_classes),where=prediction_support!=0)
    recall=np.divide(tp,support,out=np.zeros(n_classes),where=support!=0)
    f1=np.divide(2*precision*recall,precision+recall,out=np.zeros(n_classes),where=(precision+recall)!=0)
    eps=np.finfo(np.float64).eps;q=np.clip(p,eps,1-eps);q/=q.sum(axis=1,keepdims=True)
    report={'status':'ESTIMABLE','accuracy':float(np.mean(predicted==labels)),'macro_f1':float(f1.mean()),
        'log_loss':float(-np.log(q[np.arange(len(q)),labels]).mean()),'confusion':matrix.tolist(),
        'classes':[dict(index=i,precision=float(precision[i]),recall=float(recall[i]),f1=float(f1[i]),support=int(support[i])) for i in range(n_classes)],
        'scoring_dtype':'float64','raw_dtype':str(np.asarray(outputs).dtype),'class_order':list(range(n_classes))}
    if n_classes==10:
        distraction=1-p[:,0]; truth=labels!=0; decision=distraction>=.5
        report['distraction_diagnostic']={'threshold':.5,'accuracy':float(np.mean(truth==decision)),
            'c0_false_positive_proxy':float(decision[~truth].mean()) if (~truth).any() else None,
            'interpretation':'ADDITIONAL_OFFLINE_DIAGNOSTIC_NOT_LIVE_RISK'}
    return report


def conditioned_metrics(labels,outputs,n_classes,*,logits=False):
    if len(labels)==0 or set(labels)!=set(range(n_classes)):
        return {'status':'NOT_ESTIMABLE','reason':'Empty common valid set or missing fixed class','support':len(labels)}
    return classification_metrics(labels,outputs,n_classes,logits=logits)


def stability_metrics(clean,stress):
    clean=np.asarray(clean,dtype=np.float64);stress=np.asarray(stress,dtype=np.float64)
    if clean.shape!=stress.shape:raise ValueError('Unpaired stability inputs')
    clean=probabilities(clean,clean.shape[1],logits=False);stress=probabilities(stress,stress.shape[1],logits=False)
    delta=stress-clean
    clean_counts=np.bincount(clean.argmax(axis=1),minlength=clean.shape[1])
    stress_counts=np.bincount(stress.argmax(axis=1),minlength=clean.shape[1])
    distribution_delta=stress_counts-clean_counts
    return {'label_validity':'LABEL_VALIDITY_UNVERIFIED','f1_eligible':False,'human_validated':False,
        'flip_rate':float(np.mean(clean.argmax(axis=1)!=stress.argmax(axis=1))),
        'mean_l1':float(np.abs(delta).sum(axis=1).mean()),'mean_delta_probability':delta.mean(axis=0).tolist(),
        'clean_prediction_distribution':clean_counts.tolist(),
        'stress_prediction_distribution':stress_counts.tolist(),
        'clean_prediction_distribution_rate':(clean_counts/len(clean)).tolist(),
        'stress_prediction_distribution_rate':(stress_counts/len(clean)).tolist(),
        'prediction_distribution_delta_count':distribution_delta.tolist(),
        'prediction_distribution_delta_rate':(distribution_delta/len(clean)).tolist(),'support':len(clean)}


class BudgetExceeded(RuntimeError):pass


class BudgetSupervisor:
    """Single-worker wall budget with observed RSS (process tree) and disk guards.

    The 20 ms sampling is observable enforcement, not a kernel memory limit.
    Human waiting must happen between run calls and is excluded from machine time.
    """
    def __init__(self,path,*,total_seconds=14400,stage_caps=None,min_free_bytes=20*GIB,
                 min_available_ram=8*GIB,disk_cap_bytes=20*GIB,output_root=None):
        self.started=time.monotonic();self.human_wait_seconds=0.;self.last_worker_end=self.started
        self.path=Path(path);self.path.mkdir(parents=True,exist_ok=False)
        self.output_root=Path(output_root) if output_root is not None else self.path
        self.total_cap=total_seconds;self.stage_caps=stage_caps or STAGE_CAPS.copy()
        self.disk_cap=disk_cap_bytes;self.total_used=0.;self.stage_used={};self.model_used={};self.stopped=False
        self.minimum_free=min_free_bytes;self.minimum_ram=min_available_ram;self.workers=[]
        if psutil.disk_usage(self.path).free<min_free_bytes or psutil.virtual_memory().available<min_available_ram:
            self.stopped=True;self._save('BLOCKED','INSUFFICIENT_STARTUP_RESOURCES');raise BudgetExceeded('INSUFFICIENT_STARTUP_RESOURCES')
        self._save('READY',None)

    def _save(self,status,reason):
        self.total_used=time.monotonic()-self.started-self.human_wait_seconds
        atomic_json(self.path/'budget_state.json',dict(status=status,reason=reason,total_used_seconds=self.total_used,
            stage_used_seconds=self.stage_used,model_used_seconds=self.model_used,workers=self.workers,
            observed_sampling_seconds=.02,total_cap_seconds=self.total_cap,stage_caps=self.stage_caps))

    @contextlib.contextmanager
    def human_wait(self):
        """Explicit human-only pause; never wrap machine work in this context."""
        started=time.monotonic()
        try:yield
        finally:
            self.human_wait_seconds+=time.monotonic()-started
            self.last_worker_end=time.monotonic()

    def _disk_size(self):
        total=0
        for root,dirs,files in os.walk(self.output_root,followlinks=False):
            for name in dirs+files:
                item=Path(root)/name
                if item.is_symlink():raise BudgetExceeded('DISK_SYMLINK_REFUSED')
            for name in files:
                try:total+=(Path(root)/name).stat().st_size
                except FileNotFoundError:pass
        return total

    @staticmethod
    def _terminate(process):
        if process.poll() is not None:return
        with contextlib.suppress(ProcessLookupError):os.killpg(process.pid,signal.SIGTERM)
        try:process.wait(timeout=.3)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError):os.killpg(process.pid,signal.SIGKILL)
            process.wait(timeout=2)

    def run(self,command,*,stage,model,model_cap_seconds,worker_cap_seconds,rss_cap_bytes,cwd=None):
        if self.stopped:raise ValueError('Budget supervisor stopped; no automatic resume/rerun')
        if stage not in self.stage_caps:raise ValueError('Unregistered budget stage')
        key=f'{stage}:{model}';index=len(self.workers)
        parent_overhead=time.monotonic()-self.last_worker_end
        self.stage_used[stage]=self.stage_used.get(stage,0)+parent_overhead
        self.model_used[key]=self.model_used.get(key,0)+parent_overhead
        self.total_used=time.monotonic()-self.started-self.human_wait_seconds
        if psutil.disk_usage(self.output_root).free<self.minimum_free or psutil.virtual_memory().available<self.minimum_ram:
            self.stopped=True;self._save('BLOCKED','INSUFFICIENT_STARTUP_RESOURCES');raise BudgetExceeded('INSUFFICIENT_STARTUP_RESOURCES')
        allowed=min(worker_cap_seconds,self.total_cap-self.total_used,
                    self.stage_caps[stage]-self.stage_used.get(stage,0),model_cap_seconds-self.model_used.get(key,0))
        if allowed<=0:
            self.stopped=True;self._save('PARTIAL','TIME_BUDGET_EXCEEDED');raise BudgetExceeded('TIME_BUDGET_EXCEEDED')
        env=os.environ.copy()
        env['P4_BUDGET_WORKER']='1'
        env.update({k:'2' for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS')})
        started=time.monotonic();samples=[];process=None;reason=None;returncode=None
        stdout_path=self.path/f'{index:03d}_{stage}.stdout.log';stderr_path=self.path/f'{index:03d}_{stage}.stderr.log'
        try:
            with stdout_path.open('xb') as stdout,stderr_path.open('xb') as stderr:
                process=subprocess.Popen(command,cwd=cwd or self.path,env=env,start_new_session=True,stdout=stdout,stderr=stderr)
                worker=psutil.Process(process.pid)
                while True:
                    elapsed=time.monotonic()-started
                    try:
                        tree=[worker]+worker.children(recursive=True)
                        rss=sum(p.memory_info().rss for p in tree if p.is_running())
                    except psutil.NoSuchProcess:rss=0
                    except (psutil.AccessDenied,PermissionError) as error:
                        reason='RSS_OBSERVATION_BLOCKED'
                        raise BudgetExceeded(reason) from error
                    samples.append({'elapsed_seconds':elapsed,'rss_bytes':rss})
                    if elapsed>=allowed:reason='TIME_BUDGET_EXCEEDED'
                    elif rss>=rss_cap_bytes:reason='RSS_BUDGET_EXCEEDED'
                    elif self._disk_size()>=self.disk_cap:reason='DISK_BUDGET_EXCEEDED'
                    elif psutil.disk_usage(self.path).free<self.minimum_free:reason='DISK_FREE_EXCEEDED'
                    if reason:raise BudgetExceeded(reason)
                    if process.poll() is not None:
                        returncode=process.returncode
                        if returncode:raise RuntimeError(f'worker failed with exit code {returncode}')
                        break
                    time.sleep(.02)
        except BaseException as error:
            if process is not None:self._terminate(process)
            self.stopped=True
            reason=reason or ('WORKER_FAILED' if isinstance(error,Exception) else 'INTERRUPTED')
            raise
        finally:
            elapsed=time.monotonic()-started;self.last_worker_end=time.monotonic()
            self.stage_used[stage]=self.stage_used.get(stage,0)+elapsed;self.model_used[key]=self.model_used.get(key,0)+elapsed
            record={'index':index,'stage':stage,'model':model,'elapsed_seconds':elapsed,'allowed_seconds':allowed,
                'returncode':returncode if process is None else process.returncode,'reason':reason,
                'sampled_peak_rss_bytes':max((s['rss_bytes'] for s in samples),default=0),'samples':samples,
                'maximum_sampling_gap_seconds':max((b['elapsed_seconds']-a['elapsed_seconds'] for a,b in zip(samples,samples[1:])),default=0),
                'parent_overhead_seconds':parent_overhead,
                'stdout':stdout_path.name,'stderr':stderr_path.name}
            self.workers.append(record)
            self._save('PARTIAL' if reason and 'BUDGET' in reason else ('FAILED' if reason else 'READY'),reason)
        return record


def source_manifest(paths):
    records=[{'path':str(Path(p).resolve()),'sha256':sha256_file(p)} for p in sorted(paths,key=str)]
    return {'files':records,'source_sha256':hashlib.sha256(canonical_json(records)).hexdigest()}


def driver_metrics(labels,outputs,drivers,n_classes,*,logits=False):
    labels=np.asarray(labels);outputs=np.asarray(outputs);drivers=np.asarray(drivers)
    if len(labels)!=len(drivers):raise ValueError('Driver provenance must match sources')
    names=sorted(set(drivers.tolist()));per_driver={};leave={}
    for driver in names:
        mask=drivers==driver
        per_driver[driver]=classification_metrics(labels[mask],outputs[mask],n_classes,logits=logits)
        if (~mask).any():leave[driver]=classification_metrics(labels[~mask],outputs[~mask],n_classes,logits=logits)
    scores=[v['macro_f1'] for v in leave.values()]
    return {'pooled':classification_metrics(labels,outputs,n_classes,logits=logits),'drivers':per_driver,
        'leave_one_driver_out':leave,'leave_one_driver_out_macro_f1_range':[min(scores),max(scores)] if scores else None,
        'independent_driver_count':len(names),'inferential_status':'DESCRIPTIVE_ONLY_NO_FRAME_BOOTSTRAP_OR_P_VALUES'}
