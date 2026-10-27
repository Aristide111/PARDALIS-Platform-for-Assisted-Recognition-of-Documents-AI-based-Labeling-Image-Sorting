# PARDALIS
Platform for Assisted Recognition of Documents, AI-based Labeling, Image Sorting

[Version française](#version-française)

A Gradio web app that identifies what images or PDFs show using a vision model hosted on the Albert API (Etalab), then renames the files, generates CSV reports and charts, and lets you validate and correct the results to measure the model accuracy.

## Features

- **Two identification approaches**
- **Approach 1: closed reference list.** You enter items (identifier and characteristics) through a form or a CSV import. The model can only answer with an identifier from the list, or "Non identifié" if nothing matches.
- **Approach 2: free identification.** The model proposes a name on its own from what it sees. Variants of the same name are merged automatically (can be turned off).
- Optional context to guide the model.
- Supports `.jpg`, `.jpeg`, `.png` images and PDFs (each page is converted to an image).
- Automatic file renaming.
- ZIP export: original and renamed images, CSV, per-entity confidence charts and overall distribution.
- **Validation viewer**: confirm or correct each prediction, then export a corrected archive with overall and per-entity accuracy.

## Requirements

- Python 3.9 or newer
- An Albert API key (https://albert.api.etalab.gouv.fr)

## Installation

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` file at the project root:

```env
ALBERT=your_albert_api_key
```

## Running

```bash
python app_identification.py
```

The app starts on `http://127.0.0.1:7860` (or the next free port).

## Usage

1. **Tab 1: Analysis**
   - Pick an approach.
   - Add items or import a CSV for Approach 1.
   - Add context, drop images or PDFs.
   - Click run analysis and download the raw ZIP archive.
2. **Tab 2: Viewer**
   - Open the viewer, confirm or correct each image.
   - Generate the corrected ZIP archive to get the corrections CSV and the accuracy chart.

---

# Version française

[English version](#pardalis)

Application web Gradio qui identifie ce que montrent des images ou des PDF grâce à un modèle de vision hébergé sur l'API Albert (Etalab), puis renomme les fichiers, génère des rapports CSV et des graphiques, et permet de valider et corriger les résultats pour mesurer la précision du modèle.

## Fonctionnalités

- **Deux approches d'identification**
- **Approche 1 : référentiel fermé.** Saisie des entrées (identifiant et caractéristiques) via formulaire ou import CSV. Le modèle répond uniquement par un identifiant de la liste ou « Non identifié ».
- **Approche 2 : identification libre.** Le modèle propose un nom à partir de ce qu'il voit. Regroupement automatique des variantes (désactivable).
- Contexte facultatif.
- Support des images `.jpg`, `.jpeg`, `.png` et des PDF.
- Renommage automatique des fichiers.
- Export ZIP : images, CSV, graphiques de certitude.
- **Visionneuse de validation** : validation ou correction de chaque prédiction, export d'une archive corrigée.

## Prérequis

- Python 3.9 ou plus récent
- Une clé d'API Albert (https://albert.api.etalab.gouv.fr)

## Installation

```bash
python -m venv .venv
source .venv/bin/activate        # Windows : .venv\Scripts\activate
pip install -r requirements.txt
```

Créez un fichier `.env` à la racine du projet :

```env
ALBERT=votre_cle_api_albert
```

## Lancement

```bash
python app_identification.py
```

L'application démarre sur `http://127.0.0.1:7860`.

## Utilisation

1. **Onglet 1 : Analyse**
   - Choix de l'approche.
   - Saisie du référentiel ou import CSV.
   - Dépôt des fichiers et lancement de l'analyse.
2. **Onglet 2 : Visionneuse**
   - Validation ou correction des prédictions.
   - Génération de l'archive corrigée.
