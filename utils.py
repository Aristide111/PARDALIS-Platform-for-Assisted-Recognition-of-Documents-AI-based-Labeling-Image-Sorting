import os
import re
import unicodedata
import io
import fitz  # PyMuPDF
from PIL import Image

class FichierConverti:
    def __init__(self, name):
        self.name = name

def preparer_fichiers_entree(fichiers_entree, dossier_originaux):
    fichiers_traites = []
    if not fichiers_entree:
        return fichiers_traites

    for obj in fichiers_entree:
        chemin = obj.name
        ext = os.path.splitext(chemin)[1].lower()
        nom_base_orig = os.path.splitext(os.path.basename(chemin))[0]

        if ext == ".pdf":
            try:
                doc = fitz.open(chemin)
                for page_num in range(len(doc)):
                    page = doc.load_page(page_num)
                    pix = page.get_pixmap(dpi=150)
                    nom_img = f"{nom_base_orig}_p{page_num+1}.jpg"
                    chemin_dest = os.path.join(dossier_originaux, nom_img)
                    pix.save(chemin_dest)
                    fichiers_traites.append(FichierConverti(chemin_dest))
            except Exception as e:
                print(f"Erreur lors de la conversion du PDF {chemin}: {e}")
        elif ext in [".jpg", ".jpeg", ".png"]:
            nom_img = os.path.basename(chemin)
            chemin_dest = os.path.join(dossier_originaux, nom_img)
            if not os.path.exists(chemin_dest):
                import shutil
                shutil.copy(chemin, chemin_dest)
            fichiers_traites.append(FichierConverti(chemin_dest))

    return fichiers_traites

def nettoyer_nom_fichier(nom):
    nom = nom.replace(" ou ", "_")
    nom = re.sub(r'[^\w\-_]', '_', nom)
    return re.sub(r'_+', '_', nom).strip('_') or "inconnu"

def _norm(texte):
    t = unicodedata.normalize("NFKD", texte or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()

def extraire_certitude(texte):
    match = re.search(r'(\d{1,3})\s*%', texte)
    if match:
        return min(int(match.group(1)), 100)

    t = texte.lower()
    if "très élevé" in t or "tres eleve" in t or "certain" in t:
        return 90
    elif "élevé" in t or "eleve" in t or "fort" in t:
        return 75
    elif "moyen" in t or "partiel" in t:
        return 50
    elif "faible" in t or "incertain" in t:
        return 25
    return 30

def extraire_champ_llm(texte, nom_champ):
    pattern = rf"-\s*\*\*{re.escape(nom_champ)}\*\*\s*:?\s*(.*?)(?=\n\s*-\s*\*\*|\Z)"
    match = re.search(pattern, texte, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else ""

def extraire_score_champ(texte):
    champ = extraire_champ_llm(texte, "Score de certitude")
    return extraire_certitude(champ if champ else texte)

def nettoyer_nom_entite(nom):
    n = re.sub(r"\([^)]*\)", " ", nom)
    n = re.sub(r"\b(dans|de|du|selon|en)\s+(la\s+|le\s+|l')?\s*(mythologie|religion|tradition|culture)\b.*$",
               " ", n, flags=re.IGNORECASE)
    n = re.split(r"\s[-–—]\s|[:,;]", n)[0]
    n = re.sub(r"\s+", " ", n).strip(" .,;'\"")
    return n or nom.strip()

def encoder_image_b64(chemin, max_side=1024, qualite=85):
    with Image.open(chemin) as im:
        im = im.convert("RGB")
        im.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=qualite)
    return base64.b64encode(buf.getvalue()).decode("utf-8")