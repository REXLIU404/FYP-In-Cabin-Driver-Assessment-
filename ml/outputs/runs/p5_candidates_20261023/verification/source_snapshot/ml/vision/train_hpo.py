"""One user-operated MPS vision trial, supervised by run_vision_hpo.py."""
import argparse
import json
import math
import os
import random
import sys
import time
from pathlib import Path

for variable in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS']:
    os.environ[variable]='2'
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from ml.experiments import comparator_common as common
from ml.experiments import hpo_protocol as protocol


def validate_plan(plan,phase,cfg):
    if plan['model'] not in ['mobilenet_v3_large','resnet18']:raise ValueError('Unapproved architecture')
    if phase=='probe':
        if (plan['role'],plan['seed'],plan['max_epochs'],plan['config'])!=('PROBE',42,1,{'learning_rate':.0008,'weight_decay':.0001}):
            raise ValueError('Probe recipe is fixed')
    elif phase=='search':
        if plan['max_epochs']!=8 or plan['config'] not in protocol.search_configs(plan['model'],cfg):raise ValueError('Unapproved formal recipe')
        if not ((plan['role']=='SEARCH' and plan['seed']==42) or (plan['role']=='CONFIRMATION' and plan['seed'] in [43,44])):
            raise ValueError('Unapproved role or seed')
    else:raise ValueError('Only probe or search is authorized')


def advance_early_stop(best,bad,score):
    if not math.isfinite(score):raise ValueError('Non-finite validation score')
    improved=score>best
    return (score if improved else best,0 if improved else bad+1,improved,False if improved else bad+1>=2)


def train(directory,deadline):
    import numpy as np
    import pandas as pd
    import torch
    from PIL import Image
    from torch.utils.data import DataLoader,Dataset
    from torchvision import models
    from threadpoolctl import threadpool_limits

    request=json.loads((directory/'config.json').read_text())
    plan,context,phase=request['plan'],request['context'],request['phase']
    cfg=protocol.load_protocol();validate_plan(plan,phase,cfg)
    protocol.guard_environment(require_mps=True)
    torch.set_num_threads(2);torch.set_num_interop_threads(1)
    random.seed(plan['seed']);np.random.seed(plan['seed']);torch.manual_seed(plan['seed']);torch.mps.manual_seed(plan['seed'])

    def check():
        common.check_deadline(deadline)
        if os.getppid()!=int(os.environ['FYP_VISION_PARENT']):raise RuntimeError('Supervising parent exited; stopping orphan trial')

    frames,sources,names=common.load_vision(Path(context['data_root']))
    training,validation=frames['train'],frames['val']
    if (len(training),len(validation))!=(15899,2868):raise ValueError('Frozen vision split sizes changed')
    class_to_idx={c:i for i,c in enumerate(common.CLASSES)}

    class Frames(Dataset):
        def __init__(self,frame,training):self.frame=frame;self.transform=common.vision_transforms(training)
        def __len__(self):return len(self.frame)
        def __getitem__(self,index):
            check();row=self.frame.iloc[index]
            with Image.open(row.image_path) as image:values=self.transform(image.convert('RGB'))
            return values,class_to_idx[row.class_id]

    def architecture():
        if plan['model']=='resnet18':
            model=models.resnet18(weights=None);model.fc=torch.nn.Linear(512,10)
        else:
            model=models.mobilenet_v3_large(weights=None);model.classifier[-1]=torch.nn.Linear(model.classifier[-1].in_features,10)
        return model

    check()
    model=models.resnet18(weights=None) if plan['model']=='resnet18' else models.mobilenet_v3_large(weights=None)
    weight=context['weights_manifest'][plan['model']]
    prefix='f37072fd' if plan['model']=='resnet18' else '5c1a4163'
    if not weight['sha256'].startswith(prefix) or common.sha256(weight['path'])!=weight['sha256']:raise ValueError('Pretraining integrity mismatch')
    model.load_state_dict(torch.load(weight['path'],map_location='cpu',weights_only=True),strict=True)
    if plan['model']=='resnet18':model.fc=torch.nn.Linear(512,10)
    else:model.classifier[-1]=torch.nn.Linear(model.classifier[-1].in_features,10)
    model.to('mps')
    optimizer=torch.optim.AdamW(model.parameters(),lr=plan['config']['learning_rate'],weight_decay=plan['config']['weight_decay'])
    scheduler=torch.optim.lr_scheduler.CosineAnnealingLR(optimizer,T_max=8)
    criterion=torch.nn.CrossEntropyLoss()
    generator=torch.Generator().manual_seed(plan['seed'])
    train_loader=DataLoader(Frames(training,True),batch_size=64,shuffle=True,generator=generator,num_workers=0)
    val_loader=DataLoader(Frames(validation,False),batch_size=64,shuffle=False,num_workers=0)
    source_rows=[{'source_id':f'vision-v1:{r.class_id}/{r.filename}','split':split,'source_row':int(i),
                  'class_id':r.class_id,'driver_id':r.driver_id}
                 for split,frame in [('train',training),('val',validation)] for i,r in frame.iterrows()]
    pd.DataFrame(source_rows).to_csv(directory/'sample_manifest.csv',index=False)
    best,bad,best_epoch=-1.,0,0
    timings,epochs=[],[]
    peak_mps_allocated=peak_mps_driver=0
    reload_input=reload_reference=None
    best_logits=best_probabilities=best_labels=None

    def memory():
        nonlocal peak_mps_allocated,peak_mps_driver
        peak_mps_allocated=max(peak_mps_allocated,int(torch.mps.current_allocated_memory()))
        peak_mps_driver=max(peak_mps_driver,int(torch.mps.driver_allocated_memory()))

    with threadpool_limits(2):
        for epoch in range(1,plan['max_epochs']+1):
            check();model.train();train_start=time.monotonic();loss_sum=0.;train_seen=0
            lr=float(optimizer.param_groups[0]['lr'])
            for step,(inputs,labels) in enumerate(train_loader,1):
                check();started=time.monotonic();inputs,labels=inputs.to('mps'),labels.to('mps')
                optimizer.zero_grad(set_to_none=True);loss=criterion(model(inputs),labels)
                if not torch.isfinite(loss):raise ValueError('Non-finite training loss')
                loss.backward();optimizer.step();torch.mps.synchronize();memory()
                loss_sum+=float(loss.detach().cpu())*len(labels);train_seen+=len(labels)
                timings.append({'epoch':epoch,'phase':'train','step':step,'samples':len(labels),'seconds':time.monotonic()-started})
                check()
            train_seconds=time.monotonic()-train_start
            if train_seen!=len(training):raise ValueError('Incomplete full training epoch')
            model.eval();val_start=time.monotonic();all_logits=[];all_labels=[]
            epoch_reload_input=epoch_reload_reference=None
            with torch.inference_mode():
                for step,(inputs,labels) in enumerate(val_loader,1):
                    check();started=time.monotonic();logits=model(inputs.to('mps')).cpu();torch.mps.synchronize();memory()
                    if not torch.isfinite(logits).all():raise ValueError('Non-finite validation logits')
                    if epoch_reload_input is None:epoch_reload_input=inputs[:16].clone();epoch_reload_reference=logits[:16].clone()
                    all_logits.append(logits);all_labels.append(labels)
                    timings.append({'epoch':epoch,'phase':'validation','step':step,'samples':len(labels),'seconds':time.monotonic()-started})
            validation_seconds=time.monotonic()-val_start
            logits=torch.cat(all_logits);labels=torch.cat(all_labels);probabilities=logits.softmax(1).numpy()
            diag=common.diagnostics(labels.numpy(),probabilities,common.CLASSES)
            validation_loss=float(criterion(logits,labels))
            if not math.isfinite(validation_loss):raise ValueError('Non-finite validation loss')
            record={'epoch':epoch,'train_seconds':train_seconds,'validation_seconds':validation_seconds,
                    'train_images_per_second':len(training)/train_seconds,'validation_images_per_second':len(validation)/validation_seconds,
                    'train_loss':loss_sum/train_seen,'validation_loss':validation_loss,'macro_f1':diag['macro_f1'],'log_loss':diag['log_loss'],'learning_rate':lr}
            epochs.append(record)
            best,bad,improved,stop=advance_early_stop(best,bad,diag['macro_f1'])
            if improved:
                best_epoch=epoch;best_logits=logits.numpy().copy();best_probabilities=probabilities.copy();best_labels=labels.numpy().copy()
                reload_input,reload_reference=epoch_reload_input,epoch_reload_reference
                checkpoint={'state_dict':{k:v.detach().cpu() for k,v in model.state_dict().items()},
                            'arch':plan['model'],'class_to_idx':class_to_idx,'classes':common.CLASSES,'idx_to_name':names,
                            'best_epoch':epoch,'seed':plan['seed'],'pretraining':weight,'probe':phase=='probe',
                            'preprocessing':{'rgb':True,'resize':[224,224],'interpolation':'PIL bilinear','crop':False,
                                             'mean':common.MEAN,'std':common.STD,'layout':'NCHW','dtype':'float32'}}
                temporary=directory/'checkpoint.tmp.pt';torch.save(checkpoint,temporary);os.replace(temporary,directory/'checkpoint.pt')
            scheduler.step()
            print(json.dumps(record),flush=True)
            if stop:break
        check()
        saved=torch.load(directory/'checkpoint.pt',map_location='cpu',weights_only=True)
        restored=architecture();restored.load_state_dict(saved['state_dict'],strict=True);restored.to('mps').eval()
        started=time.monotonic()
        with torch.inference_mode():recovered=restored(reload_input.to('mps')).cpu()
        torch.mps.synchronize();memory()
        difference=float((recovered-reload_reference).abs().max())
        if not torch.allclose(recovered,reload_reference,atol=1e-5,rtol=1e-5):raise ValueError('Reload changed best-checkpoint logits')
        timings.append({'epoch':best_epoch,'phase':'reload_validation','step':1,'samples':len(reload_input),'seconds':time.monotonic()-started})
    np.save(directory/'probabilities_validation.npy',best_probabilities,allow_pickle=False)
    predictions=pd.DataFrame({'source_id':[f'vision-v1:{r.class_id}/{r.filename}' for r in validation.itertuples()],
                              'true_label_index':best_labels,'predicted_label_index':best_probabilities.argmax(1)})
    for i,label in enumerate(common.CLASSES):predictions[f'logit_{label}']=best_logits[:,i];predictions[f'probability_{label}']=best_probabilities[:,i]
    predictions.to_csv(directory/'predictions_validation.csv',index=False)
    metrics=common.diagnostics(best_labels,best_probabilities,common.CLASSES);report=metrics.pop('class_report')
    metrics.update(status='COMPLETED',interpretation='NON_COMPARATIVE_PROBE' if phase=='probe' else 'FORMAL_VALIDATION_ONLY',
                   formal_comparison_valid=phase!='probe',counts_toward_hpo=phase=='search',best_epoch=best_epoch,epochs=epochs,
                   epochs_completed=len(epochs),train_samples=len(training),validation_samples=len(validation),batch_size=64,
                   device='mps',threads=2,workers=0,cosine_T_max=8,early_stopping_patience=2,
                   reload_verified=True,reload_samples=len(reload_input),reload_max_abs_logit_difference=difference,
                   all_losses_and_probabilities_finite=True,test_predictions=0,test_images_opened=0,
                   mps_bitwise_reproducibility_guaranteed=False,resource_usage=common.resource_usage(),
                   mps_max_observed_allocated_bytes=peak_mps_allocated,mps_max_observed_driver_bytes=peak_mps_driver,
                   memory_measurement='OS peak RSS plus MPS memory sampled after synchronized batches; device transients may be missed')
    common.write_json(directory/'validation_metrics.json',metrics)
    common.write_json(directory/'class_report.json',report)
    common.write_json(directory/'selection_log.json',{'best_epoch':best_epoch,'selection_split':'val',
        'probe_used_for_model_selection':False,'test_predictions':'NOT_YET_DUE','model_selection':'root selection_log after all search configs'})
    pd.DataFrame([{**t,'warmup':False,'device':'mps','threads':2,'provider':'torch','batch':64} for t in timings]).to_csv(directory/'timing_samples.csv',index=False)
    pd.DataFrame([{**plan,'config':json.dumps(plan['config']),'status':'COMPLETED','counts_toward_hpo':phase=='search',
                   'best_epoch':best_epoch,'macro_f1':metrics['macro_f1'],'log_loss':metrics['log_loss']}]).to_csv(directory/'trials.csv',index=False)
    records={p.name:common.file_record(p) for p in directory.iterdir() if p.is_file() and p.name!='execution.log'}
    records['predictions_test.csv']={'status':'NOT_YET_DUE','created':False,'phase':'P4'}
    common.write_json(directory/'artifact_manifest.json',{'status':'COMPLETED','artifacts':records,'sources':sources,
        'class_to_idx':class_to_idx,'training_label_names':names,'runtime_c0_name':'safe_driving','versions':common.software_versions(),
        'git':context['environment']['git'],'source_hashes':context['source_hashes'],'pretraining':weight,
        'test_images_opened':0,'candidate_package':False,'mps_nondeterminism_disclosed':True})
    check()
    print('TRIAL_COMPLETE',plan['model'],plan['trial_id'],best_epoch,metrics['macro_f1'],flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--attempt-dir',type=Path,required=True);args=parser.parse_args()
    if not os.environ.get('FYP_VISION_DEADLINE') or not os.environ.get('FYP_VISION_PARENT'):parser.error('Supervised user-terminal vision runner required')
    common.reject_symlink_path(args.attempt_dir)
    if not args.attempt_dir.resolve().is_relative_to(common.RUNS.resolve()):parser.error('Isolated ML run directory required')
    try:train(args.attempt_dir,float(os.environ['FYP_VISION_DEADLINE']));return 0
    except Exception:
        import traceback
        traceback.print_exc();return 1


if __name__=='__main__':sys.exit(main())
