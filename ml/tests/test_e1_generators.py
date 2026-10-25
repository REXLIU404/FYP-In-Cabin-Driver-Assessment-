"""E1 preparation contracts using synthetic inputs only; no model or test data."""
import hashlib
import importlib
import json

import numpy as np
import pytest
from PIL import Image


@pytest.fixture
def e1():
    try:
        return importlib.import_module('ml.experiments.e1_generators')
    except ModuleNotFoundError as error:
        if error.name != 'ml.experiments.e1_generators':
            raise
        class Missing:
            def __getattr__(self, name):
                pytest.fail('Missing reproducible E1 preparation generators')
        return Missing()


def image():
    a=np.arange(224*224*3,dtype=np.uint32).reshape(224,224,3)%256
    return Image.fromarray(a.astype(np.uint8))


def statistics(e1):
    x=np.repeat(np.array([[0.],[2.],[4.]]),8,axis=1)
    return e1.fit_train_statistics(x,['Safe','Aggressive','Distracted'],split='train',source_sha256='toy-train')


def telemetry(e1,values=None,ids=None,labels=None,rates=(.05,.1,.2),direction=None,bounds=None):
    x=np.ones((3,8)) if values is None else values
    return list(e1.telemetry_variants(x,labels or ['Safe']*len(x),ids or [f'toy:{i}' for i in range(len(x))],
        statistics(e1),missing_rates=rates,drift_direction=[1]*8 if direction is None else direction,
        bounds=bounds,source_split='synthetic'))


def test_vision_19_variants_are_reproducible_and_leave_input_unchanged(e1):
    source=image();before=source.tobytes()
    first=list(e1.vision_variants(source,'vision-v1:c0/toy.jpg','toy-driver',source_split='synthetic'))
    second=list(e1.vision_variants(source,'vision-v1:c0/toy.jpg','toy-driver',source_split='synthetic'))
    assert len(first)==19 and len({row['variant_id'] for _,row in first})==19
    assert source.tobytes()==before
    assert [r for _,r in first]==[r for _,r in second]
    for (a,row),(b,_) in zip(first,second):
        assert a.mode=='RGB' and a.size==(224,224) and a.tobytes()==b.tobytes()
        assert row['pixel_sha256']==hashlib.sha256(a.tobytes()).hexdigest()
        assert row['source_id']=='vision-v1:c0/toy.jpg' and row['driver_id']=='toy-driver'
        assert row['seed']==42 and row['horizontal_flip'] is False


def test_vision_strengths_and_correct_names(e1):
    rows=[r for _,r in e1.vision_variants(image(),'toy','driver',source_split='synthetic')]
    expected={'brightness_up':[1.2,1.5,1.8],'brightness_down':[.8,.5,.3],
              'motion_blur':[3,7,11],'occlusion':[.05,.1,.2],
              'rotation_crop':[3,7,12],'grayscale_blend':[.3,.6,1.]}
    assert rows[0]['condition']=='clean'
    for condition,strengths in expected.items():
        assert [r['strength'] for r in rows if r['condition']==condition]==strengths
    assert not any('gaussian' in r['condition'] or 'infrared' in r['condition'] for r in rows)


@pytest.mark.parametrize('angle',[0,45,90,135])
@pytest.mark.parametrize('size',[3,7,11])
def test_motion_kernel_is_normalized_directional_line(e1,angle,size):
    kernel=e1.motion_kernel(size,angle)
    assert kernel.shape==(size,size) and np.count_nonzero(kernel)==size
    assert np.isclose(kernel.sum(),1.) and np.allclose(kernel,np.flip(kernel))
    if angle==0:assert np.count_nonzero(kernel[size//2,:])==size
    if angle==90:assert np.count_nonzero(kernel[:,size//2])==size


def test_motion_blur_impulse_is_not_gaussian(e1):
    array=np.zeros((224,224,3),dtype=np.uint8);array[112,112]=255
    variants=list(e1.vision_variants(Image.fromarray(array),'impulse','driver',source_split='synthetic'))
    output,row=next((a,r) for a,r in variants if r['condition']=='motion_blur' and r['strength']==3)
    assert np.count_nonzero(np.asarray(output)[:,:,0])==3
    assert row['params']['kernel_size']==3 and row['params']['direction_degrees'] in [0,45,90,135]


def test_occlusion_and_crop_geometry_are_recorded(e1):
    variants=list(e1.vision_variants(image(),'geometry','driver',source_split='synthetic'))
    for output,row in variants:
        p=row['params']
        if row['condition']=='occlusion':
            x,y,w,h=p['box_xywh'];assert 0<=x<x+w<=224 and 0<=y<y+h<=224
            assert abs(w*h/(224*224)-row['strength'])<.01
            assert not np.asarray(output)[y:y+h,x:x+w].any()
            assert row['qc_status']=='PENDING' and not row['f1_eligible']
        if row['condition']=='rotation_crop':
            x0,y0,x1,y1=p['crop_box_xyxy'];assert 0<=x0<x1<=224 and 0<=y0<y1<=224
            assert abs(p['angle_degrees'])==row['strength'] and x1-x0==y1-y0
            assert p['geometry_policy']=='centered_inscribed_square'


def test_brightness_and_grayscale_independent_pixel_oracles(e1):
    variants=list(e1.vision_variants(Image.new('RGB',(224,224),(100,50,10)),'solid','driver',source_split='synthetic'))
    bright,_=next((a,r) for a,r in variants if r['condition']=='brightness_up' and r['strength']==1.2)
    assert bright.getpixel((100,100))==(120,60,12)
    gray,_=next((a,r) for a,r in variants if r['condition']=='grayscale_blend' and r['strength']==1.)
    assert len(set(gray.getpixel((100,100))))==1


def test_train_only_statistics_and_imputation_do_not_depend_on_validation(e1):
    train=np.repeat(np.array([[0.],[2.]]),8,axis=1)
    stats=e1.fit_train_statistics(train,['Safe','Safe'],split='train',source_sha256='train-only')
    before=json.dumps(stats,sort_keys=True)
    heldout=np.repeat(np.array([[100.],[1000.],[np.nan]]),8,axis=1)
    rows=list(e1.telemetry_variants(heldout,['Safe']*3,['a','b','c'],stats,
        missing_rates=[0,.5,1],drift_direction=[1]*8,bounds=None,source_split='synthetic'))
    clean=[r for r in rows if r['domain']=='D0']
    assert clean[-1]['features']==[1.]*8 and np.array_equal(train[:,0],[0,2])
    assert json.dumps(stats,sort_keys=True)==before
    assert all(r['synthetic'] is True and r['perturbed'] is False for r in clean)
    assert clean[0]['raw_source_features']==[100.]*8


@pytest.mark.parametrize('split',['val','test'])
def test_statistics_refuse_non_train_fit(e1,split):
    with pytest.raises(ValueError,match='train'):
        e1.fit_train_statistics(np.ones((3,8)),['Safe']*3,split=split,source_sha256='not-train')


def test_telemetry_counts_shared_masks_and_order_independence(e1):
    rows=telemetry(e1);again=telemetry(e1,ids=['toy:2','toy:1','toy:0'])
    assert len(rows)==30 and len({r['variant_id'] for r in rows})==30
    assert {r['variant_id']:r for r in rows}=={r['variant_id']:r for r in again}
    assert all(len(r['features'])==len(r['missing_mask'])==8 for r in rows)
    assert all(np.isfinite(r['features']).all() for r in rows)
    json.dumps(rows,allow_nan=False)


def test_d1_reuses_noise_draw_and_d2_is_label_conditioned(e1):
    rows=telemetry(e1);stats=statistics(e1)
    noise=[r for r in rows if r['source_id']=='toy:0' and r['domain']=='D1']
    standardized=[(np.array(r['features'])-1)/(r['strength']*np.array(stats['sd_ddof0'])) for r in noise]
    assert np.allclose(standardized[0],standardized[1]) and np.allclose(standardized[1],standardized[2])
    for row in rows:
        if row['domain']=='D2':
            expected=np.ones(8)+row['strength']*(np.array(stats['mean_global'])-np.array(stats['mean_by_class']['Safe']))
            assert np.allclose(row['features'],expected) and row['label_conditioned'] is True
            assert row['interpretation']=='LABEL_CONDITIONED_STRESS' and not row['f1_eligible']


def test_d3_nested_masks_missing_extremes_and_train_median(e1):
    rows=[r for r in telemetry(e1,rates=(0,.5,1)) if r['domain']=='D3' and r['source_id']=='toy:0']
    assert not any(rows[0]['missing_mask']) and sum(rows[2]['missing_mask'])==1
    assert all(a<=b for a,b in zip(rows[1]['missing_mask'],rows[2]['missing_mask']))
    for i,masked in enumerate(rows[2]['missing_mask']):
        if masked:
            assert rows[2]['features'][i]==statistics(e1)['median'][i]
            assert rows[2]['observed_features'][i] is None
        else:
            assert rows[2]['observed_features'][i] is not None
    assert [r['strength'] for r in rows]==[.25,.5,1.]


def test_d3_record_missingness_exact_counts_one_feature_and_reordering(e1):
    ids=[f'population:{i}' for i in range(100)]
    rows=telemetry(e1,values=np.ones((100,8)),ids=ids)
    reverse=telemetry(e1,values=np.ones((100,8)),ids=ids[::-1])
    assert {r['variant_id']:r for r in rows}=={r['variant_id']:r for r in reverse}
    affected=[]
    for severity,expected in enumerate([5,10,20]):
        variants=[r for r in rows if r['domain']=='D3' and r['severity']==severity]
        assert len(variants)==100
        selected={r['source_id'] for r in variants if any(r['missing_mask'])}
        assert len(selected)==expected
        affected.append(selected)
        for r in variants:
            assert sum(r['missing_mask']) in [0,1]
            assert r['missingness_unit']=='RECORD' and r['missing_features_per_affected_record']==1
            assert r['affected_record_count']==expected and r['record_population_size']==100
            assert r['realized_record_missing_rate']==expected/100
    assert affected[0]<=affected[1]<=affected[2]


def test_d3_small_population_rounds_record_count_half_up_and_logs_realized_rate(e1):
    rows=telemetry(e1,values=np.ones((30,8)),ids=[f'small:{i}' for i in range(30)])
    for severity,expected in enumerate([2,3,6]):
        variants=[r for r in rows if r['domain']=='D3' and r['severity']==severity]
        assert sum(any(r['missing_mask']) for r in variants)==expected
        assert all(r['record_count_rounding']=='floor(N*rate+0.5)' for r in variants)
        assert all(r['realized_record_missing_rate']==expected/30 for r in variants)


def test_bounds_are_reported_without_silent_clipping(e1):
    rows=telemetry(e1,values=np.full((3,8),100.),bounds=[[0.,1.]]*8)
    clean=next(r for r in rows if r['domain']=='D0')
    assert clean['features']==[100.]*8 and clean['bounds_violations']==8 and clean['clipped_cells']==0
    assert clean['bounds_policy']=='REPORT_ONLY_NO_CLIP'


@pytest.mark.parametrize('split',['train','test'])
def test_preparation_generators_refuse_non_validation_or_synthetic_inputs(e1,split):
    with pytest.raises(ValueError,match='preparation'):
        list(e1.vision_variants(image(),'source','driver',source_split=split))
    with pytest.raises(ValueError,match='preparation'):
        list(e1.telemetry_variants(np.ones((1,8)),['Safe'],['source'],statistics(e1),
             missing_rates=[.05,.1,.2],drift_direction=[1]*8,bounds=None,source_split=split))


def test_missing_protocol_parameters_and_duplicate_ids_refuse(e1):
    for rates,direction,ids in [(None,[1]*8,['a']),([.05,.1,.2],None,['a']),([.05,.1,.2],[1]*8,['a','a'])]:
        with pytest.raises(ValueError):
            list(e1.telemetry_variants(np.ones((len(ids),8)),['Safe']*len(ids),ids,statistics(e1),
                 missing_rates=rates,drift_direction=direction,bounds=None,source_split='synthetic'))


def test_independent_qc_is_required_before_f1_eligibility(e1):
    assert e1.qc_decision()['status']=='PENDING' and not e1.qc_decision()['f1_eligible']
    with pytest.raises(ValueError):e1.qc_decision(valid=True)
    assert e1.qc_decision(valid=True,reviewer='independent-reviewer',reason='action remains visible')['f1_eligible']
    invalid=e1.qc_decision(valid=False,reviewer='independent-reviewer',reason='phone removed by crop')
    assert invalid['status']=='INVALID' and not invalid['f1_eligible'] and invalid['retain_for_flip_analysis']


def test_4500_synthetic_sources_produce_45000_shared_variants(e1):
    count=0;affected=[0,0,0]
    for row in e1.telemetry_variants(np.ones((4500,8)),['Safe']*4500,
        [f'synthetic:{i}' for i in range(4500)],statistics(e1),missing_rates=[.05,.1,.2],
        drift_direction=[1]*8,bounds=None,source_split='synthetic'):
        count+=1
        if row['domain']=='D3':
            assert sum(row['missing_mask']) in [0,1]
            affected[row['severity']]+=int(any(row['missing_mask']))
    assert count==45000
    assert affected==[225,450,900]
