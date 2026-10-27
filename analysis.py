import os
import shutil
import csv
import json
from collections import Counter
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib as mpl
import gradio as gr

from config import client, MODEL_ID, NON_IDENTIFIE, AUCUNE_CORRESPONDANCE, COLONNES_REF
from utils import (
    preparer_fichiers_entree, nettoyer_nom_fichier, _norm,
    extraire_champ_llm, extraire_score_champ, nettoyer_nom_entite, encoder_image_b64
)

def identifier_libre(texte_analyse):
    champ = extraire_champ_llm(texte_analyse, "Entité identifiée")
    champ = re.sub(r"[\*\n]", " ", champ).strip(" .")
    champ = re.sub(r"\s+", " ", champ)
    champ = nettoyer_nom_entite(champ)
    if not champ or _norm(champ) in {"indetermine", "inconnu", "non identifie", "aucune correspondance"}:
        return NON_IDENTIFIE
    return champ[:80]

def regrouper_heuristique(noms):
    comptes = Counter(noms)
    uniques = [n for n in comptes if n != NON_IDENTIFIE and _norm(n)]
    uniques.sort(key=lambda n: (len(_norm(n).split()), -comptes[n]))

    groupes = {}
    for nom in uniques:
        cle = f" {_norm(nom)} "
        cible = next((c for c in groupes if f" {_norm(c)} " in cle), nom)
        groupes.setdefault(cible, []).append(nom)

    mapping = {n: n for n in comptes}
    for canon, membres in groupes.items():
        variantes = [m for m in membres if _norm(m) == _norm(canon)]
        forme = max(variantes, key=lambda m: (comptes[m], sum(not c.isascii() for c in m)))
        for m in membres:
            mapping[m] = forme
    return mapping

def regrouper_par_llm(noms):
    liste = "\n".join(f"- {n}" for n in noms)
    prompt = (
        "Voici une liste de noms d'entités identifiées dans des images.\n"
        "Regroupe UNIQUEMENT les noms qui désignent exactement la même entité "
        "(variantes d'orthographe, précision de contexte ajoutée, forme longue/courte). "
        "Ne fusionne jamais deux entités distinctes. Pour chaque groupe, retiens le nom le plus court "
        "et le plus courant, choisi PARMI ceux de la liste.\n"
        "Réponds UNIQUEMENT par un objet JSON {\"nom_de_la_liste\": \"nom_retenu\", ...} "
        "contenant tous les noms, sans aucun autre texte.\n\n"
        f"Liste :\n{liste}"
    )
    response = client.chat.completions.create(
        model=MODEL_ID,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=800,
        temperature=0,
    )
    texte = response.choices[0].message.content
    match = re.search(r"\{.*\}", texte, re.DOTALL)
    data = json.loads(match.group(0))
    return {k: v for k, v in data.items() if k in noms and v in noms}

def regrouper_entites(noms):
    uniques = list(dict.fromkeys(noms))
    m1 = regrouper_heuristique(noms)
    reps = sorted({v for v in m1.values() if v != NON_IDENTIFIE})
    m2 = {}
    if len(reps) > 1:
        try:
            m2 = regrouper_par_llm(reps)
        except Exception as e:
            print(f"Regroupement LLM ignoré : {e}")
    return {n: m2.get(m1[n], m1[n]) for n in uniques}

def identifier_dans_referentiel(texte_analyse, referentiel):
    champ = extraire_champ_llm(texte_analyse, "Entité identifiée")
    n = _norm(champ)
    if not n:
        return NON_IDENTIFIE

    for e in referentiel:
        if _norm(e["id"]) == n:
            return e["id"]

    candidats = [e["id"] for e in referentiel
                 if _norm(e["id"]) and f" {_norm(e['id'])} " in f" {n} "]
    if candidats:
        return max(candidats, key=lambda i: len(_norm(i)))

    return NON_IDENTIFIE

def _bloc_cadre(consigne_utilisateur):
    if (consigne_utilisateur or "").strip():
        return (
            "Contexte fourni par l'utilisateur (à prendre en compte) :\n"
            f"\"\"\"\n{consigne_utilisateur.strip()}\n\"\"\"\n\n"
        )
    return ""

def construire_prompt_libre(consigne_utilisateur=""):
    format_reponse = (
        "Réponds en français en structurant ta réponse strictement ainsi :\n"
        "   - **Description de l'image** : (résumé des éléments visuels observés : posture, vêtements, attributs, contexte)\n"
        "   - **Entité identifiée** : (NOM SEUL de l'entité, sans précision ni contexte, forme française la plus courante, ex: 'Athéna', ou 'Indéterminé')\n"
        "   - **Score de certitude** : (ex: 30% ou 85%)\n"
        "   - **Hypothèses secondaires** : (ex: AutreEntité (40%), ... ou 'Aucune')\n"
        "   - **Justification** : (éléments précis qui ont motivé ce choix)"
    )
    return (
        "Tu es un expert en analyse visuelle (iconographie, histoire de l'art, objets).\n"
        "Aucune liste de référence n'est fournie : tu dois identifier l'entité "
        "(personnage, divinité, objet, figure...) uniquement à partir de ce que tu vois dans l'image.\n\n"
        + _bloc_cadre(consigne_utilisateur) +
        "Consignes OBLIGATOIRES :\n"
        "1. Décris précisément l'image (posture, vêtements, attributs visibles).\n"
        "2. Déduis de cette description l'entité la plus probable et propose-la, même si la certitude est faible.\n"
        "3. Fournis également des hypothèses secondaires éventuelles avec leurs pourcentages.\n"
        "4. Dans « Entité identifiée », donne uniquement le nom (ex : « Artémis », jamais « Artémis dans la mythologie grecque »).\n"
        + format_reponse
    )

def construire_prompt_referentiel(referentiel, consigne_utilisateur=""):
    liste = "\n".join(f"- {e['id']} : {e['caracteristiques']}" for e in referentiel)
    format_reponse = (
        "Réponds en français en structurant ta réponse strictement ainsi :\n"
        "   - **Description de l'image** : (résumé des éléments visuels observés)\n"
        f"   - **Entité identifiée** : (UN identifiant de la liste, recopié à l'identique, ou '{AUCUNE_CORRESPONDANCE}')\n"
        "   - **Score de certitude** : (ex: 30% ou 85%)\n"
        f"   - **Hypothèses secondaires** : (autres identifiants de la liste avec pourcentage, ex: ID2 (40%), ou 'Aucune')\n"
        "   - **Justification** : (liens précis entre ce qui est visible et les caractéristiques du référentiel)"
    )
    return (
        "Tu es un expert en analyse visuelle.\n"
        "Tu dois identifier ce que montre l'image UNIQUEMENT parmi les entités du référentiel ci-dessous "
        "(liste fermée). Chaque entrée est de la forme « identifiant : caractéristiques ».\n\n"
        f"RÉFÉRENTIEL :\n{liste}\n\n"
        + _bloc_cadre(consigne_utilisateur) +
        "Consignes OBLIGATOIRES :\n"
        "1. Décris d'abord précisément l'image.\n"
        "2. Compare cette description aux caractéristiques de chaque entrée du référentiel. Rapproche l'objet de l'entité avec le plus de caractéristiques communes.\n"
        "3. Le champ « Entité identifiée » doit contenir EXACTEMENT un identifiant du référentiel, sans rien y ajouter. "
        f"N'invente jamais d'autre nom.\n"
        "4. Les hypothèses secondaires ne peuvent contenir que des identifiants du référentiel.\n"
        + format_reponse
    )

def interroger_modele(chemin_img, prompt):
    tentatives = [(1024, False), (640, False), (640, True)]
    derniere_erreur = None
    for max_side, image_d_abord in tentatives:
        try:
            img_b64 = encoder_image_b64(chemin_img, max_side)
            bloc_texte = {"type": "text", "text": prompt}
            bloc_image = {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
            contenu = [bloc_image, bloc_texte] if image_d_abord else [bloc_texte, bloc_image]
            response = client.chat.completions.create(
                model=MODEL_ID,
                messages=[{"role": "user", "content": contenu}],
                max_tokens=800,
            )
            return response.choices[0].message.content
        except Exception as e:
            derniere_erreur = e
            print(f"Échec (côté max={max_side}, image d'abord={image_d_abord}) : {e}")
    raise derniere_erreur

def referentiel_vers_lignes(referentiel):
    return [[e["id"], e["caracteristiques"]] for e in (referentiel or [])]

def ids_referentiel(referentiel):
    return [e["id"] for e in (referentiel or [])]

def _retour_referentiel(referentiel, message):
    ids = ids_referentiel(referentiel)
    return (referentiel, referentiel_vers_lignes(referentiel),
            gr.update(choices=ids, value=None), "", "", message)

def ajouter_entree(ident, carac, referentiel):
    referentiel = list(referentiel or [])
    ident = (ident or "").strip()
    carac = (carac or "").strip()
    if not ident or not carac:
        ids = ids_referentiel(referentiel)
        return (referentiel, referentiel_vers_lignes(referentiel),
                gr.update(choices=ids), ident, carac,
                "⚠️ Renseignez l'identifiant ET les caractéristiques.")

    for e in referentiel:
        if _norm(e["id"]) == _norm(ident):
            e["id"], e["caracteristiques"] = ident, carac
            return _retour_referentiel(referentiel, f"✏️ Entrée « {ident} » mise à jour.")

    referentiel.append({"id": ident, "caracteristiques": carac})
    return _retour_referentiel(referentiel, f"✅ Entrée « {ident} » ajoutée ({len(referentiel)} au total).")

def supprimer_entree(ident, referentiel):
    referentiel = [e for e in (referentiel or []) if e["id"] != ident]
    return _retour_referentiel(referentiel, f"🗑️ Entrée « {ident} » supprimée." if ident else "Aucune entrée sélectionnée.")

def vider_referentiel(referentiel):
    return _retour_referentiel([], "Référentiel vidé.")

def importer_referentiel_csv(fichier, referentiel):
    referentiel = list(referentiel or [])
    if fichier is None:
        return _retour_referentiel(referentiel, "Aucun fichier CSV fourni.")
    try:
        df = pd.read_csv(fichier.name, sep=None, engine="python", encoding="utf-8-sig")
        if df.shape[1] < 2:
            raise ValueError("Le CSV doit contenir au moins deux colonnes (identifiant, caractéristiques).")
        existants = {_norm(e["id"]): e for e in referentiel}
        nb = 0
        for _, row in df.iterrows():
            ident, carac = str(row.iloc[0]).strip(), str(row.iloc[1]).strip()
            if not ident or ident.lower() == "nan" or carac.lower() == "nan":
                continue
            if _norm(ident) in existants:
                existants[_norm(ident)]["caracteristiques"] = carac
            else:
                nouveau = {"id": ident, "caracteristiques": carac}
                referentiel.append(nouveau)
                existants[_norm(ident)] = nouveau
            nb += 1
        return _retour_referentiel(referentiel, f"📥 {nb} entrée(s) importée(s).")
    except Exception as e:
        return _retour_referentiel(referentiel, f"❌ Erreur d'import : {e}")

def analyser_et_identifier(images_files_bruts, mode, referentiel, consigne_libre="", regrouper=True):
    from config import MODE_REF
    mode_ref = (mode == MODE_REF)
    referentiel = referentiel or []

    if mode_ref and not referentiel:
        return ("Erreur : l'approche 1 nécessite au moins une entrée dans le référentiel.",
                None, [], gr.update(visible=False))

    dossier_principal = "export_resultats_brut"
    if os.path.exists(dossier_principal):
        shutil.rmtree(dossier_principal)

    dossier_originaux = os.path.join(dossier_principal, "images_originales")
    dossier_renommes = os.path.join(dossier_principal, "images_renommees")
    dossier_dataviz = os.path.join(dossier_principal, "dataviz")
    os.makedirs(dossier_originaux, exist_ok=True)
    os.makedirs(dossier_renommes, exist_ok=True)
    os.makedirs(dossier_dataviz, exist_ok=True)

    images_files = preparer_fichiers_entree(images_files_bruts, dossier_originaux)

    if not images_files:
        return "Erreur : Veuillez déposer au moins une image valide ou un fichier PDF.", None, [], gr.update(visible=False)

    rapport_texte = f"### Résultats de l'analyse — {mode}\n\n"
    if mode_ref:
        rapport_texte += f"**Référentiel utilisé ({len(referentiel)} entrées) :** {', '.join(ids_referentiel(referentiel))}\n\n"
        prompt = construire_prompt_referentiel(referentiel, consigne_libre)
        pd.DataFrame(referentiel_vers_lignes(referentiel), columns=COLONNES_REF).to_csv(
            os.path.join(dossier_principal, "referentiel.csv"), index=False, encoding="utf-8")
    else:
        prompt = construire_prompt_libre(consigne_libre)

    if (consigne_libre or "").strip():
        rapport_texte += f"**Contexte fourni :** {consigne_libre.strip()}\n\n"

    resultats_dataviz = []
    donnees_csv = []
    compteurs = {}
    analyses = []

    for img_obj in images_files:
        chemin_img = img_obj.name
        nom_original = os.path.basename(chemin_img)

        try:
            resultat_analyse = interroger_modele(chemin_img, prompt)
            rapport_texte += f"#### Fichier / Page : `{nom_original}`\n{resultat_analyse}\n\n---\n\n"

            if mode_ref:
                entite = identifier_dans_referentiel(resultat_analyse, referentiel)
            else:
                entite = identifier_libre(resultat_analyse)

            analyses.append({
                "chemin_img": chemin_img,
                "nom_original": nom_original,
                "entite": entite,
                "score": extraire_score_champ(resultat_analyse),
                "description": extraire_champ_llm(resultat_analyse, "Description de l'image"),
                "justification": extraire_champ_llm(resultat_analyse, "Justification"),
                "hypotheses": extraire_champ_llm(resultat_analyse, "Hypothèses secondaires"),
            })
        except Exception as e:
            rapport_texte += f"#### Fichier : `{nom_original}`\nErreur lors du traitement : {str(e)}\n\n---\n\n"

    correspondances = {}
    if not mode_ref and regrouper and analyses:
        correspondances = regrouper_entites([a["entite"] for a in analyses])
        changements = sorted({f"{k} → {v}" for k, v in correspondances.items() if k != v})
        if changements:
            rapport_texte += "**Regroupements appliqués :** " + " ; ".join(changements) + "\n\n"

    for a in analyses:
        entite = correspondances.get(a["entite"], a["entite"])
        extension = os.path.splitext(a["nom_original"])[1] or ".jpg"

        compteurs[entite] = compteurs.get(entite, 0) + 1
        nouveau_nom = f"{nettoyer_nom_fichier(entite)}_{compteurs[entite]}{extension}"
        chemin_nouveau = os.path.join(dossier_renommes, nouveau_nom)
        shutil.copy(a["chemin_img"], chemin_nouveau)

        donnees_csv.append({
            "Ancien Nom / Fichier Source": a["nom_original"],
            "Nouveau Nom": nouveau_nom,
            "Personnage Attribué": entite,
            "Certitude (%)": a["score"],
            "Description": a["description"],
            "Justification": a["justification"],
            "Hypothèses Secondaires": a["hypotheses"],
            "Chemin Fichier Renommé": chemin_nouveau,
            "Chemin Image Originale": a["chemin_img"],
            "valide_correct": "Oui",
            "personnage_reel": entite,
        })
        resultats_dataviz.append({"entite": entite, "label_img": nouveau_nom, "score": a["score"]})

    chemin_csv = os.path.join(dossier_principal, "rapport_modele.csv")
    champs = ["Ancien Nom / Fichier Source", "Nouveau Nom", "Personnage Attribué",
              "Certitude (%)", "Description", "Justification", "Hypothèses Secondaires"]
    with open(chemin_csv, mode="w", newline="", encoding="utf-8") as fichier_csv:
        writer = csv.DictWriter(fichier_csv, fieldnames=champs)
        writer.writeheader()
        for ligne in donnees_csv:
            writer.writerow({k: v for k, v in ligne.items() if k in champs})

    if resultats_dataviz:
        df_res = pd.DataFrame(resultats_dataviz)
        for personnage, groupe in df_res.groupby("entite"):
            fig, ax = plt.subplots(figsize=(7, 4))
            labels = groupe["label_img"].tolist()
            scores = groupe["score"].tolist()
            norm = plt.Normalize(0, 100)
            cmap = mpl.colormaps['RdYlGn']
            couleurs = [cmap(norm(s)) for s in scores]

            bars = ax.bar(labels, scores, color=couleurs, edgecolor='black', width=0.4)
            ax.set_title(f"Certitude - {personnage}", fontsize=11, fontweight='bold')
            ax.set_xlabel("Fichiers", fontsize=9)
            ax.set_ylabel("Certitude (%)", fontsize=9)
            ax.set_ylim(0, 115)

            for bar, sc in zip(bars, scores):
                ax.annotate(f'{sc}%',
                            xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                            xytext=(0, 5), textcoords="offset points",
                            ha='center', va='bottom', fontweight='bold')

            plt.xticks(rotation=20, ha='right')
            plt.tight_layout()
            fig.savefig(os.path.join(dossier_dataviz, f"dataviz_{nettoyer_nom_fichier(personnage)}.png"), dpi=150)
            plt.close(fig)

        fig_pie, ax_pie = plt.subplots(figsize=(7, 5))
        comptes = df_res["entite"].value_counts()
        ax_pie.pie(comptes, labels=comptes.index, autopct='%1.1f%%', startangle=140,
                   colors=plt.cm.Paired.colors, wedgeprops={"edgecolor": "black", "linewidth": 1})
        ax_pie.set_title("Répartition globale des entités identifiées", fontsize=11, fontweight='bold')
        plt.tight_layout()
        fig_pie.savefig(os.path.join(dossier_dataviz, "dataviz_repartition_globale.png"), dpi=150)
        plt.close(fig_pie)

    chemin_zip_modele = shutil.make_archive("export_resultats_modele", 'zip', dossier_principal)
    vis_visible = gr.update(visible=True) if donnees_csv else gr.update(visible=False)
    return rapport_texte, chemin_zip_modele, donnees_csv, vis_visible