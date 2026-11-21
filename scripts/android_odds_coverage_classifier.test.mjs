import test from 'node:test';
import assert from 'node:assert/strict';
import { classifyAndroidOddsCoverage as classify } from './android_odds_coverage_classifier.mjs';
import { expectedTrifectaCombinations } from './android_odds_bridge_preflight.mjs';
const all=expectedTrifectaCombinations();
const make=(keys=all.slice(0,3),source='公式PC版')=>({
 odds:Object.fromEntries(keys.map(k=>[k,10.5])),source,diagnostics:[],fetchedAt:1794140000000,
});
test('120 unique official-labeled values remain unattested',()=>{
 const x=classify(make(all),all);
 assert.equal(x.classification,'ANDROID_120_VALUES_UNATTESTED');
 assert.equal(x.combination_count,120);
 assert.equal(x.eligible_for_buy,false);
 assert.equal(x.eligible_for_skip,false);
});
test('selected 3 odds are not mislabeled as 120',()=>{
 const x=classify(make(),all.slice(0,3));
 assert.equal(x.classification,'ANDROID_SELECTED_ONLY');
 assert.equal(x.coverage,'SELECTED_COMBINATIONS_ONLY');
});
test('selected 6 odds remain selected',()=>{
 assert.equal(classify(make(all.slice(0,6)),all.slice(0,6)).combination_count,6);
});
test('official smartphone label remains quarantined',()=>{
 assert.equal(classify(make(all,'公式スマホ版'),all).classification,'ANDROID_120_VALUES_UNATTESTED');
});
test('CSV selected odds are estimates',()=>{
 assert.equal(classify(make(all.slice(0,3),'BoatraceCSV推定'),all.slice(0,3)).classification,'BOATRACE_CSV_ESTIMATE');
});
test('CSV 120 values still cannot become actual live odds',()=>{
 const x=classify(make(all,'BoatraceCSV推定'),all);
 assert.equal(x.coverage,'ESTIMATED_120_VALUES');
 assert.equal(x.eligible_for_forecast,false);
});
test('unknown source cannot pass',()=>{
 assert.equal(classify(make(all,'official?'),all).classification,'UNAVAILABLE');
});
test('missing requested odds is unavailable not skip',()=>{
 assert.equal(classify(make(all.slice(0,2)),all.slice(0,3)).classification,'UNAVAILABLE');
});
test('extra unsolicited odds cannot establish 120 coverage',()=>{
 assert.equal(classify(make(all),all.slice(0,3)).reason,'UNREQUESTED_COMBINATION_PRESENT');
});
test('duplicate requested combinations fail closed',()=>{
 assert.equal(classify(make(),[all[0],all[0]]).classification,'UNAVAILABLE');
});
test('invalid combination fails closed',()=>{
 assert.equal(classify(make(['1-1-2']),['1-1-2']).classification,'UNAVAILABLE');
});
test('nonpositive odds rejected',()=>{
 const x=make();x.odds[all[0]]=0;
 assert.equal(classify(x,all.slice(0,3)).reason,'INVALID_ODDS_MAP');
});
test('infinite odds rejected',()=>{
 const x=make();x.odds[all[0]]=Infinity;
 assert.equal(classify(x,all.slice(0,3)).reason,'INVALID_ODDS_MAP');
});
test('empty map rejected',()=>{
 assert.equal(classify(make([]),all.slice(0,3)).classification,'UNAVAILABLE');
});
test('empty requested set rejected',()=>{
 assert.equal(classify(make(),[]).classification,'UNAVAILABLE');
});
test('malformed diagnostics rejected',()=>{
 const x=make();x.diagnostics=null;
 assert.equal(classify(x,all.slice(0,3)).classification,'UNAVAILABLE');
});
test('missing fetchedAt rejected',()=>{
 const x=make();delete x.fetchedAt;
 assert.equal(classify(x,all.slice(0,3)).classification,'UNAVAILABLE');
});
test('source timestamp is never invented',()=>{
 const x=classify(make(all),all);
 assert.equal(x.source_time_independently_verified,false);
 assert.equal(x.source_rights_independently_verified,false);
 assert.equal(Object.hasOwn(x,'source_observed_ms'),false);
});
