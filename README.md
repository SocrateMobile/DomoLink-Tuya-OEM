# DomoLink Tuya OEM Multi-Brand for Home Assistant
 
 // Arrêté pour le moment //
 
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![Home Assistant](https://img.shields.io/badge/Home--Assistant-2024.1%2B-blue.svg)](https://www.home-assistant.io/)

Intégration personnalisée Home Assistant permettant de connecter et piloter directement les objets connectés issus des applications **Tuya en marque blanche (OEM)**, notamment :

* 🛒 **Thank's (GiFi)** (`thanksapp`)
* 🛒 **Lidl Home (Silvercrest)** (`lidlhomesmart`)
* 🛒 **Action LSC Smart Connect** (`lscsmartconnectionsmart`)
* 🛒 **Nedis SmartLife** (`nedissmartlife`)
* 🛒 **Calex Smart** (`calexsmartsmart`)
* 🛒 **Konyks** (`konyks`)
* 🌐 **Smart Life** / **Tuya Smart**
* ⚙️ **Autre marque OEM personnalisée** (saisie directe du schéma et des clés)

---

## 🌟 Fonctionnalités

* **Multi-Comptes & Multi-Marques :** Ajoutez autant de comptes et d'enseignes que vous le souhaitez (ex: un compte Thank's GiFi ET un compte Lidl Home en parallèle).
* **Clés Pré-configurées :** Les clés de signature (`client_id`, `secret`, `schema`) ont été rétro-ingéniées directement depuis les applications officielles et sont intégrées dans le code. Vous n'avez qu'à entrer vos identifiants mobiles (email / mot de passe).
* **Multi-Plateformes :**
  * **Interrupteurs & Prises (`switch`) :** Prises simples, multiprises avec contrôle individuel des ports, interrupteurs muraux.
  * **Éclairage (`light`) :** Ampoules et bandeaux LED (ON/OFF, luminosité, température de couleur, couleur RVB).
  * **Volets & Stores (`cover`) :** Positionnement en pourcentage, montée/descente/arrêt.
  * **Chauffage & Thermostats (`climate`) :** Consigne de température, température ambiante, modes.
  * **Capteurs (`sensor`) :** Mesure de puissance (W), tension (V), intensité (mA), énergie consommée (kWh), niveau de batterie (%).
  * **Capteurs binaires (`binary_sensor`) :** Détecteurs d'ouverture de porte/fenêtre, détecteurs de mouvement (PIR), fuite d'eau, fumée.

---

## 🚀 Installation

### Méthode 1 : Copie Manuelle
1. Copiez le dossier `custom_components/domolink_tuya_oem` dans votre répertoire Home Assistant :
   ```
   /config/custom_components/domolink_tuya_oem
   ```
2. Redémarrez Home Assistant.

### Méthode 2 : Via HACS (Dépôt personnalisé)
1. Dans HACS, cliquez sur les 3 points en haut à droite > **Dépôts personnalisés**.
2. Ajoutez l'URL du dépôt et choisissez la catégorie **Intégration**.
3. Téléchargez l'intégration et redémarrez Home Assistant.

---

## ⚙️ Configuration

1. Dans Home Assistant, allez dans **Paramètres > Appareils et services > Ajouter une intégration**.
2. Recherchez **DomoLink Tuya OEM Multi-Brand**.
3. Choisissez votre enseigne dans la liste déroulante (ex: **Thank's (GiFi)**).
4. Saisissez votre **email** et votre **mot de passe** de l'application mobile.
5. Validez : vos équipements sont automatiquement découverts et créés !

Pour ajouter une autre enseigne ou un deuxième compte, répétez simplement l'opération.
