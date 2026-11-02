"""Explicitly gated P4-B formal execution; P4-A never creates authorization.

Usage: python -m ml.experiments.run_p4 formal --protocol ... --run-id ...
  --approval <separately-authorized.json> --execution-spec <paths.json>

Use `bindings` to print reviewable protocol/source hashes without observations.
Formal workers are private subprocess entrypoints and recheck all bindings.
"""
from __future__ import annotations
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
import time

import numpy as np

from ml.experiments.p4_core import (FROZEN_IDENTITIES, STAGE_CAPS, GIB, BudgetSupervisor,
    PredictionCache, P4Authorization, authorize_p4b, sha256_file, array_sha256,
    canonical_json, atomic_json, source_manifest, verify_identity, probabilities,
    classification_metrics, stability_metrics, driver_metrics, conditioned_metrics)

ROOT=Path(__file__).resolve().parents[2]
SOURCES=[ROOT/'ml/experiments'/name for name in ('p4_core.py','run_p4.py','p4_data.py','p4_preflight.py','e1_generators.py','comparator_common.py')]
NO_MANUAL_QC={'status':'REMOVED_FROM_SCOPE','pilot':'REMOVED_FROM_SCOPE',
    'formal':'REMOVED_FROM_SCOPE','conditioned_f1':'REMOVED_FROM_SCOPE',
    'human_label_validity':'REMOVED_FROM_SCOPE','inter_rater_agreement':'REMOVED_FROM_SCOPE',
    'automatic_human_validation':False}
DATA_HASHES={'vision':'b4f8e90dec769bb419eaa490aea869668bed6484089cebe4d545c7667baa8ea4',
    'telemetry_test':'3bc3d47680a87359e1470fd8ffaf5ff330dc4419b37cc645e5736d51a91c96de',
    'telemetry_train':'97dd20ee9c0832ba33455e5c31088f9b4abb65c198bf988699a959d545d1e5b5',
    'telemetry_val':'1b02792df846b5af138bae59e4f4ccfa8fa421fbb4fd6d42fad88d57722774f1'}
MEAN=np.array([.485,.456,.406],dtype=np.float32)[:,None,None]
STD=np.array([.229,.224,.225],dtype=np.float32)[:,None,None]
EMPIRICAL=[[20.,118.43983141168286],[-.9496171195275332,5.308924454984119],
    [-.4797183579219134,1.664604719278922],[.0031284689143873,99.99436534101304],
    [-49.10802185530833,53.42680553362417],[20.001443716829353,99.99476210241048],
    [.0000013439689708905078,2.3359161325462123],[5.011333019940173,49.99892385921925]]


FROZEN_PREFLIGHT_SOURCE='ffdfa6637bace58c9818ade3b9a84e812a59d2f681543927b10403061301dece'
FROZEN_VALIDATION_TENSOR='07adb0f1a37281659c298bb79e5404fa770cdea511d5ccb99710966b48a8d42e'
FROZEN_ONNX={'MN-HPO42':'9ee60abb78007773cc625af80c313049c1970f63c1f041bed9f5b2539a384828',
 'RN-HPO42':'5e226722e0712824c78aa0976afa6fa5b8dc6100b147a7f523a09048171d8cf3',
 'MN-STABLE':'b3a42e8dd4553355b1fd7d9e7fe3d28e318decb894e76eb029489b7ff2e90bcf'}


class StreamingNpyWriter:
    """Seek/write one row with no resident mapping of the complete bank."""
    def __init__(self,path,shape,dtype):
        self.path=Path(path);self.shape=tuple(shape);self.dtype=np.dtype(dtype);self.written=set()
        with self.path.open('xb') as stream:
            np.lib.format.write_array_header_1_0(stream,{'descr':np.lib.format.dtype_to_descr(self.dtype),
                'fortran_order':False,'shape':self.shape})
            self.offset=stream.tell();stream.truncate(self.offset+int(np.prod(shape))*self.dtype.itemsize)
        self.row_bytes=int(np.prod(self.shape[1:]))*self.dtype.itemsize

    def write_row(self,index,values):
        if index in self.written:raise ValueError('duplicate bank row')
        array=np.asarray(values)
        if not 0<=index<self.shape[0] or array.shape!=self.shape[1:] or array.dtype!=self.dtype:
            raise ValueError('Invalid streaming bank row shape/dtype')
        with self.path.open('r+b') as stream:
            stream.seek(self.offset+index*self.row_bytes);stream.write(array.tobytes(order='C'))
        self.written.add(index)

    def finish(self):
        if self.written!=set(range(self.shape[0])):raise ValueError('Incomplete streaming bank')
        with self.path.open('r+b') as stream:stream.flush();os.fsync(stream.fileno())


def validate_protocol(protocol):
    expected_runtime={'provider':'CPUExecutionProvider','dtype':'float32','intra_op_threads':2,'inter_op_threads':1,
        'execution_mode':'ORT_SEQUENTIAL','graph_optimization':'ORT_ENABLE_ALL','allow_spinning':False,
        'active_workers':1,'evaluation_batch_size':32,'vision_per_condition_tail':9,'runtime_batch_size':1,'paired_rounds':6,
        'warmups_per_worker':50,'latency_requests_per_worker':100,'throughput_requests_per_worker':100,'percentile_method':'linear'}
    if (protocol.get('protocol')!='P4-PROTOCOL-v2' or protocol.get('seed')!=42
            or protocol.get('amendment')!='USER_APPROVED_MANUAL_QC_REMOVAL'):
        raise ValueError('Frozen protocol identifier/seed mismatch')
    if protocol.get('formal_execution_authorized') is not False:
        raise ValueError('Frozen protocol cannot create its own P4-B authorization')
    if canonical_json(protocol.get('frozen_identities'))!=canonical_json(FROZEN_IDENTITIES):raise ValueError('Frozen protocol identities mismatch')
    if protocol.get('source_sha256')!=DATA_HASHES:raise ValueError('Frozen protocol data hash mismatch')
    if any(protocol.get('runtime',{}).get(k)!=v for k,v in expected_runtime.items()):raise ValueError('Frozen protocol runtime mismatch')
    budgets=protocol.get('budgets',{})
    if budgets.get('formal_total_machine_seconds')!=14400 or budgets.get('stage_caps_seconds')!=STAGE_CAPS:
        raise ValueError('Frozen protocol budget mismatch')
    expected_resources={'runtime_worker_seconds':90,'export_worker_seconds':120,'parity_worker_seconds':120,
        'minimum_free_disk_bytes':20*GIB,'minimum_available_ram_bytes':8*GIB,'run_output_cap_bytes':20*GIB,
        'evaluation_rss_cap_bytes':8*GIB,'runtime_rss_cap_bytes':4*GIB,'rss_sampling_seconds':.02,
        'automatic_resume':False,'automatic_retry':False}
    if any(budgets.get(k)!=v for k,v in expected_resources.items()):raise ValueError('Frozen protocol resource caps mismatch')
    expected_scope={'vision_sources':3657,'vision_conditions':19,'vision_shared_inputs':69483,'vision_identities':3,
        'vision_predictions':208449,'telemetry_sources':4500,'telemetry_conditions':10,'telemetry_shared_inputs':45000,
        'telemetry_identities':4,'telemetry_predictions':180000,'total_predictions':388449}
    if protocol.get('scope')!=expected_scope:raise ValueError('Frozen protocol scope/count mismatch')
    if protocol.get('telemetry',{}).get('bounds_policy')!='REPORT_ONLY_NO_CLIP' or protocol['telemetry'].get('perturbed_f1_eligible') is not False:
        raise ValueError('Frozen protocol telemetry label/bounds mismatch')
    if budgets.get('per_identity_seconds')!={'vision_clean':400,'vision_stress':2400,'telemetry':300,'runtime':900}:
        raise ValueError('Frozen protocol model budget mismatch')
    if protocol.get('qc')!=NO_MANUAL_QC:raise ValueError('Frozen protocol manual QC removal mismatch')
    if protocol.get('preflight',{}).get('frozen_onnx_sha256')!=FROZEN_ONNX or protocol['preflight'].get('executed_source_sha256')!=FROZEN_PREFLIGHT_SOURCE:
        raise ValueError('Frozen protocol preflight identities mismatch')
    if (protocol['preflight'].get('export_execution_authorized') is not False
            or protocol['preflight'].get('existing_exports_status')!='REUSED_AND_VERIFIED'
            or protocol['preflight'].get('historical_export_count')!=2):
        raise ValueError('Frozen protocol reuses two historical exports without authorizing new exports')
    return protocol


def freeze_preflight_attestation(directory,output):
    """Hash existing val artifacts only; does not repeat exports or inference."""
    directory=Path(directory);output=Path(output);reject_symlink(directory);reject_symlink(output)
    paths=list(directory.glob('*.json'))
    paths += list((directory/'validation').glob('*'))
    paths += list((directory/'runtime_benchmark').glob('*/*'))
    paths += [directory/'implementation/p4_preflight_executed.py']
    files={str(p.relative_to(directory)):sha256_file(p) for p in sorted(set(paths)) if p.is_file() and p!=output}
    expected_source=sha256_file(directory/'implementation/p4_preflight_executed.py')
    if expected_source!=FROZEN_PREFLIGHT_SOURCE:raise ValueError('Executed preflight source snapshot mismatch')
    for identity in FROZEN_ONNX:
        report=read_json(directory/f'parity_{identity}.json')
        if report.get('status')!='COMPLETED' or report.get('source_sha256')!=expected_source or report.get('result',{}).get('status')!='PASS':raise ValueError('Original parity report is not verified PASS')
    attestation={'schema':1,'scope':'P4A_EXISTING_VALIDATION_ARTIFACT_HASH_ATTESTATION_NO_RERUN',
        'executed_source_sha256':expected_source,'validation_tensor_sha256':FROZEN_VALIDATION_TENSOR,
        'onnx_sha256':FROZEN_ONNX,'files':files}
    if output.exists():raise FileExistsError(output)
    atomic_json(output,attestation)
    return attestation


def formal_provenance():
    import importlib.metadata,platform,psutil
    from ml.experiments import comparator_common as common,p4_preflight
    git=common.git_snapshot()
    if git['branch']!='fyp2/ml-training' or git['staged_paths']:raise ValueError('Formal branch/staging protection failed')
    battery=psutil.sensors_battery()
    return {'git':git,'protected_hashes':p4_preflight.protected_snapshot(),
        'versions':{name:importlib.metadata.version(name) for name in ('numpy','Pillow','torch','torchvision','onnx','onnxruntime','scikit-learn','xgboost','psutil')},
        'hardware':{'platform':platform.platform(),'machine':platform.machine(),'cpu_count':psutil.cpu_count(),
            'physical_memory_bytes':psutil.virtual_memory().total,'battery_power_plugged':None if battery is None else battery.power_plugged},
        'cpu_settings':{'intra':2,'inter':1,'provider':'CPUExecutionProvider','temperature_state':None}}


def read_json(path):return json.loads(Path(path).read_text())


def reject_symlink(path):
    if any(p.is_symlink() for p in [Path(path),*Path(path).parents]):raise ValueError('Symlink paths refused')


def binding_for(protocol,run_id):
    return dict(protocol_sha256=sha256_file(protocol),run_id=run_id,source_sha256=source_manifest(SOURCES)['source_sha256'])


def normalize_rgb(values):
    values=np.asarray(values)
    if values.dtype!=np.uint8 or values.ndim!=4 or values.shape[1:]!=(224,224,3):raise ValueError('Invalid shared RGB bank')
    return np.ascontiguousarray((values.transpose(0,3,1,2).astype(np.float32)/np.float32(255)-MEAN)/STD,dtype=np.float32)


def condition_name(row):
    family=row.get('condition',row.get('domain'))
    return family if family in ('clean','D0') else f"{family}:{row['severity']}"


def verify_preflight(spec):
    """Consume actual P4-A artifacts; recheck source, bank, ONNX and parity."""
    from ml.experiments import p4_preflight as preflight, p4_data
    directory=Path(spec['preflight_dir']);reject_symlink(directory)
    attestation_path=Path(spec['preflight_attestation'])
    protocol=read_json(spec['protocol_path'])
    if sha256_file(attestation_path)!=protocol['preflight']['attestation_sha256']:
        raise ValueError('Preflight attestation binding mismatch')
    attestation=read_json(attestation_path)
    for relative,digest in attestation['files'].items():
        if sha256_file(directory/relative)!=digest:raise ValueError('Frozen preflight artifact changed')
    manifest=read_json(directory/'validation/validation_manifest.json')
    if manifest.get('tensor_sha256')!=FROZEN_VALIDATION_TENSOR:raise ValueError('Frozen validation bank identity mismatch')
    if manifest.get('test_images_opened')!=0 or manifest.get('test_telemetry_rows_read')!=0 or manifest.get('split')!='val':
        raise ValueError('Validation-only preflight provenance missing')
    bank=preflight.load_bank(directory/'validation')
    models={}
    for identity in ('MN-HPO42','RN-HPO42','MN-STABLE'):
        evidence=read_json(directory/f'parity_{identity}.json')
        if evidence.get('status')!='COMPLETED' or evidence.get('result',{}).get('status')!='PASS':
            raise ValueError('All three vision parity gates must PASS')
        if evidence.get('source_sha256')!=FROZEN_PREFLIGHT_SOURCE or sha256_file(Path(preflight.__file__))!=FROZEN_PREFLIGHT_SOURCE:
            raise ValueError('Preflight implementation changed after parity')
        if evidence['result'].get('tensor_sha256')!=manifest['tensor_sha256']:
            raise ValueError('Parity did not use the same validation bank')
        if evidence['result'].get('identity')!=identity:raise ValueError('Parity identity mismatch')
        path=preflight.onnx_path(identity,directory)
        if sha256_file(path)!=FROZEN_ONNX[identity]:raise ValueError('Frozen evaluated ONNX identity mismatch')
        if identity!='MN-STABLE':
            original=read_json(directory/f'export_{identity}.json')
            if original.get('status')!='COMPLETED' or original.get('result',{}).get('onnx_sha256')!=FROZEN_ONNX[identity]:
                raise ValueError('Original export report ONNX binding mismatch')
        models[identity]={'onnx_path':str(path),'onnx_sha256':sha256_file(path),
            'checkpoint_sha256':FROZEN_IDENTITIES[identity]['sha256'],'parity_status':'PASS'}
    projection=read_json(directory/'projection.json')
    if projection.get('status')!='COMPLETED' or not projection.get('result',{}).get('fits_proposed_caps'):
        raise ValueError('Measured preflight projection does not fit frozen formal caps')
    # Geometry is a hard pre-held-out gate. If the frozen discrete crop contains
    # fill, stop for protocol review rather than silently change its margin.
    p4_data.rotation_geometry_check()
    return {'status':'PASS','models':models,'validation_bank_path':str(directory/'validation/validation_bank.npy'),
        'validation_bank_sha256':manifest['bank_file_sha256'],'tensor_sha256':manifest['tensor_sha256']}


def create_ort(path):
    import onnxruntime as ort
    options=ort.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1
    options.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
    options.graph_optimization_level=ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    options.add_session_config_entry('session.intra_op.allow_spinning','0')
    options.add_session_config_entry('session.inter_op.allow_spinning','0')
    session=ort.InferenceSession(str(path),sess_options=options,providers=['CPUExecutionProvider'])
    if session.get_providers()!=['CPUExecutionProvider']:raise ValueError('CPU provider contract')
    inputs,outputs=session.get_inputs(),session.get_outputs()
    if len(inputs)!=1 or len(outputs)!=1 or inputs[0].name!='input' or outputs[0].name!='logits' or inputs[0].type!='tensor(float)' or outputs[0].type!='tensor(float)':raise ValueError('ORT I/O contract mismatch')
    if inputs[0].shape[1:]!=[3,224,224] or outputs[0].shape[1:]!=[10] or isinstance(inputs[0].shape[0],int):raise ValueError('ORT dynamic N shape mismatch')
    return session


def cache_open(spec):
    cache=PredictionCache.open_readonly(Path(spec['run_dir'])/'cache',spec['binding'],
        {k:v['sha256'] for k,v in FROZEN_IDENTITIES.items()})
    # Only an already gated worker in the currently active fresh supervisor may
    # append. Existing CLAIMED/FAILED IDs still cannot retry, and completed IDs
    # return cached outputs. The top-level runner never reopens an existing run.
    cache.connection.close()
    import sqlite3
    cache.connection=sqlite3.connect(cache.path/'predictions.sqlite3');cache.read_only=False
    cache.connection.execute('PRAGMA synchronous=FULL')
    return cache


def validate_vision_sources(vision):
    if len(vision)!=3657 or {r['driver_id'] for r in vision}!={'p012','p026','p035','p050'} or {r['class_id'] for r in vision}!={f'c{i}' for i in range(10)}:
        raise ValueError('Frozen vision test membership mismatch')


def validate_telemetry_sources(train,val,test):
    from ml.experiments.comparator_common import LABELS
    if len(train)!=21000 or len(val)!=4500 or len(test)!=4500 or [sum(r['source_label']==label for r in test) for label in LABELS]!=[1500]*3:
        raise ValueError('Frozen telemetry membership mismatch')


def prepare_inputs(spec,authorization):
    from PIL import Image
    from ml.experiments import p4_data
    from ml.experiments.comparator_common import FEATURES,LABELS
    run=Path(spec['run_dir']);out=run/'shared_inputs';out.mkdir(exist_ok=False)
    data=Path(spec['data_root'])/'eda_outputs/processed'
    vision=p4_data.read_vision_metadata(data/'vision/vision_metadata_with_split.csv',split='test',authorization=authorization,expected_sha256=DATA_HASHES['vision'])
    validate_vision_sources(vision)
    vision.sort(key=lambda r:r['source_id'])
    # uint8 bank: 19 * 3657 * 224 * 224 * 3 = 10.46 GB. No 69k PNGs
    # or whole FP32 bank is written. Hashes bind each source/parameter/tensor.
    maps={};manifest=[]
    for index,record in enumerate(vision):
        authorization.require_heldout();record['source_sha256']=sha256_file(record['image_path'])
        with Image.open(record['image_path']) as original:
            for image,row in p4_data.vision_bank(original,record,authorization=authorization):
                name=condition_name(row)
                if name not in maps:
                    maps[name]=StreamingNpyWriter(out/f'vision_{name.replace(":","_")}.npy',(len(vision),224,224,3),np.uint8)
                pixels=np.asarray(image,dtype=np.uint8);maps[name].write_row(index,pixels)
                row['input_sha256']=array_sha256(normalize_rgb(pixels[None])[0]);row['bank_row']=index
                row['source_sha256']=record['source_sha256'];row['source_path']=record['image_path']
                row['qc_status']='REMOVED_FROM_SCOPE';row['human_validated']=False
                row['label_validity']='SOURCE_LABEL' if name=='clean' else 'LABEL_VALIDITY_UNVERIFIED'
                row['f1_eligible']=name=='clean';manifest.append(row)
    for bank in maps.values():bank.finish()
    del maps
    if len(manifest)!=len(vision)*19:raise ValueError('Incomplete 19-condition shared vision inputs')
    atomic_json(out/'vision_sources.json',vision);atomic_json(out/'vision_variants.json',manifest)
    train=p4_data.read_telemetry_csv(data/'telemetry/telemetry_train.csv',split='train',expected_sha256=DATA_HASHES['telemetry_train'])
    val=p4_data.read_telemetry_csv(data/'telemetry/telemetry_val.csv',split='val',expected_sha256=DATA_HASHES['telemetry_val'])
    test=p4_data.read_telemetry_csv(data/'telemetry/telemetry_test.csv',split='test',authorization=authorization,expected_sha256=DATA_HASHES['telemetry_test'])
    validate_telemetry_sources(train,val,test)
    test.sort(key=lambda r:r['source_id'])
    statistics=read_json(ROOT/'ml/outputs/runs/w2_preparation_20261015/preparation_evidence.json')['train_only_statistics']
    p4_data.verify_train_statistics(statistics,expected_train_sha256=DATA_HASHES['telemetry_train'])
    # Recompute statistical verification from train only, with no fit/model call.
    x=np.asarray([r['features'] for r in train]);y=np.asarray([r['source_label'] for r in train])
    from ml.experiments.e1_generators import fit_train_statistics
    computed=fit_train_statistics(x,y,split='train',source_sha256=DATA_HASHES['telemetry_train'])
    from ml.experiments.run_e1_preparation import verify_reused_statistics
    verify_reused_statistics(statistics,computed)
    for identity in ('XGB-HPO42','RF-HPO42','LR-HPO42'):
        saved=read_json((ROOT/FROZEN_IDENTITIES[identity]['path']).parent/'train_statistics.json')
        if saved['train_csv_sha256']!=DATA_HASHES['telemetry_train'] or saved['feature_order']!=FEATURES:raise ValueError('Pipeline train provenance mismatch')
        p4_data.verify_train_statistics(statistics,expected_train_sha256=DATA_HASHES['telemetry_train'],pipeline_medians=[saved['median']])
    rows=list(p4_data.telemetry_bank([r['features'] for r in test],[r['source_label'] for r in test],
        [r['source_id'] for r in test],statistics,source_split='test',authorization=authorization,empirical_bounds=EMPIRICAL))
    if len(rows)!=len(test)*10:raise ValueError('Telemetry ten shared conditions per source required')
    for row in rows:
        row['qc_status']='REMOVED_FROM_SCOPE';row['human_validated']=False
    grouped={}
    for row in rows:grouped.setdefault(condition_name(row),[]).append(row)
    for condition,group in grouped.items():
        group.sort(key=lambda r:r['source_id'])
        np.save(out/f'telemetry_{condition.replace(":","_")}.npy',np.asarray([r['features'] for r in group],dtype=np.float64),allow_pickle=False)
    atomic_json(out/'telemetry_sources.json',test);atomic_json(out/'telemetry_variants.json',rows)
    cache=PredictionCache.create(run/'cache',spec['binding'],{k:v['sha256'] for k,v in FROZEN_IDENTITIES.items()});cache.close()
    bank_files=sorted(out.glob('*.npy'))
    atomic_json(out/'bank_manifest.json',{'banks':{p.name:sha256_file(p) for p in bank_files},
        'metadata':{p.name:sha256_file(p) for p in out.glob('*.json')},'vision_sources':len(vision),'vision_inputs':len(manifest),
        'telemetry_sources':len(test),'telemetry_inputs':len(rows)})


def load_telemetry_model(identity):
    from ml.experiments.comparator_common import LABELS,FEATURES
    path=verify_identity(identity,ROOT)
    if identity=='XGB-STABLE':
        import xgboost as xgb
        model=xgb.Booster(params={'nthread':2});model.load_model(path)
        if model.attr('best_iteration')!='90':raise ValueError('Stable XGB best_iteration mismatch')
        def predict(values):
            return model.predict(xgb.DMatrix(values,feature_names=FEATURES),iteration_range=(0,91))
        return predict
    import joblib
    pipeline=joblib.load(path)
    classes=list(pipeline.classes_)
    if classes==list(range(3)):order=[0,1,2]
    elif set(classes)==set(LABELS):order=[classes.index(label) for label in LABELS]
    else:raise ValueError('Telemetry frozen class mapping mismatch')
    from threadpoolctl import threadpool_limits
    def predict(values):
        # The shared median is already applied; the original frozen scaler and
        # classifier remain intact. No fit or estimator modification is allowed.
        with threadpool_limits(limits=2):return np.asarray(pipeline.predict_proba(values))[:,order]
    return predict


def evaluate_model(spec,identity,stage):
    run=Path(spec['run_dir']);shared=run/'shared_inputs';manifest=read_json(shared/'bank_manifest.json')
    modality=FROZEN_IDENTITIES[identity]['modality'];vision=modality=='vision'
    source_path=shared/f'{modality}_sources.json'
    if sha256_file(source_path)!=manifest['metadata'][source_path.name]:raise ValueError('Shared source metadata changed')
    sources=read_json(source_path);n_classes=10 if vision else 3
    from ml.experiments.comparator_common import LABELS
    labels=[int(r['class_id'][1:]) if vision else LABELS.index(r['source_label']) for r in sources]
    source_ids=[r['source_id'] for r in sources]
    verify_identity(identity,ROOT)
    if vision:
        evidence=verify_preflight(spec);session=create_ort(evidence['models'][identity]['onnx_path'])
        model=lambda values:session.run(['logits'],{'input':values})[0]
    else:model=load_telemetry_model(identity)
    cache=cache_open(spec)
    variant_path=shared/f'{modality}_variants.json'
    if sha256_file(variant_path)!=manifest['metadata'][variant_path.name]:raise ValueError('Shared variant metadata changed')
    variant_rows=read_json(variant_path)
    by_filename={f'{modality}_{condition_name(r).replace(":","_")}.npy':condition_name(r) for r in variant_rows}
    try:
        for filename,bank_sha in manifest['banks'].items():
            if not filename.startswith(modality+'_'):continue
            condition=filename[len(modality)+1:-4].replace('_',':',1) if not vision else filename[len(modality)+1:-4]
            # Condition identifiers are kept in metadata, avoiding interpretation
            # of family underscores as severity separators.
            condition=by_filename[filename]
            if stage=='vision_clean' and condition!='clean':continue
            if stage=='vision_stress' and condition=='clean':continue
            path=shared/filename
            if sha256_file(path)!=bank_sha:raise ValueError('Shared bank changed before model')
            values=np.load(path,mmap_mode='r',allow_pickle=False)
            if len(values)!=len(sources):raise ValueError('Shared bank source count mismatch')
            selected_variants=[r for r in variant_rows if condition_name(r)==condition]
            variants={r['source_id']:r for r in selected_variants}
            if len(selected_variants)!=len(sources) or set(variants)!=set(source_ids):raise ValueError('Variant source ID coverage mismatch')
            for start in range(0,len(values),32):
                batch=normalize_rgb(values[start:start+32]) if vision else np.ascontiguousarray(values[start:start+32])
                batch.flags.writeable=False;digest=array_sha256(batch)
                rows=[]
                for index in range(start,min(start+32,len(values))):
                    row=dict(source_id=source_ids[index],condition=condition,label=labels[index],input_sha256=array_sha256(batch[index-start]))
                    expected=variants[row['source_id']].get('input_sha256')
                    if expected and expected!=row['input_sha256']:raise ValueError('Tensor input hash mismatch')
                    rows.append(row)
                def predict():
                    output=np.asarray(model(batch))
                    if array_sha256(batch)!=digest:raise ValueError('Shared tensor mutated by model')
                    probabilities(output,n_classes,logits=vision)
                    if vision and output.dtype!=np.float32:raise ValueError('Vision logits must remain FP32')
                    return output
                cache.predict_once(identity,rows,predict)
            if sha256_file(path)!=bank_sha:raise ValueError('Shared bank changed after model')
    finally:cache.close()


def runtime_worker(spec,identity,round_index):
    evidence=verify_preflight(spec);run=Path(spec['run_dir']);out=run/'runtime_benchmark';out.mkdir(exist_ok=True)
    bank=np.load(evidence['validation_bank_path'],allow_pickle=False)
    inputs=[{'input':bank[i:i+1]} for i in range(100)]
    import psutil
    import onnxruntime  # import before the pre-session RSS baseline
    baseline=psutil.Process().memory_info().rss;load_start=time.perf_counter_ns()
    session=create_ort(evidence['models'][identity]['onnx_path']);load_ns=time.perf_counter_ns()-load_start
    loaded=psutil.Process().memory_info().rss
    for i in range(50):session.run(['logits'],inputs[i%100])
    latency=[]
    for request in inputs:
        tick=time.perf_counter_ns();output=session.run(['logits'],request);latency.append(time.perf_counter_ns()-tick)
        probabilities(output[0],10,logits=True)
    tick=time.perf_counter_ns()
    for request in inputs:session.run(['logits'],request)
    throughput_elapsed=time.perf_counter_ns()-tick
    atomic_json(out/f'{identity}_round{round_index}.json',{'identity':identity,'round':round_index,
        'warmup_count':50,'latency_nanoseconds':latency,'throughput_calls':100,'throughput_loop_nanoseconds':throughput_elapsed,
        'throughput_per_second':100e9/throughput_elapsed,'session_load_nanoseconds':load_ns,
        'rss_before_session_bytes':baseline,'rss_after_session_bytes':loaded,'lifecycle_ru_maxrss':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'scope':'CPU_ORT_SESSION_RUN_ONLY_NOT_CAPTURE_TO_RENDER','validation_bank_sha256':evidence['validation_bank_sha256']})


def qc_conditioned_report(predictions,qc_rows,*,identities=None):
    """Historical v1 software helper; inactive in all P4-PROTOCOL-v2 paths."""
    from ml.experiments.p4_qc import common_valid_sources
    identities=identities or [i for i,v in FROZEN_IDENTITIES.items() if v['modality']=='vision']
    families=sorted({r['condition'] for r in qc_rows if r['condition']!='clean'})
    result={'reviewer_count':1,'independent_external_reviewers':0,'inter_rater_agreement':None,
        'policy':'SINGLE_REVIEWER_R1','families':{},'coverage':{}}
    lookup={(r['identity'],r['source_id'],r['condition']):r for r in predictions}
    for family in families:
        common=common_valid_sources(qc_rows,family);entry={'common_source_count':len(common),'models':{}}
        source_rows={r['source_id']:r for r in qc_rows if r['source_id'] in common}
        support={}
        for row in source_rows.values():
            group=support.setdefault(row['driver_id'],{});group[row['class_id']]=group.get(row['class_id'],0)+1
        entry['driver_class_support']=support
        result['coverage'][family]={str(severity):{status:sum(r['condition']==family and r['severity']==severity and r['status']==status for r in qc_rows) for status in ('VALID','INVALID','UNCERTAIN','UNREVIEWED')} for severity in range(3)}
        for identity in identities:
            scores={}
            for condition in ['clean']+[f'{family}:{severity}' for severity in range(3)]:
                rows=[lookup[(identity,sid,condition)] for sid in common]
                scores[condition]=conditioned_metrics([r['label'] for r in rows],[r['output'] for r in rows],10,logits=True)
                if rows:
                    descriptive=classification_metrics([r['label'] for r in rows],[r['output'] for r in rows],10,logits=True)
                    scores[condition]['supported_class_diagnostics']=[c for c in descriptive['classes'] if c['support']>0]
                    scores[condition]['driver_descriptive']=driver_metrics([r['label'] for r in rows],[r['output'] for r in rows],
                        [source_rows[r['source_id']]['driver_id'] for r in rows],10,logits=True)
            if scores['clean']['status']=='ESTIMABLE':
                for condition in scores:
                    if condition!='clean':scores[condition]['paired_macro_f1_delta']=scores[condition]['macro_f1']-scores['clean']['macro_f1']
            entry['models'][identity]=scores
        result['families'][family]=entry
    return result


def runtime_summary(rounds,workers,identity):
    relevant=[w for w in workers if w['stage']=='runtime' and w['model']==identity]
    if len(rounds)!=6 or len(relevant)!=6:raise ValueError('Six paired runtime rounds and supervisor samples required')
    enriched=[]
    for record,worker in zip(rounds,relevant):
        values=record['latency_nanoseconds'];samples=worker['samples']
        enriched.append(dict(record,p50_ms=float(np.percentile(values,50,method='linear')/1e6),
            p95_ms=float(np.percentile(values,95,method='linear')/1e6),
            sampled_peak_rss_bytes=worker['sampled_peak_rss_bytes'],
            sampled_peak_minus_baseline_bytes=worker['sampled_peak_rss_bytes']-record['rss_before_session_bytes'],
            maximum_sampling_gap_seconds=max((b['elapsed_seconds']-a['elapsed_seconds'] for a,b in zip(samples,samples[1:])),default=0),
            sampled_rss=samples))
    ns=[v for r in enriched for v in r['latency_nanoseconds']]
    elapsed=sum(r['throughput_loop_nanoseconds'] for r in enriched)
    return {'rounds':enriched,'p50_ms':float(np.percentile(ns,50,method='linear')/1e6),
        'p95_ms':float(np.percentile(ns,95,method='linear')/1e6),
        'round_p50_range_ms':[min(r['p50_ms'] for r in enriched),max(r['p50_ms'] for r in enriched)],
        'round_p95_range_ms':[min(r['p95_ms'] for r in enriched),max(r['p95_ms'] for r in enriched)],
        'pooled_throughput_per_second':sum(r['throughput_calls'] for r in enriched)*1e9/elapsed,
        'target_rss_sampling_seconds':.02,'rss_limitation':'Observed samples may miss instantaneous peaks; delta is not exclusive model memory.',
        'ru_maxrss_scope':'Whole worker lifecycle; macOS bytes, not model exclusive memory.'}


def telemetry_metadata_summary(rows):
    """Summarize shared input metadata once, without predictions or label F1.

    Missing rates use the actual condition's row count (cell rates use N*8).
    None excesses remain unknown/missing, rather than becoming passing zeros.
    The four stored stages preserve violations that an imputer later removes.
    """
    from collections import Counter
    from ml.experiments.comparator_common import FEATURES
    stages=('source','pre_mask','observed','imputed')
    masks={'source':'source_missing_mask','injected':'injected_missing_mask','combined':'missing_mask'}
    grouped={};seen=set()
    for row in rows:
        condition=condition_name(row);key=(condition,row['source_id'])
        if key in seen:raise ValueError('Duplicate telemetry metadata source/condition')
        seen.add(key)
        if row.get('feature_order')!=FEATURES:raise ValueError('Telemetry metadata feature order mismatch')
        for field in masks.values():
            mask=row.get(field)
            if not isinstance(mask,list) or len(mask)!=8 or any(type(v) is not bool for v in mask):
                raise ValueError('Invalid telemetry metadata missing mask')
        if row['missing_mask']!=[a or b for a,b in zip(row['source_missing_mask'],row['injected_missing_mask'])]:
            raise ValueError('Telemetry metadata combined missing mask mismatch')
        if type(row.get('record_affected')) is not bool:raise ValueError('Invalid record missingness flag')
        for stage in stages:
            flags=row.get('bounds',{}).get(stage,[])
            if len(flags)!=8 or [f.get('feature') for f in flags]!=FEATURES:
                raise ValueError('Telemetry metadata bounds feature/stage mismatch')
        grouped.setdefault(condition,[]).append(row)

    def excess_summary(flags,side):
        known=[]
        for flag in flags:
            value=flag[side]
            if value is None:continue
            if type(value) not in (float,int) or not np.isfinite(value) or value<0:
                raise ValueError('Invalid telemetry metadata bounds excess')
            known.append(float(value))
        return {'count':sum(v>0 for v in known),'sum':sum(known) if known else None,
            'max':max(known) if known else None,'known_count':len(known),
            'unknown_or_missing_count':len(flags)-len(known)}

    result={'scope':'SHARED_TELEMETRY_INPUT_METADATA_ONLY_NO_FORWARD',
        'feature_order':FEATURES.copy(),'condition_denominator':'Actual rows in each condition',
        'bounds_policy':'REPORT_ONLY_NO_CLIP','conditions':{}}
    for condition,group in sorted(grouped.items()):
        n=len(group);affected=sum(row['record_affected'] for row in group)
        summary={'record_count':n,'source_count':len({r['source_id'] for r in group}),
            'record_affected':{'count':affected,'rate':affected/n},
            'requested_record_missing_rates':sorted({r['requested_record_missing_rate'] for r in group}),
            'missingness':{},'bounds':{},
            'label_validity':'SOURCE_SYNTHETIC_LABEL' if condition=='D0' else 'LABEL_VALIDITY_UNVERIFIED',
            'f1_eligible':condition=='D0'}
        for name,field in masks.items():
            mask=np.asarray([r[field] for r in group],dtype=bool)
            count=int(mask.sum());record_count=int(mask.any(axis=1).sum())
            summary['missingness'][name]={'cell_count':count,'cell_rate':count/(n*8),
                'record_count':record_count,'record_rate':record_count/n,
                'features':{feature:{'count':int(mask[:,i].sum()),'rate':float(mask[:,i].mean())}
                    for i,feature in enumerate(FEATURES)}}
        for stage in stages:
            summary['bounds'][stage]={}
            for i,feature in enumerate(FEATURES):
                kinds={}
                for kind in ('domain','empirical'):
                    flags=[r['bounds'][stage][i][kind] for r in group]
                    counts=dict(Counter(flag['status'] for flag in flags))
                    kinds[kind]={'status_counts':counts,'status_rates':{status:count/n for status,count in counts.items()},
                        'lower_excess':excess_summary(flags,'lower_excess'),
                        'upper_excess':excess_summary(flags,'upper_excess')}
                summary['bounds'][stage][feature]=kinds
        result['conditions'][condition]=summary
    return result


def load_telemetry_metadata_summary(shared):
    shared=Path(shared);path=shared/'telemetry_variants.json'
    manifest=read_json(shared/'bank_manifest.json')
    if sha256_file(path)!=manifest['metadata'][path.name]:raise ValueError('Shared telemetry metadata changed')
    return telemetry_metadata_summary(read_json(path))


def require_complete_predictions(records):
    if len(records)!=388449:raise ValueError('Incomplete full paired prediction coverage')


def aggregate(spec):
    run=Path(spec['run_dir']);cache=PredictionCache.open_readonly(run/'cache',spec['binding'],{k:v['sha256'] for k,v in FROZEN_IDENTITIES.items()})
    try:records=cache.records()
    finally:cache.close()
    require_complete_predictions(records)
    report={'protocol':spec['binding'],'formal_prediction_count':len(records),'models':{},
        'telemetry_input_metadata':load_telemetry_metadata_summary(run/'shared_inputs'),
        'limitations':['Only four State Farm test drivers; descriptive comparisons, no frame bootstrap or p-values.',
        'Manual Recognizability QC is removed. Corruption label validity is unverified; stress outputs describe model stability, not preserved actions or human-validated robustness.',
        'Source-label corruption F1 is not computed. Any such descriptive sensitivity analysis would depend on explicit label-preservation assumptions.',
        'Telemetry sources are synthetic; driver/trip/generator independence unknown.',
        'Historical test split has been repeatedly evaluated; no directly test-driven parameter selection code was found.',
        'ResNet and XGB validation priorities remain frozen; no new selection or tuning.',
        'DMD remains BLOCKED; offline benchmark does not establish live performance.']}
    for identity,model in FROZEN_IDENTITIES.items():
        vision=model['modality']=='vision';n=10 if vision else 3;clean_name='clean' if vision else 'D0'
        own=[r for r in records if r['identity']==identity];clean={r['source_id']:r for r in own if r['condition']==clean_name}
        ordered=sorted(clean);labels=[clean[s]['label'] for s in ordered];output=np.asarray([clean[s]['output'] for s in ordered])
        entry={'clean':classification_metrics(labels,output,n,logits=vision),'stress':{}}
        entry['clean']['target_attained']=entry['clean']['macro_f1']>=(.8 if vision else .85)
        if vision:
            sources={r['source_id']:r for r in read_json(run/'shared_inputs/vision_sources.json')}
            entry['driver_metrics']=driver_metrics(labels,output,[sources[s]['driver_id'] for s in ordered],n,logits=True)
        for condition in sorted({r['condition'] for r in own}-{clean_name}):
            rows=sorted((r for r in own if r['condition']==condition),key=lambda r:r['source_id'])
            ids=[r['source_id'] for r in rows]
            if ids!=ordered:raise ValueError('Incomplete paired condition coverage')
            entry['stress'][condition]=stability_metrics(probabilities(output,n,logits=vision),probabilities([r['output'] for r in rows],n,logits=vision))
        report['models'][identity]=entry
    report['qc']=NO_MANUAL_QC.copy()
    report['paired_model_differences']={}
    for a,b in [('RN-HPO42','MN-HPO42'),('MN-HPO42','MN-STABLE'),('XGB-HPO42','XGB-STABLE'),('XGB-HPO42','RF-HPO42'),('XGB-HPO42','LR-HPO42')]:
        report['paired_model_differences'][f'{a} - {b}']={metric:report['models'][a]['clean'][metric]-report['models'][b]['clean'][metric] for metric in ('accuracy','macro_f1','log_loss')}
    runtime={}
    supervisor_workers=read_json(run/'budget_state.json')['workers']
    for identity in ('MN-HPO42','RN-HPO42'):
        rounds=[read_json(run/'runtime_benchmark'/f'{identity}_round{i}.json') for i in range(6)]
        runtime[identity]=runtime_summary(rounds,supervisor_workers,identity)
        runtime[identity]['checkpoint_bytes']=(ROOT/FROZEN_IDENTITIES[identity]['path']).stat().st_size
        runtime[identity]['onnx_bytes']=Path(verify_preflight(spec)['models'][identity]['onnx_path']).stat().st_size
    report['runtime']=runtime
    atomic_json(Path(spec.get('aggregation_output',run/'evaluation_metrics.json')),report)


def worker(spec_path,stage,identity=None,round_index=None):
    if os.environ.get('P4_BUDGET_WORKER')!='1':raise PermissionError('Private worker requires an active budget supervisor')
    spec=read_json(spec_path);validate_protocol(read_json(spec['protocol_path']));current=binding_for(spec['protocol_path'],spec['binding']['run_id'])
    if current!=spec['binding']:raise ValueError('Worker source/protocol changed')
    authorization=authorize_p4b(read_json(spec['approval_path']),**current)
    verify_preflight(spec)
    if stage=='shared_inputs':prepare_inputs(spec,authorization)
    elif stage in ('vision_clean','vision_stress','telemetry'):evaluate_model(spec,identity,stage)
    elif stage=='runtime':runtime_worker(spec,identity,round_index)
    elif stage=='aggregation':aggregate(spec)
    else:raise ValueError('Unknown worker stage')
    from threadpoolctl import threadpool_info
    provenance_dir=Path(spec['run_dir'])/'worker_provenance';provenance_dir.mkdir(exist_ok=True)
    suffix=f'{stage}_{identity or "all"}'+('' if round_index is None else f'_{round_index}')
    atomic_json(provenance_dir/f'{suffix}.json',{'threadpools':threadpool_info(),
        'environment_threads':{k:os.environ.get(k) for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS')},
        'runtime_provider':'CPUExecutionProvider','intra_op_threads':2,'inter_op_threads':1,
        'binding':current})


def formal(args):
    # This gate precedes data_root/execution-spec reads and output creation.
    if args.approval is None:raise ValueError('Separate explicit P4-B approval required')
    protocol_path=Path(args.protocol).resolve();protocol=read_json(protocol_path)
    validate_protocol(protocol)
    provenance=formal_provenance()
    binding=binding_for(protocol_path,args.run_id)
    authorize_p4b(read_json(args.approval),**binding)
    if args.execution_spec is None:raise ValueError('P4-B execution spec is required')
    spec=read_json(args.execution_spec)
    run=ROOT/'ml/outputs/runs'/args.run_id;reject_symlink(run)
    spec.update(binding=binding,run_dir=str(run),protocol_path=str(protocol_path),approval_path=str(Path(args.approval).resolve()))
    for obsolete in ('reviewers','qc_lock','qc_cue_checks'):spec.pop(obsolete,None)
    supervisor=BudgetSupervisor(run) # Resource gate precedes model loading/export/forward.
    atomic_json(run/'provenance_before.json',provenance)
    atomic_json(run/'execution_spec.json',spec);atomic_json(run/'source_manifest.json',source_manifest(SOURCES))
    atomic_json(run/'protocol.json',protocol)
    # Validation preflight is checked in a separately budgeted process before
    # any held-out preparation. New exports require separate export permission.
    def dispatch(stage,identity='all',cap=None,round_index=None):
        command=[sys.executable,'-B','-m','ml.experiments.run_p4','_worker','--execution-spec',str(run/'execution_spec.json'),'--stage',stage]
        if identity!='all':command+=['--identity',identity]
        if round_index is not None:command+=['--round-index',str(round_index)]
        worker_cap=90 if stage=='runtime' else cap
        return supervisor.run(command,stage=stage,model=identity,model_cap_seconds=cap,worker_cap_seconds=worker_cap,
            rss_cap_bytes=(4 if stage=='runtime' else 8)*GIB,cwd=ROOT)
    # Pure evidence/hash verification is bounded as part of preflight. Numeric
    # parity must already have run in authorized val-only preflight workers.
    command=[sys.executable,'-B','-m','ml.experiments.run_p4','_verify-preflight','--execution-spec',str(run/'execution_spec.json')]
    supervisor.run(command,stage='preflight',model='all',model_cap_seconds=600,worker_cap_seconds=600,rss_cap_bytes=8*GIB,cwd=ROOT)
    dispatch('shared_inputs',cap=1200)
    for stage,cap in [('vision_clean',400),('vision_stress',2400)]:
        for identity in ('MN-HPO42','RN-HPO42','MN-STABLE'):dispatch(stage,identity,cap)
    for identity in ('XGB-HPO42','RF-HPO42','LR-HPO42','XGB-STABLE'):dispatch('telemetry',identity,300)
    orders=[['MN-HPO42','RN-HPO42']]*3+[['RN-HPO42','MN-HPO42']]*3
    np.random.default_rng(42).shuffle(orders)
    atomic_json(run/'runtime_order.json',orders)
    for round_index,order in enumerate(orders):
        for identity in order:dispatch('runtime',identity,900,round_index)
    dispatch('aggregation',cap=1200)
    final_provenance=formal_provenance()
    if final_provenance['protected_hashes']!=provenance['protected_hashes']:raise ValueError('Protected hashes changed during formal run')
    atomic_json(run/'provenance_after.json',final_provenance)
    atomic_json(run/'completion.json',{'status':'MACHINE_EVALUATION_COMPLETED','qc_status':'REMOVED_FROM_SCOPE',
        'formal_prediction_count':388449,'binding':binding,'candidate_package':False,'deployment_eligible':False})
    return 0


def aggregate_cached(args):
    """Explicit cached aggregation; readonly predictions, no forward path."""
    original=read_json(args.execution_spec);binding=binding_for(original['protocol_path'],original['binding']['run_id'])
    if binding!=original['binding']:raise ValueError('Cached aggregation source/protocol mismatch')
    validate_protocol(read_json(original['protocol_path']));authorize_p4b(read_json(args.approval),**binding)
    provenance=formal_provenance();run=Path(original['run_dir'])
    if read_json(run/'completion.json').get('status')!='MACHINE_EVALUATION_COMPLETED':raise ValueError('Machine evaluation must be complete; aggregation cannot resume prediction')
    prior=read_json(run/'budget_state.json')
    remaining_total=14400-prior['total_used_seconds']
    remaining_stage=1200-prior['stage_used_seconds'].get('aggregation',0)
    if min(remaining_total,remaining_stage)<=0:raise ValueError('No frozen aggregation budget remains; separate budget approval required')
    directory=run/'cached_aggregation'
    supervisor=BudgetSupervisor(directory,total_seconds=remaining_total,stage_caps={'aggregation':remaining_stage},output_root=run)
    spec=dict(original,approval_path=str(Path(args.approval).resolve()),
        aggregation_output=str(directory/'evaluation_metrics.json'))
    for obsolete in ('reviewers','qc_lock','qc_cue_checks'):spec.pop(obsolete,None)
    atomic_json(directory/'execution_spec.json',spec);atomic_json(directory/'provenance_before.json',provenance)
    command=[sys.executable,'-B','-m','ml.experiments.run_p4','_worker','--execution-spec',str(directory/'execution_spec.json'),'--stage','aggregation']
    supervisor.run(command,stage='aggregation',model='all',model_cap_seconds=remaining_stage,
        worker_cap_seconds=remaining_stage,rss_cap_bytes=8*GIB,cwd=ROOT)
    atomic_json(directory/'provenance_after.json',formal_provenance())
    atomic_json(directory/'cumulative_budget.json',{'prior_machine_seconds':prior['total_used_seconds'],
        'additional_machine_seconds':supervisor.total_used,'combined_machine_seconds':prior['total_used_seconds']+supervisor.total_used,
        'prior_aggregation_seconds':prior['stage_used_seconds'].get('aggregation',0),
        'additional_aggregation_seconds':supervisor.stage_used.get('aggregation',0),'prediction_forward_count':0})
    return 0


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='mode',required=True)
    form=sub.add_parser('formal');form.add_argument('--protocol',required=True);form.add_argument('--run-id',required=True)
    form.add_argument('--approval');form.add_argument('--execution-spec')
    cached=sub.add_parser('aggregate-cached');cached.add_argument('--execution-spec',required=True);cached.add_argument('--approval',required=True)
    bind=sub.add_parser('bindings');bind.add_argument('--protocol',required=True);bind.add_argument('--run-id',required=True)
    private=sub.add_parser('_worker');private.add_argument('--execution-spec',required=True);private.add_argument('--stage',required=True)
    private.add_argument('--identity');private.add_argument('--round-index',type=int)
    freeze=sub.add_parser('attest-preflight');freeze.add_argument('--preflight-dir',required=True);freeze.add_argument('--output',required=True)
    verify=sub.add_parser('_verify-preflight');verify.add_argument('--execution-spec',required=True)
    args=parser.parse_args(argv)
    if args.mode=='formal':return formal(args)
    if args.mode=='aggregate-cached':return aggregate_cached(args)
    if args.mode=='attest-preflight':freeze_preflight_attestation(args.preflight_dir,args.output);return 0
    if args.mode=='bindings':print(json.dumps(binding_for(args.protocol,args.run_id),sort_keys=True));return 0
    if args.mode=='_verify-preflight':
        if os.environ.get('P4_BUDGET_WORKER')!='1':raise PermissionError('Private worker requires budget supervisor')
        spec=read_json(args.execution_spec);validate_protocol(read_json(spec['protocol_path']))
        authorize_p4b(read_json(spec['approval_path']),**binding_for(spec['protocol_path'],spec['binding']['run_id']));verify_preflight(spec);return 0
    worker(args.execution_spec,args.stage,args.identity,args.round_index);return 0


if __name__=='__main__':raise SystemExit(main())
