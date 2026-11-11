# Task 10A / CX-0 — Phase 0 preflight_report

日期：2026-10-26，Asia/Kuala_Lumpur。作者：Codex（ML事实核查与预声明）。
**结论：GO（仅 Phase 0 依赖预检）。**

指定依赖均可读取，两份manifest通过原样系统CLI校验，stable200身份及图片可复核。GO不表示候选已集成、Stage-1/2已通过、容差已批准或runner可运行。

## 范围

- 未修改、暂存、提交任何工作区的tracked文件；未切分支、reset、clean、merge、push或清理任何东西。
- 写入仅限 `/Users/liu/Desktop/FYP2-Live-System/.superpowers/collab/codex/`、用户明确要求的忽略文件 `/Users/liu/Desktop/FYP2-Live-System/.superpowers/collab/BOARD.md`，以及用户要求的 `/tmp/task10a-cx0-validator-20261026-t7lct272/` 三份原样校验器/schema源码副本。临时目录保留。
- 未启动服务或触碰8000端口；未打开、复制、哈希或写入 `driver_risk.db*`。git status仅列出既有sidecar文件名。
- 未加载模型、执行provider forward、Stage-2 runner、训练、HPO、导出或benchmark。
- 读了计划、分析§1–3（C-1–C-12优先）、规格和BOARD；用户角色限制覆盖计划里的其他实现/提交步骤。
- fast-context优先尝试后返回 `Windsurf API Key not found`；回退为 `rg` 与精确行读取，没有查找/提取凭据。

## Step 1 — Git状态及dirty列表

| 项目 | 当日结果 |
|---|---|
| Live root / branch | `/Users/liu/Desktop/FYP2-Live-System` / `fyp2/live-system` |
| Live HEAD | `7e64c4d0632923d7bb90c1c8f6b7cb757ca5ea65`，与BOARD当前基线一致 |
| Live完整dirty列表 | `?? AGENTS.md`；`?? backend/driver_risk.db-shm`；`?? backend/driver_risk.db-wal` |
| Live staged / tracked unstaged | 均空 |
| ML root / branch | `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1` / `fyp2/ml-training` |
| ML HEAD | `ba1046c9debc9fda9f87bd55016ad42e6eb360cf` |
| ML dirty | 12个既有tracked CSV修改 + `?? AGENTS.md`，完整路径在下方 |
| ML staged | 空 |
| 基线漂移 | 计划Live2745348、ML335da4e均不是今天HEAD；未改写历史来源commit |
| Live运行代码相对2745348 | `git diff --exit-code 2745348 HEAD -- backend ai/src frontend/src scripts` exit0且输出空 |
| collab写入边界 | `.git/info/exclude:8:.superpowers/`，且 `git ls-files -- .superpowers/collab` 空 |

下列脚本逐条打印命令和exit code；`GIT_OPTIONAL_LOCKS=0`避免可选index刷新。完整dirty/worktrees如下。

### 命令记录：git_state

工作目录：`/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1`。exit code：`0`。

```bash
GIT_OPTIONAL_LOCKS=0 python3 -B - <<'PY'
import subprocess,json
from datetime import datetime
from zoneinfo import ZoneInfo
print('observed_at='+datetime.now(ZoneInfo('Asia/Kuala_Lumpur')).isoformat())
for root in ['/Users/liu/Desktop/FYP2-Live-System','/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1']:
 print('ROOT='+root)
 for a in [['pwd'],['git','rev-parse','--show-toplevel'],['git','branch','--show-current'],['git','rev-parse','HEAD'],['git','status','--short'],['git','diff','--cached','--name-only'],['git','diff','--name-only']]:
  p=subprocess.run(a,cwd=root,text=True,capture_output=True);print('COMMAND='+json.dumps(a)+' EXIT='+str(p.returncode));print(p.stdout,end='');assert p.returncode==0,p.stderr
p=subprocess.run(['git','worktree','list'],cwd='/Users/liu/Desktop/FYP2-Live-System',text=True,capture_output=True);print('COMMAND=git worktree list EXIT='+str(p.returncode));print(p.stdout,end='');assert p.returncode==0
PY
```

当日输出：

```text
observed_at=2026-10-26T12:28:34.218090+08:00
ROOT=/Users/liu/Desktop/FYP2-Live-System
COMMAND=["pwd"] EXIT=0
/Users/liu/Desktop/FYP2-Live-System
COMMAND=["git", "rev-parse", "--show-toplevel"] EXIT=0
/Users/liu/Desktop/FYP2-Live-System
COMMAND=["git", "branch", "--show-current"] EXIT=0
fyp2/live-system
COMMAND=["git", "rev-parse", "HEAD"] EXIT=0
7e64c4d0632923d7bb90c1c8f6b7cb757ca5ea65
COMMAND=["git", "status", "--short"] EXIT=0
?? AGENTS.md
?? backend/driver_risk.db-shm
?? backend/driver_risk.db-wal
COMMAND=["git", "diff", "--cached", "--name-only"] EXIT=0
COMMAND=["git", "diff", "--name-only"] EXIT=0
ROOT=/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1
COMMAND=["pwd"] EXIT=0
/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1
COMMAND=["git", "rev-parse", "--show-toplevel"] EXIT=0
/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1
COMMAND=["git", "branch", "--show-current"] EXIT=0
fyp2/ml-training
COMMAND=["git", "rev-parse", "HEAD"] EXIT=0
ba1046c9debc9fda9f87bd55016ad42e6eb360cf
COMMAND=["git", "status", "--short"] EXIT=0
 M ml/outputs/runs/e1_preparation_20261019/telemetry_variants.csv
 M ml/outputs/runs/e1_preparation_20261019/vision_manifest.csv
 M ml/outputs/runs/e1_preparation_20261019_record_missingness/telemetry_variants.csv
 M ml/outputs/runs/e1_preparation_20261019_record_missingness/vision_manifest.csv
 M ml/outputs/runs/p4a_20261021/qc/validation_pilot/R1.csv
 M ml/outputs/runs/p5_candidates_20261023/p5_mobilenet_v3_large_search006_seed42_20261023/predictions_test_clean.csv
 M ml/outputs/runs/p5_candidates_20261023/p5_mobilenet_v3_large_search006_seed42_20261023/validation/stable200_annotations.csv
 M ml/outputs/runs/p5_candidates_20261023/p5_mobilenet_v3_large_search006_seed42_20261023/validation/stable200_saved_predictions.csv
 M ml/outputs/runs/p5_candidates_20261023/p5_resnet18_search004_seed42_20261023/predictions_test_clean.csv
 M ml/outputs/runs/p5_candidates_20261023/p5_resnet18_search004_seed42_20261023/validation/stable200_annotations.csv
 M ml/outputs/runs/p5_candidates_20261023/p5_resnet18_search004_seed42_20261023/validation/stable200_saved_predictions.csv
 M ml/outputs/runs/p5_candidates_20261023/telemetry_research_evidence/predictions_test_clean.csv
?? AGENTS.md
COMMAND=["git", "diff", "--cached", "--name-only"] EXIT=0
COMMAND=["git", "diff", "--name-only"] EXIT=0
ml/outputs/runs/e1_preparation_20261019/telemetry_variants.csv
ml/outputs/runs/e1_preparation_20261019/vision_manifest.csv
ml/outputs/runs/e1_preparation_20261019_record_missingness/telemetry_variants.csv
ml/outputs/runs/e1_preparation_20261019_record_missingness/vision_manifest.csv
ml/outputs/runs/p4a_20261021/qc/validation_pilot/R1.csv
ml/outputs/runs/p5_candidates_20261023/p5_mobilenet_v3_large_search006_seed42_20261023/predictions_test_clean.csv
ml/outputs/runs/p5_candidates_20261023/p5_mobilenet_v3_large_search006_seed42_20261023/validation/stable200_annotations.csv
ml/outputs/runs/p5_candidates_20261023/p5_mobilenet_v3_large_search006_seed42_20261023/validation/stable200_saved_predictions.csv
ml/outputs/runs/p5_candidates_20261023/p5_resnet18_search004_seed42_20261023/predictions_test_clean.csv
ml/outputs/runs/p5_candidates_20261023/p5_resnet18_search004_seed42_20261023/validation/stable200_annotations.csv
ml/outputs/runs/p5_candidates_20261023/p5_resnet18_search004_seed42_20261023/validation/stable200_saved_predictions.csv
ml/outputs/runs/p5_candidates_20261023/telemetry_research_evidence/predictions_test_clean.csv
COMMAND=git worktree list EXIT=0
/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1                                                           ba1046c [fyp2/ml-training]
/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/.claude/worktrees/audit-files-dev-plan-ed0c73             17c4b41 [claude/audit-files-dev-plan-ed0c73]
/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/.claude/worktrees/busy-northcutt-1c82ef                   17c4b41 [claude/busy-northcutt-1c82ef]
/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/.claude/worktrees/exciting-keller-fdf913                  17c4b41 [claude/gallant-raman-c59f98]
/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/.claude/worktrees/intelligent-chebyshev-836ed9            17c4b41 [claude/heuristic-satoshi-3045aa]
/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/.claude/worktrees/interesting-ishizaka-daf43a             17c4b41 [claude/interesting-ishizaka-daf43a]
/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/.claude/worktrees/sprint-design-acceptance-review-bdf1f8  ae55041 [claude/sprint-design-acceptance-review-bdf1f8]
/Users/liu/Desktop/FYP2-Constructed-Scenario                                                                   eca99db [fyp2/constructed-scenario]
/Users/liu/Desktop/FYP2-DeepSeek                                                                               7e64c4d [fyp2/ds-review-fixes]
/Users/liu/Desktop/FYP2-Live-System                                                                            7e64c4d [fyp2/live-system]
/Users/liu/Desktop/FYP2-Live-System-backups                                                                    75643ea [fyp2/dataset-replay]

```

### 命令记录：baseline_and_ignore

工作目录：`/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1`。exit code：`0`。

```bash
GIT_OPTIONAL_LOCKS=0 python3 -B - <<'PY'
from pathlib import Path
import subprocess,hashlib,json
root=Path('/Users/liu/Desktop/FYP2-Live-System')
for args in [['git','diff','--exit-code','2745348','HEAD','--','backend','ai/src','frontend/src','scripts'],['git','check-ignore','-v','.superpowers/collab/BOARD.md','.superpowers/collab/codex/preflight_report.md']]:
 p=subprocess.run(args,cwd=root,text=True,capture_output=True);print('COMMAND='+json.dumps(args)+' EXIT_CODE='+str(p.returncode));print(p.stdout,end='');print(p.stderr,end='');assert p.returncode==0
print('tracked_collab_paths='+repr(subprocess.check_output(['git','ls-files','--','.superpowers/collab'],cwd=root,text=True)))
PY
```

当日输出：

```text
COMMAND=["git", "diff", "--exit-code", "2745348", "HEAD", "--", "backend", "ai/src", "frontend/src", "scripts"] EXIT_CODE=0
COMMAND=["git", "check-ignore", "-v", ".superpowers/collab/BOARD.md", ".superpowers/collab/codex/preflight_report.md"] EXIT_CODE=0
/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/.git/info/exclude:8:.superpowers/	.superpowers/collab/BOARD.md
/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/.git/info/exclude:8:.superpowers/	.superpowers/collab/codex/preflight_report.md
tracked_collab_paths=''

```


## Step 2 — 两候选包文件与SHA256

包根：`/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p5_candidates_20261023/`。

| 包 | 文件数 | model.onnx SHA256 | ZIP SHA256 |
|---|---:|---|---|
| `p5_resnet18_search004_seed42_20261023` | 41 | `5e226722e0712824c78aa0976afa6fa5b8dc6100b147a7f523a09048171d8cf3` | `9fb9551f49aeb3582dfc7cb76c9050b7690a8856621944eb363fecd73ea35029` |
| `p5_mobilenet_v3_large_search006_seed42_20261023` | 41 | `9ee60abb78007773cc625af80c313049c1970f63c1f041bed9f5b2539a384828` | `ae887dabe3588969576ecfb54fead41d0f03bd02267028a8a80f73311811ae13` |

必需manifest、model、class_metadata、annotations和saved predictions全部存在。附录逐一对照两个 `artifact_manifest.json`：均 `artifact_manifest_mismatches=[]`。git dirty标记不能直接等同于包损坏；本次工作区包字节与冻结artifact manifest匹配，没有归一化或修复任何CSV。

### 命令记录：artifact_inventory

工作目录：`/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1`。exit code：`0`。

```bash
python3 -B - <<'PY'
from pathlib import Path
import hashlib,json
root=Path('/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p5_candidates_20261023')
for name in ['p5_resnet18_search004_seed42_20261023','p5_mobilenet_v3_large_search006_seed42_20261023']:
 p=root/name
 print('PACKAGE='+str(p))
 for rel in ['runtime_manifest.json','model.onnx','class_metadata.json','evaluation_metrics.json','artifact_manifest.json','predictions_test_clean.csv','validation/stable200_annotations.csv','validation/stable200_saved_predictions.csv','validation/p4a100_parity.json','validation/p4a100_annotations.json','model_card.md']:
  f=p/rel; assert f.is_file(),str(f)
 for f in sorted(p.rglob('*')):
  if f.is_file(): print(hashlib.sha256(f.read_bytes()).hexdigest()+'  '+str(f.relative_to(p)))
 z=root/(name+'.zip');assert z.is_file(),str(z)
 print('ZIP '+hashlib.sha256(z.read_bytes()).hexdigest()+'  '+str(z))
 print('FILE_COUNT='+str(sum(f.is_file() for f in p.rglob('*'))))
PY
```

当日输出：

```text
PACKAGE=/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p5_candidates_20261023/p5_resnet18_search004_seed42_20261023
1bf3e447fa6044fea99b00252468fe9140ddc72af1f49b0b268d0001947dd983  artifact_manifest.json
482081c37db841c93b8bbd49d49144e2bb8f499c6ad3a1a39d17a270b669f963  class_metadata.json
55efdd83aca334764e742ac24b185640f2812f5c0835e56668e03a449eae0e98  evaluation_metrics.json
970037a0e71304614000622c32f1d68bc83046af184bfd6c95d90f1ba342f794  evidence/p4a_environment.json
dc8f7cc36126aa994ae7ffebf9fb06cb92596246484f645f85956e052ddddaa3  evidence/p4a_preflight_attestation.json
e387a114d075841e7350f160541acc55eac325ff6f011717e9e1a1bfe09f6992  evidence/p4b_cached_audit.json
8a98353ccd4f1b20791392df6784e0ba8f92ebb6054cc78233a570ddf94546d3  evidence/p4b_closure_integrity.json
882e64929ae785d3d70cd722495bedb5441e9677d918d56fa75c31a51c3fd73e  evidence/p4b_completion.json
8b45e842875ae1c06fbb66ae2c2c9415384854f91d555c1957a44ef6ffdf0f93  evidence/p4b_protocol.json
8fe94adaa8a18c889e40a6637bae4acec1536abcd1b2fbf2c0775a1ab7c26c27  evidence/p4b_provenance_after.json
3444a6be7930c2ce91355e5cfc16d7115ec9cb8806ddbe64af4469c7bfc8dcaa  evidence/p4b_provenance_before.json
fe9506cc566094b90634ee46b92ea6d5048d9a22f8ba44c65f4ee459bf290831  evidence/p4b_source_manifest.json
0d15d61fa2284ba74bc32907506565ef1ea365310e704073787d17b53cc091ec  evidence/provenance.json
4a329762e21425e773493eebb347739abdc917c6d04ec09b8426795310ce8f85  evidence/selection_log.json
edb22e0b00ceb3b272a5afc22dd50a5d8c212a9ddd861ee0b92cbeef0f674da3  evidence/source_config.json
5688b33bf1e7a02fa7c35cbaf1b5fb4fc9aaee72044e590b5dac76777cf98385  evidence/source_export_attempt.json
94034c235bd5d9242bf23325189a93f3bf5acf58262b29ad1835b79c9a32adbd  evidence/source_export_benchmark_manifest.json
4fc767ccdda73c19f8a92d5590ccf9f5f4f98b3548a4f901a8338b8b5dfa71a8  evidence/source_export_result.json
2e0950aaad156b41cf58042b7fac1230dfbb5066cd0348aa414a9a5e6279e09f  evidence/source_hashes.json
08cbbc25685a4c6a68781ebff2b174f747c68090bb0f24176f8277ee47a9e9de  evidence/source_snapshot/ml/configs/p4_protocol.json
8ede7aa5a0604232ff5b3c54735bd9f2e5479b18a2e80e5091bfa2b07644805d  evidence/source_snapshot/ml/experiments/comparator_common.py
87c7daee65d6e763f5ce80f7a82bdd90d541c74970f7ac89d02221b97911ac68  evidence/source_snapshot/ml/experiments/p4_core.py
ffdfa6637bace58c9818ade3b9a84e812a59d2f681543927b10403061301dece  evidence/source_snapshot/ml/experiments/p4_preflight.py
b52350198c1b13e8d5fde8d48797f984413f6db50091a2b92c2507c18d5a1403  evidence/source_snapshot/ml/experiments/package_candidates.py
2760446943c7067e2a1fb852f6ae1f570ba1e4b997ab5b13711a5bdf5e61a640  evidence/source_snapshot/ml/experiments/run_p4.py
3dee8de808ff1e1840f0fc0bd31d2541105f30b79794f551eecffe3972aeb13d  evidence/source_snapshot/ml/tests/test_candidate_package.py
06c465cb3115dad5f3e5e6a63ab0b308c50e4edca41b538d5b33361d4667b4d9  evidence/source_snapshot/ml/vision/train_hpo.py
e29fbb01ea197d0886684fe67f439eaa4a119871415ba1e92b2fd2df50562827  evidence/source_training_artifact_manifest.json
79dd7aa79b2b510b02e4a4b01ecd7d8c86b55509756c8c411948bda93497e42d  evidence/trial_selection_log.json
5e226722e0712824c78aa0976afa6fa5b8dc6100b147a7f523a09048171d8cf3  model.onnx
1048ae08567e9f4e83a1dc31e413e74140263270da9721c4f72f167e9ac05a1b  model_card.md
6f7e89461922d0711a1a1b9a2c2d4f6c0bc806529bb095ac1a510e102eb95698  predictions_test_clean.csv
91e9ec82fcf04d0400cb2da9f68aecc3286faa132828319d62119622d3d8dfb3  runtime_manifest.json
a677ec9fdc8161b97073b4304bd95a2a2e56d8d0aee2994415cf9274c0a3c785  validation/class_report.json
17e00653eeaa691cad31c811f7a2d7d21954061c485d067fd16757b0c2b9cee9  validation/p4a100_annotations.json
3885dbf8b87120382f0663f1aaad84d715f2c59cbb49f63006740e002c8c8cf9  validation/p4a100_parity.json
aa50283e61d18a0b77224d4d8e9ec6a25b1b4a6e736a271f68cea4ae60d78e8a  validation/predictions_validation.csv
c80146a4c70cb0d90afb39e2eae70df0146ef194676c5349f34961ebf3d820a0  validation/saved_prediction_diagnostic.json
ef33129727fcfabdfc5dcec6dd69ceaea783e9af3480b296b0fba978fa7b39a5  validation/stable200_annotations.csv
c7d233c813a01d54ff286a836e5c6cab069558b52a9ee547953052fc92a0787d  validation/stable200_saved_predictions.csv
3d4668ed94af5212d72370a8503358200fea7f14a3b5d24e0656bb0608045ae6  validation/validation_metrics.json
ZIP 9fb9551f49aeb3582dfc7cb76c9050b7690a8856621944eb363fecd73ea35029  /Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p5_candidates_20261023/p5_resnet18_search004_seed42_20261023.zip
FILE_COUNT=41
PACKAGE=/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p5_candidates_20261023/p5_mobilenet_v3_large_search006_seed42_20261023
985bb308daf521f77db7e17c76cb49fc3e557475b218b520267b344345691252  artifact_manifest.json
482081c37db841c93b8bbd49d49144e2bb8f499c6ad3a1a39d17a270b669f963  class_metadata.json
dacbaa39d87c0cda9e60d4a2d9e2a65898382f8778cdf57ef1092d4ad8bf2d6b  evaluation_metrics.json
970037a0e71304614000622c32f1d68bc83046af184bfd6c95d90f1ba342f794  evidence/p4a_environment.json
dc8f7cc36126aa994ae7ffebf9fb06cb92596246484f645f85956e052ddddaa3  evidence/p4a_preflight_attestation.json
e387a114d075841e7350f160541acc55eac325ff6f011717e9e1a1bfe09f6992  evidence/p4b_cached_audit.json
8a98353ccd4f1b20791392df6784e0ba8f92ebb6054cc78233a570ddf94546d3  evidence/p4b_closure_integrity.json
882e64929ae785d3d70cd722495bedb5441e9677d918d56fa75c31a51c3fd73e  evidence/p4b_completion.json
8b45e842875ae1c06fbb66ae2c2c9415384854f91d555c1957a44ef6ffdf0f93  evidence/p4b_protocol.json
8fe94adaa8a18c889e40a6637bae4acec1536abcd1b2fbf2c0775a1ab7c26c27  evidence/p4b_provenance_after.json
3444a6be7930c2ce91355e5cfc16d7115ec9cb8806ddbe64af4469c7bfc8dcaa  evidence/p4b_provenance_before.json
fe9506cc566094b90634ee46b92ea6d5048d9a22f8ba44c65f4ee459bf290831  evidence/p4b_source_manifest.json
819ed4dc357324b0b4b14dfad01dfd59ddc28e6969c568ad681edc32a7747d67  evidence/provenance.json
4a329762e21425e773493eebb347739abdc917c6d04ec09b8426795310ce8f85  evidence/selection_log.json
b26e39aa1b7fcc388bf0b8744606eda1c80ff7238666403f811c8e00f4d2aa4f  evidence/source_config.json
df36321907f52a0a11425201d36da3fa35e1e88958a21f84611189530da1cf31  evidence/source_export_attempt.json
3dc6cfbcd8ea2ecb24d602864fc1cfa94e2b0c15e5ea4c9774076edfa75fe3d4  evidence/source_export_benchmark_manifest.json
312207a3a8f81ae9bec7bc6357c85b1691f8f8f5b6b96465c9d324df7304f92c  evidence/source_export_result.json
7f596fa9f682d0f21333f6be8a82a5648ddb8ba8a8bc58a67407ba804d32e12a  evidence/source_hashes.json
08cbbc25685a4c6a68781ebff2b174f747c68090bb0f24176f8277ee47a9e9de  evidence/source_snapshot/ml/configs/p4_protocol.json
8ede7aa5a0604232ff5b3c54735bd9f2e5479b18a2e80e5091bfa2b07644805d  evidence/source_snapshot/ml/experiments/comparator_common.py
87c7daee65d6e763f5ce80f7a82bdd90d541c74970f7ac89d02221b97911ac68  evidence/source_snapshot/ml/experiments/p4_core.py
ffdfa6637bace58c9818ade3b9a84e812a59d2f681543927b10403061301dece  evidence/source_snapshot/ml/experiments/p4_preflight.py
b52350198c1b13e8d5fde8d48797f984413f6db50091a2b92c2507c18d5a1403  evidence/source_snapshot/ml/experiments/package_candidates.py
2760446943c7067e2a1fb852f6ae1f570ba1e4b997ab5b13711a5bdf5e61a640  evidence/source_snapshot/ml/experiments/run_p4.py
3dee8de808ff1e1840f0fc0bd31d2541105f30b79794f551eecffe3972aeb13d  evidence/source_snapshot/ml/tests/test_candidate_package.py
06c465cb3115dad5f3e5e6a63ab0b308c50e4edca41b538d5b33361d4667b4d9  evidence/source_snapshot/ml/vision/train_hpo.py
a7f0edb9fddb28585e1fc4a5b39c8ad7557be1d3203aa75f98a8e4fee78a25a7  evidence/source_training_artifact_manifest.json
7d1d265cfe4fc15a3259fa9564e36af33a8d31590444fc6a099bb1799e4bac8b  evidence/trial_selection_log.json
9ee60abb78007773cc625af80c313049c1970f63c1f041bed9f5b2539a384828  model.onnx
33966543b550f94ade4bd142c991214f4ed87f96305dc665f888f1884594e42a  model_card.md
fc7cc292cfb0871373fd226269f429a495d754a1305e06f9d76936585a47d229  predictions_test_clean.csv
32b1a3ecdc6eca9e1c3262f3d247f44795b381c10f977f6c483159f6b6b3a0ec  runtime_manifest.json
70278d506ee0659d5c8b0119b8da0849eccbd22e4774783f7b0326676610a843  validation/class_report.json
17e00653eeaa691cad31c811f7a2d7d21954061c485d067fd16757b0c2b9cee9  validation/p4a100_annotations.json
a8544656b264a5e0698418999c05bf2fe8e869af1b03e24041d2bbf6548fd73b  validation/p4a100_parity.json
5aefbe2ff8758f8f340bce8af953a19f88cbefa3474582c2315434d5465bb67e  validation/predictions_validation.csv
97142950edcbe05c268cb423ecc7e0cfe1e73e054486357e2c8df0b244e11892  validation/saved_prediction_diagnostic.json
ef33129727fcfabdfc5dcec6dd69ceaea783e9af3480b296b0fba978fa7b39a5  validation/stable200_annotations.csv
47fd6f678247c81f6b0384a6453c7467c5b3dd39208647a9847f33807dba74b6  validation/stable200_saved_predictions.csv
56f1c190c30dee8d8bb3b5ff1d11563237bd8b144e5b7ac05e31f4ed1e4ee573  validation/validation_metrics.json
ZIP ae887dabe3588969576ecfb54fead41d0f03bd02267028a8a80f73311811ae13  /Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p5_candidates_20261023/p5_mobilenet_v3_large_search006_seed42_20261023.zip
FILE_COUNT=41

```


## Step 3 — 原样系统CLI校验

目录：`/tmp/task10a-cx0-validator-20261026-t7lct272/`，保留 `backend/app/`、`scripts/` 结构。三份source/copy SHA逐一相等：

| 文件 | source和copy SHA256 |
|---|---|
| `backend/app/runtime_manifest.py` | `f2e4b39ad6708d2feeb110b7308f6a924fe752b9a6e6a48df1927b7e058997ce` |
| `backend/app/runtime_manifest.schema.json` | `db78678d7e00dbb7935e9c122e514957e0a5913857e5ef367353a925a1b59084` |
| `scripts/validate_runtime_manifest.py` | `9b0ed4a0f7369f453768cfdac92e4a1b963eba971f9f5a36b1864becd1055d8a` |

使用Live已有Python与 `-B`，两次均为真实manifest路径加 `--package-dir <真实包>`：**RN/MN各自 `valid / exit0`、stderr空**。这只验证schema和包内模型文件hash，未加载ORT或forward。

### 命令记录：manifest_cli

工作目录：`/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1`。exit code：`0`。

```bash
python3 -B - <<'PY'
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import tempfile,shutil,hashlib,subprocess,os,json
live=Path('/Users/liu/Desktop/FYP2-Live-System')
ml=Path('/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1')
tmp=Path(tempfile.mkdtemp(prefix='task10a-cx0-validator-20261026-',dir='/tmp'))
print('observed_at='+datetime.now(ZoneInfo('Asia/Kuala_Lumpur')).isoformat());print('TEMP_ROOT='+str(tmp))
for rel in ['backend/app/runtime_manifest.py','backend/app/runtime_manifest.schema.json','scripts/validate_runtime_manifest.py']:
 src=live/rel;dst=tmp/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
 a=hashlib.sha256(src.read_bytes()).hexdigest();b=hashlib.sha256(dst.read_bytes()).hexdigest();print('COPY '+rel+' source_sha256='+a+' copied_sha256='+b+' equal='+str(a==b));assert a==b
for name in ['p5_resnet18_search004_seed42_20261023','p5_mobilenet_v3_large_search006_seed42_20261023']:
 pkg=ml/'ml/outputs/runs/p5_candidates_20261023'/name
 command=[str(live/'.venv/bin/python'),'-B',str(tmp/'scripts/validate_runtime_manifest.py'),str(pkg/'runtime_manifest.json'),'--package-dir',str(pkg)]
 p=subprocess.run(command,cwd=tmp,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'},capture_output=True,text=True)
 print('COMMAND='+json.dumps(command));print('EXIT_CODE='+str(p.returncode));print('STDOUT='+p.stdout.strip());print('STDERR='+p.stderr.strip());assert p.returncode==0
print('NO_MODEL_LOADED; TEMP_DIRECTORY_PRESERVED')
PY
```

当日输出：

```text
observed_at=2026-10-26T12:29:02.206807+08:00
TEMP_ROOT=/tmp/task10a-cx0-validator-20261026-t7lct272
COPY backend/app/runtime_manifest.py source_sha256=f2e4b39ad6708d2feeb110b7308f6a924fe752b9a6e6a48df1927b7e058997ce copied_sha256=f2e4b39ad6708d2feeb110b7308f6a924fe752b9a6e6a48df1927b7e058997ce equal=True
COPY backend/app/runtime_manifest.schema.json source_sha256=db78678d7e00dbb7935e9c122e514957e0a5913857e5ef367353a925a1b59084 copied_sha256=db78678d7e00dbb7935e9c122e514957e0a5913857e5ef367353a925a1b59084 equal=True
COPY scripts/validate_runtime_manifest.py source_sha256=9b0ed4a0f7369f453768cfdac92e4a1b963eba971f9f5a36b1864becd1055d8a copied_sha256=9b0ed4a0f7369f453768cfdac92e4a1b963eba971f9f5a36b1864becd1055d8a equal=True
COMMAND=["/Users/liu/Desktop/FYP2-Live-System/.venv/bin/python", "-B", "/tmp/task10a-cx0-validator-20261026-t7lct272/scripts/validate_runtime_manifest.py", "/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p5_candidates_20261023/p5_resnet18_search004_seed42_20261023/runtime_manifest.json", "--package-dir", "/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p5_candidates_20261023/p5_resnet18_search004_seed42_20261023"]
EXIT_CODE=0
STDOUT=valid
STDERR=
COMMAND=["/Users/liu/Desktop/FYP2-Live-System/.venv/bin/python", "-B", "/tmp/task10a-cx0-validator-20261026-t7lct272/scripts/validate_runtime_manifest.py", "/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p5_candidates_20261023/p5_mobilenet_v3_large_search006_seed42_20261023/runtime_manifest.json", "--package-dir", "/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p5_candidates_20261023/p5_mobilenet_v3_large_search006_seed42_20261023"]
EXIT_CODE=0
STDOUT=valid
STDERR=
NO_MODEL_LOADED; TEMP_DIRECTORY_PRESERVED

```


## Step 4 — stable200原图、构成与成员哈希

数据根是单横线目录：
`/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment-/state-farm-distracted-driver-detection/imgs/train/<class_id>/<filename>`。

- 两包annotations逐项相同；200个唯一source_id；c0..c9各20；split全部val。
- 原始metadata val行按各类filename排序取20，与annotations顺序一致。
- 原JPEG **200/200** 存在、可读且有JPEG文件头，缺失路径 `[]`。未解码/重编码或执行模型；最大原JPEG为 `51318` bytes，文件存在检查不是forward验收。
- 冻结成员hash规则为 `sha256("\n".join(sorted(filename)).encode("utf-8"))`，**无末尾换行**，不是CSV字节hash，也不是source_id hash。
- 重算：`601dc3ed6b99e9030f6eb5287e711baf529ea6c0c5b2facab0acd9c3f9373be9`，与两manifest一致。
- 额外source_id成员hash：`2697d288e384f340cb51f002ce39fca024827c6969de9dc9f2db9682246c5d75`。
- 原metadata SHA：`b4f8e90dec769bb419eaa490aea869668bed6484089cebe4d545c7667baa8ea4`，与源config保护记录相同。
- 为Stage-2草案额外钉住200图各自原JPEG字节SHA；聚合为 `4393095e7fd619b7df5cae8e7b4c020e29cb874af0f4ab4bee2198c5ad59eb3c`。每图hash见协议 `input_set.ordered_samples`。这是今日只读输入身份固定，不是历史模型实验结果；runner须在运行前复算，任何缺失或不符写确切路径。

### 命令记录：stable200_inputs

工作目录：`/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1`。exit code：`0`。

```bash
python3 -B - <<'PY'
from pathlib import Path
import csv,json,hashlib,collections
ml=Path('/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1')
base=ml/'ml/outputs/runs/p5_candidates_20261023'
names=['p5_resnet18_search004_seed42_20261023','p5_mobilenet_v3_large_search006_seed42_20261023']
a=list(csv.DictReader((base/names[0]/'validation/stable200_annotations.csv').open()))
b=list(csv.DictReader((base/names[1]/'validation/stable200_annotations.csv').open()))
assert a==b and len(a)==200 and len({x['source_id'] for x in a})==200
root=Path('/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment-')
meta=root/'eda_outputs/processed/vision/vision_metadata_with_split.csv'
rows=list(csv.DictReader(meta.open()));selected=[]
for c in [f'c{i}' for i in range(10)]:
 selected.extend(sorted((r for r in rows if r['split']=='val' and r['class_id']==c),key=lambda r:r['filename'])[:20])
assert [(r['class_id'],r['filename']) for r in a]==[(r['class_id'],r['filename']) for r in selected]
member=hashlib.sha256('\n'.join(sorted(r['filename'] for r in a)).encode('utf-8')).hexdigest()
source_hash=hashlib.sha256('\n'.join(sorted(r['source_id'] for r in a)).encode('utf-8')).hexdigest()
expected='601dc3ed6b99e9030f6eb5287e711baf529ea6c0c5b2facab0acd9c3f9373be9'
assert member==expected
images=[];missing=[]
for row in a:
 f=root/'state-farm-distracted-driver-detection/imgs/train'/row['class_id']/row['filename']
 if not f.is_file():missing.append(str(f));continue
 raw=f.read_bytes();assert raw[:2]==b'\xff\xd8',str(f)
 images.append(dict(source_id=row['source_id'],class_id=row['class_id'],filename=row['filename'],path=str(f),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
byte_hash=hashlib.sha256('\n'.join(x['source_id']+'\t'+x['sha256'] for x in sorted(images,key=lambda x:x['source_id'])).encode('utf-8')).hexdigest()
report=dict(n=len(a),present=len(images),missing=missing,split_counts=dict(collections.Counter(x['split'] for x in a)),class_counts=dict(collections.Counter(x['class_id'] for x in a)),annotations_equal=True,top20_rule_matches_metadata=True,metadata_path=str(meta),metadata_sha256=hashlib.sha256(meta.read_bytes()).hexdigest(),membership_sha256=member,source_ids_sha256=source_hash,image_bytes_manifest_sha256=byte_hash,images=images)
print(json.dumps(report,ensure_ascii=False,sort_keys=True))
assert not missing
PY
```

当日输出：

```text
{
  "annotations_equal": true,
  "class_counts": {
    "c0": 20,
    "c1": 20,
    "c2": 20,
    "c3": 20,
    "c4": 20,
    "c5": 20,
    "c6": 20,
    "c7": 20,
    "c8": 20,
    "c9": 20
  },
  "image_bytes_manifest_sha256": "4393095e7fd619b7df5cae8e7b4c020e29cb874af0f4ab4bee2198c5ad59eb3c",
  "membership_sha256": "601dc3ed6b99e9030f6eb5287e711baf529ea6c0c5b2facab0acd9c3f9373be9",
  "metadata_path": "/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment-/eda_outputs/processed/vision/vision_metadata_with_split.csv",
  "metadata_sha256": "b4f8e90dec769bb419eaa490aea869668bed6484089cebe4d545c7667baa8ea4",
  "missing": [],
  "n": 200,
  "present": 200,
  "source_ids_sha256": "2697d288e384f340cb51f002ce39fca024827c6969de9dc9f2db9682246c5d75",
  "split_counts": {
    "val": 200
  },
  "top20_rule_matches_metadata": true
}
```


## Step 5 — provider / XGB untouched基线

在Live root运行，`git diff 2745348 -- backend/app/providers/trained.py` **exit0且stdout/stderr空**。标准git diff的exit0本身不足以证明无差异，这里实际输出确实为空；另有Step1的运行代码 `--exit-code` 核对。未读取ML工作区provider来代替Live provider。

### 命令记录：xgb_baseline

工作目录：`/Users/liu/Desktop/FYP2-Live-System`。exit code：`0`。

```bash
GIT_OPTIONAL_LOCKS=0 git diff 2745348 -- backend/app/providers/trained.py
```

当日输出：

```text
(stdout/stderr 为空)
```


## Step 6 — 结论与后续限制

**GO**：Phase0所需两个包、原样CLI、200张原图、成员身份和provider基线全部符合，没有缺失必需依赖。HEAD变化已记录，且Live运行代码对2745348无差异；不因文档提交漂移阻塞依赖预检。

仍未执行或批准：

- `provider_load_forward=NOT_RUN`；`official_stable200_behavior=NOT_RUN`。
- 候选系统准入仍需系统轨道实现、当日forward证据、门禁和独立审计；本报告不宣称Stage1通过。
- 数值容差 `FOR_USER_DECISION`；Stage-2协议 `DRAFT`、`execution_authorized=false`。
- 没有重跑全量测试；C-7的pytest1046/vitest954为既有基线，不能列为今日通过计数。

## 附录A — 参照与预处理事实核查

两项重要纠正：

1. P4A三模型中最大概率误差为MN-HPO42的 `6.364584130613693e-6`；分析U-1的4.85e-6只适用于MN-STABLE。
2. 冻结源码把ORT `actual` 单图logits写入 `result.validation_predictions`。候选stable200 CSV才是P3 PyTorch MPS验证输出。容差文件据实区分，仍使用C-3指定参照，不新建缓存或重跑实验。

三个模型各自P4A100来源图也全部存在。下列环境版本由Live `.venv`读取；历史P4A100/211、历史PyTorch诊断和未来fresh provider forward分开记述。

### 命令记录：parity_summary

工作目录：`/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1`。exit code：`0`。

```bash
python3 -B - <<'PY'
from pathlib import Path
import json,csv,hashlib
r=Path('/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1')
for tag in ['MN-STABLE','RN-HPO42','MN-HPO42']:
 p=r/'ml/outputs/runs/p4a_20261021'/('parity_'+tag+'.json');d=json.loads(p.read_text());v=d['result']
 print(tag,'sha256='+hashlib.sha256(p.read_bytes()).hexdigest(),'status='+d['status'])
 print(json.dumps({k:v[k] for k in ['status','atol','rtol','argmax_equal','samples_compared','max_absolute_error','max_relative_error','max_probability_error','tensor_sha256']}))
 print('n_validation_predictions='+str(len(v['validation_predictions'])),'first='+json.dumps(v['validation_predictions'][0]))
 print('batch_sizes='+str(sorted(set(x['N'] for x in v['batches']))))
for name in ['p5_resnet18_search004_seed42_20261023','p5_mobilenet_v3_large_search006_seed42_20261023']:
 p=r/'ml/outputs/runs/p5_candidates_20261023'/name
 bad=[rel for rel,info in json.loads((p/'artifact_manifest.json').read_text())['files'].items() if hashlib.sha256((p/rel).read_bytes()).hexdigest()!=info['sha256']]
 print(name,'artifact_manifest_mismatches='+str(bad));assert not bad
 print('source_data_root='+json.loads((p/'evidence/source_config.json').read_text())['context']['data_root'])
 print('stable200_prediction_columns='+','.join(next(csv.reader((p/'validation/stable200_saved_predictions.csv').open()))))
PY
```

当日输出：

```text
MN-STABLE sha256=bcecf7d0afcafa48213c0a4f9b85eb6f56ea05e5f463e24881cdf914888af0f8 status=COMPLETED
{"status": "PASS", "atol": 0.0001, "rtol": 0.0001, "argmax_equal": true, "samples_compared": 211, "max_absolute_error": 5.340576171875e-05, "max_relative_error": 0.028853119979840615, "max_probability_error": 4.846009571957133e-06, "tensor_sha256": "07adb0f1a37281659c298bb79e5404fa770cdea511d5ccb99710966b48a8d42e"}
n_validation_predictions=100 first={"source_id": "vision-v1:c0/img_80662.jpg", "class_id": "c0", "driver_id": "p002", "predicted_class": "c0", "logits": [2.8743414878845215, -0.979302704334259, 0.19819563627243042, -3.8070662021636963, -6.41811990737915, 1.203446388244629, -3.342104196548462, -0.2658499777317047, 1.7205744981765747, 0.08084650337696075]}
batch_sizes=[1, 2, 4, 9, 32]
RN-HPO42 sha256=3885dbf8b87120382f0663f1aaad84d715f2c59cbb49f63006740e002c8c8cf9 status=COMPLETED
{"status": "PASS", "atol": 0.0001, "rtol": 0.0001, "argmax_equal": true, "samples_compared": 211, "max_absolute_error": 1.9073486328125e-05, "max_relative_error": 0.0010744780693894122, "max_probability_error": 2.302238954254854e-06, "tensor_sha256": "07adb0f1a37281659c298bb79e5404fa770cdea511d5ccb99710966b48a8d42e"}
n_validation_predictions=100 first={"source_id": "vision-v1:c0/img_80662.jpg", "class_id": "c0", "driver_id": "p002", "predicted_class": "c0", "logits": [1.8442738056182861, -1.4782376289367676, -1.4677212238311768, -0.07381501793861389, -0.46478646993637085, 1.088822603225708, -0.9748008251190186, -1.1025350093841553, 1.6058752536773682, -0.03126772120594978]}
batch_sizes=[1, 2, 4, 9, 32]
MN-HPO42 sha256=a8544656b264a5e0698418999c05bf2fe8e869af1b03e24041d2bbf6548fd73b status=COMPLETED
{"status": "PASS", "atol": 0.0001, "rtol": 0.0001, "argmax_equal": true, "samples_compared": 211, "max_absolute_error": 4.100799560546875e-05, "max_relative_error": 0.000533180907544042, "max_probability_error": 6.364584130613693e-06, "tensor_sha256": "07adb0f1a37281659c298bb79e5404fa770cdea511d5ccb99710966b48a8d42e"}
n_validation_predictions=100 first={"source_id": "vision-v1:c0/img_80662.jpg", "class_id": "c0", "driver_id": "p002", "predicted_class": "c0", "logits": [5.166218280792236, -0.5994257926940918, -3.659421920776367, -1.1543395519256592, -1.8691457509994507, 0.10270586609840393, -4.314615249633789, -3.313530921936035, -0.917310357093811, 2.8115789890289307]}
batch_sizes=[1, 2, 4, 9, 32]
p5_resnet18_search004_seed42_20261023 artifact_manifest_mismatches=[]
source_data_root=/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment-
stable200_prediction_columns=source_id,true_label_index,predicted_label_index,logit_c0,probability_c0,logit_c1,probability_c1,logit_c2,probability_c2,logit_c3,probability_c3,logit_c4,probability_c4,logit_c5,probability_c5,logit_c6,probability_c6,logit_c7,probability_c7,logit_c8,probability_c8,logit_c9,probability_c9
p5_mobilenet_v3_large_search006_seed42_20261023 artifact_manifest_mismatches=[]
source_data_root=/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment-
stable200_prediction_columns=source_id,true_label_index,predicted_label_index,logit_c0,probability_c0,logit_c1,probability_c1,logit_c2,probability_c2,logit_c3,probability_c3,logit_c4,probability_c4,logit_c5,probability_c5,logit_c6,probability_c6,logit_c7,probability_c7,logit_c8,probability_c8,logit_c9,probability_c9

```

### 命令记录：reference_dependencies

工作目录：`/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1`。exit code：`0`。

```bash
/Users/liu/Desktop/FYP2-Live-System/.venv/bin/python -B - <<'PY'
from pathlib import Path
import hashlib,json,csv,collections,importlib.metadata
ml=Path('/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1');live=Path('/Users/liu/Desktop/FYP2-Live-System')
for root in [live,ml]:
 for rel in ['ml/outputs/vision/mobilenetv3_large_vision.onnx','ml/outputs/vision/metrics.json','ml/outputs/telemetry/xgb_telemetry.json','ml/outputs/telemetry/metrics.json']:
  p=root/rel;print('ARTIFACT',str(p),'sha256='+hashlib.sha256(p.read_bytes()).hexdigest(),'symlink='+str(p.is_symlink()))
 print('VENV',str(root/'.venv'),'resolved='+str((root/'.venv').resolve()))
for tag in ['MN-STABLE','RN-HPO42','MN-HPO42']:
 p=ml/'ml/outputs/runs/p4a_20261021'/('parity_'+tag+'.json');d=json.loads(p.read_text());rows=d['result']['validation_predictions'];missing=[]
 for row in rows:
  f=Path('/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment-/state-farm-distracted-driver-detection/imgs/train')/row['source_id'].removeprefix('vision-v1:')
  if not f.is_file():missing.append(str(f))
 print('P4A100',tag,'unique='+str(len({x['source_id'] for x in rows})),'class_counts='+json.dumps(dict(collections.Counter(x['class_id'] for x in rows))),'missing='+json.dumps(missing));assert not missing
for name in ['p5_resnet18_search004_seed42_20261023','p5_mobilenet_v3_large_search006_seed42_20261023']:
 p=ml/'ml/outputs/runs/p5_candidates_20261023'/name
 d=json.loads((p/'validation/saved_prediction_diagnostic.json').read_text())
 print('SAVED_DIAGNOSTIC',name,'all_unique_modes_equal_label='+str(d['all_unique_modes_equal_label']),'per_class='+json.dumps({k:{'modes':v['modes'],'unique_mode_equals_label':v['unique_mode_equals_label']} for k,v in d['per_class'].items()}))
print('EXECUTION_SPEC_DATA_ROOT='+json.loads((ml/'ml/outputs/runs/p4b_20261022/execution_spec.json').read_text())['data_root'])
p=live/'ai/prototype-data/prepared_sessions/session_001/telemetry.csv';rows=list(csv.DictReader(p.open()));features=['speed_kmph','accel_x','accel_y','brake_pressure','steering_angle','throttle','lane_deviation','headway_distance']
raw={k:float(rows[0][k]) for k in features};canonical=json.dumps(raw,sort_keys=True,separators=(',',':'),ensure_ascii=False)
print('TELEMETRY_FILE_SHA256='+hashlib.sha256(p.read_bytes()).hexdigest());print('TELEMETRY_FIXED_ROW='+canonical);print('TELEMETRY_FIXED_ROW_SHA256='+hashlib.sha256(canonical.encode()).hexdigest())
for package in ['pillow','numpy','torch','torchvision','onnxruntime','jsonschema']:
 print('ENV',package,importlib.metadata.version(package))
PY
```

当日输出：

```text
ARTIFACT /Users/liu/Desktop/FYP2-Live-System/ml/outputs/vision/mobilenetv3_large_vision.onnx sha256=b3a42e8dd4553355b1fd7d9e7fe3d28e318decb894e76eb029489b7ff2e90bcf symlink=True
ARTIFACT /Users/liu/Desktop/FYP2-Live-System/ml/outputs/vision/metrics.json sha256=d32cc94aeae02f2b7068b0de1aab0e1cb698c3f7ce9c5c85cebd9cd05bf5636f symlink=False
ARTIFACT /Users/liu/Desktop/FYP2-Live-System/ml/outputs/telemetry/xgb_telemetry.json sha256=9802cb06ca98f0c1befaf851fa7668cfec70e005cf8bb3884e49d7d45d7aec07 symlink=True
ARTIFACT /Users/liu/Desktop/FYP2-Live-System/ml/outputs/telemetry/metrics.json sha256=620cbafd652463766641e4e26839593112be4dd8066e6089a163ebb663b70f22 symlink=False
VENV /Users/liu/Desktop/FYP2-Live-System/.venv resolved=/Users/liu/Desktop/FYP2-Live-System/.venv
ARTIFACT /Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/vision/mobilenetv3_large_vision.onnx sha256=b3a42e8dd4553355b1fd7d9e7fe3d28e318decb894e76eb029489b7ff2e90bcf symlink=False
ARTIFACT /Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/vision/metrics.json sha256=d32cc94aeae02f2b7068b0de1aab0e1cb698c3f7ce9c5c85cebd9cd05bf5636f symlink=False
ARTIFACT /Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/telemetry/xgb_telemetry.json sha256=9802cb06ca98f0c1befaf851fa7668cfec70e005cf8bb3884e49d7d45d7aec07 symlink=False
ARTIFACT /Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/telemetry/metrics.json sha256=620cbafd652463766641e4e26839593112be4dd8066e6089a163ebb663b70f22 symlink=False
VENV /Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/.venv resolved=/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/.venv
P4A100 MN-STABLE unique=100 class_counts={"c0": 10, "c1": 10, "c2": 10, "c3": 10, "c4": 10, "c5": 10, "c6": 10, "c7": 10, "c8": 10, "c9": 10} missing=[]
P4A100 RN-HPO42 unique=100 class_counts={"c0": 10, "c1": 10, "c2": 10, "c3": 10, "c4": 10, "c5": 10, "c6": 10, "c7": 10, "c8": 10, "c9": 10} missing=[]
P4A100 MN-HPO42 unique=100 class_counts={"c0": 10, "c1": 10, "c2": 10, "c3": 10, "c4": 10, "c5": 10, "c6": 10, "c7": 10, "c8": 10, "c9": 10} missing=[]
SAVED_DIAGNOSTIC p5_resnet18_search004_seed42_20261023 all_unique_modes_equal_label=True per_class={"c0": {"modes": [0], "unique_mode_equals_label": true}, "c1": {"modes": [1], "unique_mode_equals_label": true}, "c2": {"modes": [2], "unique_mode_equals_label": true}, "c3": {"modes": [3], "unique_mode_equals_label": true}, "c4": {"modes": [4], "unique_mode_equals_label": true}, "c5": {"modes": [5], "unique_mode_equals_label": true}, "c6": {"modes": [6], "unique_mode_equals_label": true}, "c7": {"modes": [7], "unique_mode_equals_label": true}, "c8": {"modes": [8], "unique_mode_equals_label": true}, "c9": {"modes": [9], "unique_mode_equals_label": true}}
SAVED_DIAGNOSTIC p5_mobilenet_v3_large_search006_seed42_20261023 all_unique_modes_equal_label=True per_class={"c0": {"modes": [0], "unique_mode_equals_label": true}, "c1": {"modes": [1], "unique_mode_equals_label": true}, "c2": {"modes": [2], "unique_mode_equals_label": true}, "c3": {"modes": [3], "unique_mode_equals_label": true}, "c4": {"modes": [4], "unique_mode_equals_label": true}, "c5": {"modes": [5], "unique_mode_equals_label": true}, "c6": {"modes": [6], "unique_mode_equals_label": true}, "c7": {"modes": [7], "unique_mode_equals_label": true}, "c8": {"modes": [8], "unique_mode_equals_label": true}, "c9": {"modes": [9], "unique_mode_equals_label": true}}
EXECUTION_SPEC_DATA_ROOT=/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment-
TELEMETRY_FILE_SHA256=3be8432a0ed36ac62989af9c6e04b69121e4ed6a3eb568ab4389a76687724f7e
TELEMETRY_FIXED_ROW={"accel_x":0.3,"accel_y":0.1,"brake_pressure":12.0,"headway_distance":26.0,"lane_deviation":0.3,"speed_kmph":34.0,"steering_angle":-2.0,"throttle":30.0}
TELEMETRY_FIXED_ROW_SHA256=0d9e4d8d116ee48f0288bbd8b714e8edeb9d5442937104119f9369b9043fd58b
ENV pillow 12.2.0
ENV numpy 2.4.6
ENV torch 2.12.0
ENV torchvision 0.27.0
ENV onnxruntime 1.26.0
ENV jsonschema 4.26.0

```

### 命令记录：source_audit

工作目录：`/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1`。exit code：`0`。

```bash
python3 -B - <<'PY'
from pathlib import Path
import hashlib,json,subprocess
ml=Path('/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1');live=Path('/Users/liu/Desktop/FYP2-Live-System')
refs=[(live/'backend/app/providers/trained.py',94,116),(ml/'ml/experiments/comparator_common.py',114,120),(ml/'ml/vision/train_hpo.py',60,70),(ml/'ml/vision/train_hpo.py',120,127),(ml/'ml/vision/train_hpo.py',160,173),(ml/'ml/outputs/runs/p4a_20261021/source_snapshot/ml/experiments/p4_preflight.py',108,134),(ml/'ml/outputs/runs/p4a_20261021/source_snapshot/ml/experiments/p4_preflight.py',426,440),(ml/'ml/outputs/runs/p5_candidates_20261023/p5_resnet18_search004_seed42_20261023/evidence/source_snapshot/ml/experiments/package_candidates.py',196,222)]
for p,start,end in refs:
 print('SOURCE='+str(p)+' sha256='+hashlib.sha256(p.read_bytes()).hexdigest())
 for i,line in enumerate(p.read_text().splitlines(),1):
  if start<=i<=end:print(str(i)+': '+line)
for tag in ['MN-STABLE','RN-HPO42','MN-HPO42']:
 p=ml/'ml/outputs/runs/p4a_20261021'/('parity_'+tag+'.json');d=json.loads(p.read_text());print('P4A_SOURCE_BINDING '+tag+' '+json.dumps(d['source_sha256'],sort_keys=True))
PY
```

当日输出：

```text
SOURCE=/Users/liu/Desktop/FYP2-Live-System/backend/app/providers/trained.py sha256=a240d77aaa2bfff1bf726dd4ae814e4c1078e2ab60023124214736877a136e2f
94:     @staticmethod
95:     def preprocess(encoded):
96:         import numpy as np
97:         from PIL import Image, UnidentifiedImageError
98:         if encoded.startswith("data:"):
99:             if not encoded.startswith(("data:image/jpeg;base64,", "data:image/png;base64,")):
100:                 raise InvalidFrame("Only JPEG/PNG frames are supported")
101:             encoded = encoded.split(",", 1)[1]
102:         try:
103:             raw = base64.b64decode(encoded, validate=True)
104:             if len(raw) > 2_000_000:
105:                 raise InvalidFrame("Frame exceeds 2 MB")
106:             with Image.open(io.BytesIO(raw)) as image:
107:                 if image.format not in ("JPEG", "PNG") or max(image.size) > 4096 or min(image.size) < 16:
108:                     raise InvalidFrame("Expected JPEG/PNG image between 16 and 4096 pixels per side")
109:                 image = image.convert("RGB").resize((224, 224), Image.Resampling.BILINEAR)
110:                 values = np.asarray(image, dtype=np.float32) / 255.0
111:         except (binascii.Error, UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
112:             raise InvalidFrame("Invalid or damaged image") from exc
113:         values = (values - np.array([0.485, 0.456, 0.406], np.float32)) / np.array([0.229, 0.224, 0.225], np.float32)
114:         return np.ascontiguousarray(values.transpose(2, 0, 1)[None])
115: 
116:     def infer(self, data: LiveInput):
SOURCE=/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/experiments/comparator_common.py sha256=8ede7aa5a0604232ff5b3c54735bd9f2e5479b18a2e80e5091bfa2b07644805d
114: 
115: def vision_transforms(training=False):
116:     from torchvision import transforms
117:     operations = [transforms.Resize((224, 224))]
118:     if training:
119:         operations.extend([transforms.RandomRotation(8), transforms.ColorJitter(brightness=0.2, contrast=0.2)])
120:     return transforms.Compose([*operations, transforms.ToTensor(), transforms.Normalize(MEAN, STD)])
SOURCE=/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/vision/train_hpo.py sha256=06c465cb3115dad5f3e5e6a63ab0b308c50e4edca41b538d5b33361d4667b4d9
60: 
61:     class Frames(Dataset):
62:         def __init__(self,frame,training):self.frame=frame;self.transform=common.vision_transforms(training)
63:         def __len__(self):return len(self.frame)
64:         def __getitem__(self,index):
65:             check();row=self.frame.iloc[index]
66:             with Image.open(row.image_path) as image:values=self.transform(image.convert('RGB'))
67:             return values,class_to_idx[row.class_id]
68: 
69:     def architecture():
70:         if plan['model']=='resnet18':
SOURCE=/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/vision/train_hpo.py sha256=06c465cb3115dad5f3e5e6a63ab0b308c50e4edca41b538d5b33361d4667b4d9
120:             model.eval();val_start=time.monotonic();all_logits=[];all_labels=[]
121:             epoch_reload_input=epoch_reload_reference=None
122:             with torch.inference_mode():
123:                 for step,(inputs,labels) in enumerate(val_loader,1):
124:                     check();started=time.monotonic();logits=model(inputs.to('mps')).cpu();torch.mps.synchronize();memory()
125:                     if not torch.isfinite(logits).all():raise ValueError('Non-finite validation logits')
126:                     if epoch_reload_input is None:epoch_reload_input=inputs[:16].clone();epoch_reload_reference=logits[:16].clone()
127:                     all_logits.append(logits);all_labels.append(labels)
SOURCE=/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/vision/train_hpo.py sha256=06c465cb3115dad5f3e5e6a63ab0b308c50e4edca41b538d5b33361d4667b4d9
160:     np.save(directory/'probabilities_validation.npy',best_probabilities,allow_pickle=False)
161:     predictions=pd.DataFrame({'source_id':[f'vision-v1:{r.class_id}/{r.filename}' for r in validation.itertuples()],
162:                               'true_label_index':best_labels,'predicted_label_index':best_probabilities.argmax(1)})
163:     for i,label in enumerate(common.CLASSES):predictions[f'logit_{label}']=best_logits[:,i];predictions[f'probability_{label}']=best_probabilities[:,i]
164:     predictions.to_csv(directory/'predictions_validation.csv',index=False)
165:     metrics=common.diagnostics(best_labels,best_probabilities,common.CLASSES);report=metrics.pop('class_report')
166:     metrics.update(status='COMPLETED',interpretation='NON_COMPARATIVE_PROBE' if phase=='probe' else 'FORMAL_VALIDATION_ONLY',
167:                    formal_comparison_valid=phase!='probe',counts_toward_hpo=phase=='search',best_epoch=best_epoch,epochs=epochs,
168:                    epochs_completed=len(epochs),train_samples=len(training),validation_samples=len(validation),batch_size=64,
169:                    device='mps',threads=2,workers=0,cosine_T_max=8,early_stopping_patience=2,
170:                    reload_verified=True,reload_samples=len(reload_input),reload_max_abs_logit_difference=difference,
171:                    all_losses_and_probabilities_finite=True,test_predictions=0,test_images_opened=0,
172:                    mps_bitwise_reproducibility_guaranteed=False,resource_usage=common.resource_usage(),
173:                    mps_max_observed_allocated_bytes=peak_mps_allocated,mps_max_observed_driver_bytes=peak_mps_driver,
SOURCE=/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4a_20261021/source_snapshot/ml/experiments/p4_preflight.py sha256=ffdfa6637bace58c9818ade3b9a84e812a59d2f681543927b10403061301dece
108: def check_parity(bank, reference, runtime):
109:     if len(bank) != 100:
110:         raise ValueError('Parity requires exactly validation100')
111:     plan = [bank[i:i + 1] for i in range(100)]
112:     plan += [bank[i:i + 32] for i in range(0, 100, 32)] + [bank[:2], bank[:9]]
113:     maximum_abs = maximum_relative = maximum_probability = 0.0
114:     records, single_predictions = [], []
115:     for index, batch in enumerate(plan):
116:         expected = logits(reference(batch), len(batch))
117:         actual = logits(runtime(batch), len(batch))
118:         error = np.abs(actual.astype(np.float64) - expected.astype(np.float64))
119:         if np.any(error > 1e-4 + 1e-4 * np.abs(expected)) or not np.array_equal(actual.argmax(1), expected.argmax(1)):
120:             raise ValueError(f'ONNX parity failure in batch {index}, N={len(batch)}')
121:         absolute = float(error.max())
122:         relative = float((error / np.maximum(np.abs(expected), np.finfo(np.float32).tiny)).max())
123:         probability = float(np.abs(softmax(actual) - softmax(expected)).max())
124:         maximum_abs = max(maximum_abs, absolute)
125:         maximum_relative = max(maximum_relative, relative)
126:         maximum_probability = max(maximum_probability, probability)
127:         records.append({'batch': index, 'N': len(batch), 'max_absolute_error': absolute,
128:                         'max_relative_error': relative, 'max_probability_error': probability})
129:         if index < 100:
130:             single_predictions.append(actual)
131:     return {'status': 'PASS', 'atol': 1e-4, 'rtol': 1e-4, 'argmax_equal': True,
132:             'samples_compared': 211, 'max_absolute_error': maximum_abs,
133:             'max_relative_error': maximum_relative, 'max_probability_error': maximum_probability,
134:             'batches': records}, np.concatenate(single_predictions)
SOURCE=/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4a_20261021/source_snapshot/ml/experiments/p4_preflight.py sha256=ffdfa6637bace58c9818ade3b9a84e812a59d2f681543927b10403061301dece
426: def parity_model(run, identity):
427:     import torch
428:     bank = load_bank(run / 'validation')
429:     model = torch_model(identity, run)
430:     session = ort_session(onnx_path(identity, run))
431:     def reference(batch):
432:         with torch.inference_mode():
433:             return model(torch.from_numpy(batch.copy())).numpy()
434:     report, predictions = check_parity(bank, reference, lambda x: session.run(['logits'], {'input': x})[0])
435:     records = json.loads((run / 'validation/validation_manifest.json').read_text())['records']
436:     report['validation_predictions'] = [dict(source_id=r['source_id'], class_id=r['class_id'], driver_id=r['driver_id'],
437:         predicted_class=CLASSES[int(logit.argmax())], logits=logit.tolist()) for r, logit in zip(records, predictions)]
438:     report['identity'] = identity
439:     report['tensor_sha256'] = hashlib.sha256(bank.tobytes()).hexdigest()
440:     if hashlib.sha256(load_bank(run / 'validation').tobytes()).hexdigest() != report['tensor_sha256']:
SOURCE=/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p5_candidates_20261023/p5_resnet18_search004_seed42_20261023/evidence/source_snapshot/ml/experiments/package_candidates.py sha256=b52350198c1b13e8d5fde8d48797f984413f6db50091a2b92c2507c18d5a1403
196: def stable_smoke(metadata_rows, validation_predictions, per_class=20):
197:     annotations = []
198:     for class_id in CLASSES:
199:         rows = sorted((r for r in metadata_rows if r['split'] == 'val' and r['class_id'] == class_id), key=lambda r: r['filename'])[:per_class]
200:         if len(rows) != per_class: raise ValueError("Incomplete validation smoke class")
201:         annotations += [{"source_id": f"vision-v1:{class_id}/{r['filename']}", "filename": r['filename'], "class_id": class_id,
202:                          "true_label_index": CLASS_TO_IDX[class_id], "training_label": r['class_name'], "driver_id": r['driver_id'], "split": "val"} for r in rows]
203:     predictions = {r['source_id']: r for r in validation_predictions}
204:     if len(predictions) != len(validation_predictions): raise ValueError("Duplicate validation predictions")
205:     selected = []
206:     for row in annotations:
207:         pred = predictions.get(row['source_id'])
208:         if pred is None or int(pred['true_label_index']) != row['true_label_index']:
209:             raise ValueError("Missing/misaligned saved validation prediction")
210:         selected.append(pred)
211:     modes = {}
212:     for i, class_id in enumerate(CLASSES):
213:         counts = Counter(int(p['predicted_label_index']) for a, p in zip(annotations, selected) if a['class_id'] == class_id)
214:         winners = sorted(k for k, v in counts.items() if v == max(counts.values()))
215:         modes[class_id] = {"count": sum(counts.values()), "predicted_counts": dict(counts), "modes": winners,
216:                            "unique_mode_equals_label": winners == [i]}
217:     return annotations, selected, {"scope": "SAVED_VALIDATION_PREDICTION_DIAGNOSTIC", "n": len(annotations),
218:         "filename_sha256": hashlib.sha256("\n".join(sorted(r['filename'] for r in annotations)).encode()).hexdigest(),
219:         "source_ids_sha256": hashlib.sha256("\n".join(sorted(r['source_id'] for r in annotations)).encode()).hexdigest(),
220:         "per_class": modes, "all_unique_modes_equal_label": all(v['unique_mode_equals_label'] for v in modes.values()),
221:         "provider_load_forward": "NOT_RUN", "official_behavior_check": "NOT_RUN", "new_inference": False,
222:         "limitation": "Saved PyTorch validation predictions are diagnostic only; no stable200 ONNX/provider behavior claim."}
P4A_SOURCE_BINDING MN-STABLE "ffdfa6637bace58c9818ade3b9a84e812a59d2f681543927b10403061301dece"
P4A_SOURCE_BINDING RN-HPO42 "ffdfa6637bace58c9818ade3b9a84e812a59d2f681543927b10403061301dece"
P4A_SOURCE_BINDING MN-HPO42 "ffdfa6637bace58c9818ade3b9a84e812a59d2f681543927b10403061301dece"

```


## 附录B — tracked文件保护

下列指纹针对git tracked工作区diff和staged diff字节，不读取db文件。交付后再次核对；指纹采样自12:30起，不冒充更早的全文件快照。

### 命令记录：preservation_before

工作目录：`/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1`。exit code：`0`。

```bash
GIT_OPTIONAL_LOCKS=0 python3 -B - <<'PY'
from pathlib import Path
import subprocess,hashlib,json
from datetime import datetime
from zoneinfo import ZoneInfo
print('observed_at='+datetime.now(ZoneInfo('Asia/Kuala_Lumpur')).isoformat())
for root in ['/Users/liu/Desktop/FYP2-Live-System','/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1']:
 print('ROOT='+root)
 for args in [['git','diff','--binary','--no-ext-diff'],['git','diff','--cached','--binary','--no-ext-diff']]:
  p=subprocess.run(args,cwd=root,capture_output=True);assert p.returncode==0
  print(json.dumps(args)+' exit=0 bytes='+str(len(p.stdout))+' sha256='+hashlib.sha256(p.stdout).hexdigest())
PY
```

当日输出：

```text
observed_at=2026-10-26T12:30:18.402492+08:00
ROOT=/Users/liu/Desktop/FYP2-Live-System
["git", "diff", "--binary", "--no-ext-diff"] exit=0 bytes=0 sha256=e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
["git", "diff", "--cached", "--binary", "--no-ext-diff"] exit=0 bytes=0 sha256=e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
ROOT=/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1
["git", "diff", "--binary", "--no-ext-diff"] exit=0 bytes=14034950 sha256=0897882611a3b0d0bf2512a333af28aa3fac6230e3bd705c4eca60bf3d66d86d
["git", "diff", "--cached", "--binary", "--no-ext-diff"] exit=0 bytes=0 sha256=e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855

```


计划通常要求 `docs/evidence/<date>/`；本次用户明确只准写collab，所以当日命令与输出嵌入本报告，由Claude后续归档，未修改tracked文档。

## 所有 FOR_USER_DECISION 项

- **FUD-01 — FOR_USER_DECISION**：Stage-1 三模型数值容差。提议：每个有参照的集合分别要求 max_abs_prob_delta <= 1e-4 且 argmax_agreement == 1.0；200 帧 per_class_mode_equals_label 单独评估；超限如实失败，不事后放宽。
- **FUD-02 — FOR_USER_DECISION**：Stage-2 输入及顺序。提议：stable200：c0..c9 各类 filename 升序取 validation 前20，按10个连续类别块运行；P4A100/211只作历史附录。
- **FUD-03 — FOR_USER_DECISION**：Stage-2 时间与观测策略。提议：固定UTC合成起点2026-10-25T00:00:00Z，间隔100ms；200窗口i=0..199；同一epoch=1，frame.index=i+1，telemetry_seq=i+1，两种源时间均等于该窗口注入时间。
- **FUD-04 — FOR_USER_DECISION**：固定遥测配对。提议：所有窗口使用 prepared_sessions/session_001/telemetry.csv 第一数据行的8项原始特征；只更新合成时间与seq，运行稳定XGB，不采用CSV中的预设概率。
- **FUD-05 — FOR_USER_DECISION**：Stage-2 协议整体批准。提议：批准正式协议及其sha256后才允许runner运行；每模型一子进程+独立临时SQLite、真实provider+TestClient /infer、固定融合配置、描述性比较，Stage5由用户作替换决定。
- **FUD-06 — FOR_USER_DECISION**：Stage-3 规格措辞更正。提议：将规格中“延迟JSON与perf02同构”更正为perf01；perf02用于日志完整性。该项属于后续Stage3，不阻断Phase0依赖预检。

FUD-01至FUD-05未因“GO”自动生效；FUD-06是后续Stage3规格确认。用户Stage1审计和Stage5最终替换决定仍保留。

## 附录C — 交付回读与最终保护核对

2026-10-26 12:36:27 +08，在追加本节前回读三份文件并验证JSON、200图字节hash、三模型/三parity参照hash、固定遥测hash、忽略/未跟踪状态；命令exit0。对照附录B，Live和ML的tracked工作区diff、staged diff的字节长度及SHA256逐项完全相同；HEAD和dirty列表亦相同。此为工件与只读保护检查，不是provider forward或Stage验收。

实际验证命令：

```bash
GIT_OPTIONAL_LOCKS=0 python3 -B - <<'PY'
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import json,hashlib,subprocess,csv
live=Path('/Users/liu/Desktop/FYP2-Live-System');ml=Path('/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1');out=live/'.superpowers/collab/codex'
print('observed_at='+datetime.now(ZoneInfo('Asia/Kuala_Lumpur')).isoformat())
files=['preflight_report.md','tolerance_predeclaration.md','comparison_protocol.draft.json']
for name in files:
 p=out/name;assert p.is_file() and p.stat().st_size>0
 print('DELIVERABLE',str(p),'bytes='+str(p.stat().st_size),'sha256='+hashlib.sha256(p.read_bytes()).hexdigest())
 p1=subprocess.run(['git','check-ignore','-v',str(p)],cwd=live,text=True,capture_output=True);assert p1.returncode==0;print('IGNORED_EXIT=0',p1.stdout.strip())
 p2=subprocess.run(['git','ls-files','--error-unmatch',str(p)],cwd=live,capture_output=True);assert p2.returncode==1;print('TRACKED_LOOKUP_EXIT=1 EXPECTED_UNTRACKED')
p=json.loads((out/files[2]).read_text());assert p['status']=='DRAFT' and p['execution_authorized'] is False and p['runner_execution']=='NOT_RUN';assert p['approval']['status']=='FOR_USER_DECISION'
assert len(p['compared_identities'])==3 and len(p['for_user_decision'])==6 and all(x['status']=='FOR_USER_DECISION' and not x['approved'] for x in p['for_user_decision'])
samples=p['input_set']['ordered_samples'];assert len(samples)==200 and [r['sequence_index'] for r in samples]==list(range(200))
assert len({r['source_id'] for r in samples})==200
assert hashlib.sha256('\n'.join(sorted(x['filename'] for x in samples)).encode()).hexdigest()==p['input_set']['membership_sha256']
assert hashlib.sha256('\n'.join(sorted(x['source_id'] for x in samples)).encode()).hexdigest()==p['input_set']['source_ids_sha256']
for x in samples:
 f=Path(p['input_set']['data_root'])/x['class_id']/x['filename'];assert hashlib.sha256(f.read_bytes()).hexdigest()==x['sha256'],str(f)
assert hashlib.sha256('\n'.join(x['source_id']+'\t'+x['sha256'] for x in sorted(samples,key=lambda x:x['source_id'])).encode()).hexdigest()==p['input_set']['image_bytes_manifest_sha256']
for x in p['compared_identities']:
 f=Path(x.get('onnx_path',str(Path(x.get('source_package',''))/'model.onnx')));assert hashlib.sha256(f.read_bytes()).hexdigest()==x['sha256'],str(f)
 parity=ml/'ml/outputs/runs/p4a_20261021'/('parity_'+x['parity_tag']+'.json');assert hashlib.sha256(parity.read_bytes()).hexdigest()==x['parity_sha256'],str(parity)
t=p['telemetry_pairing'];assert hashlib.sha256(Path(t['source_file']).read_bytes()).hexdigest()==t['source_file_sha256']
fixed={k:float(v) for k,v in t['features'].items()};assert hashlib.sha256(json.dumps(fixed,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()==t['features_sha256']
preflight=(out/files[0]).read_text();tol=(out/files[1]).read_text();assert all(('Step '+str(i)) in preflight for i in range(1,7));assert '6.364584130613693e-6' in tol and 'single_predictions' in tol and 'NO_STABLE200_REFERENCE' in tol
for root in [live,ml]:
 print('ROOT='+str(root))
 for args in [['git','rev-parse','HEAD'],['git','status','--short']]:
  proc=subprocess.run(args,cwd=root,text=True,capture_output=True);assert proc.returncode==0;print('COMMAND='+json.dumps(args)+' EXIT=0');print(proc.stdout,end='')
 for args in [['git','diff','--binary','--no-ext-diff'],['git','diff','--cached','--binary','--no-ext-diff']]:
  proc=subprocess.run(args,cwd=root,capture_output=True);assert proc.returncode==0;print(json.dumps(args)+' exit=0 bytes='+str(len(proc.stdout))+' sha256='+hashlib.sha256(proc.stdout).hexdigest())
proc=subprocess.run(['git','diff','2745348','--','backend/app/providers/trained.py'],cwd=live,capture_output=True);assert proc.returncode==0 and proc.stdout==b'';print('XGB_BASELINE_DIFF_EMPTY exit=0')
print('ARTIFACT_CONTENT_CHECKS=PASS; JSON_valid=PASS; source/model/input/telemetry_hashes=PASS; NOT_A_PROVIDER_FORWARD_OR_STAGE_ACCEPTANCE')
PY
```

关键输出（保留Git保护与检查结论；文件自身hash以追加后最终回读为准）：

```text
ROOT=/Users/liu/Desktop/FYP2-Live-System
COMMAND=["git", "rev-parse", "HEAD"] EXIT=0
7e64c4d0632923d7bb90c1c8f6b7cb757ca5ea65
COMMAND=["git", "status", "--short"] EXIT=0
?? AGENTS.md
?? backend/driver_risk.db-shm
?? backend/driver_risk.db-wal
["git", "diff", "--binary", "--no-ext-diff"] exit=0 bytes=0 sha256=e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
["git", "diff", "--cached", "--binary", "--no-ext-diff"] exit=0 bytes=0 sha256=e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
ROOT=/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1
COMMAND=["git", "rev-parse", "HEAD"] EXIT=0
ba1046c9debc9fda9f87bd55016ad42e6eb360cf
COMMAND=["git", "status", "--short"] EXIT=0
 M ml/outputs/runs/e1_preparation_20261019/telemetry_variants.csv
 M ml/outputs/runs/e1_preparation_20261019/vision_manifest.csv
 M ml/outputs/runs/e1_preparation_20261019_record_missingness/telemetry_variants.csv
 M ml/outputs/runs/e1_preparation_20261019_record_missingness/vision_manifest.csv
 M ml/outputs/runs/p4a_20261021/qc/validation_pilot/R1.csv
 M ml/outputs/runs/p5_candidates_20261023/p5_mobilenet_v3_large_search006_seed42_20261023/predictions_test_clean.csv
 M ml/outputs/runs/p5_candidates_20261023/p5_mobilenet_v3_large_search006_seed42_20261023/validation/stable200_annotations.csv
 M ml/outputs/runs/p5_candidates_20261023/p5_mobilenet_v3_large_search006_seed42_20261023/validation/stable200_saved_predictions.csv
 M ml/outputs/runs/p5_candidates_20261023/p5_resnet18_search004_seed42_20261023/predictions_test_clean.csv
 M ml/outputs/runs/p5_candidates_20261023/p5_resnet18_search004_seed42_20261023/validation/stable200_annotations.csv
 M ml/outputs/runs/p5_candidates_20261023/p5_resnet18_search004_seed42_20261023/validation/stable200_saved_predictions.csv
 M ml/outputs/runs/p5_candidates_20261023/telemetry_research_evidence/predictions_test_clean.csv
?? AGENTS.md
["git", "diff", "--binary", "--no-ext-diff"] exit=0 bytes=14034950 sha256=0897882611a3b0d0bf2512a333af28aa3fac6230e3bd705c4eca60bf3d66d86d
["git", "diff", "--cached", "--binary", "--no-ext-diff"] exit=0 bytes=0 sha256=e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
XGB_BASELINE_DIFF_EMPTY exit=0
ARTIFACT_CONTENT_CHECKS=PASS; JSON_valid=PASS; source/model/input/telemetry_hashes=PASS; NOT_A_PROVIDER_FORWARD_OR_STAGE_ACCEPTANCE

```

## 附录D — 用户批准（原预检快照不改写）

记录时间：2026-10-26T12:56:55.974477+08:00。用户原文：“都批准”。FUD-01–FUD-06全部为APPROVED。正文中的DRAFT/FOR_USER_DECISION及未批准状态属于原预检时点；以本附录、当前容差文件和 `approval_record.json` 为最新批准状态。

- 批准版协议：`comparison_protocol.approved.json`，SHA256 `b63050221c467ac7ed1ced0ae5e4af95ca734a7ba15fe4d7af94c948074c988f`。
- 生效容差：概率最大绝对差≤1e-4且argmax一致率=1.0；原稿保留。
- 其余批准内容：stable200连续类别块；100ms合成时钟及逐帧新观测；固定遥测第一行；完整隔离/描述性Stage-2协议；Stage-3使用perf01测延迟、perf02核对日志。
- 原始draft保持原字节，供审计追溯。由Claude发布正式协议与规格更正；本轮仍不改tracked文件、不运行runner。
- 本批准不等于Stage-1用户审计通过或Stage-5发布决定。Live System当前HEAD `4ca3c69e6fae38c76635b360754ba0468755d0dd` 属其他lane推进；原GO结论仍只对应原记录时点，不外推为当前集成验收。
