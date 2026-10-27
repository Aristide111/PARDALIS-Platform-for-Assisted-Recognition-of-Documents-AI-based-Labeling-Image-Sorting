import socket
import os
import shutil
import gradio as gr

from config import MODEL_ID, MODE_REF, MODE_LIBRE, COLONNES_REF
from analysis import (
    ajouter_entree, supprimer_entree, vider_referentiel,
    importer_referentiel_csv, analyser_et_identifier
)
from viewer import (
    action_ouvrir_visionneuse, enregistrer_et_suivant,
    precedent_element, generer_fichiers_corriges_et_dataviz,
    generer_archive_globale
)

def basculer_mode(mode):
    return gr.update(visible=(mode == MODE_REF))

def reinitialiser_application():
    for d in ["export_resultats_brut", "export_resultats_corriges_dir", "export_global_projet"]:
        if os.path.exists(d):
            shutil.rmtree(d, ignore_errors=True)
            
    return (
        None, [], 0, [], [], gr.update(choices=[], value=None),
        "", "", "", None, "", gr.update(visible=False), gr.update(visible=False),
        None, None, "", None
    )

css_content = ""
if os.path.exists("style.css"):
    with open("style.css", "r", encoding="utf-8") as f:
        css_content = f.read()

with gr.Blocks(theme=gr.themes.Base(), css=css_content) as demo:
    
    # --- MISE EN PAGE EN 3 COLONNES : Banderole gauche | Corps | Banderole droite ---
    with gr.Row(elem_id="main-layout"):
        
        # Banderole Latérale Gauche (Image portrait en fond)
        with gr.Column(scale=2, min_width=200, visible=os.path.exists("logo.jpeg")):
            gr.Image("logo.jpeg", show_label=False, interactive=False, container=False, height=800)

        # Corps Central de l'Application
        with gr.Column(scale=10):
            
            # En-tête : Fond rouge, texte or
            with gr.Column(elem_id="header-container"):
                gr.Markdown("# PARDALIS")
                gr.Markdown(f"Platform for Assisted Recognition of Documents, AI-based Labeling, Image Sorting : **`{MODEL_ID}`**")

            stock_donnees = gr.State([])
            index_visionneuse = gr.State(0)
            stock_referentiel = gr.State([])

            with gr.Row():
                btn_reset = gr.Button("🔄 Réinitialiser / Nettoyer l'application", variant="stop")

            with gr.Tabs():
                # --- Onglet 1 ---
                with gr.TabItem("1. Analyse & Export Modèle Brut"):
                    mode_choix = gr.Radio(
                        [MODE_REF, MODE_LIBRE],
                        value=MODE_LIBRE,
                        label="Approche d'identification",
                        info="Approche 1 : le modèle choisit uniquement parmi vos entrées. "
                             "Approche 2 : le modèle propose librement un nom.",
                    )

                    with gr.Group(visible=False) as bloc_referentiel:
                        gr.Markdown("#### Référentiel : ajoutez les entités à reconnaître")
                        with gr.Row():
                            champ_id = gr.Textbox(label="Identifiant", placeholder="ex : Athéna", scale=1)
                            champ_carac = gr.Textbox(
                                label="Caractéristiques",
                                placeholder="ex : casque, égide, lance, chouette...",
                                lines=2, scale=3)
                        with gr.Row():
                            btn_ajouter = gr.Button("➕ Ajouter / mettre à jour", variant="primary")
                            btn_vider = gr.Button("Vider le référentiel")
                        tableau_ref = gr.Dataframe(
                            headers=COLONNES_REF, value=[], interactive=False, wrap=True,
                            label="Entrées du référentiel",
                        )
                        with gr.Row():
                            liste_suppr = gr.Dropdown(choices=[], label="Entrée à supprimer", scale=3)
                            btn_suppr = gr.Button("🗑️ Supprimer", scale=1)
                        with gr.Accordion("Importer depuis un CSV (optionnel)", open=False):
                            csv_ref = gr.File(label="CSV à deux colonnes : identifiant ; caractéristiques", file_types=[".csv"])
                            btn_import = gr.Button("Importer")
                        statut_ref = gr.Markdown("")

                    regrouper_noms = gr.Checkbox(
                        value=True,
                        label="Regrouper automatiquement les variantes d'un même nom (approche 2)",
                    )
                    prompt_libre = gr.Textbox(
                        label="Contexte / cadre de l'identification (optionnel)",
                        placeholder="ex : Statues antiques de musée.",
                        lines=3,
                    )
                    gr.Markdown("Glissez-déposez vos photos (`.jpg`, `.jpeg`, `.png`) ou documents PDF.")
                    with gr.Row():
                        images_input = gr.File(
                            label="Glissez-déposez vos fichiers ici",
                            file_count="multiple",
                            file_types=[".jpg", ".jpeg", ".png", ".pdf"],
                        )
                    with gr.Row():
                        btn_analyser = gr.Button("Lancer l'analyse et générer le dossier Modèle", variant="primary")
                    with gr.Row():
                        output_zip_modele = gr.File(label="📥 Télécharger l'archive ZIP Brute")
                    output_texte = gr.Markdown(label="Rapport détaillé")
                    btn_ouvrir_visionneuse = gr.Button("🔍 Ouvrir la visionneuse de validation & correction", visible=False, variant="secondary")

                # --- Onglet 2 ---
                with gr.TabItem("2. Visionneuse & Export Corrigé"):
                    gr.Markdown("Vérifiez chaque prédiction du modèle, validez-la ou corrigez-la.")

                    with gr.Row(visible=False) as bloc_visionneuse:
                        with gr.Column(scale=1):
                            img_apercu = gr.Image(label="Image analysée", type="filepath", height=350)
                        with gr.Column(scale=1):
                            info_apercu = gr.Markdown("Informations de l'image")
                            choix_valide = gr.Radio(["Oui", "Non"], label="La prédiction est-elle correcte ?", value="Oui")
                            choix_personnage_reel = gr.Dropdown(
                                choices=[], label="Bonne entité (si 'Non')", value=None, allow_custom_value=True,
                            )
                            with gr.Row():
                                btn_precedent = gr.Button("⬅️ Précédent")
                                btn_suivant = gr.Button("Enregistrer & Suivant ➡️", variant="primary")

                    with gr.Row():
                        btn_generer_corriges = gr.Button("📊 Générer l'archive ZIP Corrigée & la Dataviz", variant="primary")
                    with gr.Row():
                        output_zip_corrige = gr.File(label="📥 Télécharger l'archive ZIP Corrigée")
                        plot_precision = gr.Image(label="Graphique de Précision")
                    texte_precision = gr.Markdown(label="Statistiques de précision")

                # --- Onglet 3 ---
                with gr.TabItem("3. Téléchargement Global"):
                    gr.Markdown("Téléchargez l'intégralité du projet (dossiers brut et corrigé).")
                    btn_zip_global = gr.Button("📦 Générer l'archive complète du projet", variant="primary")
                    output_zip_global = gr.File(label="📥 Télécharger le dossier complet (ZIP)")

        # Banderole Latérale Droite (Image portrait en fond)
        with gr.Column(scale=2, min_width=200, visible=os.path.exists("logo.jpeg")):
            gr.Image("logo.jpeg", show_label=False, interactive=False, container=False, height=800)

    # --- Événements ---
    mode_choix.change(fn=basculer_mode, inputs=[mode_choix], outputs=[bloc_referentiel])
    sorties_ref = [stock_referentiel, tableau_ref, liste_suppr, champ_id, champ_carac, statut_ref]

    btn_ajouter.click(fn=ajouter_entree, inputs=[champ_id, champ_carac, stock_referentiel], outputs=sorties_ref)
    btn_suppr.click(fn=supprimer_entree, inputs=[liste_suppr, stock_referentiel], outputs=sorties_ref)
    btn_vider.click(fn=vider_referentiel, inputs=[stock_referentiel], outputs=sorties_ref)
    btn_import.click(fn=importer_referentiel_csv, inputs=[csv_ref, stock_referentiel], outputs=sorties_ref)

    btn_analyser.click(
        fn=analyser_et_identifier,
        inputs=[images_input, mode_choix, stock_referentiel, prompt_libre, regrouper_noms],
        outputs=[output_texte, output_zip_modele, stock_donnees, btn_ouvrir_visionneuse],
    )

    btn_ouvrir_visionneuse.click(
        fn=action_ouvrir_visionneuse,
        inputs=[stock_donnees, mode_choix, stock_referentiel],
        outputs=[index_visionneuse, img_apercu, info_apercu, choix_valide, choix_personnage_reel, bloc_visionneuse],
    )

    btn_suivant.click(
        fn=enregistrer_et_suivant,
        inputs=[index_visionneuse, stock_donnees, choix_valide, choix_personnage_reel],
        outputs=[index_visionneuse, stock_donnees, img_apercu, info_apercu, index_visionneuse, choix_valide, choix_personnage_reel, bloc_visionneuse],
    )

    btn_precedent.click(
        fn=precedent_element,
        inputs=[index_visionneuse, stock_donnees],
        outputs=[index_visionneuse, stock_donnees, img_apercu, info_apercu, index_visionneuse, choix_valide, choix_personnage_reel, bloc_visionneuse],
    )

    btn_generer_corriges.click(
        fn=generer_fichiers_corriges_et_dataviz,
        inputs=[stock_donnees],
        outputs=[output_zip_corrige, plot_precision, texte_precision],
    )

    btn_zip_global.click(fn=generer_archive_globale, inputs=[], outputs=[output_zip_global])

    btn_reset.click(
        fn=reinitialiser_application,
        inputs=[],
        outputs=[
            images_input, stock_donnees, index_visionneuse, stock_referentiel,
            tableau_ref, liste_suppr, champ_id, champ_carac, statut_ref,
            output_zip_modele, output_texte, btn_ouvrir_visionneuse, bloc_visionneuse,
            output_zip_corrige, plot_precision, texte_precision, output_zip_global
        ]
    )

def trouver_port_libre(port_depart=7860):
    port = port_depart
    while port < 65535:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                port += 1
    return port_depart

if __name__ == "__main__":
    port_dispo = trouver_port_libre(7860)
    print(f"Lancement de l'application sur le port : {port_dispo}")
    demo.launch(server_name="127.0.0.1", server_port=port_dispo, share=False)