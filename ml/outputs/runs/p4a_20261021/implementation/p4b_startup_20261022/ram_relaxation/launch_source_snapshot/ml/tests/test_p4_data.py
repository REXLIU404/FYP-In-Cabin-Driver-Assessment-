"""P4 data contracts; all observations in this file are synthetic."""
import csv
import hashlib
import importlib
import json

import numpy as np
import pytest
from PIL import Image


@pytest.fixture
def data():
    try:
        return importlib.import_module('ml.experiments.p4_data')
    except ModuleNotFoundError as error:
        if error.name != 'ml.experiments.p4_data':
            raise
        pytest.fail('Missing gated P4 data adapters')


def stats():
    return {'fit_split':'train','fit_rows':3,'train_split_sha256':'train-sha',
            'feature_order':['speed_kmph','accel_x','accel_y','brake_pressure',
              'steering_angle','throttle','lane_deviation','headway_distance'],
            'median':[2.]*8,'mean_global':[2.]*8,'sd_ddof0':[1.]*8,
            'mean_by_class':{x:[2.]*8 for x in ['Safe','Aggressive','Distracted']}}


def test_test_metadata_and_telemetry_are_denied_before_open(data,tmp_path):
    for fn in [data.read_vision_metadata,data.read_telemetry_csv]:
        with pytest.raises(PermissionError):
            fn(tmp_path/'does-not-exist',split='test',expected_sha256='anything')


def test_metadata_proves_validation_before_images_and_preserves_row_identity(data,tmp_path):
    p=tmp_path/'metadata.csv'; image=tmp_path/'val.png'
    Image.new('RGB',(4,4),'white').save(image)
    p.write_text('split,class_id,filename,driver_id,image_path,class_name\n'
                 'test,c1,hidden.jpg,p012,/do/not/open,action\n'
                 f'val,c0,val.png,p002,{image},normal_driving\n')
    records=data.read_vision_metadata(p,split='val',expected_sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    assert len(records)==1 and records[0]['source_id']=='vision-v1:c0/val.png'
    assert records[0]['source_row']==1 and records[0]['source_split']=='val'
    loaded=data.load_validation_image(records[0]); assert loaded.size==(4,4)
    forged=dict(records[0],source_split='test')
    with pytest.raises(PermissionError): data.load_validation_image(forged)


def test_telemetry_ids_assigned_before_any_order_changes(data,tmp_path):
    p=tmp_path/'val.csv'
    with p.open('w') as f:
        w=csv.writer(f);w.writerow(stats()['feature_order']+['behavior_label'])
        w.writerow([3]*8+['Safe']);w.writerow([1]*8+['Distracted'])
    sha=hashlib.sha256(p.read_bytes()).hexdigest()
    rows=data.read_telemetry_csv(p,split='val',expected_sha256=sha)
    assert [r['source_id'] for r in rows]==[f'telemetry-v1:{sha}:val:0',f'telemetry-v1:{sha}:val:1']
    assert rows[0]['features']==[3.]*8


def test_shared_vision_bank_retains_pixels_provenance_and_p3_guard(data):
    from ml.experiments import e1_generators as old
    record={'source_id':'vision-v1:c0/toy','driver_id':'toy','source_split':'synthetic'}
    image=Image.new('RGB',(224,224),(90,80,70));before=image.tobytes()
    bank=list(data.vision_bank(image,record))
    assert len(bank)==19 and image.tobytes()==before
    assert all(r['source_split']=='synthetic' and not r['f1_eligible'] for _,r in bank)
    assert bank[0][0].getpixel((112,112))==(90,80,70)
    with pytest.raises(ValueError):list(old.vision_variants(image,'x','p',source_split='test'))


def test_rotation_six_signed_angles_have_no_fill_after_frozen_crop(data):
    checks=data.rotation_geometry_check()
    assert [x['angle'] for x in checks]==[-12,-7,-3,3,7,12]
    assert [x['side'] for x in checks]==[188,201,213,213,201,188]
    assert all(x['fill_pixels']==0 and x['status']=='PASS' for x in checks)


def test_train_stats_reuse_verifies_full_arrays_and_hpo_medians(data):
    original=stats();before=json.dumps(original,sort_keys=True)
    assert data.verify_train_statistics(original,expected_train_sha256='train-sha',
        pipeline_medians=[[2.]*8]*3)=='REUSED_AND_VERIFIED'
    with pytest.raises(ValueError):data.verify_train_statistics(original,expected_train_sha256='other')
    with pytest.raises(ValueError):data.verify_train_statistics(original,expected_train_sha256='train-sha',pipeline_medians=[[3.]*8])
    assert json.dumps(original,sort_keys=True)==before


def test_telemetry_nested_record_masks_and_multistage_bounds(data):
    values=np.tile([[-1.,3.,3.,3.,3.,3.,3.,-1.]],(100,1))
    rows=list(data.telemetry_bank(values,['Safe']*100,[f'id{i}' for i in range(100)],stats(),
        source_split='synthetic',empirical_bounds=[[0.,2.]]*8))
    assert len(rows)==1000
    sets=[]
    for s,n in enumerate([5,10,20]):
        group=[r for r in rows if r['domain']=='D3' and r['severity']==s]
        affected={r['source_id'] for r in group if r['record_affected']};sets.append(affected)
        assert len(affected)==n
        assert all(sum(r['injected_missing_mask'])==int(r['record_affected']) for r in group)
        assert all(r['interpretation']=='COMBINED_POSITIVE_BIAS_AND_RECORD_MISSINGNESS' for r in group)
    assert sets[0]<=sets[1]<=sets[2]
    masked=next(r for r in rows if r['domain']=='D3' and r['record_affected'])
    feature=masked['masked_feature_index'];b=masked['bounds']
    assert b['observed'][feature]['domain']['status']=='MISSING'
    assert b['pre_mask'][feature]['empirical']['status']=='OUT_OF_BOUNDS'
    assert b['imputed'][feature]['empirical']['status']=='WITHIN_BOUNDS'
    assert b['source'][1]['domain']['status']=='UNKNOWN'
    assert b['source'][0]['domain']['lower_excess']==1.
    assert b['source'][0]['domain']['upper_excess'] is None
    assert all(r['label_validity']=='LABEL_VALIDITY_UNVERIFIED' and not r['f1_eligible'] for r in rows if r['domain']!='D0')


def test_source_nan_fails_without_imputing_or_refitting(data):
    x=np.ones((1,8));x[0,1]=np.nan
    with pytest.raises(ValueError,match='finite'):
        list(data.telemetry_bank(x,['Safe'],['x'],stats(),source_split='synthetic'))


def test_mislabelled_heldout_path_and_frozen_sha_cannot_bypass_gate(data,tmp_path):
    with pytest.raises(PermissionError):
        data.read_telemetry_csv(tmp_path/'telemetry_test.csv',split='val',expected_sha256='irrelevant')
    with pytest.raises(PermissionError):
        data.read_telemetry_csv(tmp_path/'renamed.csv',split='val',
            expected_sha256='3bc3d47680a87359e1470fd8ffaf5ff330dc4419b37cc645e5736d51a91c96de')


def test_statistics_reuse_detects_changed_global_or_class_statistics(data):
    computed=stats();computed['mean_global'][0]=99.
    with pytest.raises(ValueError):
        data.verify_train_statistics(stats(),expected_train_sha256='train-sha',computed_statistics=computed)
    computed=stats();computed['mean_by_class']['Safe'][0]=99.
    with pytest.raises(ValueError):
        data.verify_train_statistics(stats(),expected_train_sha256='train-sha',computed_statistics=computed)


def test_authorized_synthetic_test_split_adapter_retains_split_without_global_change(data):
    from ml.experiments import e1_generators as old
    from ml.experiments.p4_core import authorize_p4b
    binding={'protocol_sha256':'a'*64,'source_sha256':'b'*64,'run_id':'synthetic_unit_only'}
    token=authorize_p4b(dict(binding,phase='P4-B',authorized=True,human_approval='synthetic fixture only'),**binding)
    image=Image.new('RGB',(4,4),'white')
    record={'source_id':'synthetic-test','driver_id':'toy','source_split':'test'}
    bank=list(data.vision_bank(image,record,authorization=token))
    assert len(bank)==19 and all(r['source_split']=='test' for _,r in bank)
    with pytest.raises(ValueError):list(old.vision_variants(image,'x','p',source_split='test'))
