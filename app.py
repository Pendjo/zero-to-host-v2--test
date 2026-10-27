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
DATA = json.loads((Path(__file__).parent / 'data' / 'villes.json').read_text(encoding='utf-8'))
CITIES = {row['ville']: row for row in DATA}
st.title('🏠 Zero to Host — V2.2 pilote')
st.caption('Carte, adresses, trajets et données vérifiables · sans dépendance à Overpass')
st.warning('Prototype autonome : ne remplace pas votre application actuelle. Ne constitue pas un avis juridique.')
city = st.selectbox('Choisir une ville', sorted(CITIES))
address = st.text_input('Adresse du bien (facultative)', placeholder='Rue et numéro, code postal')
record = CITIES[city]

st.subheader('🗺️ Carte interactive — Leonberg, Ditzingen et Rutesheim')
st.caption('Les marqueurs indiquent des centres-villes approximatifs, et non des adresses de biens. Les distances routières de 20 minutes ne sont pas encore calculées.')
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
        return {'lat': float(lat), 'lon': float(lon), 'label': place or 'Résultat du géocodeur', 'house': str(props.get('housenumber', '')).strip(), 'street': str(props.get('street', '')).strip(), 'city': str(props.get('city', '')).strip()}
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError):
        return None

if city in PILOT_CENTERS:
    center = PILOT_CENTERS[city]
else:
    center = PILOT_CENTERS['Leonberg']

points = [
    {'lat': lat, 'lon': lon, 'lieu': f'Centre approximatif : {name}', 'type': 'Centre-ville'}
    for name, (lat, lon) in PILOT_CENTERS.items()
]
if address.strip():
    if st.button('📍 Localiser cette adresse sur la carte'):
        st.session_state['geocode_request'] = (address.strip(), city)
    if st.session_state.get('geocode_request') == (address.strip(), city):
        with st.spinner('Recherche de l’adresse…'):
            found = geocode_address(f'{address.strip()}, {city}, Deutschland')
        if found:
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
            st.warning('Adresse non trouvée ou service temporairement indisponible. La carte des trois communes reste accessible.')

map_data = pd.DataFrame(points)
st.map(map_data, latitude='lat', longitude='lon', zoom=11, use_container_width=True)
st.dataframe(map_data[['lieu', 'type']], hide_index=True, use_container_width=True)
st.subheader('🚗 Temps de trajet routier vers les trois centres pilotes')
st.caption('Trajet calculé par le service public OSRM depuis le point géocodé (si trouvé), sinon depuis le centre approximatif de la ville. Durées indicatives hors trafic, pas une isochrone exhaustive de 20 minutes.')
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

st.subheader('🏥🚉🏨 Facteurs de demande — données documentées')
st.caption('Aucune donnée POI n’est inventée. Importe un CSV de lieux réels et sourcés pour les afficher sur la carte et les compter.')
with st.expander('Importer un fichier CSV de lieux vérifiés', expanded=False):
    st.markdown('Colonnes requises : `categorie,nom,lat,lon,source,date_verification`. Exemple : hôpital, gare, hôtel, entreprise, université.')
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
                st.success(f'{len(poi)} lieux valides importés. Ces données proviennent du fichier fourni, sans vérification indépendante automatique.')
                if len(poi):
                    st.map(poi, latitude='lat', longitude='lon', zoom=11, use_container_width=True)
                    st.dataframe(poi[['categorie','nom','source','date_verification']], hide_index=True, use_container_width=True)
                    st.dataframe(poi.groupby('categorie').size().reset_index(name='Nombre dans le CSV'), hide_index=True)
        except Exception as exc:
            st.error('Impossible de lire ce CSV. Vérifie le séparateur et les colonnes.')
    else:
        st.info('Pas encore de base POI vérifiée intégrée : aucun nombre d’hôpitaux, gares ou hôtels n’est annoncé.')
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
st.markdown(f"**Source :** [ouvrir la source]({record['source']})")
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
st.info('À développer ensuite : base POI préchargée et sourcée, 30 villes, zones de conduite complètes et PDF. Les trajets OSRM sont des durées vers trois centres, pas une zone complète de 20 minutes.')
