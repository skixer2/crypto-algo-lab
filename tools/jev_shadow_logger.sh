#!/bin/bash
# JEV shadow logger: every 8h at funding settlements (00/08/16 UTC) — state -> typed questions -> CSV log.
# Lawful test of an LLM advisor: LIVE ONLY (backtests of LLMs are hindsight-contaminated).
cd /home/node/.openclaw/workspace/crypto
KEY=$(grep '^TYPESAFE_API_KEY=' /home/node/.openclaw/.env | cut -d= -f2)
LOG=data/jev_shadow/jev_shadow.csv
[ -f "$LOG" ] || echo "ts_utc,eth_close,eth_high_48h,eth_low_48h,eth_ret_24h_pct,btc_mom_30d,mkt_choice,mkt_p_bull,mkt_p_bear,mkt_p_range,mkt_conf,entry_choice,entry_p_yes,entry_conf" >> "$LOG"
while true; do
  NOW=$(date -u +%s)
  NEXT=$(( (NOW/28800 + 1) * 28800 ))
  sleep $(( NEXT - NOW + 60 ))
  STATE=$(MPLCONFIGDIR=/tmp/mpl python3 << 'PYEOF' 2>/dev/null
import json, urllib.request, time
def get(u):
    return json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent":"curl/8.0"}), timeout=20))
try:
    cl = [float(x[4]) for x in get("https://www.okx.com/api/v5/market/candles?instId=ETH-USDT-SWAP&bar=15m&limit=200")['data']][::-1]
    btc = [float(x[4]) for x in get("https://www.okx.com/api/v5/market/candles?instId=BTC-USDT-SWAP&bar=1D&limit=35")['data']][::-1]
    print(json.dumps({"context":"ETH-USDT perpetual 15m. Judgments for the next 8 hours.","eth_close":cl[-1],"eth_high_48h":max(cl[-192:]),"eth_low_48h":min(cl[-192:]),"eth_ret_24h_pct":round((cl[-1]/cl[-96]-1)*100,2),"btc_mom_30d_ratio":round(btc[-1]/btc[-31],4),"timestamp_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())}))
except Exception:
    pass
PYEOF
)
  [ -z "$STATE" ] && continue
  cat > /tmp/jev_p.json <<EOP
{"state": $STATE, "model": "jev-latest", "questions": {
  "market_state": {"type":"choice","choices":["bull","bear","range"],"criteria":{"bull":"trend up, higher highs likely next 8h","bear":"trend down, lower lows likely","range":"chop, no directional edge"}},
  "take_new_breakout_entries": {"type":"choice","choices":["yes","no"],"criteria":{"yes":"fresh 48h-high breakouts likely to follow through","no":"breakouts likely to fail or chop"}}}}
EOP
  RESP=$(curl -s -m 90 -X POST https://api.typesafe.ai/v1/systemone -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" -d @/tmp/jev_p.json)
  echo "$STATE|$RESP" | python3 -c "
import sys, json, csv
line = sys.stdin.read()
state_s, resp_s = line.split('|', 1)
try:
    st = json.loads(state_s); r = json.loads(resp_s)['answers']
    m, e = r['market_state'], r['take_new_breakout_entries']
    row = [st['timestamp_utc'], st['eth_close'], st['eth_high_48h'], st['eth_low_48h'], st['eth_ret_24h_pct'], st['btc_mom_30d_ratio'],
           m['choice'], m['probabilities']['bull'], m['probabilities']['bear'], m['probabilities']['range'], m['confidence'],
           e['choice'], e['probabilities']['yes'], e['confidence']]
    with open('data/jev_shadow/jev_shadow.csv', 'a') as f: csv.writer(f).writerow(row)
except Exception as ex:
    pass"
done
