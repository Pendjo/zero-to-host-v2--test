"""Zero to Host V2 — pilote juridique autonome, sans dépendance Overpass."""
import json
import io
import re
from datetime import date
import pandas as pd
import requests
from pathlib import Path
import streamlit as st

st.set_page_config(page_title="Zero to Host | Pilote V2", page_icon="🏠", layout="wide")
DATA_PATH = Path(__file__).parent / 'data' / 'villes.json'
if not DATA_PATH.exists():
    st.error('Fichier manquant : data/villes.json. Conserve le dossier data de la V2.3 dans ton dépôt GitHub.')
    st.stop()
DATA = json.loads(DATA_PATH.read_text(encoding='utf-8'))
CITIES = {row['ville']: row for row in DATA}
st.title('🏠 Zero to Host — V2.8 pilote')
st.caption('Recherche libre, zones accessibles en voiture, Wikidata, réglementation, rentabilité et PDF')
st.warning('Prototype autonome : ne remplace pas votre application actuelle. Ne constitue pas un avis juridique.')
mode = st.radio('Mode de recherche', ['Ville enregistrée', 'Saisir librement une ville allemande'], horizontal=True)
if mode == 'Ville enregistrée':
    city = st.selectbox('Choisir une ville', sorted(CITIES))
else:
    city = st.text_input('Ville allemande à analyser', placeholder='Ex. München, Essen, Saarbrücken').strip()
    if not city:
        st.info('Saisis une ville allemande pour lancer son analyse.')
        st.stop()
address = st.text_input('Adresse du bien (facultative)', placeholder='Rue et numéro, code postal')
record = CITIES.get(city, {
    'ville': city, 'region': 'Allemagne', 'statut': 'À confirmer auprès de la mairie',
    'satzung': 'Non vérifiée', 'source': '', 'date_verification': 'Non vérifiée',
    'remarque': 'Aucune vérification juridique pour cette commune. Contacter la mairie et le Bauamt avant toute décision.'
})

st.subheader('🗺️ Carte interactive — recherche dans toute l’Allemagne')
st.caption('La carte affiche uniquement la commune recherchée et, si disponible, l’adresse du bien. Les trajets pilotes ne constituent pas une zone exhaustive de 20 minutes.')
# Coordonnées indicatives des centres-villes. Aucune donnée POI n'est inventée.
PILOT_CENTERS = {
    'Leonberg': (48.8015, 9.0161),
    'Ditzingen': (48.8267, 9.0675),
    'Rutesheim': (48.8086, 8.9450),
}

@st.cache_data(ttl=86400, show_spinner=False)
def geocode_address(query):
    """Géocodage optionnel, jamais présenté comme confirmé sans résultat."""
    try:
        response = requests.get(
            'https://photon.komoot.io/api/',
            params={'q': query, 'limit': 3},
            headers={'User-Agent': 'ZeroToHostPilot/2.1 (educational prototype)'},
            timeout=7,
        )
        response.raise_for_status()
        features = response.json().get('features', [])
        if not features:
            return None
        feature = features[0]
        lon, lat = feature['geometry']['coordinates']
        props = feature.get('properties', {})
        place = ', '.join(str(props[k]) for k in ('name', 'street', 'housenumber', 'city', 'postcode') if props.get(k))
        return {'lat': float(lat), 'lon': float(lon), 'label': place or 'Résultat du géocodeur', 'house': str(props.get('housenumber', '')).strip(), 'street': str(props.get('street', '')).strip(), 'city': str(props.get('city', '')).strip(), 'countrycode': str(props.get('countrycode', '')).lower()}
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError):
        return None

# Ne jamais utiliser Leonberg comme position de secours pour une autre ville.
if city in PILOT_CENTERS:
    center = PILOT_CENTERS[city]
    city_label = city
else:
    with st.spinner('Localisation de la commune…'):
        located_city = geocode_address(f'{city}, Deutschland')
    if not located_city or located_city.get('countrycode') != 'de':
        st.error('Commune non localisée avec certitude en Allemagne. Vérifie son nom et réessaie ; aucune analyse ne sera faite à partir de Leonberg.')
        st.stop()
    city_label = located_city['label']
    center = (located_city['lat'], located_city['lon'])
    st.info(f'Position approximative de la commune : {city_label}. Vérifie la carte avant de continuer.')

points = [{'lat': center[0], 'lon': center[1], 'lieu': f'Commune recherchée : {city}', 'type': 'Ville recherchée'}]
if address.strip():
    if st.button('📍 Localiser cette adresse sur la carte'):
        st.session_state['geocode_request'] = (address.strip(), city)
    if st.session_state.get('geocode_request') == (address.strip(), city):
        with st.spinner('Recherche de l’adresse…'):
            found = geocode_address(f'{address.strip()}, {city}, Deutschland')
        if found and found.get('countrycode') == 'de':
            points.append({'lat': found['lat'], 'lon': found['lon'], 'lieu': f'Adresse recherchée : {found["label"]}', 'type': 'Adresse géocodée'})
            center = (found['lat'], found['lon'])
            requested_house = re.search(r'\b(\d+[a-zA-Z]?)\b', address)
            actual_house = found['house']
            if requested_house and actual_house.lower() != requested_house.group(1).lower():
                st.warning(f'⚠️ Numéro différent : demandé {requested_house.group(1)}, trouvé {actual_house or "non renseigné"}. Le point est APPROXIMATIF : ne pas le considérer comme adresse confirmée.')
            elif requested_house and actual_house:
                st.success(f'Numéro de rue concordant : {found["label"]}. Vérifier aussi la rue et la commune.')
            else:
                st.info(f'Résultat de géocodage : {found["label"]}. Correspondance exacte non garantie.')
        else:
            st.warning('Adresse non trouvée ou service temporairement indisponible. La carte de la commune reste accessible.')

map_data = pd.DataFrame(points)
st.map(map_data, latitude='lat', longitude='lon', zoom=11, use_container_width=True)
st.caption(f'Point de référence utilisé : latitude {center[0]:.5f}, longitude {center[1]:.5f}.')
st.dataframe(map_data[['lieu', 'type']], hide_index=True, use_container_width=True)
st.subheader('🚗 Temps de trajet vers les trois centres pilotes')
st.caption('OSRM calcule les trajets depuis la ville ou adresse choisie uniquement vers Leonberg, Ditzingen et Rutesheim, même si la recherche porte sur une autre région. Ce n’est PAS une recherche des villes voisines en 20 minutes. Durées sans trafic.')
@st.cache_data(ttl=3600, show_spinner=False)
def route_to_centers(start_lat, start_lon):
    coords = ';'.join([f'{start_lon},{start_lat}'] + [f'{lon},{lat}' for lat, lon in PILOT_CENTERS.values()])
    try:
        resp = requests.get('https://router.project-osrm.org/table/v1/driving/' + coords,
            params={'sources': '0', 'destinations': '1;2;3', 'annotations': 'duration'},
            headers={'User-Agent': 'ZeroToHostPilot/2.2 (educational prototype)'}, timeout=9)
        resp.raise_for_status()
        result = resp.json()
        if result.get('code') != 'Ok':
            return None
        return result['durations'][0]
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError):
        return None

start_point = center
if st.button('🚗 Calculer les trajets (service externe)'):
    with st.spinner('Calcul des itinéraires routiers…'):
        durations = route_to_centers(*start_point)
    if durations is None:
        st.warning('Service routier indisponible. Aucun temps de trajet ne sera inventé.')
    else:
        route_rows = []
        for name, seconds in zip(PILOT_CENTERS, durations):
            route_rows.append({'Destination': name,
                'Durée estimée (min)': round(seconds / 60, 1) if seconds is not None else None,
                'Dans les 20 min': ('Oui' if seconds <= 1200 else 'Non') if seconds is not None else 'Indisponible'})
        st.dataframe(pd.DataFrame(route_rows), hide_index=True, use_container_width=True)
        st.caption('Source : OSRM (réseau routier OSM). Les résultats ne tiennent pas compte des embouteillages. Centre de ville approximatif.')

st.subheader('🏥🚉🏨 Facteurs de demande — recherche automatique')
st.caption('Source : Wikidata, données ouvertes collaboratives. Couverture partielle : une absence de résultat ne signifie PAS absence d’établissement. Cette recherche ne mesure pas la demande réelle Airbnb.')

# Wikidata Query Service est distinct d’Overpass. Le service public peut être indisponible.
# Les classes Wikidata retenues sont explicitement documentées ci-dessous.
POI_TYPES = {
    'Q16917': 'Hôpital',
    'Q55488': 'Gare ferroviaire',
    'Q27686': 'Hôtel',
    'Q3918': 'Université',
    'Q33506': 'Musée',
    'Q570116': 'Attraction touristique',
}

@st.cache_data(ttl=604800, show_spinner=False)
def wikidata_pois(lat, lon, radius_km):
    # Recherche de lieux géolocalisés avec instance directe ou sous-classe à un niveau.
    # LIMIT : résultats incomplets dans les zones denses ; aucun comptage exhaustif.
    types = ' '.join('wd:' + k for k in POI_TYPES)
    query = f"""
    SELECT DISTINCT ?item ?itemLabel ?coord ?kind WHERE {{
      SERVICE wikibase:around {{
        ?item wdt:P625 ?coord .
        bd:serviceParam wikibase:center 'Point({lon} {lat})'^^geo:wktLiteral .
        bd:serviceParam wikibase:radius '{radius_km}' .
      }}
      VALUES ?kind {{ {types} }}
      ?item wdt:P31/wdt:P279? ?kind .
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language 'fr,de,en'. }}
    }} LIMIT 180
    """
    try:
        response = requests.get(
            'https://query.wikidata.org/sparql',
            params={'query': query, 'format': 'json'},
            headers={'User-Agent': 'ZeroToHostStandortanalyse/2.3 (educational prototype; contact via github.com/Pendjo/zero-to-host-v2-test)', 'Accept': 'application/sparql-results+json'},
            timeout=(5, 18),
        )
        response.raise_for_status()
        bindings = response.json()['results']['bindings']
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return None
    results = []
    seen = set()
    for b in bindings:
        try:
            uri = b['item']['value']
            qid = uri.rsplit('/', 1)[-1]
            kind = b['kind']['value'].rsplit('/', 1)[-1]
            match = re.fullmatch(r'Point\((-?\d+(?:\.\d+)?) (-?\d+(?:\.\d+)?)\)', b['coord']['value'])
            if not match or kind not in POI_TYPES or (qid, kind) in seen:
                continue
            seen.add((qid, kind))
            longitude, latitude = map(float, match.groups())
            name = b.get('itemLabel', {}).get('value', qid)
            results.append({'categorie': POI_TYPES[kind], 'nom': name, 'lat': latitude, 'lon': longitude, 'source': uri, 'identifiant': qid})
        except (ValueError, KeyError, TypeError):
            continue
    return results

radius_km = st.slider('Rayon de recherche des établissements (km)', min_value=2, max_value=15, value=7)
st.caption('Point de départ : adresse géocodée si elle a été trouvée ; sinon centre approximatif de la ville choisie.')
if st.button('🔎 Rechercher automatiquement les établissements'):
    with st.spinner('Recherche Wikidata…'):
        st.session_state['poi_result'] = wikidata_pois(round(start_point[0], 5), round(start_point[1], 5), radius_km)
        st.session_state['poi_context'] = (round(start_point[0], 5), round(start_point[1], 5), radius_km)
context = (round(start_point[0], 5), round(start_point[1], 5), radius_km)
if st.session_state.get('poi_context') == context:
    results = st.session_state.get('poi_result')
    if results is None:
        st.warning('Wikidata est indisponible pour cette recherche. Aucun nombre ne peut être confirmé. Réessaie plus tard ou utilise un CSV.')
    elif not results:
        st.info('Aucun établissement référencé trouvé dans Wikidata pour cette requête. Cela ne signifie pas qu’il n’existe aucun établissement.')
    else:
        poi_df = pd.DataFrame(results)
        st.success(f'{len(poi_df)} correspondances Wikidata trouvées (résultats partiels, doublons possibles entre catégories).')
        st.dataframe(poi_df.groupby('categorie').size().reset_index(name='Fiches trouvées (non exhaustif)'), hide_index=True, use_container_width=True)
        st.map(poi_df, latitude='lat', longitude='lon', zoom=11, use_container_width=True)
        st.dataframe(poi_df[['categorie', 'nom', 'source']], hide_index=True, use_container_width=True, column_config={'source': st.column_config.LinkColumn('Fiche Wikidata')})
        st.download_button('📥 Télécharger ces résultats CSV', poi_df.to_csv(index=False).encode('utf-8-sig'), file_name='poi_wikidata_pilote.csv', mime='text/csv')
        st.caption('Attention : Wikidata n’est pas un annuaire exhaustif. Les entreprises, zones d’activité et événements ne sont pas couverts par cette recherche.')
else:
    st.info('Clique sur « Rechercher automatiquement » pour obtenir les lieux documentés disponibles.')

with st.expander('Option complémentaire : importer des lieux vérifiés par CSV', expanded=False):
    st.markdown('Colonnes requises : `categorie,nom,lat,lon,source,date_verification`.')
    template = 'categorie,nom,lat,lon,source,date_verification\n'
    st.download_button('📄 Télécharger le modèle CSV', template.encode('utf-8'), file_name='modele_poi_verifies.csv', mime='text/csv')
    uploaded = st.file_uploader('CSV de lieux vérifiés', type=['csv'])
    if uploaded is not None:
        try:
            poi = pd.read_csv(uploaded, sep=None, engine='python')
            required = {'categorie','nom','lat','lon','source','date_verification'}
            if not required.issubset(poi.columns):
                st.error('Colonnes manquantes : ' + ', '.join(sorted(required-set(poi.columns))))
            else:
                poi['lat'] = pd.to_numeric(poi['lat'], errors='coerce')
                poi['lon'] = pd.to_numeric(poi['lon'], errors='coerce')
                poi = poi.dropna(subset=['lat','lon','nom','source','date_verification'])
                poi = poi[poi['lat'].between(-90,90) & poi['lon'].between(-180,180)]
                st.success(f'{len(poi)} lieux importés ; vérification indépendante non effectuée.')
                if len(poi):
                    st.map(poi, latitude='lat', longitude='lon', zoom=11, use_container_width=True)
                    st.dataframe(poi[['categorie','nom','source','date_verification']], hide_index=True, use_container_width=True)
        except (ValueError, pd.errors.ParserError, UnicodeDecodeError):
            st.error('Impossible de lire ce CSV. Vérifie le séparateur et les colonnes.')

# V2.5 : comparer les sources documentaires sans confondre couverture et potentiel Airbnb.
st.divider()
st.subheader('📊 Comparaison des trois villes pilotes — infrastructures documentées')
st.caption('Cette comparaison concerne uniquement Leonberg, Ditzingen et Rutesheim, indépendamment de la ville librement recherchée. Wikidata est partiel et ne mesure pas la demande Airbnb.')
CATEGORY_WEIGHTS = {'Hôpital': 20, 'Gare ferroviaire': 25, 'Hôtel': 15, 'Université': 15, 'Musée': 10, 'Attraction touristique': 15}

def distance_km(lat1, lon1, lat2, lon2):
    import math
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2-p1
    dl = math.radians(lon2-lon1)
    h = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 6371.0088 * 2 * math.asin(min(1, math.sqrt(h)))


# V2.8 : recherche OSM ciblée, avec repli Wikidata, puis contrôle routier OSRM.
# Les données OSM sont contributives et incomplètes. Pas de promesse d'exhaustivité.
st.divider()
st.subheader('🏭🎪 Bassins de demande autour du logement — V2.8')
st.markdown('**Professionnel : 15 min maximum en voiture** · **Salons, attractions et loisirs : 50 min maximum en voiture**')
st.caption('Départ : adresse géocodée si disponible, sinon centre approximatif de la commune. OSRM : temps hors trafic, sans stationnement. La recherche comprend les communes voisines.')

DEMAND_GROUPS = {
    'Professionnel (15 min)': {'minutes': 15, 'radius_m': 18000, 'radius_km': 18,
        'types': {'Q4830453': 'Entreprise', 'Q166210': 'Zone industrielle', 'Q16917': 'Hôpital', 'Q3918': 'Université'}},
    'Tourisme et événements (50 min)': {'minutes': 50, 'radius_m': 55000, 'radius_km': 55,
        'types': {'Q1529128': 'Parc des expositions', 'Q33506': 'Musée', 'Q570116': 'Attraction touristique', 'Q3375722': 'Parc de loisirs'}},
}

@st.cache_data(ttl=86400, show_spinner=False)
def osm_demand_places(lat, lon, group):
    """Récupère un échantillon documenté de lieux OSM ; None = source indisponible."""
    radius = DEMAND_GROUPS[group]['radius_m']
    if group.startswith('Professionnel'):
        filters = [
            'way["landuse"="industrial"]', 'way["landuse"="commercial"]',
            'nwr["office"="company"]', 'nwr["office"="corporate"]',
            'nwr["industrial"]', 'nwr["building"="industrial"]["name"]',
            'nwr["healthcare"="hospital"]', 'nwr["amenity"="hospital"]',
            'nwr["amenity"="university"]', 'nwr["office"="research"]',
        ]
    else:
        filters = [
            'nwr["amenity"="conference_centre"]', 'nwr["amenity"="events_venue"]',
            'nwr["amenity"="theatre"]', 'nwr["tourism"="museum"]',
            'nwr["tourism"="attraction"]', 'nwr["tourism"="theme_park"]',
            'nwr["leisure"="amusement_arcade"]', 'nwr["leisure"="water_park"]',
            'nwr["tourism"="zoo"]', 'nwr["historic"="castle"]',
        ]
    # Sélection de catégories ciblées, sans télécharger tous les commerces d'une région.
    statements = ''.join(f'{f}(around:{radius},{lat},{lon});' for f in filters)
    query = f'[out:json][timeout:22];({statements});out center 550;'
    endpoints = ['https://overpass.kumi.systems/api/interpreter',
                 'https://overpass.nchc.org.tw/api/interpreter',
                 'https://overpass-api.de/api/interpreter']
    payload = None
    for endpoint in endpoints:
        try:
            response = requests.post(endpoint, data={'data': query},
                headers={'User-Agent': 'ZeroToHostEducationalPilot/2.8 (OSM research)'}, timeout=(5, 28))
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload.get('elements'), list):
                break
            payload = None
        except (requests.RequestException, ValueError, AttributeError):
            payload = None
    if payload is None:
        return None
    found = {}
    for obj in payload.get('elements', []):
        tags = obj.get('tags') or {}
        name = tags.get('name') or tags.get('operator') or tags.get('brand')
        if not name:
            continue
        loc = obj.get('center') or obj
        lt, lng = loc.get('lat'), loc.get('lon')
        if not isinstance(lt, (float, int)) or not isinstance(lng, (float, int)):
            continue
        if group.startswith('Professionnel'):
            if tags.get('landuse') in ('industrial', 'commercial'):
                category = 'Gewerbegebiet / zone d’activité'
            elif tags.get('amenity') == 'hospital' or tags.get('healthcare') == 'hospital':
                category = 'Hôpital'
            elif tags.get('amenity') == 'university':
                category = 'Université'
            elif tags.get('office') == 'research':
                category = 'Recherche / laboratoire'
            else:
                category = 'Entreprise / site professionnel'
        else:
            category = ('Salon / centre de congrès' if tags.get('amenity') in ('conference_centre', 'events_venue')
                        else 'Musée' if tags.get('tourism') == 'museum'
                        else 'Parc de loisirs' if tags.get('tourism') in ('theme_park', 'zoo') or tags.get('leisure') in ('water_park', 'amusement_arcade')
                        else 'Lieu de spectacle' if tags.get('amenity') == 'theatre'
                        else 'Patrimoine' if tags.get('historic') == 'castle'
                        else 'Attraction touristique')
        key = f"{obj.get('type')}/{obj.get('id')}"
        found[key] = {'Nom': str(name), 'Catégorie': category, 'lat': float(lt), 'lon': float(lng),
            'Source': f'https://www.openstreetmap.org/{key}',
            'Distance directe (km)': round(distance_km(lat, lon, lt, lng), 1)}
    return sorted(found.values(), key=lambda x: x['Distance directe (km)'])

@st.cache_data(ttl=86400, show_spinner=False)
def discover_demand_places(lat, lon, group):
    # Repli sur Wikidata si les serveurs OSM sont indisponibles.
    config = DEMAND_GROUPS[group]
    kinds = config['types']
    values = ' '.join('wd:' + q for q in kinds)
    query = f"""SELECT DISTINCT ?item ?itemLabel ?coord ?kind WHERE {{
      SERVICE wikibase:around {{ ?item wdt:P625 ?coord .
        bd:serviceParam wikibase:center 'Point({lon} {lat})'^^geo:wktLiteral .
        bd:serviceParam wikibase:radius '{config['radius_km']}' . }}
      VALUES ?kind {{ {values} }} ?item wdt:P31/wdt:P279? ?kind .
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language 'fr,de,en'. }}
    }} LIMIT 120"""
    try:
        resp = requests.get('https://query.wikidata.org/sparql',
            params={'query': query, 'format': 'json'},
            headers={'User-Agent': 'ZeroToHostEducationalPilot/2.8 (github.com/Pendjo/zero-to-host-v2--test)',
                     'Accept': 'application/sparql-results+json'}, timeout=(5, 18))
        resp.raise_for_status()
        bindings = resp.json()['results']['bindings']
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return None
    found = {}
    for entry in bindings:
        try:
            uri = entry['item']['value']
            qid = uri.rsplit('/', 1)[-1]
            kind = entry['kind']['value'].rsplit('/', 1)[-1]
            coords = re.fullmatch(r'Point\((-?\d+(?:\.\d+)?) (-?\d+(?:\.\d+)?)\)', entry['coord']['value'])
            if not coords or kind not in kinds:
                continue
            lng, lt = map(float, coords.groups())
            name = entry.get('itemLabel', {}).get('value', qid)
            if name == qid:
                continue
            found[qid] = {'Nom': name, 'Catégorie': kinds[kind], 'lat': lt, 'lon': lng,
                'Source': uri, 'Distance directe (km)': round(distance_km(lat, lon, lt, lng), 1)}
        except (KeyError, ValueError, TypeError):
            continue
    return sorted(found.values(), key=lambda x: x['Distance directe (km)'])

@st.cache_data(ttl=3600, show_spinner=False)
def driving_minutes_to_places(lat, lon, coordinates):
    if not coordinates:
        return []
    output = []
    for offset in range(0, len(coordinates), 25):
        chunk = coordinates[offset:offset + 25]
        route_coords = ';'.join([f'{lon},{lat}'] + [f'{p[1]},{p[0]}' for p in chunk])
        try:
            resp = requests.get('https://router.project-osrm.org/table/v1/driving/' + route_coords,
                params={'sources': '0', 'annotations': 'duration'},
                headers={'User-Agent': 'ZeroToHostEducationalPilot/2.8'}, timeout=(5, 20))
            resp.raise_for_status()
            payload = resp.json()
            if payload.get('code') != 'Ok':
                return None
            durations = payload['durations'][0][1:]
            if len(durations) != len(chunk):
                return None
            output.extend([round(t / 60, 1) if t is not None else None for t in durations])
        except (requests.RequestException, ValueError, KeyError, IndexError, TypeError):
            return None
    return output

origin_key = (round(start_point[0], 5), round(start_point[1], 5))
if st.button('🔎 Rechercher les bassins de demande (15 et 50 min)', key='demand_search'):
    report = {}
    with st.spinner('Recherche OpenStreetMap et vérification des trajets…'):
        for group, config in DEMAND_GROUPS.items():
            candidates = osm_demand_places(*origin_key, group)
            source_name = 'OpenStreetMap'
            if candidates is None:
                candidates = discover_demand_places(*origin_key, group)
                source_name = 'Wikidata (secours)'
            if candidates is None:
                report[group] = {'status': 'Sources de lieux indisponibles', 'rows': []}
                continue
            selected = candidates[:60]
            minutes = driving_minutes_to_places(*origin_key,
                tuple((r['lat'], r['lon']) for r in selected))
            if minutes is None:
                report[group] = {'status': 'Calcul routier indisponible', 'rows': []}
                continue
            rows = [{**place, 'Trajet voiture (min)': mins} for place, mins in zip(selected, minutes)
                    if mins is not None and mins <= config['minutes']]
            report[group] = {'status': 'Partiel', 'rows': sorted(rows, key=lambda x: x['Trajet voiture (min)']),
                             'candidates': len(candidates), 'tested': len(selected), 'source': source_name}
    st.session_state['v28_demand'] = report
    st.session_state['v28_origin'] = origin_key

if st.session_state.get('v28_origin') == origin_key and st.session_state.get('v28_demand'):
    for group, result in st.session_state['v28_demand'].items():
        st.markdown(f'#### {group}')
        if result['status'] != 'Partiel':
            st.warning(result['status'] + ' : aucun résultat ne peut être confirmé.')
            continue
        st.caption(f"Source : {result['source']} · {result['tested']} candidats évalués sur {result['candidates']} trouvés (maximum 60). Résultats non exhaustifs.")
        if result['rows']:
            df = pd.DataFrame(result['rows'])
            st.dataframe(df[['Nom', 'Catégorie', 'Trajet voiture (min)', 'Distance directe (km)', 'Source']],
                hide_index=True, use_container_width=True,
                column_config={'Source': st.column_config.LinkColumn('Fiche source')})
            st.map(df, latitude='lat', longitude='lon', use_container_width=True)
            st.download_button('📥 Télécharger ce bassin (CSV)', df.to_csv(index=False).encode('utf-8-sig'),
                file_name=('professionnel' if 'Professionnel' in group else 'tourisme') + '_v28.csv',
                mime='text/csv', key='csv_' + group)
        else:
            st.info('Aucun lieu retenu parmi les candidats évalués. Cela ne signifie pas absence de demande.')
else:
    st.info('Clique sur « Rechercher les bassins de demande » pour lancer la recherche.')
st.caption('⚠️ OpenStreetMap et Wikidata sont incomplets. Les zones industrielles ne correspondent pas nécessairement à des employeurs identifiés. Les lieux événementiels ne prouvent pas qu’un événement est programmé. Seuls les 60 premiers candidats par catégorie sont vérifiés ; aucune statistique Airbnb n’est calculée.')

comparison_radius = st.slider('Rayon identique pour comparer les villes (km)', 2, 15, 7, key='comparison_radius')
if st.button('📊 Comparer les trois villes (Wikidata)', key='compare_cities'):
    compared, details = [], []
    with st.spinner('Recherche des établissements documentés pour chaque ville…'):
        for name, (lat, lon) in PILOT_CENTERS.items():
            entries = wikidata_pois(lat, lon, comparison_radius)
            if entries is None:
                compared.append({'Ville': name, 'Recherche': 'Indisponible', 'Fiches uniques': None, 'Catégories documentées / 6': None, 'Présence pondérée / 100': None})
                continue
            categories = {r['categorie'] for r in entries}
            unique_ids = {r['identifiant'] for r in entries}
            score = sum(w for c,w in CATEGORY_WEIGHTS.items() if c in categories)
            compared.append({'Ville': name, 'Recherche': 'Résultats partiels', 'Fiches uniques': len(unique_ids), 'Catégories documentées / 6': len(categories), 'Présence pondérée / 100': score})
            for r in entries:
                details.append({'Ville': name, 'Catégorie': r['categorie'], 'Établissement': r['nom'], 'Distance du centre (km)': round(distance_km(lat, lon, r['lat'], r['lon']), 2), 'Source': r['source'], 'Identifiant': r['identifiant']})
    st.session_state['v25_comparison'] = compared
    st.session_state['v25_details'] = details
    st.session_state['v25_comparison_radius'] = comparison_radius

comparison = st.session_state.get('v25_comparison')
if comparison and st.session_state.get('v25_comparison_radius') == comparison_radius:
    comparison_df = pd.DataFrame(comparison)
    st.dataframe(comparison_df, hide_index=True, use_container_width=True)
    st.download_button('📥 Télécharger la comparaison CSV', comparison_df.to_csv(index=False).encode('utf-8-sig'), file_name='zero_to_host_comparaison_v25.csv', mime='text/csv')
    st.caption('Présence pondérée : 25 points pour au moins une gare, 20 pour un hôpital, 15 pour un hôtel, 15 pour une université, 10 pour un musée et 15 pour une attraction. Un résultat absent signifie seulement « non trouvé dans Wikidata ».')
    details_df = pd.DataFrame(st.session_state.get('v25_details', []))
    if not details_df.empty:
        st.subheader('🏥🚉🏨 Établissements et distances')
        st.caption('Distances à vol d’oiseau depuis le centre approximatif de chaque ville, et non depuis le logement. Les fiches peuvent apparaître dans plusieurs villes si leurs rayons se chevauchent.')
        city_filter = st.selectbox('Afficher les établissements de', ['Toutes les villes'] + list(PILOT_CENTERS), key='detail_city')
        show = details_df if city_filter == 'Toutes les villes' else details_df[details_df['Ville'] == city_filter]
        st.dataframe(show[['Ville','Catégorie','Établissement','Distance du centre (km)','Source']], hide_index=True, use_container_width=True, column_config={'Source': st.column_config.LinkColumn('Fiche Wikidata')})
        st.download_button('📥 Télécharger les établissements et distances CSV', details_df.to_csv(index=False).encode('utf-8-sig'), file_name='zero_to_host_etablissements_v25.csv', mime='text/csv')
    if comparison_df['Présence pondérée / 100'].notna().all():
        st.bar_chart(comparison_df.set_index('Ville')['Présence pondérée / 100'])
    else:
        st.warning('Recherche incomplète : les valeurs indisponibles ne sont pas remplacées par zéro.')
else:
    st.info('Lance la comparaison pour afficher les trois villes avec le même rayon.')

st.divider()
st.subheader('🧭 Les trois dimensions de la décision Airbnb')
st.markdown('**1. Emplacement :** établissements documentés, distances et accessibilité. Ces données sont des indices de contexte, pas des réservations.')
st.markdown('**2. Rentabilité :** prix par nuit, occupation, loyer et coûts renseignés par toi dans le calculateur ci-dessous. Les hypothèses doivent être confrontées à des annonces comparables.')
st.markdown('**3. Réglementation :** vérifier la Zweckentfremdungssatzung, la Nutzungsänderung et l’accord écrit du propriétaire avant de signer.')
st.info('Conclusion automatique d’investissement : non disponible. Une décision nécessite des comparables locatifs, des estimations de revenus sourcées et une vérification juridique locale.')

st.divider()
st.subheader('Zweckentfremdungssatzung')
if record['statut'] == 'Satzung confirmée':
    st.error('⚠️ Satzung confirmée')
else:
    st.info('❔ Statut non confirmé — vérification auprès de la mairie nécessaire')
st.write('**État :**', record['satzung'])
st.write('**Commune :**', city)
if address:
    st.write('**Adresse à examiner :**', address)
st.write('**Observation :**', record['remarque'])
st.write('**Vérification documentaire :**', record['date_verification'])
if record.get('source'):
    st.markdown(f"**Source :** [ouvrir la source]({record['source']})")
else:
    st.warning('Aucune source juridique communale vérifiée pour cette ville. Statut inconnu, pas autorisé par défaut.')
st.divider()
st.subheader('Checklist avant de signer le bail')
for item in [
    'Confirmer par écrit auprès de la commune la Satzung applicable au bien',
    'Demander au Bauamt si une Nutzungsänderung est nécessaire',
    'Obtenir une autorisation écrite du propriétaire pour la location touristique',
    'Vérifier le règlement de copropriété, les obligations fiscales et les formalités locales',
]:
    st.checkbox(item, key=item)
st.divider()
st.subheader('Calculateur de rentabilité — hypothèses personnelles')
c1,c2,c3=st.columns(3)
with c1:
    adr=st.number_input('Prix moyen par nuit (€)',min_value=0.0,value=95.0,step=5.0)
    occ=st.slider('Occupation (%)',0,100,60)
with c2:
    rent=st.number_input('Loyer mensuel (€)',min_value=0.0,value=850.0,step=50.0)
    fixed=st.number_input('Autres charges fixes / mois (€)',min_value=0.0,value=420.0,step=20.0)
with c3:
    variable=st.slider('Coûts variables (% du CA)',0,100,15)
    invest=st.number_input('Investissement initial (€)',min_value=0.0,value=3900.0,step=100.0)
revenue=adr*(occ/100)*365/12
profit=revenue*(1-variable/100)-rent-fixed
m1,m2,m3=st.columns(3)
m1.metric('CA mensuel estimé',f'{revenue:,.0f} €')
m2.metric('Résultat mensuel estimé',f'{profit:,.0f} €')
m3.metric('Retour sur investissement',f'{invest/profit:.1f} mois' if profit>0 else 'Non atteint')
st.caption('Calcul simplifié, hors taxes, commissions et frais non renseignés. ADR et occupation sont des hypothèses, pas des statistiques Airbnb.')
st.divider()
st.subheader('📄 Rapport PDF de l’analyse')
st.caption('Le rapport indique explicitement les hypothèses et les limites des données. Les résultats de recherche ne sont pas des statistiques Airbnb.')

def build_pdf_report():
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from xml.sax.saxutils import escape
    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=(595, 842), rightMargin=42, leftMargin=42, topMargin=45, bottomMargin=45)
    styles = getSampleStyleSheet()
    story = [Paragraph('Zero to Host - Rapport de localisation V2.7', styles['Title']), Spacer(1, 12)]
    def line(label, value):
        story.append(Paragraph(f'<b>{escape(str(label))} :</b> {escape(str(value))}', styles['BodyText']))
        story.append(Spacer(1, 6))
    line('Date', date.today().isoformat())
    line('Commune', city)
    line('Adresse saisie', address or 'Non renseignee')
    line('Zweckentfremdungssatzung - statut', record['satzung'])
    line('Verification documentaire', record['date_verification'])
    line('Source juridique', record['source'])
    line('Observation juridique', record['remarque'])
    if st.session_state.get('v28_origin') == origin_key and st.session_state.get('v28_demand'):
        story.append(Paragraph('Bassins de demande V2.8 (resultats partiels)', styles['Heading2']))
        for group, result in st.session_state['v28_demand'].items():
            line(group, f"{len(result['rows'])} lieux avec trajet confirme ; statut : {result['status']}")
        line('Methode', 'Wikidata partiel ; trajet routier OSRM hors trafic ; maximum 60 candidats par bassin')
    story.append(Spacer(1, 10))
    story.append(Paragraph('Hypotheses de rentabilite', styles['Heading2']))
    for label, val in [
        ('Prix par nuit (EUR)', f'{adr:.2f}'), ('Occupation supposee (%)', occ),
        ('Loyer mensuel (EUR)', f'{rent:.2f}'), ('Autres charges fixes (EUR)', f'{fixed:.2f}'),
        ('Couts variables (%)', variable), ('Investissement initial (EUR)', f'{invest:.2f}'),
        ('Chiffre d affaires mensuel estime (EUR)', f'{revenue:.2f}'),
        ('Resultat mensuel estime (EUR)', f'{profit:.2f}')
    ]:
        line(label, val)
    if comparison and st.session_state.get('v25_comparison_radius') == comparison_radius:
        story.append(Paragraph('Comparaison des infrastructures documentees', styles['Heading2']))
        line('Rayon de recherche (km)', comparison_radius)
        rows = [['Ville', 'Fiches', 'Présence / 100', 'Recherche']]
        for r in comparison:
            rows.append([str(r['Ville']), str(r['Fiches uniques'] if r['Fiches uniques'] is not None else 'N/D'), str(r['Présence pondérée / 100'] if r['Présence pondérée / 100'] is not None else 'N/D'), r['Recherche']])
        t = Table(rows, colWidths=[110, 70, 100, 160], repeatRows=1)
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e9eef6')),('GRID',(0,0),(-1,-1),0.4,colors.grey),('VALIGN',(0,0),(-1,-1),'TOP'),('FONTSIZE',(0,0),(-1,-1),9),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
        story.append(t)
    story.append(Spacer(1, 14))
    story.append(Paragraph('Limites importantes', styles['Heading2']))
    story.append(Paragraph('Wikidata est incomplet et ne mesure pas la demande Airbnb. Le score indique uniquement des categories documentees. Les durees OSRM excluent les embouteillages. Les prix et taux d occupation sont saisis par l utilisateur, non verifies. Les charges et impots non renseignes sont exclus. Confirmer les autorisations avec les autorites competentes avant tout engagement.', styles['BodyText']))
    doc.build(story)
    return output.getvalue()

try:
    pdf_bytes = build_pdf_report()
    st.download_button('📄 Télécharger le rapport PDF V2.7', pdf_bytes, file_name=f'zero_to_host_v27_{re.sub(r'[^a-z0-9_-]', '_', city.lower())}.pdf', mime='application/pdf')
except ImportError:
    st.error('Pour activer le PDF, ajoute reportlab dans requirements.txt de ton dépôt GitHub.')
except Exception as exc:
    st.error('Le PDF n’a pas pu être généré. Vérifie les données et les journaux Streamlit.')

st.info('Prochaine étape : loyers locaux et annonces comparables vérifiées. Aucune estimation de marché Airbnb ne sera inventée.')