"""Single-reviewer R1 QC preparation and lock-before-reveal workflow.

R1 is the project developer. This supports a small validation pilot and records
single-reviewer bias; it provides no inter-rater agreement or invented ratings.
"""
import argparse
import csv
import hashlib
import html
import json
from pathlib import Path
import re
import time

import numpy as np
from PIL import Image

from ml.experiments import p4_data

CHOICES = [f'c{i}' for i in range(10)] + ['UNRECOGNIZABLE','AMBIGUOUS']
CLASS_GUIDE = {'c0':'normal driving','c1':'texting right','c2':'talking on phone right',
 'c3':'texting left','c4':'talking on phone left','c5':'operating radio',
 'c6':'drinking','c7':'reaching behind','c8':'hair and makeup','c9':'talking to passenger'}
LIMITATIONS = ['Single reviewer R1 is the project developer; developer/reviewer bias.',
 'Small validation pilot: 2 source images and 38 related cases, not 38 independent people.',
 'No second reviewer and no inter-rater agreement.',
 'No validity retention or human timing result exists before actual R1 judgments.']


def _digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def _json(path, value):
    with Path(path).open('x') as stream:
        json.dump(value,stream,indent=2,sort_keys=True,allow_nan=False)


def byte_attestation_path(kit):
    kit=Path(kit).absolute()
    return kit.with_name(kit.name+'_byte_attestation.json')


def _regular_path(path):
    path=Path(path).absolute()
    if any(p.is_symlink() for p in [path,*path.parents]):
        raise ValueError('QC byte binding refuses symlink paths')
    return path


def _file_sha(path):
    return hashlib.sha256(_regular_path(path).read_bytes()).hexdigest()


def _kit_sources(manifest, authorization):
    """Prove val membership before opening original/variant image bytes.

    Synthetic fixture source paths are never opened. Actual test observations
    require the separately issued P4-B token, including when a kit is malformed.
    """
    sources={}; metadata={}
    for row in manifest['restricted_cases']:
        split=row.get('source_split')
        p4_data._gate(split,authorization)
        if split=='synthetic':
            continue
        if split not in ('val','test'):
            raise ValueError('QC real image split must be val/test')
        from ml.experiments.comparator_common import DEFAULT_DATA
        meta_path=row.get('metadata_path') or str(DEFAULT_DATA/'eda_outputs/processed/vision/vision_metadata_with_split.csv')
        key=(meta_path,row.get('metadata_sha256'),split)
        if key not in metadata:
            metadata[key]={r['source_id']:r for r in p4_data.read_vision_metadata(
                meta_path,split=split,authorization=authorization,expected_sha256=key[1])}
        original=metadata[key].get(row['source_id'])
        if (not original or any(original.get(k)!=row.get(k) for k in ('class_id','driver_id'))
                or Path(original['image_path']).absolute()!=Path(row.get('source_path','')).absolute()):
            raise PermissionError('QC original source does not match proven split membership')
        expected=row.get('source_sha256')
        if not isinstance(expected,str) or not re.fullmatch('[0-9a-f]{64}',expected):
            raise ValueError('QC original source SHA256 is required')
        record={'source_id':row['source_id'],'path':str(_regular_path(row['source_path'])),
                'sha256':expected,'source_split':split,'metadata_sha256':key[1]}
        if row['source_id'] in sources and sources[row['source_id']]!=record:
            raise ValueError('Inconsistent QC original source binding')
        sources[row['source_id']]=record
    return sources


def _current_kit_bytes(kit, manifest, authorization):
    kit=_regular_path(kit)
    sources=_kit_sources(manifest,authorization)  # Before any image byte read.
    for source in sources.values():
        if _file_sha(source['path'])!=source['sha256']:
            raise ValueError('QC original source SHA256 mismatch')
    records=[]
    for row in sorted(manifest['restricted_cases'],key=lambda r:r['case_id']):
        case_id=row['case_id']
        if not re.fullmatch('q[0-9a-f]{24}',case_id):
            raise ValueError('Malformed anonymous QC case ID')
        path=_regular_path(kit/'images'/f'{case_id}.png')
        file_sha=_file_sha(path)
        with Image.open(path) as image:
            rgb=image.convert('RGB');pixel_sha=hashlib.sha256(rgb.tobytes()).hexdigest()
            shape=[rgb.height,rgb.width,3]
        if row.get('pixel_sha256') and row['pixel_sha256']!=pixel_sha:
            raise ValueError('QC PNG decoded pixel SHA256 mismatch')
        records.append({'case_id':case_id,'png':str(path.relative_to(kit)),
            'png_sha256':file_sha,'decoded_pixel_sha256':pixel_sha,'shape':shape,
            'source_id':row['source_id'],'source_sha256':row.get('source_sha256'),
            'input_sha256':row.get('input_sha256'),
            'parameter_provenance':'SOURCE_KEY_RECORDED' if 'params' in row else 'UNRECORDED'})
    if len({r['case_id'] for r in records})!=len(records):
        raise ValueError('Duplicate QC cases in byte binding')
    return records,[sources[sid] for sid in sorted(sources)]


def attest_kit(kit, *, authorization=None, scope='CURRENT_KIT_BYTE_FREEZE'):
    if scope not in ('CURRENT_KIT_BYTE_FREEZE','INITIAL_KIT_BYTE_FREEZE'):
        raise ValueError('Invalid QC byte freeze scope')
    kit=_regular_path(kit)
    destination=byte_attestation_path(kit)
    if destination.exists():
        raise FileExistsError('QC byte attestation is exclusive; existing freeze cannot be replaced')
    key_path=kit/'restricted/source_key.json'
    manifest=json.loads(key_path.read_text())
    payload={k:v for k,v in manifest.items() if k!='source_key_sha256'}
    if manifest.get('source_key_sha256')!=_digest(payload):
        raise ValueError('QC source key changed before byte freeze')
    cases,sources=_current_kit_bytes(kit,manifest,authorization)
    generator_paths=[Path(__file__),Path(p4_data.__file__),Path(p4_data.e1.__file__)]
    generators=[{'path':str(_regular_path(p)),'sha256':_file_sha(p)} for p in generator_paths]
    result={'version':'qc-byte-attestation-v1','scope':scope,'kit_path':str(kit),
        'source_key_file_sha256':_file_sha(key_path),'source_key_sha256':manifest['source_key_sha256'],
        'case_set_sha256':manifest['case_set_sha256'],'cases':cases,'sources':sources,
        'generator_sources':generators,'initial_generation_proof':scope=='INITIAL_KIT_BYTE_FREEZE',
        'parameter_policy':'Missing source-key parameters remain UNRECORDED; no reconstruction claimed',
        'authorization_binding':None if not any(r.get('source_split')=='test' for r in manifest['restricted_cases'])
            else {k:getattr(authorization,k) for k in ('protocol_sha256','source_sha256','run_id')}}
    result['attestation_sha256']=_digest(result)
    _json(destination,result)
    return result


def verify_byte_attestation(attestation, *, authorization=None):
    if not isinstance(attestation,dict):
        raise ValueError('QC byte attestation is required before lock/reveal/finalize')
    payload={k:v for k,v in attestation.items() if k!='attestation_sha256'}
    if attestation.get('attestation_sha256')!=_digest(payload):
        raise ValueError('QC byte attestation digest changed')
    kit=_regular_path(attestation['kit_path'])
    if json.loads(byte_attestation_path(kit).read_text())!=attestation:
        raise ValueError('QC external byte attestation changed')
    key_path=kit/'restricted/source_key.json'
    if _file_sha(key_path)!=attestation['source_key_file_sha256']:
        raise ValueError('QC source key file changed after byte freeze')
    manifest=json.loads(key_path.read_text())
    _kit_sources(manifest,authorization)  # Gate malformed/test kits before image I/O.
    binding=attestation.get('authorization_binding')
    if binding is not None and any(getattr(authorization,k,None)!=v for k,v in binding.items()):
        raise PermissionError('QC held-out byte attestation approval binding mismatch')
    for generator in attestation['generator_sources']:
        if _file_sha(generator['path'])!=generator['sha256']:
            raise ValueError('QC frozen generator source changed')
    cases,sources=_current_kit_bytes(kit,manifest,authorization)
    if cases!=attestation['cases'] or sources!=attestation['sources']:
        raise ValueError('QC PNG/pixel/original byte binding changed')
    return manifest


def load_byte_attestation(kit, *, authorization=None):
    value=json.loads(byte_attestation_path(kit).read_text())
    if Path(value['kit_path']).absolute()!=Path(kit).absolute():
        raise ValueError('QC byte attestation kit path mismatch')
    verify_byte_attestation(value,authorization=authorization)
    return value


def authorization_from_execution_spec(path, kit):
    """Validate an existing formal run binding before opening any kit images.

    The JSON files record separately granted human authorization. This command
    neither creates approval nor enables the P4-A protocol's authorization flag.
    """
    from ml.experiments import run_p4
    from ml.experiments.p4_core import authorize_p4b
    spec=json.loads(_regular_path(path).read_text())
    protocol_path=_regular_path(spec['protocol_path'])
    run_p4.validate_protocol(json.loads(protocol_path.read_text()))
    frozen=spec['binding']
    current=run_p4.binding_for(protocol_path,frozen['run_id'])
    if current!=frozen:
        raise ValueError('QC execution protocol/source/run binding mismatch')
    run=_regular_path(spec['run_dir'])
    if run.name!=current['run_id'] or _regular_path(kit)!=run/'qc_review_kit':
        raise PermissionError('QC kit is not bound to the approved formal run')
    approval=json.loads(_regular_path(spec['approval_path']).read_text())
    authorization=authorize_p4b(approval,**current)
    if approval.get('single_reviewer_amendment_approved') is not True:
        raise PermissionError('QC formal single-reviewer amendment approval is required')
    return authorization


def select_sources(records, cap_per_stratum=5, seed=42):
    if not 0 < cap_per_stratum <= 5:
        raise ValueError('QC per driver/class cap must be at most 5')
    groups = {}
    if len({r['source_id'] for r in records}) != len(records):
        raise ValueError('Duplicate QC source IDs')
    for row in records:
        groups.setdefault((row['driver_id'],row['class_id']),[]).append(row)
    selected = []
    for key in sorted(groups):
        selected.extend(sorted(groups[key],key=lambda r:(hashlib.sha256(
            f"{seed}|qc-source|{r['source_id']}".encode()).digest(),r['source_id']))[:cap_per_stratum])
    return selected


def build_review_kit(cases, out_dir, *, reviewer='R1', seed=42, authorization=None):
    if reviewer != 'R1':
        raise ValueError('Approved QC reviewer is R1, the project developer')
    directory = Path(out_dir)
    if any(p.is_symlink() for p in [directory,*directory.parents]):
        raise ValueError('QC output must not use symlinks')
    directory.mkdir(parents=True,exist_ok=False)
    (directory/'images').mkdir()
    (directory/'restricted').mkdir(mode=0o700)
    restricted, blind = [], []
    seen = set()
    for image,row in cases:
        p4_data._gate(row.get('source_split'),authorization)
        pixel_sha=hashlib.sha256(image.convert('RGB').tobytes()).hexdigest()
        if row.get('pixel_sha256') and row['pixel_sha256']!=pixel_sha:
            raise ValueError('QC supplied pixel SHA256 differs from image pixels')
        if row['variant_id'] in seen:
            raise ValueError('Duplicate QC variant')
        seen.add(row['variant_id'])
        case_id = 'q'+hashlib.sha256(f"{seed}|qc-case|{row['variant_id']}".encode()).hexdigest()[:24]
        filename = f'images/{case_id}.png'
        image.convert('RGB').save(directory/filename)
        blind.append({'case_id':case_id,'image':filename})
        source = {k:row[k] for k in ('source_id','driver_id','class_id','source_split',
                   'condition','severity','source_path','source_sha256','metadata_sha256',
                   'metadata_path','params','pixel_sha256','input_sha256','shared_tensor_sha256') if k in row}
        source['pixel_sha256']=pixel_sha
        restricted.append(dict(source,case_id=case_id,status='UNREVIEWED',variant_id=row['variant_id']))
    blind.sort(key=lambda r:hashlib.sha256(f"{seed}|qc-shuffle|{r['case_id']}".encode()).digest())
    manifest = {'reviewer':reviewer,'reviewer_role':'project developer','reviewer_count':1,
        'inter_rater_agreement':None,'seed':seed,'human_ratings_count':0,
        'limitations':LIMITATIONS,'restricted_cases':restricted,
        'case_set_sha256':_digest(sorted(r['case_id'] for r in restricted)),
        'class_guide':CLASS_GUIDE,'status':'PREPARED_HUMAN_REVIEW_PENDING'}
    manifest['source_key_sha256']=_digest(manifest)
    _json(directory/'blind_cases.json',blind)
    _json(directory/'restricted/source_key.json',manifest)
    with (directory/'R1.csv').open('x',newline='') as stream:
        writer=csv.writer(stream)
        writer.writerow(['case_id','reviewer','selected_class','status','reason','duration_seconds','timestamp'])
        writer.writerows([[r['case_id'],'R1','','','','',''] for r in blind])
    payload=json.dumps(blind).replace('<','\\u003c')
    guide='; '.join(f'{k}: {v}' for k,v in CLASS_GUIDE.items())
    page='''<!doctype html><html lang="en"><meta charset="utf-8"><title>R1 blind QC</title>
<style>body{font:18px system-ui;max-width:820px;margin:35px auto;background:#f4f5f7;color:#18222c}img{width:448px;max-width:100%;image-rendering:auto}label{display:block;margin:12px 0}textarea{width:95%;height:75px}button,select{font:inherit;padding:10px}small{display:block;color:#566}</style>
<h1>R1 blind recognizability review</h1><p>Review the visible action independently. Source references, labels and model outputs remain hidden until all judgments are exported and locked. Clean variants are anonymous cases within the shuffle.</p>
<small>Single reviewer: project developer. No inter-rater agreement. Validation pilot cases share only two sources; results do not establish population validity. Per-case duration is elapsed wall time while displayed, including interruptions. Drafts save in this browser on this device.</small>
<details><summary>Frozen class action guide</summary><p>GUIDE</p></details>
<p id="progress"></p><img id="picture" alt="anonymous action case"><p id="case"></p>
<label>Visible action <select id="choice"><option value="">Choose</option>OPTIONS</select></label>
<label>Recognizability <select id="status"><option value="">Choose</option><option>VALID</option><option>INVALID</option><option>UNCERTAIN</option></select></label>
<small>VALID here means visually recognizable, pending the later source cue check. Use UNCERTAIN for ambiguity and INVALID when action evidence is clearly absent.</small>
<label>Visible action evidence / reason <textarea id="reason"></textarea></label><button id="next">Save and next</button><p id="message"></p>
<script>const cases=PAYLOAD,key='p4-qc-'+cases.map(c=>c.case_id).join('-');let ratings=JSON.parse(localStorage.getItem(key)||'[]'),index=ratings.length,started=performance.now();
function show(){const c=cases[index];document.getElementById('picture').src=c.image;document.getElementById('case').textContent=c.case_id;document.getElementById('progress').textContent=(index+1)+' / '+cases.length;started=performance.now()}
function download(){const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(ratings,null,2)],{type:'application/json'}));a.download='R1_blind_judgments.json';a.click();document.getElementById('next').textContent='Download completed judgments again';document.getElementById('message').textContent='Blind judgments exported. Lock them with the preparation tool before source reveal.'}
document.getElementById('next').onclick=()=>{if(index===cases.length){download();return}const choice=document.getElementById('choice').value,status=document.getElementById('status').value,reason=document.getElementById('reason').value.trim();if(!choice||!status||!reason){document.getElementById('message').textContent='Choose an action and status, and describe the visible evidence.';return}ratings.push({case_id:cases[index].case_id,reviewer:'R1',selected_class:choice,status,reason,duration_seconds:(performance.now()-started)/1000,timestamp:new Date().toISOString()});localStorage.setItem(key,JSON.stringify(ratings));index++;if(index===cases.length){download();return}['choice','status','reason'].forEach(x=>document.getElementById(x).value='');document.getElementById('message').textContent='';show()};if(index<cases.length)show();else{document.getElementById('progress').textContent='Completed draft restored';document.getElementById('next').textContent='Download completed judgments again'}</script></html>'''
    page=page.replace('GUIDE',html.escape(guide)).replace('OPTIONS',''.join(
        f'<option>{x}</option>' for x in CHOICES)).replace('PAYLOAD',payload)
    (directory/'review.html').write_text(page)
    attest_kit(directory,authorization=authorization,scope='INITIAL_KIT_BYTE_FREEZE')
    return manifest


def lock_blind_judgments(judgments, *, reviewer, case_ids, source_key_sha256,
                         attestation=None, authorization=None):
    actual_manifest=verify_byte_attestation(attestation,authorization=authorization)
    if actual_manifest['source_key_sha256']!=source_key_sha256 or actual_manifest['case_set_sha256']!=_digest(sorted(case_ids)):
        raise ValueError('QC judgments differ from byte-attested source/case bindings')
    if reviewer != 'R1' or not judgments or len(judgments)!=len(case_ids):
        raise ValueError('All approved R1 blind judgments must be complete before reveal')
    rows=[]
    for entry in judgments:
        choice=entry.get('selected_class',entry.get('choice'))
        duration=entry.get('duration_seconds')
        if (entry.get('reviewer')!=reviewer or choice not in CHOICES
                or entry.get('status') not in ('VALID','INVALID','UNCERTAIN')
                or not isinstance(entry.get('reason'),str) or not entry['reason'].strip()
                or not entry.get('timestamp') or type(duration) not in (int,float)
                or not 0 < duration < float('inf')):
            raise ValueError('Incomplete blind judgment, reason or measured duration')
        rows.append({k:entry[k] for k in ('case_id','reviewer','status','reason','duration_seconds','timestamp')}
                    | {'selected_class':choice})
    if sorted(x['case_id'] for x in rows)!=sorted(case_ids) or len(set(case_ids))!=len(case_ids):
        raise ValueError('Blind judgment case coverage differs from locked kit')
    if not isinstance(source_key_sha256,str) or len(source_key_sha256)!=64:
        raise ValueError('Frozen source key SHA256 binding is required')
    payload={'reviewer':reviewer,'judgments':rows,'phase':'BLIND_LOCKED',
             'byte_attestation_sha256':attestation['attestation_sha256'],
             'source_key_sha256':source_key_sha256,
             'case_set_sha256':_digest(sorted(case_ids))}
    return payload | {'lock_sha256':_digest(payload)}


def reveal_sources(manifest, lock, *, attestation=None, authorization=None):
    actual_manifest=verify_byte_attestation(attestation,authorization=authorization)
    if actual_manifest!=manifest:
        raise ValueError('QC revealed manifest differs from byte-attested source key')
    if not isinstance(lock,dict) or lock.get('phase')!='BLIND_LOCKED':
        raise ValueError('Blind judgments must be locked before source reveal')
    payload={k:v for k,v in lock.items() if k!='lock_sha256'}
    key_payload={k:v for k,v in manifest.items() if k!='source_key_sha256'}
    if (lock.get('lock_sha256')!=_digest(payload) or lock.get('reviewer')!=manifest['reviewer']
            or lock.get('case_set_sha256')!=manifest['case_set_sha256']
            or lock.get('source_key_sha256')!=manifest.get('source_key_sha256')
            or lock.get('byte_attestation_sha256')!=attestation['attestation_sha256']
            or manifest.get('source_key_sha256')!=_digest(key_payload)):
        raise ValueError('Blind lock or case set was changed')
    by_id={r['case_id']:r for r in lock['judgments']}
    return [dict(row,blind_judgment=by_id[row['case_id']],preserved_cue=None,
                 final_status='UNCERTAIN') for row in manifest['restricted_cases']]


def finalize_qc(manifest, lock, cue_checks, *, attestation=None, authorization=None):
    revealed=reveal_sources(manifest,lock,attestation=attestation,authorization=authorization)
    ids=[r['case_id'] for r in revealed]
    if len(cue_checks)!=len(ids) or sorted(r['case_id'] for r in cue_checks)!=sorted(ids):
        raise ValueError('Post-lock source checks must cover every case exactly once')
    by_id={r['case_id']:r for r in cue_checks}
    output=[]
    for row in revealed:
        cue=by_id[row['case_id']]
        if (type(cue.get('preserved_cue')) is not bool
                or not isinstance(cue.get('reason'),str) or not cue['reason'].strip()
                or not cue.get('timestamp') or type(cue.get('duration_seconds')) not in (int,float)
                or not 0 < cue['duration_seconds'] < float('inf')):
            raise ValueError('Post-lock cue checks require boolean cue, reason and measured duration')
        blind=row['blind_judgment'];status=resolve_qc(blind,row['class_id'],preserved_cue=cue['preserved_cue'])
        output.append({k:v for k,v in row.items() if k not in ('status','final_status','preserved_cue')}
            | {'status':status,'selected_class':blind['selected_class'],
               'blind_reason':blind['reason'],'source_cue_check':cue,'f1_eligible':status=='VALID'})
    def timing(values):
        return {'count':len(values),'sum_seconds':float(np.sum(values)),
                'mean_seconds':float(np.mean(values)),'median_seconds':float(np.median(values)),
                'p95_seconds':float(np.percentile(values,95))}
    by_class={c:{s:sum(r['class_id']==c and r['status']==s for r in output)
                  for s in ('VALID','INVALID','UNCERTAIN')} for c in CLASS_GUIDE}
    families=sorted({r['condition'] for r in output if r['condition']!='clean'})
    common={f:common_valid_sources(output,f) for f in families}
    source_classes={r['source_id']:r['class_id'] for r in output}
    common_coverage={f:{'sources':len(ids),'class_source_support':{
        c:sum(source_classes[sid]==c for sid in ids) for c in CLASS_GUIDE},
        'ten_class_macro_f1_status':'SUPPORTED_CLASSES_ONLY_NO_PREDICTIONS'
        if {source_classes[sid] for sid in ids}==set(CLASS_GUIDE) else 'NOT_ESTIMABLE'}
        for f,ids in common.items()}
    supported={r['class_id'] for r in output if r['status']=='VALID'}
    summary={'reviewer':'R1','reviewer_count':1,'inter_rater_agreement':None,
        'case_count':len(output),'source_count':len({r['source_id'] for r in output}),
        'counts':{s:sum(r['status']==s for r in output) for s in ('VALID','INVALID','UNCERTAIN')},
        'valid_retention':sum(r['status']=='VALID' for r in output)/len(output),
        'blind_timing':timing([r['blind_judgment']['duration_seconds'] for r in output]),
        'source_check_timing':timing([r['source_cue_check']['duration_seconds'] for r in output]),
        'class_support':by_class,'common_valid_sources':common,
        'common_set_coverage':common_coverage,
        'driver_class_support':{f'{driver}/{c}':{status:sum(r['driver_id']==driver
            and r['class_id']==c and r['status']==status for r in output)
            for status in ('VALID','INVALID','UNCERTAIN')}
            for driver,c in sorted({(r['driver_id'],r['class_id']) for r in output})},
        'family_severity_support':{f:{str(s):{status:sum(r['condition']==f and r['severity']==s
            and r['status']==status for r in output) for status in ('VALID','INVALID','UNCERTAIN')}
            for s in range(3)} for f in families},
        'ten_class_macro_f1_status':'SUPPORTED_CLASSES_ONLY_NO_PREDICTIONS' if len(supported)==10 else 'NOT_ESTIMABLE',
        'class_coverage':sorted(supported),'limitations':LIMITATIONS,
        'blind_lock_sha256':lock['lock_sha256'],'source_key_sha256':manifest['source_key_sha256'],
        'byte_attestation_sha256':attestation['attestation_sha256'],
        'cases':output,'status':'QC_LOCKED_SINGLE_REVIEWER'}
    summary['qc_lock_sha256']=_digest(summary)
    return summary


def resolve_qc(judgment, source_label, *, preserved_cue):
    if judgment is None:
        return 'UNREVIEWED'
    if preserved_cue is False or judgment.get('status')=='INVALID':
        return 'INVALID'
    choice=judgment.get('selected_class',judgment.get('choice'))
    if judgment.get('status')=='VALID' and choice==source_label and preserved_cue is True:
        return 'VALID'
    return 'UNCERTAIN'


def _source_review_page(rows):
    """Called only after the locked blind-phase source reveal succeeds."""
    payload=[]
    for row in rows:
        source=row.get('source_path')
        payload.append({'case_id':row['case_id'],'source_label':row['class_id'],
                        'source_image':Path(source).absolute().as_uri() if source else '',
                        'variant_image':f"../images/{row['case_id']}.png",
                        'selected_class':row['blind_judgment']['selected_class']})
    page='''<!doctype html><html lang="en"><meta charset="utf-8"><title>R1 source cue check</title>
<style>body{font:18px system-ui;max-width:1000px;margin:32px auto;background:#f4f5f7;color:#18222c}.pair{display:flex;gap:16px}figure{margin:8px;flex:1}img{width:100%}textarea{width:95%;height:70px}button,select{font:inherit;padding:10px}</style>
<h1>R1 post-lock source cue check</h1><p>The blind choices are locked. Confirm whether the original action evidence remains in each variant. Model predictions remain hidden. Elapsed wall time includes interruptions; drafts save locally.</p>
<p id="progress"></p><p id="label"></p><div class="pair"><figure><img id="source"><figcaption>Source reference</figcaption></figure><figure><img id="variant"><figcaption>Reviewed variant</figcaption></figure></div>
<label>Original action cue preserved? <select id="preserved_cue"><option value="">Choose</option><option value="true">Yes</option><option value="false">No</option></select></label>
<p><textarea id="reason" placeholder="Describe the preserved or removed action evidence"></textarea></p><button id="next">Save and next</button><p id="message"></p>
<script>const cases=PAYLOAD,key='p4-source-'+cases.map(c=>c.case_id).join('-');let ratings=JSON.parse(localStorage.getItem(key)||'[]'),index=ratings.length,started=performance.now();
function show(){const c=cases[index];document.getElementById('source').src=c.source_image;document.getElementById('variant').src=c.variant_image;document.getElementById('progress').textContent=(index+1)+' / '+cases.length+' '+c.case_id;document.getElementById('label').textContent='Source label: '+c.source_label+'; locked blind choice: '+c.selected_class;started=performance.now()}
function download(){const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(ratings,null,2)],{type:'application/json'}));a.download='R1_source_cue_checks.json';a.click();document.getElementById('next').textContent='Download cue checks again';document.getElementById('message').textContent='Exported. Use finalize to lock the QC results.'}
document.getElementById('next').onclick=()=>{if(index===cases.length){download();return}const cue=document.getElementById('preserved_cue').value,reason=document.getElementById('reason').value.trim();if(!cue||!reason){document.getElementById('message').textContent='Choose yes/no and record the action evidence.';return}ratings.push({case_id:cases[index].case_id,preserved_cue:cue==='true',reason,duration_seconds:(performance.now()-started)/1000,timestamp:new Date().toISOString()});localStorage.setItem(key,JSON.stringify(ratings));index++;if(index===cases.length){download();return}document.getElementById('reason').value='';document.getElementById('preserved_cue').value='';document.getElementById('message').textContent='';show()};if(index<cases.length)show();else{document.getElementById('progress').textContent='Completed draft restored';document.getElementById('next').textContent='Download cue checks again'}</script></html>'''
    return page.replace('PAYLOAD',json.dumps(payload).replace('<','\\u003c'))


def common_valid_sources(records, family):
    groups={}
    for row in records:
        if row['condition'] in ('clean',family):
            groups.setdefault(row['source_id'],{}).setdefault((row['condition'],row['severity']),[]).append(row)
    required=[('clean',0)]+[(family,s) for s in range(3)]
    return sorted(sid for sid,rows in groups.items() if all(
        len(rows.get(key,[]))==1 and rows[key][0]['status']=='VALID' for key in required))


def prepare_validation_pilot(metadata_path, expected_sha256, out_dir):
    started=time.monotonic()
    p4_data.rotation_geometry_check()  # Failure precedes any image read.
    records=p4_data.read_vision_metadata(metadata_path,split='val',expected_sha256=expected_sha256)
    # Small pilot selects two deterministic validation sources before opening images.
    selected=sorted(records,key=lambda r:(hashlib.sha256(
        f"42|qc-pilot|{r['source_id']}".encode()).digest(),r['source_id']))[:2]
    if len(selected)!=2:
        raise ValueError('QC pilot requires exactly two verified validation sources')
    cases=[]; image_seconds=[]; sources=[]
    for record in selected:
        before=time.monotonic()
        image=p4_data.load_validation_image(record)
        sha=hashlib.sha256(Path(record['image_path']).read_bytes()).hexdigest()
        source=dict(record,source_sha256=sha)
        sources.append(source)
        for variant,row in p4_data.vision_bank(image,source):
            cases.append((variant,dict(row,source_path=record['image_path'])))
        image_seconds.append(time.monotonic()-before)
    manifest=build_review_kit(cases,out_dir)
    measurements={'sources':2,'cases':38,'reviewers':['R1'],'reviewer_role':'project developer',
        'model_predictions':0,'heldout_images_opened':0,'human_ratings_count':0,
        'preparation_seconds':time.monotonic()-started,'source_generation_seconds':image_seconds,
        'human_review_seconds':None,'valid_retention':None,'status':'HUMAN_PILOT_PENDING',
        'scenario_estimates':[{'assumed_seconds_per_case':s,'pilot_seconds':38*s,
                              'maximum_formal_3800_cases_hours':3800*s/3600,
                              'measured':False} for s in (5,10,20)],
        'limitations':LIMITATIONS,'sources':sources}
    _json(Path(out_dir)/'restricted/preparation_measurements.json',measurements)
    return measurements


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    pilot=sub.add_parser('pilot');pilot.add_argument('--metadata',required=True)
    pilot.add_argument('--metadata-sha256',required=True);pilot.add_argument('--output',required=True)
    lock=sub.add_parser('lock');lock.add_argument('--kit',required=True);lock.add_argument('--ratings',required=True)
    reveal=sub.add_parser('reveal');reveal.add_argument('--kit',required=True)
    attest=sub.add_parser('attest');attest.add_argument('--kit',required=True)
    final=sub.add_parser('finalize');final.add_argument('--kit',required=True)
    final.add_argument('--cue-checks',required=True)
    for command in (lock,reveal,attest,final):
        command.add_argument('--execution-spec',help='Existing approved P4-B execution_spec.json; required for held-out kits')
    args=parser.parse_args(argv)
    authorization=None
    if getattr(args,'execution_spec',None):
        authorization=authorization_from_execution_spec(args.execution_spec,args.kit)
    if args.command=='pilot':
        print(json.dumps(prepare_validation_pilot(args.metadata,args.metadata_sha256,args.output),indent=2))
    elif args.command=='attest':
        frozen=attest_kit(args.kit,authorization=authorization,scope='CURRENT_KIT_BYTE_FREEZE')
        print('CURRENT_KIT_BYTE_FREEZE',frozen['attestation_sha256'])
    else:
        kit=Path(args.kit);manifest=json.loads((kit/'restricted/source_key.json').read_text())
        attestation=load_byte_attestation(kit,authorization=authorization)
        if args.command=='lock':
            ratings=json.loads(Path(args.ratings).read_text())
            locked=lock_blind_judgments(ratings,reviewer='R1',case_ids=[r['case_id'] for r in manifest['restricted_cases']],
                                       source_key_sha256=manifest['source_key_sha256'],attestation=attestation,
                                       authorization=authorization)
            _json(kit/'restricted/R1_blind_locked.json',locked)
            print('R1_BLIND_LOCKED',locked['lock_sha256'])
        elif args.command=='reveal':
            locked=json.loads((kit/'restricted/R1_blind_locked.json').read_text())
            rows=reveal_sources(manifest,locked,attestation=attestation,authorization=authorization)
            _json(kit/'restricted/R1_source_reveal.json',rows)
            with (kit/'restricted/source_review.html').open('x') as stream:
                stream.write(_source_review_page(rows))
            with (kit/'restricted/R1_source_cue_check.csv').open('x',newline='') as stream:
                writer=csv.writer(stream);writer.writerow(['case_id','preserved_cue','source_check_reason','duration_seconds','timestamp'])
                writer.writerows([[r['case_id'],'','','',''] for r in rows])
            print('R1_SOURCE_REVEALED; complete post-lock cue checks; no automatic VALID ratings')
        else:
            locked=json.loads((kit/'restricted/R1_blind_locked.json').read_text())
            source=Path(args.cue_checks)
            if source.suffix.lower()=='.csv':
                with source.open(newline='') as stream:raw=list(csv.DictReader(stream))
                cues=[]
                for row in raw:
                    value=row['preserved_cue'].lower().strip()
                    if value not in ('true','false'):
                        raise ValueError('CSV preserved_cue must be true/false')
                    cues.append(dict(row,preserved_cue=value=='true',reason=row['source_check_reason'],
                                     duration_seconds=float(row['duration_seconds'])))
            else:
                cues=json.loads(source.read_text())
            result=finalize_qc(manifest,locked,cues,attestation=attestation,authorization=authorization)
            _json(kit/'restricted/R1_qc_final_locked.json',result)
            print('R1_QC_LOCKED',result['qc_lock_sha256'])
    return 0


if __name__=='__main__':
    raise SystemExit(main())
