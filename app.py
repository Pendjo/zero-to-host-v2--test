"""Zero to Host V3.8 — base régionale et compléments Overture, contrôle de couverture."""
import json
import io
import re
from datetime import date
import pandas as pd
import requests
import logging
from pathlib import Path
import streamlit as st

st.set_page_config(page_title="Zero to Host | V3.7", page_icon="🏠", layout="wide")
DATA_PATH = Path(__file__).parent / 'data' / 'villes.json'
if not DATA_PATH.exists():
    st.error('Fichier manquant : data/villes.json. Conserve le dossier data de la V2.3 dans ton dépôt GitHub.')
    st.stop()
DATA = json.loads(DATA_PATH.read_text(encoding='utf-8'))
CITIES = {row['ville']: row for row in DATA}
st.title('🏠 Zero to Host — V3.8')
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
st.map(map_data, latitude='lat', longitude='lon', zoom=11, width='stretch')
st.caption(f'Point de référence utilisé : latitude {center[0]:.5f}, longitude {center[1]:.5f}.')
st.dataframe(map_data[['lieu', 'type']], hide_index=True, width='stretch')
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
        st.dataframe(pd.DataFrame(route_rows), hide_index=True, width='stretch')
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
        st.dataframe(poi_df.groupby('categorie').size().reset_index(name='Fiches trouvées (non exhaustif)'), hide_index=True, width='stretch')
        st.map(poi_df, latitude='lat', longitude='lon', zoom=11, width='stretch')
        st.dataframe(poi_df[['categorie', 'nom', 'source']], hide_index=True, width='stretch', column_config={'source': st.column_config.LinkColumn('Fiche Wikidata')})
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
                    st.map(poi, latitude='lat', longitude='lon', zoom=11, width='stretch')
                    st.dataframe(poi[['categorie','nom','source','date_verification']], hide_index=True, width='stretch')
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


# V2.8.1 : diagnostic explicite des sources, sans journaliser les adresses.
LOGGER = logging.getLogger('zero_to_host.demand')
if not LOGGER.handlers:
    LOGGER.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(levelname)s %(name)s: %(message)s'))
    LOGGER.addHandler(handler)
    LOGGER.propagate = False

# Cache des détails de diagnostic par requête, lisibles depuis Streamlit.
# Ne jamais inclure d'adresse ou de coordonnées dans les messages.
def record_service_issue(service, exc):
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        message = f'HTTP {exc.response.status_code}'
    elif isinstance(exc, requests.Timeout):
        message = 'Délai dépassé (timeout)'
    elif isinstance(exc, requests.ConnectionError):
        message = 'Connexion impossible'
    elif isinstance(exc, requests.RequestException):
        message = f'Erreur réseau : {type(exc).__name__}'
    else:
        message = f'Réponse invalide : {type(exc).__name__}'
    LOGGER.warning('%s — %s', service, message)
    return f'{service} : {message}'

# V3.0 : recherche OSM ciblée, avec repli Wikidata, puis contrôle routier OSRM.
# Les données OSM sont contributives et incomplètes. Pas de promesse d'exhaustivité.
st.divider()
st.subheader('🏭🎪 Bassins de demande autour du logement — V3.4')
st.markdown('**Professionnel : 15 min maximum en voiture** · **Salons, attractions et loisirs : 50 min maximum en voiture**')
st.caption('Départ : adresse géocodée si disponible, sinon centre approximatif de la commune. OSRM : temps hors trafic, sans stationnement. La recherche comprend les communes voisines.')

DEMAND_GROUPS = {
    'Professionnel (15 min)': {'minutes': 15, 'radius_m': 14000, 'radius_km': 18,
        'types': {'Q4830453': 'Entreprise', 'Q166210': 'Zone industrielle', 'Q16917': 'Hôpital', 'Q3918': 'Université', 'Q7315155': 'Centre de recherche'}},
    'Tourisme et événements (50 min)': {'minutes': 50, 'radius_m': 55000, 'radius_km': 55,
        'types': {'Q1529128': 'Parc des expositions', 'Q33506': 'Musée', 'Q570116': 'Attraction touristique', 'Q3375722': 'Parc de loisirs', 'Q24354': 'Théâtre'}},
}

# V3.4 : petites requêtes OSM indépendantes pour limiter les échecs Overpass.
# Un service indisponible n'est jamais assimilé à une absence de lieux.
OSM_FILTERS = {
    'Professionnel (15 min)': [
        ('Zones d’activité', ['way["landuse"="industrial"]["name"]', 'way["landuse"="commercial"]["name"]']),
        ('Entreprises', ['nwr["office"="company"]["name"]', 'nwr["office"="corporate"]["name"]',
                         'nwr["man_made"="works"]["name"]', 'nwr["industrial"]["name"]']),
        ('Artisanat', ['nwr["craft"]["name"]']),
        ('Hôpitaux', ['nwr["amenity"="hospital"]["name"]']),
        ('Universités', ['nwr["amenity"="university"]["name"]']),
        ('Recherche', ['nwr["office"="research"]["name"]']),
    ],
    'Tourisme et événements (50 min)': [
        ('Salons / congrès', ['nwr["amenity"="conference_centre"]["name"]', 'nwr["amenity"="events_venue"]["name"]']),
        ('Musées', ['nwr["tourism"="museum"]["name"]']),
        ('Attractions', ['nwr["tourism"="attraction"]["name"]', 'nwr["historic"="castle"]["name"]']),
        ('Loisirs', ['nwr["tourism"="theme_park"]["name"]', 'nwr["leisure"="water_park"]["name"]', 'nwr["tourism"="zoo"]["name"]']),
        ('Spectacles', ['nwr["amenity"="theatre"]["name"]']),
    ],
}

# V3.4 : test de connectivité indépendant des grandes recherches OSM.
# Ne transmet ni adresse ni coordonnées du logement aux serveurs.
OVERPASS_ENDPOINTS = [
    'https://overpass.kumi.systems/api/interpreter',
    'https://overpass-api.de/api/interpreter',
    'https://overpass.nchc.org.tw/api/interpreter',
]

@st.cache_data(ttl=300, show_spinner=False)
def test_overpass_connectivity():
    # Requête minimale : une seule fiche, sans géolocalisation utilisateur.
    query = '[out:json][timeout:5];node(50.0,8.0,50.001,8.001);out 1;'
    headers = {'User-Agent': 'ZeroToHostEducationalPilot/3.3 (github.com/Pendjo/zero-to-host-v2--test)',
               'Accept': 'application/json'}
    results = []
    for endpoint in OVERPASS_ENDPOINTS:
        host = endpoint.split('/')[2]
        for method in ('GET', 'POST'):
            try:
                kwargs = {'params': {'data': query}} if method == 'GET' else {'data': {'data': query}}
                response = requests.request(method, endpoint, headers=headers, timeout=(3, 7), **kwargs)
                status = response.status_code
                if not response.ok:
                    results.append(f'{host} · {method} : HTTP {status}')
                    continue
                try:
                    payload = response.json()
                except ValueError:
                    results.append(f'{host} · {method} : HTTP {status}, réponse non JSON')
                    continue
                if isinstance(payload, dict) and isinstance(payload.get('elements'), list):
                    results.append(f'{host} · {method} : OK (HTTP {status}, {len(payload["elements"])} élément(s) test)')
                    break
                results.append(f'{host} · {method} : HTTP {status}, format inattendu')
            except requests.Timeout:
                results.append(f'{host} · {method} : timeout')
            except requests.ConnectionError:
                results.append(f'{host} · {method} : connexion impossible')
            except requests.RequestException as exc:
                results.append(f'{host} · {method} : erreur réseau ({type(exc).__name__})')
    return results

@st.cache_data(ttl=86400, show_spinner=False)
def osm_demand_places(lat, lon, group):
    """Recherche OSM par lots : données partielles, aucune garantie de disponibilité."""
    radius = DEMAND_GROUPS[group]['radius_m']
    endpoints = ['https://overpass.kumi.systems/api/interpreter',
                 'https://overpass-api.de/api/interpreter',
                 'https://overpass.nchc.org.tw/api/interpreter']
    found, diagnostics = {}, []
    succeeded = 0
    for category_label, filters in OSM_FILTERS[group]:
        statements = ''.join(f'{f}(around:{radius},{lat},{lon});' for f in filters)
        query = f'[out:json][timeout:18];({statements});out center 100;'
        payload = None
        for endpoint in endpoints:
            try:
                response = requests.post(endpoint, data={'data': query},
                    headers={'User-Agent': 'ZeroToHostEducationalPilot/3.2 (github.com/Pendjo/zero-to-host-v2--test)'},
                    timeout=(4, 20))
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict) or not isinstance(payload.get('elements'), list):
                    payload = None
                    continue
                break
            except (requests.RequestException, ValueError, AttributeError):
                continue
        if payload is None:
            diagnostics.append(f'OpenStreetMap {category_label} : indisponible sur les serveurs testés')
            continue
        succeeded += 1
        diagnostics.append(f'OpenStreetMap {category_label} : {len(payload["elements"])} fiches reçues (maximum 100)')
        for obj in payload['elements']:
            tags = obj.get('tags') or {}
            name = tags.get('name')
            loc = obj.get('center') or obj
            lt, lng = loc.get('lat'), loc.get('lon')
            if not name or not isinstance(lt, (float, int)) or not isinstance(lng, (float, int)):
                continue
            if group.startswith('Professionnel'):
                if tags.get('landuse') in ('industrial', 'commercial'):
                    category = 'Gewerbegebiet / zone d’activité'
                elif tags.get('amenity') == 'hospital':
                    category = 'Hôpital'
                elif tags.get('amenity') == 'university':
                    category = 'Université'
                elif tags.get('office') == 'research':
                    category = 'Recherche / laboratoire'
                else:
                    category = 'Entreprise / site professionnel'
            else:
                category = ('Salon / centre de congrès' if category_label == 'Salons / congrès'
                            else 'Musée' if category_label == 'Musées'
                            else 'Parc de loisirs' if category_label == 'Loisirs'
                            else 'Lieu de spectacle' if category_label == 'Spectacles'
                            else 'Attraction touristique')
            key = f"{obj.get('type')}/{obj.get('id')}"
            found[key] = {'Nom': str(name), 'Catégorie': category, 'lat': float(lt), 'lon': float(lng),
                          'Source': f'https://www.openstreetmap.org/{key}',
                          'Distance directe (km)': round(distance_km(lat, lon, lt, lng), 1),
                          'Fiabilité': 'Fiche OSM — activité non vérifiée'}
    diagnostics.insert(0, f'OpenStreetMap : {succeeded}/{len(OSM_FILTERS[group])} catégories accessibles')
    if not succeeded:
        return None, diagnostics
    return sorted(found.values(), key=lambda x: x['Distance directe (km)']), diagnostics

@st.cache_data(ttl=86400, show_spinner=False)
def discover_demand_places(lat, lon, group):
    """Recherche Wikidata par catégorie : évite qu'une catégorie monopolise le quota."""
    config = DEMAND_GROUPS[group]
    kinds = config['types']
    found = {}
    diagnostics = []
    successful = 0
    for qid, category in kinds.items():
        # Une requête par type avec quota indépendant. Les catégories restent partielles.
        query = f"""SELECT DISTINCT ?item ?itemLabel ?coord WHERE {{
          SERVICE wikibase:around {{ ?item wdt:P625 ?coord .
            bd:serviceParam wikibase:center 'Point({lon} {lat})'^^geo:wktLiteral .
            bd:serviceParam wikibase:radius '{config['radius_km']}' . }}
          ?item wdt:P31/wdt:P279? wd:{qid} .
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language 'fr,de,en'. }}
        }} LIMIT 35"""
        try:
            resp = requests.get('https://query.wikidata.org/sparql',
                params={'query': query, 'format': 'json'},
                headers={'User-Agent': 'ZeroToHostEducationalPilot/3.0 (github.com/Pendjo/zero-to-host-v2--test)',
                         'Accept': 'application/sparql-results+json'}, timeout=(5, 20))
            resp.raise_for_status()
            bindings = resp.json()['results']['bindings']
            successful += 1
            diagnostics.append(f'Wikidata {category} : {len(bindings)} candidats reçus')
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            diagnostics.append(record_service_issue('Wikidata ' + category, exc))
            continue
        for entry in bindings:
            try:
                uri = entry['item']['value']
                item_qid = uri.rsplit('/', 1)[-1]
                coords = re.fullmatch(r'Point\((-?\d+(?:\.\d+)?) (-?\d+(?:\.\d+)?)\)', entry['coord']['value'])
                if not coords:
                    continue
                lng, lt = map(float, coords.groups())
                name = entry.get('itemLabel', {}).get('value', item_qid)
                if name == item_qid:
                    continue
                # Un cinéma, théâtre ou lieu de divertissement ne doit pas être
                # présenté comme un employeur industriel sur la seule base de P31.
                if group.startswith('Professionnel') and category == 'Entreprise':
                    if re.search(r'kino|cinema|cineplex|filmtheater|kinocenter|lichtspiel', name, re.I):
                        continue
                if item_qid not in found:
                    found[item_qid] = {'Nom': name, 'Catégorie': category, 'lat': lt, 'lon': lng,
                        'Source': uri, 'Distance directe (km)': round(distance_km(lat, lon, lt, lng), 1),
                        'Fiabilité': 'Fiche Wikidata — activité non vérifiée'}
            except (KeyError, ValueError, TypeError):
                continue
    if not successful:
        return None, diagnostics
    return sorted(found.values(), key=lambda x: x['Distance directe (km)']), diagnostics


def balanced_candidates(candidates, cap=60):
    """Sélection par tours de catégories, puis proximité à l'intérieur de chaque catégorie."""
    buckets = {}
    for place in candidates:
        buckets.setdefault(place['Catégorie'], []).append(place)
    for bucket in buckets.values():
        bucket.sort(key=lambda x: x['Distance directe (km)'])
    selected = []
    while len(selected) < cap and any(buckets.values()):
        for category in list(buckets):
            if buckets[category] and len(selected) < cap:
                selected.append(buckets[category].pop(0))
    return selected

def correct_category(place):
    """Ne pas assimiler un site technique à un Gewerbegebiet entier."""
    p = dict(place)
    category = str(p.get('Catégorie', '')).casefold()
    name = str(p.get('Nom', '')).casefold()
    if any(t in category for t in ('gewerbegebiet', 'zone industrielle', 'zone d’activité')):
        site_terms = ('winterdienst', 'stützpunkt', 'umspannwerk', 'kläranlage',
                      'wasserwerk', 'pumpwerk', 'bauhof', 'recyclinghof',
                      'wertstoffhof', 'deponie', 'heizkraftwerk', 'kraftwerk')
        if any(term in name for term in site_terms):
            p['Catégorie'] = 'Site technique / infrastructure (à vérifier)'
    return p


def prioritize_local_candidates(candidates, cap=300, group='Professionnel (15 min)'):
    """Priorité à la proximité et aux entreprises; repli Wikidata ensuite.

    Les quotas empêchent les zones industrielles de masquer les entreprises.
    Ce n'est pas une recherche exhaustive.
    """
    candidates = [correct_category(p) for p in candidates]
    local = [p for p in candidates if str(p.get('Fiabilité', '')).startswith('Base locale')]
    remote = [p for p in candidates if not str(p.get('Fiabilité', '')).startswith('Base locale')]
    def ordered(pool):
        if not group.startswith('Professionnel'):
            return sorted(pool, key=lambda p: p['Distance directe (km)'])
        def rank(p):
            cat = str(p.get('Catégorie', '')).casefold()
            if 'entreprise' in cat: tier = 0
            elif any(x in cat for x in ('hôpital', 'université', 'recherche')): tier = 1
            elif 'gewerbegebiet' in cat or 'zone d’activité' in cat: tier = 2
            else: tier = 3
            # Proximity remains decisive within each tier.
            return (tier, p['Distance directe (km)'])
        return sorted(pool, key=rank)
    if not group.startswith('Professionnel'):
        return (ordered(local) + ordered(remote))[:cap]
    # Reserve at most 20% of the evaluation capacity for Gewerbegebiete;
    # each industrial area is a context indicator, not an individual employer.
    result = []
    zone_limit = max(1, cap // 5)
    zones = 0
    for p in ordered(local) + ordered(remote):
        cat = str(p.get('Catégorie', '')).casefold()
        zone = 'gewerbegebiet' in cat or 'zone d’activité' in cat
        if zone and zones >= zone_limit:
            continue
        result.append(p)
        zones += int(zone)
        if len(result) == cap:
            break
    return result


@st.cache_data(ttl=3600, show_spinner=False)
def driving_minutes_to_places(lat, lon, coordinates):
    if not coordinates:
        return [], ['OSRM : aucun lieu à vérifier']
    output = []
    diagnostics = []
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
                msg = f"OSRM : réponse {str(payload.get('code', 'inconnue'))[:40]}"
                LOGGER.warning(msg)
                return None, diagnostics + [msg]
            durations = payload['durations'][0][1:]
            if len(durations) != len(chunk):
                return None, diagnostics + ['OSRM : nombre de trajets inattendu']
            output.extend([round(t / 60, 1) if t is not None else None for t in durations])
        except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
            return None, diagnostics + [record_service_issue('OSRM', exc)]
    return output, diagnostics + [f'OSRM : {len(output)} trajets évalués']

# V3.4 : lecture pédagogique par clientèle. Une fiche OSM/Wikidata n'est pas
# une preuve d'activité, d'effectifs, de fréquentation ou de demande Airbnb.
LEISURE_TERMS = ('cinema', 'cinéma', 'cineplex', 'cine', 'kino', 'lichtburg',
                 'filmstudio', 'theater', 'theatre', 'théâtre', 'museum', 'musée',
                 'alhambra', 'multiplex', 'schauspielhaus', 'filmpalast', 'filmstudio',
                 'roxy', 'lichtspielhaus', 'kinopolis', 'cinestar', 'ufa-palast')

def audience_category(place, group):
    name = str(place.get('Nom', '')).casefold()
    category = str(place.get('Catégorie', '')).casefold()
    if group.startswith('Professionnel'):
        if any(term in name for term in LEISURE_TERMS):
            return 'À vérifier — loisir/spectacle (hors cible professionnelle)'
        if 'gewerbegebiet' in category or 'zone industrielle' in category or 'zone d’activité' in category:
            return 'Zones d’activité / Gewerbegebiete'
        if 'hôpital' in category:
            return 'Hôpitaux'
        if 'université' in category:
            return 'Universités'
        if 'recherche' in category or 'laboratoire' in category:
            return 'Centres de recherche'
        if 'site technique' in category:
            return 'Sites techniques / infrastructures (à vérifier)'
        if 'entreprise' in category:
            return 'Entreprises potentielles (activité à vérifier)'
        return 'Autres lieux professionnels à vérifier'
    if 'exposition' in category or 'congrès' in category or 'salon' in category:
        return 'Salons / congrès (lieux, pas événements datés)'
    if 'musée' in category:
        return 'Musées'
    if 'spectacle' in category or 'théâtre' in category:
        return 'Spectacles / théâtres'
    if 'loisir' in category or 'parc' in category:
        return 'Parcs et loisirs'
    if 'patrimoine' in category:
        return 'Patrimoine'
    return 'Attractions touristiques'

# V3.4 : base locale facultative. Elle ne dépend pas du réseau Overpass.
# Un export OSM régional doit être préparé hors de Streamlit puis placé dans data/.
LOCAL_PLACES_PATH = Path(__file__).parent / 'data' / 'lieux_allemagne.csv'
# Les données Overture sont fusionnées hors ligne dans ce même fichier CSV.
# Aucun téléchargement volumineux ni API payante n'est lancé depuis Streamlit.
LOCAL_COLUMNS = {'nom', 'categorie', 'lat', 'lon', 'source', 'public_cible'}

@st.cache_data(ttl=3600, show_spinner=False)
def read_local_places(path_string, file_mtime):
    try:
        table = pd.read_csv(path_string, dtype={'nom': str, 'categorie': str, 'source': str,
                                                'public_cible': str}, encoding='utf-8-sig')
        if not LOCAL_COLUMNS.issubset(table.columns):
            return None, 'Colonnes requises : ' + ', '.join(sorted(LOCAL_COLUMNS))
        table['lat'] = pd.to_numeric(table['lat'], errors='coerce')
        table['lon'] = pd.to_numeric(table['lon'], errors='coerce')
        table = table.dropna(subset=['nom', 'categorie', 'lat', 'lon', 'source', 'public_cible'])
        table = table[table['lat'].between(47, 56) & table['lon'].between(5, 16)]
        table = table[table['public_cible'].str.strip().str.lower().isin(['professionnel', 'tourisme'])]
        return table, None
    except (OSError, ValueError, UnicodeError, pd.errors.ParserError) as exc:
        return None, f'Lecture CSV impossible : {type(exc).__name__}'

def local_demand_places(lat, lon, group):
    if not LOCAL_PLACES_PATH.is_file():
        return [], 'Base locale absente (facultative) : data/lieux_allemagne.csv'
    table, error = read_local_places(str(LOCAL_PLACES_PATH), LOCAL_PLACES_PATH.stat().st_mtime_ns)
    if error:
        return [], 'Base locale : ' + error
    audience = 'professionnel' if group.startswith('Professionnel') else 'tourisme'
    subset = table[table['public_cible'].str.strip().str.lower() == audience]
    # Préfiltre géographique à vol d’oiseau ; le filtre définitif reste OSRM.
    max_km = DEMAND_GROUPS[group]['radius_km']
    found = []
    for row in subset.itertuples(index=False):
        dist = distance_km(lat, lon, float(row.lat), float(row.lon))
        if dist <= max_km:
            found.append({'Nom': str(row.nom), 'Catégorie': str(row.categorie),
                          'lat': float(row.lat), 'lon': float(row.lon),
                          'Source': str(row.source), 'Distance directe (km)': round(dist, 1),
                          'Fiabilité': 'Base locale — activité non vérifiée'})
    return sorted(found, key=lambda x: x['Distance directe (km)']), f'Base locale : {len(found)} lieux dans le rayon ({len(subset)} fiches pour cette clientèle)'

st.caption('V3.8 : sélection automatique des candidats les plus proches, avec priorité aux établissements professionnels. Base actuelle : OSM + Wikidata ; Overture non encore intégré.')
MAX_ROUTE_CANDIDATES = 300
st.caption('Contrôle automatique : jusqu’à 300 candidats par clientèle. Ce plafond protège le service de calcul routier ; l’analyse reste partielle.')
with st.expander('📂 Base de lieux locale — fonctionnement V3.4', expanded=False):
    st.write('Dépose un fichier `data/lieux_allemagne.csv` dans GitHub pour alimenter la recherche sans Overpass. Le fichier peut contenir des établissements de plusieurs régions allemandes.')
    st.write('Colonnes : `nom,categorie,lat,lon,source,public_cible` ; public_cible = `professionnel` ou `tourisme`. Les coordonnées doivent être réelles et les sources vérifiables.')
    st.download_button('📥 Télécharger le modèle CSV vide',
        'nom,categorie,lat,lon,source,public_cible\n'.encode('utf-8-sig'),
        file_name='modele_lieux_allemagne.csv', mime='text/csv')
    st.info('Aucune base d’entreprises complète n’est incluse. Sans CSV local, les résultats proviennent de Wikidata uniquement ; leur couverture reste partielle.')

origin_key = (round(start_point[0], 5), round(start_point[1], 5))
if st.button('🔎 Rechercher les bassins de demande (15 et 50 min)', key='demand_search'):
    report = {}
    with st.spinner('Recherche dans la base locale, Wikidata et calcul des trajets…'):
        for group, config in DEMAND_GROUPS.items():
            candidates, local_message = local_demand_places(*origin_key, group)
            diagnostics = [local_message]
            source_name = 'Base locale OSM + Wikidata (Overture non intégré)' if candidates else 'Wikidata (base locale vide ou absente)'
            wikidata_candidates, fallback_diagnostics = discover_demand_places(*origin_key, group)
            diagnostics += fallback_diagnostics
            if wikidata_candidates:
                seen = {(re.sub(r'\W+', '', p['Nom'].casefold()), round(p['lat'], 3), round(p['lon'], 3)) for p in candidates}
                for place in wikidata_candidates:
                    key = (re.sub(r'\W+', '', place['Nom'].casefold()), round(place['lat'], 3), round(place['lon'], 3))
                    if key not in seen:
                        candidates.append(place)
                        seen.add(key)
            elif wikidata_candidates is None and not candidates:
                report[group] = {'status': 'Base locale vide et Wikidata indisponible', 'rows': [], 'diagnostics': diagnostics}
                continue
            if not candidates:
                report[group] = {'status': 'Aucun lieu documenté trouvé', 'rows': [], 'diagnostics': diagnostics}
                continue
            selected = prioritize_local_candidates(candidates, cap=MAX_ROUTE_CANDIDATES, group=group)
            local_tested = sum(str(p.get("Fiabilité", "")).startswith("Base locale") for p in selected)
            diagnostics.append(f"Sélection : {local_tested} fiches locales prioritaires sur {len(selected)} candidats testés")
            minutes, routing_diagnostics = driving_minutes_to_places(*origin_key,
                tuple((r['lat'], r['lon']) for r in selected))
            diagnostics += routing_diagnostics
            if minutes is None:
                report[group] = {'status': 'Calcul routier indisponible', 'rows': [], 'diagnostics': diagnostics}
                continue
            local_within = sum(
                str(place.get('Fiabilité', '')).startswith('Base locale')
                and mins is not None and mins <= config['minutes']
                for place, mins in zip(selected, minutes)
            )
            local_outside = sum(
                str(place.get('Fiabilité', '')).startswith('Base locale')
                and mins is not None and mins > config['minutes']
                for place, mins in zip(selected, minutes)
            )
            local_unreachable = sum(
                str(place.get('Fiabilité', '')).startswith('Base locale') and mins is None
                for place, mins in zip(selected, minutes)
            )
            diagnostics.append(
                f"Base locale après OSRM : {local_within} dans la limite de {config['minutes']} min ; "
                f"{local_outside} au-delà ; {local_unreachable} sans itinéraire"
            )
            checked_rows = [{**place, 'Trajet voiture (min)': mins,
                             'Statut trajet': ('Sans itinéraire' if mins is None else
                                 ('Dans la limite' if mins <= config['minutes'] else 'Au-delà de la limite'))}
                            for place, mins in zip(selected, minutes)]
            rows = [{**place, 'Trajet voiture (min)': mins,
                     'Sous-catégorie V3.4': audience_category(place, group)}
                    for place, mins in zip(selected, minutes)
                    if mins is not None and mins <= config['minutes']]
            report[group] = {'status': 'Partiel', 'rows': sorted(rows, key=lambda x: x['Trajet voiture (min)']),
                             'candidates': len(candidates), 'tested': len(selected), 'source': source_name,
                             'local_within': local_within, 'local_outside': local_outside,
                             'checked_rows': checked_rows,
                             'diagnostics': diagnostics}
    st.session_state['v34_demand'] = report
    st.session_state['v34_origin'] = (city, origin_key, MAX_ROUTE_CANDIDATES)

if st.session_state.get('v34_origin') == (city, origin_key, MAX_ROUTE_CANDIDATES) and st.session_state.get('v34_demand'):
    report = st.session_state['v34_demand']
    st.markdown('### Deux clientèles, deux analyses distinctes')
    with st.expander('🧪 Diagnostic réseau Overpass V3.4 — GET / POST', expanded=False):
        st.caption('Test indépendant des lieux : petite requête publique, sans adresse ni coordonnées de ton logement. Peut prendre jusqu’à environ une minute si les serveurs ne répondent pas.')
        if st.button('Tester la connexion aux serveurs Overpass', key='test_overpass_v34'):
            with st.spinner('Test GET et POST en cours…'):
                st.session_state['overpass_v34_results'] = test_overpass_connectivity()
        for diagnostic in st.session_state.get('overpass_v34_results', []):
            st.write('• ' + diagnostic)

    st.caption('Un lieu référencé est un indice de contexte, pas une preuve de nuitées vendues. La base locale ne garantit pas l’activité actuelle. Les trajets OSRM sont hors trafic.')
    tab_pro, tab_tour = st.tabs(['🏭 Monteure & Geschäftsreisende · 15 min',
                                '🎪 Touristes, familles & événements · 50 min'])
    for tab, group in zip((tab_pro, tab_tour), DEMAND_GROUPS):
        with tab:
            result = report.get(group, {})
            st.markdown('#### ' + group)
            if group.startswith('Professionnel'):
                st.caption('Cibles : entreprises, zones d’activité, hôpitaux, universités et recherche. Les emplois, chantiers et déplacements professionnels ne sont pas mesurés.')
            else:
                st.caption('Cibles : salons, congrès, spectacles, attractions et loisirs. Les événements programmés et leur fréquentation ne sont pas vérifiés.')
            with st.expander('🔧 Diagnostic des services (V3.7)', expanded=result.get('status') != 'Partiel'):
                for message in result.get('diagnostics', []):
                    st.write('• ' + message)
                if not result.get('diagnostics'):
                    st.info('Aucun diagnostic enregistré.')
            if result.get('status') != 'Partiel':
                st.warning(result.get('status', 'Résultats indisponibles') + ' : aucun résultat ne peut être confirmé.')
                continue
            st.caption(f"Source : {result['source']} · {result['tested']} candidats évalués sur {result['candidates']} trouvés (plafond automatique {MAX_ROUTE_CANDIDATES}). Résultats partiels.")
            st.info(f"Base locale : {result.get('local_within', 0)} lieu(x) à {DEMAND_GROUPS[group]['minutes']} min maximum en voiture ; {result.get('local_outside', 0)} au-delà. Ce décompte ne mesure pas la demande Airbnb.")
            if result.get('checked_rows'):
                with st.expander('🔎 Voir les candidats évalués et exclus', expanded=False):
                    checked_df = pd.DataFrame(result['checked_rows'])
                    st.dataframe(checked_df[['Nom', 'Catégorie', 'Trajet voiture (min)',
                                             'Statut trajet', 'Distance directe (km)', 'Source']],
                                 hide_index=True, width='stretch',
                                 column_config={'Source': st.column_config.LinkColumn('Fiche source')})
                    st.download_button('📥 Télécharger les candidats évalués (CSV)',
                        checked_df.to_csv(index=False).encode('utf-8-sig'),
                        file_name=('professionnel' if group.startswith('Professionnel') else 'tourisme') + '_candidats_v36.csv',
                        mime='text/csv', key='checked_v36_' + group)
            if not result.get('rows'):
                st.info('Aucun lieu retenu parmi les candidats évalués. Cela ne signifie pas absence de demande.')
                continue
            df = pd.DataFrame(result['rows'])
            if 'Sous-catégorie V3.4' not in df.columns:
                df['Sous-catégorie V3.4'] = [audience_category(r, group) for r in result['rows']]
            excluded = df['Sous-catégorie V3.4'].str.startswith('À vérifier — loisir')
            if group.startswith('Professionnel') and excluded.any():
                st.warning(f"{int(excluded.sum())} lieu(x) de loisirs/spectacles écarté(s) de la synthèse professionnelle ; consulter l'export pour les vérifier.")
            shown = df.loc[~excluded].copy() if group.startswith('Professionnel') else df
            if shown.empty:
                st.info('Aucun lieu professionnel clairement classé dans cet échantillon.')
            else:
                st.markdown('**Répartition des lieux identifiés**')
                summary = shown.groupby('Sous-catégorie V3.4').size().reset_index(name='Lieux référencés')
                st.dataframe(summary, hide_index=True, width='stretch')
                st.dataframe(shown[['Nom', 'Sous-catégorie V3.4', 'Catégorie', 'Trajet voiture (min)', 'Distance directe (km)', 'Source', 'Fiabilité']],
                    hide_index=True, width='stretch', column_config={'Source': st.column_config.LinkColumn('Fiche source')})
                st.map(shown, latitude='lat', longitude='lon', width='stretch')
            st.download_button('📥 Télécharger cette analyse (CSV)', df.to_csv(index=False).encode('utf-8-sig'),
                file_name=('professionnel' if group.startswith('Professionnel') else 'tourisme') + '_v34.csv',
                mime='text/csv', key='csv_v34_' + group)
else:
    st.info('Clique sur « Rechercher les bassins de demande » pour lancer les deux analyses séparées.')
st.caption('⚠️ Base locale facultative et Wikidata partiel : la couverture et l’activité des établissements ne sont pas garanties. Aucun taux d’occupation ni revenu Airbnb n’est déduit de ces lieux.')

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
    st.dataframe(comparison_df, hide_index=True, width='stretch')
    st.download_button('📥 Télécharger la comparaison CSV', comparison_df.to_csv(index=False).encode('utf-8-sig'), file_name='zero_to_host_comparaison_v25.csv', mime='text/csv')
    st.caption('Présence pondérée : 25 points pour au moins une gare, 20 pour un hôpital, 15 pour un hôtel, 15 pour une université, 10 pour un musée et 15 pour une attraction. Un résultat absent signifie seulement « non trouvé dans Wikidata ».')
    details_df = pd.DataFrame(st.session_state.get('v25_details', []))
    if not details_df.empty:
        st.subheader('🏥🚉🏨 Établissements et distances')
        st.caption('Distances à vol d’oiseau depuis le centre approximatif de chaque ville, et non depuis le logement. Les fiches peuvent apparaître dans plusieurs villes si leurs rayons se chevauchent.')
        city_filter = st.selectbox('Afficher les établissements de', ['Toutes les villes'] + list(PILOT_CENTERS), key='detail_city')
        show = details_df if city_filter == 'Toutes les villes' else details_df[details_df['Ville'] == city_filter]
        st.dataframe(show[['Ville','Catégorie','Établissement','Distance du centre (km)','Source']], hide_index=True, width='stretch', column_config={'Source': st.column_config.LinkColumn('Fiche Wikidata')})
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
    story = [Paragraph('Zero to Host - Rapport de localisation V3.4', styles['Title']), Spacer(1, 12)]
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
    if st.session_state.get('v34_origin') == (city, origin_key, MAX_ROUTE_CANDIDATES) and st.session_state.get('v34_demand'):
        story.append(Paragraph('Bassins de demande V3.4 (resultats partiels)', styles['Heading2']))
        for group, result in st.session_state['v34_demand'].items():
            line(group, f"{len(result['rows'])} lieux avec trajet confirme ; statut : {result['status']}")
        line('Methode', 'Base locale facultative et Wikidata partiel ; trajet routier OSRM hors trafic ; nombre de candidats paramétrable par bassin')
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
    st.download_button('📄 Télécharger le rapport PDF V3.4', pdf_bytes, file_name='zero_to_host_v34_' + re.sub(r'[^a-z0-9_-]', '_', city.lower()) + '.pdf', mime='application/pdf')
except ImportError:
    st.error('Pour activer le PDF, ajoute reportlab dans requirements.txt de ton dépôt GitHub.')
except Exception as exc:
    st.error('Le PDF n’a pas pu être généré. Vérifie les données et les journaux Streamlit.')

st.info('Prochaine étape : loyers locaux et annonces comparables vérifiées. Aucune estimation de marché Airbnb ne sera inventée.')