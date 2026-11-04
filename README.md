# ⚡ Shunkan Idō & 🔥 Golden Warrior

Deux effets pour webcam 100 % local sur Mac (Apple Silicon).

| Effet                 | Geste                           | Résultat                                           |
| :-------------------- | :------------------------------ | :------------------------------------------------- |
| ⚡ **Shunkan Idō**    | **Index + majeur sur le front** | Tu te téléportes hors de l'image avec le bruitage. |
| 🔥 **Golden Warrior** | **Les deux poings serrés**      | Tu deviens un super guerrier doré.                 |

瞬間移動 (_shunkan idō_) = téléportation instantanée.

---

## ⚡ Installation & Lancement en 3 commandes (macOS)

### 1️⃣ Prérequis (1 seule fois)

- **[OBS Studio](https://obsproject.com/)** :
  Ouvre-le une fois, clique sur **Démarrer la caméra virtuelle**, puis autorise l'extension dans
  **Réglages Système › Général › Ouverture et extensions › Extensions caméra › OBS Virtual Camera**.
- **[uv](https://docs.astral.sh/uv/)** pour gérer Python :

```bash
brew install uv
```

### 2️⃣ Installation

Dans le dossier du projet :

```bash
uv sync
```

_(uv installe Python 3.12 et les dépendances dans `.venv/`. Les modèles MediaPipe, ~25 Mo, sont téléchargés au premier lancement.)_

### 3️⃣ Lancer la caméra

```bash
uv run shunkan-ido
```

Au premier lancement, macOS te demande l'accès à la caméra pour le Terminal.
Un **compte à rebours de 5 s** démarre : **sors du champ**, le script photographie la pièce vide.

> Un seul programme à la fois peut utiliser la caméra virtuelle.

---

## 🎮 Connecter à Zoom, Teams, Meet ou Discord

1. Lance `uv run shunkan-ido`.
2. Dans **Zoom** (ou Teams, Meet, Discord), choisis la caméra **`OBS Virtual Camera`**.
3. C'est tout.

---

## ⌨️ Touches (dans la fenêtre d'aperçu)

|        Touche         | Action                                                                                       |
| :-------------------: | :------------------------------------------------------------------------------------------- |
|     **`espace`**      | `shunkan-ido` : disparaître / réapparaître sans faire le geste                               |
|        **`b`**        | `shunkan-ido` : recalibrer le fond (nouveau compte à rebours, sors du champ)                 |
|        **`g`**        | Se transformer en guerrier doré / revenir à la normale                                       |
|        **`d`**        | Mode debug : zone du front et doigts détectés, ou poings reconnus, avec la barre de maintien |
| **`q`** / **`échap`** | Quitter                                                                                      |

---

## ⚙️ Options

Options communes aux deux programmes :

| Option                       |      Défaut       | Description                                                                         |
| :--------------------------- | :---------------: | :---------------------------------------------------------------------------------- |
| `--camera N`                 |        `0`        | Index de la webcam (voir `--list-cameras`), ou chemin d'une image/vidéo pour tester |
| `--hold S`                   |   `0.3` / `0.5`   | Durée pendant laquelle tenir le geste                                               |
| `--no-sound`                 |                   | Coupe les effets sonores                                                            |
| `--volume V`                 |        `1`        | Volume des effets sonores, de 0 à 1                                                 |
| `--no-virtual`               |                   | Aperçu seul, sans caméra virtuelle (pour tester sans OBS)                           |
| `--width / --height / --fps` | `1280 / 720 / 30` | Format envoyé à la caméra virtuelle                                                 |

Options de `shunkan-ido` :

| Option               | Défaut | Description                                                                     |
| :------------------- | :----: | :------------------------------------------------------------------------------ |
| `--transition S`     | `0.45` | Durée de l'effet de téléportation                                               |
| `--countdown S`      |  `5`   | Compte à rebours avant la photo du fond                                         |
| `--loose`            |        | Geste plus tolérant (ignore annulaire et auriculaire, zone du front plus large) |
| `--static`           |        | Quand caché, envoie le fond figé au lieu de gommer seulement ta silhouette      |
| `--reuse-background` |        | Réutilise le fond de la dernière session (pas de compte à rebours)              |
| `--golden-hold S`    | `0.5`  | Durée pendant laquelle tenir les poings serrés                                  |
| `--no-golden`        |        | Désactive le guerrier doré (téléportation seule)                                |

Options de `golden-warrior` :

| Option           | Défaut | Description           |
| :--------------- | :----: | :-------------------- |
| `--no-lightning` |        | Désactive les éclairs |

`uv run shunkan-ido --help` et `uv run golden-warrior --help` listent tout.

---

## 🧠 Comment ça marche

1. **Fond** : au lancement, 30 images de la pièce vide sont fusionnées (médiane) en une image de référence.
2. **Geste** : [MediaPipe](https://ai.google.dev/edge/mediapipe) détecte les 21 points de la main et le cadre du visage. Règle géométrique : index et majeur tendus et proches, annulaire et auriculaire repliés, les deux bouts de doigts dans la zone du front. Tenu 0,3 s, puis relâché avant de pouvoir redéclencher.
3. **Disparition** : MediaPipe segmente ta silhouette à chaque image, qui est remplacée par le fond. Le reste de l'image reste en direct. Pour qu'on ne devine pas ton contour :
   - le masque est **large et adouci**;
   - le fond est **recoloré localement** d'après la zone visible autour de toi, ce qui suit l'exposition auto, la balance des blancs et les variations de lumière ;
   - un **grain** dosé sur celui de ta webcam est ajouté, sinon la zone gommée serait trop lisse.
4. **Effet** : découpe en bandes horizontales décalées, traînées blanches, flash, fondu vers le décor. 0,45 s dans un sens, idem à l'envers pour revenir.
5. **Guerrier doré** (`golden-warrior`) : le détourage utilise le modèle **multiclasse** de MediaPipe, qui sépare cheveux, peau, vêtements et fond. Seuls tes vrais cheveux passent en or, avec une teinte recentrée pour que même des cheveux noirs deviennent un or vif qui garde le relief des mèches. Le modèle tourne **en parallèle** de la vidéo, et un **filtre guidé** recolle son masque sur les contours de l'image courante, mèches comprises. Un liseré lumineux épouse ton contour, entouré d'un halo doré qui pulse. Des traits d'énergie naissent sur ton contour et montent derrière toi. Des éclairs partent du contour au hasard.
6. **Son** : `teleport.mp3` est joué avec `afplay`, le lecteur intégré à macOS, à chaque téléportation dans les deux sens. `golden.mp3` accompagne la transformation du guerrier doré : 3 s de musique puis un fondu de 2 s. Aucun son à l'arrêt, et la musique est coupée si tu arrêtes avant la fin.
7. **Sortie** : chaque image est poussée dans **OBS Virtual Camera** via [pyvirtualcam](https://github.com/letmaik/pyvirtualcam), à 30 fps en 720p.

Sur un M4 Pro, chaque étape prend quelques millisecondes : le flux reste à 30 fps.

---

## 📁 Architecture du projet

```text
.
├── camkit/              # 🧰 Socle commun aux deux programmes
│   ├── camera.py        # 📷 Capture webcam (AVFoundation) et sortie OBS Virtual Camera
│   ├── gesture.py       # 🖐️ Détection des gestes : doigts sur le front, poings serrés (MediaPipe)
│   ├── segment.py       # ✂️ Segmentation de la silhouette, détourage fin cheveux + personne
│   ├── sound.py         # 🔊 Effets sonores (afplay)
│   └── models.py        # ⬇️ Téléchargement des modèles MediaPipe
├── shunkan_ido/         # ⚡ Téléportation, et programme qui réunit les deux effets
│   ├── main.py          # 🎬 Boucle principale, options, touches, aperçu
│   ├── background.py    # 🏠 Calibration du fond, recoloration, grain, masque
│   ├── effects.py       # 💨 Machine à états et effet de téléportation
│   └── teleport.mp3     # Bruitage de la téléportation
├── golden_warrior/      # 🔥 Effet guerrier doré, utilisable seul
│   ├── main.py          # 🎬 Boucle principale, options, touches, aperçu
│   ├── effect.py        # ✨ Cheveux dorés, aura, traits d'énergie, éclairs
│   └── golden.mp3       # Musique de la transformation (fondu à 3 s)
├── models/              # Modèles MediaPipe (téléchargés au premier lancement, ignorés par git)
├── pyproject.toml       # Dépendances et commandes shunkan-ido / golden-warrior
└── README.md
```

---

## 🛠️ Dépannage

- **« OBS Virtual Camera is not installed »** : l'extension n'est pas activée. Ouvre OBS › Démarrer la caméra virtuelle, puis autorise-la dans Réglages Système › Extensions caméra. Redémarre le Mac si besoin.
- **« not authorized to capture video »** : autorise ton Terminal dans Réglages Système › Confidentialité et sécurité › Caméra.
- **On devine encore ton contour quand tu as disparu** : recalibre le fond (`b`) avec la lumière actuelle. Éloigne-toi du mur d'au moins 1 m : l'ombre que tu projettes derrière toi n'existe pas sur la photo du fond. Coupe si possible l'exposition automatique de la webcam.
- **Le guerrier doré ne se déclenche pas** : les deux mains doivent être entièrement visibles. Active le debug (`d`) : un cercle jaune apparaît sur chaque poing reconnu.
- **Le geste ne déclenche pas** : lance avec `--loose`, active le debug (`d`) pour voir si tes doigts entrent dans le rectangle du front. Place-toi à 50-80 cm de la caméra.
- **Zoom ne voit pas la caméra** : la caméra virtuelle doit être lancée **avant** d'ouvrir le sélecteur de caméra dans Zoom.

---

## 🙏 Inspirations

- [disappear-effect](https://github.com/SaiThurainKhant007/disappear-effect) (Windows) pour l'architecture caméra virtuelle + MediaPipe.
- [vanish_camera](https://github.com/ElFamosoBandito/vanish_camera) pour l'esprit et l'effet DBZ.
- [camera-effects](https://github.com/NeHeGL/camera-effects) pour les effets posés sur la tête et le visage à partir des repères MediaPipe.
