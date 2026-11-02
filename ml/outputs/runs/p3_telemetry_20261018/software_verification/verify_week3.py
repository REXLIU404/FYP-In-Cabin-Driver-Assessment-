"""Read-only Week 3/P1 evidence recheck; no model fit, forward, or data loader."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score, log_loss

ROOT=Path(__file__).resolve().parents[5]
RUN=ROOT/'ml/outputs/runs/p1_comparators_20261015'


def main():
    ledger=json.loads((RUN/'artifact_manifest.json').read_text())
    configuration=json.loads((RUN/'config.json').read_text())
    count=0;models=[]
    for attempt in ledger['attempts']:
        for record in attempt['artifact_records']:
            path=Path(record['path'])
            assert path.is_file() and path.stat().st_size==record['bytes']
            assert hashlib.sha256(path.read_bytes()).hexdigest()==record['sha256'],str(path)
            count+=1
        directory=RUN/attempt['model']/f'attempt_{attempt["attempt"]:02d}'
        metrics=json.loads((directory/'validation_metrics.json').read_text())
        samples=pd.read_csv(directory/'sample_manifest.csv')
        expected={'train':200,'val':100} if attempt['model']=='resnet18' else {'train':300,'val':90}
        # P1 manifests spell the validation split "val".
        assert samples.groupby('split').size().to_dict()==expected
        classes=10 if attempt['model']=='resnet18' else 3
        for split,size in expected.items():
            counts=samples[samples.split==split].groupby('label').size()
            assert len(counts)==classes and set(counts)=={size//classes}
        assert samples.source_id.is_unique
        prediction=pd.read_csv(directory/'predictions_validation.csv')
        columns=[c for c in prediction if c.startswith('probability_')]
        probabilities=prediction[columns].to_numpy()
        if attempt['model']=='resnet18':probabilities=probabilities.astype(np.float32)
        labels=prediction['true_label_index'].to_numpy()
        assert np.isfinite(probabilities).all() and np.allclose(probabilities.sum(1),1.,atol=1e-6)
        assert probabilities.shape==tuple(metrics['output_shape'])
        recalculated={'accuracy':accuracy_score(labels,probabilities.argmax(1)),
            'macro_f1':f1_score(labels,probabilities.argmax(1),average='macro',zero_division=0),
            'log_loss':log_loss(labels,probabilities,labels=list(range(len(columns))))}
        for key,value in recalculated.items():assert np.isclose(value,metrics[key],rtol=1e-6,atol=1e-9),(attempt['model'],key)
        assert metrics['status']=='VERIFIED_PASS' and attempt['attempt']==1
        models.append({'model':attempt['model'],'stratified_sample_counts':expected,'prediction_rows':len(prediction),'metrics':recalculated,
                       'saved_reload_evidence':str(directory/'validation_metrics.json')})
    for name,wanted in configuration['source_hashes'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==wanted,name
    assert ledger['status']=='VERIFIED_PASS' and len(ledger['attempts'])==3
    print(json.dumps({'week3':'VERIFIED_PASS_WITHIN_APPROVED_COMPARATOR_SMOKE_SCOPE',
        'artifact_hash_records':count,'p1_source_files_unchanged':len(configuration['source_hashes']),
        'models':models,'p1_original_combined_wall_seconds':ledger['used_wall_seconds'],
        'new_smoke_fits':0,'independent_model_forward_this_check':0,'test_access':False,
        'limitations':['Original save/reload logs and binaries verified; no new P1 reload or numerical retraining',
                       'ResNet18 random-initialized smoke is not valid for formal model comparison']},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
