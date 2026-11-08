import test from 'node:test';
import assert from 'node:assert/strict';
import {evaluate} from './live_feed_trial_metrics.mjs';
const deadline=1000000;
const a=(stage,overrides={})=>({stage,request_ms:520000,received_ms:521000,complete:true,permission_verified:true,race_identity_verified:true,preview_6_st_weather_complete:true,odds_120_positive_complete:true,preview_observed_ms:500000,weather_observed_ms:500000,odds_observed_ms:500000,...overrides});
const t=(id,attempts)=>({id,deadline_ms:deadline,attempts});
test('zero population yields null rates',()=>assert.equal(evaluate([]).final_complete_rate,null));
test('T8 complete',()=>assert.equal(evaluate([t('a',[a('T8')])]).final_complete,1));
test('T5 rescue',()=>assert.equal(evaluate([t('a',[a('T8',{complete:false}),a('T5',{request_ms:700000,received_ms:701000,preview_observed_ms:700000,weather_observed_ms:700000,odds_observed_ms:700000})])]).t5_rescued,1));
test('unattempted remains unavailable, not SKIP',()=>{const x=evaluate([t('a',[])]);assert.equal(x.unavailable,1);assert.equal(x.skips,0);});
test('unknown odds source time rejected',()=>assert.equal(evaluate([t('a',[a('T8',{odds_observed_ms:null})])]).final_complete,0));
test('stale weather rejected',()=>assert.equal(evaluate([t('a',[a('T8',{weather_observed_ms:370000})])]).final_complete,0));
test('permission absent rejected',()=>assert.equal(evaluate([t('a',[a('T8',{permission_verified:false})])]).final_complete,0));
test('late response rejected',()=>assert.equal(evaluate([t('a',[a('T8',{received_ms:deadline})])]).final_complete,0));
test('duplicate race rejected',()=>assert.throws(()=>evaluate([t('a',[]),t('a',[])])));
test('duplicate stage rejected',()=>assert.throws(()=>evaluate([t('a',[a('T8'),a('T8')])])));
test('unnecessary T5 rejected',()=>assert.throws(()=>evaluate([t('a',[a('T8'),a('T5')])])));
test('incomplete odds rejected',()=>assert.equal(evaluate([t('a',[a('T8',{odds_120_positive_complete:false})])]).final_complete,0));

test('T5 rescue denominator is actually attempted retries',()=>{const x=evaluate([t('a',[a('T8',{complete:false}),a('T5')]),t('b',[a('T8',{complete:false})])]);assert.equal(x.t5_eligible,2);assert.equal(x.t5_attempted,1);assert.equal(x.t5_rescue_rate,1);assert.equal(x.t5_attempt_rate,0.5);});
test('T5 before T8 is rejected by stage windows',()=>assert.throws(()=>evaluate([t('a',[a('T8',{complete:false,request_ms:600000,received_ms:601000}),a('T5',{request_ms:500000})])]),/stage window/));
test('T5 zero attempted denominator remains null',()=>assert.equal(evaluate([t('a',[a('T8',{complete:false})])]).t5_rescue_rate,null));

test('T5 without T8 cannot count as rescue',()=>assert.throws(()=>evaluate([t('a',[a('T5',{request_ms:700000,received_ms:701000})])]),/requires recorded T8/));
test('T8 label with T5-clock timestamp rejected',()=>assert.throws(()=>evaluate([t('a',[a('T8',{request_ms:700000,received_ms:701000})])]),/stage window/));
test('T5 label with T8-clock timestamp rejected',()=>assert.throws(()=>evaluate([t('a',[a('T8',{complete:false}),a('T5',{request_ms:520000})])]),/stage window/));
test('request after deadline rejected',()=>assert.throws(()=>evaluate([t('a',[a('T8',{request_ms:deadline+1000,received_ms:deadline+2000})])]),/stage window/));
