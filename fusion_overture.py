"""Fusion hors ligne d'un export Overture Places GeoJSON avec Zero to Host.
Usage: python fusion_overture.py base.csv overture.geojson sortie.csv
Aucune API et aucune modification automatique du dépôt GitHub.
"""
import csv, json, math, re, sys, unicodedata
from pathlib import Path

FIELDS = ['nom','categorie','lat','lon','source','public_cible']
BUSINESS_TERMS = ('industrial','manufactur','factory','logistic','warehouse','construction','engineering','business','company','corporate','office','professional','hospital','university','research')
TOURISM_TERMS = ('museum','tourist','attraction','theme_park','theater','theatre','conference','convention','exhibition')

def normalize(s):
    s = unicodedata.normalize('NFKD', str(s).casefold())
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]+','',s)

def km(a,b,c,d):
    r=math.pi/180; x=(c-a)*r; y=(d-b)*r*math.cos((a+c)*r/2)
    return 6371*math.hypot(x,y)

def parse_feature(f):
    p=f.get('properties') or {}; geom=f.get('geometry') or {}
    if geom.get('type') != 'Point': return None
    xy=geom.get('coordinates') or []
    if len(xy)<2: return None
    lon,lat=xy[:2]
    if not isinstance(lat,(float,int)) or not isinstance(lon,(float,int)) or not (47<=lat<=56 and 5<=lon<=16):return None
    names=p.get('names') or {}
    primary=names.get('primary') if isinstance(names,dict) else None
    if isinstance(primary,dict):primary=primary.get('value')
    name=primary or p.get('name')
    if not isinstance(name,str) or len(name.strip())<3:return None
    cats=p.get('categories') or {}
    vals=[]
    if isinstance(cats,dict): vals=[cats.get('primary')] + (cats.get('alternate') or [])
    elif isinstance(cats,list):vals=cats
    category=' '.join(str(v or '') for v in vals).lower()
    if any(t in category for t in TOURISM_TERMS):
        audience='tourisme'; label='Attraction touristique'
        if 'museum' in category:label='Musée'
        elif 'theater' in category or 'theatre' in category:label='Théâtre'
        elif 'conference' in category or 'convention' in category or 'exhibition' in category:label='Salon / centre de congrès'
    elif any(t in category for t in BUSINESS_TERMS):
        audience='professionnel';label='Entreprise'
        if 'hospital' in category:label='Hôpital'
        elif 'university' in category:label='Université'
        elif 'research' in category:label='Recherche / laboratoire'
    else:
        return None # ne pas classer automatiquement restaurants et commerces comme employeurs industriels
    identifier=f.get('id') or p.get('id')
    source=f'https://explore.overturemaps.org/?id={identifier}' if identifier else 'https://overturemaps.org/'
    return dict(nom=name.strip(),categorie=label,lat=round(lat,7),lon=round(lon,7),source=source,public_cible=audience)

def features(path):
    with open(path,encoding='utf-8-sig') as h:
        first=h.read(2048);h.seek(0)
        if first.lstrip().startswith('{'):
            data=json.load(h)
            if data.get('type')=='FeatureCollection':yield from data.get('features',[])
            elif data.get('type')=='Feature':yield data
            else:raise ValueError('GeoJSON non reconnu')
        else:
            for line in h:
                if line.strip():yield json.loads(line)

def main(base, overture, output):
    with open(base,encoding='utf-8-sig',newline='') as h:
        old=list(csv.DictReader(h))
    if not old or not set(FIELDS).issubset(old[0]):raise ValueError('Base CSV incompatible')
    kept=[{k:r[k] for k in FIELDS} for r in old]
    buckets={}
    def add_index(row):
        try:
            lat,lon=float(row['lat']),float(row['lon'])
            buckets.setdefault((int(lat*100),int(lon*100)),[]).append(row)
        except (ValueError,TypeError):pass
    for row in kept:add_index(row)
    stats={'base_initiale':len(kept),'overture_lus':0,'candidats_pertinents':0,'doublons_probables':0,'ajoutes':0}
    for feat in features(overture):
        stats['overture_lus']+=1
        row=parse_feature(feat)
        if row is None:continue
        stats['candidats_pertinents']+=1
        a,b=int(row['lat']*100),int(row['lon']*100)
        nearby=(r for i in range(a-1,a+2) for j in range(b-1,b+2) for r in buckets.get((i,j),[]))
        duplicate=any(normalize(row['nom'])==normalize(r['nom']) and km(float(row['lat']),float(row['lon']),float(r['lat']),float(r['lon']))<0.2 for r in nearby)
        if duplicate:stats['doublons_probables']+=1;continue
        kept.append(row);add_index(row);stats['ajoutes']+=1
    with open(output,'w',encoding='utf-8-sig',newline='') as h:
        w=csv.DictWriter(h,fieldnames=FIELDS);w.writeheader();w.writerows(kept)
    print(json.dumps(stats,ensure_ascii=False,indent=2))

if __name__=='__main__':
    if len(sys.argv)!=4:sys.exit('Usage: python fusion_overture.py base.csv overture.geojson sortie.csv')
    main(*sys.argv[1:])
