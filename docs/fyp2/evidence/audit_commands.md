
## fyp2_audit_checks.py

```python
import os,sys,json,time,platform,subprocess,tempfile,shutil,hashlib,importlib.metadata as im
from datetime import datetime,timezone
from pathlib import Path
src=Path('/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1')
out=Path('/Users/liu/.codex/worktrees/d39a/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/evidence')
scratch=Path(tempfile.mkdtemp(prefix='fyp2-audit-'))
py=src/'.venv/bin/python'
records=[]
def run(id,args,cwd,extra=None,timeout=120):
 env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','TMPDIR':str(scratch),'PYTHONPATH':str(src/'backend'),'DRA_DATABASE_URL':f'sqlite:///{scratch}/fallback.db','OMP_NUM_THREADS':'2','OPENBLAS_NUM_THREADS':'2','VECLIB_MAXIMUM_THREADS':'2',**(extra or {})}
 start=datetime.now(timezone.utc).isoformat(); t=time.monotonic()
 try:
  p=subprocess.run(args,cwd=cwd,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)
  code=p.returncode; output=p.stdout
 except subprocess.TimeoutExpired as e:
  code=124; output=(e.stdout or b'').decode() if isinstance(e.stdout,bytes) else (e.stdout or '')
  output+='\nAUDIT TIMEOUT\n'
 rec={'id':id,'argv':[str(x) for x in args],'cwd':str(cwd),'start_utc':start,'duration_s':round(time.monotonic()-t,3),'timeout_s':timeout,'exit_code':code,'environment_overrides':{k:env[k] for k in ['PYTHONDONTWRITEBYTECODE','TMPDIR','PYTHONPATH','DRA_DATABASE_URL','OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','VECLIB_MAXIMUM_THREADS']},'log':f'evidence/{id}.log'}
 (out/f'{id}.log').write_text(json.dumps(rec,indent=2)+'\n\n'+output)
 records.append(rec); (out/'checks.json').write_text(json.dumps(records,indent=2)+'\n')
 print(id,code,round(rec['duration_s'],2),output[-1000:],flush=True)
run('ENV',['/bin/zsh','-c',"uname -m && sw_vers && sysctl -n machdep.cpu.brand_string hw.memsize && node --version && npm --version"],src)
run('PYTEST',[str(py),'-m','pytest','backend/tests','-vv','-p','no:cacheprovider','--basetemp',str(scratch/'pytest')],src,timeout=120)
copy=scratch/'frontend-check';copy.mkdir()
for folder in ['ai','frontend']:
 shutil.copytree(src/folder,copy/folder)
for f in ['package.json','package-lock.json','tsconfig.json','vite.config.ts','vitest.config.ts','eslint.config.js']:
 shutil.copy2(src/f,copy/f)
(copy/'node_modules').symlink_to(src/'node_modules',target_is_directory=True)
run('VITEST',['npm','test','--','--no-cache'],copy)
run('BUILD',['npm','run','build'],copy)
run('LINT',['npm','run','linc'],copy)
(out/'scratch.json').write_text(json.dumps({'scratch':str(scratch),'frontend_copy':str(copy),'source':str(src)},indent=2)+'\n')

```

## fyp2_audit_followup.py

```python
exec(open('/tmp/fyp2_audit_checks.py').read().split("run('ENV'")[0])
records=json.loads((out/'checks.json').read_text())
prior=json.loads((out/'scratch.json').read_text());scratch=Path(prior['scratch'])
run('ENV-VERSIONS',['/bin/zsh','-c','node --version && npm --version'],src)
run('BUILD-RUNNER',['npm','run','build','--','--configLoader','runner'],Path(prior['frontend_copy']))
run('ML-TELEMETRY',[str(py),'ml/experiments/telemetry_benchmark.py','--output',str(out/'telemetry_recheck.json')],src,timeout=90)
run('ML-VISION-SMOKE',[str(py),'ml/experiments/vision_benchmark.py','--mode','evaluate','--limit','20','--parity-samples','20','--output',str(out/'vision_smoke.json')],src,timeout=90)

```

## fyp2_audit_metadata.py

```python
import json,hashlib,subprocess,platform,sys,importlib.metadata as im
from pathlib import Path
from datetime import datetime,timezone
import pandas as pd
src=Path('/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1'); out=Path('/Users/liu/.codex/worktrees/d39a/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/evidence'); data=Path('/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment-')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
files=[]
for folder in ['ai/src','backend/app','backend/tests','frontend','ml/experiments','ml/vision','ml/telemetry','ml/outputs','docs','prototype-tests','FYP2_Codex_ClaudeCode_Audit_Package_v2']:
 for p in (src/folder).rglob('*'):
  if p.is_file() and p.suffix in ['.py','.ts','.tsx','.css','.html','.md','.json','.ipynb','.onnx','.pt','.txt','.log','.csv'] and not any(x in p.parts for x in ['__pycache__','cache','node_modules']):files.append(p)
for name in ['README.md','AGENTS.md','package.json','package-lock.json','vite.config.ts','vitest.config.ts','tsconfig.json','eslint.config.js','.gitignore','ml/.gitignore','backend/requirements.txt','backend/requirements-inference.txt']:
 files.append(src/name)
inventory={str(p.relative_to(src)):{'bytes':p.stat().st_size,'sha256':sha(p),'lines':len(p.read_text().splitlines()) if p.suffix not in ['.pt','.onnx'] else None} for p in sorted(set(files))}
getgit=lambda root,args:subprocess.check_output(['git','-C',str(root),*args],text=True).strip()
report={'captured_utc':datetime.now(timezone.utc).isoformat(),'source_root':str(src),'branch':getgit(src,['branch','--show-current']),'head':getgit(src,['rev-parse','HEAD']),'source_status':getgit(src,['status','--short']),'output_head':getgit(out.parents[2],['rev-parse','HEAD']),'files':inventory,'environment':{'python':sys.version,'platform':platform.platform(),'packages':{p:im.version(p) for p in ['pytest','httpx','fastapi','SQLAlchemy','pydantic','torch','torchvision','onnxruntime','xgboost','numpy','pandas','scikit-learn','Pillow']}}}
(out/'source_inventory.json').write_text(json.dumps(report,indent=2)+'\n')
v=data/'eda_outputs/processed/vision/vision_metadata_with_split.csv';df=pd.read_csv(v)
groups={s:set(df[df.split==s].driver_id) for s in ['train','val','test']}
summary={'vision':{'metadata_path':str(v),'sha256':sha(v),'columns':list(df.columns),'rows':df.split.value_counts().to_dict(),'drivers':{s:len(g) for s,g in groups.items()},'driver_overlap':{a+'_'+b:len(groups[a]&groups[b]) for a,b in [('train','val'),('train','test'),('val','test')]},'duplicate_image_paths':int(df.image_path.duplicated().sum()),'missing_image_paths':sum(not Path(x).is_file() for x in df.image_path),'image_byte_near_duplicate_audit':'NOT_RUN'},'telemetry':{},'historical_evidence':{}}
tables={}
for split in ['train','val','test']:
 p=data/f'eda_outputs/processed/telemetry/telemetry_{split}.csv'; t=pd.read_csv(p); tables[split]=t
 summary['telemetry'][split]={'path':str(p),'sha256':sha(p),'rows':len(t),'columns':list(t.columns),'missing_values':int(t.isna().sum().sum()),'duplicate_complete_rows':int(t.duplicated().sum()),'class_counts':t.behavior_label.value_counts().to_dict()}
summary['telemetry']['exact_row_overlap']={a+'_'+b:len(set(pd.util.hash_pandas_object(tables[a],index=False)) & set(pd.util.hash_pandas_object(tables[b],index=False))) for a,b in [('train','val'),('train','test'),('val','test')]}
for rel in ['docs/evidence/2026-09-28/vision-benchmark.json','docs/evidence/2026-09-28/telemetry-benchmark.json','docs/evidence/2026-09-28/robustness-probe.json','docs/evidence/2026-09-28/linear-probe.json']:
 j=json.loads((src/rel).read_text()); summary['historical_evidence'][rel]={k:j[k] for k in j if k not in ['evaluation','conditions','models']}
 if 'evaluation' in j:summary['historical_evidence'][rel]['evaluation']={k:v for k,v in j['evaluation'].items() if k not in ['per_class','confusion_matrix']}
 if 'conditions' in j:summary['historical_evidence'][rel]['conditions']={k:{x:v[x] for x in ['samples','accuracy','macro_f1']} for k,v in j['conditions'].items()}
for name in ['vision','telemetry']:
 j=json.loads((src/f'ml/outputs/{name}/metrics.json').read_text());summary[name]['baseline_metrics']={k:j[k] for k in j if k!='metrics'}
 summary[name]['baseline_metrics']['metrics']={s:{k:v for k,v in m.items() if k!='confusion_matrix'} for s,m in j['metrics'].items()}
(out/'data_artifact_audit.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps({'source_files':len(inventory),'vision':{k:v for k,v in summary['vision'].items() if k!='baseline_metrics'},'telemetry':{k:v for k,v in summary['telemetry'].items() if k!='baseline_metrics'}},indent=2))

```

## fyp2_audit_diagnostics.py

```python
import json
from datetime import datetime,timezone,timedelta
from app import fusion,inference
from app.schemas import WindowInput,RuntimeConfig,TelemetryFeatures
base=datetime(2026,10,9,10,tzinfo=timezone.utc)
rows=[]
def capture(id,expected,observed,status):rows.append(dict(id=id,expected=expected,observed=observed,status=status))
for p,t,vs,ts,name,expected in [(.1,.9,'fresh','fresh','UT-FUS-CLEAN',50),(.1,.9,'missing','fresh','E3-01',90),(.1,.9,'fresh','missing','E3-02',10),(.1,.9,'stale','fresh','E3-04',65.2),(.1,.9,'fresh','stale','E3-05',34.8),(.1,.9,'stale','stale','E3-06',50)]:
 v=fusion.compute_risk_score(p,t,.5,.5,vs,ts);capture(name,expected,v,'TEST_PASSED' if v==expected else 'TEST_FAILED')
w=WindowInput(P_distraction=.9,P_telemetry_anomaly=.9,vision_status='missing',telemetry_status='missing')
u=inference.run_inference('audit',1,w,now=base).model_dump()
capture('E3-03','unavailable without a valid-looking numeric Low/NORMAL assessment',{k:u[k] for k in ['RiskScore','RiskLevel','SystemHealth','AlertSeverity','DominantEvidence']},'TEST_FAILED')
u=inference.run_inference('audit',1,WindowInput(P_distraction=.1,P_telemetry_anomaly=.9,vision_status='missing'),config=RuntimeConfig(weight_vision=1,weight_telemetry=0),now=base).model_dump()
capture('UT-FUS-ZERO-WEIGHT','no usable weighted evidence => unavailable',{k:u[k] for k in ['RiskScore','RiskLevel','SystemHealth']},'TEST_FAILED')
for age in [2.999,3,3.001]:
 observed=inference.freshness('fresh',(base-timedelta(seconds=age)).isoformat(),base,3)
 expected='stale' if age>3 else 'fresh';capture('UT-TIME-FRESH-'+str(age),expected,observed,'TEST_PASSED' if observed==expected else 'TEST_FAILED')
for score,expected in [(29.9,'Low'),(30,'Medium'),(59.9,'Medium'),(60,'High')]:
 actual=fusion.map_risk_level(score);capture('UT-FUS-BOUNDARY-'+str(score),expected,actual,'TEST_PASSED' if actual==expected else 'TEST_FAILED')
state={};config=RuntimeConfig(ema_alpha=1)
for seconds,p,expected in [(0,1,'CAUTION'),(1.999,1,'CAUTION'),(2,1,'HIGH_ALERT'),(3,0,'HIGH_ALERT'),(5,0,'HIGH_ALERT'),(7,0,'HIGH_ALERT'),(9,0,'HIGH_ALERT'),(11,0,'HIGH_ALERT'),(12.999,0,'HIGH_ALERT'),(13,0,'NORMAL')]:
 actual=inference.run_inference('audit',int(seconds*1000)+1,WindowInput(P_distraction=p,P_telemetry_anomaly=p),state=state,config=config,now=base+timedelta(seconds=seconds)).AlertSeverity
 capture('UT-TIME-FSM-'+str(seconds),expected,actual,'TEST_PASSED' if actual==expected else 'TEST_FAILED')
capture('E3-DRIFT-COUNTEREXAMPLE','formula correct but original delta<=.15 target unmet',{'R_full':.5,'R_vision_missing':.9,'delta':.4,'formula_pass':True,'original_target_met':False},'PARTIALLY_VERIFIED')
print(json.dumps({'executed_utc':datetime.now(timezone.utc).isoformat(),'scope':'Small read-only deterministic diagnostics of existing functions; no test definitions changed, no inference benchmark, no DB connection','cases':rows},indent=2))

```

## fyp2_audit_diag_run.py

```python
exec(open('/tmp/fyp2_audit_checks.py').read().split("run('ENV'")[0])
records=json.loads((out/'checks.json').read_text()); scratch=Path(json.loads((out/'scratch.json').read_text())['scratch'])
run('DIAGNOSTICS',[str(py),'/tmp/fyp2_audit_diagnostics.py'],src,timeout=30)
for name in ['fyp2_audit_checks.py','fyp2_audit_followup.py','fyp2_audit_metadata.py','fyp2_audit_diagnostics.py','fyp2_audit_diag_run.py']:
 p=Path('/tmp')/name
 with (out/'audit_commands.md').open('a') as f:f.write('\n## '+name+'\n\n```python\n'+p.read_text()+'\n```\n')

```

## fyp2_finalize_evidence.py

```python
import os,json,hashlib,subprocess,platform,re
from pathlib import Path
from datetime import datetime,timezone
src=Path('/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1'); out=Path('/Users/liu/.codex/worktrees/d39a/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2');ev=out/'evidence'
start=datetime.now(timezone.utc).isoformat();inventory=json.loads((ev/'source_inventory.json').read_text())
paths=[]
for root in ['ai','backend','frontend','ml','docs','prototype-tests','.github','FYP2_Codex_ClaudeCode_Audit_Package_v2']:
 for base,dirs,files in os.walk(src/root):
  dirs[:]=[d for d in dirs if d not in ['__pycache__','node_modules','.git','.venv','.local']]
  for name in files:
   p=Path(base)/name
   if p.suffix in ['.pt','.pth','.onnx','.pkl','.joblib','.npz','.ipynb','.py','.ts','.tsx','.json','.yaml','.yml','.md','.pdf','.docx']:
    paths.append({'path':str(p.relative_to(src)),'bytes':p.stat().st_size})
changed=[]
for f,m in inventory['files'].items():
 p=src/f
 if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest()!=m['sha256']:changed.append(f)
result={'command_id':'DISCOVERY-FINAL','start_utc':start,'finished_utc':datetime.now(timezone.utc).isoformat(),'command':'python3 /tmp/fyp2_finalize_evidence.py (script preserved in evidence/audit_commands.md)','source_root':str(src),'metadata_only_paths':paths,'changed_since_source_inventory':changed,'source_git_head':subprocess.check_output(['git','-C',str(src),'rev-parse','HEAD'],text=True).strip(),'source_git_status':subprocess.check_output(['git','-C',str(src),'status','--short'],text=True),'output_git_status':subprocess.check_output(['git','status','--short'],text=True),'checks':{'source_144_snapshot_files_unchanged':not changed,'no_primary_github_workflow':not (src/'.github/workflows').exists()}}
(ev/'repository_discovery.json').write_text(json.dumps(result,indent=2)+'\n')
with (ev/'audit_commands.md').open('a') as f:f.write('\n## fyp2_finalize_evidence.py\n\n```python\n'+Path('/tmp/fyp2_finalize_evidence.py').read_text()+'\n```\n')
print('discovered',len(paths),'paths; changed:',changed)
print('artifact_names',[p['path'] for p in paths if Path(p['path']).suffix in ['.pt','.pth','.onnx','.pkl','.joblib','.npz']])
# Append exact inherited validation metrics; explicitly do not claim reproduction.
with (out/'04_ML_COMPARISON_AND_TUNING_AUDIT.md').open('a') as f:
 f.write('\n## Stored validation metrics (artifact inspection only)\n\nThese are `FYP1_REPORTED` / inspected stored values, not freshly rerun validation.\n\n| Model | Validation accuracy | Validation macro-F1 | Source |\n|---|---:|---:|---|\n')
 for name in ['vision','telemetry']:
  j=json.loads((src/f'ml/outputs/{name}/metrics.json').read_text());v=j['metrics']['val'];f.write(f"| {name} baseline | {v['accuracy']:.9f} | {v['macro_f1']:.9f} | `ml/outputs/{name}/metrics.json` / metrics.val |\n")

```

## fyp2_validate_documents.py

```python
from pathlib import Path
from datetime import datetime,timezone
import json,re,hashlib,subprocess
out=Path('/Users/liu/.codex/worktrees/d39a/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2');src=Path('/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1');ev=out/'evidence'
required=['00_AUDIT_EXECUTIVE_SUMMARY.md','01_MODULE_AND_ARCHITECTURE_INVENTORY.md','02_TEST_CASE_INVENTORY_AND_CRITIQUE.md','03_EVALUATION_COVERAGE_MATRIX.md','04_ML_COMPARISON_AND_TUNING_AUDIT.md','05_RUBRIC_TRACEABILITY_AND_REPORT_MAP.md','06_WEEK7_CRITICAL_PATH_AND_ACTION_PLAN.md','07_EVIDENCE_MANIFEST.md','08_OPEN_DECISIONS_FOR_SUPERVISOR.md']
master=(src/'FYP2_Codex_ClaudeCode_Audit_Package_v2/FYP2_MASTER_REPOSITORY_AUDIT_PROMPT.md').read_text()
errors=[];refs=[];links=[]
for name in required:
 if name not in master:errors.append('Required filename not in master: '+name)
 p=out/name
 if not p.exists() or p.stat().st_size<1000:errors.append('Missing/empty required doc: '+name);continue
 t=p.read_text()
 for link in re.findall(r'\[[^\]]*\]\(([^)]+)\)',t):
  if link.startswith(('http','/','#')):continue
  links.append(link)
  if not (p.parent/link.split('#')[0]).exists() and link!='evidence/document_validation.json':errors.append('Broken link: '+name+':'+link)
 for path,start,end in re.findall(r'((?:backend|frontend|ai|ml)/[\w/.-]+\.(?:py|ts|tsx)):(\d+)(?:[–-](\d+))?',t):
  q=src/path
  if not q.exists():errors.append('Source absent: '+path);continue
  if not 1<=int(start)<=int(end or start)<=len(q.read_text().splitlines()):errors.append('Source range invalid: '+path+':'+start)
  refs.append([path,start,end])
 width=None
 for line in t.splitlines():
  if line.startswith('|'):
   current=len(line.split('|'))
   if width and current!=width:errors.append('Table columns: '+name+' '+line[:60])
   width=current
  else:width=None
manifest=json.loads((out/'audit_manifest.json').read_text());tests=manifest['test_cases']
if len(tests)!=60 or len(set(x['id'] for x in tests))!=60:errors.append('Test count/id mismatch')
fields=['id','layer','requirement','input_origin_and_split','preconditions','steps','expected_output','metric_unit','pass_threshold','implementation_status','test_presence','execution_status','actual_results','run_command','executed_date','source','evidence','methodological_verdict','concern','proposed_correction','priority']
for case in tests:
 for key in fields:
  if key not in case:errors.append('Test schema missing '+case['id']+':'+key)
 if case['execution_status'] not in manifest['allowed_statuses']:errors.append('Invalid status')
 if not (out/case['evidence']).exists():errors.append('Missing test log')
 if case['methodological_verdict'] not in ['SOUND','SOUND_WITH_RESTRICTIONS','NEEDS_REDRAFT','INVALID']:errors.append('Invalid verdict')
pylog=(ev/'PYTEST.log').read_text();tslog=(ev/'VITEST.log').read_text()
if len(re.findall(r'backend/tests/[^\n]+ PASSED',pylog))!=28:errors.append('Pytest raw result mismatch')
if '32 passed (32)' not in tslog:errors.append('TS raw result mismatch')
inv=json.loads((ev/'source_inventory.json').read_text());changed=[]
for name,meta in inv['files'].items():
 p=src/name
 if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest()!=meta['sha256']:changed.append(name)
if changed:errors.append('Source changed: '+str(changed))
status=subprocess.check_output(['git','status','--short'],text=True).strip()
if status!='?? docs/fyp2/':errors.append('Unexpected output worktree edits: '+status)
current_src_status=subprocess.check_output(['git','-C',str(src),'status','--short'],text=True).strip()
if current_src_status!=inv['source_status'].strip():errors.append('Primary git status changed')
# Inspect coverage requirements structurally after the substantive source/document review.
coverage={'all_nine_named_master_outputs':all((out/n).exists() for n in required),'source_scope_explicit':all('17c4b41' in (out/n).read_text() and 'ae55041' in (out/n).read_text() for n in required),'all_weekly_gates':all('| W'+str(i)+' |' in (out/required[6]).read_text() for i in range(1,8)),'five_required_models':all(s in (out/required[4]).read_text() for s in ['MobileNetV3-Large','ResNet18','XGBoost','Random Forest','Logistic Regression']),'all_evaluation_categories':all(s in (out/required[3]).read_text() for s in ['E1-V','E1-T','E2','E3','E4','E5','D0','D1','D2','D3']),'minimum_test_prefixes':all(s in (out/required[2]).read_text() for s in ['UT-FUS','UT-TIME','UT-MODEL','IT-AI','IT-API','ST-REPLAY','ST-FAIL','PERF','UAT']),'report_claim_matrix':'Claim-to-evidence wording matrix' in (out/required[5]).read_text(),'master_completion_map':'Requirement-by-requirement audit completion map' in (out/required[7]).read_text(),'source_snapshot_files_unchanged':not changed,'docs_only_changes':status=='?? docs/fyp2/'}
if not all(coverage.values()):errors.append('Structural coverage missing: '+str(coverage))
result={'executed_utc':datetime.now(timezone.utc).isoformat(),'command':'python3 /tmp/fyp2_validate_documents.py','exit_code':0 if not errors else 1,'required_documents':required,'review_scope':'Substantive audit mapped in07; automated checks verify existence, bounded refs, links, tables, result/schema counts and unchanged source. Structure checks alone are not project acceptance.','source_files_checked':len(inv['files']),'source_references_checked':len(refs),'local_links_checked':len(links),'test_cases_checked':len(tests),'coverage':coverage,'errors':errors,'application_source_changes':changed,'git_status':status}
(ev/'document_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
if not errors:
 p=out/'task_plan.md';t=p.read_text().replace('5. Validate references, completeness and unchanged application files — in_progress.','5. Validate references, completeness and unchanged application files — complete.').replace('Verify nine deliverables and machine manifest against the master requirement map; finish handoff.','Audit complete. Hand off nine documents, key findings and next72h plan; implementation remains unstarted.');p.write_text(t)
 with (out/'progress.md').open('a') as f:f.write('\nFinal verification: nine required documents exist; all60 existing cases reviewed; full master requirement mapping in07 checked. Application/model/test snapshot144 files unchanged and desktop git status unchanged. Output worktree changes confined to docs/fyp2. Audit complete; W7 development remains NO-GO and no training/code modification was performed.\n')
manifest['completion_audit']={'audit_completed':not errors,'project_week7_complete':False,'verification':'evidence/document_validation.json','master_map':'07_EVIDENCE_MANIFEST.md#requirement-by-requirement-audit-completion-map'}
manifest['generated_utc']=datetime.now(timezone.utc).isoformat()
manifest['artifacts']={str(p.relative_to(out)):{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(out.rglob('*')) if p.is_file() and p.name!='audit_manifest.json'}
(out/'audit_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False,indent=2))
raise SystemExit(0 if not errors else 1)

```
