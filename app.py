"""Zero to Host V2 — pilote juridique autonome, sans dépendance Overpass."""
import json
import pandas as pd
import requests
from pathlib import Path
import streamlit as st

st.set_page_config(page_title="Zero to Host | Pilote V2", page_icon="🏠", layout="wide")
DATA = json.loads((Path(__file__).parent / 'data' / 'villes.json').read_text(encoding='utf-8'))
CITIES = {row['ville']: row for row in DATA}
st.title('🏠 Zero to Host — V2 pilote')
st.caption('Module juridique et carte pilote · sans dépendance à Overpass')
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
            params={'q': query, 'limit': 1},
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
        return {'lat': float(lat), 'lon': float(lon), 'label': place or 'Résultat du géocodeur'}
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
            st.success(f'Adresse trouvée : {found["label"]}. Vérifie que le résultat correspond bien à ton bien.')
        else:
            st.warning('Adresse non trouvée ou service temporairement indisponible. La carte des trois communes reste accessible.')

map_data = pd.DataFrame(points)
st.map(map_data, latitude='lat', longitude='lon', zoom=11, use_container_width=True)
st.dataframe(map_data[['lieu', 'type']], hide_index=True, use_container_width=True)
st.info('Les hôpitaux, gares, hôtels, entreprises et temps de trajet routier ne sont pas encore intégrés. Aucun résultat fictif ne sera affiché.')
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
st.info('À développer ensuite : temps de trajet routier de 20 min, base de POI vérifiés hors ligne, 30 communes et PDF complet. Aucun temps de trajet n’est inventé dans ce pilote.')
