import test from 'node:test';
import assert from 'node:assert/strict';
import { inspectPurchaseDryRun as inspect } from './purchase_dry_run_coordinator.mjs';

const plan = () => ({race_date:'2026-11-08',stadium_number:1,race_number:7,
  tickets:[{combination:'1-2-3',yen:500},{combination:'2-3-4',yen:1000}]});
const review = () => ({...plan(),total_yen:1500});
const receipt = () => ({...review(),receipt_status:'ACCEPTED'});
function map() {
  const selector = name => ({id:'safe-fixture-'+name});
  const node = (name, editable=false) => ({
    resourceId:'safe-fixture-'+name,visible:true,password:false,
    clickable:!editable,editable,
  });
  const lanes = Object.fromEntries([1,2,3].map(p=>[String(p),
    Object.fromEntries([1,2,3,4,5,6].map(n=>[n,selector('lane'+p+'-'+n)]))]));
  const samples = {venue:[node('venue')],race:[node('race')],trifecta:[node('trifecta')],
    lane1:[node('lane1-1')],lane2:[node('lane2-2')],lane3:[node('lane3-3')],
    amount:[node('amount',true)],add:[node('add')],review:[node('review'),node('next')],
    confirmation:[node('confirmation-total',true),node('review-title'),node('submit')],
    receipt:[node('receipt-title')]};
  return {profile:{
    venues:{1:selector('venue')},races:{7:selector('race')},trifecta:selector('trifecta'),
    lanes,amount:selector('amount'),add:selector('add'),review:selector('review'),
    finalization:{next:selector('next'),confirmAmount:selector('confirmation-total'),
      title:selector('review-title'),submit:selector('submit'),
      rowId:'fixture-row',totalId:'fixture-total',rowPattern:'^row$',totalPattern:'^total$'},
    receipt:{title:selector('receipt-title'),contractId:'fixture-contract',
      rowId:'fixture-row',totalId:'fixture-total',contractPattern:'^contract$',
      rowPattern:'^row$',totalPattern:'^total$'}},
    samples,selection:{stadiumNumber:1,raceNumber:7,combination:'1-2-3'}};
}
const input = (mode='CALIBRATION') => ({mode,plan:plan(),journal:[],
  controlMap:map(),review:review(),receipt:receipt()});
test('calibration is explicitly no-submit',()=>{const x=inspect(input());assert.equal(x.classification,'OFFLINE_CALIBRATION_ONLY');assert.equal(x.ready_for_offline_dry_run,true);assert.equal(x.ready_for_live_submission,false);assert.equal(x.purchase_confirmed,false)});
test('review match is still offline',()=>{const x=inspect(input('REVIEW'));assert.equal(x.classification,'OFFLINE_REVIEW_ONLY');assert.equal(x.ready_for_live_submission,false)});
test('matching receipt cannot prove official acceptance',()=>{const x=inspect(input('RECEIPT_AUDIT'));assert.equal(x.classification,'OFFLINE_RECEIPT_AUDIT_ONLY');assert.equal(x.purchase_confirmed,false)});
test('invalid or unknown mode fails closed',()=>{for(const x of [null,{},[],{...input(),mode:'SUBMIT'}])assert.equal(inspect(x).classification,'UNAVAILABLE')});
test('journal missing or corrupted blocks all modes',()=>{for(const mode of ['CALIBRATION','REVIEW','RECEIPT_AUDIT'])for(const journal of [null,{},[{fingerprint:'bad',state:'UNKNOWN'}]])assert.equal(inspect({...input(mode),journal}).stage,'REPLAY')});
test('previous UNKNOWN submission blocks even synthetic receipt match',()=>{const i=input('RECEIPT_AUDIT');const probe=inspect(i);i.journal=[{fingerprint:probe.fingerprint,state:'UNKNOWN'}];assert.equal(inspect(i).reason,'DUPLICATE_OR_UNCERTAIN_SUBMISSION')});
test('previous REJECTED attempt also blocks automatic retry',()=>{const i=input();const probe=inspect(i);i.journal=[{fingerprint:probe.fingerprint,state:'REJECTED'}];assert.equal(inspect(i).stage,'REPLAY')});
test('unmapped selector blocks all stages',()=>{const i=input('RECEIPT_AUDIT');delete i.controlMap.profile.finalization.submit;assert.equal(inspect(i).stage,'CONTROL_MAP')});
test('ambiguous selector blocks dry run',()=>{const i=input();i.controlMap.samples.venue.push({...i.controlMap.samples.venue[0]});assert.equal(inspect(i).reason,'CONTROL_MAP_NOT_CALIBRATED')});
test('mismatched review blocks receipt audit',()=>{const i=input('RECEIPT_AUDIT');i.review.total_yen=1600;assert.equal(inspect(i).stage,'REVIEW')});
test('mismatched receipt blocks receipt audit',()=>{const i=input('RECEIPT_AUDIT');i.receipt.total_yen=1600;assert.equal(inspect(i).stage,'RECEIPT_AUDIT')});
test('no sensitive raw review or receipt strings appear in result',()=>{const i=input('RECEIPT_AUDIT');i.receipt.raw_text='secret=do-not-export';i.review.password='do-not-export';assert.equal(JSON.stringify(inspect(i)).includes('do-not-export'),false)});
test('bad plan cannot reach selector stage',()=>{const i=input();i.plan.tickets[0].yen=50;assert.equal(inspect(i).stage,'REPLAY')});
test('receipt audit cannot skip missing review',()=>{const i=input('RECEIPT_AUDIT');i.review=null;assert.equal(inspect(i).stage,'REVIEW')});
