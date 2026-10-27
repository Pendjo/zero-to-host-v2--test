# Zero to Host V2 — pilote juridique

Prototype **séparé** de l'application existante. Ne remplacez pas votre `app.py` de production avant test.

## Tester localement

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Contenu

- `app.py` : interface juridique + checklist + simulateur financier simplifié.
- `data/villes.json` : 3 villes pilotes avec statut non confirmé, plus Stuttgart et Mannheim documentées.

## Important

- Le statut « Non vérifiée » n'est pas une affirmation d'absence de Satzung.
- Les URL des trois mairies sont des points d'entrée généraux, **pas** des confirmations réglementaires.
- Aucun temps de trajet n'est calculé dans cette version : un moteur routier sera nécessaire.
- Aucune statistique de marché Airbnb n'est incluse.
- Sources réglementaires : https://mlw.baden-wuerttemberg.de/de/bauen-wohnen/wohnungsbau/zweckentfremdungsverbot/ ; https://www.stuttgart.de/leben/bauen/baurecht/zweckentfremdung ; https://www.mannheim.de/de/nachrichten/mannheim-verlaengert-zweckentfremdungsverbot-fuer-wohnraum
