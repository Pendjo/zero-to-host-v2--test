"""Zero to Host V2 — pilote juridique autonome, sans dépendance Overpass."""
import json
from pathlib import Path
import streamlit as st

st.set_page_config(page_title="Zero to Host | Pilote V2", page_icon="🏠", layout="wide")
DATA = json.loads((Path(__file__).parent / 'data' / 'villes.json').read_text(encoding='utf-8'))
CITIES = {row['ville']: row for row in DATA}
st.title('🏠 Zero to Host — V2 pilote')
st.caption('Module juridique pilote · données documentées · aucune dépendance à Overpass')
st.warning('Prototype autonome : ne remplace pas votre application actuelle. Ne constitue pas un avis juridique.')
city = st.selectbox('Choisir une ville', sorted(CITIES))
address = st.text_input('Adresse du bien (facultative)', placeholder='Rue et numéro, code postal')
record = CITIES[city]
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
st.info('À développer ensuite : géocodage précis, temps de trajet routier de 20 min, base de POI hors ligne, 30 communes et PDF complet. Aucun temps de trajet n’est inventé dans ce pilote.')
