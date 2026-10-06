# NewsReel V2 — production full-H3

NewsReel transforme des actualités Google News en un JT vertical satirique original puis produit :

```text
output/<run_id>/newsreel_final.mp4
```

Le pipeline de production est :

```text
Google News RSS
  → Agnes texte : scénario factuel + sketch satirique
  → Agnes image : 1 keyframe host + 1 keyframe reporter par sujet
  → FastH3 / MiniMax H3 : host + reporter avec audio natif
  → FFmpeg local : overlays, intro/outro, normalisation, concat
  → MP4 1080×1920 / 24 fps / H.264 + AAC
```

Pour 3 sujets : 6 clips H3.  
Pour 7 sujets : 14 clips H3.  
Le batch est traité séquentiellement dans un seul conteneur Modal/ComfyUI.

## Identité créative

`newsreel/creative.py` contient la couche créative historique restaurée :

- 25 directions artistiques ;
- 16 palettes ;
- 3 intensités réellement actives : `subtle`, `moderate`, `strong` ;
- costumes rétrofuturistes ;
- décors hallucinatoires ;
- gags physiques ;
- personnages secondaires ;
- Stanislavski ;
- caméra, lumière et texture ;
- prompts image host/reporter ;
- prompts vidéo host/reporter.

L'intensité change la densité et l'escalade visuelle sans modifier les faits.

## Garde-fous factuels

Le scénario Agnes reçoit pour chaque actualité :

- le titre exact ;
- la source ;
- la date ;
- le contexte RSS nettoyé.

Le modèle doit sélectionner des titres exacts parmi les sources fournies. Les titres inventés
ou dupliqués rendent le scénario invalide et déclenchent une correction automatique unique.

NewsReel ne duplique plus silencieusement un sujet lorsqu'Agnes retourne un mauvais nombre
de segments : le scénario doit contenir exactement le nombre demandé.

## FastH3 / Modal

Configuration validée et figée dans `newsreel/h3_workflow.py` :

- FastH3 8-Step V2 / MiniMax H3 ;
- 768×1344 ;
- 243 frames ;
- 24 fps ;
- 10,125 s ;
- 8 steps ;
- sampler `res_multistep` ;
- scheduler `simple` ;
- audio natif H3 ;
- sigma shift vidéo 10 / audio 3 ;
- Comfy Kitchen attention + VSA ;
- L40S 48 Go ;
- 8 CPU ;
- 98304 MiB RAM ;
- `max_containers=1` ;
- `single_use_containers=True`.

ComfyUI est piné sur :

```text
d49e888586dd8ae012c0667b33466b815fee07f7
```

Cette révision correspond au HEAD ComfyUI disponible lors du premier smoke H3 réussi du
6 octobre 2026. Un futur changement de `master` ne peut donc plus casser silencieusement
un redéploiement.

Poids attendus dans le volume Modal `fasth3-models` :

```text
diffusion_models/fastvideo_fasth3_8step_v2_pruned_int8_convrot.safetensors
text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors
vae/minimax_h3_video_vae_int8_convrot.safetensors
vae/minimax_h3_audio_vae_fp32.safetensors
```

## Installation Windows

```powershell
git clone https://github.com/saillardsimon71-del/NewsReels.git
cd NewsReels

py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r requirements-modal.txt
```

FFmpeg + ffprobe doivent être disponibles :

```powershell
ffmpeg -version
ffprobe -version
```

Copier éventuellement `.env.example` vers `.env`.

## Déployer le worker Modal

Après une modification de `modal_h3.py`, `newsreel/h3_workflow.py`,
`newsreel/h3_worker_contract.py` ou de la couche de prompts utilisée dans le worker :

```powershell
modal deploy modal_h3.py
```

Le démarrage d'un run réel effectue ensuite un preflight du déploiement Modal **avant**
de consommer un appel Agnes.

## Lancer le studio

```powershell
python bridge.py
```

Ouvrir :

```text
http://127.0.0.1:8000
```

Par défaut le bridge écoute uniquement sur `127.0.0.1`.

Variables optionnelles :

```text
NEWSREEL_HOST=127.0.0.1
NEWSREEL_PORT=8000
```

## Interface

Le studio permet de choisir :

- recherche / thème Google News ;
- catégorie ;
- 1 à 7 sujets ;
- direction artistique ;
- palette ;
- intensité ;
- modèles et endpoint Agnes.

La clé Agnes est utilisée en mémoire puis effacée du champ après lancement. Elle n'est pas
écrite dans `scenario.json`, `run_manifest.json` ou les logs applicatifs.

## Reprise après erreur

Chaque run est isolé dans `output/<run_id>`.

Le manifeste persiste :

- étapes ;
- fichiers ;
- paramètres créatifs ;
- modèles Agnes ;
- contrat H3 complet ;
- erreurs ;
- métriques de génération.

L'interface expose :

- **Reprendre le run** : si les clips H3 existent, remonte le MP4 ; sinon, si les keyframes
  Agnes existent, relance H3 puis remonte le MP4 ;
- **Remonter le MP4** : reconstruit `timeline.json` depuis les clips H3 existants puis
  relance uniquement FFmpeg.

Si le run s'est arrêté avant que les keyframes Agnes soient complètes, il faut démarrer un
nouveau run : la clé Agnes n'est volontairement jamais persistée.

Endpoints compatibles :

- `POST /resume`
- `POST /render-h3-batch`
- `POST /assemble`

## Démo et validation locale

```powershell
python -m pip install -r requirements-dev.txt
python -m newsreel.demo
python -m pytest -q
ruff check .
python -m compileall -q newsreel bridge.py modal_h3.py
```

La démo hors-ligne ne contacte ni Agnes ni Modal et n'utilise aucun GPU.

## Architecture

```text
bridge.py                       bridge FastAPI local + UI + reprise
modal_h3.py                     worker Modal full-H3
newsreel/creative.py            couche créative
newsreel/agnes.py               client Agnes + validation scénario/images
newsreel/news.py                Google News RSS + nettoyage contexte
newsreel/models.py              modèles scénario/timeline
newsreel/h3_workflow.py         contrat + graphe FastH3
newsreel/h3_worker_contract.py  jobs host/reporter + client Modal
newsreel/timeline.py            timeline finale
newsreel/assembler.py           montage FFmpeg local
newsreel/run_store.py           isolation/manifeste des runs
newsreel/demo.py                smoke hors-ligne
web/index.html                  studio local
legacy/ltx/                     ancien prototype archivé
```

## Entrées de production

Utiliser uniquement :

```text
python bridge.py
modal deploy modal_h3.py
```

Les anciens fichiers LTX ont été déplacés dans `legacy/ltx/` et ne font pas partie du
runtime de production.
