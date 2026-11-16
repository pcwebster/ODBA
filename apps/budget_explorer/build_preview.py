import argparse,csv,hashlib,json,math
from pathlib import Path
from urllib.parse import urlsplit
import duckdb
from build_o1_explorer import build_o1

def read(path):
    with path.open(encoding='utf-8-sig',newline='') as fh:
        return list(csv.DictReader(fh))

def unique(rows,key):
    result={key(r):r for r in rows}
    if len(result)!=len(rows): raise ValueError("duplicate key")
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("green_book",type=Path);p.add_argument("odba",type=Path);p.add_argument("out",type=Path)
    a=p.parse_args()
    g=read(a.green_book)
    assert hashlib.sha256(a.green_book.read_bytes()).hexdigest()=='8bc67dae22c6baff30bc55c2a73f0a84734a28cce7b2f64eda23ec6d11f94364', 'Unexpected historical CSV bytes'
    assert len(g)==760 and all(r['source_year_status']=='Historical' and r['reconciliation_status']=='Within rounding tolerance' for r in g)
    unique(g,lambda r:(r['funding_fy'],r['military_department'],r['dollar_basis']))
    q=a.odba/'output'; c=q/'consumption'
    par=q/'fact_budget_line_items.parquet'
    fields='record_id,budget_year,service_agency_acronym,service_agency_name,exhibit_type,source_file,line_item_number,line_item_title,program_element,appropriation_code,appropriation_name,description,justification'
    res=duckdb.connect().execute(f'SELECT {fields} FROM read_parquet(?)',[str(par)])
    cols=[d[0] for d in res.description]
    lookup=unique([dict(zip(cols,r)) for r in res.fetchall()],lambda r:r['record_id'])
    cycle=unique(read(c/'dim_budget_cycle.csv'),lambda r:(int(r['budget_year']),r['source_file']))
    fs=read(c/'fact_budget_long.csv')
    assert len(fs)==4384 and len(lookup)==1413
    req=[]
    for f in fs:
        if f['data_lifecycle_stage']!='Budget Request' or f['amount_basis']!='request': continue
        y=int(f['budget_year']); assert y==int(f['funding_fy'])
        h=lookup[f['record_id']]; assert (int(h['budget_year']),h['source_file'],h['service_agency_acronym'])==(y,f['source_file'],f['service_agency_acronym'])
        s=cycle[y,f['source_file']]; assert s['lifecycle_stage']=='Budget Request' and s['ingest_status']=='parsed' and s['acquisition_date']==f['data_vintage']
        url=s['source_url']; u=urlsplit(url)
        if not (u.scheme=='https' and u.netloc in {'comptroller.war.gov','comptroller.defense.gov'}): continue
        v=float(f['amount_musd']); assert math.isfinite(v)
        req.append(dict(h,year=y,amount=v,url=url,sha=s['sha256'],vintage=f['data_vintage'],funding=f['funding_type']))
    unique(req,lambda r:r['record_id'])
    o1=build_o1(a.odba)
    keys={'green_book':a.green_book,'facts':c/'fact_budget_long.csv','source_registry':c/'dim_budget_cycle.csv','record_details':par}
    payload=dict(o1=o1,history=[dict(year=int(r['funding_fy']),dep=r['military_department'],basis=r['dollar_basis'],v=int(r['budget_authority']),p=int(r['source_printed_page'])) for r in g],request=req,all_amount_rows=len(fs),total_records=len(lookup),hashes={k:hashlib.sha256(v.read_bytes()).hexdigest() for k,v in keys.items()})
    t=Path(__file__).with_name('template.html').read_text()
    safe=json.dumps(payload,ensure_ascii=True,separators=(',',':')).replace('<','\\u003c')
    a.out.write_text(t.replace('__PAYLOAD__',safe),encoding='utf-8')
    print(len(g),len(req),len({(r['year'],r['source_file']) for r in req}))

if __name__=='__main__':main()
