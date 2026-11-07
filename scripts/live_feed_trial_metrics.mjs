#!/usr/bin/env node
// Offline-only trial evaluator. No network access or provider credentials.
import { readFileSync } from 'node:fs';
export function evaluate(trials) {
  if (!Array.isArray(trials)) throw Error('trials must be an array');
  const ids=new Set(), result={registered:trials.length,t8_attempted:0,t8_complete:0,t5_eligible:0,t5_attempted:0,t5_rescued:0,final_complete:0,unavailable:0,skips:0,buys:0};
  for(const t of trials){
    if(!t||typeof t.id!=='string'||!t.id||ids.has(t.id)||!Number.isFinite(t.deadline_ms)||!Array.isArray(t.attempts))throw Error('invalid/duplicate registered race');
    ids.add(t.id);const stages=new Map();
    for(const a of t.attempts){
      if(!a||!['T8','T5'].includes(a.stage)||stages.has(a.stage)||![a.request_ms,a.received_ms].every(Number.isFinite)||a.received_ms<a.request_ms)throw Error('invalid attempt');
      stages.set(a.stage,a);
    }
    const valid=a=>!!a&&a.received_ms<t.deadline_ms&&a.complete===true&&a.permission_verified===true&&a.race_identity_verified===true&&a.preview_6_st_weather_complete===true&&a.odds_120_positive_complete===true&&['preview_observed_ms','weather_observed_ms','odds_observed_ms'].every(k=>Number.isFinite(a[k])&&a[k]<=a.received_ms&&a.received_ms-a[k]<=120000&&a[k]<t.deadline_ms);
    const t8=stages.get('T8'),t5=stages.get('T5');if(t8)result.t8_attempted++;
    const good8=valid(t8);if(good8)result.t8_complete++;else result.t5_eligible++;
    if(t5){if(good8)throw Error('unnecessary T5 after complete T8');if(t8&&t5.request_ms<t8.request_ms)throw Error('T5 request precedes T8');result.t5_attempted++;}
    const good5=!good8&&valid(t5);if(good5)result.t5_rescued++;
    if(good8||good5)result.final_complete++;else result.unavailable++;
  }
  const rate=(n,d)=>d===0?null:n/d;
  return {...result,t8_complete_rate:rate(result.t8_complete,result.registered),t5_rescue_rate:rate(result.t5_rescued,result.t5_attempted),t5_attempt_rate:rate(result.t5_attempted,result.t5_eligible),final_complete_rate:rate(result.final_complete,result.registered)};
}
if(process.argv[1]&&import.meta.url===new URL('file://'+process.argv[1]).href)console.log(JSON.stringify(evaluate(JSON.parse(readFileSync(process.argv[2],'utf8')).trials),null,2));
