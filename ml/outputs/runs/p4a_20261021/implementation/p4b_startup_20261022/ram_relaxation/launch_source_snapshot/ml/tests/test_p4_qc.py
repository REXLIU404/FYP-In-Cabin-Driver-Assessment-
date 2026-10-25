"""Independent human QC workflow, never synthetic ratings as evidence."""
import importlib
import hashlib
import json

import pytest
from PIL import Image


@pytest.fixture
def qc():
    try:return importlib.import_module('ml.experiments.p4_qc')
    except ModuleNotFoundError as error:
        if error.name!='ml.experiments.p4_qc':raise
        pytest.fail('Missing blinded P4 QC workflow')


def cases():
    return [(Image.new('RGB',(4,4),'white'),{'variant_id':f's:{family}:{s}',
        'source_id':'s','driver_id':'p','class_id':'c0','source_split':'synthetic',
        'condition':family,'severity':s,'source_path':'/secret/c0/a.jpg','prediction':'c9'})
        for family,sevs in [('clean',[0]),('occlusion',[0,1,2])] for s in sevs]


def test_selection_is_hash_ranked_capped_and_order_independent(qc):
    rows=[{'source_id':f'x{i}','driver_id':'p','class_id':'c0'} for i in range(8)]
    selected=qc.select_sources(rows)
    assert len(selected)==5
    assert selected==qc.select_sources(list(reversed(rows)))
    assert len(qc.select_sources(rows+[{'source_id':'y','driver_id':'q','class_id':'c1'}]))==6


def test_blind_kit_has_no_source_label_driver_condition_or_prediction(qc,tmp_path):
    out=tmp_path/'kit';manifest=qc.build_review_kit(cases(),out,reviewer='R1')
    blind=json.loads((out/'blind_cases.json').read_text())
    assert len(blind)==4 and all(set(x)=={'case_id','image'} for x in blind)
    assert len({x['case_id'] for x in blind})==4
    assert all(x['source_id']=='s' for x in manifest['restricted_cases'])
    assert (out/'review.html').exists() and (out/'R1.csv').exists()
    assert all(x['status']=='UNREVIEWED' for x in manifest['restricted_cases'])
    assert manifest['human_ratings_count']==0


def judgement(case_id, reviewer='R1', choice='c0',evidence_retained=True):
    return {'case_id':case_id,'reviewer':reviewer,'choice':choice,'reason':'visible hand/action',
            'timestamp':'2026-10-21T10:00:00+08:00','evidence_retained':evidence_retained,
            'duration_seconds':3.2,'status':'VALID'}


def test_reveal_requires_single_reviewer_locked_judgments_and_tamper_check(qc,tmp_path):
    manifest=qc.build_review_kit(cases(),tmp_path/'kit',reviewer='R1')
    attestation=qc.load_byte_attestation(tmp_path/'kit')
    ids=[r['case_id'] for r in manifest['restricted_cases']]
    a=qc.lock_blind_judgments([judgement(i) for i in ids],reviewer='R1',case_ids=ids,
        source_key_sha256=manifest['source_key_sha256'],attestation=attestation)
    with pytest.raises(ValueError):qc.reveal_sources(manifest,None,attestation=attestation)
    reveal=qc.reveal_sources(manifest,a,attestation=attestation);assert len(reveal)==4
    a['judgments'][0]['choice']='c1'
    with pytest.raises(ValueError):qc.reveal_sources(manifest,a,attestation=attestation)


def test_consensus_and_common_family_support_never_invent_validity(qc):
    assert qc.resolve_qc(None,'c0',preserved_cue=None)=='UNREVIEWED'
    assert qc.resolve_qc(judgement('i'),'c0',preserved_cue=True)=='VALID'
    assert qc.resolve_qc(judgement('i',choice='c1'),'c0',preserved_cue=True)=='UNCERTAIN'
    assert qc.resolve_qc(judgement('i'),'c0',preserved_cue=False)=='INVALID'
    assert qc.resolve_qc(judgement('i'),'c0',preserved_cue=None)=='UNCERTAIN'
    rows=[dict(r,status='VALID') for _,r in cases()]
    assert qc.common_valid_sources(rows,'occlusion')==['s']
    rows[-1]['status']='UNREVIEWED'
    assert qc.common_valid_sources(rows,'occlusion')==[]


def test_finalization_requires_locked_choice_and_measured_postlock_cue_check(qc,tmp_path):
    manifest=qc.build_review_kit(cases(),tmp_path/'kit',reviewer='R1')
    attestation=qc.load_byte_attestation(tmp_path/'kit')
    ids=[r['case_id'] for r in manifest['restricted_cases']]
    locked=qc.lock_blind_judgments([judgement(i) for i in ids],reviewer='R1',case_ids=ids,
        source_key_sha256=manifest['source_key_sha256'],attestation=attestation)
    cue_checks=[{'case_id':i,'preserved_cue':True,'reason':'source action cue remains',
                 'duration_seconds':1.,'timestamp':'2026-10-21T11:00:00+08:00'} for i in ids]
    finalized=qc.finalize_qc(manifest,locked,cue_checks,attestation=attestation)
    assert all(r['status']=='VALID' and r['selected_class']=='c0' for r in finalized['cases'])
    assert finalized['reviewer_count']==1 and finalized['inter_rater_agreement'] is None
    assert finalized['ten_class_macro_f1_status']=='NOT_ESTIMABLE'
    cue_checks.pop()
    with pytest.raises(ValueError):qc.finalize_qc(manifest,locked,cue_checks,attestation=attestation)


def test_source_key_binding_prevents_reveal_under_another_case_mapping(qc,tmp_path):
    first=qc.build_review_kit(cases(),tmp_path/'one')
    attestation=qc.load_byte_attestation(tmp_path/'one')
    second=qc.build_review_kit([(image,dict(row,class_id='c1')) for image,row in cases()],tmp_path/'two')
    ids=[r['case_id'] for r in first['restricted_cases']]
    locked=qc.lock_blind_judgments([judgement(i) for i in ids],reviewer='R1',case_ids=ids,
        source_key_sha256=first['source_key_sha256'],attestation=attestation)
    with pytest.raises(ValueError):qc.reveal_sources(second,locked,attestation=attestation)


def test_local_cli_reveals_only_after_lock_and_finalizes_real_input_files(qc,tmp_path):
    kit=tmp_path/'kit';manifest=qc.build_review_kit(cases(),kit)
    with pytest.raises(FileNotFoundError):qc.main(['reveal','--kit',str(kit)])
    ids=[r['case_id'] for r in manifest['restricted_cases']]
    ratings=tmp_path/'synthetic_ratings.json';ratings.write_text(json.dumps([judgement(i) for i in ids]))
    assert qc.main(['lock','--kit',str(kit),'--ratings',str(ratings)])==0
    assert qc.main(['reveal','--kit',str(kit)])==0
    source_page=(kit/'restricted/source_review.html').read_text()
    assert 'preserved_cue' in source_page and '/secret/c0/a.jpg' in source_page
    cues=tmp_path/'synthetic_cues.json';cues.write_text(json.dumps([
        {'case_id':i,'preserved_cue':True,'reason':'cue still visible',
         'duration_seconds':2.,'timestamp':'2026-10-21T12:00:00+08:00'} for i in ids]))
    assert qc.main(['finalize','--kit',str(kit),'--cue-checks',str(cues)])==0
    final=json.loads((kit/'restricted/R1_qc_final_locked.json').read_text())
    assert final['counts']=={'VALID':4,'INVALID':0,'UNCERTAIN':0}
    assert final['blind_timing']['mean_seconds']==3.2
    assert final['source_check_timing']['mean_seconds']==2.


def test_boolean_is_not_a_measured_duration_and_numeric_is_not_a_cue(qc,tmp_path):
    manifest=qc.build_review_kit(cases(),tmp_path/'kit')
    attestation=qc.load_byte_attestation(tmp_path/'kit')
    ids=[r['case_id'] for r in manifest['restricted_cases']]
    ratings=[judgement(i) for i in ids]
    ratings[0]['duration_seconds']=True
    with pytest.raises(ValueError):
        qc.lock_blind_judgments(ratings,reviewer='R1',case_ids=ids,
            source_key_sha256=manifest['source_key_sha256'],attestation=attestation)
    ratings=[judgement(i) for i in ids]
    locked=qc.lock_blind_judgments(ratings,reviewer='R1',case_ids=ids,
        source_key_sha256=manifest['source_key_sha256'],attestation=attestation)
    cues=[{'case_id':i,'preserved_cue':True,'reason':'visible cue',
           'duration_seconds':1.,'timestamp':'2026-10-21T11:00:00+08:00'} for i in ids]
    cues[0]['duration_seconds']=True
    with pytest.raises(ValueError):qc.finalize_qc(manifest,locked,cues,attestation=attestation)
    cues[0]['duration_seconds']=1.;cues[0]['preserved_cue']=1
    with pytest.raises(ValueError):qc.finalize_qc(manifest,locked,cues,attestation=attestation)


def test_attestation_freezes_png_bytes_and_decoded_pixels_before_lock(qc,tmp_path):
    kit=tmp_path/'kit';manifest=qc.build_review_kit(cases(),kit)
    attestation=qc.load_byte_attestation(kit)
    assert attestation['scope']=='INITIAL_KIT_BYTE_FREEZE'
    assert len(attestation['cases'])==4
    row=manifest['restricted_cases'][0]
    Image.new('RGB',(4,4),'black').save(kit/'images'/f"{row['case_id']}.png")
    ids=[r['case_id'] for r in manifest['restricted_cases']]
    with pytest.raises(ValueError,match='PNG|pixel|byte'):
        qc.lock_blind_judgments([judgement(i) for i in ids],reviewer='R1',case_ids=ids,
            source_key_sha256=manifest['source_key_sha256'],attestation=attestation)


def val_cases(tmp_path):
    source=tmp_path/'val.png';Image.new('RGB',(4,4),'white').save(source)
    meta=tmp_path/'fixture_metadata.csv'
    meta.write_text('split,class_id,filename,driver_id,image_path,class_name\n'
        f'val,c0,val.png,p002,{source},normal_driving\n')
    sha=hashlib.sha256(source.read_bytes()).hexdigest()
    metadata_sha=hashlib.sha256(meta.read_bytes()).hexdigest()
    return source,[(Image.new('RGB',(4,4),'white'),{
        'variant_id':'vision-v1:c0/val.png:clean:0','source_id':'vision-v1:c0/val.png',
        'source_split':'val','class_id':'c0','driver_id':'p002','condition':'clean',
        'severity':0,'source_path':str(source),'source_sha256':sha,
        'metadata_path':str(meta),'metadata_sha256':metadata_sha,'params':{},
        'pixel_sha256':hashlib.sha256(bytes([255])*48).hexdigest(),'input_sha256':'x'*64})]


def test_original_source_tamper_stops_reveal_and_finalize(qc,tmp_path):
    source,items=val_cases(tmp_path);kit=tmp_path/'kit'
    manifest=qc.build_review_kit(items,kit);attestation=qc.load_byte_attestation(kit)
    ids=[r['case_id'] for r in manifest['restricted_cases']]
    locked=qc.lock_blind_judgments([judgement(i) for i in ids],reviewer='R1',case_ids=ids,
        source_key_sha256=manifest['source_key_sha256'],attestation=attestation)
    assert manifest['restricted_cases'][0]['input_sha256']=='x'*64
    Image.new('RGB',(4,4),'black').save(source)
    with pytest.raises(ValueError,match='source|Source'):
        qc.reveal_sources(manifest,locked,attestation=attestation)
    with pytest.raises(ValueError,match='source|Source'):
        qc.finalize_qc(manifest,locked,[],attestation=attestation)


@pytest.mark.parametrize('reason',['   ',7,None])
def test_postlock_cue_reason_requires_nonblank_text(qc,tmp_path,reason):
    kit=tmp_path/'kit';manifest=qc.build_review_kit(cases(),kit)
    attestation=qc.load_byte_attestation(kit)
    ids=[r['case_id'] for r in manifest['restricted_cases']]
    locked=qc.lock_blind_judgments([judgement(i) for i in ids],reviewer='R1',case_ids=ids,
        source_key_sha256=manifest['source_key_sha256'],attestation=attestation)
    cues=[{'case_id':i,'preserved_cue':True,'reason':reason,
           'duration_seconds':1.,'timestamp':'2026-10-21T11:00:00+08:00'} for i in ids]
    with pytest.raises(ValueError):qc.finalize_qc(manifest,locked,cues,attestation=attestation)


def test_current_legacy_freeze_is_exclusive_and_preserves_kit_bytes(qc,tmp_path):
    kit=tmp_path/'kit';qc.build_review_kit(cases(),kit)
    before={str(p.relative_to(kit)):p.read_bytes() for p in kit.rglob('*') if p.is_file()}
    qc.byte_attestation_path(kit).unlink()  # Test fixture simulates a pre-attestation kit.
    current=qc.attest_kit(kit)
    assert current['scope']=='CURRENT_KIT_BYTE_FREEZE' and not current['initial_generation_proof']
    assert all(r['parameter_provenance']=='UNRECORDED' for r in current['cases'])
    with pytest.raises(FileExistsError):qc.attest_kit(kit)
    assert before=={str(p.relative_to(kit)):p.read_bytes() for p in kit.rglob('*') if p.is_file()}


def test_malformed_test_kit_is_denied_before_any_image_read(qc,tmp_path):
    kit=tmp_path/'kit';manifest=qc.build_review_kit(cases(),kit)
    qc.byte_attestation_path(kit).unlink()
    for row in manifest['restricted_cases']:row['source_split']='test'
    manifest['source_key_sha256']=qc._digest({k:v for k,v in manifest.items() if k!='source_key_sha256'})
    (kit/'restricted/source_key.json').write_text(json.dumps(manifest))
    for p in (kit/'images').glob('*.png'):p.unlink()
    with pytest.raises(PermissionError):qc.attest_kit(kit)


def test_val_source_path_cannot_be_replaced_by_unverified_original(qc,tmp_path):
    _,items=val_cases(tmp_path)
    items[0][1]['source_path']='/must/not/open/test.jpg'
    with pytest.raises(PermissionError):qc.build_review_kit(items,tmp_path/'kit')


def test_new_kit_rejects_supplied_pixel_hash_that_does_not_match_image(qc,tmp_path):
    items=cases();items[0][1]['pixel_sha256']='0'*64
    with pytest.raises(ValueError,match='pixel'):
        qc.build_review_kit(items,tmp_path/'kit')


def formal_fixture(qc,tmp_path):
    """Only generated pixels/metadata; no actual held-out observation is used."""
    from ml.experiments import run_p4
    run=tmp_path/'synthetic_formal';run.mkdir()
    source,items=val_cases(tmp_path)
    row=items[0][1];metadata=tmp_path/'fixture_metadata.csv'
    metadata.write_text(metadata.read_text().replace('val,c0','test,c0'))
    row.update(source_split='test',metadata_sha256=hashlib.sha256(metadata.read_bytes()).hexdigest())
    protocol=run/'protocol.json'
    protocol.write_text((run_p4.ROOT/'ml/configs/p4_protocol.json').read_text())
    binding=run_p4.binding_for(protocol,run.name)
    approval=run/'synthetic_approval.json'
    approval.write_text(json.dumps(dict(binding,phase='P4-B',authorized=True,
        human_approval='SYNTHETIC_TEST_FIXTURE_ONLY',single_reviewer_amendment_approved=True)))
    spec=run/'execution_spec.json'
    spec.write_text(json.dumps(dict(binding=binding,protocol_path=str(protocol),
        run_dir=str(run),approval_path=str(approval))))
    from ml.experiments.p4_core import authorize_p4b
    token=authorize_p4b(json.loads(approval.read_text()),**binding)
    kit=run/'qc_review_kit'
    manifest=qc.build_review_kit(items,kit,authorization=token)
    return kit,manifest,spec,approval


def test_cli_execution_spec_carries_authorization_through_complete_synthetic_workflow(qc,tmp_path):
    kit,manifest,spec,_=formal_fixture(qc,tmp_path)
    qc.byte_attestation_path(kit).unlink()  # Simulate a legacy un-attested kit.
    assert qc.main(['attest','--kit',str(kit),'--execution-spec',str(spec)])==0
    ids=[r['case_id'] for r in manifest['restricted_cases']]
    ratings=tmp_path/'synthetic_ratings.json'
    ratings.write_text(json.dumps([judgement(case_id) for case_id in ids]))
    assert qc.main(['lock','--kit',str(kit),'--ratings',str(ratings),'--execution-spec',str(spec)])==0
    assert qc.main(['reveal','--kit',str(kit),'--execution-spec',str(spec)])==0
    cues=tmp_path/'synthetic_cues.json'
    cues.write_text(json.dumps([dict(case_id=case_id,preserved_cue=True,reason='synthetic cue',
        duration_seconds=1.,timestamp='2026-10-22T00:00:00Z') for case_id in ids]))
    assert qc.main(['finalize','--kit',str(kit),'--cue-checks',str(cues),'--execution-spec',str(spec)])==0
    final=json.loads((kit/'restricted/R1_qc_final_locked.json').read_text())
    assert final['counts']=={'VALID':1,'INVALID':0,'UNCERTAIN':0}


@pytest.mark.parametrize('mutation',['protocol','source','run','kit','approval'])
def test_cli_bad_binding_refuses_before_kit_bytes(qc,tmp_path,monkeypatch,mutation):
    kit,_,spec,approval=formal_fixture(qc,tmp_path)
    value=json.loads(spec.read_text())
    if mutation=='protocol':value['binding']['protocol_sha256']='0'*64
    elif mutation=='source':value['binding']['source_sha256']='0'*64
    elif mutation=='run':value['binding']['run_id']='different_run'
    elif mutation=='kit':value['run_dir']=str(tmp_path/'another_run')
    else:
        approved=json.loads(approval.read_text());approved['authorized']=False
        approval.write_text(json.dumps(approved))
    spec.write_text(json.dumps(value))
    monkeypatch.setattr(qc,'load_byte_attestation',lambda *args,**kwargs:pytest.fail('kit byte read before authorization'))
    with pytest.raises((ValueError,PermissionError)):
        qc.main(['reveal','--kit',str(kit),'--execution-spec',str(spec)])
