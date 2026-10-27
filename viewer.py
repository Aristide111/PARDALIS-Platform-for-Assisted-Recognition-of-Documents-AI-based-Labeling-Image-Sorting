import os
import shutil
import csv
import pandas as pd
import matplotlib.pyplot as plt
import gradio as gr
from config import MODE_REF, NON_IDENTIFIE
from analysis import ids_referentiel
from utils import nettoyer_nom_fichier

def choix_entites(liste_donnees, mode, referentiel):
    choix = []
    if mode == MODE_REF:
        choix.extend(ids_referentiel(referentiel))
        choix.append(NON_IDENTIFIE)
    for item in (liste_donnees or []):
        for e in (item.get("Personnage Attribué"), item.get("personnage_reel")):
            if e and e not in choix:
                choix.append(e)
    return choix

def charger_element_visionneuse(index, liste_donnees):
    if not liste_donnees or index >= len(liste_donnees):
        return None, "Fin de la liste", "", "Oui", None, gr.update(visible=False)

    item = liste_donnees[index]
    info_texte = (f"**Image {index + 1} / {len(liste_donnees)}**\n\n"
                  f"- **Fichier :** `{item['Ancien Nom / Fichier Source']}`\n"
                  f"- **Modèle prédit :** **{item['Personnage Attribué']}**\n"
                  f"- **Certitude :** {item['Certitude (%)']}%\n"
                  f"- **Justification :** {item['Justification']}")

    val_correct = item.get("valide_correct", "Oui")
    val_reel = item.get("personnage_reel", item['Personnage Attribué'])
    return item["Chemin Image Originale"], info_texte, index, val_correct, val_reel, gr.update(visible=True)

def enregistrer_et_suivant(index, liste_donnees, valide_correct, personnage_reel):
    if not liste_donnees or index >= len(liste_donnees):
        return index, liste_donnees, None, "", index, "Oui", None, gr.update(visible=False)

    liste_donnees[index]["valide_correct"] = valide_correct
    liste_donnees[index]["personnage_reel"] = (
        (personnage_reel or liste_donnees[index]["Personnage Attribué"])
        if valide_correct == "Non" else liste_donnees[index]["Personnage Attribué"]
    )

    prochain_index = index + 1
    if prochain_index < len(liste_donnees):
        img_path, info, idx, v_cor, v_rel, vis = charger_element_visionneuse(prochain_index, liste_donnees)
        return prochain_index, liste_donnees, img_path, info, idx, v_cor, v_rel, vis
    return index, liste_donnees, None, "### Validation terminée pour toutes les images !", index, "Oui", None, gr.update(visible=False)

def precedent_element(index, liste_donnees):
    if not liste_donnees or index <= 0:
        return index, liste_donnees, None, "Début de la liste", 0, "Oui", None, gr.update(visible=True)

    prochain_index = index - 1
    img_path, info, idx, v_cor, v_rel, vis = charger_element_visionneuse(prochain_index, liste_donnees)
    return prochain_index, liste_donnees, img_path, info, idx, v_cor, v_rel, vis

def action_ouvrir_visionneuse(liste_donnees, mode, referentiel):
    if not liste_donnees:
        return 0, None, "Aucune donnée.", "Oui", None, gr.update(visible=False)
    img_path, info, idx, v_cor, v_rel, vis = charger_element_visionneuse(0, liste_donnees)
    return (0, img_path, info, v_cor,
            gr.update(choices=choix_entites(liste_donnees, mode, referentiel), value=v_rel), vis)

def generer_fichiers_corriges_et_dataviz(liste_donnees):
    if not liste_donnees:
        return None, None, "Aucune donnée à analyser."

    df = pd.DataFrame(liste_donnees)
    if "valide_correct" not in df.columns:
        df["valide_correct"] = "Oui"
    if "personnage_reel" not in df.columns:
        df["personnage_reel"] = df["Personnage Attribué"]

    df["est_correct"] = df.apply(
        lambda row: 1 if (row["valide_correct"] == "Oui" or row["Personnage Attribué"] == row["personnage_reel"]) else 0,
        axis=1)
    accuracy_globale = df["est_correct"].mean() * 100

    dossier_corrige = "export_resultats_corriges_dir"
    if os.path.exists(dossier_corrige):
        shutil.rmtree(dossier_corrige)
    dossier_renommes_corriges = os.path.join(dossier_corrige, "images_corrigees")
    dossier_dataviz_corriges = os.path.join(dossier_corrige, "dataviz")
    os.makedirs(dossier_renommes_corriges, exist_ok=True)
    os.makedirs(dossier_dataviz_corriges, exist_ok=True)

    compteurs_corriges = {}
    donnees_csv_corrige = []

    for _, row in df.iterrows():
        pers_reel = row["personnage_reel"]
        chemin_orig = row["Chemin Image Originale"]
        extension = os.path.splitext(row["Nouveau Nom"])[1]

        compteurs_corriges[pers_reel] = compteurs_corriges.get(pers_reel, 0) + 1
        nom_corrige = f"{nettoyer_nom_fichier(pers_reel)}_{compteurs_corriges[pers_reel]}{extension}"
        shutil.copy(chemin_orig, os.path.join(dossier_renommes_corriges, nom_corrige))

        donnees_csv_corrige.append({
            "Ancien Nom / Fichier Source": row["Ancien Nom / Fichier Source"],
            "Nouveau Nom Corrigé": nom_corrige,
            "Personnage Attribué (Modèle)": row["Personnage Attribué"],
            "Validé Correct ?": row["valide_correct"],
            "Personnage Réel (Corrigé)": pers_reel,
            "Certitude (%)": row["Certitude (%)"],
            "Description": row["Description"],
            "Justification": row["Justification"],
            "Hypothèses Secondaires": row["Hypothèses Secondaires"],
        })

    chemin_csv_corrige = os.path.join(dossier_corrige, "rapport_corrigé.csv")
    with open(chemin_csv_corrige, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(donnees_csv_corrige[0].keys()))
        writer.writeheader()
        writer.writerows(donnees_csv_corrige)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    comptes_globaux = df["est_correct"].value_counts().rename({1: "Correct", 0: "Incorrect"})
    couleurs_pie = ["#4CAF50" if i == "Correct" else "#F44336" for i in comptes_globaux.index]
    ax1.pie(comptes_globaux, labels=comptes_globaux.index, autopct='%1.1f%%', startangle=90,
            colors=couleurs_pie, wedgeprops={"edgecolor": "black"})
    ax1.set_title(f"Précision Globale du Modèle\n(Exactitude : {accuracy_globale:.1f}%)", fontsize=11, fontweight='bold')

    precision_par_pers = df.groupby("personnage_reel")["est_correct"].mean() * 100
    bars = ax2.bar(precision_par_pers.index, precision_par_pers.values, color="#3F51B5", edgecolor="black", width=0.4)
    ax2.set_title("Précision par Entité Réelle (%)", fontsize=11, fontweight='bold')
    ax2.set_ylabel("Précision (%)", fontsize=9)
    ax2.set_ylim(0, 110)
    plt.sca(ax2)
    plt.xticks(rotation=20, ha='right')

    for bar, val in zip(bars, precision_par_pers.values):
        ax2.annotate(f'{val:.1f}%', xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                     xytext=(0, 3), textcoords="offset points", ha='center', va='bottom', fontweight='bold')

    plt.tight_layout()
    chemin_plot_precision = os.path.join(dossier_dataviz_corriges, "dataviz_evaluation_precision.png")
    fig.savefig(chemin_plot_precision, dpi=150)
    plt.close(fig)

    chemin_zip_corrige = shutil.make_archive("export_resultats_corriges", 'zip', dossier_corrige)

    texte_rapport = (f"### Rapport d'évaluation et de correction\n\n"
                     f"- **Exactitude globale (Accuracy) :** {accuracy_globale:.1f}%\n"
                     f"- **Total images validées :** {len(df)}\n"
                     f"- **Corrections apportées :** {len(df) - df['est_correct'].sum()}")
    return chemin_zip_corrige, chemin_plot_precision, texte_rapport

def generer_archive_globale():
    dossier_global = "export_global_projet"
    if os.path.exists(dossier_global):
        shutil.rmtree(dossier_global)
    os.makedirs(dossier_global, exist_ok=True)

    for dossier in ["export_resultats_brut", "export_resultats_corriges_dir"]:
        if os.path.exists(dossier):
            shutil.copytree(dossier, os.path.join(dossier_global, os.path.basename(dossier)), dirs_exist_ok=True)

    return shutil.make_archive("export_complet_projet", 'zip', dossier_global)