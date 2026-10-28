# Spordle Hockey Stats — documentation

[Français](#français) | [English](#english)

---

## Français

### Description

**Spordle Hockey Stats** (`spordle_scraper`) est un module complémentaire (add-on) Home Assistant qui lit les pages publiques d'une équipe de hockey sur la plateforme **Spordle** (`page.spordle.com`) et publie les données dans Home Assistant par **MQTT** (découverte automatique MQTT Discovery) : alignement, horaire, dernier match, classement et statistiques des joueurs.

Le module est conçu pour une équipe de la ligue **LHQCA** sur Spordle : les adresses consultées sont de la forme `https://page.spordle.com/fr/lhqca/teams/<team_id>`, et la ligue ainsi que les horaires (saison régulière, hors concours) sont fixés dans le code. Voir [Limites connues](#limites-connues).

Les pages sont chargées par un vrai navigateur Chromium sans interface (Playwright), puisque le site est généré en JavaScript.

### Fonctionnalités

- **Alignement** de l'équipe : gardiens, joueurs (nom, numéro, position, statistiques) et personnel (nom, rôle).
- **Horaire de la saison complète** : le module bascule le filtre « 7 prochains jours » vers « Saison » et fait défiler la page pour charger tous les matchs ; la vue « 7 prochains jours » est aussi lue pour ne manquer aucun match à venir.
- **Historique des matchs joués** conservé d'un cycle à l'autre (`/data/matchs_joues.json`) : un match joué ne disparaît pas si le site ne l'affiche plus.
- **Dernier match** et **prochain match** (date, heure, aréna, équipes, pointage, statut).
- **Classement** de l'équipe, de sa division et de toute la ligue (rang dans la ligue). Pour la LHQCA, les victoires et défaites détaillées (VR/VP/VF, DR/DP/DF) sont additionnées dans `V` et `D`.
- **Statistiques des joueurs de la ligue**, saison régulière et hors concours.
- **Joueur suivi** (facultatif) : points en saison régulière et hors concours d'un joueur choisi.
- **Logos des équipes** téléchargés localement et servis par Home Assistant sous `/local/spordle_logos/`.
- **Rythme de mise à jour adaptatif** les jours de match (toutes les 10 min pendant un match).
- **Données conservées en cas d'échec** : si une page ne se charge pas, les capteurs gardent leur dernière valeur (messages MQTT retenus) au lieu d'être effacés.

### Installation

Prérequis : un **broker MQTT** (par exemple le module complémentaire officiel **Mosquitto broker**) et l'**intégration MQTT** configurée dans Home Assistant.

1. Dans Home Assistant : **Paramètres → Modules complémentaires → Boutique des modules complémentaires → ⋮ (en haut à droite) → Dépôts**.
2. Ajoutez l'adresse du dépôt : `https://github.com/Frazou1/spordle-addon`, puis fermez la fenêtre.
3. Rechargez la boutique au besoin, ouvrez **Spordle Hockey Stats** et cliquez sur **Installer**. L'image est construite sur votre appareil à partir d'une image Playwright : la première installation peut prendre plusieurs minutes.
4. Dans l'onglet **Configuration**, remplacez les valeurs par celles de votre équipe (voir ci-dessous) et enregistrez.
5. Dans l'onglet **Info**, cliquez sur **Démarrer**, puis suivez l'onglet **Journal**.

Architectures prises en charge : `amd64`, `aarch64`.

### Configuration

| Option | Type | Défaut du code | Rôle |
|---|---|---|---|
| `team_id` | texte (obligatoire) | — | Numéro de l'équipe sur Spordle : le nombre à la fin de l'adresse `https://page.spordle.com/fr/lhqca/teams/<team_id>`. Il sert aussi à nommer les capteurs. |
| `team_name` | texte (obligatoire) | — | Nom (ou partie du nom) de l'équipe tel qu'il apparaît dans la colonne « Équipe » du classement. La comparaison ignore la casse et cherche le texte **à l'intérieur** du nom complet. |
| `tracked_player` | texte (facultatif) | vide | Nom (ou partie du nom, par exemple le nom de famille) d'un joueur à suivre, cherché dans la colonne « Nom » des statistiques de la ligue. Laissez vide pour ne pas créer de capteur joueur. |
| `update_interval_hours` | entier | `6` | Intervalle normal entre deux lectures, en heures. |
| `mqtt_host` | texte | `core-mosquitto` | Adresse du broker MQTT (`core-mosquitto` = module Mosquitto de Home Assistant). |
| `mqtt_port` | entier | `1883` | Port du broker MQTT. |
| `mqtt_user` | texte (facultatif) | vide | Utilisateur MQTT. |
| `mqtt_password` | texte (facultatif) | vide | Mot de passe MQTT. L'identification n'est envoyée que si l'utilisateur **et** le mot de passe sont remplis. |

> Les valeurs proposées par défaut dans l'onglet Configuration correspondent à une équipe précise : remplacez `team_id`, `team_name` et `tracked_player` par les vôtres.

Exemple (valeurs fictives) :

```yaml
team_id: "123456"
team_name: "MON ÉQUIPE"
tracked_player: "tremblay"
update_interval_hours: 6
mqtt_host: core-mosquitto
mqtt_port: 1883
mqtt_user: mqtt_ha
mqtt_password: "votre_mot_de_passe"
```

Avec le module Mosquitto, un utilisateur Home Assistant ordinaire (non administrateur) créé pour l'occasion peut servir d'identifiant MQTT.

### Entités créées

Les capteurs sont créés par MQTT Discovery (sujets `homeassistant/sensor/.../config`, messages retenus). Il n'y a pas d'appareil associé : l'identifiant d'entité est généré par Home Assistant à partir du nom. Les identifiants ci-dessous sont ceux que Home Assistant produit normalement pour `team_id: "123456"`, `team_name: "MON ÉQUIPE"` et `tracked_player: "tremblay"` ; vérifiez-les dans **Paramètres → Appareils et services → Entités** (recherche « Spordle »).

| Nom du capteur | Entité (exemple) | `unique_id` | État | Attributs principaux |
|---|---|---|---|---|
| `Spordle Équipe <team_id> Alignement` | `sensor.spordle_equipe_123456_alignement` | `spordle_team_<team_id>_roster` | `12 joueurs \| 3 instructeurs` | `gardiens`, `joueurs` (`nom`, `numero`, `position`, `stats`), `personnel` (`nom`, `role`) |
| `Spordle Équipe <team_id> Horaire` | `sensor.spordle_equipe_123456_horaire` | `spordle_team_<team_id>_schedule` | `<date> <heure> - <aréna>` du prochain match, ou `Aucun match prévu` | `prochain_match`, `matchs_a_venir`, `nb_total`, `dates_trouvees`, `prochains_matchs` |
| `Spordle Équipe <team_id> Dernier match` | `sensor.spordle_equipe_123456_dernier_match` | `spordle_team_<team_id>_last_match` | `<date> : <équipes> <pointage>` | `match`, `tous_les_matchs_joues` |
| `Spordle Classement <Team_name>` | `sensor.spordle_classement_mon_equipe` | `spordle_team_<team_id>_standings` | `<rang>e rang`, ou `Saison en cours` si l'équipe n'est pas trouvée | `mon_equipe`, `classement_complet`, `classement_division`, `rang_ligue`, `nb_equipes_ligue`, `classement_ligue` |
| `Spordle Équipe <team_id> Stats hors concours` | `sensor.spordle_equipe_123456_stats_hors_concours` | `spordle_team_<team_id>_stats_hors_concours` | `<n> joueurs` | `joueurs` (une ligne par joueur de la ligue) |
| `Spordle Équipe <team_id> Stats saison reguliere` | `sensor.spordle_equipe_123456_stats_saison_reguliere` | `spordle_team_<team_id>_stats_saison_reguliere` | `<n> joueurs` | `joueurs` |
| `Spordle Joueur <Tracked_player>` (si `tracked_player` est rempli) | `sensor.spordle_joueur_tremblay` | `spordle_player_<joueur>` | `SR: <pts> pts \| HC: <pts> pts` | `stats_saison_reguliere`, `stats_hors_concours` |

Chaque match (dans `prochain_match`, `matchs_a_venir`, `match`, `tous_les_matchs_joues`) contient : `numero`, `date` (ex. `SAM. 8 NOV.`), `date_iso`, `heure` (ex. `13h30`), `iso`, `arene`, `equipes`, `equipes_details` (`nom`, `logo_remote`, `logo_local`), `score` (ex. `4-2`), `statut` (`À VENIR`, `FINAL`, `EN COURS`, `PROLONGATION`, `FUSILLADE`) et `joue`.

Les colonnes des statistiques et du classement sont reprises telles quelles du site (ex. `#`, `Équipe`, `MJ`, `V`, `D`, `N`, `PTS`, `Nom`). Les lignes du classement ont aussi `logo_local`, utilisable directement comme image (`/local/spordle_logos/<nom>.png`).

### Exemples d'utilisation

Carte Markdown du prochain match :

```yaml
type: markdown
content: >
  {% set m = state_attr('sensor.spordle_equipe_123456_horaire', 'prochain_match') %}
  {% if m %}
  **Prochain match :** {{ m.date }} {{ m.heure }}<br>
  {{ m.equipes | join(' vs ') }}<br>
  {{ m.arene }}
  {% else %}
  Aucun match prévu.
  {% endif %}
```

Notification à chaque nouveau résultat :

```yaml
alias: Hockey - nouveau résultat
triggers:
  - trigger: state
    entity_id: sensor.spordle_equipe_123456_dernier_match
conditions:
  - condition: template
    value_template: "{{ trigger.from_state is not none and trigger.from_state.state not in ['unknown', 'unavailable'] }}"
actions:
  - action: notify.notify
    data:
      title: Hockey
      message: "{{ state_attr('sensor.spordle_equipe_123456_dernier_match', 'match').score }} — {{ state_attr('sensor.spordle_equipe_123456_dernier_match', 'match').equipes | join(' vs ') }}"
mode: single
```

### Rythme de mise à jour

Après chaque lecture, le module calcule le délai avant la suivante (`rythme.py`) et retient le plus court des délais suivants :

- **intervalle normal** : `update_interval_hours` ;
- **avant un match** : réveil à l'heure de début du prochain match, si elle arrive avant l'intervalle normal ;
- **pendant un match** : toutes les **10 minutes**, jusqu'à ce que le résultat soit publié sur Spordle (au plus 4 h après le début) ;
- **après un match** : toutes les **heures** pendant **3 h** après la fin détectée (moment où le résultat a été lu, ou début + 4 h sans résultat).

Seuls les matchs commencés depuis moins de 12 h sont pris en compte, et le délai n'est jamais inférieur à 1 minute. Le journal affiche la raison, par exemple `[ATTENTE] 10 min (match en cours ...)`.

### Fichiers persistants

| Emplacement | Contenu |
|---|---|
| `/data/matchs_joues.json` | Historique des matchs joués (interne au module). |
| `/data/rythme_fins.json` | Heures de fin détectées des matchs récents (gardées 2 jours). |
| `/config/www/spordle_logos/` | Logos des équipes, servis sous `/local/spordle_logos/`. Repli dans `/share/spordle_logos/` si `/config` n'est pas disponible. |
| `/share/spordle_roster_debug.html` | Dernière page d'alignement lue (aide au diagnostic), réécrite à chaque cycle. |

### Dépannage

Consultez l'onglet **Journal** du module. Chaque cycle commence par `[START] Scraping Spordle` et se termine par `[FIN] Cycle terminé`.

| Message dans le journal | Cause probable et solution |
|---|---|
| `[MQTT ERROR] Échec sur ... : message non confirmé par le broker (identifiants MQTT ?)` | Le broker refuse la connexion : remplissez `mqtt_user` **et** `mqtt_password`, vérifiez `mqtt_host` et `mqtt_port`. |
| `[MQTT ERROR] ... Connection refused` ou nom d'hôte introuvable | Broker arrêté ou mauvaise adresse : vérifiez que Mosquitto est démarré. |
| `[SCRAPE ERROR] Échec sur <page>` / `[PUBLICATION] Pages en échec, capteurs conservés` | Le site n'a pas répondu (réseau, lenteur, blocage). Les capteurs gardent leur dernière valeur ; le prochain cycle réessaiera. |
| `[SCHEDULE] Filtre après essai 2 : ... -> NON appliqué` | Le filtre « Saison » n'a pas pu être choisi (site modifié ou lent) : seuls les matchs visibles par défaut sont lus. |
| `[ROSTER] Aucun joueur lu : alignement précédent conservé.` | Page d'alignement vide ou bloquée ; voir `/share/spordle_roster_debug.html`. |
| `[PARSING STANDINGS] Équipe introuvable dans le classement.` | `team_name` ne correspond à aucune ligne de la colonne « Équipe » du classement de la ligue. |
| Capteur `Classement` à `Saison en cours` | `team_name` introuvable dans le classement de la page d'équipe. |
| Pas de capteur joueur | `tracked_player` vide, ou les deux pages de statistiques ont échoué. Si le capteur existe mais affiche `0 pts`, le nom n'a pas été trouvé dans la colonne « Nom ». |
| Aucune entité dans Home Assistant | Intégration MQTT absente ou découverte désactivée, ou erreur MQTT dans le journal. |

Les logos n'apparaissent pas : vérifiez que les fichiers existent dans `/config/www/spordle_logos/` ; si le dossier `www` vient d'être créé, Home Assistant doit être redémarré une fois pour servir `/local/`.

### Limites connues

- La ligue (**LHQCA**), son identifiant de ligue et les identifiants d'horaire (saison régulière et hors concours) sont **écrits dans le code** (`main.py`). Une équipe d'une autre ligue Spordle, ou une nouvelle saison avec d'autres identifiants, demande une modification du code.
- Le module lit le HTML du site : une refonte de Spordle peut le casser sans avertissement.
- Les dates et heures sont converties à l'heure de l'Est (`America/Toronto`).
- Un seul joueur suivi par instance.
- Selon la version de Home Assistant, l'état texte peut s'afficher entre guillemets, puisque le module publie l'état encodé en JSON.

### Revenir à une version précédente

Les versions publiées sont étiquetées dans le dépôt (par exemple `v1.6.2`, `v1.7.8` ; liste complète sous l'onglet **Tags** de GitHub). La boutique installe toujours la dernière version de la branche `main`. Pour revenir en arrière :

1. **Sauvegarde automatique** : si l'option « Sauvegarder avant la mise à jour » était cochée, restaurez la sauvegarde partielle du module dans **Paramètres → Système → Sauvegardes**.
2. **Module local** : téléchargez l'archive de l'étiquette voulue, par exemple `https://github.com/Frazou1/spordle-addon/archive/refs/tags/v1.7.8.zip`, copiez son dossier `spordle_scraper` dans le dossier `/addons` de Home Assistant (partage Samba ou module SSH), puis **Boutique → ⋮ → Rechercher des mises à jour** : le module apparaît sous **Modules complémentaires locaux**. Arrêtez la version de la boutique avant de démarrer la version locale ; la configuration est à ressaisir.

---

## English

### Description

**Spordle Hockey Stats** (`spordle_scraper`) is a Home Assistant add-on that reads a hockey team's public pages on the **Spordle** platform (`page.spordle.com`) and publishes the data to Home Assistant over **MQTT** (MQTT Discovery): roster, schedule, last game, standings and player statistics.

The add-on is built for a team of the **LHQCA** league on Spordle: the pages it reads look like `https://page.spordle.com/fr/lhqca/teams/<team_id>`, and the league and its schedules (regular season, exhibition) are fixed in the code. See [Known limitations](#known-limitations).

Pages are loaded by a real headless Chromium browser (Playwright), because the site is rendered with JavaScript.

### Features

- Team **roster**: goalies, players (name, number, position, statistics) and staff (name, role).
- **Full-season schedule**: the add-on switches the "next 7 days" filter to "Season" and scrolls the page to load every game; the "next 7 days" view is also read so no upcoming game is missed.
- **Played-games history** kept across cycles (`/data/matchs_joues.json`): a played game does not disappear when the site stops showing it.
- **Last game** and **next game** (date, time, arena, teams, score, status).
- **Standings** for the team, its division and the whole league (league rank). For the LHQCA, detailed wins and losses (VR/VP/VF, DR/DP/DF) are added up into `V` and `D`.
- **League player statistics**, regular season and exhibition.
- **Tracked player** (optional): regular-season and exhibition points of one chosen player.
- **Team logos** downloaded locally and served by Home Assistant under `/local/spordle_logos/`.
- **Adaptive update rhythm** on game days (every 10 min during a game).
- **Data kept on failure**: if a page fails to load, sensors keep their last value (retained MQTT messages) instead of being wiped.

### Installation

Requirements: an **MQTT broker** (for example the official **Mosquitto broker** add-on) and the **MQTT integration** set up in Home Assistant.

1. In Home Assistant: **Settings → Add-ons → Add-on Store → ⋮ (top right) → Repositories**.
2. Add the repository URL `https://github.com/Frazou1/spordle-addon` and close the dialog.
3. Reload the store if needed, open **Spordle Hockey Stats** and click **Install**. The image is built on your device from a Playwright image, so the first install can take several minutes.
4. In the **Configuration** tab, replace the values with your team's (see below) and save.
5. In the **Info** tab, click **Start**, then watch the **Log** tab.

Supported architectures: `amd64`, `aarch64`.

### Configuration

| Option | Type | Code default | Purpose |
|---|---|---|---|
| `team_id` | string (required) | — | The team's Spordle number: the number at the end of `https://page.spordle.com/fr/lhqca/teams/<team_id>`. Also used to name the sensors. |
| `team_name` | string (required) | — | Team name (or part of it) as shown in the "Équipe" column of the standings. Matching is case-insensitive and looks for the text **inside** the full name. |
| `tracked_player` | string (optional) | empty | Name (or part of it, e.g. the last name) of a player to follow, searched in the "Nom" column of the league statistics. Leave empty for no player sensor. |
| `update_interval_hours` | integer | `6` | Normal interval between two reads, in hours. |
| `mqtt_host` | string | `core-mosquitto` | MQTT broker address (`core-mosquitto` = Home Assistant's Mosquitto add-on). |
| `mqtt_port` | integer | `1883` | MQTT broker port. |
| `mqtt_user` | string (optional) | empty | MQTT user. |
| `mqtt_password` | string (optional) | empty | MQTT password. Credentials are only sent when both user **and** password are set. |

> The values pre-filled in the Configuration tab belong to one specific team: replace `team_id`, `team_name` and `tracked_player` with your own.

Example (made-up values):

```yaml
team_id: "123456"
team_name: "MY TEAM"
tracked_player: "smith"
update_interval_hours: 6
mqtt_host: core-mosquitto
mqtt_port: 1883
mqtt_user: mqtt_ha
mqtt_password: "your_password"
```

With the Mosquitto add-on, a regular (non-admin) Home Assistant user created for this purpose can be used as the MQTT login.

### Created entities

Sensors are created through MQTT Discovery (`homeassistant/sensor/.../config` topics, retained). There is no device attached, so Home Assistant builds the entity ID from the name. The IDs below are what Home Assistant normally generates for `team_id: "123456"`, `team_name: "MY TEAM"` and `tracked_player: "smith"`; check them under **Settings → Devices & services → Entities** (search "Spordle").

| Sensor name | Entity (example) | `unique_id` | State | Main attributes |
|---|---|---|---|---|
| `Spordle Équipe <team_id> Alignement` (roster) | `sensor.spordle_equipe_123456_alignement` | `spordle_team_<team_id>_roster` | `12 joueurs \| 3 instructeurs` | `gardiens`, `joueurs` (`nom`, `numero`, `position`, `stats`), `personnel` (`nom`, `role`) |
| `Spordle Équipe <team_id> Horaire` (schedule) | `sensor.spordle_equipe_123456_horaire` | `spordle_team_<team_id>_schedule` | `<date> <time> - <arena>` of the next game, or `Aucun match prévu` | `prochain_match`, `matchs_a_venir`, `nb_total`, `dates_trouvees`, `prochains_matchs` |
| `Spordle Équipe <team_id> Dernier match` (last game) | `sensor.spordle_equipe_123456_dernier_match` | `spordle_team_<team_id>_last_match` | `<date> : <teams> <score>` | `match`, `tous_les_matchs_joues` |
| `Spordle Classement <Team_name>` (standings) | `sensor.spordle_classement_my_team` | `spordle_team_<team_id>_standings` | `<rank>e rang`, or `Saison en cours` if the team is not found | `mon_equipe`, `classement_complet`, `classement_division`, `rang_ligue`, `nb_equipes_ligue`, `classement_ligue` |
| `Spordle Équipe <team_id> Stats hors concours` (exhibition) | `sensor.spordle_equipe_123456_stats_hors_concours` | `spordle_team_<team_id>_stats_hors_concours` | `<n> joueurs` | `joueurs` (one row per league player) |
| `Spordle Équipe <team_id> Stats saison reguliere` (regular season) | `sensor.spordle_equipe_123456_stats_saison_reguliere` | `spordle_team_<team_id>_stats_saison_reguliere` | `<n> joueurs` | `joueurs` |
| `Spordle Joueur <Tracked_player>` (when `tracked_player` is set) | `sensor.spordle_joueur_smith` | `spordle_player_<player>` | `SR: <pts> pts \| HC: <pts> pts` | `stats_saison_reguliere`, `stats_hors_concours` |

Each game (in `prochain_match`, `matchs_a_venir`, `match`, `tous_les_matchs_joues`) has: `numero`, `date` (e.g. `SAM. 8 NOV.`), `date_iso`, `heure` (e.g. `13h30`), `iso`, `arene`, `equipes`, `equipes_details` (`nom`, `logo_remote`, `logo_local`), `score` (e.g. `4-2`), `statut` (`À VENIR`, `FINAL`, `EN COURS`, `PROLONGATION`, `FUSILLADE`) and `joue`.

Statistics and standings columns are copied as-is from the site (e.g. `#`, `Équipe`, `MJ`, `V`, `D`, `N`, `PTS`, `Nom`). Standings rows also carry `logo_local`, usable directly as an image (`/local/spordle_logos/<name>.png`).

### Usage examples

Markdown card for the next game:

```yaml
type: markdown
content: >
  {% set m = state_attr('sensor.spordle_equipe_123456_horaire', 'prochain_match') %}
  {% if m %}
  **Next game:** {{ m.date }} {{ m.heure }}<br>
  {{ m.equipes | join(' vs ') }}<br>
  {{ m.arene }}
  {% else %}
  No game scheduled.
  {% endif %}
```

Notification on each new result:

```yaml
alias: Hockey - new result
triggers:
  - trigger: state
    entity_id: sensor.spordle_equipe_123456_dernier_match
conditions:
  - condition: template
    value_template: "{{ trigger.from_state is not none and trigger.from_state.state not in ['unknown', 'unavailable'] }}"
actions:
  - action: notify.notify
    data:
      title: Hockey
      message: "{{ state_attr('sensor.spordle_equipe_123456_dernier_match', 'match').score }} — {{ state_attr('sensor.spordle_equipe_123456_dernier_match', 'match').equipes | join(' vs ') }}"
mode: single
```

### Update rhythm

After each read, the add-on computes the delay before the next one (`rythme.py`) and keeps the shortest of:

- **normal interval**: `update_interval_hours`;
- **before a game**: wake up at the next game's start time, if it comes before the normal interval;
- **during a game**: every **10 minutes** until the result is posted on Spordle (at most 4 h after the start);
- **after a game**: every **hour** for **3 h** after the detected end (when the result was read, or start + 4 h without a result).

Only games that started less than 12 h ago are considered, and the delay is never shorter than 1 minute. The log shows the reason, e.g. `[ATTENTE] 10 min (match en cours ...)`.

### Persistent files

| Location | Content |
|---|---|
| `/data/matchs_joues.json` | Played-games history (internal to the add-on). |
| `/data/rythme_fins.json` | Detected end times of recent games (kept 2 days). |
| `/config/www/spordle_logos/` | Team logos, served under `/local/spordle_logos/`. Falls back to `/share/spordle_logos/` when `/config` is unavailable. |
| `/share/spordle_roster_debug.html` | Last roster page read (diagnostic aid), rewritten every cycle. |

### Troubleshooting

Check the add-on's **Log** tab. Each cycle starts with `[START] Scraping Spordle` and ends with `[FIN] Cycle terminé`.

| Log message | Likely cause and fix |
|---|---|
| `[MQTT ERROR] Échec sur ... : message non confirmé par le broker (identifiants MQTT ?)` | The broker refuses the connection: set both `mqtt_user` **and** `mqtt_password`, check `mqtt_host` and `mqtt_port`. |
| `[MQTT ERROR] ... Connection refused` or unknown host | Broker stopped or wrong address: make sure Mosquitto is running. |
| `[SCRAPE ERROR] Échec sur <page>` / `[PUBLICATION] Pages en échec, capteurs conservés` | The site did not answer (network, slowness, blocking). Sensors keep their last value; the next cycle retries. |
| `[SCHEDULE] Filtre après essai 2 : ... -> NON appliqué` | The "Season" filter could not be selected (site changed or slow): only the games shown by default are read. |
| `[ROSTER] Aucun joueur lu : alignement précédent conservé.` | Roster page empty or blocked; see `/share/spordle_roster_debug.html`. |
| `[PARSING STANDINGS] Équipe introuvable dans le classement.` | `team_name` matches no row of the "Équipe" column in the league standings. |
| `Classement` sensor shows `Saison en cours` | `team_name` not found in the team page standings. |
| No player sensor | `tracked_player` is empty, or both statistics pages failed. If the sensor exists but shows `0 pts`, the name was not found in the "Nom" column. |
| No entity in Home Assistant | MQTT integration missing or discovery disabled, or an MQTT error in the log. |

Logos do not show: check that the files exist in `/config/www/spordle_logos/`; if the `www` folder was just created, Home Assistant must be restarted once to serve `/local/`.

### Known limitations

- The league (**LHQCA**), its league ID and the schedule IDs (regular season and exhibition) are **hard-coded** in `main.py`. A team from another Spordle league, or a new season with different IDs, requires a code change.
- The add-on parses the site's HTML: a Spordle redesign can break it without warning.
- Dates and times are converted to Eastern time (`America/Toronto`).
- One tracked player per instance.
- Depending on the Home Assistant version, the text state may show between quotes, because the add-on publishes the state JSON-encoded.

### Rolling back to a previous version

Released versions are tagged in the repository (for example `v1.6.2`, `v1.7.8`; full list under the GitHub **Tags** tab). The store always installs the latest version from the `main` branch. To go back:

1. **Automatic backup**: if "Back up before updating" was checked, restore the add-on's partial backup under **Settings → System → Backups**.
2. **Local add-on**: download the archive of the wanted tag, e.g. `https://github.com/Frazou1/spordle-addon/archive/refs/tags/v1.7.8.zip`, copy its `spordle_scraper` folder into Home Assistant's `/addons` folder (Samba share or SSH add-on), then **Store → ⋮ → Check for updates**: the add-on shows up under **Local add-ons**. Stop the store version before starting the local one; the configuration has to be entered again.
