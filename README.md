# NewsReel V1 — générateur de JT local → MP4

NewsReel assemble un journal vertical dans `output/<run_id>/newsreel_final.mp4`. Le run par défaut contient trois sujets et envoie **un seul batch Modal** pour les reporters. Agnes prépare le scénario et les images; le modèle image par défaut est `agnes-image-2.5-flash` avec `size="1K"` et `ratio="9:16"`. Edge TTS génère la voix du présentateur; le plateau est animé et le montage final est réalisé localement par FFmpeg.

## Intégration FastH3

Le graphe ComfyUI API est construit directement en Python par `newsreel/h3_workflow.py` et exécuté par `modal_h3.py`. Aucun export JSON ComfyUI, fichier de workflow ou chemin de workflow externe n'est requis. Les modèles, réglages et connexions du graphe sont fixés dans le code et vérifiés hors ligne par les tests.

Configuration appliquée :

- **FastH3 8-Step V2 / MiniMax H3**, image **768×1344**, **243 frames à 24 fps** (10,125 s), **BasicScheduler `simple`, 8 étapes**, sampler **`res_multistep`**;
- audio natif H3 avec `MiniMaxH3SigmaShift` vidéo **10** / audio **3**;
- `ModelAttentionBackend` **`comfy kitchen attention`** et `BlockSparseAttention` VSA (`keep_percent=10`, début `0.2`, fin `1`);
- UNet `fastvideo_fasth3_8step_v2_pruned_int8_convrot.safetensors`;
- text encoder `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors`;
- VAE vidéo `minimax_h3_video_vae_int8_convrot.safetensors` et VAE audio `minimax_h3_audio_vae_fp32.safetensors`.

Pour les trois reporters, le bridge fait un seul appel Modal. Le worker démarre un ComfyUI sur un unique conteneur L40S, traite les clips séquentiellement avec les mêmes IDs de nœuds chargeurs, puis termine ComfyUI et détruit le conteneur. Ressources : **8 CPU, 98304 MiB, timeout 5400 s, un conteneur maximum, `single_use_containers=True`**; ComfyUI démarre avec `--disable-comfy-compiler`. Les poids sont lus depuis le volume Modal existant `fasth3-models`; le worker refuse de substituer un modèle manquant.

### Note sur les références de smoke test

Le checkout inspecté ne contient pas `reference/fasth3_push_test.py`. Le graphe ci-dessus applique les paramètres FastH3 explicitement fournis et ceux du template public Comfy-Org; cette absence ne doit pas être interprétée comme une preuve de parité bit à bit avec un smoke test privé. Le worker clone `https://github.com/Comfy-Org/ComfyUI.git`, dépôt déjà utilisé par le prototype Modal présent sur `origin/main`, mais la révision précise du push-test FastH3 n'a pas pu être vérifiée depuis ce checkout.

## Architecture

```text
bridge.py                     API FastAPI locale + progression/polling + livraison MP4
modal_h3.py                   worker Modal: 1 L40S, 1 ComfyUI, batch séquentiel
newsreel/config.py            configuration Windows / chemins FFmpeg / Agnes
newsreel/models.py            scénario, scène et timeline sérialisables
newsreel/timeline.py          timeline source de vérité (host → reporter → ...)
newsreel/agnes.py             client texte + image Agnes OpenAI-compatible
newsreel/news.py              Google News RSS français
newsreel/tts.py               abstraction TTS et adaptateur Edge TTS
newsreel/h3_workflow.py       graphe FastH3 API construit dans le code
newsreel/h3_worker_contract.py contrat fixe et appel Modal batch unique
newsreel/assembler.py         montage local H.264/AAC, titres, audio et validation ffprobe
newsreel/run_store.py         isolation `output/<run_id>` et run_manifest.json
web/index.html                interface sans framework
newsreel/demo.py              fixtures synthétiques, entièrement hors-ligne
```

Les runs sont isolés, `timeline.json` reste la source de vérité du montage, le TTS host Edge s'exécute sur la machine locale et FFmpeg produit `newsreel_final.mp4` localement. Le mode démo synthétique n'appelle ni Agnes, ni Modal, ni GPU.

## Installation Windows (PowerShell)

Chemin cible : `C:\Users\saill\Downloads\videomaker`.

```powershell
cd C:\Users\saill\Downloads\videomaker
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Installer FFmpeg (les exécutables `ffmpeg` **et** `ffprobe`) et rouvrir le terminal pour actualiser le PATH :

```powershell
winget install --id Gyan.FFmpeg.Shared -e
ffmpeg -version
ffprobe -version
```

Si FFmpeg n'est pas dans le PATH, indiquer ses exécutables :

```powershell
$env:NEWSREEL_FFMPEG = "C:\tools\ffmpeg\bin\ffmpeg.exe"
$env:NEWSREEL_FFPROBE = "C:\tools\ffmpeg\bin\ffprobe.exe"
```

## Préparer Modal et lancer le premier vrai run

1. Vérifier dans le compte Modal que le volume existant `fasth3-models` contient **les quatre noms de fichiers exacts ci-dessus** dans les catégories ComfyUI `diffusion_models`, `text_encoders` et `vae`. Le worker échoue explicitement si l'un manque.
2. Installer le client Modal et l'associer au compte habituel :
   ```powershell
   python -m pip install -r requirements-modal.txt
   modal setup
   modal volume ls fasth3-models
   ```
3. Déployer le worker (cela construit l'image ComfyUI; **aucun rendu GPU n'est déclenché par le déploiement**) :
   ```powershell
   modal deploy modal_h3.py
   ```
4. Configurer Agnes et démarrer l'interface locale. La clé peut aussi être saisie directement dans l'interface; elle n'est pas écrite dans le manifeste du run.
   ```powershell
   $env:AGNES_API_KEY = "<votre clé Agnes>"
   $env:AGNES_API_BASE_URL = "https://apihub.agnes-ai.com/v1"
   $env:AGNES_TEXT_MODEL = "agnes-2.5-flash"
   $env:AGNES_IMAGE_MODEL = "agnes-image-2.5-flash"
   $env:AGNES_IMAGE_SIZE = "1K"
   $env:AGNES_IMAGE_RATIO = "9:16"
   $env:NEWSREEL_MODAL_APP = "newsreel-fasth3"
   $env:NEWSREEL_MODAL_FUNCTION = "render_h3_batch"
   python bridge.py
   ```
5. Ouvrir **http://127.0.0.1:8000**, garder trois sujets et cliquer **Lancer le JT**. NewsReel récupère le RSS, appelle Agnes, synthétise les prises host, envoie les trois reporters dans un seul appel Modal séquentiel, puis assemble le tout localement. Le résultat est `output/<run_id>/newsreel_final.mp4`.

Une copie des variables non secrètes est disponible dans `.env.example`; le bridge charge `.env` au démarrage. Ne commitez jamais `.env`.

## Démonstration et tests hors-ligne

Les commandes suivantes n'appellent pas Agnes, Modal ou de GPU :

```powershell
python -m pip install -r requirements-dev.txt
python -m newsreel.demo
python -m pytest -q
```

La démo fabrique des assets synthétiques puis vérifie avec ffprobe le MP4, sa durée, sa résolution 1080×1920, ses 24 fps et son audio. Les tests de contrat vérifient hors ligne les modèles FastH3, les dimensions, frames/fps/steps, VSA, shifts, dialogue français exact, audio natif, le graphe construit dans le code et l'unicité de l'appel Modal batch.

## API locale

- `GET /health` — état local, disponibilité FFmpeg, graphe intégré et dépendances
- `GET /config` — paramètres UI Agnes/TTS
- `POST /runs` — démarre un run Agnes → H3 batch → assemblage
- `POST /demo` — démarre un run de fixtures hors-ligne
- `POST /render-h3-batch` — relance le batch H3 pour un run ayant scénario/images
- `POST /assemble` — monte le `timeline.json` d'un run existant
- `GET /run/<run_id>` — manifeste, progression, timeline et lien final
- `GET /output/<run_id>/<path>` — lecture/téléchargement des fichiers du run

Chaque run a son dossier propre; les chemins d'assets de `timeline.json` sont relatifs au run et la timeline reste la source de vérité du montage.
