# DomoLink Tuya OEM Multi-Brand for Home Assistant

[![Documentation Officielle](https://img.shields.io/badge/Documentation-socratemobile.fr-06b6d4.svg?logo=googlechrome&logoColor=white)](https://socratemobile.fr/integration.html?id=domolink-tuya-oem)
[![Version 2.0.0](https://img.shields.io/badge/version-2.0.0-blue.svg)](https://github.com/SocrateMobile/DomoLink-Tuya-OEM/releases)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![Home Assistant](https://img.shields.io/badge/Home--Assistant-2024.1%2B-blue.svg)](https://www.home-assistant.io/)

> 🌐 **Site officiel & Documentation complète** : Retrouvez le guide d'installation pas à pas, les entités supportées et les exemples d'automatisations sur [socratemobile.fr](https://socratemobile.fr/integration.html?id=domolink-tuya-oem).

Intégration personnalisée Home Assistant complète avec **panneau latéral au look DomoLink (Glassmorphism)** permettant de connecter, classifier et piloter tous les objets connectés issus des applications **Tuya en marque blanche (OEM)** :

* 🛒 **Thank's (GiFi)** (`thanksapp`)
* 🛒 **Lidl Home (Silvercrest)** (`lidlhomesmart`)
* 🛒 **Action LSC Smart Connect** (`lscsmartconnectionsmart`)
* 🛒 **Nedis SmartLife** (`nedissmartlife`)
* 🛒 **Calex Smart** (`calexsmartsmart`)
* 🛒 **Konyks** (`konyks`)
* 🌐 **Smart Life** / **Tuya Smart (Officiel)**
* ⚙️ **Autre marque OEM personnalisée** (saisie directe du schéma et des clés)

---

## 🌟 Nouveautés majeures de la Version 2.0.0

* **✨ Panneau Latéral DomoLink intégré :**
  * Accès direct depuis la barre latérale de Home Assistant.
  * **Onglet Appareils** : affichage par type de produit avec les photos officielles Tuya, état de connexion (🟢 En ligne / 🔴 Hors ligne / ⚡ Contrôle Local LAN), interrupteurs, variateurs de luminosité, température de blanc Kelvin, sélecteur de couleur RVB et retour de télémétrie en direct.
  * **Inspecteur de DataPoints (DPs)** : visualisez et testez n'importe quel DP brut ou décodé en un clic.
  * **Onglet Paramètres & Comptes** : connectez ou supprimez des comptes directement depuis le panneau, renommez les appareils, forcez les types de matériel et lancez un scan réseau local LAN.
* **📹 Plateforme Caméra (`camera`) :**
  * Support des flux vidéo en direct (RTSP / HLS), snapshots et alertes mouvements.
  * Commandes dédiées : activation du mode privé, sensibilité et suivi de mouvement.
* **🧠 Moteur de classification & décodage universel des DPs (`dp_registry.py`) :**
  * Détection automatique fiable entre ampoules, prises, caméras, capteurs et thermostats.
  * Résolution des conflits de DPs numériques (ex: DP 20 bool switch vs int voltage).
  * Encodage/décodage de couleur HSV bidirectionnel (protocoles 12 et 14 caractères hex).
* **📶 Suivi de connectivité :**
  * Création automatique d'une entité binaire `Connectivité` pour chaque appareil.

---

## 🚀 Installation & Mise à jour

### Via HACS (Dépôt personnalisé)
1. Dans HACS, ouvrez **DomoLink Tuya OEM Multi-Brand**.
2. Téléchargez ou mettez à jour vers la version **v2.0.0**.
3. Redémarrez Home Assistant.
4. Le panneau **DomoLink Tuya** apparaîtra immédiatement dans la barre latérale gauche !
