# ⚡ Shunkan Idō — Disparais de Zoom avec le geste de Goku, ou passe Super Saiyan

Pose **index + majeur sur le front** comme Goku, et tu disparais de ta webcam en direct, avec le bruitage. Serre **les deux poings** et tu passes **Super Saiyan** sur **Zoom**, **Teams**, **Meet** ou **Discord**. Le décor reste, toi non. **Sans fond vert**, sans ouvrir OBS, 100 % local sur ton Mac (Apple Silicon).

瞬間移動 (*shunkan idō*) = téléportation instantanée.

---

## ⚡ Installation & Lancement en 3 commandes (macOS)

### 1️⃣ Prérequis (1 seule fois)

- **[OBS Studio](https://obsproject.com/)** : il fournit la caméra virtuelle, tu ne l'ouvriras plus ensuite.
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

*(uv installe Python 3.12 et les dépendances dans `.venv/`. Les modèles MediaPipe, ~8 Mo, sont téléchargés au premier lancement.)*

### 3️⃣ Lancer la caméra

```bash
uv run shunkan-ido
```

Au premier lancement, macOS te demande l'accès à la caméra pour le Terminal : accepte.
Un **compte à rebours de 5 s** démarre : **sors du champ**, le script photographie la pièce vide. Reviens, c'est prêt.

---

## 🖐️ Les gestes

| Geste à faire devant la caméra | Effet | Touche manuelle |
| :--- | :--- | :---: |
| **Index + majeur serrés, posés sur le front**, annulaire et auriculaire repliés, tenu 0,3 s | ⚡ **Téléportation Goku** : bandes qui se déchirent, traînées blanches, flash, bruitage… et tu n'es plus là | **`[espace]`** |
| **Les deux poings serrés face à la caméra**, tenus 0,5 s | 🔥 **Super Saiyan** : cheveux dorés, aura de flammes jaunes, éclairs, flash et tremblement à la transformation | **`[s]`** |

> 💡 **Pour revenir** : refais simplement le même geste (ou la même touche). La téléportation se joue à l'envers, l'aura s'éteint.
>
> Les deux modes se combinent : un Super Saiyan peut se téléporter, l'aura disparaît avec lui.

Quand tu es caché, seule **ta silhouette** est remplacée par le fond : ce qui bouge autour (un collègue, ton chat) reste visible. Avec `--static`, c'est le fond figé qui est envoyé, plus robuste si ton décor change de lumière.

---

## 🎮 Connecter à Zoom, Teams, Meet ou Discord

1. Lance `uv run shunkan-ido`.
2. Dans **Zoom** (ou Teams, Meet, Discord), choisis la caméra **`OBS Virtual Camera`**.
3. C'est tout. Pas besoin d'ouvrir OBS.

---

## ⌨️ Touches (dans la fenêtre d'aperçu)

| Touche | Action |
| :---: | :--- |
| **`espace`** | Disparaître / réapparaître sans faire le geste |
| **`s`** | Passer en Super Saiyan / revenir à la normale |
| **`b`** | Recalibrer le fond (nouveau compte à rebours, sors du champ) |
| **`d`** | Mode debug : zone du front, doigts détectés, poings reconnus, barres de maintien |
| **`q`** / **`échap`** | Quitter |

---

## ⚙️ Options

```bash
uv run shunkan-ido --help
```

| Option | Défaut | Description |
| :--- | :---: | :--- |
| `--camera N` | `0` | Index de la webcam (voir `--list-cameras`), ou chemin d'une image/vidéo pour tester |
| `--hold S` | `0.3` | Durée pendant laquelle tenir le geste |
| `--saiyan-hold S` | `0.5` | Durée pendant laquelle tenir les poings serrés |
| `--transition S` | `0.45` | Durée de l'effet de téléportation |
| `--countdown S` | `5` | Compte à rebours avant la photo du fond |
| `--loose` | | Geste plus tolérant (ignore annulaire et auriculaire, zone du front plus large) |
| `--static` | | Quand caché, envoie le fond figé au lieu de gommer seulement ta silhouette |
| `--reuse-background` | | Réutilise le fond de la dernière session (pas de compte à rebours) |
| `--no-sound` | | Coupe les effets sonores |
| `--volume V` | `1` | Volume des effets sonores, de 0 à 1 |
| `--no-virtual` | | Aperçu seul, sans caméra virtuelle (pour tester sans OBS) |
| `--width / --height / --fps` | `1280 / 720 / 30` | Format envoyé à la caméra virtuelle |

---

## 🧠 Comment ça marche

1. **Fond** : au lancement, 30 images de la pièce vide sont fusionnées (médiane) en une image de référence.
2. **Geste** : [MediaPipe](https://ai.google.dev/edge/mediapipe) détecte les 21 points de la main et le cadre du visage. Règle géométrique : index et majeur tendus et proches, annulaire et auriculaire repliés, les deux bouts de doigts dans la zone du front. Tenu 0,3 s, puis relâché avant de pouvoir redéclencher.
3. **Disparition** : MediaPipe segmente ta silhouette à chaque image, qui est remplacée par le fond. Le reste de l'image reste en direct. Pour qu'on ne devine pas ton contour :
   - le masque est **large et adouci** (cheveux, halo et bord flou compris) ;
   - le fond est **recoloré localement** d'après la zone visible autour de toi, ce qui suit l'exposition auto, la balance des blancs et les variations de lumière ;
   - un **grain** dosé sur celui de ta webcam est ajouté, sinon la zone gommée serait trop lisse.
4. **Effet** : découpe en bandes horizontales décalées, traînées blanches, flash, fondu vers le décor. 0,45 s dans un sens, idem à l'envers pour revenir.
5. **Super Saiyan** : la zone de ta silhouette au-dessus du front est teintée en or en gardant les reflets. Une aura est générée autour de la silhouette puis étirée vers le haut par un bruit qui défile, ce qui donne des flammes. Des éclairs partent du contour au hasard.
6. **Son** : `teleport.mp3` est joué avec `afplay`, le lecteur intégré à macOS, à chaque téléportation dans les deux sens. Dépose un `saiyan.mp3` (et un `saiyan_off.mp3`) dans `shunkan_ido/` pour sonoriser la transformation.
7. **Sortie** : chaque image est poussée dans **OBS Virtual Camera** via [pyvirtualcam](https://github.com/letmaik/pyvirtualcam), à 30 fps en 720p.

Sur un M4 Pro, chaque étape prend quelques millisecondes : le flux reste à 30 fps.

---

## 📁 Architecture du projet

```text
.
├── shunkan_ido/
│   ├── main.py          # 🎬 Boucle principale, options, touches, aperçu
│   ├── camera.py        # 📷 Capture webcam (AVFoundation) et sortie OBS Virtual Camera
│   ├── gesture.py       # 🖐️ Détection des gestes Goku et Super Saiyan (MediaPipe mains + visage)
│   ├── background.py    # 🏠 Calibration du fond, exposition, segmentation de la silhouette
│   ├── effects.py       # ⚡ Machine à états et effet de téléportation
│   ├── saiyan.py        # 🔥 Mode Super Saiyan : cheveux dorés, aura, éclairs
│   ├── sound.py         # 🔊 Effets sonores (afplay)
│   ├── teleport.mp3     # Bruitage de la téléportation
│   └── models.py        # ⬇️ Téléchargement des modèles MediaPipe
├── models/              # Modèles MediaPipe (téléchargés au premier lancement, ignorés par git)
├── pyproject.toml       # Dépendances : MediaPipe, OpenCV, NumPy, pyvirtualcam
└── README.md
```

---

## 🛠️ Dépannage

- **« OBS Virtual Camera is not installed »** : l'extension n'est pas activée. Ouvre OBS › Démarrer la caméra virtuelle, puis autorise-la dans Réglages Système › Extensions caméra. Redémarre le Mac si besoin.
- **« not authorized to capture video »** : autorise ton Terminal dans Réglages Système › Confidentialité et sécurité › Caméra.
- **On devine encore ton contour quand tu as disparu** : recalibre le fond (`b`) avec la lumière actuelle. Éloigne-toi du mur d'au moins 1 m : l'ombre que tu projettes derrière toi n'existe pas sur la photo du fond. Coupe si possible l'exposition automatique de la webcam.
- **Le Super Saiyan ne se déclenche pas** : les deux mains doivent être entièrement visibles. Active le debug (`d`) : un cercle jaune apparaît sur chaque poing reconnu.
- **Le geste ne déclenche pas** : lance avec `--loose`, active le debug (`d`) pour voir si tes doigts entrent dans le rectangle du front. Place-toi à 50-80 cm de la caméra.
- **Zoom ne voit pas la caméra** : la caméra virtuelle doit être lancée **avant** d'ouvrir le sélecteur de caméra dans Zoom.

---

## 🙏 Inspirations

- [disappear-effect](https://github.com/SaiThurainKhant007/disappear-effect) (Windows) pour l'architecture caméra virtuelle + MediaPipe.
- [vanish_camera](https://github.com/ElFamosoBandito/vanish_camera) pour l'esprit et l'effet DBZ.
