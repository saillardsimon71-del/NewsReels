# NewsReel V1 — générateur de JT local → MP4

NewsReel assemble un journal vertical prêt à publier dans `output/<run_id>/newsreel_final.mp4`.
Le run par défaut contient trois sujets et utilise une seule requête batch FastH3 pour tous les reporters. Le plateau du présentateur est une image Agnes animée localement (Ken Burns), sa voix est générée par Edge TTS, puis FFmpeg fait le montage **sur le PC**.

## État des références source

Dans le checkout fourni pour cette mission, `git ls-files` ne contient que le README initial : aucun dossier `reference/`, `videomaker/`, `fasth3_push_test.py` ou ancien bridge n'est présent. Le worker ci-dessous ne choisit donc pas à leur place un autre modèle, checkpoint ou workflow VSA. Il consomme un export **ComfyUI API JSON du workflow FastH3 validé** et conserve ses nœuds/modèles/réglages, en ne changeant que l'image, le dialogue, la résolution/cadence/durée demandées et le nom de sortie. Si cet export n'est pas configuré, le bridge bloque le run avant les appels Agnes (pour éviter des coûts inutiles) au lieu de lancer un workflow supposé.

Cette absence est la limitation d'intégration à lever avant le premier vrai rendu H3; tout le chemin de montage est autonome et démontrable sans Agnes ni Modal.

## Architecture

```text
bridge.py                     API FastAPI locale + progression/polling + livraison MP4
modal_h3.py                   worker Modal: 1 conteneur L40S, 1 ComfyUI, batch séquentiel
newsreel/config.py            configuration Windows / chemins FFmpeg / Agnes
newsreel/models.py            scénario, scène et timeline sérialisables
newsreel/timeline.py          timeline source de vérité (host → reporter → ...)
newsreel/agnes.py             client texte + image Agnes OpenAI-compatible
newsreel/news.py              Google News RSS français
newsreel/tts.py               abstraction TTS et adaptateur Edge TTS
newsreel/h3_worker_contract.py contrat fixe FastH3 et appel Modal batch unique
newsreel/assembler.py         montage local H.264/AAC, titres, audio et validation ffprobe
newsreel/run_store.py         isolation `output/<run_id>` et run_manifest.json
web/index.html                interface sans framework
newsreel/demo.py              fixtures synthétiques, entièrement hors-ligne
```

Réglages FastH3 du contrat : **FastH3 8-Step V2 / MiniMax H3, 768×1344, 24 fps, 243 frames / 10,125 s, 8 étapes, audio natif, VSA, L40S**, volume Modal `fasth3-models`. Les générations H3 partent en un seul appel Modal par run; la boucle des jobs conserve le même processus ComfyUI.

## Installation Windows (PowerShell)

Exemple avec le chemin de projet de la machine cible :

```powershell
cd C:\Users\saill\Downloads\videomaker
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Installer FFmpeg (ffmpeg **et** ffprobe) et rouvrir le terminal pour actualiser le PATH :

```powershell
winget install --id Gyan.FFmpeg.Shared -e
ffmpeg -version
ffprobe -version
```

Si les exécutables ne sont pas dans le PATH :

```powershell
$env:NEWSREEL_FFMPEG = "C:\tools\ffmpeg\bin\ffmpeg.exe"
$env:NEWSREEL_FFPROBE = "C:\tools\ffmpeg\bin\ffprobe.exe"
```

Configurer Agnes et le chemin de l'export du workflow FastH3 validé. La clé peut aussi être saisie dans l'interface; elle n'est pas écrite dans les fichiers du run.

```powershell
$env:AGNES_API_KEY = "<votre clé Agnes>"
$env:AGNES_API_BASE_URL = "https://apihub.agnes-ai.com/v1"
$env:AGNES_TEXT_MODEL = "agnes-2.5-flash"
$env:AGNES_IMAGE_MODEL = "agnes-image-2.1-flash"
$env:NEWSREEL_H3_API_WORKFLOW = "C:\Users\saill\Downloads\videomaker\reference\fasth3_api_workflow.json"
```

Une copie de ces variables peut être placée dans `.env` (voir `.env.example`); le bridge charge ce fichier au démarrage. Ne commitez jamais `.env`.

Lancer le bridge local :

```powershell
python bridge.py
```

Puis ouvrir **http://127.0.0.1:8000**. Le bouton « Démo hors-ligne » fabrique des actualités, images, audio et trois clips vidéo synthétiques, puis exécute le vrai moteur FFmpeg sans contacter Agnes, Modal ou un GPU.

## Préparer le worker Modal (premier test réel)

1. Vérifier que le volume de smoke nommé `fasth3-models` existe bien et contient les mêmes fichiers de poids que le test FastH3 validé.
2. Depuis ce checkout Windows, installer le client Modal dans le venv et s'authentifier via la procédure Modal habituelle :
   ```powershell
   python -m pip install -r requirements-modal.txt
   modal setup
   ```
3. Exporter en **format API** le workflow réellement utilisé par `fasth3_push_test.py` (ComfyUI → *Save / Export API workflow*) vers le chemin donné dans `NEWSREEL_H3_API_WORKFLOW`. Le graphe doit inclure ses nœuds validés d'image-vers-vidéo, FastH3 8-Step V2 et Video Sparse Attention. Le worker conserve les choix de checkpoint, VAE, text encoder, attention/VSA, sampler et autres nœuds du fichier.
4. Déployer le worker une fois :
   ```powershell
   modal deploy modal_h3.py
   ```
   Le déploiement construit ComfyUI dans l'image Modal et monte `fasth3-models` sous `/mnt/fasth3-models`; aucun clip n'est généré pendant l'installation.
5. Démarrer `python bridge.py`, saisir la clé Agnes dans l'interface, garder 3 sujets, puis cliquer **Lancer le JT**. Le bridge récupère le RSS, appelle Agnes, produit les quatre images, synthétise les trois prises host, envoie le batch FastH3 une seule fois, puis assemble localement.
6. Suivre les étapes ou `GET /run/<run_id>`. Le résultat est `output/<run_id>/newsreel_final.mp4` et peut être téléchargé depuis la carte **JT FINAL**.

**Important :** tant que le fichier `reference/fasth3_push_test.py` et son workflow API exporté ne sont pas réintroduits/configurés, le bridge bloque le démarrage réel **avant tout appel Agnes/Modal**. N'exportez pas un workflow différent si l'objectif est de reproduire à l'identique le test validé.

## Démonstration et tests hors-ligne

Aucune de ces commandes ne contacte Agnes, Modal ou un GPU :

```powershell
python -m pip install -r requirements-dev.txt
python -m newsreel.demo
python -m pytest -q
```

Le test d'intégration génère des assets synthétiques puis vérifie réellement avec ffprobe : existence du MP4, durée 45–60 s, 1080×1920, 24 fps et présence d'audio. Les tests de contrat garantissent aussi que le dialogue reporter exact est inclus dans `<d>[French] …</d>` et que les paramètres H3 validés ne dérivent pas.

## API locale

- `GET /health` — état local, disponibilité FFmpeg et configuration non secrète
- `GET /config` — paramètres UI Agnes/TTS
- `POST /runs` — démarre un run Agnes → H3 batch → assemblage
- `POST /demo` — démarre un run de fixtures hors-ligne
- `POST /render-h3-batch` — relance le batch H3 pour un run ayant scénario/images
- `POST /assemble` — monte le `timeline.json` d'un run existant
- `GET /run/<run_id>` — manifeste, progression, timeline et lien final
- `GET /output/<run_id>/<path>` — lecture/téléchargement des fichiers du run

Chaque run a son dossier propre; les chemins d'assets de `timeline.json` sont relatifs au run et la timeline est la source de vérité du montage.
