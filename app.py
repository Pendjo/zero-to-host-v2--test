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
st.title('🏠 Zero to Host — V2.4 pilote')
st.caption('Carte, adresses, trajets, comparaison des villes et rapport PDF · sans dépendance à Overpass')
st.warning('Prototype autonome : ne remplace pas votre application actuelle. Ne constitue pas un avis juridique.')
city = st.selectbox('Choisir une ville', sorted(CITIES))
address = st.text_input('Adresse du bien (facultative)', placeholder='Rue et numéro, code postal')
record = CITIES[city]

st.subheader('🗺️ Carte interactive — Leonberg, Ditzingen et Rutesheim')
st.caption('Les marqueurs de ville sont approximatifs. Les durées routières vers les trois centres sont calculables plus bas ; ce n’est pas une zone exhaustive de 20 minutes.')
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

# V2.4 : comparaison fondée sur des fiches réellement récupérées, jamais sur des données inventées.
st.divider()
st.subheader('📊 Comparer Leonberg, Ditzingen et Rutesheim')
st.caption('Indicateur pédagogique de présence documentée : Wikidata est incomplet. Ce score ne prédit ni les réservations, ni le taux d’occupation, ni le potentiel économique Airbnb. Les villes ne sont comparées que si les trois recherches réussissent.')

CATEGORY_WEIGHTS = {
    'Hôpital': 20,
    'Gare ferroviaire': 25,
    'Hôtel': 15,
    'Université': 15,
    'Musée': 10,
    'Attraction touristique': 15,
}

def documented_score(items):
    """Score de présence, plafonné à 100 ; un résultat absent reste inconnu."""
    present = {r['categorie'] for r in items}
    return sum(weight for category, weight in CATEGORY_WEIGHTS.items() if category in present)

comparison_radius = st.slider('Rayon identique pour comparer les villes (km)', 2, 15, 7, key='comparison_radius')
if st.button('📊 Comparer les trois villes (Wikidata)', key='compare_cities'):
    compared = []
    with st.spinner('Recherche des établissements documentés pour chaque ville…'):
        for name, (lat, lon) in PILOT_CENTERS.items():
            entries = wikidata_pois(lat, lon, comparison_radius)
            if entries is None:
                compared.append({'Ville': name, 'Recherche': 'Indisponible', 'Fiches Wikidata': None, 'Score documentaire / 100': None, 'Catégories présentes / 6': None})
            else:
                compared.append({'Ville': name, 'Recherche': 'Résultats partiels', 'Fiches Wikidata': len({r['identifiant'] for r in entries}), 'Score documentaire / 100': documented_score(entries), 'Catégories présentes / 6': len({r['categorie'] for r in entries})})
    st.session_state['v24_comparison'] = compared
    st.session_state['v24_comparison_radius'] = comparison_radius

comparison = st.session_state.get('v24_comparison')
if comparison and st.session_state.get('v24_comparison_radius') == comparison_radius:
    comparison_df = pd.DataFrame(comparison)
    st.dataframe(comparison_df, hide_index=True, use_container_width=True)
    st.download_button('📥 Télécharger la comparaison CSV', comparison_df.to_csv(index=False).encode('utf-8-sig'), file_name='zero_to_host_comparaison_v24.csv', mime='text/csv')
    if comparison_df['Score documentaire / 100'].notna().all():
        st.bar_chart(comparison_df.set_index('Ville')['Score documentaire / 100'])
    else:
        st.warning('Au moins une recherche a échoué : comparaison incomplète, aucun score fictif.')
    st.caption('Méthode : 25 points si au moins une gare est référencée, 20 pour un hôpital, 15 pour un hôtel, 15 pour une université, 10 pour un musée et 15 pour une attraction. Aucun point supplémentaire pour les quantités. Un zéro signifie uniquement « aucune fiche trouvée dans cette recherche », jamais « aucun établissement existant ».')
else:
    st.info('Lance la comparaison pour afficher les trois villes avec le même rayon.')

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
    story = [Paragraph('Zero to Host - Rapport de localisation V2.4', styles['Title']), Spacer(1, 12)]
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
    if comparison and st.session_state.get('v24_comparison_radius') == comparison_radius:
        story.append(Paragraph('Comparaison documentaire des trois villes', styles['Heading2']))
        line('Rayon de recherche (km)', comparison_radius)
        rows = [['Ville', 'Fiches', 'Score / 100', 'Recherche']]
        for r in comparison:
            rows.append([str(r['Ville']), str(r['Fiches Wikidata'] if r['Fiches Wikidata'] is not None else 'N/D'), str(r['Score documentaire / 100'] if r['Score documentaire / 100'] is not None else 'N/D'), r['Recherche']])
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
    st.download_button('📄 Télécharger le rapport PDF V2.4', pdf_bytes, file_name=f'zero_to_host_v24_{city.lower()}.pdf', mime='application/pdf')
except ImportError:
    st.error('Pour activer le PDF, ajoute reportlab dans requirements.txt de ton dépôt GitHub.')
except Exception as exc:
    st.error('Le PDF n’a pas pu être généré. Vérifie les données et les journaux Streamlit.')

st.info('Prochaine étape : base de lieux documentés plus complète, entreprises et zones d’activité, puis extension progressive à d’autres villes. Les données Wikidata ne remplacent pas une étude du marché Airbnb.')
