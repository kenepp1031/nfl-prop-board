import json, urllib.request, urllib.parse, time
K="CHi8Hy5CEE4khd46XNYL23dCFX96oUdw6qOt1Dnh"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"
def get(path):
    r=urllib.request.Request("https://api.bettingpros.com/v3/"+path,headers={"x-api-key":K,"User-Agent":UA})
    return json.load(urllib.request.urlopen(r,timeout=30))
ev=get("events?sport=NFL&season=2026&week=2")["events"]
eids=":".join(str(e["id"]) for e in ev)
MK={103:"passing yards",107:"rushing yards",105:"receiving yards",406:"rush+rec yards",
    102:"passing TDs",101:"interceptions",78:"anytime TD"}
print(f"{'market':<18}{'offers':>7}{'DK':>6}{'FD':>6}  example")
for mid,name in MK.items():
    offers=[]; page=1
    while True:
        d=get(f"offers?sport=NFL&market_id={mid}&event_id={eids}&limit=10&page={page}")
        offers+=d.get("offers",[]); pg=d.get("_pagination",{})
        if page>=pg.get("total_pages",1) or page>40: break
        page+=1; time.sleep(0.12)
    dk=fd=0; ex=""
    for o in offers:
        ids={b["id"] for s in o.get("selections",[]) for b in s.get("books",[]) if b.get("lines")}
        if 12 in ids: dk+=1
        if 10 in ids: fd+=1
        if not ex and 12 in ids:
            nm=o["participants"][0]["name"]
            for s in o["selections"]:
                for b in s["books"]:
                    if b["id"]==12 and b.get("lines"):
                        l=b["lines"][0]; ex=f"{nm} {s['label']} {l.get('line')} @ {l.get('cost')}"; break
                if ex: break
    print(f"{name:<18}{len(offers):>7}{dk:>6}{fd:>6}  {ex}")
